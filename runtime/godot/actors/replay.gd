extends "res://tests/playthrough.gd"
## Original checker/save proof plus real actors attached to the actual presenter per witness.
func _initialize() -> void:
	call_deferred("run_proofs")
func run_proofs() -> void:
	super._initialize()
func replay_claim(claim: Dictionary, path: String) -> bool:
	var ok: bool = super.replay_claim(claim,path)
	var presenter = load("res://view/presenter.gd").new()
	presenter.resolver = load("res://actors/assets.gd").new()
	root.add_child(presenter)
	var loaded: Dictionary = presenter.boot(game,{"pack":"res://theme.json","bindings":"res://bindings.json"})
	ok = ok and loaded.ok
	if loaded.ok:
		var bridge = load("res://actors/bridge.gd").new()
		presenter.add_child(bridge)
		bridge.attach(presenter)
		for action in claim.witness:
			var result: Dictionary = presenter.dispatch(action.action)
			if not result.ok: ok = false
		if claim.has("final_state") and presenter.runtime.state != claim.final_state: ok = false
		if not presenter.resolver.placeholders.is_empty() or not presenter.resolver.missing.is_empty(): ok = false
		var visual = presenter.player.get_node_or_null("visual")
		if visual == null or not visual.get_meta("real_character",false): ok = false
	presenter.free()
	return ok
