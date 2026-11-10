"""Local argv-only execution, hard budgets, macOS write/network sandbox."""
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

PROCESS_LIMIT = 1024 * 1024
DEFAULTS = {'blender': '/opt/homebrew/bin/blender',
            'godot': '/Applications/Godot.app/Contents/MacOS/Godot', 'python': 'python3'}


def locate(tool, configured=''):
    def executable(value):
        path = shutil.which(value) if '/' not in value else value
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
    for candidate in _default_candidates(tool, DEFAULTS[tool]):
        result = executable(candidate)
        if result:
            return result
    fail('missing_tool', '{} not found; configure {}_path. Checked {} and PATH. Nothing was installed.'.format(tool, tool, DEFAULTS[tool]))


def _default_candidates(tool, default):
    """Default search order. For python, the interpreter Hermes itself runs under comes first:
    it is the one known to carry numpy/Pillow, while a bare `python3` on PATH often resolves to
    an interpreter without them (and the plugin runs it in isolated mode, so user-site packages
    do not count). A configured python_path always wins and never falls back silently."""
    if tool == 'python':
        host = sys.executable
        if host and sys.version_info >= (3, 9):
            return (host, 'python3')
        return ('python3',)
    return (default, tool)


class Runner:
    def __init__(self, project):
        self.project = project

    def environment(self):
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

    def sandbox_argv(self, argv):
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
