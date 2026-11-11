extends Node
## One trusted fixed-tick authority, mounted without changing protected controls.
signal control_claimed(owner: String, generation: int)
signal control_released(generation: int)
signal motion_requested(intent: Dictionary)
signal animation_requested(clip: String, placeholder: bool)
signal focus_changed(id: String, position: Vector3)
signal story_event(kind: String, payload: Dictionary)
const InputAdapter = preload("res://modules/input_adapter.gd")
const Combat = preload("res://modules/combat/runtime.gd")
const Course = preload("res://modules/course/runtime.gd")
const Regions = preload("res://modules/regions/runtime.gd")
const AnimationState = preload("res://modules/animation_state.gd")
const ClipPhases = preload("res://modules/combat/clip_phases.gd")
const Room = preload("res://view/room.gd")
const PuzzleController = preload("res://modules/puzzle/controller.gd")
## A defeated actor's model stays as a corpse for this many ticks (death plays to its last key at
## 15 fps by tick 60, then holds). Presentation only: corpses are never hashed, saved or collided.
const CORPSE_TICKS := 90
var presenter
var runtime
var input = InputAdapter.new()
var animation = AnimationState.new()
var regions = Regions.new()
var combat
var run = preload("res://modules/combat/run.gd").new()
var course
var course_roll_age := -1
var course_roll_direction := Vector3.ZERO
var generation := 0
var physics_tick := 0
var attempt_tick := 0
var sequence := 0
var retry_ticks := 0
var flash_ticks := 0
var modal := false
var was_modal := false
var active_id := ""
var pending := {}
var previous_position := Vector3.ZERO
var markers: Node3D
var hud
var events := []
var attempts := []
var base_speed := 2.4
var transition_errors := []
var loaded_generation := 0
var has_simulation_gate := false
var combat_bindings = preload("res://modules/bindings.gd").new()
var binding_error := ""
# Combat art seam (MERGE3): res://combat.json, staged from characters/combat/manifest.json. Empty when
# no art is staged; then the pre-MERGE3 labelled POSE TEST path stays in force.
var combat_art := {}
var corpses := []
var hidden_player := false
var block_ticks := 0
var death_ticks := 0
var course_animating := false
# COMBAT lane readability (presentation only, never hashed or saved): the combat camera challenge profile and the
# combat stage (lighting, telegraph decals, contact shadows, flashes, dodge glyphs, audio cues).
var combat_camera = preload("res://modules/combat/camera.gd").new()
var stage = preload("res://modules/combat/stage.gd").new()
var puzzle = null # STORY 1.3 puzzle executor; only when the build ships res://puzzle.json
static func install(view, actions = null):
	if view.runtime.game.contract_version != "1.2.0": return null
	if view.has_meta("module_host"): return view.get_meta("module_host")
	var host = load("res://modules/host.gd").new()
	host.presenter = view
	host.runtime = view.runtime
	if actions == null:
		host.binding_error = "production module host requires Actions"
		return host
	host.input.provider = actions
	view.add_child(host)
	view.set_meta("module_host", host)
	host.attach()
	return host
func attach() -> void:
	process_physics_priority = 10
	var binding_data = null
	if FileAccess.file_exists("res://combat-bindings.json"):
		binding_data = JSON.parse_string(FileAccess.get_file_as_string("res://combat-bindings.json"))
		if binding_data == null: binding_error = "invalid combat binding JSON"; set_physics_process(false); return
	if not combat_bindings.configure(binding_data,presenter.resolver):
		binding_error = combat_bindings.error
		set_physics_process(false)
		return
	if FileAccess.file_exists("res://combat.json"):
		var art = JSON.parse_string(FileAccess.get_file_as_string("res://combat.json"))
		if not art is Dictionary or art.get("api_version") != "1.0.0" or not art.get("enemies") is Dictionary or not art.get("clips") is Dictionary:
			binding_error = "invalid combat art manifest"; set_physics_process(false); return
		combat_art = art
	if combat_bindings.rows.has("player"):
		var previous = presenter.player.get_node_or_null("visual")
		if previous != null: previous.free()
		var visual = combat_bindings.character("player",presenter.resolver)
		if visual == null: binding_error = "combat player failed to load"; set_physics_process(false); return
		presenter.player.add_child(visual)
		visual.name = "visual"
		visual.rotation.y = PI
	has_simulation_gate = presenter.get_property_list().any(func(p): return p.name == "simulation_enabled")
	regions.configure(runtime)
	run.configure(runtime.game.gameplay.get("run", {}), runtime.game.gameplay.get("movement_combat_profile", "") == "combat2_v1" and runtime.game.gameplay.has("run"))
	base_speed = float(presenter.player.tuning.run_speed_mps)
	presenter.state_changed.connect(_state_changed)
	presenter.room_entered.connect(_room_entered)
	combat_camera.attach(presenter)
	stage.attach(self)
	hud = preload("res://modules/hud.gd").new()
	hud.host = self
	presenter.viewport.add_child(hud)
	restore_checkpoint()
	if FileAccess.file_exists("res://puzzle.json"):
		puzzle = PuzzleController.new()
		puzzle.name = "puzzle"
		add_child(puzzle)
		puzzle.attach(self)
		if puzzle.error != "": binding_error = puzzle.error; set_physics_process(false)
func vector(a: Array) -> Vector3:
	return Vector3(a[0], a[1], a[2])
