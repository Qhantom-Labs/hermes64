"""Locations of the read-only sources (overridable by env or arguments). Nothing here is written."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LANE = os.path.dirname(HERE)
ADVENTURE = os.path.dirname(LANE)

TOOL_ID = "hermes64_pack_from_refs"
TOOL_VERSION = "1.1.0-python"


def kits_dir(override=None):
    return os.path.abspath(override or os.environ.get("HERMES64_KITS_DIR") or os.path.join(LANE, "kits"))


def audio_dir(override=None):
    return os.path.abspath(override or os.environ.get("HERMES64_AUDIO_DIR") or os.path.join(LANE, "audio"))


def blender_bin(override=None):
    return override or os.environ.get("HERMES64_BLENDER") or "/opt/homebrew/bin/blender"


def library_path(name):
    return os.path.join(HERE, "library", name)
