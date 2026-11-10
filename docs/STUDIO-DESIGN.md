# Hermes64 Studio: design

![The catalogue home: the selection on the fourth card, half cards at both edges](studio/final/home-page-1280x720.jpg)

![A game's detail card: what was verified, in words](studio/final/detail-1280x720.jpg)

![The Studio page beside the SESSIONS | BOTS | STUDIO tab (mock host window)](studio/final/plugin-in-context-1440x810.jpg)

These are real headless-Chrome renders of this branch. In the third image, only the two plugin views are real; the window chrome around them is a stand-in, not the Hermes app.

More renders:

- `docs/studio/final/`: every state at 480x720, 960x600, 1280x720 and 1920x1080, plus motion filmstrips;
- `docs/studio/STUDIO-SHEET.jpg`: one sheet of the main states;
- `docs/studio/steer1-before-after.jpg`: the previous dark design beside this one.

Prototype: open `studio/prototype/index.html` (it works from `file://` or any static server). Desktop half: `desktop/plugin.js` (generated). Install steps and what is untested: `docs/STUDIO-INSTALL.md`. Critique rounds: `docs/studio/CRITIQUE-1.md` to `CRITIQUE-6.md` for the first design, and `docs/studio/CRITIQUE-STEER1.md` for this one (with the band-position table).

---

## What it is

A third place in Hermes Desktop, beside Sessions and Bots, where the games you make with the Hermes64 plugin live as boxed games on a shelf. It is a bright, late-90s console-style menu:

- a row of box cards, the selected one enlarged and framed in blue;
- the game's name in a wide title bar;
- a strip of tiny covers for the whole library.

Opening a card shows what the game is and what has honestly been checked. From there you play it, hand it to Hermes to edit, export it, or open its folder. A blank NEW GAME card starts a new game by handing your premise to Hermes in a fresh chat.

The Studio reads your local projects folder. It never uploads, fetches or publishes anything.

## Where it lives in the app

Three doors, one place:

1. **A Studio tab beside SESSIONS | BOTS.** A narrow rack of game spines, with NEW GAME on top and a red OPEN STUDIO button at the bottom.
   - Each spine shows a colour band for the style, the game's name, a verdict dot, and a SAMPLE tape where it applies.
   - The selected row is framed in blue, and it follows the page's selection.
   - Arrow keys move; Enter or a click opens the full Studio on that game.
2. **A "Studio" row in the sidebar nav** (codicon `game`).
3. **The Studio page** at `/hermes64-studio`, the catalogue described below.

## The catalogue home

The page is composed on a 1280x720 stage and scaled as one piece, so a big window shows the same screen larger, not a stretched web page.

A window under 760 px wide, or taller than it is wide, gets a narrow layout: one centred card with both neighbours peeking, and the menu centred under the wordmark.

From top to bottom:

- **Wordmark** (top left). "HERMES" in chunky H64 Pixel letters, with a sunny gold-to-orange fill, a dark outline and a stepped 3-D extrusion. Beside it sit a sky-blue "64" sticker and the mark: a small tilted box card with a three-feather wing. STUDIO and QHANTOM LABS sit beneath.
- **Icon bar** (top centre). A grey stepped plate with four square buttons: **Games**, **Styles**, **Filters** and **Help**.
  - The lit button is bright cyan, and a white tooltip with a pointer names it: "Games", "Filters: Status".
  - By default the lit button is where you are: Games, Styles, or Filters while a filter is on.
  - **Tab** or **↑** moves the cursor into the bar, which adds a dark ring. There, ←→ choose, Enter selects, and Esc or ↓ return to the shelf.
  - Games and Styles switch shelves. Filters steps to the next filter (All, Style, Modules, Status, Mine). Help opens a small controls card.
- **Counter** (top right). A white pill flush to the screen edge, with dark-red pixel text: "ALL 2/14". Inside a grouped filter it names the group: "UNTESTED 11/14", "FOREST VILLAGE 5/14".
- **Title bar.** A wide white bar with the selected game's name in a clean sans. A SAMPLE tag appears when the entry is invented. The bar doubles as the find field.
- **The row.** Four whole box cards, with half cards cut off at both screen edges.
  - The highlight moves from card to card. The row slides one card only when the highlight would leave the page.
  - Shelves with fewer than four cards are centred.
- **Pointer and strip.** A small blue pointer marks the current game above a thin strip of tiny covers. The strip is as long as the library, up to a window of 38 covers around the selection.
- **Hints.** Only the actions that matter now, as red glyphs with words. The home row reads ENTER Open · TAB Menu · Q Previous Filter · E Next Filter.
  - Keyboard first, with keycaps.
  - A generic gamepad set appears as soon as a pad is used: round A/B buttons, START/LB/RB/LT/RT pills and a D-pad cross. A key press switches back.

**Backdrop.** An original, bright illustrated room, slightly blurred like a photo's soft background so the cards carry the colour. It has:

- a pale sky with a faint pixel-dot grid;
- a huge soft periwinkle workbench and a warm sunny block;
- big clouds and a sun;
- a giant faint box card leaning in the corner.

There is no help text, no tooltip clutter, and no panel you didn't ask for. Detail appears when you open something (progressive disclosure).

## The box card

An original rectangular card: a white frame with pixel-stepped corners and a thin grey edge, plus a hard dark shadow stepped down and to the right.

- **Top margin**: a narrow white band. On invented entries it carries a red SAMPLE tag.
- **Cover**: the top ~60% (next section).
- **Lower strip**: four dots on the left and a grey badge on the right.
  - The dots, in order: story proof, bot play, style gate, human play.
    - Filled green: the check ran on this build and passed.
    - Hollow: not run, or the report is for an older build.
    - Red ring with a slash: it ran and failed.
  - The badge is the kind of game, from its modules: STORY, EXPLORE (region), COMBAT, COURSE or MIXED.
- **Selected**: the frame turns a thick bright blue, the inside takes a light-blue tint, the shadow deepens, and the card grows about 4.5% upward in three held frames.

## Covers: real box art

Each cover is composed in SVG on top of its art:

- a style-coloured wash;
- a vignette;
- the **title logotype**: heavy condensed italic caps in a system font, with a gradient fill from the style colour, a dark outline and a hard drop shadow.
  - It sits on one or two balanced lines, at the top, or at the bottom when the subject is high in the frame.
  - A line wider than the art is squeezed to fit.
- a **style band** along the bottom edge;
- a small **corner mark**: a tiny white card with a gold feather.

**Real games** use a real runtime frame: native 320x240, cast present, no HUD. Thaw uses the conversation pit, The Last Light the fog street.

- **Crop** (`cover.focus`, in source pixels). Frames the subject: Thaw's white-suited new arrival, The Last Light's lighthouse.
- **Grade** (`cover.grade`). An SVG filter: saturation, optional warmth, a gamma lift and an S-curve for punch. It needs no pixel reads, so it works over `file://` and on the plugin backend's data URLs.
- **Light.** A soft-light spotlight on the subject, plus a mood:
  - *day*: a soft-light sky wash in the style colour;
  - *dusk*: a sunset multiplied into the sky, so The Last Light's cream lighthouse glows against amber;
  - *night*: deepened edges, so Thaw's white suit pops.
- **Backend projects** without these hints get a centre crop and the default grade. An explicit `.maker/studio/cover.png` is used as given.

**Sample games** get original key art, painted procedurally at 160x120 in a hand-painted low-poly look.

- Layers, back to front: sky, ridges and sea; a landmark with a halo behind it; a hero figure drawn at twice its old size; particles.
- Graded for box art: lifted darks, more saturation, less haze between layers, and an S-curve.
- Finished with a 4x4 ordered dither to 16-bit colour.
- Deterministic per game.

The art is enlarged with crisp pixels, so the selected and detail cards are larger and sharper, not blurred.

**NEW GAME**: a clean ruled paper label with a red margin line, a bold gold plus and "NEW GAME" in white logotype. Its dots and NEW badge are dashed.

**Unreadable shelf**: a cracked dark cover with a big "?", a hazard band and a red ERROR badge.

## Honesty rules (in the data, not just the art)

- A verdict shows as current only when its report names the current build's `game_hash`. A stale verdict never lights a dot.
- "Human play" stays NOT YET unless a person has explicitly marked this exact build as played. Nothing in the Studio sets that.
- Thaw and The Last Light show their real recorded status on main at 80d5236:
  - story proof proved;
  - style gate passed for Thaw and failed for The Last Light;
  - no bot playtest report (UNTESTED);
  - no export.
- Every other entry in the sample is marked SAMPLE.

## NEW GAME

Opening the blank card moves it to the left and opens a short card:

- **A premise field.** What you type is written onto the card's paper label as you type, in a handwriting face.
- **Style chips.** Approved and example styles only; drafts are excluded. The chosen style recolours the label's band and plus.
- **GIVE TO HERMES.** Enter opens a **fresh chat with a short brief already in the composer**: the premise, the chosen style, and the next steps (scaffold, then compile and check before building assets).
  - The Studio never sends it; you read it and press Enter yourself.
  - With no premise, the brief asks Hermes to help you choose one, one question at a time.

## The style shelf

Reach it with the **Styles** icon. Each style profile or pack is a card: its window shows a scene painted from its palette, its swatches run along the strip, and a badge shows its status:

| Status | Badge | Meaning |
|---|---|---|
| in use | USED | selected by a game in this folder; looks are checked per game, not approved here |
| approved | OK | approved style |
| example | DATA | example profile; data only, no rendered approval |
| data valid, runtime pending | DATA | valid data; runtime support still pending |
| draft awaiting approval | DRAFT (dashed) | a reference-to-pack draft waiting for your approval |

Opening a style offers two actions:

- NEW GAME IN THIS STYLE (disabled for drafts: "approve the draft before building with it");
- REVIEW WITH HERMES / ASK HERMES ABOUT IT.

Nothing is approved from the Studio. Approval stays a conversation with Hermes.

## Game detail (Enter)

The card lifts to the left, about 10% larger, and a white stepped panel opens beside it.

- **Premise.**
- **Meta line**: rooms · endings · style · kind, with the style's swatch.
- **What is verified**: four rows in the same order as the card's dots, each led by its dot, so the two teach each other.
  - **PROOF**: PROVED, REJECTED, INCONCLUSIVE, NOT RUN or STALE.
  - **BOT PLAY**: the verdict, marked "· OLD" when it belongs to an older build.
  - **STYLE GATE**: measured look checks, not human art approval.
  - **HUMAN PLAY**: NOT YET or PLAYED.
- **Back-of-box shots**: three real captures, or three procedural variants.
- **Actions**: PLAY, EDIT WITH HERMES, EXPORT and OPEN FOLDER.
  - The cyan cursor opens on the first available action.
  - Unavailable actions are dimmed and carry a short dashed tag: NO BUILD, SAMPLE or REMOTE. The full sentence appears as a notice if you try one.
  - **PLAY** runs the web export inside the app's sandboxed frame. A game with only a macOS build shows PLAY MACOS BUILD, which asks first; the question defaults to NO.
  - **EDIT WITH HERMES** and **EXPORT** open a fresh chat with a brief in the composer, unsent. Export asks Hermes to show what will be written before running.
  - **OPEN FOLDER** reveals the project folder.

## Play: inserting the card

1. The chosen card is picked up from the detail spot and carried to the centre (160 ms).
2. It tips back and sinks into a dark slot that glows cyan as it arrives (240 ms).
3. The screen fades to black in four steps, and a CRT line opens into the picture.
4. The game runs in a 4:3 screen with ESC · EJECT in the corner.

With reduced motion it cuts straight to the running screen.

In the desktop plugin, the web export is served for the SDK's `SandboxedFrame` by a tiny local server that starts only on that click:

- bound to 127.0.0.1 on a random port;
- serving only that one export folder, behind a random path token;
- stopping on eject, on the next play, or after 30 idle minutes.

Sample entries show their cover and "SAMPLE BUILD · NOTHING TO RUN".

## Motion

Eased curves sampled at low, fixed frame rates and held between steps, the way late-90s menus moved.

| Motion | Curve | Timing |
|---|---|---|
| Highlight moves within the page | the new card grows into its enlarged size | 3 held frames, 110 ms |
| Page slide at the edge of the page | ease-out cubic, retargetable mid-slide | 190 ms, sampled at 30 fps |
| Bump at either end | small shake | 240 ms, alternating amplitude |
| Filter or shelf change | new shelf rises from below, selection first, neighbours 24 ms apart | 170 ms, 5 held frames, starting at 30% opacity so no frame is empty |
| Title change | the name steps up into place | 200 ms, 3 steps |
| Insert | lift, tip, sink | 8 held steps per phase, then a 4-step fade to black and the CRT line |

Filmstrips are in `docs/studio/final/motion-*.jpg`.

- Held keys retarget the slide from wherever the row is.
- `prefers-reduced-motion` (or `#motion=reduce`) replaces every motion with an instant change.

## Sound (optional)

Off by default; **M** toggles it. Cues are addressed by Hermes64 audio-catalog id and checked against `audio/catalog.json` by the tests:

| Moment | Cue id |
|---|---|
| move | `ui.move` |
| open / select / enter the menu | `ui.select` |
| back | `ui.back` |
| filter | `core.ui.move.02` |
| shelf switch | `core.hatch.slide.open` |
| insert | `hatch.open` |
| boot | `core.machine.computer.accept` |
| NEW GAME | `core.magic.chime` |
| hand-off to Hermes | `core.ui.confirm.01` |
| bump / no match | `core.ui.error.01` |

## Input

| Action | Keyboard | Standard gamepad |
|---|---|---|
| Browse | ← → (or wheel, or click a card or a strip cover) | D-pad / left stick |
| Open / select | Enter or Space | A |
| Back / cancel / eject | Esc or Backspace | B |
| Menu (icon bar) | Tab or ↑ | START, D-pad up |
| Previous / next filter | Q / E (or [ / ]) | LB / RB |
| Page | PageUp / PageDown | LT / RT |
| First / last | Home / End | |
| Find by name | / then type | |
| Help | ? (or the Help icon) | |
| Sound | M | |

- Keys are read only while the Studio has focus, so it never takes keys from the chat composer.
- Modifier chords (⌘, Ctrl, Alt) are ignored.
- **A second Tab, or Shift+Tab, is left to the browser, so keyboard focus can always leave the Studio.**
- The gamepad uses the W3C standard mapping. Held directions repeat and speed up.

## Accessibility

- Keyboard-first. Every action is reachable without a pointer, and the hints always show the current keys.
- The selected card is the focus indicator: a thick blue frame (3.7:1 against the sky), a tint and a lift. The menu cursor adds a dark ring to the lit icon.
- The root is `role="application"` named "Hermes64 Studio". A polite live region announces each selection: title, position, bot verdict, proof status, whether a person has played it, and SAMPLE.
- Reduced motion is honoured everywhere.
- Measured contrast (WCAG 2):

| Element | Ratio |
|---|---|
| title | 17.9:1 |
| tooltip | 18.0:1 |
| counter | 7.8:1 |
| hint labels, on the sky | 8.5:1 |
| hint labels, on the bluest part of the bench | 4.9:1, with a solid white halo |
| key glyphs | 4.7:1 |
| menu cursor | 10.9:1 |
| dimmed actions | 4.7:1 |

  The full table is in `CRITIQUE-STEER1.md`.
- No information is carried by colour alone. The dots sit in a fixed order matching the named rows, failures add a slash, and verdicts and SAMPLE are words.

## Empty and error states

- **No games yet**: the NEW GAME card with four dashed ghost cards waiting to be filled, and a strip of empty dashed slots. Hints: ENTER Open, TAB Menu.
- **Shelf unreadable** (bad folder, backend off, unreadable catalogue).
  - The title reads "Can't read the shelf", with one centred cracked "?" card and one plain sentence saying what to check.
  - The only hint is ENTER Try Again.
  - The counter and strip are hidden, because the count is unknown.
- **Projects root not set**: the backend answers with a plain configuration message ("Choose a projects folder for Hermes64 in Settings…"), shown as the unreadable shelf.
- **A broken project**: it still gets a card, with its problems listed as issues. Folders that are not projects, or are symlinks, are skipped and listed in the catalogue's `skipped` rows.
- **Play or launch failure**: a short notice. The Studio never falls into a blank screen.

## From 0 games to 300

- **0**: the empty shelf above.
- **1 to 3**: the cards are centred.
- **4 and more**: pages of four with half cards at the edges. The strip shows up to 38 covers around the selection.
- **Over 40**: the hints add / Find (LT/RT Page on a pad), and PageUp/PageDown and Home/End jump far. Find works like this:
  - Press / and type. The shelf jumps to the first title that starts with the text, then to the first that contains it.
  - The title bar turns blue with a FIND tag.
  - A miss shows NO MATCH with the bump cue.
  - Enter keeps the result; Esc restores the previous selection.
- **Built to scale**:
  - Covers are painted lazily when a card first comes near the screen, at most two per frame.
  - Only about a dozen cards exist in the DOM at any size.
  - Measured in headless Chrome at 300 games with these cards: 120 ms to boot, 14 card slots, about 1,000 DOM nodes, a 7 MB heap, and a worst frame of 5.7 ms of JavaScript.
  - The catalogue format caps at 2,000 games.
  - The scanner considers at most 512 project folders, then sets `truncated`.

## Data: the catalogue

`studio/catalogue_schema.json` (schema id `hermes64.studio.catalogue/1`) describes one local catalogue. Fields per game:

- id, title, premise, sample flag, owner;
- project kind and path;
- style: id, label, colour, palette, source;
- modules, rooms, endings;
- verification: proof, replay, playtest verdict and freshness, style gate, human;
- exports: target, path, entry, bytes, verified;
- cover: a capture, file or procedural recipe, with optional fields:
  - `width`, `height`;
  - a `focus` crop `[x, y, w, h]`;
  - `title` (top or bottom);
  - `grade` (gamma, gain, lift, saturation, warmth, contrast, mood);
- up to three shots and up to sixteen issues.

The UI clamps every grade value and drops a bad crop. The schema uses only the keyword subset the repository's own bounded validator evaluates. The tests validate both the sample and real scanner output against it.

`adventure_maker/studio_catalogue.py` builds the catalogue from the plugin's `projects_root`, using only the standard library:

- **Managed projects** (`.maker/project.json`, as written by `hermes64_scaffold`). It reads:
  - the compiled game named by `.maker/current.json`;
  - `proof.json` from check, replay and edit runs, and `replay.json`;
  - bot-playtest `report.json` (`.maker/runs/playtest-<id>/`);
  - asset reports with `style_validation`;
  - export folders.
- **Style-core projects** (`project.json` with `content.story`): the story spec, the style profile palette, and `style.lock` approval.
- **Covers**: an explicit `.maker/studio/cover.png`, else frames from the current bot playtest, else a procedural recipe.
- **Confinement**:
  - `projects_root` must be absolute, must exist, and must not be a symlink.
  - Below it, every path is opened component by component with `O_NOFOLLOW` against an open directory descriptor.
  - FIFOs and devices are refused.
  - JSON is capped at 2 MB per file, and PNGs at 4 MB and 4096 px.
  - Duplicate JSON keys and NaN are rejected.
- **Deterministic**: sorted, no timestamps, no absolute paths, and a SHA-256 digest of the canonical JSON.
- **Never writes.** The CLI's `--out` uses exclusive create.

## Privacy, and a community catalogue later (out of scope here)

Everything stays on the machine. The catalogue holds project-relative paths only. The absolute folder path is revealed only for an explicit OPEN FOLDER click.

If a shared catalogue is ever built, it should be a separate opt-in, per game, with:

- an explicit export step that shows exactly what leaves the machine;
- verdicts published with their build hash and scope;
- human-test claims only from the person who played it;
- revocation;
- no automatic upload, and no telemetry from browsing.

## Taken from the reference, as principles only

From Dylan's private reference screenshot (which is not in this repository), we took composition and interaction principles, never art:

1. Four horizontal bands at the same heights, measured to within about 1% (see `CRITIQUE-STEER1.md`):
   - logo, icon bar and counter;
   - a wide title bar naming the selection;
   - the row of boxed items;
   - a whole-library strip with control hints under it.
2. A page of four whole boxes, with half boxes cut off at the screen edges. The highlight moves within the page. The selected box is enlarged, raised and framed in blue, with a tinted lower strip.
3. The box anatomy: a white frame, a chunky dark stepped shadow on the right and bottom, art in the top ~60%, and a strip with four circles on the left and a grey badge on the right. We use the circles as verification dots and the badge for the module.
4. An icon bar with a bright highlight and a pointed tooltip naming it.
5. A white pill counter flush to the right edge, in dark-red pixel text.
6. A small pointer above a strip of tiny covers.
7. Red glyph pills with plain words for the control hints.
8. A bright, soft, light backdrop.

Not taken:

- any logo or wordmark;
- console, controller or retail box imagery;
- game titles, characters or typefaces;
- trade dress. Our style band runs along the bottom of the art, not as a coloured side strip.

The wordmark, mark, icons, card, covers, procedural art, backdrop and H64 Pixel font are all original. Typography is the system stack (Avenir Next / Avenir Next Condensed, Helvetica Neue, Futura, Segoe UI, Arial) plus our hand-authored 5x7 pixel font. Style labels never show the third-party "N64" mark as a name: bundled ids such as `n64_base` display as "Classic Base".

## Files

| Path | What |
|---|---|
| `studio/prototype/` | the no-build prototype (`index.html`, `studio.css`, `catalogue.sample.json`, `covers/`, `js/`, `dist/studio.bundle.js` for `file://`) |
| `studio/prototype/js/` | shared modules: `model`, `state` (pure reducer), `cartridge` (the box card), `covers`, `pixelfont`, `icons`, `motion`, `input`, `sound`, `app` (DOM shell with a host adapter), `rack` |
| `studio/plugin/glue.js` | the desktop-only part: registration, React page/rack wrappers, SDK host adapter |
| `desktop/plugin.js` | generated desktop half (only `@hermes/plugin-sdk`, `react`, `react/jsx-runtime` imports) |
| `dashboard/plugin_api.py`, `dashboard/manifest.json` | backend routes under `/api/plugins/hermes64/` (web-dashboard tab hidden) |
| `adventure_maker/studio_catalogue.py`, `studio/catalogue_schema.json` | scanner and schema |
| `studio/tools/` | `sync_shared.py` (generates the two bundles), `make_covers.py` (real cover frames) |
| `studio/harness/` | headless-Chrome tools (`shoot`, `sheet`, `filmstrip`, `bands`) and the mock desktop host |
| `tests/test_studio_catalogue.py`, `studio/harness/test_shared.mjs` | schema, scanner, plugin API, generated-file contract, hygiene; reducer, icon bar, input, card dots and badge |
| `docs/studio/` | critique rounds with sheets, final screenshots |

## Verified, and not

Verified on this machine, in headless Chrome:

- the prototype in 23 states at 480x720, 960x600, 1280x720 and 1920x1080, over http and `file://`, with zero console errors;
- frame-exact motion filmstrips;
- the band measurements;
- 30 Python tests;
- 14 Node tests of the shared modules;
- the repository's existing suites;
- 25 mock-host checks of `desktop/plugin.js` against the real backend functions, over fixture projects. They cover registration, render, covers, reveal, sandboxed play, token and traversal refusal, eject, the chat hand-off left unsent, unmount, and the rack.

Not verified:

- the real Hermes Desktop app (not installed; the React and SDK used are stand-ins);
- a physical gamepad;
- a real Godot web export inside the app's `SandboxedFrame` (a hand-written page stood in);
- native macOS launch of a real export;
- dedicated hero renders for the covers (the covers are crops of existing captures);
- other screens, DPIs and slower machines;
- the sound cues by ear;
- how it feels to a person.