func emit_event(kind: String, payload: Dictionary) -> void:
	var row := {"kind":kind,"payload":payload.duplicate(true),"tick":physics_tick,"attempt":generation}
	events.append(row)
	story_event.emit(kind, payload)
func clear_attempt() -> void:
	generation += 1
	sequence = 0
	# Stale corpses go first; disposing this attempt's enemies may keep the defeated ones as corpses.
	clear_corpses()
	if combat != null: combat.dispose()
	combat = null
	course = null
	course_roll_age = -1; course_roll_direction = Vector3.ZERO
	active_id = ""
	course_animating = false
	block_ticks = 0
	death_ticks = 0
	# Readability eases out from here (presentation only).
	combat_camera.stop()
	stage.stop()
	animation.release()
	input.clear()
	presenter.player.speed_limit = INF
	control_released.emit(generation)
func restore_checkpoint() -> void:
	clear_attempt()
	combat_camera.reset()
	stage.reset()
	retry_ticks = 0
	loaded_generation += 1
	var cp: Dictionary = runtime.modules.checkpoints[runtime.state.modules.checkpoint]
	if cp.room == runtime.state.location:
		presenter.player.position = vector(cp.position_m) + Vector3.UP * 0.02
	presenter.player.velocity = Vector3.ZERO
	presenter.player.latched = false
	previous_position = presenter.player.position
	refresh_markers()
func _room_entered(_id: String) -> void:
	clear_attempt()
	# The new room's look was just applied: cut back at once, never restore the old room's globals.
	combat_camera.reset()
	stage.reset()
	refresh_markers()
func _state_changed(_result: Dictionary) -> void:
	var id: String = runtime.state.modules.active
	if id != "" and id != active_id: start_attempt(id)
	elif active_id != "" and id == "":
		clear_attempt()
	# enter_room may have already cleared the executor before state_changed.
	if runtime.state.modules.failed != "" and retry_ticks == 0: retry_ticks = 60
	refresh_markers()
func start_attempt(id: String) -> void:
	clear_attempt()
	active_id = id
	attempt_tick = 0
	var c: Dictionary = runtime.modules.challenges[id]
	if c.kind == "combat":
		# Combat owns the player's animation; a course leaves locomotion to the actor bridge and only
		# borrows the roll clip while a course roll runs.
		animation.bind(presenter.player.get_node_or_null("visual"))
		arm_player()
		combat_audit.attempts += 1
		if not animation.placeholder: combat_audit.player_real_clips += 1
		combat = Combat.new()
		combat.profile = runtime.game.gameplay.get("movement_combat_profile", "legacy")
		combat.moveset = runtime.modules.catalogue.abilities.config.get("moveset", "")
		combat.on_release = _enemy_released
		combat.protection_ticks = int(run.rules.get("hit_invulnerability_ticks", 18))
		combat.begin(runtime.modules.entities("combat", "encounters")[c.subject], runtime.modules.entities("combat", "archetypes"), presenter.player, presenter.world, int(run.rules.get("max_health", runtime.modules.catalogue.abilities.config.max_health)) if run.enabled else runtime.modules.catalogue.abilities.config.max_health, int(runtime.game.gameplay.seed))
		if run.enabled: run.checkpoint()
		combat.block_available = animation.has_clip("block")
		build_enemies()
		stage.start(combat.encounter)
		combat_camera.configure(stage.profile)
		combat_camera.start()
		quiet_clear = bool(combat.extended)
	else:
		course = Course.new()
		course.begin(runtime.modules.entities("course", "tracks")[c.subject], runtime.modules.catalogue.course.config.max_speed_mps)
		presenter.player.speed_limit = minf(base_speed, course.speed)
	previous_position = presenter.player.position
	presenter.n64_ui.hide_dialog()
	control_claimed.emit(c.kind, generation)
	emit_event("challenge_started", {"challenge":id})
## The trail_staff on hand_r (documented grip), for a combatant whose real clips are bound.
func arm_player() -> void:
	if combat_art.is_empty() or animation.placeholder or animation.actor == null: return
	var grip = combat_art.get("grips", {}).get(str(animation.actor.get_meta("character_id", "")), null)
	if not grip is Dictionary: return
	var row = combat_art.get("weapons", {}).get(grip.get("pack", ""), null)
	if not row is Dictionary: return
	var staff = presenter.resolver.weapon_node(row, animation.actor)
	if staff != null and not animation.attach_weapon(staff, grip, row.rotation_xyzw): staff.free()
## Enemy art for an archetype: its own model, else the model of its FSM template's archetype
## (cairn_keeper is a melee_dash_v1 like cairn_dasher). Null when no combat art is staged.
func enemy_art(data: Dictionary):
	if combat_art.is_empty(): return null
	var rows: Dictionary = combat_art.enemies
	if rows.has(data.id): return rows[data.id]
	var alias: String = combat_art.get("templates", {}).get(data.get("fsm", {}).get("template", ""), "")
	if alias == "": alias = str(robot_standin(data).get("model", ""))
	return rows.get(alias, null)
## COMBAT lane manifest seam: a robot template without its own art (no enemies[id], no templates[template] in
## combat.json) uses an existing enemy model from modules/combat/robots.json, with its scale/lift. {} otherwise.
static var standins = null
func robot_standin(data: Dictionary) -> Dictionary:
	var template: String = data.get("fsm", {}).get("template", "")
	if not template in ["walker_patrol_v1", "brute_slam_v1", "hover_drone_v1", "boss_phases_v1"]: return {}
	if combat_art.get("enemies", {}).has(data.id) or combat_art.get("templates", {}).has(template): return {}
	if standins == null:
		var parsed = JSON.parse_string(FileAccess.get_file_as_string("res://modules/combat/robots.json"))
		standins = parsed.get("standins", {}) if parsed is Dictionary else {}
	return standins.get(template, {})
