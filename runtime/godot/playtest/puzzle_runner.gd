extends "res://playtest/module_runner.gd"
## Puzzle bot: executes the proved solution (res://puzzle-plan.json = story/puzzle/analysis.py witness routes)
## through production Actions frames only (submit_frame: WASD, E, Z, R). Every grid step must reproduce the
## planned exact state key, every macro step its planned puzzle facts and inventory, and the run must reach the
## ending; anything else is a failure, so PLAYABLE only follows a complete physical run. No facts, positions or
## outcomes are injected; doors are left by walking into them.
const Rules = preload("res://modules/puzzle/rules.gd")
const WALL_DIR := {"north": "n", "south": "s", "east": "e", "west": "w"}
var plan: Dictionary
var retries := 0
var turns := 0
var mismatches := []
var row_log := []
var shots := []
var saved := {}
var probed := {}
var probe_log := []
var save_receipt := {}

func ctl():
	return view.module_host.puzzle

func fail(reason: String) -> bool:
	failures.append(reason)
	return false

## The executor decides on the next physics tick (idle, or the last tick of a step animation).
func deciding() -> bool:
	var c = ctl()
	if c == null or c.pending_setup or not c.active: return true
	return c.step_age < 0 or c.step_age == c.rules.step_ticks - 1

func idle_until_decision(limit := 240) -> bool:
	for i in limit:
		if deciding(): return true
		await step()
	return deciding()

func settle_frames(n: int) -> void:
	for i in n: await step()

## Direction from the player's cell toward an element: adjacent cell, or along the row/column (orbs).
func face_toward(eid: String) -> String:
	var c = ctl()
	var at: Vector2i = Rules.cell(c.rules.el[eid].cell)
	var d: Vector2i = at - c.st.p
	if d.x == 0 and d.y < 0: return "n"
	if d.x == 0 and d.y > 0: return "s"
	if d.y == 0 and d.x > 0: return "e"
	if d.y == 0 and d.x < 0: return "w"
	return ""

func face(d: String) -> bool:
	var c = ctl()
	if d == "" or c.facing == d: return true
	for attempt in 3:
		if not await idle_until_decision(): return false
		await step(c.input_for(d), ["focus"])
		turns += 1
		if c.facing == d:
			await step() # release Z and the stick before the next chord
			return true
		retries += 1
	return false

## A token the rules reject: the same production chord must start no executor step and leave the key as is.
func reject_token(token: String) -> bool:
	var c = ctl()
	var parts := token.split(".")
	if parts[0] == "pull" and not await face(Rules.OPPOSITE[parts[1]]): return fail("could not face the block for " + token)
	if parts[0] == "act": await face(face_toward(parts[1]))
	if not await idle_until_decision(): return fail("executor never became ready for rejected " + token)
	var before: int = c.steps.size()
	var key := str(c.rules.key(c.st))
	var v := Vector2.ZERO
	var b := []
	match parts[0]:
		"move": v = c.input_for(parts[1])
		"pull":
			v = c.input_for(parts[1])
			b = ["primary"]
		"act": b = ["primary"]
	await step(v, b)
	await step(v, b)
	await step()
	if c.steps.size() != before or str(c.rules.key(c.st)) != key:
		return fail("rejected token " + token + " changed the grid in " + c.rules.room)
	return true

func run_probes(room: String) -> bool:
	probed[room] = true
	var row: Dictionary = plan.get("probes", {}).get(room, {})
	if row.is_empty(): return true
	var c = ctl()
	if c.entry != str(row.entry): return fail("probe entry mismatch in " + room)
	var t0 := tick
	for p in row.tokens:
		var ok: bool = await run_token(str(p.token), str(p.key)) if bool(p.ok) else await reject_token(str(p.token))
		if not ok: return false
	probe_log.append({"room": room, "tokens": row.tokens.size(), "rejected": row.tokens.filter(func(p): return not p.ok).size(), "ticks": tick - t0})
	return true

func run_token(token: String, expect_key: String) -> bool:
	var c = ctl()
	if not await idle_until_decision(): return fail("executor never became ready for " + token)
	var before: int = c.steps.size()
	if token == "reset":
		for i in 120:
			await step(Vector2.ZERO, ["reset"])
			if c.steps.size() > before and c.steps[-1].token == "reset": break
		await step()
		if c.steps.size() <= before or c.steps[-1].token != "reset": return fail("hold R did not reset " + c.rules.id)
	else:
		var parts := token.split(".")
		var kind := parts[0]
		if kind == "pull" and not await face(Rules.OPPOSITE[parts[1]]): return fail("could not face the block for " + token)
		if kind == "act" and not await face(face_toward(parts[1])): return fail("could not face " + parts[1])
		var v := Vector2.ZERO
		var b := []
		match kind:
			"move": v = c.input_for(parts[1])
			"pull":
				v = c.input_for(parts[1])
				b = ["primary"]
			"act": b = ["primary"]
		for attempt in 3:
			if not await idle_until_decision(): break
			await step(v, b)
			if c.steps.size() > before: break
			retries += 1
			await step() # a neutral frame releases E / awaiting-neutral before retrying
		if c.steps.size() <= before: return fail("token was not executed physically: " + token + " in " + c.rules.room)
	var row: Dictionary = c.steps[-1]
	if row.token != token or row.key != expect_key:
		mismatches.append({"token": token, "expected": expect_key, "got": row})
		return fail("grid state diverged from the proof at " + token + " in " + c.rules.room)
	return true

