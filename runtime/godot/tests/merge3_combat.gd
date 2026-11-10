extends SceneTree
## MERGE3 combat-clip acceptance. Run by tools/merge3_combat.py on a confined copy of the runtime with
## the imported combat art staged (res://combat.json, res://bindings.json with real cast paths).
## A: every tick of the phase maps: hit window <=> swing keys 5-7, i-frames <=> roll keys 2-9.
## B: real combat ticks: damage lands only while the swing shows keys 5-7; no damage while the roll
##    shows keys 2-9 and contact lands again once they end; enemies show their whole telegraph before
##    the attack and their contact lands only on attack hit-window keys.
## C: the real GLBs: every clip key the host asks for is the key on the skeleton (incl. key 15 of a
##    looping-mode clip), the staff rides hand_r with the documented grip, stance props hide/return.
const Combat = preload("res://modules/combat/runtime.gd")
const Phases = preload("res://modules/combat/clip_phases.gd")
const Adapter = preload("res://modules/input_adapter.gd")
const Player = preload("res://view/player.gd")
const AnimationState = preload("res://modules/animation_state.gd")
const Actor = preload("res://actors/character.gd")
var world: Node3D
var player
var failures := []
var checks := 0
var game: Dictionary
var art: Dictionary
var report := {}
func expect(value: bool, label: String) -> void:
	checks += 1
	if not value: failures.append(label)
func _initialize() -> void:
	call_deferred("run")
func in_range(key: int, span: Array) -> bool:
	return key >= int(span[0]) and key <= int(span[1])

func phase_maps() -> void:
	var meta: Dictionary = art.get("clips", {})
	var hit: Array = meta.get("swing", {}).get("hit_window", {}).get("frames", [])
	expect(hit == [5, 7], "swing hit window frames are 5-7 in the imported metadata")
	var last := 0
	var shown := []
	for t in Combat.WINDUP + Combat.ACTIVE + Combat.RECOVERY:
		var key: int = Phases.swing_key(t, meta)
		shown.append(key)
		expect(Combat.window(t, Combat.WINDUP, Combat.ACTIVE) == in_range(key, [5, 7]), "swing tick %d: window <=> keys 5-7 (key %d)" % [t, key])
		expect(key >= last, "swing keys never step back at tick %d" % t)
		last = key
	report["swing_keys_by_tick"] = shown
	var iframes: Array = meta.get("roll", {}).get("iframes", [])
	expect(iframes == [2, 9], "roll i-frames are keys 2-9 in the imported metadata")
	last = 0
	shown = []
	for t in Combat.ROLL_TICKS:
		var key: int = Phases.roll_key(t, meta)
		shown.append(key)
		expect(Combat.iframe(t) == in_range(key, [2, 9]), "roll tick %d: invulnerable <=> keys 2-9 (key %d)" % [t, key])
		expect(key >= last, "roll keys never step back at tick %d" % t)
		last = key
	report["roll_keys_by_tick"] = shown
	shown = []
	for t in Combat.HURT_TICKS: shown.append(Phases.hurt_key(t))
	expect(shown[0] == 1 and shown[-1] == 15, "hurt shows impact key 1 through key 15 over the hurt ticks")
	report["hurt_keys_by_tick"] = shown
	expect(Phases.block_key(0, meta) == 1 and Phases.block_key(2, meta) == 3 and Phases.block_key(600, meta) == 15, "block raises 1-2 then guards 3-15 and holds 15")
	expect(Phases.realtime_key(0) == 0 and Phases.realtime_key(59) == 14 and Phases.realtime_key(60) == 15 and Phases.realtime_key(900) == 15, "death plays at 15 fps and holds key 15")
	expect(Phases.loop_key(56) == 14 and Phases.loop_key(60) == 0, "idle_combat loops keys 0-14")
	for row in art.get("enemies", {}).values():
		for numbers in [[8, 4, 12], [36, 8, 36], [42, 12, 44]]:
			var data := {"attack":{"windup_ticks":numbers[0], "active_ticks":numbers[1], "recovery_ticks":numbers[2]}}
			var window: Array = Phases.enemy_hit(row)
			var keys := []
			for age in range(1, numbers[0] + 1): keys.append(Phases.enemy_pose(row, data, "telegraph", age)[1])
			var peak: int = row.phases.telegraph.get("telegraph_peak_frame", 1)
			expect(keys[0] == 1 and keys.max() >= peak and keys.max() >= int(row.phases.telegraph.hold_frames[0]), "%s telegraph over %d ticks reaches the peak and hold keys" % [row.id, numbers[0]])
			var attack := []
			for age in range(1, numbers[1] + 1): attack.append(Phases.enemy_pose(row, data, "attack", age)[1])
			# Every attack tick shows a hit-window key; with at least one tick per key the whole window plays.
			var whole: bool = numbers[1] < window[1] - window[0] + 1 or attack[-1] == window[1]
			expect(attack.all(func(k): return in_range(k, window)) and attack[0] == window[0] and whole, "%s attack ticks show only hit-window keys %s (%s)" % [row.id, str(window), str(attack)])
			expect(Phases.enemy_pose(row, data, "telegraph", 1)[0] == row.fsm_state_clip.telegraph and Phases.enemy_pose(row, data, "attack", 1)[0] == row.fsm_state_clip.attack, "%s FSM states pick the documented clips" % row.id)