func enemy_scale(enemy) -> float:
	var stand := robot_standin(enemy.data)
	if not stand.is_empty(): return float(stand.get("scale", 1.0))
	if enemy.has_method("current_attack"): return 1.0
	return 1.12 if enemy.data.max_health > 3 else 1.0
func build_enemies() -> void:
	if combat == null: return
	for enemy in combat.enemies:
		if enemy.visual != null: continue
		var original = presenter.player.get_node_or_null("visual")
		var row = enemy_art(enemy.data) if not combat_bindings.rows.has(enemy.data.id) else null
		if row is Dictionary:
			enemy.visual = presenter.resolver.enemy_actor(row)
			if enemy.visual != null:
				enemy.body.add_child(enemy.visual)
				# Same model convention as the player's real-character visual: the model faces +Z.
				enemy.visual.rotation.y = PI
				enemy.visual.scale *= enemy_scale(enemy)
				enemy.visual.position.y += float(robot_standin(enemy.data).get("lift_m", 0.0))
				enemy.set_meta("art_row", row)
				enemy.animation.face_cells = row.get("face_atlas", {}).get("clip_cells", {})
				enemy.animation.bind(enemy.visual, row.get("clips", []))
				combat_audit.enemy_models[enemy.data.id] = {"model":row.id, "sha256":row.sha256, "clips_bound":not enemy.animation.placeholder}
				continue
		combat_audit.enemy_placeholders += 1
		# No staged combat art (or a toolkit pin): the admitted actor binding with labelled POSE TEST poses.
		var c: Dictionary = runtime.characters.get(runtime.game.metadata.get("protagonist", ""), {})
		enemy.visual = combat_bindings.character(enemy.data.id,presenter.resolver)
		if enemy.visual == null: enemy.visual = presenter.resolver.character(c)
		if enemy.visual == null: enemy.visual = presenter.room_root.person(enemy.body, {"colour":"867852"})
		else: enemy.body.add_child(enemy.visual)
		enemy.visual.set_meta("module_pose_placeholder", true)
		if original != null: enemy.visual.rotation.y = original.rotation.y
		enemy.visual.scale *= enemy_scale(enemy)
		enemy.animation.bind(enemy.visual)
## Shown key for the player's pose this tick, from the ages the combat runtime used for its checks.
func player_key(pose: String) -> int:
	var meta: Dictionary = combat_art.get("clips", {})
	if combat.brawler() and pose in ["swing", "swing2", "swing3", "charge", "dash_attack"]: return ClipPhases.move_key(combat.shown_swing, combat.frame_data())
	block_ticks = block_ticks + 1 if pose == "block" else 0
	death_ticks = death_ticks + 1 if pose == "death" else 0
	match pose:
		"swing": return ClipPhases.swing_key(combat.shown_swing, meta)
		"roll": return ClipPhases.roll_key(combat.shown_roll, meta)
		"hurt": return ClipPhases.hurt_key(combat.shown_hurt)
		"death": return ClipPhases.realtime_key(death_ticks - 1)
		"block": return ClipPhases.block_key(block_ticks - 1, meta)
	return ClipPhases.loop_key(combat.tick_index)
## COMBATFIX: moving in the idle stance plays the body's baked walk/run at the ground speed (backwards when moving away
## from the facing), the stance's spine, head and arms held; a stop settles into the stance. Every other pose (swing,
## roll, hurt, block, death) shows at once, as before. Bodies without baked locomotion keep the stance. Presentation only.
var walk_back := false
var walk_from = null
func show_player(pose: String) -> void:
	var key := player_key(pose)
	var actor = animation.actor
	# the ground speed is the body's move this tick after the fight's impulse and arena clamp (actual_velocity is the
	# controller's, which keeps walking into the arena edge)
	var v: Vector3 = presenter.player.actual_velocity
	var at: Vector3 = presenter.player.position
	if walk_from is Vector3 and (at - walk_from).length() < 0.2: v = (at - walk_from) * 60.0
	walk_from = at
	if pose == "idle_combat" and not animation.placeholder and is_instance_valid(actor) and actor.get("loco") is Dictionary and not actor.loco.is_empty():
		var speed := Vector2(v.x, v.z).length()
		if speed > 0.05 or actor.loco_on:
			var ahead := Vector3(-sin(presenter.player.facing_yaw), 0, -cos(presenter.player.facing_yaw)).dot(Vector3(v.x, 0, v.z)) / maxf(speed, 0.001)
			if speed > 0.05: walk_back = ahead < -0.2 or (walk_back and ahead < 0.2)
			actor.hold = {"clip": animation.resolve_clip(pose), "key": key}
			actor.drive(speed, 0.05, walk_back)
			actor.advance_pose(1.0 / 60.0)
			animation.shown = ""
			if actor.loco_on: return
	if is_instance_valid(actor) and actor.get("hold") is Dictionary: actor.hold = {}
	animation.show(pose, key)
