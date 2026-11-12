"""Linux-only runtime hygiene. Never admit a symlink to project content.

PulseAudio's client creates config/pulse/<machine-id>-runtime -> TMPDIR/pulse-*
when no XDG_RUNTIME_DIR is supplied. Remove only that precise managed scratch
shape after the child is gone, or on the next audit of an older game.
"""
import os
from pathlib import Path
import re
import stat

from .safety import inspect_path


def cleanup(project):
    root = inspect_path(project.root)
    parent = inspect_path(root / '.maker/local/config/pulse')
    if not parent.is_dir():
        return []
    notes = []
    # O_NOFOLLOW + dir_fd prevents a replaced leaf directory redirecting unlink.
    fd = os.open(str(parent), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for name in os.listdir(fd):
            if not re.fullmatch(r'[A-Za-z0-9_-]+-runtime', name):
                continue
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if not stat.S_ISLNK(info.st_mode):
                continue
            target = Path(os.readlink(name, dir_fd=fd))
            if target.parent != root / '.maker/local/tmp' or not re.fullmatch(r'pulse-[A-Za-z0-9]+', target.name):
                continue  # leave arbitrary links intact so the general audit rejects them
            inspect_path(target)  # no target symlink chain, even inside the controlled scratch folder
            os.unlink(name, dir_fd=fd)  # unlink the runtime link, never its target
            notes.append('Removed stale PulseAudio runtime symlink: .maker/local/config/pulse/' + name)
    finally:
        os.close(fd)
    if notes:
        project.runtime_cleanup = list(getattr(project, 'runtime_cleanup', [])) + notes
    return notes
