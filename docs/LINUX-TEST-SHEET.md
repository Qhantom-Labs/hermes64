# Linux test sheet v1 (about 60 minutes)

For a tester on a **real Linux computer**. Nothing on this sheet has passed yet: Linux authoring was implemented and
simulated on a Mac only ([LINUX.md](LINUX.md), [PLATFORM-EVIDENCE.md](PLATFORM-EVIDENCE.md)). Record what really
happens, pass or fail; never retype or tidy output. The receipt template is
[receipts/LINUX-RECEIPT-TEMPLATE.md](receipts/LINUX-RECEIPT-TEMPLATE.md).

Rules:
- Use a scratch folder (`$T` below) and, for the Hermes part, a separate Hermes profile or `HERMES_HOME`, so the
  tester's own setup is untouched. Commands marked **sudo** change the machine: run them only with the machine
  owner's approval and undo them as written.
- Run each block as written, from a normal user account (not root). Every step says **PASS if** / **FAIL if**.
  On a FAIL: save the output, note the step, continue with the next part unless the step says stop.
- No secrets in receipts: no tokens, no `.env`, no `config.yaml`, no hostnames or user names (replace them with
  `<host>` / `<user>`).

## A. Preflight (10 min)

1. Folders and the facts to record:

   ```sh
   export T="$HOME/h64-test"; export R="$T/receipt"; mkdir -p "$T" "$R/outputs"
   { date -u +%FT%TZ; cat /etc/os-release; uname -srm; nproc; free -m | head -2; df -h "$T" | tail -1
     for k in kernel.unprivileged_userns_clone user.max_user_namespaces kernel.apparmor_restrict_unprivileged_userns; do
       printf '%s = %s\n' "$k" "$(sysctl -n "$k" 2>/dev/null || echo absent)"; done
     [ -e /.dockerenv ] || [ -e /run/.containerenv ] && echo CONTAINER || echo not-a-container
     grep -qi microsoft /proc/version && echo WSL || echo not-WSL
   } > "$R/outputs/a1-machine.txt" 2>&1; cat "$R/outputs/a1-machine.txt"
   ```

   **PASS if** the file lists the distribution, kernel and the three sysctl lines. (Nothing to judge yet.)
2. Install the prerequisites (**sudo**; Debian/Ubuntu shown, use your package manager elsewhere):

   ```sh
   sudo apt install bubblewrap git python3 python3-venv unzip
   ```

   Then a Python with numpy and Pillow in its own site-packages:

   ```sh
   python3 -m venv "$T/venv" && "$T/venv/bin/python3" -m pip install "numpy>=2.0,<3" "Pillow>=11.3,<14"
   export PY="$T/venv/bin/python3"
   { bwrap --version; "$PY" -c 'import sys,numpy,PIL; print(sys.version.split()[0], numpy.__version__, PIL.__version__)'
     git --version; hermes --version; } 2>&1 | tee "$R/outputs/a2-versions.txt"
   ```

   **PASS if** bwrap is 0.4 or newer, Python 3.9+ (3.11+ preferred) prints numpy 2.x and Pillow, and Hermes prints a
   version of at least 0.18.2. **FAIL if** any line errors.