## Enemy clip/key from its FSM state and saved FSM age (dead counts presentation ticks on the host).
func show_enemy(enemy) -> void:
	var row = enemy.get_meta("art_row", null)
	if not row is Dictionary:
		enemy.animation.play({"telegraph":"idle_combat","attack":"swing","hurt":"hurt","dead":"death"}.get(enemy.state,"idle_combat"))
		return
	var dead_t := 0
	if enemy.state == "dead":
		dead_t = int(enemy.get_meta("dead_t", -1)) + 1
		enemy.set_meta("dead_t", dead_t)
	var shown: Array = ClipPhases.enemy_pose(row, pose_data(enemy), enemy.state, enemy.age, dead_t)
	enemy.animation.show(shown[0], shown[1])
## Clip pacing data: a robot's attack in play and stagger length; the archetype row for the melee templates.
func pose_data(enemy) -> Dictionary:
	return enemy.pose_data() if enemy.has_method("pose_data") else enemy.data
func attack_of(enemy) -> Dictionary:
	return enemy.current_attack() if enemy.has_method("current_attack") else enemy.data.attack
func _enemy_released(enemy) -> void:
	var visual = enemy.visual
	if visual == null or not is_instance_valid(visual) or enemy.state != "dead" or not enemy.has_meta("art_row"): return
	var at: Transform3D = visual.global_transform
	visual.get_parent().remove_child(visual)
	presenter.room_root.add_child(visual)
	visual.global_transform = at
	enemy.visual = null
	keep_corpse(visual, enemy.get_meta("art_row").get("face_atlas", {}).get("clip_cells", {}), int(enemy.get_meta("dead_t", -1)) + 1)
func keep_corpse(visual: Node3D, cells: Dictionary, t := 0) -> void:
	var state = AnimationState.new()
	state.face_cells = cells
	state.bind(visual, ["death"])
	if state.placeholder:
		visual.free()
		return
	corpses.append({"visual":visual, "animation":state, "t":t})
	state.show("death", ClipPhases.realtime_key(t))
## On a KO the player's model is shown collapsing where it fell while the retry countdown runs at the
## checkpoint; the live player visual stays hidden until the retry is ready.
func spawn_player_corpse(at: Transform3D) -> void:
	var visual = presenter.player.get_node_or_null("visual")
	if visual == null or not visual.get_meta("real_character", false): return
	var body = presenter.resolver.character(runtime.characters.get(runtime.game.metadata.get("protagonist", ""), {}))
	if body == null: return
	presenter.room_root.add_child(body)
	body.global_transform = at
	keep_corpse(body, {})
	visual.visible = false
	hidden_player = true
## Presentation audit for acceptance (never hashed or saved): which keys were on screen when gameplay
## events landed. Violations: a hit outside swing keys 5-7, damage taken while the roll shows its i-frame
## keys 2-9, enemy contact outside its attack clip's hit-window keys, or an attack whose telegraph was
## not shown for the whole windup.
var combat_audit := {"attempts":0, "player_real_clips":0, "enemy_models":{}, "enemy_placeholders":0, "hits":[], "contacts":[], "telegraphs":[], "violations":[]}
var audited_tick := -1
func audit_combat() -> void:
	# A hit-stop holds the fight (tick_index does not advance): audit each simulated tick once.
	if combat.extended:
		if combat.tick_index == audited_tick: return
		audited_tick = combat.tick_index
	var a: Dictionary = combat_audit
	var meta: Dictionary = combat_art.get("clips", {})
	var roll: int = ClipPhases.roll_key(combat.shown_roll, meta) if combat.shown_roll >= 0 else -1
	var hurt := false
	for f in combat.feedback:
		if f.kind == "hurt": hurt = true
		# A deflected shot's hit lands on its own flight, not on swing keys (COMBAT lane, API 1.1.0).
		if f.kind != "hit" or f.get("source", "") == "deflect": continue
		var key: int = ClipPhases.swing_key(combat.shown_swing, meta)
		a.hits.append({"tick":combat.tick_index, "enemy":f.id, "swing_age":combat.shown_swing, "swing_key":key, "real":not animation.placeholder})
		if key < 5 or key > 7: a.violations.append("tick %d: hit on swing key %d" % [combat.tick_index, key])
	for enemy in combat.enemies:
		var row = enemy.get_meta("art_row", null)
		var shown: Array = ClipPhases.enemy_pose(row, pose_data(enemy), enemy.state, enemy.age) if row is Dictionary else [enemy.state, -1]
		if enemy.state == "telegraph":
			enemy.set_meta("audit_telegraph", int(enemy.get_meta("audit_telegraph", 0)) + 1)
			enemy.set_meta("audit_peak", maxi(int(enemy.get_meta("audit_peak", 0)), shown[1]))
		elif enemy.state == "attack" and enemy.age == 1:
			var ticks := int(enemy.get_meta("audit_telegraph", 0))
			a.telegraphs.append({"tick":combat.tick_index, "enemy":enemy.identity, "telegraph_ticks":ticks, "windup_ticks":int(attack_of(enemy).windup_ticks), "max_telegraph_key":int(enemy.get_meta("audit_peak", -1)), "real":row is Dictionary})
			if ticks < int(attack_of(enemy).windup_ticks): a.violations.append("tick %d: %s attacked after %d telegraph ticks" % [combat.tick_index, enemy.identity, ticks])
		if enemy.state != "telegraph":
			enemy.set_meta("audit_telegraph", 0)
			enemy.set_meta("audit_peak", 0)
		if enemy.hit and int(enemy.get_meta("audit_attack", -1)) != enemy.attack_id:
			enemy.set_meta("audit_attack", enemy.attack_id)
			var window: Array = ClipPhases.enemy_hit(row) if row is Dictionary else [0, ClipPhases.LAST]
			a.contacts.append({"tick":combat.tick_index, "enemy":enemy.identity, "state":enemy.state, "clip":shown[0], "key":shown[1], "player_hurt":hurt, "player_roll_key":roll, "real":row is Dictionary})
			if enemy.state != "attack" or shown[1] < window[0] or shown[1] > window[1]:
				a.violations.append("tick %d: %s contact on %s key %d" % [combat.tick_index, enemy.identity, shown[0], shown[1]])
			if hurt and roll >= 2 and roll <= 9: a.violations.append("tick %d: damage during roll i-frame key %d" % [combat.tick_index, roll])
