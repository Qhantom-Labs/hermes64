# Quick start: install to your first game

**Shortest full-game path:** install and enable the plugin, restart Hermes, start a **NEW chat**, then ask for a game. Keep your existing working Hermes model/provider; no new account is required by the plugin. The repository is public: https://github.com/Qhantom-Labs/hermes64.

## 1. Install and enable (Terminal or PowerShell)

```sh
hermes plugins install Qhantom-Labs/hermes64 --enable
hermes plugins list --enabled
```

This needs the network (GitHub, and PyPI for numpy and Pillow). Review any dependency/security prompt; `--enable` does **not** skip dependency consent. Do not grant built-in tool override: Hermes64 does not need it. On recent hosts dependency preparation can change Hermes's shared Python environment, not just the current `HERMES_HOME`. Do not bypass a failed enable by editing `plugins.enabled` by hand.

Two-step alternative: `hermes plugins install https://github.com/Qhantom-Labs/hermes64.git --no-enable`, then `hermes plugins enable hermes64`. If the one-liner is unavailable, use a supplied release ZIP (no network needed when Hermes's Python already has numpy and Pillow): use the checksum/backup recipe in [Install for your agent](docs/INSTALL-FOR-YOUR-AGENT.md). Do not pass a ZIP or a bare filesystem directory to `plugins install`.

## 2. Restart, then start a NEW chat

Exit/reopen the Hermes surface that runs your agent and create a new conversation. Do not resume the pre-install chat. If a shared backend owns the session, arrange its supported refresh with its owner rather than interrupting other work. A new window alone does not establish that a long-lived backend reloaded the plugin.

## 3. First prompt

> Make me a game about a wizard tower with a ghost and three crystal keys.

No special slash command should be needed on a host that discovers the plugin. **Expect minutes to craft it; a fuller game may take longer.** This is the agent-designed path, not an instant demo selector. The agent should load `hermes64:hermes64-create`, plan, build, run bots and report unsupported details instead of silently dropping them.

### Expected first reply and completion

These are the content to expect, **not an observed verbatim model transcript**:

```text
I will make: <the supported rooms, characters, objectives and mechanics>.
Not as asked: <each unsupported detail and the closest supported version, or none>.
The build and bot checks will take minutes. I will report their actual results.
```

The shipped skill asks for `I will make: ... Not as asked: ...` after the plan, then proceeds without another design interview. Before setup is ready, expect the missing dependency and one next step instead. The final reply should give the game folder and how to play, what was not applied, the actual story/bot/audit results and any available captures. A refusal or failed gate must stay visible. These lines are expectations, not a promise that every model follows them.

## If setup is missing

In Hermes:

```text
/hermes64 setup
```

This is a read-only checklist, not a dependency installer. The agent's `hermes64_doctor` tool reports the checklist and official download plan too. It has no download-consent argument.

If Godot is absent, the **human** types:

```text
/hermes64 setup --fetch
/hermes64 setup --fetch --yes
```

The first line is a plan only; the second is your explicit download approval. It fetches the official **Godot 4.6.2** standard editor for the host OS, verifies pinned SHA-512, safely unpacks to the user cache and runs `--version`. macOS quarantine is removed only from that verified app. Merely installing the plugin, calling doctor or asking for a game does **not** fetch Godot. Add `--templates` only when exporting; templates are a separate large download. [Fetch details and cache locations](docs/SETUP-FETCH.md).

Blender is optional for static rooms: the default `builder=auto` can use Python with numpy. If doctor names missing numpy/Pillow or a bad executable override, fix that exact requirement through the host's approved dependency path. Do not install extra tools or change approval settings just to make a green report.

## Where games go

On storage-capable hosts: `<Hermes home>/plugin-data/hermes64/games`. A configured `projects_root` wins. Use the absolute folder the actual report returns.

**0.18.2 needs an explicit existing games directory.** On Mac, after installation:

```sh
mkdir -p "$HOME/Hermes64 Games"
hermes config set plugins.entries.hermes64.settings.projects_root "$HOME/Hermes64 Games"
```

PowerShell equivalent (not executed on Windows here):

```powershell
New-Item -ItemType Directory -Force -Path "$HOME\Hermes64 Games" | Out-Null
hermes config set plugins.entries.hermes64.settings.projects_root "$HOME\Hermes64 Games"
```

Then restart/new chat as above. The old installer does not establish that numpy/Pillow are present; run the checklist. The old-host compatibility adapter and exact-name skill loading are documented in [HOST-COMPAT](docs/HOST-COMPAT.md). Windows also needs the explicit Job Object opt-in in [WINDOWS](docs/WINDOWS.md); no native Windows proof is supplied by this guide.

## If nothing happens

1. **Plugin listed?** Run `hermes plugins list --user --plain` in the same profile/home as the agent. Check that `hermes64` exists and is enabled. If absent, confirm the installed directory contains `hermes64/plugin.yaml`, not `hermes64/hermes64/plugin.yaml`.
2. **New chat?** Restart/refresh the correct execution host, then create a new chat. Do not continue the stale chat that existed before installation.
3. **Tools visible?** Ask the agent to describe `hermes64_doctor`. Recent hosts defer plugin tools: it should use `tool_describe`, then `tool_call`, rather than treating absence from the immediate tool list as absence from Hermes. Use `hermes tools list` to inspect the active profile if discovery still fails.
4. **Skill visible?** Ask: `Load the skill hermes64:hermes64-create, then make the game with Hermes64.` On older hosts it may load only by exact name rather than appear in the skills index.
5. **Can the plugin answer directly?** Type `/hermes64 setup`. Keep its `This is Hermes64 ... running from ...` build-identification line and missing-requirement rows. If it still cannot answer, report the error; do not let the agent silently substitute a browser game or another engine.
6. **Build already running?** Let the agent inspect its existing create-flow status/report. Long work belongs in a background terminal process; a foreground timeout is not permission to start a duplicate build.

## Fastest smaller alternative

If you want only a starter rather than a game authored by your agent:

```text
/hermes64 new "A fox searches the village for its lost lantern"
```

Read its actual game folder, asset/bot/audit results and `Play:` command. A starter is not a finished original game. The full-game prompt remains the recommended plugin trial.

## Command evidence and NOT verified

Only local source/help and the rc7 package were used; no documentation website or network was fetched.

| Host basis | What was checked | Limit |
|---|---|---|
| 0.18.2 source, commit `9de9c25f620ff7f1ce0fd5457d596052d5159596` | Its intact parser accepts `plugins install URL --enable`, `plugins enable hermes64` and `plugins list --user --plain`; installer URL resolver inspected/exercised | No running 0.18.2 install or Windows execution. No dependency-install guarantee. |
| 0.22.7 local source/tag | Same command parser/resolver checks; `--no-enable` exists | Published launcher in a fresh scratch home stopped before help: `no dependency environment is committed for this install`. No repair attempted. |
| 0.23.1 local source/tag | Same parser/resolver checks; install help includes dependency consent options | Source-level check only, not a running 0.23 host. |

All three resolvers interpret `/absolute/path/hermes64` as GitHub shorthand, **not** a local path. `file:///absolute/path/hermes64` is accepted as a Git URL and needs a Git repository, not an extracted ZIP; installation was not exercised. No need to create a Git repo just to install a ZIP.

The package hash and all 5,964 manifest files were verified locally. The Mac ZIP extraction/check recipe was exercised separately; fresh-host install/enable, dependency fetching, real Godot download, a new model-driven first game and native Windows execution were **not verified in this docs lane**. Source parser success is not installation success. No speed benchmark for a clean first install is claimed.
