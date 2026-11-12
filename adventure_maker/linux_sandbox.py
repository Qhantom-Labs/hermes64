"""Linux child sandbox: bubblewrap (bwrap) argv, a one-time functional probe, and the explicit unconfined fallback.

Design: docs/LINUX-RUNNER-DESIGN.md. Standard library only. Every child gets new user, mount, PID, IPC, UTS and
network namespaces (only loopback), an empty tmpfs root with read-only system folders, the plugin folder and the tool
itself bound read-only, and the game project as the only writable host path. The outer stdlib shim sets safe
memory/CPU/file/core limits then execs bwrap; an inner shim applies NPROC after namespace creation and execs the tool.
Runner keeps the macOS run loop: new session,
killpg at every exit; --die-with-parent plus the PID namespace tear the whole tree down.

Default is fail closed: without a bwrap that passes the probe every child is refused (sandbox_unavailable) with the
reason and the fix. HERMES64_LINUX_RUNNER=unconfined is an owner opt-in used only when the probe fails: no
OS-enforced network or write confinement; process-group kill and rlimits only.

Host access is injectable (which/read/run/exists) so tests simulate distributions on any OS. Nothing runs at import.
"""
import errno
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

RUNNER_ENV = 'HERMES64_LINUX_RUNNER'
UNCONFINED = 'unconfined'
DISCLOSURE = 'no OS-enforced network or write confinement; process-group kill and rlimits only'
BWRAP_DIRS = ('/usr/bin', '/usr/local/bin', '/bin')
# Read-only system folders (present ones only; merged-/usr symlinks such as /bin -> usr/bin are recreated as symlinks).
SYSTEM_DIRS = ('/usr', '/bin', '/sbin', '/lib', '/lib32', '/lib64', '/libx32', '/opt', '/nix', '/gnu',
               '/run/current-system')
# /etc minimal: the dynamic loader, user/group lookup, time zone, fonts and Debian alternatives (program symlinks).
ETC_ENTRIES = ('alternatives', 'fonts', 'group', 'ld.so.cache', 'ld.so.conf', 'ld.so.conf.d', 'localtime',
               'nsswitch.conf', 'os-release', 'passwd')
REQUIRED_FLAGS = ('--unshare-all', '--die-with-parent', '--new-session')
LIMITS = {'RLIMIT_AS': 16 * 1024 ** 3, 'RLIMIT_CPU': 3600, 'RLIMIT_NOFILE': 4096, 'RLIMIT_CORE': 0}
NPROC_HEADROOM = 512
PROBE_TIMEOUT = 10
PROBE_ADDRESS = ('192.0.2.1', 9)          # TEST-NET-1 (RFC 5737): never routed, so no third party is ever contacted
PLUGIN_ROOT = Path(__file__).resolve().parents[1]

# The rlimit shim: lower soft and hard limits (never raise them), then exec the real command. Lowering cannot fail
# with EPERM; any other error ends the run before the command starts (fail closed).
SHIM = ('import json,os,resource,sys\n'
        'def visible_tasks():\n'
        ' n=0\n'
        ' for p in os.listdir("/proc"):\n'
        '  if not p.isdigit(): continue\n'
        '  try:\n'
        '   if os.stat("/proc/"+p).st_uid==os.getuid(): n+=len(os.listdir("/proc/"+p+"/task"))\n'
        '  except FileNotFoundError: pass\n'
        ' return max(n,1)\n'
        'for k,v in sorted(json.loads(sys.argv[1]).items()):\n'
        ' r=getattr(resource,k,None)\n'
        ' if r is None: continue\n'
        ' if v=="visible_tasks+512": v=visible_tasks()+512\n'
        ' s,h=resource.getrlimit(r)\n'
        ' v=min([v]+[x for x in (s,h) if x!=resource.RLIM_INFINITY])\n'
        ' resource.setrlimit(r,(v,v))\n'
        'os.execv(sys.argv[3],sys.argv[3:])\n')