func facts_match(row: Dictionary) -> bool:
	var flags: Dictionary = view.runtime.state.flags
	for name in row.flags:
		if bool(flags.get(name, false)) != bool(row.flags[name]):
			mismatches.append({"action": row.action, "fact": name, "expected": row.flags[name], "got": flags.get(name, null)})
			return false
	var have: Array = view.runtime.state.inventory.duplicate()
	have.sort()
	var want: Array = row.inventory.duplicate()
	want.sort()
	if have != want:
		mismatches.append({"action": row.action, "inventory_expected": want, "inventory_got": have})
		return false
	return true

func shoot(label: String) -> void:
	if DisplayServer.get_name() == "headless": return
	measurement_boundary("puzzle screenshot readback")
	if await view.capture_low(config.output.path_join("puzzle_" + label + ".png")): shots.append("puzzle_" + label + ".png")

func run_row(row: Dictionary, check_facts := true) -> bool:
	var c = ctl()
	var id := str(row.action)
	if row.has("error"): return fail("plan step has no continuous grid route: " + id)
	if view.runtime.state.location != str(row.room): return fail("bot is in " + view.runtime.state.location + ", plan expects " + str(row.room))
	var t0 := tick
	if c.active and row.route.size() > 0 and c.steps.size() > 0 and str(c.steps[-1].token).begins_with("enter:"):
		await shoot(c.rules.id + "_entry")
	if c.active and not probed.has(c.rules.room) and not await run_probes(c.rules.room): return false
	for r in row.route:
		if not await run_token(str(r.token), str(r.key)): return false
	if c.active and row.has("end_key") and str(c.rules.key(c.st)) != str(row.end_key):
		return fail("grid state after " + id + " differs from the plan")
	if id.begins_with("move:"):
		var d: String = WALL_DIR[str(row.exit_dir)]
		var before_room: String = view.runtime.state.location
		for attempt in 3:
			if not await idle_until_decision(): break
			await step(c.input_for(d), [])
			await step()
			if view.runtime.state.location != before_room: break
			retries += 1
		if view.runtime.state.location != str(row.location): return fail("door did not lead to " + str(row.location) + " via " + id)
		await settle_frames(2)
	elif id.begins_with("puzzle:"):
		if id.ends_with(":solve"): await shoot(c.rules.id + "_solved")
	elif id.begins_with("checkpoint:"):
		return fail("checkpoint commits inside puzzle rooms are not exercised by this bot") # puzzle_hall has none
	else:
		if row.has("target_cell"):
			var at := Vector2i(int(row.target_cell[0]), int(row.target_cell[1]))
			var dv: Vector2i = at - c.st.p
			var d := ""
			for k in Rules.DIRS:
				if Rules.DIRS[k] == dv: d = k
			if not await face(d): return fail("could not face the anchor of " + id)
		var before := dispatches.size()
		for attempt in 3:
			if not await idle_until_decision(): break
			await step(Vector2.ZERO, ["primary"])
			await step()
			if dispatches.size() > before: break
			retries += 1
		if dispatches.size() <= before or dispatches[-1].action != id or not dispatches[-1].ok:
			return fail("E did not dispatch " + id + " in the puzzle room")
		await settle_frames(30)
		await shoot(view.runtime.state.location + "_" + id.replace(":", "_"))
	actions_done.append(id)
	states.append(view.runtime.state.duplicate(true))
	events.append({"tick": tick, "action": id, "room": view.runtime.state.location}); last_event = tick
	if first_event < 0: first_event = tick
	row_log.append({"index": row.index, "action": id, "ticks": tick - t0, "tokens": row.route.size()})
	# A step whose follow-up fires on the same tick (plan row "immediate") is checked after that follow-up.
	if check_facts and not facts_match(row): return fail("puzzle facts after " + id + " differ from the plan")
	return true

## First solved puzzle inside the committed checkpoint room: the quick save carries real puzzle facts.
func save_point(row: Dictionary) -> bool:
	if not str(row.action).begins_with("puzzle:") or not str(row.action).ends_with(":solve"): return false
	var cp: Dictionary = view.runtime.modules.checkpoints[view.runtime.state.modules.checkpoint]
	return str(cp.room) == view.runtime.state.location