## One-spawn encounter from the combat fixture; `patch` overrides archetype numbers for every kind.
func fixture(patch: Dictionary, spawn_at: Vector3, archetype := "") -> Combat:
	var r = preload("res://core/runtime.gd").new()
	r.configure(game)
	var combat = Combat.new()
	var enc: Dictionary = r.modules.entities("combat","encounters").values()[0].duplicate(true)
	var spawn: Dictionary = enc.spawns[0]
	for row in enc.spawns:
		if row.archetype == archetype: spawn = row
	enc.spawns = [spawn]
	enc.spawns[0].position_m = [spawn_at.x, spawn_at.y, spawn_at.z]
	var kinds: Dictionary = r.modules.entities("combat","archetypes").duplicate(true)
	for e in kinds.values():
		for key in ["windup_ticks", "active_ticks", "recovery_ticks"]:
			if patch.has(key): e.attack[key] = patch[key]
		if patch.has("max_health"): e.max_health = patch.max_health
	player.position = Vector3(8,0.02,8)
	player.rotation = Vector3.ZERO
	player.velocity = Vector3.ZERO
	combat.begin(enc, kinds, player, world, 6, 7)
	return combat

func swing_hits() -> void:
	var meta: Dictionary = art.get("clips", {})
	var combat := fixture({"windup_ticks":6000, "max_health":50}, Vector3(8,0,6.6))
	await physics_frame
	var input = Adapter.new()
	var hits := []
	var swings := 0
	for tick in 320:
		var press: bool = tick % 32 == 0
		input.inject(Vector2.ZERO, ["focus", "primary"] if press else ["focus"])
		var before: int = combat.enemies[0].hp
		combat.tick(input)
		input.consume()
		if press: swings += 1
		if combat.enemies[0].hp < before:
			var key: int = Phases.swing_key(combat.shown_swing, meta)
			hits.append({"tick":tick, "swing_age":combat.shown_swing, "key":key})
			expect(in_range(key, [5, 7]), "damage landed on swing key %d (tick %d)" % [key, tick])
	expect(hits.size() == swings, "every swing lands exactly once inside its window (%d hits, %d swings)" % [hits.size(), swings])
	report["swing_hits"] = hits
	combat.dispose()

