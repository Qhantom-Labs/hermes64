# ORCH owner hunks (not applied in orch-lane)

The create flow works without these (`python -B -m adventure_maker.create_flow run "<prompt>" --projects-root DIR`).
They hook it into the existing `/hermes64 new` path, ship the modules it needs in the package, and register its
skill. No tool schema changes: the Hermes tool count and schema tokens are unchanged by all three.

Apply order (each passes `git apply --check` at the stated base):

1. `docs/agen-hunks/*.patch` (AGEN lane; `register-generator-skill.patch` must come before hunk 4 below, and
   `packs-gen-id.patch` is what lets a project pack place `gen:` recipes; without it generated pieces are built and
   reported but listed as not placed).
2. `docs/orch-hunks/newgame-create.patch` - owner: newgame.py (integrator).
3. `docs/orch-hunks/package-include.patch` - owner: tools/package.py (integrator / CAT-FIX).
4. `docs/orch-hunks/register-create-skill.patch` - owner: `__init__.py` entrypoint (integrator).
5. `docs/orch-hunks/package-contents-doc.patch` - owner: docs/PACKAGE-CONTENTS.md; documents hunk 3 (needs AGEN's
   `package-consumer-doc.patch` first). With both doc hunks `tests/test_package.py` passes in the integration copy.

## 2. newgame.py: `/hermes64 new --create "<prompt>"`

A leading `--create` token routes the slash command to `create_flow.command_create`, which reuses `new`'s own premise
check, doctor (`preflight`), games-folder rule (`resolve_root`, the plugin data dir `games/` by default) and one-line
failure format, then runs the create flow and replies with 4-5 lines (made/where, style+mood, needs ready + bots +
closeness, report path, count of things it could not make). Without `--create` nothing changes. The `hermes64_demo`
tool schema is not touched (no new action: the schema budget is near its cap), and the reply-line pins of
`tests/test_newgame.py` stay valid because the classic path is unchanged.

```diff
--- a/adventure_maker/newgame.py
+++ b/adventure_maker/newgame.py
@@ -400,13 +400,26 @@ def run_tool(settings, args, default_root=None):
         return json.dumps(failure(exc), ensure_ascii=True)
 
 
+def split_create(raw):
+    """A leading `--create` routes `/hermes64 new` to the create flow (brief, mood, gap report, generated pieces,
+    dressed rooms, honest report): adventure_maker/create_flow.py. Anything else is the classic starter path."""
+    value = (raw or '').strip()
+    if value == '--create' or value.startswith('--create '):
+        return True, value[len('--create'):].strip()
+    return False, raw
+
+
 def command(ctx, raw):
     """Slash command text: the four-line success summary, or one plain-English failure line."""
     from .tools import SETTINGS
     from .plugin_settings import default_games_root
     try:
         settings = {key: ctx.get_config(key, '') for key in SETTINGS}
+        create_mode, raw = split_create(raw)
         premise, style, name = parse(raw)
+        if create_mode:
+            from .create_flow import command_create
+            return command_create(settings, premise, style, name, default_games_root(ctx))
         return create(settings, premise, style, name, default_games_root(ctx))['message']
     except Exception as exc:
         return 'Hermes64 new: ' + failure(exc)['error']['message']
```

Tested in a disposable copy (orch-lane + AGEN hunks + these hunks, `git init` scratch repo, never this worktree):
`tests/test_newgame.py` 12 tests OK; the western proof prompt was run through `newgame.command(ctx, '--create "a
western train-robbery shootout"')` with a host-like ctx (plugin data dir) inside the clean-HERMES_HOME package and
replied with the 5-line summary (`docs/ORCH-RESULT.md`). The `/hermes64` help text (wire.py) does not mention
`--create`; that one-line help addition is left to the wire.py owner.

## 3. tools/package.py: ship the modules the flow imports

```diff
--- a/tools/package.py
+++ b/tools/package.py
@@ -47,6 +47,8 @@ INCLUDE = (
     'tools/check_install.py', 'tools/roomlook.py',
     # Data-only generator CLI screens recipes with the same derived bible consumer as kit authoring.
     'tools/style_bible.py',
+    # Create flow (ORCH): the kit room compilers it compiles room skeletons with, and the mood pack derive/install.
+    'tools/medievalkit_rooms.py', 'tools/westernkit_rooms.py', 'tools/mood_pack.py',
 )
```

Without it a package install refuses the style/mood/rooms stages with one line (`create_component: tools.mood_pack is
not available in this plugin tree ... Next: apply docs/orch-hunks/package-include.patch ...`). All three
are stdlib + the shipped `kits/core` modules.

## 4. `__init__.py`: register the skill (after the AGEN generator-skill hunk)

```diff
--- a/__init__.py
+++ b/__init__.py
@@ -19,6 +19,7 @@ SKILLS = {
     'hermes64-characters': 'Make house-style characters with hermes64_character.',
     'hermes64-hub': 'Use when sharing or installing Hermes64 Hub entries.',
     'hermes64-generators': 'Use when a game needs a new prop. Author bounded recipes.',
+    'hermes64-create': 'Use when asked to make a game from a prompt. Run create.',
 }
```
