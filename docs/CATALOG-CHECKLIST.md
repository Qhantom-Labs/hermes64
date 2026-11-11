# Catalog checklist: public repository, admission pending

**Public repository: yes**, https://github.com/Qhantom-Labs/hermes64. The plugin is the submission; its separate demo is supporting evidence. Public visibility does not establish catalog admission. **The catalog PR pins the public repository's own full commit SHA**; no future SHA, submitted PR or maintainer acceptance is asserted here.

## Manifest and recorded checks

`plugin.yaml` declares `hermes64`, version `1.0.0-rc`, author `Qhantom Labs`, MIT, `requires_hermes >=0.18.2`, platforms `[macos, windows]`, **27 tools**, hook `[pre_llm_call]`, no middleware/capability grants/required environment secrets, and bounded numpy/Pillow dependencies. `__init__.py` registers 11 skills, the command, tools and hint hook.

On the unzipped rc7 package, `hermes plugins validate . --install-deps` returned **exit 0**, security scan **safe**, **1 warning**. The warning is catalog rule 9: the lazy, guarded `hermes_cli` import in `adventure_maker/host_compat.py` for the host-version check. The Blender-only `tools.preview` isolation note is informational, not another warning. `hermes plugins doctor --ci` also returned 0 and reported 27 tools and 1 hook. Source: repository-only `docs/FINALINT4-RESULT.md`, exact validation/doctor transcript. These are rc7 receipts, not a new rc8 pass.

Validation used a scratch Hermes home, but `--install-deps` changed the shared host dependency environment; the rc7 receipt records that side effect. This text-only lane did not repeat an install or validation. The rc7 checksum and structural checks are package evidence, not credentials/history clearance or legal rights.

## Admission rows mapped to evidence

Rule labels come from the locally inspected catalog guidance; current upstream policy was not fetched in this offline lane.

| Rule | Evidence / still required |
|---|---|
| 1. Human-merged catalog entry | **Maintainer review: not yet.** Approved submission and human merge remain pending; no listing claimed. |
| 2. Exact public SHA | The catalog PR pins the public repository's own full commit SHA, not an implementation or private development SHA. Fill it only after the public commit exists. |
| 3. No plugin self-updating | Setup fetch is for official Godot, not plugin replacement: [setup disclosure](SETUP-FETCH.md). Final code review still required. |
| 4. Updates use new pin PRs | Future release process, not permission to publish. |
| 5. Owner/major contributor submits | Author is Qhantom Labs; the owner chooses the submitting identity and authorizes the PR. |
| 6. Capability match | rc7 validation/doctor matched 27 tools and 1 hook; repeat on the exact final package. |
| 7. Admission security scan | rc7: safe, validation exit 0, one rule-9 warning above. Exact-final-package validation remains a separate gate. |
| 8. Desktop SDK boundary | Desktop source and backend ship; rc7 validator passed the SDK boundary check. Maintainer review remains open. |
| 9. No core overrides | rc7 validator passed no-runtime-rebind checks; the guarded host-version private-import warning remains disclosed. |
| 10. Dependency policy | `numpy>=2.0,<3`, `Pillow>=11.3,<14`; preparation requires host consent and can affect its shared environment. |
| 11. Credential handling | `requires_env: []` is a declaration, not a universal secret audit. See [security](../SECURITY.md). |
| 12. Approval/unattended behavior | Human-only setup fetch vs model doctor; no policy bypass proposed. |
| 13. Risk disclosure | [Disclosure](DISCLOSURE.md), [platform parity](PLATFORM-PARITY.md), setup and security guidance. |
| 14. Compatibility | Floor `>=0.18.2`: 0.18.2 source/parser and stub-adapter checks; actual 0.22.7 runs in the rc7 receipt. The [quick start](../QUICKSTART.md#command-evidence-and-not-verified) records 0.23.1 source/parser checks only. No 0.23.0 runtime receipt was located here, so no pass is claimed for it. |
| 15. Not a bundled-plugin skin/fork | Maintainer lineage review remains required; no endorsement claimed. |
| 16. One listing per lineage | One proposed `hermes64` listing; actual catalog state was not checked over the network. |
| 17. Reviewable payloads | rc7 structural scan found no forbidden archives/executable headers; generated assets still need provenance review. |
| 18. Password-manager backends | No password-manager backend is declared or proposed. |

## Before submission

- Rebuild and verify the exact final package after merges; the integrator will record rc8 in repository-only `docs/FINALINT5-RESULT.md` when produced. Do not expose development history, submission drafts or private demo material.
- Verify a clean install and first game from the README in a new chat; retain failures and version/build identifiers.
- Supply final UI screenshots, approved video/post, form answers and public URLs only after they exist. A video placeholder is not evidence.
- Keep exact-final-pin native Windows and rights confirmation open until supplied. No all-green, all-platform or aesthetic verdict is implied.
