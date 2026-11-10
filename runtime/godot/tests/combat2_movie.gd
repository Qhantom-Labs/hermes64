extends "res://playtest/module_runner.gd"
## Complete production-input acceptance, with one deliberate death (no state injection).
var rules_trace := []
var moves_seen := []
var landed_moves := []
var death_attempted := false
var retry_facts := {}
func step(v := Vector2.ZERO, discrete := []) -> void:
	await super.step(v, discrete)
	var h = view.module_host
	if h == null: return
	var row: Dictionary = h.run.snapshot()
	row["tick"] = tick; row["retry"] = h.retry_ticks; row["challenge"] = h.active_id
	if h.combat != null:
		row["health"] = h.combat.health
		row["defeated"] = h.combat.defeated.duplicate()
		for f in h.combat.feedback:
			if f.kind == "move" and not moves_seen.has(f.move): moves_seen.append(f.move)
			if f.kind == "hit" and not landed_moves.has(h.combat.move_kind): landed_moves.append(h.combat.move_kind)
	rules_trace.append(row)
func challenge_bot() -> bool:
	var h = view.module_host
	var id: String = h.active_id
	if not death_attempted:
		death_attempted = true
		for t in 4000:
			if h.combat == null: break
			var enemy = h.combat.enemies[0]
			buttons = []
			await step(steer(flat(enemy.body.position)))
		if h.run.deaths != 1:
			failures.append("deliberate physical death did not occur"); return false
		var before: Dictionary = h.run.snapshot(); var remaining: int = h.retry_ticks
		while h.retry_ticks > 0: buttons = []; await step()
		var after: Dictionary = h.run.snapshot()
		retry_facts = {"countdown":remaining,"clock_delta":after.ticks-before.ticks,"checkpoint":view.runtime.state.modules.checkpoint,"position":[view.player.position.x,view.player.position.y,view.player.position.z]}
		var action := "challenge:start:" + id
		if not await walk(action, target(action)) or not await activate(action): failures.append("checkpoint challenge could not restart through input"); return false
		retry_facts["health"] = h.combat.health
		retry_facts["homes"] = h.combat.enemies.map(func(e): return [e.home.x,e.home.y,e.home.z])
	# Deliberate charged-strike input on the restored first trial. Approach and
	# hold/release go through exactly the same Actions frames as normal play.
	if id == "clear_1" and not moves_seen.has("charge"):
		for t in 600:
			if h.combat == null: break
			var enemy = h.combat.enemies[0]
			if enemy.body.position.distance_to(view.player.position) <= 1.35: break
			buttons = ["focus"]; await step(steer(flat(enemy.body.position)))
		for t in 28:
			buttons = ["focus","primary"]; await step()
		for t in 35:
			buttons = ["focus"]; await step()
		if h.active_id == "": return true
	return await super.challenge_bot()
func finish() -> void:
	if view.module_host == null:
		print("COMBAT2_BOOT_FAILURE ",JSON.stringify(failures)); quit(1); return
	var report := {"run":view.module_host.run.snapshot(),"moves":moves_seen,"landed_moves":landed_moves,"retry":retry_facts,"trace":rules_trace}
	var f = FileAccess.open(config.output.path_join("rules.json"),FileAccess.WRITE)
	f.store_string(JSON.stringify(report,"  ")); f.close()
	await super.finish()
