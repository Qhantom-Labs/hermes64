# Hermes64 quick start (Mac)

Hermes64 is a plugin for Hermes that makes small 3D adventure games in the style of 1990s consoles. You describe a game in one sentence; it builds a playable starter you can then change.

## What you need

1. **Hermes** (the desktop app or the `hermes` command), already working.
2. **Godot 4.6.2**, the standard build (not ".NET"). Download `Godot_v4.6.2-stable_macos.universal.zip` from https://github.com/godotengine/godot/releases/tag/4.6.2-stable , unzip it, move `Godot.app` into Applications, then Control-click it and choose Open once.
3. Optional: **Blender**. Without it, room models are only built if you change one setting (see "If something is missing").

## Install

1. Unzip the Hermes64 zip into your Hermes plugins folder:
   ```
   mkdir -p ~/.hermes/plugins
   unzip hermes64-*.zip -d ~/.hermes/plugins
   ```
2. Check the copy (it should end with `PASS`):
   ```
   python3 ~/.hermes/plugins/hermes64/tools/check_install.py
   ```
3. Turn it on: run `hermes plugins enable hermes64`. If that fails (it needs the internet), open `~/.hermes/config.yaml` in a text editor and add:
   ```
   plugins:
     enabled:
       - hermes64
   ```
4. Restart Hermes.

## First game

1. Ask Hermes: *"Run hermes64_doctor and show me the table and the guidance lines."* It lists what works on your Mac and what to install. It changes nothing.
2. In Hermes, type:
   ```
   /hermes64 new "A fox searches the village for its lost lantern"
   ```
   After about 10 to 40 seconds you get four or more lines: where the game is, the style it picked, a badge, and a `Play:` line.
3. Copy the `Play:` line into Terminal and press Enter to play. Keys: WASD move, E act, Tab action menu, I inventory, Esc pause.

The first game is a two-room starter, not a finished game. Ask Hermes to change it ("move the door to the east wall", "add an ending") and it edits, re-checks and updates the same `Play:` folder.

## Share it

Ask Hermes to *"export my game for web and macOS"*. This needs Godot's export templates (about 1.25 GB, a separate download; the error message tells you where and how). Exports take one to two minutes and land inside the game folder under `.maker/runs/export-.../share`.

## Studio (desktop app)

In the Hermes desktop app: Capabilities > Plugins > Rescan, then turn on **Hermes64 Studio**. Your games appear as boxes on a shelf.

## If something is missing

- **"Godot wasn't found"**: install Godot 4.6.2 as above, or set `godot_path` in the hermes64 plugin settings.
- **"assets NOT BUILT (Blender not found ...)"**: either install Blender, or set the hermes64 plugin setting `builder` to `auto`. `auto` needs a Python with numpy.
- **"numpy is missing ..."** (from the doctor): set `python_path` in the plugin settings to a Python 3.9 or newer that has numpy. Hermes64 never installs anything for you.
- **"export templates aren't installed"**: follow the steps in that message, then export again.
- **"style audit FAIL"** on the badge: the game still plays; the look did not pass the automatic check. Ask Hermes to follow the audit's next steps, or try another style by adding a word after the sentence, for example `forest` or `polar`.

Nothing is uploaded. Games stay on your Mac.