# Runs inside the probe sandbox: argv = writable dir, hidden host file.
PROBE = ('import errno,os,socket,subprocess,sys\n'
         'w,hidden=sys.argv[1],sys.argv[2]\n'
         'out=[]\n'
         'try:\n'
         ' open(os.path.join(w,"inside"),"w").write("1"); out.append("WRITE_INSIDE_OK")\n'
         'except OSError as e: out.append("WRITE_INSIDE_FAILED:"+str(e.errno))\n'
         'try:\n'
         ' open("/usr/.hermes64-probe","w").write("1"); out.append("WRITE_SYSTEM_OK")\n'
         'except OSError: out.append("WRITE_SYSTEM_DENIED")\n'
         'out.append("HIDDEN_VISIBLE" if os.path.exists(hidden) else "HIDDEN_ABSENT")\n'
         's=socket.socket(); s.settimeout(1)\n'
         'try:\n'
         ' s.connect((' + repr(PROBE_ADDRESS[0]) + ',' + str(PROBE_ADDRESS[1]) + ')); out.append("NET_OPEN")\n'
         'except OSError as e: out.append("NET_BLOCKED" if e.errno==errno.ENETUNREACH else "NET_OTHER:"+str(e.errno))\n'
         'try:\n'
         ' c=subprocess.run([sys.executable,"-I","-S","-c","pass"],env=dict(os.environ),timeout=2,stdin=subprocess.DEVNULL)\n'
         ' out.append("CHILD_OK" if c.returncode==0 else "CHILD_FAILED:"+str(c.returncode))\n'
         'except (OSError,subprocess.SubprocessError) as e: out.append("CHILD_FAILED:"+str(e))\n'
         'print(" ".join(out))\n')
PROBE_OK = ('WRITE_INSIDE_OK', 'WRITE_SYSTEM_DENIED', 'HIDDEN_ABSENT', 'NET_BLOCKED', 'CHILD_OK')

INSTALL_LINES = ('Debian/Ubuntu: sudo apt install bubblewrap; Fedora: sudo dnf install bubblewrap; '
                 'Arch: sudo pacman -S bubblewrap; openSUSE: sudo zypper install bubblewrap; Alpine: sudo apk add '
                 'bubblewrap')
OPT_IN = ('Or, knowingly, set %s=%s and restart Hermes: children then run without bwrap (%s). docs/LINUX.md.'
          % (RUNNER_ENV, UNCONFINED, DISCLOSURE))

_CACHE = {}


def reset():
    """Forget the cached probe result (tests; doctor's explicit refresh)."""
    _CACHE.clear()