## Course rolls borrow the roll clip with the same key map as combat (24 ticks; no damage on a course).
func show_course_roll(t: int) -> void:
	if t >= 0:
		if not course_animating:
			animation.bind(presenter.player.get_node_or_null("visual"), ["roll"])
			course_animating = not animation.placeholder
			if not course_animating: animation.release(); return
		animation.show("roll", ClipPhases.roll_key(t, combat_art.get("clips", {})))
	elif course_animating:
		animation.release()
		course_animating = false
func tick_corpses() -> void:
	for row in corpses.duplicate():
		if not is_instance_valid(row.visual):
			corpses.erase(row); continue
		row.t += 1
		if row.t >= CORPSE_TICKS:
			row.visual.free(); corpses.erase(row); continue
		row.animation.show("death", ClipPhases.realtime_key(row.t))
func clear_corpses() -> void:
	for row in corpses:
		if is_instance_valid(row.visual): row.visual.free()
	corpses.clear()
	if hidden_player:
		var visual = presenter.player.get_node_or_null("visual")
		if visual != null: visual.visible = true
		hidden_player = false
func anchor(id: String) -> Vector3:
	if id.begins_with("challenge:start:"):
		var cid := id.trim_prefix("challenge:start:")
		if not runtime.modules.challenges.has(cid): return Vector3.INF
		var c: Dictionary = runtime.modules.challenges[cid]
		if c.kind == "course": return vector(runtime.modules.entities("course", "tracks")[c.subject].start_position_m)
		var arena: Dictionary = runtime.modules.entities("combat", "encounters")[c.subject].arena
		return Vector3((arena.min[0]+arena.max[0])*0.5, 0, arena.min[2]+1.0)
	if id.begins_with("checkpoint:"):
		var cid := id.trim_prefix("checkpoint:")
		return vector(runtime.modules.checkpoints[cid].position_m) if runtime.modules.checkpoints.has(cid) else Vector3.INF
	return presenter.room_root.target_positions.get(id, Vector3.INF)
func allows_action(id: String) -> bool:
	if id.begins_with("assume:") or not pending.is_empty(): return false
	if puzzle != null and not puzzle.allows(id): return false
	if id.begins_with("challenge:start:") or id.begins_with("checkpoint:"):
		return not modal and presenter.player.position.distance_to(anchor(id)) <= 1.0
	if id.begins_with("move:"): return regions.eligible(id, presenter.player.position, anchor(id))
	return true
func travel(id: String) -> Dictionary:
	if not allows_action(id): return {"ok":false,"reason":"portal gate or proximity"}
	var destination := ""
	for a in runtime.actions(runtime.state):
		if a.id == id: destination = a.state.location
	if destination == "": return {"ok":false,"reason":"unavailable portal"}
	var at := regions.arrival(destination)
	if at == Vector3.INF: return {"ok":false,"reason":"missing destination checkpoint"}
	var probe = Room.new()
	probe.theme = presenter.theme
	probe.build(runtime.rooms[destination], runtime, presenter.resolver)
	probe.position = Vector3(2048,0,2048)
	probe.visible = false
	presenter.world.add_child(probe)
	pending = {"action":id,"room":destination,"arrival":at,"probe":probe,"ticks":0}
	presenter.menu_open = false
	presenter.sync_n64_ui(); presenter.sync_input_context()
	input.clear()
	control_claimed.emit("transition", generation)
	return {"ok":true,"status":"pending"}
func tick_transition() -> void:
	pending.ticks += 1
	presenter.player.enabled = false
	if pending.ticks < 12: return
	var arrival: Vector3 = pending.arrival
	var probe: Node3D = pending.probe
	var shape := CapsuleShape3D.new()
	shape.radius = 0.28
	shape.height = 1.4
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = shape
	query.collision_mask = 1
	query.transform = Transform3D(Basis.IDENTITY, probe.position + arrival + Vector3.UP * 0.75)
	var room: Dictionary = runtime.rooms[pending.room]
	var valid: bool = arrival.x >= 0.4 and arrival.z >= 0.4 and arrival.x <= room.grid_size[0]-0.4 and arrival.z <= room.grid_size[1]-0.4 and arrival.y < 0.2
	valid = valid and presenter.world.get_world_3d().direct_space_state.intersect_shape(query, 1).is_empty()
	var action: String = pending.action
	probe.free()
	pending = {}
	if valid:
		var result: Dictionary = presenter.commit_portal(action)
		if result.ok:
			presenter.player.position = arrival + Vector3.UP * 0.02
			previous_position = presenter.player.position
			emit_event("region_unlocked", {"room":runtime.state.location})
	else:
		transition_errors.append({"action":action,"reason":"unsafe destination checkpoint"})
	presenter.player.enabled = true
	input.clear()
	control_released.emit(generation)
