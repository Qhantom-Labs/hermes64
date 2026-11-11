# Security

Hermes64 executes local programs and handles user-supplied game/project data. Install only a release and source you trust; verify the supplied archive hash and `PACKAGE-MANIFEST.json` with `tools/check_install.py` before activation. A checksum establishes byte identity, not safety or licensing.

## Boundaries

- The central macOS runner denies network and confines writes, but some preview/character/audio helpers are outside it. Do not assume every subprocess is sandboxed.
- The opt-in Windows Job Object runner limits resources and process lifetime, **not network access or filesystem writes**.
- The model-facing doctor cannot consent to Godot downloads. A human-typed setup fetch is separate from plugin installation, and checks the pinned official SHA-512 before unpacking.
- Optional Hub HTTPS reads require configured `hub_url`. Host dependency preparation may modify the shared Hermes Python environment.
- No plugin credentials are declared. Do not put tokens, private models, recordings or private reference material in a bug report or public game package.

See [platform details](docs/PLATFORM-PARITY.md), [setup](docs/SETUP-FETCH.md) and [disclosure](docs/DISCLOSURE.md). These boundaries are source-documented behavior, not an independent security certification.

## Reporting a suspected vulnerability

Do not post an exploit containing private data in a public issue. If this repository's **Security → Advisories → Report a vulnerability** route is available, use it. That private reporting route has not been verified as enabled. If it is unavailable, ask the maintainer for a private reporting route without attaching secrets; no security email address or response-time promise is invented here.

Include the exact package source commit, Hermes/OS versions, a minimal redacted reproduction and expected versus actual behavior. Keep full logs private until reviewed. Do not test against someone else's files, credentials or systems.

If a package behaves unexpectedly, stop using that copy and retain its checksum and reports. Do not disable host approvals, weaken sandbox checks or overwrite the evidence to make a build pass. Suspected credential exposure requires the owner to rotate/revoke the affected credential; deleting a public file is not enough.