3. Godot 4.6.2, by hand (the plugin's fetch is refused on Linux until a pin exists; [LINUX.md](LINUX.md)). From
   `https://github.com/godotengine/godot-builds/releases/tag/4.6.2-stable` download into `$T/dl/`:
   `Godot_v4.6.2-stable_linux.x86_64.zip` (or `.arm64.zip`), `Godot_v4.6.2-stable_export_templates.tpz` and
   `SHA512-SUMS.txt`. Then:

   ```sh
   cd "$T/dl" && sha512sum --check --ignore-missing SHA512-SUMS.txt | tee "$R/outputs/a3-sha512.txt"
   mkdir -p "$HOME/.local/bin" && python3 -m zipfile -e Godot_v4.6.2-stable_linux.x86_64.zip "$HOME/.local/bin"
   chmod +x "$HOME/.local/bin/Godot_v4.6.2-stable_linux.x86_64"
   export HERMES64_GODOT="$HOME/.local/bin/Godot_v4.6.2-stable_linux.x86_64"
   "$HERMES64_GODOT" --headless --version | tee -a "$R/outputs/a3-sha512.txt"
   TPL="$HOME/.local/share/godot/export_templates/4.6.2.stable"; mkdir -p "$TPL" "$T/tpz"
   python3 -m zipfile -e Godot_v4.6.2-stable_export_templates.tpz "$T/tpz"
   cp "$T/tpz/templates/version.txt" "$T/tpz/templates/web_nothreads_release.zip" \
      "$T/tpz/templates/windows_release_x86_64.exe" "$TPL/"
   ls -l "$TPL" | tee -a "$R/outputs/a3-sha512.txt"
   ```

   **PASS if** both archives say `OK`, Godot prints `4.6.2.stable.official.` followed by a hash, and the templates
   folder holds the three files. **FAIL if** a checksum is not `OK` (stop: do not use that file).

## B. The plugin files and the checklist (5 min)

4. Get the exact code under test, then check it. Either the release zip from the maintainers (with its SHA-256):

   ```sh
   sha256sum "$T/dl/hermes64-XXXX.zip"         # must equal the SHA-256 given with the zip
   python3 -m zipfile -e "$T/dl/hermes64-XXXX.zip" "$T/plugin" && export PLUGIN="$T/plugin/hermes64"
   ```

   or the repository at the commit under test:

   ```sh
   git clone https://github.com/Qhantom-Labs/hermes64 "$T/plugin/hermes64" && export PLUGIN="$T/plugin/hermes64"
   git -C "$PLUGIN" checkout COMMIT_UNDER_TEST && git -C "$PLUGIN" rev-parse HEAD | tee "$R/outputs/b4-commit.txt"
   ```

   Then:

   ```sh
   cd "$PLUGIN"; python3 -B tools/check_install.py 2>&1 | tee "$R/outputs/b4-check-install.txt"
   ```

   **PASS if** (zip) `PASS hermes64 ... N/N files verified` with both numbers equal. A git checkout has no
   `PACKAGE-MANIFEST.json`; its `FAIL ... missing` line is expected there: record it and go on.
5. The Linux checklist and the sandbox probe:

   ```sh
   cd "$PLUGIN"; "$PY" -B -m adventure_maker.doctor --linux-checklist 2>&1 | tee "$R/outputs/b5-checklist.txt"
   ```

   **PASS if** there is no `SIMULATED` line, the `Child runner (bwrap)` line is `OK`, Godot is `OK` at the file from
   step 3, numpy is `OK`, and the last line is `RESULT  READY to make games`.
   **FAIL if** the runner line is `OFF`: copy its whole sentence (it names the cause: AppArmor, userns sysctl,
   container, WSL 1, missing bwrap, or "the probe saw ...") into the receipt. On Ubuntu 24.04 apply the AppArmor
   profile from [LINUX.md](LINUX.md) (**sudo**), rerun, and record both outputs.

## C. Security probes through the real runner (10 min)

6. Save the probe script. It drives the plugin's own runner; outside `$T` it only creates and then removes a
   sentinel file in your home folder, reads `/proc` to find leftover processes, and kills only processes it
   started (matched by unique markers, your user only). Paste this block as it is:

```sh
cat > "$T/h64_probe.py" <<'EOF'
"""Hermes64 Linux runner probes. python3 -B h64_probe.py PLUGIN WORK [--unconfined-sim] [--no-fork]"""
import errno, os, socket, subprocess, sys, threading, time
plugin, work = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
sys.path.insert(0, plugin)
from adventure_maker import linux_sandbox, platforms, runner, safety
from adventure_maker.safety import Fault
if '--unconfined-sim' in sys.argv:            # real children; bwrap reported absent to exercise the fallback
    linux_sandbox.find_bwrap = lambda env=None, is_exe=None: None
iso = platforms.isolation()
print('ISOLATION', iso['mode'], '|', iso['note'])
if not iso['available']:
    print('RESULT runner off: no child was started')
    sys.exit(2)
confined = iso['mode'] in ('bwrap', 'sandbox-exec')
games = os.path.join(work, 'games')
os.makedirs(games, exist_ok=True)
name = 'probe%d' % int(time.time())
proj = safety.Project(games, name, create=True)
run = runner.Runner(proj)
root = str(proj.root)
home = os.path.expanduser('~')
results = []


def child(code, timeout=20):
    try:
        out = run.run([sys.executable, '-I', '-S', '-c', code], proj.root, timeout=timeout)
        return out['returncode'], out['stdout'].strip(), out['stderr'].strip()[-200:], out.get('isolation')
    except Fault as exc:
        return 'FAULT:' + exc.code, '', str(exc)[:200], None


def check(label, ok, detail):
    results.append(bool(ok))
    print('%-4s %-28s %s' % ('PASS' if ok else 'FAIL', label, detail))


def mine(match):
    """PIDs of this user's processes whose argv satisfies match (from /proc on Linux, ps elsewhere)."""
    rows = []
    if os.path.isdir('/proc/self'):
        for pid in filter(str.isdigit, os.listdir('/proc')):
            try:
                if os.stat('/proc/' + pid).st_uid != os.getuid():
                    continue
                with open('/proc/%s/cmdline' % pid, 'rb') as f:
                    rows.append((int(pid), [p.decode('utf-8', 'replace') for p in f.read().split(b'\0') if p]))
            except OSError:
                continue
    else:
        out = subprocess.run(['ps', '-U', str(os.getuid()), '-o', 'pid=,command='], capture_output=True,
                             text=True).stdout
        rows = [(int(l.split(None, 1)[0]), l.split()[1:]) for l in out.splitlines() if l.strip()]
    return [pid for pid, argv in rows if pid != os.getpid() and match(argv)]


srv = socket.socket()
srv.bind(('127.0.0.1', 0))
srv.listen(5)
port = srv.getsockname()[1]
threading.Thread(target=lambda: [srv.accept()[0].close() for _ in range(9)], daemon=True).start()
socket.create_connection(('127.0.0.1', port), 2).close()          # control: reachable outside the runner
sentinel = os.path.join(home, '.h64-probe-sentinel-' + name)
with open(sentinel, 'w') as f:
    f.write('the sandbox must not see this file\n')
esc_home = os.path.join(home, 'h64-escape-%s.txt' % name)
esc_plugin = os.path.join(plugin, 'h64-escape-%s.txt' % name)
esc_tmp = '/tmp/h64-escape-%s.txt' % name
marker = '600.%03d' % (os.getpid() % 1000)          # unique-enough sleep argument for the setsid grandchild
fork_tag = 'h64fork-' + name
is_keep = lambda argv: len(argv) == 2 and os.path.basename(argv[0]) == 'sleep' and argv[1] == marker
is_fork = lambda argv: any(fork_tag in part for part in argv)
try:
    if confined:
        NET = ('import errno,socket\n'
               'def t(a):\n'
               ' s=socket.socket(); s.settimeout(3)\n'
               ' try:\n'
               '  s.connect(a); return "OPEN"\n'
               ' except socket.timeout: return "TIMEOUT"\n'
               ' except OSError as e: return errno.errorcode.get(e.errno, str(e.errno))\n'
               'print(t(("127.0.0.1", %d)), t(("192.0.2.1", 9)))\n' % port)
        code, out, err, tag = child(NET)
        host_lo, testnet = (out.split() + ['?', '?'])[:2]
        check('net: host 127.0.0.1 service', host_lo not in ('OPEN', '?'), host_lo + ' (expect ECONNREFUSED)')
        check('net: outside address', testnet not in ('OPEN', 'TIMEOUT', '?'), testnet + ' (expect ENETUNREACH)')
        check('result isolation tag', tag == 'linux-bwrap', str(tag))
        W = ('import os\n'
             'def w(p):\n'
             ' try:\n'
             '  open(p, "w").write("x"); return "wrote-inside"\n'
             ' except OSError as e: return type(e).__name__\n'
             'print(w(%r), w("/usr/h64-escape"), w(%r), w(%r), w("inside.txt"), os.path.exists(%r))\n'
             % (esc_home, esc_plugin, esc_tmp, sentinel))
        code, out, err, tag = child(W)
        parts = (out.split() + ['?'] * 6)[:6]
        check('write: home (host copy)', not os.path.exists(esc_home), 'inside: ' + parts[0] + '; host copy absent')
        check('write: /usr', parts[1] != 'wrote-inside', parts[1])
        check('write: plugin folder', parts[2] != 'wrote-inside' and not os.path.exists(esc_plugin), parts[2])
        check('write: /tmp (host copy)', not os.path.exists(esc_tmp), 'inside: ' + parts[3] + '; host copy absent')
        check('write: project allowed', parts[4] == 'wrote-inside' and os.path.isfile(os.path.join(root, 'inside.txt')),
              parts[4])
        check('read: home file hidden', parts[5] == 'False', 'sentinel visible=' + parts[5])
    else:
        print('SKIP network and write probes: the unconfined runner has no confinement by design')
    os.environ['H64_SECRET_TEST'] = 'should-not-pass'
    code, out, err, tag = child('import os; print(" ".join(sorted(os.environ)))')
    allowed = {'HOME', 'TMPDIR', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME', 'PATH', 'LANG', 'LC_ALL',
               'PYTHONDONTWRITEBYTECODE', 'PYTHONNOUSERSITE', 'BLENDER_USER_CONFIG', 'BLENDER_USER_SCRIPTS',
               'BLENDER_USER_DATAFILES'}
    extra = sorted(set(out.split()) - allowed)
    check('env scrubbed', out and 'H64_SECRET_TEST' not in out and not extra, 'extra=%s' % extra)
    code, out, err, tag = child('import resource as r; print(*[r.getrlimit(getattr(r, k))[0] for k in '
                                '("RLIMIT_NOFILE", "RLIMIT_CORE", "RLIMIT_AS", "RLIMIT_NPROC")])')
    lim = out.split()
    check('rlimits', lim[:3] == ['4096', '0', str(16 * 1024 ** 3)], 'nofile core as nproc = ' + ' '.join(lim))
    KEEP = ('import subprocess, time\n'
            'subprocess.Popen(["sleep", "%s"], start_new_session=True)\n'
            'time.sleep(600)\n' % marker)
    t0 = time.time()
    code, out, err, tag = child(KEEP, timeout=5)
    time.sleep(2)
    left = mine(is_keep)
    check('timeout kills setsid child', code == 'FAULT:timeout' and not left,
          '%s after %.1fs; leftovers=%s' % (code, time.time() - t0, left))
    if '--no-fork' not in sys.argv:
        FORK = ('import errno, os, time  # %s\n' % fork_tag +
                'n = 0; err = "none"\n'
                'for i in range(2000):\n'
                ' try:\n'
                '  pid = os.fork()\n'
                ' except OSError as e:\n'
                '  err = errno.errorcode.get(e.errno, str(e.errno)); break\n'
                ' if pid == 0:\n'
                '  time.sleep(600); os._exit(0)\n'
                ' n += 1\n'
                'open("fork-count.txt", "w").write("%d %s" % (n, err))\n'
                'time.sleep(600)\n')
        code, out, err, tag = child(FORK, timeout=10)
        time.sleep(2)
        counted = os.path.join(root, 'fork-count.txt')
        count = open(counted).read() if os.path.exists(counted) else 'none'
        left = mine(is_fork)
        check('fork storm killed', code == 'FAULT:timeout' and not left, '%s; leftovers=%d' % (code, len(left)))
        print('INFO fork count and stop reason (cap = processes you had + 512):', count)
finally:
    for pid in mine(is_keep) + mine(is_fork):
        try:
            os.kill(pid, 9)
        except OSError:
            pass
    for path in (sentinel, esc_home, esc_tmp, esc_plugin):
        if os.path.exists(path) and path != esc_plugin:
            os.remove(path)
print('RESULT %s (%d/%d checks passed)' % ('PASS' if all(results) else 'FAIL', sum(results), len(results)))
EOF
```

7. Run it:

   ```sh
   cd "$PLUGIN"; "$PY" -B "$T/h64_probe.py" "$PLUGIN" "$T" 2>&1 | tee "$R/outputs/c7-probe.txt"
   ```

   **PASS if** the first line is `ISOLATION bwrap | Linux bubblewrap sandbox: ...` and the last line is
   `RESULT PASS (13/13 checks passed)` (12/12 with `--no-fork`): the host's own 127.0.0.1 service and an outside address are unreachable
   from inside (expected `ECONNREFUSED` and `ENETUNREACH`), writes to your home, `/usr` and the plugin folder fail,
   writes to `/tmp` (and to the sandbox's own empty folders) never reach the host, the project is writable, a file in your home folder is invisible, the environment holds
   only the listed names, the limits read `4096 0 17179869184 <n>`, and the timeout leaves no `sleep` process
   behind even though it started its own session. Note the `INFO fork count` line. **FAIL if** any line says FAIL:
   send the whole file. (The fork step briefly starts up to a few hundred sleeping processes; add `--no-fork` on a
   shared machine and say so.)

## D. Making games without a model (20 min)

8. A bundled example through the whole pipeline (scaffold, compile, proof, build, bot playtest, web export):

   ```sh
   cd "$PLUGIN"; mkdir -p "$T/games"
   "$PY" -B -m adventure_maker.demo --projects-root "$T/games" --project thaw1 --example thaw 2>&1 | tee "$R/outputs/d8-demo.txt"
   ```

   **PASS if** it prints `HERMES64 — local demo ready`, one line per stage, `Playtest:` with a verdict and a
   `Web/share:` path. **FAIL if** it prints `HERMES64 DEMO FAILED:` (send the JSON after it).
9. The `/hermes64 new` path, called directly:

   ```sh
   cd "$PLUGIN"; "$PY" -B - "$T/games" <<'EOF' 2>&1 | tee "$R/outputs/d9-new.txt"
   import json, sys
   from adventure_maker import demo
   r = json.loads(demo.handle({'projects_root': sys.argv[1], 'python_path': sys.executable}, 'hermes64_demo',
                              {'project': 'fox1', 'premise': 'A fox searches the village for its lost lantern'}))
   print(json.dumps({k: r.get(k) for k in ('ok', 'status', 'created', 'assets_built', 'style_audit', 'badge',
                                           'play_command', 'seconds', 'error')}, indent=1))
   print(r.get('message', ''))
   EOF
   ```

   **PASS if** `"created": true`, `"status": "new_game_ready"` (or `new_game_needs_work` with the reason printed;
   record which), and a `play_command`. A style-audit line that says screenshots were skipped (no display) is
   expected on Linux. **FAIL if** `"ok": false` with an `error` (send it).
10. The create flow (the agent's full pipeline, here with the keyword brief and the Python builder):

    ```sh
    cd "$PLUGIN"; "$PY" -B -m adventure_maker.create_flow run "a haunted lighthouse puzzle adventure" \
      --projects-root "$T/games" --name light1 --builder python 2>&1 | tee "$R/outputs/d10-create.txt"
    "$PY" -B -m adventure_maker.create_flow status --projects-root "$T/games" --name light1 | tee -a "$R/outputs/d10-create.txt"
    ```

    **PASS if** the stages up to `playtest` succeed and `$T/games/light1/CREATE-REPORT.md` exists; a `capture`
    stage reported as skipped for lack of a display is expected. **FAIL if** a stage before `capture` fails.
11. Playtest and export the `/hermes64 new` game, then the refusal:

    ```sh
    cd "$PLUGIN"; "$PY" -B - "$T/games" <<'EOF' 2>&1 | tee "$R/outputs/d11-export.txt"
    import json, sys
    from adventure_maker import demo
    s = {'projects_root': sys.argv[1], 'python_path': sys.executable}
    for tool, args in (('hermes64_playtest', {'project': 'fox1', 'mode': 'winning'}),
                       ('hermes64_export', {'project': 'fox1', 'targets': ['web']}),
                       ('hermes64_export', {'project': 'fox1', 'targets': ['windows']}),
                       ('hermes64_export', {'project': 'fox1', 'targets': ['macos']})):
        r = json.loads(demo.handle(s, tool, args))
        print(tool, args.get('targets', ''), 'ok=%s' % r.get('ok'), json.dumps(r.get('error') or
              {k: r[k] for k in ('verdict', 'share_path', 'zip_path') if k in r})[:600])
    EOF
    ```

    **PASS if** the playtest and the `web` and `windows` exports say `ok=True`, and `macos` says `ok=False` with
    `export_target` and `The macos target needs a Mac ... Nothing was exported.` **FAIL if** web or windows fails
    (send the error; it names the `.process.json` file to attach).
12. (Desktop only) play the web build: `python3 -m http.server --bind 127.0.0.1 8000 --directory <share_path>/web`,
    open http://127.0.0.1:8000/, click once, play a minute. **PASS if** picture and sound work. Ctrl+C stops it.

## E. Inside Hermes (10 min)

13. In a separate Hermes profile or `HERMES_HOME`: `hermes plugins install Qhantom-Labs/hermes64 --ref
    COMMIT_UNDER_TEST --enable` (no `--ref` on your Hermes: use the zip route from [LINUX.md](LINUX.md)). Approve
    numpy/Pillow, keep `HERMES64_GODOT` in the environment Hermes starts with, restart Hermes, open a **new** chat:
    `/hermes64 setup`. **PASS if** the reply names the commit under test and shows `Child runner: bwrap: ...`
    as ok. Then `/hermes64 new "A fox searches the village for its lost lantern"`. **PASS if** it returns the
    Made / Style / Badge / Play lines.

## F. The unconfined opt-in (5 min)

14. Fail closed, then the fallback, with real children and bwrap reported absent (no sudo needed):

    ```sh
    cd "$PLUGIN"
    "$PY" -B "$T/h64_probe.py" "$PLUGIN" "$T" --unconfined-sim --no-fork 2>&1 | tee "$R/outputs/f14-off.txt"
    HERMES64_LINUX_RUNNER=unconfined "$PY" -B "$T/h64_probe.py" "$PLUGIN" "$T" --unconfined-sim --no-fork 2>&1 \
      | tee "$R/outputs/f14-unconfined.txt"
    HERMES64_LINUX_RUNNER=unconfined "$PY" -B -m adventure_maker.doctor --linux-checklist | tee "$R/outputs/f14-bwrap-wins.txt"
    ```

    **PASS if** (1) the first run prints `ISOLATION off`, a sentence naming bubblewrap as not installed plus the
    opt-in, and `RESULT runner off: no child was started`; (2) the second prints `ISOLATION unconfined` with
    `no OS-enforced network or write confinement; process-group kill and rlimits only`, skips the network/write
    probes and passes the rest (the setsid line may FAIL here: unconfined runs have no PID namespace; record it);
    (3) the checklist still shows `Child runner (bwrap)`: a working bwrap wins over the opt-in.
15. Optional, **sudo**, machine owner's approval: make the real probe fail, then restore.

    ```sh
    OLD=$(sysctl -n user.max_user_namespaces); sudo sysctl -w user.max_user_namespaces=0
    "$PY" -B -m adventure_maker.doctor --linux-checklist | tee "$R/outputs/f15-userns-off.txt"
    sudo sysctl -w user.max_user_namespaces="$OLD"
    ```

    **PASS if** the runner line is `OFF` and names `user.max_user_namespaces=0` with the fix. While it is 0, other
    sandboxed programs (browsers, flatpak) may fail; restore it at once.

## G. Receipt and failures

16. Copy [receipts/LINUX-RECEIPT-TEMPLATE.md](receipts/LINUX-RECEIPT-TEMPLATE.md) to
    `$R/RECEIPT.md`, fill every field from the files in `$R/outputs/`, mark each step PASS / FAIL / SKIPPED with the
    reason, remove user names and host names, and hand the folder over as
    `docs/receipts/linux/<YYYY-MM-DD>-<machine alias>/`. Do not edit `LINUX.md`, `PLATFORM-PARITY.md` or "Tested by
    the owner"; maintainers update those from the receipt.
17. On any failure also attach: the `.maker/runs/*/*.process.json` file a message names, the full checklist output,
    `bwrap --version`, and `dmesg | grep -i -E 'apparmor|denied' | tail -20` if AppArmor may be involved. Do not
    work around a failure by changing plugin code or gates; report it.
