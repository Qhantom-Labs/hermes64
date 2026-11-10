"""Input guards (stdlib, run before anything is decoded or written).

Read side: only the paths the caller gave; regular files; size and header-dimension limits; PNG/JPEG
magic; symlink containment. Write side: <realpath(project_dir)>/packs/<pack_id>/ only; no symlinked
`packs/` or pack dir; never overwrite a pack that this tool did not draft."""
import hashlib
import json
import os
import re
import stat

from . import imgsniff

MAX_REFS = 8
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_SIDE = 16384
MAX_PIXELS = 64 * 1000 * 1000
MIN_SIDE = 16
PACK_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,39}$")
RESERVED_PACK_IDS = ("polar_pod", "forest_village", "harbor_dusk", "n64_v0", "core", "default")
TOOL_ID = "hermes64_pack_from_refs"


class GuardError(ValueError):
    pass


def _inside(child, parent):
    child = os.path.normcase(child)
    parent = os.path.normcase(parent.rstrip(os.sep)) or os.sep
    return child == parent or child.startswith(parent + os.sep)


def sha256_file(path, limit=None):
    h = hashlib.sha256()
    n = 0
    with open(path, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            n += len(b)
            if limit is not None and n > limit:
                raise GuardError("file grew beyond %d bytes while hashing: %s" % (limit, path))
            h.update(b)
    return h.hexdigest()


def check_reference(path, read_root=None, index=0):
    """Returns a dict describing one accepted reference. Raises GuardError with a clear reason."""
    tag = "reference %d (%s)" % (index, os.path.basename(str(path)))
    if not isinstance(path, str) or not path:
        raise GuardError("reference %d: path must be a non-empty string" % index)
    if "\x00" in path:
        raise GuardError("%s: path contains a NUL byte" % tag)
    given = os.path.abspath(path)
    if not os.path.lexists(given):
        raise GuardError("%s: file not found: %s" % (tag, given))
    real = os.path.realpath(given)
    if read_root is not None:
        root = os.path.realpath(read_root)
        if not os.path.isdir(root):
            raise GuardError("read_root is not a directory: %s" % read_root)
        if not _inside(real, root):
            raise GuardError("%s: resolves outside read_root (%s -> %s); symlinks may not leave the root" % (tag, given, real))
    else:
        own_dir = os.path.realpath(os.path.dirname(given))
        if not _inside(real, own_dir):
            raise GuardError("%s: is a symlink that leaves its own folder (%s -> %s); pass the real file or a read_root" % (tag, given, real))
    try:
        st = os.stat(real)
    except OSError as e:
        raise GuardError("%s: cannot stat: %s" % (tag, e))
    if not stat.S_ISREG(st.st_mode):
        raise GuardError("%s: not a regular file" % tag)
    if st.st_size > MAX_FILE_BYTES:
        raise GuardError("%s: %d bytes is over the %d MiB per-image limit" % (tag, st.st_size, MAX_FILE_BYTES // (1024 * 1024)))
    if st.st_size < 32:
        raise GuardError("%s: only %d bytes; not an image" % (tag, st.st_size))
    try:
        info = imgsniff.sniff(real)
        imgsniff.verify_container(real, info["format"], MAX_FILE_BYTES)
    except imgsniff.SniffError as e:
        raise GuardError("%s: %s" % (tag, e))
    except OSError as e:
        raise GuardError("%s: cannot read: %s" % (tag, e))
    w, h = info["width"], info["height"]
    if w < MIN_SIDE or h < MIN_SIDE:
        raise GuardError("%s: %dx%d is too small (min %d px per side)" % (tag, w, h, MIN_SIDE))
    if w > MAX_SIDE or h > MAX_SIDE or w * h > MAX_PIXELS:
        raise GuardError("%s: %dx%d exceeds the decode limit (%d px per side, %d MP)" % (tag, w, h, MAX_SIDE, MAX_PIXELS // 1000000))
    return {"index": index, "given": given, "real": real, "basename": os.path.basename(given), "bytes": st.st_size,
            "sha256": sha256_file(real, limit=MAX_FILE_BYTES), "format": info["format"], "width": w, "height": h}


def check_references(paths, read_root=None):
    if not isinstance(paths, (list, tuple)):
        raise GuardError("reference_paths must be a list of file paths")
    if not 1 <= len(paths) <= MAX_REFS:
        raise GuardError("give 1 to %d reference images (got %d)" % (MAX_REFS, len(paths)))
    out = [check_reference(p, read_root, i) for i, p in enumerate(paths)]
    total = sum(r["bytes"] for r in out)
    if total > MAX_TOTAL_BYTES:
        raise GuardError("references total %d bytes (> %d MiB)" % (total, MAX_TOTAL_BYTES // (1024 * 1024)))
    seen = {}
    for r in out:
        if r["sha256"] in seen:
            raise GuardError("reference %d is the same file content as reference %d (sha256 %s...)" % (r["index"], seen[r["sha256"]], r["sha256"][:12]))
        seen[r["sha256"]] = r["index"]
    return out


def check_pack_id(pack_id):
    if not isinstance(pack_id, str) or not PACK_ID_RE.match(pack_id):
        raise GuardError("pack_id must match %s (got %r)" % (PACK_ID_RE.pattern, pack_id))
    if pack_id in RESERVED_PACK_IDS:
        raise GuardError("pack_id %r is reserved (a shipped/core pack); choose a new id" % pack_id)
    return pack_id


def prepare_pack_dir(project_dir, pack_id, create=True):
    """Returns the absolute pack dir (<realpath(project)>/packs/<id>). Refuses symlinks and foreign packs."""
    if not isinstance(project_dir, str) or not project_dir:
        raise GuardError("project_dir must be a non-empty path")
    proj = os.path.realpath(os.path.abspath(project_dir))
    if not os.path.isdir(proj):
        raise GuardError("project_dir does not exist or is not a directory: %s" % project_dir)
    packs = os.path.join(proj, "packs")
    if os.path.islink(packs):
        raise GuardError("refusing to write: %s is a symlink (writes must stay inside the project)" % packs)
    if os.path.lexists(packs) and not os.path.isdir(packs):
        raise GuardError("refusing to write: %s exists and is not a directory" % packs)
    pdir = os.path.join(packs, pack_id)
    if os.path.islink(pdir):
        raise GuardError("refusing to write: %s is a symlink" % pdir)
    if os.path.lexists(pdir):
        if not os.path.isdir(pdir):
            raise GuardError("refusing to write: %s exists and is not a directory" % pdir)
        prov = os.path.join(pdir, "PROVENANCE.json")
        entries = [e for e in os.listdir(pdir) if not e.startswith(".")]
        if entries:
            ok = False
            if os.path.isfile(prov) and not os.path.islink(prov):
                try:
                    with open(prov, "r", encoding="utf-8") as f:
                        ok = json.load(f).get("tool") == TOOL_ID
                except (OSError, ValueError):
                    ok = False
            if not ok:
                raise GuardError("refusing to overwrite %s: it is not a draft made by %s (no matching PROVENANCE.json)" % (pdir, TOOL_ID))
        for sub in ("proof", ".work"):
            sp = os.path.join(pdir, sub)
            if os.path.islink(sp):
                raise GuardError("refusing to write: %s is a symlink" % sp)
    if create:
        os.makedirs(pdir, exist_ok=True)
        if not _inside(os.path.realpath(pdir), proj):
            raise GuardError("pack dir resolved outside the project: %s" % os.path.realpath(pdir))
    return pdir


def safe_join(pack_dir, *parts):
    """Join under pack_dir and refuse anything that resolves outside it."""
    p = os.path.abspath(os.path.join(pack_dir, *parts))
    if not _inside(p, os.path.abspath(pack_dir)):
        raise GuardError("path escapes the pack dir: %s" % p)
    parent = os.path.dirname(p)
    if os.path.exists(parent) and not _inside(os.path.realpath(parent), os.path.realpath(pack_dir)):
        raise GuardError("path escapes the pack dir via a symlink: %s" % p)
    return p
