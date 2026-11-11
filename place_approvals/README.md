# Place approvals (style lock)

Approved rooms per archetype and style: `place_approvals/<archetype>/<pack>__<mood>/<id>/approval.json` + `frames/`.
Written only by `python3 -B -m tools.place_maker approve --run <run dir> --room <room id> --by <name>`.
The store records who the caller says approved a room; it does not verify it. Records marked `"synthetic": true`
are test/demo records and are never offered as approved examples.

This store is empty at the start: nothing here has been approved by a human yet.
