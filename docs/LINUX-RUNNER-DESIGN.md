# Linux child runner: design note

Status: first real run on Debian 13 with bwrap 0.12.0 (2026-11-12, plugin `6af4ba26`) failed every official child
with `sandbox_unavailable` ([receipt](receipts/LINUX-RECEIPT-2026-11-12-debian13.md)). The fix below is simulated on
Mac only, awaiting a second [Linux test-sheet](LINUX-TEST-SHEET.md) run; Linux is **not verified**.

## Goal

Same contract as the macOS runner (`sandbox-exec`): argv list only, no shell; no network; writes only inside the
game project; scrubbed environment; the same budgets (timeout at most 180 s, 1,048,576 bytes of combined output,
strict UTF-8 stdout) and the same `Fault` codes (`sandbox_unavailable`, `timeout`, `output_limit`, `launch_failed`,
`missing_tool`, `arguments`). macOS and Windows code paths are unchanged.

## Default: bubblewrap (`bwrap`)

Each child runs as:

```text
<python> -I -S -c <outer rlimit shim> <AS/CPU/NOFILE/CORE only> -- bwrap --unshare-all --die-with-parent --new-session --cap-drop ALL
  --ro-bind /usr /usr  (and /bin /sbin /lib* /opt /nix /gnu as present; merged-usr symlinks become --symlink)
  --ro-bind /etc/<ld.so.cache, ld.so.conf(.d), alternatives, fonts, localtime, nsswitch.conf, passwd, group, os-release>
  --proc /proc --dev /dev --tmpfs /tmp
  --ro-bind <plugin folder> ; --ro-bind <the tool: Godot file, Blender folder, Python venv + base prefix>
  --ro-bind <any other existing absolute path named in argv>
  --bind <project folder>  (the only writable host path)
  -- <python> -I -S -c <inner NPROC shim> <visible tasks + 512, clamped> -- <original argv>
```

The working folder is the one the runner passes (the project or a folder inside it); bwrap keeps the caller's
working folder when that path exists inside the sandbox, and every run's folder does.

- `--unshare-all` gives new user, mount, PID, IPC, UTS and network namespaces (cgroup where available). The network
  namespace has only loopback, so nothing outside the sandbox is reachable, including the host's 127.0.0.1 services
  and abstract Unix sockets (X11, D-Bus).
- The sandbox root is a fresh tmpfs: `$HOME` and everything not listed above is absent. Child `HOME`, `TMPDIR` and
  `XDG_*` point into the project's `.maker/local/`, as on macOS. `/tmp` is a per-run tmpfs, discarded at exit.
- Environment: only `HOME`, `TMPDIR`, `XDG_*`, `PATH=/usr/local/bin:/usr/bin:/bin`, `LANG/LC_ALL=C.UTF-8`, the
  Python and Blender variables macOS sets. No credentials, proxies or Hermes flags.
- Limits: the **outer** stdlib shim sets AS (16 GiB), CPU (3,600 s), NOFILE (4,096) and CORE (0) before bwrap.
  It does **not** lower NPROC. After bwrap creates its namespaces, mounts the new `/proc` and drops capabilities,
  an **inner** isolated Python shim counts visible same-UID tasks (including threads), adds 512, clamps to the
  inherited soft/hard ceilings, sets NPROC and execs the original tool. The wrapper interpreter/venv/base and the
  original tool's binds are all kept read-only. Unconfined mode retains host-count-plus-512 NPROC before the tool.
  This retains the fork brake; it does not substitute lifetime cleanup for a process-count limit. Visible tasks are
  a sizing baseline, **not** an exact model of Linux's hierarchical real-UID/ucounts accounting. Ancestor limits,
  host load, kernel generation and root exemptions still matter. The candidate needs a real-kernel retest.
  The first-run diagnostic establishes NPROC as the trigger, not which task/namespace counter exhausted: counting
  168 process leaders did not count their threads. Pre-namespace limits could be inherited into new namespace
  accounting; post-namespace application avoids imposing the plugin's small ceiling during bwrap setup.
