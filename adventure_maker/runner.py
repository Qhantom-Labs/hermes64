"""Local argv-only execution, hard budgets, macOS write/network sandbox; opt-in Windows Job Object runner.

macOS: every child runs under sandbox-exec (no network, writes confined to the project). Unchanged.
Windows: there is no one-line equivalent. With HERMES64_WINDOWS_RUNNER=job (owner opt-in, see platforms.isolation and
docs/WINDOWS.md) a child runs in a Job Object that kills it and everything it started when the run ends or times out,
caps processes and memory, and gets private profile folders inside the project; network and writes are NOT
OS-confined. Without the opt-in a child is refused (sandbox_unavailable) exactly as before.
"""
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import sys
import time
from .safety import Fault, fail
from . import platforms

PROCESS_LIMIT = 1024 * 1024
DEFAULTS = {'blender': '/opt/homebrew/bin/blender',
            'godot': '/Applications/Godot.app/Contents/MacOS/Godot', 'python': 'python3'}


def locate(tool, configured='', platform=None, env=None):
    def executable(value):
        path = shutil.which(value) if not platforms.looks_like_path(value, platform) else value
        if path and Path(path).is_file() and os.access(path, os.X_OK):
            # A venv's python is often a symlink. Resolving its final component
            # launches the base interpreter and silently loses numpy/Pillow.
            if tool == 'python':
                return str(Path(path).absolute())
            return str(Path(path).resolve())
        return None
    if configured:
        result = executable(configured)
        if result:
            return result
        fail('missing_tool', '{} not found at configured path {!r}; change {}_path to an existing local executable'.format(tool, configured, tool))
    for candidate in _default_candidates(tool, DEFAULTS[tool], platform, env):
        result = executable(candidate)
        if result:
            return result
    fail('missing_tool', '{} not found; configure {}_path (or {}). Checked {} and PATH. Nothing was installed.'.format(
        tool, tool, platforms.OVERRIDE_ENV[tool], _checked(tool, platform, env)))


def _checked(tool, platform=None, env=None):
    if not platforms.is_windows(platform):
        return DEFAULTS[tool]
    shown = [c for c in platforms.candidates(tool, platform, env) if platforms.looks_like_path(c, platform)][:3]
    return ', '.join(shown) or tool


def _default_candidates(tool, default, platform=None, env=None):
    """Default search order. For python, the interpreter Hermes itself runs under comes first:
    it is the one known to carry numpy/Pillow, while a bare `python3` on PATH often resolves to
    an interpreter without them (and the plugin runs it in isolated mode, so user-site packages
    do not count). Under the Hermes launcher that is its environment's python, not the bare base
    interpreter in sys.executable (platforms.environment_pythons; BFIX).
    A configured python_path always wins and never falls back silently.
    HERMES64_GODOT / HERMES64_BLENDER / HERMES64_PYTHON come before the defaults on every platform;
    on Windows the defaults are platforms.candidates (LOCALAPPDATA, Program Files, winget, scoop, PATH)."""
    first = [platforms.override(tool, env)] if platforms.override(tool, env) else []
    if platforms.is_windows(platform):
        return tuple(platforms.candidates(tool, platform, env))
    if tool == 'python':
        host = sys.executable
        envs = tuple(platforms.environment_pythons(platform)) if env is None else ()
        if host and sys.version_info >= (3, 9):
            return tuple(first) + envs + (host, 'python3')
        return tuple(first) + envs + ('python3',)
    if tool == 'godot':
        # Keep explicit/configured and env overrides ahead of verified cached Godot.
        # Windows cache discovery is in platforms.godot_candidates; inventories stay pure.
        if platform is None and env is None:
            from .godot_fetch import cached_godot
            cached = cached_godot()
            return tuple(first) + ((str(cached),) if cached else ()) + (default, tool)
    return tuple(first) + (default, tool)


