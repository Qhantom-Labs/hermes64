# Assembly critique — actual images, not style acceptance

Inspected final captures: `evidence/screens/capture-20261108T004636869459Z/contact-sheet.png`, all ten room tiles, plus the full-window workstation capture from `evidence/screens/e2e-20261108T003730019528Z/thaw/workstation.png`. Earlier comparisons: `evidence/screens/e2e-20261108T003141197799Z/contact-sheet.png` and `evidence/review-20261108T002234716602Z/sheet.png`. These are real windowed Godot Mobile/Metal captures, not mockups. Exact command/report paths are in RESULT.md.

## What is working

- The two packs are visibly distinct through the same runtime. Last Light has timber/brown/green materials and warm fog; Thaw has cobalt/periwinkle/pearl, softened small textures and rounded windows/furniture.
- The 320×240 grid, nearest upscale and bitmap dialogue are coherent. The dialogue is readable at native pixel size; long source text has pages rather than disappearing after three lines.
- The conversation pit is now an actual low-poly circular lounge with cushions and a table/orb. The workstation has the shaped multi-screen desk. Snow Field now has uneven snow, a small dome and tree instead of an indoor wall box.
- Kit chrome/glass materials are recognized by the runtime and receive environment textures; no PBR reflection or dynamic ray tracing is implied. Texture/fog/vertex colour rendering is visibly active, not flat grey primitives.
- All four Last Light rooms and all six Thaw rooms contain real library geometry and explicit actor markers. The loader reports no missing assets in these runs. Warm timber versus cool molded surfaces demonstrates pack contrast, not universal-theme acceptance.

## What is visibly wrong or unfinished

- **The characters are blocky markers**, not the serious painted-face people or rounded faceless expedition figures in the style bible. Cats are tiny box cats, not expressive animated animals. Coat patterns, mittens, hood shapes, posture and held-frame animation are not represented adequately.
- Thaw still reads as sparse cutaway dioramas. Several interiors share the same rectangular shell. The curved corridor is not convincingly curved; the dome interior is not a domed volume. Door frames can sit against continuous walls or stand alone outside because geometric portals are not cut for each semantic door.
- The pit bowl is placed on a flat floor rather than actually recessed into a floor opening. Windows do not convincingly reveal a rich snow village; the tree outside the pit is exposed above the cutaway instead of framed in a convincing panoramic scene.
- Fog remains strong, especially Pod Bay and Snow Field. It unifies the palette but reduces small prop/character contrast. Chrome highlights are subtler and flatter than the reference's white-hot mirrored furniture; this is a cheap env-map treatment, not the final look.
- Some props are only explicit approximations: a bell/device, gear/tool and headphones/tool do not read like bespoke hero objects. Text describes objects with greater specificity than their visuals deliver. The new isolated glass pickup is better than the earlier table substitution, but remains small.
- Last Light is a warm forest-kit interpretation, not the intended moody coastal lighthouse. Fog Street has a simple platform/water field and small house/tree; the lamp room is sparse and lacks a compelling lighthouse mechanism.
- The all-room harness uses initial story state and teleports only for visual coverage. It does not establish spatial navigation, collision perfection, narrative camera timing or a human's understanding. The action menu exposes legal story actions without proximity gating.
- Room/location/counter text is useful during dialogue but needs a human UI pass. Long action labels, inventory icon coverage, camera/subject scale and keyboard feel still need attention. The suite does not replace human playtesting or listening.

## Assessment

**Integration demonstrator, not final visual-quality approval.** Real assets, renderer, UI and story logic now meet at one running interface, with measured render budgets and explicit gaps. Main should keep real-character landing, geometry-aware doorway/shell staging, richer windows/backgrounds and human art/feel review separate from this technical acceptance. No new optional combat/lab-building module was started.
