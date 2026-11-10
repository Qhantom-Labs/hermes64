# Hub roadmap: from a folder to a community marketplace

Hub v0 is a trustworthy file format with local tooling. A real marketplace for every Hermes user needs the following
pieces, roughly in this order. Each step should keep the v0 guarantees: data only, hashes everywhere, honest tiers, and
no network unless the owner asks.

## 1. Public registry (smallest useful step)

- A public Git repository holding `index.json`, `archives/` and `previews/`, plus CI that runs `tools.hub check`,
  `add-draft` validation and a privacy scan on every pull request.
- Static hosting for the files and the browse page, so `hub_url` works. Signed release tags of the index.
- Maintainer guide: review checklist, tier review, licence checks, takedown handling.

## 2. Signing and provenance

- Sign `index.json`, for example with minisign or Sigstore, and pin the public key in the plugin. The plugin's schema and
  licence allow-list already cannot be widened by a registry; signatures add "this is the registry I trust".
- Optional author signatures per entry. A provenance block records the tool versions, the proof report hash and the
  playtest receipt hash.
- Reproducible packs: re-run `hub pack` in CI and compare bytes.

## 3. Better discovery

- Generated previews for every entry: turntables for kits and characters, short audio previews for sounds, and the
  title cover and a few frames for games. Render them in CI, never from user machines.
- Search over the static index: tags, styles, budgets, "works with my game's style lock".
- Collections ("polar starter set"), and featured picks made by humans.

## 4. Updates and dependencies

- `hub update <id>` with a diff of changed files and a re-check. Pinning, rollback, and an `uninstall` that removes
  files and the catalog row.
- Declared dependencies between entries, for example a game that needs a character pack, resolved without running
  any code.
- Compatibility ranges against plugin and contract versions, with clear messages when a contract moves.

## 5. Community features (need a server, accounts and moderation staff)

- Accounts, author pages, ratings, comments and download counts. These need abuse handling, privacy policy, data
  retention rules and a moderation team before launch.
- Reporting flows wired to the takedown policy in `docs/HUB.md`, with response-time targets.
- Optional payments or tips for creators: legal entity, tax handling, refund policy, payment provider, regional rules.
  This should be a separate decision; the format does not depend on it.

## 6. Safety hardening

- Fuzz the archive validator (ZIP, PNG, WAV, Ogg and GLB parsers) in CI.
- Decode Ogg fully. v0 checks only the container header.
- Image and audio content moderation assistance, with humans deciding.
- A second-opinion scanner for likeness and trademark concerns. The cameo pack is the model case: consent recorded,
  a notice attached, and removable.

## Open questions for the owner

- Who maintains the public registry, and under which organisation and licence?
- Should bundled seed entries stay in the plugin, or live only in the public registry?
- Is a tier ever upgraded by a human ("owner-approved") through the registry, and who may do that?
