<!-- Suggested README fragment for Main; not an installation/default change. -->

## Blender is optional for static kits (opt-in)

Use an existing Python 3.9+ interpreter containing **numpy**, set `python_path` to it, and choose `builder=python` (or `auto`). Static geometry, textures, baked colours and GLB export then run without Blender. The binary writer itself uses only the standard library. Verified bundled kits and prebuilt cast are reused unchanged.

Reference-to-pack's staged developer workflow also works without Blender: PNG measurement uses Python/numpy; JPEG additionally needs Pillow. Proofs use existing Godot or a clearly labelled lower-fidelity software preview. Results remain **draft_unapproved**.

Godot is still required for play/replay/screenshots and executable exports. New custom character bodies, armatures and animation exports still need Blender. Nothing is installed automatically.

**Not yet the default:** 249/276 strict paired parity cases passed, while the fixed 12/12 Godot render subset passed. Some source parameter samples fail existing validators on both builders. Blender remains the default until the full parity gate passes. This is not universal visual or creative approval.

See [capabilities and limits](docs/NOBLENDER.md), the [measured parity table](docs/NOBLENDER-PARITY.md), and [integration/doctor registration](docs/NOBLENDER-INTEGRATION.md). Local capability check: `python -B -m adventure_maker.doctor --table` using the chosen interpreter. Main's registered doctor wrapper must probe the actual `python_path` through Runner.