func set_modal(value: bool) -> void:
	modal = value
	if value != was_modal:
		input.clear()
		presenter.player.velocity = Vector3.ZERO
	was_modal = value
func finish_attempt(success: bool) -> void:
	if active_id == "" or runtime.state.modules.active != active_id: return
	var id := active_id
	var kind: String = runtime.modules.challenges[id].kind
	var metric := {"challenge":id,"kind":kind,"ticks":attempt_tick,"seconds":float(attempt_tick)/60.0,"success":success,"damage_taken":combat.damage_taken if combat != null else 0,"swings":combat.swings if combat != null else 0,"rolls":combat.rolls if combat != null else 0}
	if course != null: metric["course"] = course.snapshot()
	attempts.append(metric)
	# Only this trusted executor invokes the macro reducer. No player event injection API.
	runtime.state = runtime.modules.outcome(runtime.state, success)
	if success and run.enabled and runtime.modules.challenges.keys().all(func(cid): return cid in runtime.state.modules.completed): run.finish()
	var new_room: String = runtime.state.location
	clear_attempt()
	if not success:
		if run.enabled: run.died()
		retry_ticks = 60
		if presenter.room_root.data.id != new_room: presenter.enter_room("")
		presenter.player.position = vector(runtime.modules.checkpoints[runtime.state.modules.checkpoint].position_m) + Vector3.UP*0.02
		presenter.player.velocity = Vector3.ZERO
	presenter.refresh()
	presenter.n64_ui.hide_dialog()
	emit_event(("encounter_cleared" if kind == "combat" else "course_completed") if success else "challenge_failed", metric)
	refresh_markers()
func paused() -> bool:
	return modal or not presenter.simulation_enabled or presenter.actions.context != "gameplay"

func prepare_motion() -> void:
	# Called by presenter at -50, before normal locomotion at 0; never a second mover.
	presenter.player.speed_limit = minf(base_speed,course.speed) if course != null else INF
	if paused() or not pending.is_empty() or retry_ticks > 0:
		presenter.player.enabled = false
	elif combat != null:
		var rolling: bool = combat.roll_age >= 0 or (combat.age < 0 and combat.hurt_age < 0 and input.just_pressed("dodge"))
		presenter.player.enabled = not rolling and combat.hurt_age < 0 and not (combat.extended and (combat.hitstop > 0 or combat.buffered == "dodge"))
	elif course != null:
		presenter.player.enabled = course.countdown == 0 and course_roll_age < 0 and not input.just_pressed("dodge")
	elif puzzle != null and puzzle.owns_input():
		presenter.player.enabled = false # the grid executor is the sole mover in puzzle rooms

func _physics_process(_delta: float) -> void:
	input.begin_tick()
	var stopped := paused()
	if stopped != was_modal:
		input.clear()
		was_modal = stopped
	input.suppressed = stopped
	if stopped:
		input.consume()
		return
	physics_tick += 1
	if run.enabled: run.advance(input.get_move().length() > 0.01 or ["primary","secondary","dodge","focus"].any(func(a): return input.is_pressed(a)))
	if flash_ticks > 0: flash_ticks -= 1
	if not pending.is_empty(): tick_transition(); hud.queue_redraw(); return
	if not corpses.is_empty(): tick_corpses()
	if retry_ticks > 0:
		retry_ticks -= 1
		if retry_ticks == 0:
			runtime.step("challenge:retry:" + runtime.state.modules.failed)
			restore_checkpoint()
			presenter.refresh()
			presenter.n64_ui.hide_dialog()
			emit_event("checkpoint_ready", {})
	elif active_id != "":
		attempt_tick += 1
		if combat != null:
			var motion: Dictionary = combat.tick(input)
			# The last KO tick, not the later hit-stop/clear beat, is the finish line.
			if run.enabled and combat.health > 0 and combat.defeated.size() == combat.encounter.spawns.size() and runtime.modules.challenges.keys().all(func(cid): return cid == active_id or cid in runtime.state.modules.completed): run.finish()
			if motion.impulse != Vector3.ZERO:
				presenter.player.move_and_collide(motion.impulse)
				presenter.player.position = presenter.player.position.snapped(Vector3.ONE*float(presenter.player.tuning.position_quantum_m))
			var area: Dictionary = combat.encounter.arena
			presenter.player.position.x = clampf(presenter.player.position.x, area.min[0]+0.3, area.max[0]-0.3)
			presenter.player.position.z = clampf(presenter.player.position.z, area.min[2]+0.3, area.max[2]-0.3)
			var target = combat.find_target(combat.target)
			presenter.player.focus_point = target.body.position if target != null else null
			presenter.focus_id = combat.target
			if target != null:
				var d: Vector3 = target.body.position - presenter.player.position
				presenter.player.set_facing_yaw(atan2(-d.x, -d.z))
				focus_changed.emit(combat.target, target.body.position)
			show_player(motion.pose)
			animation_requested.emit(motion.pose, animation.placeholder)
			motion_requested.emit({"enabled":presenter.player.enabled,"speed_scale":1.0,"facing_target":target.body.position if target != null else null,"impulse":motion.impulse})
			tick_feedback = combat.feedback.duplicate(true)
			sfx_extra = sfx_events() if presenter.sounds.has_method("has_sfx") and presenter.sounds.has_sfx() else []
			if not combat.feedback.is_empty(): flash_ticks = 6
			# Story events for the boss beat (dialogue/region hooks); emitted before encounter_cleared.
			for f in combat.feedback:
				if f.kind == "boss_defeated": emit_event("boss_defeated", {"challenge":active_id, "boss":f.id})
				elif f.kind == "phase": emit_event("boss_phase", {"challenge":active_id, "boss":f.id, "phase":f.phase})
			build_enemies()
			for enemy in combat.enemies: show_enemy(enemy)
			audit_combat()
			if combat.result != "":
				var knocked_out: bool = combat.result == "failed" and combat.health <= 0 and not animation.placeholder and is_instance_valid(animation.actor)
				var at: Transform3D = animation.actor.global_transform if knocked_out else Transform3D()
				var room: String = runtime.state.location
				finish_attempt(combat.result == "completed")
				if knocked_out and runtime.state.location == room and retry_ticks > 0: spawn_player_corpse(at)
		else:
			if course.countdown == 0 and course_roll_age < 0 and input.just_pressed("dodge"):
				course_roll_age = 0
				course_roll_direction = presenter.player.direction(input.get_move()).normalized()
				if course_roll_direction.length() < 0.1:
					var yaw: float = presenter.player.facing_yaw
					course_roll_direction = Vector3(-sin(yaw),0,-cos(yaw))
			show_course_roll(course_roll_age)
			if course_roll_age >= 0:
				if course_roll_age < Combat.ROLL_MOVE:
					presenter.player.move_and_collide(course_roll_direction * minf(4.0,course.speed)/60.0)
					presenter.player.position = presenter.player.position.snapped(Vector3.ONE*float(presenter.player.tuning.position_quantum_m))
				course_roll_age += 1
				if course_roll_age >= Combat.ROLL_TICKS: course_roll_age = -1
			var position: Vector3 = presenter.player.position
			position.y = maxf(0.0, position.y)
			for event in course.tick(previous_position, position): emit_event("course_checkpoint", event)
			previous_position = position
			if course.result != "": finish_attempt(course.result == "completed")
	if puzzle != null and active_id == "" and retry_ticks == 0: puzzle.physics_tick(input)
	tick_readability()
	input.consume()
	hud.queue_redraw()
