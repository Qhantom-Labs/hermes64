## Physical playtest, local exports and one-command demo

From this assembled checkout on macOS, with existing Python 3.9+, Blender and official Godot 4.6.2 plus separately approved verified release templates:

```sh
python3 -m adventure_maker.demo --projects-root /absolute/existing/project-root --project first-demo
```

Bare `python3 -m adventure_maker.demo` uses the current directory as the existing root and `hermes64-demo` as its project ID. It scaffolds Last Light (or `--example starter` / `--example thaw`), compiles/checks, builds real assets, follows proof witnesses through physical Godot movement, explores with seeded inputs, builds a no-threads web export and prints measured stage timings and paths. Repeating an unchanged demo is safe: it reuses asset caches, retains fresh run receipts and refuses to reset edited/unowned projects. The ~10-minute cold target is a goal, not a fixed promise; receipts report actual execution. Template downloads are never automatic.

New tools (after [Main's additive registration](docs/SHIP-INTEGRATION.md)):

- `hermes64_playtest`: fixed-step winning-path + explorer probes; reports, room heatmaps, optional captured contact sheet; SOLID/PLAYABLE/ROUGH/BROKEN with reasons. **Cannot judge fun.**
- `hermes64_export`: local web, macOS and Windows artifacts, licenses, sorted hash inventories and a share ZIP. **Windows execution unverified on Mac. Nothing is uploaded.**
- `hermes64_demo`: the same pipeline as the CLI, using the configured existing project root.

See [PLAYTEST](docs/PLAYTEST.md), [EXPORT](docs/EXPORT.md), [SHIP disclosure](docs/DISCLOSURE-SHIP.md), and the lane's `evidence/ship/` receipts. A successful export is not browser/recipient acceptance; use the separate headless-Chrome smoke and native Mac receipt. These additions do not change authored stories, character assets or visual styles.
