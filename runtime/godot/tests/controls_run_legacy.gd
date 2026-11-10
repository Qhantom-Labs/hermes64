extends SceneTree
## Frozen digests captured from the actual pre-FEEL2 reducer; preservation control.
const ActionsType = preload("res://input/actions.gd")
const Wire = preload("res://core/wire.gd")
var checks := 0
var failures := []
func check(ok: bool, label: String) -> void:
	checks += 1
	if not ok: failures.append(label); printerr("FAIL ",label)
func _initialize() -> void:
	var fixture: Dictionary = Wire.read_json("res://tests/fixtures/feel2_legacy_input.json")
	check(fixture.source_commit == "7edc26fd" and fixture.cases.size() == 3,"pinned pre-FEEL2 fixture")
	var snapshots := 0
	for case in fixture.cases:
		var a := ActionsType.new()
		var configured: Dictionary = a.configure(case.profile)
		check(configured.ok,"full legacy movie profile accepted: %s %s" % [case.mode,configured.get("reason","")])
		for step in case.steps:
			if step.has("context"): a.set_context(step.context)
			a.advance(step.frame)
			var digest := JSON.stringify(a.snapshot(),"",true,true).sha256_text()
			check(digest == step.hash,"legacy %s tick %d retains exact input snapshot" % [case.mode,a.tick])
			snapshots += 1
		a.free()
	check(snapshots == 213,"all captured legacy snapshots exercised")
	print("CONTROLS RUN LEGACY ",JSON.stringify({"checks":checks,"snapshots":snapshots,"failures":failures}))
	quit(0 if failures.is_empty() else 1)
