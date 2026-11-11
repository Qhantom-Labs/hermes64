# README honest-scope line (draft; README.md is not edited by this lane)

Proposed line for the README's honest-scope text:

> **Owner waivers.** A character the rig kit validator refuses can still be bound if its owner approves. The approval
> goes through `hermes64_character bind waive=true owner_approved=<name> brief=<their words>`. It covers only stretch,
> floor and body-budget failures (at most 800 triangles), and only the checks, clips and failing numbers measured at
> that moment, for that mesh. Every waived failure is still reported as WAIVED. A different mesh or bigger numbers
> fail again. The hub refuses to pack or publish a waived character unless told otherwise. A waiver is a person's
> decision about how something looks, not a pass: the plugin does not judge it, and it does not travel to other
> projects.

Where it would go: the honest-scope paragraph on what the validator guarantees, next to the line on
`mesh.deformation`. Details: docs/WAIVER.md.