class Runner:
    def __init__(self, project):
        self.project = project

    def environment(self):
        if platforms.is_windows():
            return self.windows_environment()
        paths = {}
        for key, rel in [('HOME', 'home'), ('TMPDIR', 'tmp'), ('XDG_CONFIG_HOME', 'config'),
                         ('XDG_CACHE_HOME', 'cache'), ('XDG_DATA_HOME', 'data')]:
            path = self.project.path('.maker/local/' + rel)
            path.mkdir(parents=True, exist_ok=True)
            paths[key] = str(path)
        # Never copy ambient credentials, startup injection, proxies or Hermes guard flags.
        paths.update(PATH='/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin',
                     LANG='en_US.UTF-8', LC_ALL='en_US.UTF-8',
                     PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1',
                     BLENDER_USER_CONFIG=paths['XDG_CONFIG_HOME'],
                     BLENDER_USER_SCRIPTS=paths['XDG_CONFIG_HOME'],
                     BLENDER_USER_DATAFILES=paths['XDG_DATA_HOME'])
        return paths

    def windows_environment(self, env=None):
        """Windows child environment: profile/temp folders inside the project, system folders only on PATH."""
        source = os.environ if env is None else env
        paths = {}
        for key, folder in platforms.project_local_dir(self.project.path('.maker/local'), 'win32').items():
            Path(folder).mkdir(parents=True, exist_ok=True)
            paths[key] = str(folder)
        root = source.get('SystemRoot') or source.get('SYSTEMROOT') or 'C:\\Windows'
        paths.update(SystemRoot=root, WINDIR=root, PATH=';'.join([root + '\\System32', root,
                                                                    root + '\\System32\\Wbem']),
                     PATHEXT='.COM;.EXE;.BAT;.CMD', COMSPEC=root + '\\System32\\cmd.exe',
                     NUMBER_OF_PROCESSORS=source.get('NUMBER_OF_PROCESSORS', '4'),
                     PROCESSOR_ARCHITECTURE=source.get('PROCESSOR_ARCHITECTURE', 'AMD64'),
                     PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', PYTHONUTF8='1', PYTHONIOENCODING='utf-8',
                     BLENDER_USER_CONFIG=paths['APPDATA'], BLENDER_USER_SCRIPTS=paths['APPDATA'],
                     BLENDER_USER_DATAFILES=paths['LOCALAPPDATA'])
        return paths

    def sandbox_argv(self, argv):
        if platforms.is_windows():
            if not platforms.windows_runner_enabled():
                fail('sandbox_unavailable', 'Required no-network/write-confinement sandbox unavailable on this host; '
                     'no child started. ' + platforms.isolation('win32')['note'])
            return list(argv)
        if sys.platform != 'darwin' or not Path('/usr/bin/sandbox-exec').is_file():
            fail('sandbox_unavailable', 'Required no-network/write-confinement sandbox unavailable on this host; no child started')
        root = json.dumps(str(self.project.root.resolve()))
        policy = ('(version 1) (allow default) (deny network*) (deny file-write*) '
                  '(allow file-write* (subpath ' + root + ') (literal "/dev/null"))')
        return ['/usr/bin/sandbox-exec', '-p', policy] + argv

    def run(self, argv, cwd, timeout=30):
        if not isinstance(argv, list) or not argv or any(not isinstance(x, str) or '\x00' in x for x in argv):
            fail('arguments', 'Subprocess requires an argv list of strings, never a shell string')
        if not 0 < timeout <= 180:
            fail('arguments', 'Subprocess timeout must be within (0, 180] seconds')
        if not Path(argv[0]).is_absolute() or not Path(argv[0]).is_file():
            fail('missing_tool', 'Executable not found: ' + argv[0])
        self.project.audit()
        command = self.sandbox_argv(argv)
        env = self.environment()
        if platforms.is_windows():
            return _run_windows(command, cwd, env, timeout)
        started = time.monotonic()
        try:
            proc = subprocess.Popen(command, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
                                    start_new_session=True)
        except OSError as exc:
            fail('launch_failed', 'Could not start local process: ' + str(exc))
        buffers = {'stdout': bytearray(), 'stderr': bytearray()}
        size = 0
        try:
            with selectors.DefaultSelector() as events:
                for name, pipe in [('stdout', proc.stdout), ('stderr', proc.stderr)]:
                    os.set_blocking(pipe.fileno(), False)
                    events.register(pipe, selectors.EVENT_READ, name)
                while events.get_map() or proc.poll() is None:
                    if time.monotonic() - started > timeout:
                        fail('timeout', 'Local process timeout after {} seconds; child process group stopped'.format(timeout))
                    for key, _mask in events.select(0.05):
                        data = os.read(key.fileobj.fileno(), 16384)
                        if not data:
                            events.unregister(key.fileobj)
                            continue
                        size += len(data)
                        if size > PROCESS_LIMIT:
                            fail('output_limit', 'Subprocess combined output limit exceeded (1048576 bytes); process stopped')
                        buffers[key.data].extend(data)
                code = proc.wait(timeout=1)
        finally:
            # Also reap inherited pipe-holding children; never touch unrelated processes.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait(timeout=5)
            proc.stdout.close()
            proc.stderr.close()
        return {'returncode': code, 'stdout': bytes(buffers['stdout']).decode('utf-8', 'strict'),
                'stderr': bytes(buffers['stderr']).decode('utf-8', 'replace'),
                'elapsed_seconds': round(time.monotonic() - started, 4)}


# ---------------------------------------------------------------- Windows (opt-in)
JOB_MEMORY_LIMIT = 8 * 1024 ** 3      # bytes, whole job
JOB_PROCESS_LIMIT = 64