## Feedback rows of this tick's combat step (kept past finish_attempt, which drops the executor).
var tick_feedback := []
## The last fight used gameplay API 1.1.0: it ends on its own defeat beat (burst ring, cue, gate bars lifting), so
## the presenter shows no "Arena cleared" text panel for it. 1.0.0 fights keep the panel.
var quiet_clear := false
## COMBATFIX: combat event sounds (audio rows "sfx:<event>:<n>", from the project's audio slots combat_sfx). An event
## with rows replaces the stock cue for that feedback; games without rows keep the stock cues exactly. Events read from
## state after the step: dodge (a roll starts), punch_miss (a swing's hit window closes with no hit) and boss_telegraph
## (a boss enters telegraph). Presentation only: nothing here is read back by the simulation.
var sfx_extra := []
var sfx_rolls := 0
var sfx_window := false
var sfx_states := {}
func sfx_events() -> Array:
	var out := []
	if combat.rolls > sfx_rolls: out.append({"kind": "dodge"})
	sfx_rolls = combat.rolls
	var open: bool = combat.attack_window()
	if sfx_window and not open and combat.hit_ids.is_empty(): out.append({"kind": "miss"})
	sfx_window = open
	for enemy in combat.enemies:
		var was: String = sfx_states.get(enemy.identity, "")
		sfx_states[enemy.identity] = str(enemy.state)
		sfx_kinds[enemy.identity] = ("boss" if enemy.is_boss() else "robot") if enemy.has_method("is_boss") else "other"
		if str(enemy.state) == "telegraph" and was != "telegraph" and sfx_kinds[enemy.identity] == "boss": out.append({"kind": "telegraph", "id": enemy.identity})
	return out
var sfx_kinds := {}
func combat_sfx(f: Dictionary) -> bool:
	if not presenter.sounds.has_method("has_sfx") or not presenter.sounds.has_sfx(): return false
	var who: String = sfx_kinds.get(str(f.get("id", "")), "other")
	var boss := who == "boss"
	var robot := who == "robot"
	var event: String = {"hit": "boss_hit" if boss else ("robot_hit" if robot else "punch_hit"), "hurt": "player_hurt", "block": "block",
		"armor": "block", "deflect": "block", "defeated": "robot_death" if robot else "", "boss_defeated": "boss_hit", "dodge": "dodge",
		"miss": "punch_miss", "telegraph": "boss_telegraph"}.get(str(f.get("kind", "")), "")
	return event != "" and presenter.sounds.sfx(event, int(f.get("variant", 0)))