func quick_save() -> void:
	await idle_until_decision()
	await step(Vector2.ZERO, ["quick_save"])
	await step()
	saved = {"flags": view.runtime.state.flags.duplicate(true), "inventory": view.runtime.state.inventory.duplicate(),
		"location": view.runtime.state.location, "tick": tick}
	save_receipt["saved_at_tick"] = tick
	save_receipt["file"] = FileAccess.file_exists(config.output.path_join("checkpoint.json"))

## After the ending: Q-free quick load must restore the saved facts, re-enter the checkpoint room and rebuild
## the puzzle room from those facts (lock open, key taken) through the real codec + membership check.
func quick_load() -> bool:
	await step(Vector2.ZERO, ["quick_load"])
	await settle_frames(4)
	var c = ctl()
	save_receipt["loaded_location"] = view.runtime.state.location
	save_receipt["loaded_flags_match"] = view.runtime.state.flags == saved.flags
	save_receipt["loaded_inventory_match"] = view.runtime.state.inventory == saved.inventory
	save_receipt["executor_room"] = c.rules.room if c.active else ""
	save_receipt["executor_key"] = str(c.rules.key(c.st)) if c.active else ""
	save_receipt["expected_key"] = str(plan.get("load_key", ""))
	var ok: bool = save_receipt.file and view.runtime.state.location == saved.location and save_receipt.loaded_flags_match and save_receipt.loaded_inventory_match and c.active and save_receipt.executor_key == save_receipt.expected_key
	if not ok: failures.append("quick load did not restore the saved puzzle checkpoint: " + JSON.stringify(save_receipt))
	await shoot("after_load")
	return ok

func run() -> void:
	config = Wire.read_json("res://playtest-config.json")
	plan = Wire.read_json("res://puzzle-plan.json")
	input_file = FileAccess.open(config.output.path_join("inputs.jsonl"), FileAccess.WRITE)
	snapshots = FileAccess.open(config.output.path_join("module-inputs.jsonl"), FileAccess.WRITE)
	view = ModuleView.new()
	root.add_child(view)
	var booted: Dictionary = view.boot(Wire.read_json("res://game.json"), {"pack": "res://theme.json", "bindings": "res://bindings.json", "save": config.output.path_join("checkpoint.json")})
	if not booted.ok: failures.append(str(booted)); await finish(); return
	view.state_changed.connect(func(result): dispatches.append(result))
	view.actions.configure({"version": 1}); view.actions.set_source("bot")
	view.options["replay_trace"] = true
	install_frame_probes()
	start_memory = int(Performance.get_monitor(Performance.MEMORY_STATIC))
	module_names = ["puzzle"]
	if ctl() == null: failures.append("puzzle executor not installed"); await finish(); return
	await step()
	view.replay.start_record(config.output.path_join("modules.h64movie.json"), int(config.get("seed", 7)))
	var passed := true
	var rows: Array = plan.rows
	for i in rows.size():
		var chained: bool = i + 1 < rows.size() and bool(rows[i + 1].get("immediate", false))
		if not await run_row(rows[i], not chained):
			passed = false
			break
		if saved.is_empty() and not chained and save_point(rows[i]):
			await quick_save()
	await settle_frames(20)
	passed = passed and view.runtime.endings(view.runtime.state).has(str(plan.ending))
	# The movie covers the proved run up to the ending (replayed by tools/puzzle_play.py); the quick load
	# afterwards is a separate receipt because replay-mode saves use in-memory checkpoints.
	if view.replay != null and view.replay.recording:
		var recorded: Dictionary = view.replay.stop_record()
		if recorded.ok: replay_files.append(recorded.path.get_file())
		else: failures.append("module movie recording failed")
	if passed and not saved.is_empty(): passed = await quick_load()
	paths.append({"ending": plan.ending, "passed": passed})
	completed = passed and failures.is_empty()
	await finish()

func finish() -> void:
	var c = ctl()
	var receipt := {"plan_rows": plan.get("rows", []).size(), "rows_done": row_log, "retries": retries, "turns": turns,
		"mismatches": mismatches, "executor_steps": c.steps if c != null else [], "cues": c.cue_log if c != null else [],
		"dispatched": c.dispatched if c != null else [], "final_hash": view.module_host.state_hash() if view != null and view.module_host != null else "",
		"screenshots": shots, "completed": completed, "ticks": tick, "ending": plan.get("ending", ""), "save_load": save_receipt, "probes": probe_log}
	var file := FileAccess.open(config.output.path_join("puzzle-bot.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(receipt, "", true)); file.close()
	print("PUZZLE_BOT completed=%s ticks=%d steps=%d retries=%d mismatches=%d" % [completed, tick, receipt.executor_steps.size(), retries, mismatches.size()])
	await super.finish()
