# Linux test sheet v3 (about 60 minutes)

For a tester on a **real Linux computer**. Two Debian 13/bwrap 0.12.0 runs are recorded in [PLATFORM-EVIDENCE.md](PLATFORM-EVIDENCE.md): run 1 failed, run 2 built/bot-played/exported games with C7 PWD and D10 display failures. Use the **third-run addendum** below for this candidate. Record what really happens, pass or fail; never retype or tidy output. ([LINUX.md](LINUX.md), [PLATFORM-EVIDENCE.md](PLATFORM-EVIDENCE.md)). The receipt template is
[receipts/LINUX-RECEIPT-TEMPLATE.md](receipts/LINUX-RECEIPT-TEMPLATE.md).

Rules:
- Hermes chat steps (especially E13) require a configured working model. Confirm a harmless ordinary chat reply first; HTTP 404/model-not-found is a prerequisite failure, not plugin acceptance.
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
               'BLENDER_USER_DATAFILES', 'XDG_RUNTIME_DIR', 'PULSE_RUNTIME_PATH', 'PULSE_STATE_PATH',
               'PULSE_CLIENTCONFIG', 'PULSE_SERVER', 'PWD'}  # explicit private-runtime constants; bwrap creates PWD
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
                'for i in range(768):\n'
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
        forked = count.split()
        cap_holds = len(forked) == 2 and forked[0].isdigit() and 0 < int(forked[0]) < 768 and forked[1] == 'EAGAIN'
        check('fork storm killed', code == 'FAULT:timeout' and not left and cap_holds,
              '%s; leftovers=%d; fork count/stop=%s; cap observed=%s' % (code, len(left), count, cap_holds))
        print('INFO fork count and stop reason (inner visible tasks + 512; inherited ceilings may be lower):', count)
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

## Fourth Linux run addendum: PLATFORMS-3 candidate

**Linux: Not verified. Tested by the owner: Not yet.** Preserve all three prior receipts. Record the exact candidate SHA, use a fresh `$T`, and extract C7 again from this sheet (the private runtime keys are now explicit constants, not inherited variables). Do not install packages, change sysctls or enable the unconfined fallback to obtain a pass.

1. **B5 / C7:** real confined Runner readiness and tiny PNG probe must pass. Re-run C7 with `--no-fork`; expect **12/12**, with no provider/Hermes/sentinel key. New `XDG_RUNTIME_DIR`/`PULSE_*` values point under `/tmp/hermes64-runtime` in the private per-run tmpfs, not a project or host Pulse socket. NPROC exhaustion remains not exercised on a shared machine.
2. **D9 control:** build a fresh game and run its rendered audit. Preserve WARN findings (run 3 was 88/100, not human approval). Save process argv/stderr and list runtime symlinks afterward. Automated rendered/headless Godot argv should include `--audio-driver Dummy`; no host sound/display devices are exposed.
3. **D10:** re-run the create flow. Require exit 0, exact `CAPTURE status=passed` marker/count, complete `capture.json`, actual decodable/nonblank PNGs and CREATE-REPORT.md/.json. Read actual style/N64 verdicts, per-room reasons and copied frames; never replace a failed visual gate with a pass. Known device diagnostics may appear only in a retained `benign_stderr` list; script/parse/load/crash/signal errors, nonzero exit, missing marker or missing/blank images must still fail. A missing display remains an honest not-run report, not a visual pass.
4. **D11 on that rendered game:** bot playtest, web export and Windows cross-export must succeed; macOS must retain its explicit target refusal. Repeat once on the D9 rendered game. Check there is no surviving `.maker/local/config/pulse/*-runtime` link after any child.
5. **Existing-game repair:** if untouched run-3 affected games remain at their original scratch paths, make an archival backup first, then run the next playtest/export call on the original game path. Require a `runtime_cleanup` note, the reported internal Pulse runtime link removed without deleting its target, and bots/export proceeding without manual deletion. Preserve the original receipt/outputs and the backup; save this call as a new diagnostic. A moved/copied game's absolute link to the old scratch root is outside the new project and must still be refused, not silently removed.

Save the new process reports, CREATE reports, screens listing and symlink listing with the fourth receipt; do not modify plugin code or visual thresholds. If the first real attempt differs from the local simulation, retain it as a failure. Human graphics/audio/save, Studio, Hermes integration and fork exhaustion are separate gates, not implied by this addendum.

## Third-run addendum: PLATFORMS-2 candidate (historical; run completed)

Record the exact candidate commit and use a **fresh** `$T`; retain both earlier receipts. Re-run **B5, C7 (expect 12/12 with `--no-fork`), D8, D9, D10 and D11**, with the updated probe extracted from this sheet, not the old saved script.