def _job_limits():
    """ctypes JOBOBJECT_EXTENDED_LIMIT_INFORMATION for the job (built on any host so tests can inspect it)."""
    import ctypes

    class IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in ('ReadOperationCount', 'WriteOperationCount',
                                                      'OtherOperationCount', 'ReadTransferCount',
                                                      'WriteTransferCount', 'OtherTransferCount')]

    class Basic(ctypes.Structure):
        _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong), ('PerJobUserTimeLimit', ctypes.c_longlong),
                    ('LimitFlags', ctypes.c_uint32), ('MinimumWorkingSetSize', ctypes.c_size_t),
                    ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', ctypes.c_uint32),
                    ('Affinity', ctypes.c_size_t), ('PriorityClass', ctypes.c_uint32),
                    ('SchedulingClass', ctypes.c_uint32)]

    class Extended(ctypes.Structure):
        _fields_ = [('BasicLimitInformation', Basic), ('IoInfo', IO), ('ProcessMemoryLimit', ctypes.c_size_t),
                    ('JobMemoryLimit', ctypes.c_size_t), ('PeakProcessMemoryUsed', ctypes.c_size_t),
                    ('PeakJobMemoryUsed', ctypes.c_size_t)]

    info = Extended()
    # KILL_ON_JOB_CLOSE | DIE_ON_UNHANDLED_EXCEPTION | JOB_MEMORY | ACTIVE_PROCESS
    info.BasicLimitInformation.LimitFlags = 0x2000 | 0x400 | 0x200 | 0x8
    info.BasicLimitInformation.ActiveProcessLimit = JOB_PROCESS_LIMIT
    info.JobMemoryLimit = JOB_MEMORY_LIMIT
    return info


class _Job:
    """A Windows Job Object owning one child tree; closing it kills every process still in it."""

    def __init__(self):
        import ctypes
        try:
            self.k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        except (AttributeError, OSError):
            fail('sandbox_unavailable', 'Windows Job Object API unavailable on this host; no child started')
        self.k32.CreateJobObjectW.restype = ctypes.c_void_p
        self.handle = self.k32.CreateJobObjectW(None, None)
        if not self.handle:
            fail('sandbox_unavailable', 'Could not create a Windows Job Object; no child started')
        info = _job_limits()
        if not self.k32.SetInformationJobObject(ctypes.c_void_p(self.handle), 9, ctypes.byref(info),
                                                ctypes.sizeof(info)):
            self.close()
            fail('sandbox_unavailable', 'Could not set Windows Job Object limits; no child started')

    def assign(self, proc):
        import ctypes
        if not self.k32.AssignProcessToJobObject(ctypes.c_void_p(self.handle), ctypes.c_void_p(int(proc._handle))):
            proc.kill()
            fail('sandbox_unavailable', 'Could not place the child in its Windows Job Object; child stopped')

    def close(self):
        import ctypes
        if self.handle:
            self.k32.TerminateJobObject(ctypes.c_void_p(self.handle), 1)
            self.k32.CloseHandle(ctypes.c_void_p(self.handle))
            self.handle = None


def _run_windows(command, cwd, env, timeout):
    """Same contract as Runner.run (budgets, output cap, strict UTF-8 stdout), with reader threads (Windows pipes
    have no select) and a Job Object instead of a process group. CRLF from the child is normalised to LF."""
    import threading
    started = time.monotonic()
    job = _Job()
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0x200)
    try:
        try:
            proc = subprocess.Popen(command, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, shell=False, creationflags=flags)
        except OSError as exc:
            fail('launch_failed', 'Could not start local process: ' + str(exc))
        job.assign(proc)
        buffers = {'stdout': bytearray(), 'stderr': bytearray()}
        state = {'size': 0, 'over': False}
        lock = threading.Lock()

        def pump(name, pipe):
            for data in iter(lambda: pipe.read1(16384) if hasattr(pipe, 'read1') else pipe.read(16384), b''):
                with lock:
                    state['size'] += len(data)
                    if state['size'] > PROCESS_LIMIT:
                        state['over'] = True
                        return
                    buffers[name].extend(data)
        readers = [threading.Thread(target=pump, args=(n, p), daemon=True)
                   for n, p in (('stdout', proc.stdout), ('stderr', proc.stderr))]
        for t in readers:
            t.start()
        code = None
        while code is None:
            if state['over']:
                fail('output_limit', 'Subprocess combined output limit exceeded (1048576 bytes); process stopped')
            if time.monotonic() - started > timeout:
                fail('timeout', 'Local process timeout after {} seconds; child process tree stopped'.format(timeout))
            try:
                code = proc.wait(timeout=0.05)
            except subprocess.TimeoutExpired:
                pass
        for t in readers:
            t.join(timeout=5)
        if state['over']:
            fail('output_limit', 'Subprocess combined output limit exceeded (1048576 bytes); process stopped')
    finally:
        job.close()            # kills anything the child left running (its tree), never unrelated processes
    for pipe in (proc.stdout, proc.stderr):
        pipe.close()
    return {'returncode': code,
            'stdout': bytes(buffers['stdout']).decode('utf-8', 'strict').replace('\r\n', '\n'),
            'stderr': bytes(buffers['stderr']).decode('utf-8', 'replace').replace('\r\n', '\n'),
            'elapsed_seconds': round(time.monotonic() - started, 4)}
