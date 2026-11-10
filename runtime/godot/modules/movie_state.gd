extends RefCounted
## Complete simulation extension; scene resources are reconstructed from pinned game data.
const HOST = ["generation","physics_tick","attempt_tick","sequence","retry_ticks","flash_ticks","modal","was_modal","active_id","loaded_generation"]
const COMBAT = ["health","max_health","age","roll_age","hurt_age","tick_index","swing_id","hit_ids","defeated","target","result","wave","damage_taken","blocks","rolls","swings","block_available","blocking","seed_value","feedback"]
const ENEMY = ["hp","state","age","attack_id","hit"]
const COURSE = ["countdown","elapsed","history","result","speed","invalid_motion"]
static func vector(v: Vector3) -> Array: return [v.x,v.y,v.z]
static func v3(v: Array) -> Vector3: return Vector3(v[0],v[1],v[2])
static func fields(object, names: Array) -> Dictionary:
	var out := {}
	for key in names: out[key] = object.get(key)
	return out.duplicate(true)
static func apply(object, value: Dictionary, names: Array) -> void:
	for key in names: object.set(key,value[key])
static func capture(host) -> Dictionary:
	var data := fields(host,HOST)
	data["course_roll_age"] = host.course_roll_age
	data["course_roll_direction"] = vector(host.course_roll_direction)
	data["finite"] = host.runtime.state.duplicate(true)
	data["previous_position"] = vector(host.previous_position)
	data["input"] = {"suppressed":host.input.suppressed,"awaiting_neutral":host.input.awaiting_neutral}
	data["pending"] = {} if host.pending.is_empty() else {"action":host.pending.action,"ticks":host.pending.ticks}
	data["combat"] = {}; data["course"] = {}
	if host.combat != null: data.combat = capture_combat(host.combat)
	if host.course != null: data.course = fields(host.course,COURSE)
	if host.run.enabled: data["run"] = host.run.snapshot()
	if host.puzzle != null: data["puzzle"] = host.puzzle.capture()
	return data
## The fight in progress (also used directly by tests/combat_robots.gd for mid-fight capture/restore).
static func capture_combat(c) -> Dictionary:
	var out := fields(c,COMBAT)
	out["rng"] = str(c.rng.state)
	out["roll_direction"] = vector(c.roll_direction)
	out["enemies"] = []
	for enemy in c.enemies:
		var e := fields(enemy,ENEMY)
		e["id"] = enemy.identity; e["latched"] = vector(enemy.latched)
		e["position"] = vector(enemy.body.position); e["yaw"] = enemy.body.rotation.y
		# COMBAT lane (API 1.1.0): robot/boss FSM extras; absent for the melee templates.
		if enemy.has_method("capture_extra"): e["robot"] = enemy.capture_extra()
		out.enemies.append(e)
	if c.extended: out["extra"] = c.extra_snapshot()
	return out
## Rebuild `c` (already begun on the same encounter) to a captured fight.
static func restore_combat(c, data: Dictionary) -> void:
	c.dispose(); c.wave = int(data.wave); c.spawn_wave()
	apply(c,data,COMBAT)
	c.rng.state = int(data.rng); c.roll_direction = v3(data.roll_direction)
	for row in data.enemies:
		for enemy in c.enemies:
			if enemy.identity != row.id: continue
			apply(enemy,row,ENEMY); enemy.latched = v3(row.latched)
			enemy.body.position = v3(row.position); enemy.body.rotation.y = row.yaw
			if row.has("robot"): enemy.restore_extra(row.robot)
	if data.has("extra"): c.restore_extra(data.extra)
static func restore(host, data: Dictionary) -> void:
	if not host.pending.is_empty():
		if is_instance_valid(host.pending.probe): host.pending.probe.free()
		host.pending = {}
	host.clear_attempt()
	if data.active_id != "": host.start_attempt(data.active_id)
	if not data.combat.is_empty():
		restore_combat(host.combat, data.combat)
		host.build_enemies()
	if not data.course.is_empty(): apply(host.course,data.course,COURSE)
	if not data.pending.is_empty():
		host.travel(data.pending.action)
		host.pending.ticks = int(data.pending.ticks)
	apply(host,data,HOST)
	host.course_roll_age = int(data.course_roll_age)
	host.course_roll_direction = v3(data.course_roll_direction)
	host.previous_position = v3(data.previous_position)
	host.input.suppressed = data.input.suppressed
	host.input.awaiting_neutral = data.input.awaiting_neutral
	host.presenter.player.focus_point = null
	if data.has("run") and host.run.enabled: host.run.restore(data.run)
	if host.puzzle != null and data.has("puzzle"): host.puzzle.restore(data.puzzle)
	if host.combat != null:
		var enemy = host.combat.find_target(host.combat.target)
		if enemy != null: host.presenter.player.focus_point = enemy.body.position
	host.prepare_motion()