- **B5:** confined Runner child must exit 0. Record the separate `capture display` row. If Xvfb is already installed, the real tiny Compatibility/OpenGL3 PNG must succeed before capture OK. If absent/failed, record the exact reason; doctor must say `capture display: missing, install xvfb (sudo apt install xvfb)` before any create. Do not install without separate machine-owner approval.
- **C7:** bwrap 0.12.0 sets PWD itself, even with an empty input environment. Only PWD was added to the allowlist; no provider keys, HERMES variables or `H64_SECRET_TEST` may survive. Expect `RESULT PASS (12/12 checks passed)` on this shared machine. Fork exhaustion remains not exercised; do not run it without dedicated-machine permission.
- **D8/D9:** default demo/new build and bots pass. Keep all output, including ffmpeg discovery and play commands.
- **D10:** all logic stages and report must complete. With a working capture route, require actual PNGs and record real style/N64 verdicts (a failed style gate is not a pass). Without it, CREATE-REPORT.md must still exist, both gates must say `not_run` / `not run: no display on this machine`, no visual pass or invented frame.
- **D11:** bot playtest, web and Windows exports succeed; macOS retains its explicit refusal. Paste the heredoc terminator only as a shell delimiter, never into Python (the first attempt in run 2 had a tester `EOF` typo, not a plugin bug).

Write a new receipt; do not edit an earlier one or mark Linux acceptance from these instructions.

## Second-run addendum: LINUXFIX candidate (historical; run completed)

The second real run used this addendum; its results are in [PLATFORM-EVIDENCE.md](PLATFORM-EVIDENCE.md). Keep the C7a diagnostic below. For this candidate use the third-run list above it.

The first run on Debian 13/bwrap 0.12.0 failed every official child even though the old checklist said READY.
Keep [that receipt](receipts/LINUX-RECEIPT-2026-11-12-debian13.md). On the fixed candidate, in a new `$T` (do not
reuse the half-made `fox1`/`light1` folders), record the exact new SHA and redo **B5, C7, D8, D9 and D10**, then D11
if authoring succeeds. The child-runner row must explicitly say a real `Runner.run` readiness child exited 0;
otherwise READY must not appear. Debian's system ffmpeg should now be found without changing the child PATH.

**New step C7a, inside and outside facts** (no sysctl changes, no environment dump):

```sh
cd "$PLUGIN"
{ printf 'OUTSIDE sandbox\n'; bash -c 'printf "ulimit -u: "; ulimit -u; cat /proc/self/status | grep -E "^(Uid|NSpid|Threads):"; grep -i "Max processes" /proc/self/limits'; } \
  2>&1 | tee "$R/outputs/c7a-host.txt"
"$PY" -B - "$T" <<'EOF' 2>&1 | tee "$R/outputs/c7a-inside.txt"
import json, sys
from pathlib import Path
from adventure_maker.runner import Runner
from adventure_maker.safety import Project, Fault
from adventure_maker import linux_sandbox
base = Path(sys.argv[1]).resolve() / 'limit-facts'
base.mkdir(parents=True, exist_ok=True)
print('ISOLATION', linux_sandbox.status()['mode'])
try:
    p = Project(str(base), 'facts', create=True)
    r = Runner(p).run(['/bin/bash', '-c', 'printf "INSIDE sandbox\\nulimit -u: "; ulimit -u; cat /proc/self/status | grep -E "^(Uid|NSpid|Threads):"; grep -i "Max processes" /proc/self/limits'], p.root, timeout=10)
    print('exit', r['returncode'], 'isolation', r.get('isolation'))
    print(r['stdout'], end='')
    print(r['stderr'], end='')
except Fault as e:
    print('FAULT', e.code, str(e))
EOF
```

`/proc/self/status` has **no NPROC field** on ordinary Linux: Uid/NSpid/Threads show namespace/task facts; the
NPROC soft/hard ceilings are `Max processes` in `/proc/self/limits` and `ulimit -u`. Record both, not an empty grep
as a pass. Inside must exit 0 with `linux-bwrap`, a small namespace-visible task baseline plus 512 (or a stricter
inherited ceiling), not the old host-process-plus-512 value. The original host ceiling must not be changed.

The bounded C7 fork check now requires **positive fork headroom, EAGAIN before 768 forks, timeout, and no surviving
tagged child**. It keeps the same 13 checks (12 with `--no-fork`); it no longer passes merely because a run timed
out. NPROC is retained, not replaced by the PID namespace. A namespace controls visibility/lifetime, not a task-count
cap. Run exhaustion only on a dedicated VM with machine-owner approval; shared machines must use `--no-fork` and
record the cap as **not exercised**. A different inherited/cgroup ceiling can also cause EAGAIN: record those
limits before attributing the observed stop to this plugin. No native Linux or Windows verification is implied by
this addendum or the Mac simulation tests.