- Kill: the run loop is the macOS one (`start_new_session` + `killpg` at every exit, timeout and output overflow).
  `killpg` kills the outer bwrap; `--die-with-parent` kills the namespace's first process; a PID namespace whose
  first process dies is torn down by the kernel, so no descendant survives, even one that called `setsid`.

### Detection: present and functional

`linux_sandbox.status()` runs one real probe per process (10 s limit) **through `Runner.run`**, with the same
command builder, limit ordering, minimal environment, process-group/namespace cleanup and bounded output as builds.
A private candidate isolation record prevents recursive status calls; it is never published as ready until the
child exits 0 and every marker passes. The probe folder is the only writable host path. Its Python must see
(1) its write inside succeed, (2) a write under `/usr` fail, (3) a host file outside the binds be invisible,
(4) `connect()` to 192.0.2.1 (TEST-NET-1, never routed) fail with `ENETUNREACH`, (5) a nested tiny Python child exit 0
under the effective limits. Anything else, including timeout, is a failure. Setup/checklist require this passed
runner record; unconfined fallback cannot earn sandboxed READY. On failure the message includes the error and
likely cause when the host shows it:

| Host fact | Message and fix |
|---|---|
| no `bwrap` on PATH or in /usr/bin, /usr/local/bin, /bin | install bubblewrap (apt/dnf/pacman/zypper/apk lines) |
| `kernel.apparmor_restrict_unprivileged_userns=1` (Ubuntu 23.10+, 24.04) | AppArmor blocks bwrap's user namespace: an AppArmor profile for bwrap with `userns,` (text in LINUX.md), or the weaker sysctl |
| `kernel.unprivileged_userns_clone=0` (older Debian, hardened kernels) | `sysctl kernel.unprivileged_userns_clone=1` |
| `user.max_user_namespaces=0` | `sysctl user.max_user_namespaces=15000` |
| container markers (`/.dockerenv`, `/run/.containerenv`, `container=`) | the container blocks namespaces: run Hermes on the host or allow user namespaces in the container |
| WSL 1 | no namespaces in WSL 1; use WSL 2 |
| probe ran but saw the network or wrote outside | refuse: the sandbox is not working as required |

### Fail closed

No working bwrap means every child is refused with `sandbox_unavailable` and that message, exactly like Windows
without its opt-in. Nothing starts.

## Fallback: `HERMES64_LINUX_RUNNER=unconfined` (owner opt-in)

Only when the probe fails **and** the owner set this variable, children run without bwrap: same scrubbed
environment, project-local folders, rlimit shim, process group and `killpg`. Disclosure (doctor, setup, the
`/hermes64 new` reply and each run's result): **no OS-enforced network or write confinement; process-group kill
and rlimits only.** A child that calls `setsid` leaves the process group and can outlive the run. When the probe
passes, bwrap is used even if the variable is set.

## Programs that cannot run inside

snap and flatpak programs start through their own sandbox launcher (setuid `snap-confine`; flatpak's own bwrap
and portals). That launcher is not expected to work inside an unprivileged user namespace, and the project folder
would not be visible to it. Discovery skips them and says so; an explicit path to one is refused with that
sentence. Not tested on Linux.

## Display and GPU

Authoring is headless: Godot runs `--headless` (no display, no GPU, no audio device, no network). Captures and the
measured style audit need a display, so on Linux they are skipped and reported as such, as on a Windows service
session. Playing a web export needs a browser; Studio Play serves it on 127.0.0.1 from the Hermes process, outside
the sandbox, as on macOS.

## Not built (documented options)

firejail (setuid, larger attack surface) and Landlock (kernel 5.13+, file-system rules without namespaces; no
network rules before 6.7) are possible later backends. Neither is implemented. cgroup memory limits (systemd-run
`--user --scope`) are not used: they need a delegated user cgroup tree that many hosts lack.