func roll_iframes() -> void:
	var meta: Dictionary = art.get("clips", {})
	# The enemy's attack window outlasts the roll's i-frames: contact must wait for the roll to leave keys 2-9.
	var combat := fixture({"active_ticks":40, "max_health":50}, Vector3(8,0.02,7), "reed_warden")
	await physics_frame
	combat.enemies[0].latched = player.position
	combat.enemies[0].transition("attack")
	var input = Adapter.new()
	var rows := []
	var first_damage := -1
	for tick in 30:
		input.inject(Vector2.ZERO, ["dodge", "focus"] if tick == 0 else ["focus"])
		var before: int = combat.health
		combat.tick(input)
		input.consume()
		var key: int = Phases.roll_key(combat.shown_roll, meta) if combat.shown_roll >= 0 else -1
		rows.append({"tick":tick, "roll_age":combat.shown_roll, "roll_key":key, "health":combat.health})
		if combat.health < before:
			expect(not in_range(key, [2, 9]), "damage taken while the roll shows i-frame key %d" % key)
			if first_damage < 0: first_damage = tick
	expect(first_damage == Combat.ROLL_IFRAMES, "contact lands on the first tick after the i-frame keys (tick %d)" % first_damage)
	report["roll_contact"] = rows
	combat.dispose()

func telegraph_attack(id: String, numbers: Array) -> void:
	var combat := fixture({"windup_ticks":numbers[0], "active_ticks":numbers[1], "recovery_ticks":numbers[2], "max_health":50}, Vector3(8,0.02,5.2), id)
	await physics_frame
	var enemy = combat.enemies[0]
	var row: Dictionary = art.get("enemies", {}).get(enemy.data.id, {})
	expect(enemy.data.id == id and not row.is_empty(), "combat art row for " + id)
	if row.is_empty(): combat.dispose(); return
	var window: Array = Phases.enemy_hit(row)
	var input = Adapter.new()
	var telegraph := 0
	var telegraphs := []
	var contacts := []
	var peak := 0
	for tick in 260:
		# A knocked-out player ends the encounter; the frozen FSM is not a new attack.
		if combat.result != "": break
		input.inject(Vector2.ZERO, [])
		var before: int = combat.health
		combat.tick(input)
		input.consume()
		var shown: Array = Phases.enemy_pose(row, enemy.data, enemy.state, enemy.age)
		if enemy.state == "telegraph":
			telegraph += 1
			peak = maxi(peak, shown[1])
			expect(shown[0] == row.fsm_state_clip.telegraph, "telegraph state shows the telegraph clip")
		elif enemy.state == "attack" and enemy.age == 1:
			telegraphs.append({"tick":tick, "telegraph_ticks":telegraph, "max_key":peak})
			expect(telegraph == numbers[0], "%s showed its telegraph for the whole %d-tick windup (%d)" % [id, numbers[0], telegraph])
			expect(peak >= int(row.phases.telegraph.get("telegraph_peak_frame", 1)), "%s reached its telegraph peak key before attacking" % id)
		if enemy.state != "telegraph":
			telegraph = 0
			peak = 0
		if combat.health < before:
			contacts.append({"tick":tick, "state":enemy.state, "clip":shown[0], "key":shown[1]})
			expect(enemy.state == "attack" and shown[0] == row.fsm_state_clip.attack and in_range(shown[1], window), "%s damage on %s key %d (window %s)" % [id, shown[0], shown[1], str(window)])
	expect(not telegraphs.is_empty() and not contacts.is_empty(), "%s telegraphed and attacked within the run" % id)
	report["telegraph_%s_%d" % [id, numbers[0]]] = {"telegraphs":telegraphs, "contacts":contacts, "window":window, "numbers":numbers}
	combat.dispose()

func load_actor(path: String, row: Dictionary) -> Node3D:
	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	if doc.append_from_file(path, state) != OK: return null
	var model = doc.generate_scene(state)
	var actor := Actor.new()
	actor.configure(model, row)
	world.add_child(actor)
	return actor
