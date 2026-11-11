# README disclosure paragraph for the setup download (CAT-FIX F4)

Paste under "What this plugin does on your computer", **Network**, in README.md when the godotfetch lane merges
(the rc3 README carries an `A3` marker for it). Text for strangers, catalog rule 13:

> **Setup download (only when you type it).** If you type `/hermes64 setup --fetch --yes` (or run
> `tools/hermes64_setup.py --fetch` and answer yes), Hermes64 downloads the official Godot 4.6.2 editor for your OS
> (`Godot_v4.6.2-stable_macos.universal.zip` or `Godot_v4.6.2-stable_win64.exe.zip`, capped at 512 MiB). With
> `--templates` it also downloads Godot's official export templates (`Godot_v4.6.2-stable_export_templates.tpz`,
> about 1.25 GB, capped at 1.4 GiB), keeps only the three players exports use and deletes the rest. Both come only
> from `github.com/godotengine/godot-builds` (redirects only to GitHub's release-asset hosts), and each file must
> match the SHA-512 published by Godot before anything is unpacked. Files go to `~/Library/Caches/hermes64/` (macOS)
> or `%LOCALAPPDATA%\hermes64\` (Windows), never into the plugin folder. It runs the verified Godot once with
> `--version`; on macOS it also removes the download quarantine flag from that verified Godot.app only. The agent cannot start this
> download: its setup tool only shows the plan and the command for you to type.