def _read(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except OSError:
        return None


def _is_exe(path):
    return os.path.isfile(path) and os.access(path, os.X_OK)


def find_bwrap(env=None, is_exe=_is_exe):
    """Absolute path of bwrap: the system folders first, then the PATH of env; None when absent."""
    env = os.environ if env is None else env
    dirs = list(BWRAP_DIRS) + [d for d in (env.get('PATH') or '').split(os.pathsep) if d and d not in BWRAP_DIRS]
    for d in dirs:
        candidate = os.path.join(d, 'bwrap')
        if os.path.isabs(candidate) and is_exe(candidate):
            return candidate
    return None


def host_facts(read=_read, exists=os.path.exists, env=None):
    """What the kernel and the environment say about unprivileged user namespaces (None = not reported)."""
    env = os.environ if env is None else env

    def num(path):
        text = read(path)
        try:
            return int(text.strip()) if text is not None else None
        except ValueError:
            return None
    version = (read('/proc/version') or '').lower()
    wsl = 'wsl2' if ('microsoft' in version and ('wsl2' in version or 'microsoft-standard' in version)) else \
        'wsl1' if 'microsoft' in version else None
    container = bool(exists('/.dockerenv') or exists('/run/.containerenv') or env.get('container'))
    return {'unprivileged_userns_clone': num('/proc/sys/kernel/unprivileged_userns_clone'),
            'max_user_namespaces': num('/proc/sys/user/max_user_namespaces'),
            'apparmor_restrict_unprivileged_userns': num('/proc/sys/kernel/apparmor_restrict_unprivileged_userns'),
            'container': container, 'wsl': wsl}


APPARMOR_FIX = ('Ubuntu restricts unprivileged user namespaces with AppArmor '
                '(kernel.apparmor_restrict_unprivileged_userns=1) and bwrap has no profile that allows one. Fix: '
                'give bwrap an AppArmor profile with the userns permission (the file text is in docs/LINUX.md, '
                '"Ubuntu 24.04") and load it as root with apparmor_parser -r /etc/apparmor.d/bwrap; or, system-wide and '
                'weaker, as root: sysctl -w kernel.apparmor_restrict_unprivileged_userns=0.')


def diagnose(stderr, facts):
    """(reason, sentence with the fix) for a probe that failed to start or failed a check."""
    text = (stderr or '').strip().splitlines()
    first = text[-1][:300] if text else 'no output'
    if facts.get('wsl') == 'wsl1':
        return 'wsl1', 'WSL 1 has no Linux namespaces, so bwrap cannot sandbox anything. Use WSL 2 (wsl --set-version <distro> 2).'
    if facts.get('unprivileged_userns_clone') == 0:
        return 'userns_disabled', ('Unprivileged user namespaces are off (kernel.unprivileged_userns_clone=0), so bwrap '
                                   'cannot start. Fix, as root: sysctl -w kernel.unprivileged_userns_clone=1 (persist it in '
                                   '/etc/sysctl.d/). bwrap said: ' + first)
    if facts.get('max_user_namespaces') == 0:
        return 'userns_disabled', ('User namespaces are capped at 0 (user.max_user_namespaces=0), so bwrap cannot '
                                   'start. Fix, as root: sysctl -w user.max_user_namespaces=15000 (persist it in '
                                   '/etc/sysctl.d/). bwrap said: ' + first)
    if facts.get('apparmor_restrict_unprivileged_userns') == 1:
        return 'apparmor_userns', APPARMOR_FIX + ' bwrap said: ' + first
    if 'Resource temporarily unavailable' in (stderr or ''):
        return 'namespace_resources', (first + '. Likely namespace/task resource exhaustion: check inherited '
                'RLIMIT_NPROC (tasks/threads, not just process leaders), user namespace ceilings, and cgroup '
                'pids/memory limits. Hermes64 applies its own NPROC limit only after bwrap setup; a stricter '
                'inherited limit still applies. See docs/LINUX.md and the Linux retest addendum.')
    if facts.get('container'):
        return 'container', ('This looks like a container, and its security policy blocks the user namespaces bwrap '
                             'needs. Run Hermes on the host, or allow user namespaces in the container. bwrap said: '
                             + first)
    return 'probe_failed', 'bwrap could not start the probe sandbox. bwrap said: ' + first


def _under(path, roots):
    p = str(path)
    return any(p == r or p.startswith(r.rstrip('/') + '/') for r in roots)


def tool_binds(exe, read=_read, exists=os.path.exists):
    """Read-only host paths a tool needs inside the sandbox, beyond the system folders.

    Godot is one file. Blender needs its own folder (lib/ and the version folder sit beside the binary). Python needs
    its virtual environment (pyvenv.cfg one level above bin/) plus the base installation named by pyvenv.cfg's home,
    or its own prefix. Paths already under a system folder need nothing."""
    exe = str(exe)
    if not exe.startswith('/') or _under(exe, SYSTEM_DIRS):
        return []
    path = Path(exe)
    name = path.name.lower()
    if name.startswith('godot'):
        return [exe]
    if name.startswith('python'):
        root = path.parent.parent
        cfg = read(str(root / 'pyvenv.cfg'))
        if cfg is not None:
            binds = [str(root)]
            for line in cfg.splitlines():
                key, _sep, value = line.partition('=')
                if key.strip().lower() == 'home' and value.strip().startswith('/'):
                    base = Path(value.strip()).parent      # home = <base prefix>/bin
                    if not _under(base, SYSTEM_DIRS) and str(base) != '/':
                        binds.append(str(base))
            return binds
        return [str(root)] if str(root) != '/' else [exe]
    return [str(path.parent)]


def _resolved(value):
    try:
        return str(Path(value).resolve())
    except OSError:
        return str(value)


def bwrap_argv(bwrap, project_root, argv, plugin_root=PLUGIN_ROOT, extra_ro=(), exists=os.path.exists,
               islink=os.path.islink, readlink=os.readlink, read=_read, cap_drop=True):
    """The full bwrap command for one child (argv list; no shell anywhere)."""
    cmd = [bwrap] + list(REQUIRED_FLAGS) + (['--cap-drop', 'ALL'] if cap_drop else [])
    for d in SYSTEM_DIRS:
        if islink(d):
            cmd += ['--symlink', readlink(d), d]
        elif exists(d):
            cmd += ['--ro-bind', d, d]
    for name in ETC_ENTRIES:
        path = '/etc/' + name
        if exists(path):
            cmd += ['--ro-bind', path, path]
    cmd += ['--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
            '--perms', '0700', '--dir', '/tmp/hermes64-runtime',
            '--perms', '0700', '--dir', '/tmp/hermes64-runtime/pulse']
    project = str(project_root)
    ro = [str(plugin_root)] + list(extra_ro)
    if argv:
        # Both the name as invoked (a venv's bin/python3 symlink: the venv layout decides what Python imports) and
        # the file it resolves to (the real Godot/Blender/base interpreter).
        ro += tool_binds(argv[0], read=read, exists=exists) + tool_binds(_resolved(argv[0]), read=read, exists=exists)
    for value in list(argv[1:]):
        if value.startswith('/') and exists(value):
            ro.append(value)
    binds, seen = [], set()
    for path in sorted(set(ro), key=lambda p: (p.count('/'), p)):
        if path in seen or _under(path, SYSTEM_DIRS) or _under(path, [project]) or \
                any(_under(path, [b]) for b, _rw in binds):
            continue
        seen.add(path)
        binds.append((path, False))
    binds.append((project, True))
    # Parents before children: bwrap applies binds in order, so a writable project inside a read-only tree still works.
    for path, rw in sorted(binds, key=lambda b: (b[0].count('/'), b[0])):
        cmd += ['--bind' if rw else '--ro-bind', path, path]
    return cmd + ['--'] + list(argv)


def user_process_count(listdir=os.listdir, stat=os.stat, uid=None):
    """Processes the current user owns (RLIMIT_NPROC counts all of them, inside any namespace)."""
    uid = os.getuid() if uid is None else uid
    count = 0
    try:
        names = listdir('/proc')
    except OSError:
        return 0
    for name in names:
        if name.isdigit():
            try:
                count += stat('/proc/' + name).st_uid == uid
            except OSError:
                continue
    return count


def limits(nproc=None):
    """Unconfined/default-shim limits: host process-leader count + headroom is an approximate fork brake.
    Confined command() instead sizes NPROC inside the new namespace and never lowers it before bwrap setup."""
    values = dict(LIMITS)
    values['RLIMIT_NPROC'] = (user_process_count() if nproc is None else nproc) + NPROC_HEADROOM
    return values


def shim_argv(argv, python=None, values=None):
    """[python -I -S -c SHIM limits --] + argv: set rlimits in a fresh process, then exec argv[0]."""
    return [python or sys.executable, '-I', '-S', '-c', SHIM,
            json.dumps(limits() if values is None else values, sort_keys=True), '--'] + list(argv)


def _help(bwrap, run=subprocess.run):
    from .runner import scratch_env
    try:
        with scratch_env() as env:
            out = run([bwrap, '--help'], capture_output=True, text=True, encoding='utf-8', errors='replace',
                      timeout=PROBE_TIMEOUT, stdin=subprocess.DEVNULL, env=env)
        return (out.stdout or '') + (out.stderr or '')
    except (OSError, subprocess.SubprocessError):
        return ''


def probe(bwrap, run=subprocess.run, python=None, base=None, read=_read, exists=os.path.exists, env=None):
    """Run the real probe once: {'ok', 'reason', 'detail', 'cap_drop'}. Never raises for a host problem."""
    from .runner import Runner
    from .safety import Fault, Project
    facts = host_facts(read=read, exists=exists, env=env)
    help_text = _help(bwrap, run)
    missing = [f for f in REQUIRED_FLAGS if help_text and f not in help_text]
    if missing:
        return {'ok': False, 'reason': 'bwrap_too_old', 'cap_drop': False,
                'detail': 'This bwrap is too old: it lacks %s. Install bubblewrap 0.4 or newer (%s).'
                          % (', '.join(missing), INSTALL_LINES)}
    cap_drop = '--cap-drop' in help_text if help_text else True
    python = python or sys.executable
    base = Path(base or os.path.join(os.environ.get('XDG_CACHE_HOME') or os.path.expanduser('~/.cache'), 'hermes64'))
    try:
        base.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix='bwrap-probe-', dir=str(base)))
    except OSError as exc:
        return {'ok': False, 'reason': 'probe_folder', 'cap_drop': cap_drop,
                'detail': 'Could not make the probe folder in %s: %s' % (base, exc)}
    try:
        try:
            project = Project(str(work.resolve()), 'project', create=True)
            writable = project.root
            hidden = work / 'hidden-host-file'
            hidden.write_text('not for the sandbox\n', encoding='utf-8')
        except (OSError, Fault) as exc:
            return {'ok': False, 'reason': 'probe_folder', 'cap_drop': cap_drop,
                    'detail': 'Could not prepare the managed readiness folder: %s' % exc}
        # The sentinel is derived in the child: an absolute argv path would be auto-bound read-only by command().
        code = PROBE.replace('sys.argv[2]', 'os.path.join(os.path.dirname(sys.argv[1]),"hidden-host-file")')
        argv = [python, '-I', '-S', '-c', code, str(writable)]
        candidate = {'mode': 'bwrap', 'available': True, 'bwrap': bwrap, 'cap_drop': cap_drop}
        try:
            out = Runner(project, _linux_isolation=candidate).run(argv, writable, timeout=PROBE_TIMEOUT)
        except Fault as exc:
            reason, detail = diagnose(str(exc), facts)
            if exc.code == 'timeout':
                reason, detail = 'probe_timeout', 'The runner probe timed out: ' + str(exc)
            return {'ok': False, 'reason': reason, 'cap_drop': cap_drop, 'detail': detail}
        except (OSError, ValueError) as exc:
            return {'ok': False, 'reason': 'probe_failed', 'cap_drop': cap_drop,
                    'detail': 'Runner.run could not start the readiness child: %s' % exc}
        marks = (out['stdout'] or '').split()
        if out['returncode'] != 0 or not marks:
            reason, detail = diagnose(out['stderr'], facts)
            return {'ok': False, 'reason': reason, 'detail': detail, 'cap_drop': cap_drop}
        bad = [m for m in PROBE_OK if m not in marks]
        if bad:
            return {'ok': False, 'reason': 'probe_unsafe', 'cap_drop': cap_drop,
                    'detail': 'bwrap started, but the probe saw %s (expected %s); the sandbox is not working as '
                              'required, so it is not used.' % (' '.join(marks)[:200], ' '.join(PROBE_OK))}
        return {'ok': True, 'reason': 'ok', 'detail': ' '.join(marks), 'cap_drop': cap_drop}
    finally:
        shutil.rmtree(str(work), ignore_errors=True)