## Every rotation track of the clip: the skeleton holds the value of the key at k/15 s.
func key_mismatches(actor, clip: String, key: int) -> Array:
	var anim: Animation = actor.animation.get_animation(clip)
	var bad := []
	var compared := 0
	for i in anim.get_track_count():
		if anim.track_get_type(i) != Animation.TYPE_ROTATION_3D: continue
		var bone := String(anim.track_get_path(i)).get_slice(":", 1)
		var index: int = actor.skeleton.find_bone(bone)
		if index < 0: continue
		compared += 1
		var expected: Quaternion = anim.track_get_key_value(i, anim.track_find_key(i, float(key) / 15.0))
		var actual: Quaternion = actor.skeleton.get_bone_pose_rotation(index)
		if not actual.is_equal_approx(expected) and not actual.is_equal_approx(-expected): bad.append("%s:%d:%s" % [clip, key, bone])
	if compared == 0: bad.append("%s: no rotation tracks compared" % clip)
	return bad
func changed_bones(actor, clip: String, a: int, b: int) -> int:
	var anim: Animation = actor.animation.get_animation(clip)
	var count := 0
	for i in anim.get_track_count():
		if anim.track_get_type(i) != Animation.TYPE_ROTATION_3D: continue
		var qa: Quaternion = anim.track_get_key_value(i, anim.track_find_key(i, float(a) / 15.0))
		var qb: Quaternion = anim.track_get_key_value(i, anim.track_find_key(i, float(b) / 15.0))
		if not qa.is_equal_approx(qb) and not qa.is_equal_approx(-qb): count += 1
	return count
func user_arg(name: String, fallback := "") -> String:
	var args := OS.get_cmdline_user_args()
	var at := args.find(name)
	return args[at + 1] if at >= 0 and at + 1 < args.size() else fallback
