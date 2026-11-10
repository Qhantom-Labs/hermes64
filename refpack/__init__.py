"""refpack: reference images -> draft Hermes64 theme pack (tool `hermes64_pack_from_refs`).

Public API: `refpack.pack_from_refs(...)`. Stdlib orchestration; numpy for static
generation/measurement, optional Pillow for JPEG, Godot or labelled software proof.
Blender modules are retained only as reference-test oracles, never called by this API."""
from .tool import pack_from_refs  # noqa: F401
from .config import TOOL_ID, TOOL_VERSION  # noqa: F401