## COMBAT lane: camera, stage and cues after the simulation tick. Reads state only; presentation never feeds back.
func tick_readability() -> void:
	var feedback := tick_feedback
	tick_feedback = []
	var player: Vector3 = presenter.player.position
	var focus = null
	var focus_size := 1.0
	var others := []
	if combat != null:
		var target = combat.find_target(combat.target)
		if target != null:
			focus = target.body.position
			focus_size = enemy_scale(target)
		var nearest := INF
		for enemy in combat.enemies:
			if enemy.hp <= 0: continue
			others.append(enemy.body.position)
			var d: float = player.distance_to(enemy.body.position)
			if target == null and d < nearest:
				nearest = d
				focus = enemy.body.position
				focus_size = enemy_scale(enemy)
	var reduced := bool(presenter.actions.profile.options.get("reduced_motion", false)) if presenter.actions != null else false
	combat_camera.tick(player, focus, reduced, others, focus_size)
	stage.tick(combat, combat_camera.current())
	if stage.active or not stage.bursts.is_empty(): stage.effects(feedback, combat)
	var fb: Dictionary = stage.profile.get("feedback", {})
	var cues: Array = stage.cues.duplicate()
	var played := false
	for f in feedback + sfx_extra:
		if combat_sfx(f):
			played = true
			continue
		match str(f.get("kind", "")):
			"hurt":
				stage.edge_ticks = int(fb.get("edge_flash_ticks", 8))
				cues.append(str(fb.get("hurt_audio", "")))
			"hit": cues.append(str(fb.get("hit_audio", "")))
			"block", "armor", "deflect": cues.append("core.combat.block.metal")
			"defeated": cues.append(str(fb.get("defeat_audio", "")))
			"boss_defeated": cues.append(str(fb.get("boss_defeat_audio", "")))
			"phase": cues.append(str(fb.get("phase_audio", "")))
			"heal": cues.append(str(fb.get("heal_audio", "")))
			"cue": cues.append(str(f.get("id", "")))
	sfx_extra = []
	for id in cues:
		if id != "" and presenter.sounds.has_method("cue") and presenter.sounds.cue(id): played = true
	if not played and not feedback.is_empty(): presenter.sounds.trigger()
func refresh_markers() -> void:
	if is_instance_valid(markers): markers.free()
	markers = Node3D.new()
	presenter.room_root.add_child(markers)
	for c in runtime.modules.challenges.values():
		if c.room != runtime.state.location or runtime.state.modules.completed.has(c.id): continue
		var points := [anchor("challenge:start:"+c.id)]
		# Combat entry posts would stand inside the arena as clutter under the combat framing: hidden while any
		# fight runs in the room (they return with the next marker refresh after it).
		if c.kind == "combat" and runtime.state.modules.active != "" and combat_camera.active: points.clear()
		if c.kind == "course":
			for cp in runtime.modules.entities("course","tracks")[c.subject].checkpoints: points.append(vector(cp.position_m))
		for p in points:
			presenter.room_root.box(markers,"gate",Vector3(0.12,1.3,0.12),p+Vector3(-0.5,0.65,0),Color("b9a663"))
			presenter.room_root.box(markers,"gate",Vector3(0.12,1.3,0.12),p+Vector3(0.5,0.65,0),Color("b9a663"))
		# COMBAT lane boss gate (API 1.1.0): bars across the encounter's gate door until its challenge completes
		# (the door's own conditions keep it shut; the arena clamp locks the fight itself).
		if c.kind == "combat":
			var enc: Dictionary = runtime.modules.entities("combat", "encounters")[c.subject]
			if str(enc.get("gate", "")) != "": gate_bars(anchor("move:" + c.room + ":" + str(enc.gate)), runtime.state.modules.active == c.id)
	for region in runtime.modules.regions.values():
		if region.room != runtime.state.location: continue
		for mark in region.landmarks:
			presenter.room_root.box(markers,"landmark",Vector3(0.45,2.0,0.45),vector(mark.position_m)+Vector3.UP,Color("9e9866"))
## Five dark bars and a lintel across a door (closed gate); brighter rust while the fight is on.
func gate_bars(at: Vector3, locked: bool) -> void:
	if at == Vector3.INF: return
	var room_size: Array = runtime.rooms[runtime.state.location].grid_size
	# Bars run along the wall the door sits on (the nearer of the x/z room edges).
	var along_x: bool = minf(at.z, float(room_size[1]) - at.z) < minf(at.x, float(room_size[0]) - at.x)
	var col := Color("8a4a2c") if locked else Color("4a4f58")
	for i in 5:
		var off := (float(i) - 2.0) * 0.32
		var p := at + (Vector3(off, 0, 0) if along_x else Vector3(0, 0, off))
		presenter.room_root.box(markers, "boss_gate", Vector3(0.09, 1.9, 0.09), p + Vector3(0, 0.95, 0), col)
	presenter.room_root.box(markers, "boss_gate", Vector3(1.5, 0.12, 0.12) if along_x else Vector3(0.12, 0.12, 1.5), at + Vector3(0, 1.95, 0), col)
func capture_state() -> Dictionary:
	return preload("res://modules/movie_state.gd").capture(self)
func restore_state(value: Dictionary) -> void:
	preload("res://modules/movie_state.gd").restore(self,value)
func state_hash() -> String:
	var value := {"finite":runtime.state,"combat":combat.snapshot() if combat != null else null,"course":course.snapshot() if course != null else null,"retry":retry_ticks,"attempt":generation}
	if run.enabled: value["run"] = run.snapshot()
	if puzzle != null: value["puzzle"] = puzzle.snapshot()
	return JSON.stringify(value,"",true).sha256_text()
## Hold R inside a puzzle room resets the room (permanent facts kept) instead of reloading the checkpoint.
func claim_reset() -> bool:
	return puzzle != null and puzzle.claim_reset()
func owns_input() -> bool:
	return puzzle != null and puzzle.owns_input()
func _exit_tree() -> void:
	combat_camera.dispose()
	stage.dispose()
	clear_corpses()
	if combat != null:
		combat.on_release = Callable()
		combat.dispose()
	if not pending.is_empty() and is_instance_valid(pending.probe): pending.probe.free()