def _note_off(reason_detail):
    return ('Making and rebuilding games is off on this Linux computer: Hermes64 runs Godot, Blender and Python only '
            'inside a bubblewrap (bwrap) sandbox with no network and writes confined to the project, and %s %s'
            % (reason_detail.rstrip('.') + '.', OPT_IN))


def status(env=None, refresh=False, which=None, run=subprocess.run, read=_read, exists=os.path.exists, python=None,
           base=None):
    """The Linux isolation record (same keys as platforms.isolation): bwrap when the probe passes, unconfined only
    when it fails and the owner opted in, otherwise off. One real probe per process (cached by bwrap file)."""
    env = os.environ if env is None else env
    opted = (env.get(RUNNER_ENV) or '').strip().lower() == UNCONFINED
    bwrap = (which or find_bwrap)(env)
    if bwrap is None:
        result = {'ok': False, 'reason': 'bwrap_missing',
                  'detail': 'bubblewrap (bwrap) is not installed. Install it (%s), then restart Hermes.' % INSTALL_LINES,
                  'cap_drop': False}
    else:
        try:
            st = os.stat(bwrap)
            key = (bwrap, st.st_mtime_ns, st.st_size, python or sys.executable)
        except OSError:
            key = (bwrap, None, None, python or sys.executable)
        if refresh or key not in _CACHE:
            _CACHE[key] = probe(bwrap, run=run, python=python, base=base, read=read, exists=exists, env=env)
        result = _CACHE[key]
    if result['ok']:
        return {'mode': 'bwrap', 'available': True, 'network_blocked': True, 'writes_confined': True,
                'bwrap': bwrap, 'reason': 'ok', 'cap_drop': result.get('cap_drop', True), 'runner_probe_ok': True,
                'note': ('Linux bubblewrap sandbox: no network, writes confined to the project folder, home folder '
                         'hidden, process tree killed at the end of each run. Readiness child via Runner.run '
                         '(same command, limits and environment) exited 0 inside the sandbox.')}
    if opted:
        return {'mode': 'unconfined', 'available': True, 'network_blocked': False, 'writes_confined': False,
                'bwrap': bwrap, 'reason': result['reason'], 'cap_drop': False,
                'note': ('Linux unconfined runner (your %s=%s opt-in; bwrap is not usable here: %s): %s.'
                         % (RUNNER_ENV, UNCONFINED, result['detail'].rstrip('.'), DISCLOSURE))}
    return {'mode': 'off', 'available': False, 'network_blocked': False, 'writes_confined': False, 'bwrap': bwrap,
            'reason': result['reason'], 'cap_drop': False, 'note': _note_off(result['detail'])}


