# TIERS shared hunks

Files this lane touches that other lanes also own or edit. INTEG6 merges stack A; tiers-lane branches from detail-lane
313a383d, so detail-lane commits after that point (cc204933, a1a36416, 5e03ddc0, bacf2dfc) are the main overlap.

| file | owner / other lanes | change | size |
|---|---|---|---|
| `skills/hermes64-create/SKILL.md` | orch/orch2 (author); **detail-lane rewrote it** (a1a36416 1.2.0 story block; bacf2dfc waves and resume lines) | full rewrite to 2.0.0: how to call deferred tools, golden path with CORE tools in order, brief limits, refusals, ADVANCED tools by intent. Frontmatter name/description unchanged. | 93 -> 99 lines |
| `adventure_maker/tools.py` (`help_command` only) | token-diet / merge lanes | `/hermes64` help names the skill and the golden path; still names `hermes64_scaffold` and "tools" (`tests/test_registration.py`) | 8 -> 10 lines |
| `adventure_maker/wire.py` (`PARAMS`) | token-diet lane | one entry: `hermes64_compile.spec_path` gets a description ("Inside the project, e.g. source/spec.json; never absolute."); advertised copy only, validation unchanged; +19 schema tokens (5,868 -> 5,887) | +2 lines |

The two code hunks are `docs/tiers-hunks/tiers-surface.patch` (`git diff 313a383d HEAD` of those two files). Detail-lane
never changed them: the patch applies cleanly to bacf2dfc (`git apply --check`).

Merging the skill with detail-lane: a ready candidate is `docs/tiers-hunks/hermes64-create-with-detail.md` (2.1.0: the
2.0.0 sections plus detail's bacf2dfc story block, plan/report wording and "never drop a part of the prompt"; 112
lines, 105 in the body). When both lanes are merged, copy it over `skills/hermes64-create/SKILL.md`. It differs from
the shipped 2.0.0 in one measured-later line too: start `create_flow run` in the background (the host's 420 s cutoff,
docs/TIERS-HOST.md). `tests/test_tiers.py` checks both files: golden-path order, every ADVANCED tool listed once by
intent, no unknown tool or skill names, body at most 120 lines, the detail terms present in the candidate. Detail's own
tests do not read the skill text.

The candidate was run as condition C on bacf2dfc + the owner hunks + `tiers-surface.patch` (results in
docs/TIERS-RESULT.md; skill sha256 ed96e59f882e...). After C, only the count in the wire.py comment changed (2 -> 3 of
12 condition-A runs, once every A run was scored); the advertised schema is unchanged.

Files that are new in this lane (no conflict expected) are listed at the end of docs/TIERS-RESULT.md.
