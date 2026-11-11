# Owner waiver for a character file

The rig kit validator (`adventure_maker.rigkit.validate_character`) refuses some converted characters that their owner
has looked at and wants to use anyway, for example a Meshy body whose bends stretch past the edge limits. A waiver
records that decision in the character file. It is narrow:

- it belongs to one file;
- it covers named checks and clips only;
- it is bounded by the failing numbers at the time it was granted.

It never changes what the validator does for any other file, check or clip.

## Who can grant one, and how

Only the owner can approve a waiver. The agent does what the owner said, through the existing `hermes64_character`
bind action. There is no new tool, and the schema budget is unchanged (27 tools, 5,996 of 6,000 tokens).

```
hermes64_character action=bind project=<p> glb=<file> id=<cast id> display_name="..." source=community \
    waive=true owner_approved=<the owner's name, as they gave it> brief="<the owner's own words>"
```

- `owner_approved` without `waive=true`, `waive=true` without `owner_approved`, a generic name (`owner`, `the user`,
  `assistant`, `agent` ...) and a missing `brief` are each refused in one line. Nothing is written.
- Bind validates the file (every clip it carries, plus idle) with no waiver.
- When the current game makes this cast id the player of a combat game, bind also validates each fight clip the file
  lacks (idle_combat, swing, hurt, death, roll, block). It attaches each one from the rig clip packs exactly as staging
  will (`cast_binding._complete`, same pack order). A pack clip that passes as it is is used, and is not waived.
- Bind refuses when nothing fails ("nothing to waive"), when anything fails that may not be waived (see the rules),
  and when the body is over 800 triangles.
- Otherwise it writes `characters/waived/<id>.glb`: the bound file, unchanged, plus the waiver block. The source file
  stays as it was. Bind then validates the new file with the waiver granted, and records the waiver in the cast row
  (`characters/cast.json`, with the block's sha256) and in the catalog row (tag `owner-waiver`; the provenance says so).
- The result names every waived failure as `WAIVED (<owner>, <date>): ...` with its numbers, under `waived`. Every
  bind result and `list what=cast` also list all waived characters of the project (`waived_characters`).

## The block

The block is stored in the GLB as root extras `hermes64_waiver`, format `hermes64-waiver/1`:

| field | what |
|---|---|
| `approved_by` | `owner` |
| `owner` | the name the owner gave (`owner_approved`) |
| `approved_on` | the day bind wrote the block (YYYY-MM-DD) |
| `reason` | the owner's words (`brief`) |
| `scope` | `{checks: [...], clips: [...] or 'all'}`: the failing checks and the clips they fail in |
| `measured` | the failing numbers per clip at that time: edge ratio range, keys with an edge out, floor deviation, floor keys; plus the body triangle count |
| `file_hash` | sha256 of the skinned mesh, skin weights and skeleton it was granted for (positions, triangles, joints, weights, inverse binds, joint names and rest offsets; not the texture, not the clips) |

## What the validator does with it

`validate_character(glb, ..., waiver=False)` is the default. A block is then only reported (`report['waiver']`,
`honored: false`) and every failure stays an error. So the hub, the CLI, generated characters and any other caller
behave exactly as before. A file without a block gives the same report whether `waiver` is True or False; this is
tested.

With `waiver=True`, the caller grants the block. The validator then applies these rules, which are fixed in
`rigkit/waiver.py`; nothing in a block can change them:

| rule | result |
|---|---|
| Waivable checks: `mesh.deformation`, `mesh.silhouette.floor`, and `budget.body` for a body of at most 800 triangles | A covered failure moves from `errors` to `waived`, with the clip's numbers now and as recorded |
| Any other check in `scope` (non-finite data, skeleton contract incl. left/right hierarchy, skin, clip form, root motion beyond the declared seat/flight rules, connectivity, props, container, hash) | The whole block is refused (`waiver.refused`) and nothing is waived |
| A malformed block (owner missing or generic, no reason, bad date, bad hash, empty scope) | `waiver.invalid`, nothing waived |
| The mesh/weights hash differs from `file_hash` | `waiver.hash_mismatch`, nothing waived |
| A failing clip that is not in `scope.clips` | Stays an error ("not in the waiver scope") |
| A failing check that is not in `scope.checks` | Stays an error |
| A clip whose numbers exceed the record by more than 5 % (edge ratio high or low, keys out, floor deviation or floor keys) | Stays an error ("grew beyond the waiver") |

A waived failure is never dropped. It is listed under `report['waived']`, the check gets `waived: <n>`, and
`report['waiver']['result']` says `WAIVED`.

## Where it is granted

- Bind grants the block it has just written. Re-binding that file (same id, same path) grants the block that the cast
  row recorded.
- Staging (`cast_binding.stage`) grants a file's block only when its cast row recorded exactly that block. That
  covers the derived player and enemy bodies, so the player's fight clips attached from the rig pack are judged by the
  same waiver. A row whose file carries another block (or none) gets a plain warning, and the role falls back as for
  any refused clip: POSE TEST, or the stock robot art.
- A file carrying a block from another project is not granted. Bind refuses it with the usual reason, plus "the
  file carries an owner waiver that this project did not grant".
- `cast-binding.json` lists the waived characters (`waived`), with one warning line each.

## Doctor, hub and export

- `hermes64_doctor` lists every waived character (`waived_characters`: project, id, owner, date, checks, clips,
  reason) and adds one guidance line. With a project it lists that project's; without one, every project under
  `projects_root`. Read-only.
- `hermes64_hub` pack refuses a game whose cast has waived characters, and any archive with a model that carries a
  waiver block. The refusal (`hub_waived`) names each character. `waived=true` acknowledges it: the entry is tagged
  `owner-waiver`, and publish refuses that entry again unless `waived=true` is passed again. The slash command takes
  `waived=true`.
- `hermes64_export` is unchanged. By reading `adventure_maker/export.py`, a release export already refuses any bound
  project character whose hash is not in the public frozen manifest (`release_private`), waived or not. No export with
  a waived character was run here.

## Tests

`tests/test_waiver.py` holds the known-bad controls: hash changed, numbers grew, 5 % tolerance both ways, unlisted
check, unlisted clip, floor waiver and floor growth, safety checks in scope, budget over the cap (validator and bind),
invalid blocks, no owner string, generic owner, nothing to waive, an unwaivable failure (connectivity), a block from
another project, hub pack and publish refused unless acknowledged. A staging test shows that the player's fight clips
measured at bind are granted, and that a cast row whose record does not match the file is not.