def command(project_root, argv, iso=None, env=None, python=None, values=None):
    """The argv the runner starts for one child, or a sandbox_unavailable Fault (nothing started)."""
    from .safety import fail
    iso = iso or status(env)
    if not iso['available']:
        fail('sandbox_unavailable', 'Required no-network/write-confinement sandbox unavailable on this host; no child '
             'started. ' + iso['note'])
    if iso['mode'] == 'bwrap':
        # Never lower NPROC before clone/unshare: Linux namespace ucounts can inherit that small ceiling.
        # Evaluate the baseline only after bwrap has installed the new /proc and dropped capabilities.
        py = python or sys.executable
        safe = dict(LIMITS if values is None else values)
        nproc = safe.pop('RLIMIT_NPROC', 'visible_tasks+512')
        extra = tool_binds(py) + tool_binds(_resolved(py))
        inner = bwrap_argv(iso['bwrap'], project_root, argv, extra_ro=extra,
                           cap_drop=iso.get('cap_drop', True))
        cut = inner.index('--')
        inner = inner[:cut + 1] + shim_argv(argv, python=py, values={'RLIMIT_NPROC': nproc})
        return shim_argv(inner, python=py, values=safe)
    return shim_argv(list(argv), python=python, values=values)


def environment(paths):
    """Child environment on Linux: project-local HOME/TMPDIR/XDG_* (already in paths), system PATH, C.UTF-8."""
    out = dict(paths)
    out.update(XDG_RUNTIME_DIR='/tmp/hermes64-runtime',
               PULSE_RUNTIME_PATH='/tmp/hermes64-runtime/pulse',
               PULSE_STATE_PATH='/tmp/hermes64-runtime/pulse',
               PULSE_CLIENTCONFIG='/tmp/hermes64-runtime/client.conf',
               PULSE_SERVER='unix:/tmp/hermes64-runtime/pulse/native',
               PATH='/usr/local/bin:/usr/bin:/bin', LANG='C.UTF-8', LC_ALL='C.UTF-8',
               PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1',
               BLENDER_USER_CONFIG=paths['XDG_CONFIG_HOME'], BLENDER_USER_SCRIPTS=paths['XDG_CONFIG_HOME'],
               BLENDER_USER_DATAFILES=paths['XDG_DATA_HOME'])
    return out


def finish(result, iso):
    """Annotate a finished run with its isolation mode; a bwrap setup failure becomes sandbox_unavailable."""
    from .safety import fail
    if iso['mode'] == 'bwrap' and result['returncode'] != 0 and result['stderr'].startswith('bwrap: '):
        fail('sandbox_unavailable', 'The Linux bubblewrap sandbox could not start this child: '
             + result['stderr'].splitlines()[0][:300])
    out = dict(result)
    out['isolation'] = 'linux-bwrap' if iso['mode'] == 'bwrap' else 'linux-unconfined: ' + DISCLOSURE
    return out


__all__ = ['RUNNER_ENV', 'UNCONFINED', 'DISCLOSURE', 'find_bwrap', 'host_facts', 'diagnose', 'tool_binds',
           'bwrap_argv', 'limits', 'shim_argv', 'probe', 'status', 'command', 'environment', 'finish', 'reset',
           'errno']