func real_clips() -> void:
	var bindings: Dictionary = preload("res://core/wire.gd").read_json("res://bindings.json")
	var rows: Array = bindings.characters.filter(func(r): return art.get("grips", {}).has(r.character_id))
	expect(not rows.is_empty(), "staged bindings include combatants")
	if rows.is_empty(): return
	var row: Dictionary = rows[0]
	var wanted := user_arg("--character", "fv_scribe")
	for candidate in rows:
		if candidate.character_id == wanted: row = candidate
	expect(row.character_id == wanted, "requested combatant %s is bound" % wanted)
	var actor = load_actor(row.path, {"character_id":row.character_id, "source_rig":row.source_rig, "ground_offset":0.0})
	expect(actor != null, "combatant GLB loads")
	if actor == null: return
	var state = AnimationState.new()
	state.bind(actor)
	expect(not state.placeholder and state.missing.is_empty(), "all six combat clips bound on %s (missing %s)" % [row.character_id, str(state.missing)])
	var mismatched := []
	for clip in AnimationState.REQUIRED:
		for key in 16:
			state.show(clip, key)
			mismatched.append_array(key_mismatches(actor, clip, key))
	expect(mismatched.is_empty(), "every shown key is the key on the skeleton (mismatched %s)" % str(mismatched.slice(0, 8)))
	var moved := changed_bones(actor, "death", 0, 15)
	expect(moved > 0, "death key 15 differs from key 0 (%d bones), so the key-15 check above is not vacuous" % moved)
	report["key_checks"] = {"character":row.character_id, "clips":AnimationState.REQUIRED, "keys":16, "death_key15_bones_changed":moved}
	var grip: Dictionary = art.grips[row.character_id]
	var weapon: Dictionary = art.get("weapons", {}).get(grip.pack, {})
	expect(not weapon.is_empty(), "weapon staged for pack " + grip.pack)
	var props: Array = actor.find_children("kit_acc_hand_*", "Node3D", true, false)
	var expects_prop: bool = row.get("prop_triangles", {}).keys().any(func(k): return String(k).begins_with("kit_acc_hand_"))
	expect(not expects_prop or not props.is_empty(), "stance hand props found on %s (%d)" % [row.character_id, props.size()])
	if not weapon.is_empty():
		var doc := GLTFDocument.new()
		var gstate := GLTFState.new()
		expect(doc.append_from_file(weapon.path, gstate) == OK, "staff GLB loads")
		var staff = doc.generate_scene(gstate)
		expect(state.attach_weapon(staff, grip, weapon.rotation_xyzw), "staff attaches")
		var holder = staff.get_parent()
		expect(holder is BoneAttachment3D and holder.bone_name == "hand_r", "staff rides a hand_r BoneAttachment3D")
		var t: Array = grip.translation
		var r: Array = weapon.rotation_xyzw
		expect(staff.transform.origin.is_equal_approx(Vector3(t[0], t[1], t[2])) and staff.transform.basis.get_rotation_quaternion().is_equal_approx(Quaternion(r[0], r[1], r[2], r[3]).normalized()), "staff uses the documented grip transform")
		expect(staff.find_child("kit_acc_hand_r_trail_staff", true, false) != null, "staff mesh node present")
		expect(props.all(func(p): return not p.visible), "stance props hidden while the staff is held (%d)" % props.size())
		report["grip"] = {"character":row.character_id, "translation":t, "rotation_xyzw":r, "stance_props_hidden":props.size()}
		state.release()
		expect(props.all(func(p): return is_instance_valid(p) and p.visible), "stance props return after combat")
		expect(actor.skeleton.find_child("combat_weapon", false, false) == null, "staff removed after combat")
	actor.free()
	var enemy_checks := {}
	for enemy_row in art.get("enemies", {}).values():
		var enemy = load_actor(enemy_row.path, {"character_id":enemy_row.id, "source_rig":enemy_row.rig, "ground_offset":0.0})
		expect(enemy != null, "enemy GLB loads: " + enemy_row.id)
		if enemy == null: continue
		var es = AnimationState.new()
		es.bind(enemy, enemy_row.clips)
		expect(not es.placeholder, "enemy clips bound: " + enemy_row.id)
		var bad := []
		for clip in enemy_row.clips:
			for key in 16:
				es.show(clip, key)
				bad.append_array(key_mismatches(enemy, clip, key))
		expect(bad.is_empty(), "%s every key on the skeleton (bad %s)" % [enemy_row.id, str(bad.slice(0, 6))])
		enemy_checks[enemy_row.id] = {"clips":enemy_row.clips.size(), "telegraph_key4_vs_0_bones":changed_bones(enemy, "telegraph", 0, 4)}
		enemy.free()
	report["enemy_key_checks"] = enemy_checks

func run() -> void:
	game = preload("res://core/wire.gd").read_json("res://module-vectors.json")[0].game
	art = preload("res://core/wire.gd").read_json("res://combat.json") if FileAccess.file_exists("res://combat.json") else {}
	expect(not art.is_empty(), "combat art staged (res://combat.json)")
	world = Node3D.new()
	root.add_child(world)
	player = Player.new()
	world.add_child(player)
	player.set_physics_process(false)
	var floor := StaticBody3D.new()
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(16,0.2,16)
	shape.shape = box
	floor.add_child(shape)
	world.add_child(floor)
	floor.position = Vector3(8,-0.1,8)
	await physics_frame
	if not art.is_empty():
		phase_maps()
		await swing_hits()
		await roll_iframes()
		for id in art.get("enemies", {}):
			await telegraph_attack(id, [36, 8, 36])
			await telegraph_attack(id, [8, 4, 12])
		real_clips()
	world.free()
	var out := user_arg("--report")
	if out != "":
		var file := FileAccess.open(out, FileAccess.WRITE)
		expect(file != null, "report file writable: " + out)
		if file != null:
			file.store_string(JSON.stringify({"checks":checks, "failures":failures, "report":report}, "  ", true))
			file.close()
	print("MERGE3_COMBAT checks=%d failures=%d" % [checks, failures.size()])
	for f in failures: print("FAIL ", f)
	quit(0 if failures.is_empty() else 1)
