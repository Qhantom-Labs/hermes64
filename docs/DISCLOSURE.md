# Catalog disclosure — public repository, review pending

Hermes64 is a native Python Hermes plugin for authoring small, room-based, late-1990s-console-style 3D adventures from structured game data and theme packs. `plugin.yaml` declares version `1.0.0-rc`, author Qhantom Labs, MIT, **27 tools**, one `pre_llm_call` hint hook, and `requires_hermes >=0.18.2`. It also registers the `/hermes64` command and 11 skills and includes an optional Desktop Studio surface. No middleware, privileged capability grant or required environment secret is declared.

## Local execution and storage

Godot, Python, optional Blender and user-provided ffmpeg are local subprocesses. Godot is not bundled. The default `builder=auto` can use Python with numpy for static rooms; some character workflows still require Blender. Tool callers cannot supply arbitrary executable scripts through the structured game format. Executable overrides and component bundles must be trusted by the owner.

The central macOS runner denies network and confines writes with `sandbox-exec`, but not every character, preview or audio helper uses that runner. The sandbox is not a confidentiality/read sandbox. Some helpers can inherit the host environment. Windows child execution needs explicit `HERMES64_WINDOWS_RUNNER=job` opt-in: Job Objects bound resources and child lifetime, **not network or filesystem access**. Linux authoring runs children inside bubblewrap (no network, writes confined to the project) and is not verified; without a working bubblewrap it is off unless the owner opts in to `HERMES64_LINUX_RUNNER=unconfined` (no OS-enforced network or write confinement). See [platform parity](PLATFORM-PARITY.md), [Windows](WINDOWS.md) and [Linux](LINUX.md).

Game data, builds, reports and exports use the configured project/data roots. Modern storage-capable hosts default to `<Hermes home>/plugin-data/hermes64/games`; older hosts need an explicit `projects_root`. Setup downloads use a separate per-user cache. The create flow can also write a generated style pack inside the installed plugin folder; `tools/check_install.py` reports these additions as extra files. Studio Play can serve an export on `127.0.0.1` at a random port with a 30-idle-minute limit. These are exceptions to any earlier claim of project-only writes or foreground-only execution.

## Network and approval

Ordinary game creation does not fetch Godot. The human-approved setup flow downloads pinned official Godot files over HTTPS and verifies SHA-512 before unpacking; configured Hub reads can also use HTTPS. Hermes dependency preparation for the declared numpy/Pillow requirements is a separate host action and may affect its shared Python environment. No plugin self-update, telemetry, OAuth provider or stored credential is declared. See [setup fetch](SETUP-FETCH.md), [security](../SECURITY.md) and the [README boundaries](../README.md#platforms-and-security-boundaries).

## Admission and compatibility evidence

- **Public repository: yes**, https://github.com/Qhantom-Labs/hermes64. Public visibility is separate from catalog admission.
- **Validation:** `hermes plugins validate . --install-deps` exited **0** on the unzipped **rc7** package in a scratch Hermes home; security scan **safe**, **1 warning**. The warning is catalog rule 9: the lazy, guarded `hermes_cli` import in `adventure_maker/host_compat.py` used to read the host version. The Blender-only `tools.preview` isolation note is informational, not another warning. Source: repository-only `docs/FINALINT4-RESULT.md`, validation receipt. This is rc7 evidence, not a new rc8 validation claim. Dependency preparation changed the shared host environment despite the scratch home, as that receipt discloses.
- **Pin:** the catalog PR pins the public repository's own full commit SHA. No not-yet-created SHA or submitted PR is asserted here.
- **Maintainer review:** not yet; no catalog acceptance or endorsement claimed.
- **Compatibility:** `requires_hermes >=0.18.2`. The 0.18.2 source/parser checks and stub adapter tests are not a fresh native install. Actual 0.22.7 runs are recorded in the rc7 receipt. Local 0.23.1 source/parser checks are recorded in the [quick start](../QUICKSTART.md#command-evidence-and-not-verified); a 0.23.0 runtime receipt was not found in this lane's available records, so no such pass is asserted.

The plugin is the submission; a separate demo illustrates it. Story proof, bot completion, replay and measured image gates do not certify fun, balance, appearance or rights. Exact-final-package validation, native Windows acceptance, rights clearance and maintainer review remain distinct gates. Repository-only `docs/FINALINT5-RESULT.md` will record rc8 integration evidence when produced.
