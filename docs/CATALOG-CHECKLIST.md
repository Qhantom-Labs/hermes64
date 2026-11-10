# Catalog submission checklist — DO NOT SUBMIT YET

Source: cached official `catalog-submission.md` (all 18 admission rules); canonical URL in PUBLIC-SURFACE.md. Current scope forbids public/network/install actions. A local source check or recording ctx is not catalog admission. **NOT DONE means no evidence, not implied approval.**

## Prerequisites / entry fields

| Gate | State / evidence |
|---|---|
| Public HTTPS-cloneable repository | **NOT DONE**. No remote created. |
| Final assembled plugin at pin, loadable entrypoint | Local root `plugin.yaml` + `__init__.py` and complete assembled tree exist; real facade/component execution is in RESULT.md. **Real Hermes load NOT DONE.** |
| Plugin name/version/license | Local `hermes64`, quoted JSON string `"0.1.0"`, MIT LICENSE. Name clearance/owner final branding NOT DONE. |
| Catalog `plugin-catalog/hermes64.yaml` | **NOT DONE**; no fake entry/pin is supplied. One file in eventual owner-approved PR. |
| Full 40-character git SHA | **Local implementation candidate:** `89b383de9ed3bf83d1fe4b83fc16c06764afa1cc` (RESULT.md). **Final reviewed catalog pin NOT DONE.** Installed Hermes source SHA is NOT a submission pin. |
| `repo`, optional monorepo `subdir`, quoted `version`, capabilities inventory | **NOT DONE** for catalog entry. Final design places plugin at repo root; no subdir needed unless Main changes that. |
| Truthful `requires_hermes` floor in manifest AND entry | **NOT DONE**. Manifest intentionally omits field. Need tested minimum released SemVer, not CalVer, HEAD, or an invented example floor. Do not release without it. |
| `hermes plugins validate <pinned-path> --install-deps` / same catalog CI | **NOT DONE**. This commission prohibits installs and full bootstrap's lane-only behavior is unproven. Empty Python dependencies does not itself establish CI parity. |
| Install security scan / caution review | **NOT DONE**. No scanner executed; no clean/safe verdict claimed. |
| Demo/UI screenshots, <90 s owner-approved X demo, Typeform | Local all-room captures/contact sheets exist (RESULT.md). **Public demo/Typeform NOT DONE**; separate owner/public-action gates. |

## Every admission rule

| # | Rule | Evidence / outstanding action |
|---|---|---|
| 1 | Human-merged gate | **NOT DONE**: maintainer-reviewed catalog PR and merge. No self-serve listing. |
| 2 | Exact SHA pin | **NOT DONE**: full 40-character commit of complete reviewed tree. |
| 3 | No self-updating code | Local source: no network/updater/downloader in production modules. Pin-reviewed final tree audit **NOT DONE**. |
| 4 | SHA bumps get new PRs | Documented release policy; no update/pin exists. Future updates require a fresh reviewed pin. |
| 5 | Owner/major-contributor submission | Authored for Dylan/Qhantom; submission/identity authority and actual owner PR **NOT DONE**. |
| 6 | Declared capabilities match reality | Local recording-ctx tests assert 13 exact provides_tools names, empty hooks/middleware/env/capabilities; one help slash command documented. Actual Hermes validator and pinned tree **NOT DONE**. |
| 7 | Install scanner at admission | **NOT DONE**. Dangerous must block; caution findings need reviewer disclosure/resolution, not suppression. |
| 8 | Desktop stays inside SDK | No Desktop plugin/UI shipped; rule not applicable to current native tool-only package. Final tree check **NOT DONE**. |
| 9 | Public surfaces, no core overrides | Production uses only ctx registration/settings plus stdlib/relative imports; no monkeypatch or private Hermes import. Source review and recording test evidence; admission lint/review **NOT DONE**. Inspection helper is development-only, not installed plugin code. |
| 10 | Plugin dependency security | `python_dependencies:[]`; implementation/tests stdlib-only. Existing external engines disclosed. Complete assembled dependency/constraint audit **NOT DONE**. No unbounded pip floors added. |
| 11 | Credentials through Hermes, never stores | No credentials/env/auth declaration or secret-store read needed. Child env scrubbed. No OAuth route to audit in this package. Final scan/review **NOT DONE**. |
| 12 | Respect approvals/unattended | Read-only slash help; no automatic config/guard changes, shell child, inherited approval flags or prompts. argv/timeout tests verified. Real Hermes approval-route behavior **NOT DONE**. |
| 13 | Disclose risky behavior | README + DISCLOSURE.md cover subprocesses, reads, writes, previews, no network/telemetry/credentials, macOS scope and limits. Catalog PR disclosure **NOT DONE**. |
| 14 | Truthful compatibility | **NOT DONE** for minimum released Hermes SemVer and pinned-version matrix. Python 3.9.6 local unit execution observed; not general compatibility. |
| 15 | No skins/forks of bundled plugins | New maker architecture/source; no bundled plugin fork/skin or vendor-lookalike Desktop UI. Name/brand final review **NOT DONE**. |
| 16 | One listing per lineage | No GameForge code copied; convention-only inspection documented. No upstream-lineage claim or second listing created. Maintainer review **NOT DONE**. |
| 17 | Reviewable executable payloads | Production artifact is source/data; no compiled engine, binary library, WASM or committed bytecode intended. Final manifest/audit records exact local files; full assembled binary/security scan **NOT DONE**. Generated game art is not a precompiled plugin executable. No attestation exemption claimed. |
| 18 | Vendor-only password-manager backends | Not applicable: no login backend/vault integration. |

## Required release sequence (not authorization)

Finish sibling contracts and assemble; make Thaw through plugin tools; exercise real STORY/Blender/Godot and all acceptance gates; independently review; establish minimum Hermes release; create owner-approved public repo/commit; record full SHA; run permitted full validation/scan against that pin; reconcile every warning; obtain approval for catalog PR/demo/Typeform separately. No production activation, install or public action follows automatically from this checklist.
