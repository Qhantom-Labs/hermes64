extends "res://playtest/module_runner.gd"
## Debug/evidence trace of the module bot in 1.1.0 fights: one JSON row per simulated tick with the player, the
## enemies' FSM states, live hazards and the bot's buttons (combat-trace.jsonl in the run output). Read-only.
var trace: FileAccess
func step(v := Vector2.ZERO, discrete := []) -> void:
	await super.step(v, discrete)
	var host = view.module_host
	if host == null or host.combat == null: return
	if trace == null: trace = FileAccess.open(config.output.path_join("combat-trace.jsonl"), FileAccess.WRITE)
	var c = host.combat
	var p: Vector3 = view.player.position
	var rows := []
	for e in c.enemies:
		var t: Dictionary = preload("res://modules/combat/telegraph.gd").info(e)
		rows.append({"id": e.identity, "hp": e.hp, "state": e.state, "age": e.age, "kind": e.get("kind"), "d": snappedf(e.body.position.distance_to(p), 0.01),
			"pos": [snappedf(e.body.position.x, 0.01), snappedf(e.body.position.z, 0.01)], "contact_in": t.get("contact_in", -1), "open": t.get("open", false)})
	trace.store_line(JSON.stringify({"tick": tick, "hp": c.health, "wave": c.wave, "age": c.age, "roll": c.roll_age, "hurt": c.hurt_age, "stop": c.hitstop,
		"p": [snappedf(p.x, 0.01), snappedf(p.z, 0.01)], "buttons": buttons, "move": [v.x, v.y], "enemies": rows,
		"waves": c.shockwaves.map(func(w): return [snappedf(w.radius, 0.01), w.contact_in(p), w.glyph_open(p)]),
		"shots": c.projectiles.map(func(s): return [s.contact_in(p), s.reflected]), "fb": c.feedback.map(func(f): return f.kind)}))
func finish() -> void:
	if trace != null: trace.close()
	await super.finish()
