extends SceneTree
## COMBAT lane assertions (gameplay API 1.1.0), run by tools/combat_godot.py on a confined runtime copy whose
## res://module-vectors.json holds the compiled city_arena_test game.
## walker_patrol_v1: patrol, spot, approach, telegraph = windup, one bump contact, push + hit-stop, hurt, knockback, death.
## brute_slam_v1: armoured until recover, slam disc + ring telegraph, ring expands at its speed, hits once, a roll
##   through it on i-frames passes, recovery is vulnerable, reward drop heals.
## hover_drone_v1: keeps its distance and strafes, telegraphs, fires a fixed-tick shot (speed, radius, damage once,
##   despawn), a roll passes through, a timed swing deflects it back into the drone.
## boss_phases_v1: thresholds, per-phase patterns, the phase beat, the defeat beat holding the clear, boss_defeated.
## Determinism of a scripted fight, mid-fight capture/restore (movie_state.capture_combat), the readability profile
## (resolution, clamps, N64 light caps) and the combat camera (0.5 s smoothstep blend, framing, reduced motion).
const Combat = preload("res://modules/combat/runtime.gd")
const Robot = preload("res://modules/combat/robot.gd")
const Telegraph = preload("res://modules/combat/telegraph.gd")
const Readability = preload("res://modules/combat/readability.gd")
const CombatCamera = preload("res://modules/combat/camera.gd")
const MovieState = preload("res://modules/movie_state.gd")
const Adapter = preload("res://modules/input_adapter.gd")
const Player = preload("res://view/player.gd")
const Rig = preload("res://look/rig.gd")
var world: Node3D
var player
var failures := []
var checks := 0
var game: Dictionary
var report := {}

class FakeView extends RefCounted:
	var camera: Camera3D
	var world: Node3D
	var room_root = null
	var player

func expect(value: bool, label: String) -> void:
	checks += 1
	if not value: failures.append(label)

func _initialize() -> void:
	call_deferred("run")

func kinds() -> Dictionary:
	var r = preload("res://core/runtime.gd").new()
	r.configure(game)
	return r.modules.entities("combat", "archetypes").duplicate(true)

## One-spawn encounter of `archetype` at `at` (wave 0); the player stands at `me`.
func fight(archetype: String, at: Vector3, me: Vector3, patch := {}, bystander := false) -> Combat:
	var all := kinds()
	for key in patch: all[archetype][key] = patch[key]
	var spawns := [{"id": archetype, "archetype": archetype, "position_m": [at.x, at.y, at.z], "wave": 0}]
	# A far, idle walker keeps the encounter open (the last robot's fall ends the fight and its drops).
	if bystander: spawns.append({"id": "zz_bystander", "archetype": "pitch_walker", "position_m": [15.0, 0.0, 15.0], "wave": 0})
	var enc := {"id": "test", "room": "forecourt", "arena": {"min": [0, 0, 0], "max": [16, 4, 16]},
		"spawns": spawns,
		"win": "all_spawns_defeated", "lose": "player_health_zero", "double_ko": "failure",
		"boss": archetype if str(all[archetype].fsm.template) == "boss_phases_v1" else "", "gate": ""}
	player.position = me
	player.rotation = Vector3.ZERO
	player.velocity = Vector3.ZERO
	player.facing_yaw = 0.0
	var c = Combat.new()
	c.begin(enc, all, player, world, 8, 11)
	return c

## One tick: inject, tick, apply the returned displacement to the player (tests have no character controller).
func step(c, input, buttons := [], move := Vector2.ZERO) -> Dictionary:
	input.inject(move, buttons)
	var out: Dictionary = c.tick(input)
	input.consume()
	player.position += out.impulse
	return out

func face(p: Vector3) -> void:
	var d: Vector3 = p - player.position
	player.facing_yaw = atan2(-d.x, -d.z)

func kinds_of(feedback: Array) -> Array:
	return feedback.map(func(f): return str(f.kind))

func walker() -> void:
	var c := fight("pitch_walker", Vector3(8, 0, 11.5), Vector3(8, 0.02, 8))
	await physics_frame
	var e = c.enemies[0]
	expect(e.template == "walker_patrol_v1" and e.kind == "bump" and e.mode == "patrol", "walker starts patrolling with a bump attack")
	var input = Adapter.new()
	var states := []
	var telegraph := 0
	var first_hurt := -1
	var hurts := 0
	var spot_seen := false
	for t in 200:
		var before: int = c.health
		step(c, input)
		if e.mode == "spot": spot_seen = true
		if states.is_empty() or states[-1] != e.state: states.append(e.state)
		if e.state == "telegraph": telegraph += 1
		if c.health < before:
			hurts += 1
			if first_hurt < 0:
				first_hurt = t
				expect(e.state == "attack", "walker damage lands in its attack state (%s)" % e.state)
				expect(c.push_ticks == Combat.PUSH_TICKS and c.hitstop == int(e.robot.hitstop_ticks), "a bump pushes the player and starts the robot's hit-stop")
	expect(spot_seen, "walker spots the player before approaching")
	expect(states.slice(0, 5) == ["idle", "approach", "telegraph", "attack", "recover"], "walker FSM idle > approach > telegraph > attack > recover (%s)" % str(states))
	expect(telegraph >= int(e.data.attack.windup_ticks), "walker telegraph lasts its windup (%d ticks)" % telegraph)
	expect(hurts >= 1 and first_hurt > 0, "walker bump lands")
	report["walker_states"] = states
	c.dispose()
	# Hurt + knockback + death on the player's swings.
	c = fight("pitch_walker", Vector3(8, 0, 7.0), Vector3(8, 0.02, 8))
	await physics_frame
	e = c.enemies[0]
	e.transition("approach")
	var start: Vector3 = e.body.position
	var hp0: int = e.hp
	var hit_tick := -1
	for t in 40:
		step(c, input, ["focus", "primary"] if t == 0 else ["focus"])
		if e.hp < hp0 and hit_tick < 0:
			hit_tick = t
			expect(e.state == "hurt" or e.state == "dead", "a landed hit staggers the walker")
	expect(hit_tick >= 0, "the player's swing hurts the walker")
	expect(e.body.position.distance_to(start) > 0.2 or e.hp == 0, "knockback moves the walker away")
	for t in 120:
		step(c, input, ["focus", "primary"] if t % 32 == 0 else ["focus"])
		if c.result != "": break
	expect(e.hp == 0 and e.state == "dead" and c.defeated.has("pitch_walker"), "the walker dies at zero health")
	expect(c.result == "completed", "the encounter completes when its only robot falls")
	c.dispose()

func brute() -> void:
	var c := fight("pivot_brute", Vector3(8, 0, 6.8), Vector3(8, 0.02, 8))
	await physics_frame
	var e = c.enemies[0]
	var input = Adapter.new()
	expect(e.armored(), "the brute is armoured outside recovery")
	# Armour: a swing while it approaches lands no damage.
	e.transition("approach")
	face(e.body.position)
	var hp0: int = e.hp
	var armour_seen := false
	for t in 20:
		step(c, input, ["focus", "primary"] if t == 0 else ["focus"])
		if "armor" in kinds_of(c.feedback): armour_seen = true
	expect(armour_seen and e.hp == hp0, "a swing on the armoured brute shows armour and does no damage")
	c.dispose()
	c = fight("pivot_brute", Vector3(8, 0, 10.6), Vector3(8, 0.02, 8))
	await physics_frame
	e = c.enemies[0]
	var disc := {}
	var contact_prev := -1
	var contact_steps := true
	var telegraph := 0
	var ring_seen := false
	var ring_hit := -1
	for t in 160:
		var before: int = c.health
		step(c, input, ["focus"])
		if e.state == "telegraph":
			telegraph += 1
			var info: Dictionary = Telegraph.info(e)
			if disc.is_empty(): disc = info
			if contact_prev >= 0 and int(info.contact_in) != contact_prev - 1: contact_steps = false
			contact_prev = int(info.contact_in)
		if not c.shockwaves.is_empty(): ring_seen = true
		if c.health < before and ring_hit < 0: ring_hit = t
		if e.state == "recover": break
	expect(telegraph == int(e.data.attack.windup_ticks), "brute slam telegraph lasts its windup (%d)" % telegraph)
	expect(disc.get("shape", "") == "disc" and is_equal_approx(float(disc.get("radius", 0)), 1.3) and is_equal_approx(float(disc.get("reach", 0)), 4.0), "slam telegraph: landing disc (1.3 m) with the ring's 4 m reach")
	expect(contact_steps, "slam contact countdown steps one tick at a time")
	expect(ring_seen, "the slam spawns a ground ring")
	# Ring physics: expands by speed/60 per tick and damages a grounded player once; a timed roll passes through.
	c.dispose()
	c = fight("pivot_brute", Vector3(2, 0, 2), Vector3(8, 0.02, 8))
	await physics_frame
	e = c.enemies[0]
	c.spawn_ring(e, Vector3(8, 0, 5.5), 5.0, 4.0, 0.5, 2)
	var w = c.shockwaves[0]
	var r0: float = w.radius
	step(c, input)
	expect(is_equal_approx(w.radius - r0, 5.0 / 60.0), "the ring grows 5 m/s on fixed ticks")
	var hits := 0
	for t in 60:
		var before: int = c.health
		step(c, input)
		if c.health < before: hits += 1
	expect(hits == 1 and c.health == 6, "a ring hits a standing player exactly once for its damage (hp %d)" % c.health)
	c.dispose()
	c = fight("pivot_brute", Vector3(2, 0, 2), Vector3(8, 0.02, 8))
	await physics_frame
	e = c.enemies[0]
	c.spawn_ring(e, Vector3(8, 0, 5.5), 5.0, 4.0, 0.5, 2)
	w = c.shockwaves[0]
	var rolled := false
	var hurt := false
	for t in 60:
		var buttons: Array = []
		if not rolled and w.glyph_open(player.position) and w.contact_in(player.position) <= 2:
			buttons = ["dodge"]
			rolled = true
		var before: int = c.health
		step(c, input, buttons, Vector2(0, -1) if buttons.size() > 0 else Vector2.ZERO)
		if c.health < before: hurt = true
	expect(rolled and not hurt, "rolling in the open window passes through the ring on i-frames")
	c.dispose()
	# Vulnerable recovery, reward drop and heal.
	c = fight("pivot_brute", Vector3(8, 0, 6.9), Vector3(8, 0.02, 8), {}, true)
	await physics_frame
	e = c.enemies[0]
	e.hp = 1
	e.transition("recover")
	face(e.body.position)
	c.health = 5
	for t in 30:
		step(c, input, ["focus", "primary"] if t == 0 else ["focus"])
		if e.hp == 0: break
	expect(e.hp == 0, "the brute takes damage while it recovers")
	expect(c.drops.size() == 1, "the brute leaves a reward drop")
	if c.drops.size() == 1:
		player.position = Vector3(c.drops[0].position.x, 0.02, c.drops[0].position.z)
		var healed := false
		for t in 10:
			step(c, input)
			if "heal" in kinds_of(c.feedback): healed = true
		expect(healed and c.health == 6, "walking over the drop heals (hp %d)" % c.health)
	c.dispose()

func drone() -> void:
	var c := fight("buzz_drone", Vector3(8, 0, 13), Vector3(8, 0.02, 8))
	await physics_frame
	var e = c.enemies[0]
	var input = Adapter.new()
	var shot = null
	var shot_tick := -1
	var telegraph := 0
	var distances := []
	for t in 260:
		step(c, input)
		distances.append(e.body.position.distance_to(player.position))
		if e.state == "telegraph": telegraph += 1
		if not c.projectiles.is_empty() and shot == null:
			shot = c.projectiles[0]
			shot_tick = t
			break
	expect(shot != null, "the drone fires a projectile")
	if shot == null: c.dispose(); return
	expect(telegraph == int(e.data.attack.windup_ticks), "drone telegraph lasts its windup (%d)" % telegraph)
	expect(absf(distances[-1] - float(e.data.hover.keep_distance_m)) <= 0.6, "the drone holds its keep distance (%.2f m)" % distances[-1])
	expect(is_equal_approx(shot.velocity.length(), 4.5 / 60.0) and is_equal_approx(shot.radius, 0.25), "shot speed 4.5 m/s, radius 0.25 m on fixed ticks")
	var lifetime := 0
	var hits := 0
	while not c.projectiles.is_empty() and lifetime < 400:
		var before: int = c.health
		step(c, input)
		if c.health < before: hits += 1
		lifetime += 1
	expect(hits == 1 and c.health == 7, "a shot that reaches a standing player hits once and is gone")
	c.dispose()
	# Despawn: a shot that misses expires at its lifetime or the arena edge.
	c = fight("buzz_drone", Vector3(2, 0, 2), Vector3(14, 0.02, 14))
	await physics_frame
	e = c.enemies[0]
	c.spawn_shot(e, Vector3(1, 0, 0), 1.0, 0.25, 1, 30, true, 0.6)
	var alive := 0
	while not c.projectiles.is_empty() and alive < 100:
		step(c, input)
		alive += 1
	expect(alive == 30, "a missing shot despawns at its lifetime (%d ticks)" % alive)
	c.dispose()
	# Roll through on i-frames.
	c = fight("buzz_drone", Vector3(8, 0, 13), Vector3(8, 0.02, 8))
	await physics_frame
	e = c.enemies[0]
	e.transition("recover")
	c.spawn_shot(e, Vector3(0, 0, -1), 4.5, 0.25, 1, 180, true, 0.6)
	shot = c.projectiles[0]
	var rolled := false
	var hurt := false
	for t in 120:
		var buttons: Array = []
		var ci: int = shot.contact_in(player.position)
		if not rolled and ci >= 0 and ci <= 3:
			buttons = ["dodge"]
			rolled = true
		var before: int = c.health
		step(c, input, buttons, Vector2(0, 1) if buttons.size() > 0 else Vector2.ZERO)
		if c.health < before: hurt = true
	expect(rolled and not hurt, "a roll carries the player through a shot on its i-frames")
	c.dispose()
	# Deflect: a swing whose hit window meets a deflectable shot in front sends it back into the drone.
	c = fight("buzz_drone", Vector3(8, 0, 12), Vector3(8, 0.02, 8))
	await physics_frame
	e = c.enemies[0]
	e.transition("recover")
	face(e.body.position)
	c.spawn_shot(e, Vector3(0, 0, -1), 4.5, 0.25, 1, 180, true, 0.6)
	shot = c.projectiles[0]
	var deflected := false
	var drone_hit := false
	var hp0: int = e.hp
	var swung := false
	for t in 140:
		var buttons: Array = ["focus"]
		var ci: int = shot.contact_in(player.position)
		if not swung and ci >= 0 and ci <= Combat.WINDUP + 2:
			buttons = ["focus", "primary"]
			swung = true
		step(c, input, buttons)
		var fb := kinds_of(c.feedback)
		if "deflect" in fb: deflected = true
		for f in c.feedback:
			if f.kind == "hit" and f.get("source", "") == "deflect": drone_hit = true
	expect(deflected, "a timed swing deflects the shot")
	expect(drone_hit and e.hp < hp0, "the deflected shot damages its drone")
	expect(c.health == 8, "a deflected shot never hurts the player")
	c.dispose()

func boss() -> void:
	var c := fight("chairbot", Vector3(8, 0, 11), Vector3(8, 0.02, 8))
	await physics_frame
	var e = c.enemies[0]
	var input = Adapter.new()
	var data: Dictionary = e.data
	expect(e.is_boss() and c.boss() == e, "the encounter's boss is live")
	expect(e.phase_marks() == [0.6, 0.3], "phase marks at 60%% and 30%% (%s)" % str(e.phase_marks()))
	# Patterns cycle within the phase.
	var seen := []
	for i in 4:
		seen.append(str(e.pattern().id))
		e.end_cycle()
	expect(seen == ["lunge", "memo", "lunge", "memo"], "phase 1 cycles its own patterns (%s)" % str(seen))
	e.pattern_index = 0
	# Thresholds: 12 hp -> phase 2 at 7, phase 3 at 3 (health * 1000 <= permille * max).
	var phases := []
	for i in 11:
		e.damage(1, player.position)
		phases.append(e.phase)
	expect(phases == [0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2], "boss phases change at the thresholds (%s)" % str(phases))
	expect(str(e.pattern().id) in data.boss.phases[2].patterns, "the last phase draws from its own pattern set")
	c.dispose()
	# Phase beat and defeat beat through real swings (in recover, so the armour is down).
	c = fight("chairbot", Vector3(8, 0, 6.9), Vector3(8, 0.02, 8))
	await physics_frame
	e = c.enemies[0]
	face(e.body.position)
	e.hp = 8
	e.transition("recover")
	var phase_fb := false
	for t in 30:
		step(c, input, ["focus", "primary"] if t == 0 else ["focus"])
		if "phase" in kinds_of(c.feedback):
			phase_fb = true
			expect(c.hitstop >= 3, "a phase change holds a short hit-stop")
	expect(phase_fb and e.phase == 1, "crossing 60 percent plays the phase beat")
	for t in 40:
		if c.age < 0 and c.hitstop == 0 and c.hurt_age < 0: break
		step(c, input, ["focus"])
	e.hp = 1
	e.transition("recover")
	e.body.position = Vector3(8, 0, 6.9)
	face(e.body.position)
	var defeated_tick := -1
	var completed_tick := -1
	var boss_fb := false
	for t in 60:
		step(c, input, ["focus", "primary"] if t == 0 else ["focus"])
		if "boss_defeated" in kinds_of(c.feedback):
			boss_fb = true
			defeated_tick = t
			expect(c.hitstop == int(data.boss.defeat_hitstop_ticks), "the defeat beat holds %d ticks" % int(data.boss.defeat_hitstop_ticks))
			expect(c.result == "", "the clear waits for the defeat beat")
		if c.result == "completed" and completed_tick < 0: completed_tick = t
	expect(boss_fb, "the boss's defeat raises boss_defeated")
	expect(completed_tick - defeated_tick == int(data.boss.defeat_hitstop_ticks), "the encounter clears when the defeat beat ends (%d ticks)" % (completed_tick - defeated_tick))
	c.dispose()
	# A phase without patterns never attacks (the checker's combat_stall rule rejects such a boss).
	var all := kinds()
	all.chairbot.boss.phases[0].patterns = []
	c = fight("chairbot", Vector3(8, 0, 11), Vector3(8, 0.02, 8), {"boss": all.chairbot.boss})
	await physics_frame
	e = c.enemies[0]
	var attacked := false
	for t in 300:
		step(c, input)
		if e.state == "telegraph" or e.state == "attack": attacked = true
	expect(not attacked, "a phase with no patterns never telegraphs or attacks")
	c.dispose()

## A scripted boss fight: the player rolls on open windows and swings while the boss recovers.
func scripted(c, ticks: int, capture_at := -1) -> Dictionary:
	var input = Adapter.new()
	var hashes := []
	var captured := {}
	var at := []
	for t in ticks:
		var e = c.find_target(c.encounter.boss)
		var buttons: Array = ["focus"]
		var move := Vector2.ZERO
		if e != null:
			var info: Dictionary = Telegraph.info(e)
			if info.get("open", false) and c.roll_age < 0 and c.age < 0: buttons.append("dodge"); move = Vector2(1, 0)
			elif e.state == "recover" and e.body.position.distance_to(player.position) <= Combat.REACH: face(e.body.position); buttons.append("primary")
			elif e.state == "recover": move = Vector2(0, -1)
		step(c, input, buttons, move)
		hashes.append(hash(JSON.stringify(c.snapshot())))
		at.append([player.position.x, player.position.y, player.position.z, player.facing_yaw])
		if t == capture_at:
			captured = {"combat": JSON.parse_string(JSON.stringify(MovieState.capture_combat(c))), "player": at[-1]}
		if c.result != "": break
	return {"hashes": hashes, "captured": captured, "at": at}

func determinism_and_restore() -> void:
	var a := fight("chairbot", Vector3(8, 0, 11), Vector3(8, 0.02, 8))
	await physics_frame
	var first := scripted(a, 900, 400)
	a.dispose()
	await physics_frame
	var b := fight("chairbot", Vector3(8, 0, 11), Vector3(8, 0.02, 8))
	await physics_frame
	var second := scripted(b, 900)
	b.dispose()
	expect(first.hashes.size() > 450 and first.hashes == second.hashes, "two runs of a scripted boss fight hash identically (%d ticks)" % first.hashes.size())
	report["boss_script_ticks"] = first.hashes.size()
	# Mid-fight capture (JSON round trip, as a movie checkpoint) restored into a fresh fight continues identically.
	await physics_frame
	var r := fight("chairbot", Vector3(8, 0, 11), Vector3(8, 0.02, 8))
	await physics_frame
	var cap: Dictionary = first.captured
	expect(not cap.is_empty(), "captured the fight at tick 400")
	if cap.is_empty(): r.dispose(); return
	MovieState.restore_combat(r, cap.combat)
	player.position = Vector3(cap.player[0], cap.player[1], cap.player[2])
	player.facing_yaw = float(cap.player[3])
	expect(hash(JSON.stringify(r.snapshot())) == first.hashes[400], "the restored fight equals the captured tick")
	var rest := scripted(r, first.hashes.size() - 401)
	r.dispose()
	expect(rest.hashes == first.hashes.slice(401), "the restored fight continues tick-for-tick (%d ticks)" % rest.hashes.size())
	report["restore_ticks"] = rest.hashes.size()

func profile() -> void:
	var d := Readability.defaults()
	var p := Readability.resolve({}, {})
	expect(p.camera.distance_m == d.camera.distance_m and p.camera.blend_ticks == 30, "defaults resolve unchanged (0.5 s blend)")
	p = Readability.resolve({"combat": {"camera": {"distance_m": 100.0, "pitch_deg": 20.0}}}, {"combat": {"camera": {"pitch_deg": 45.0}}})
	expect(is_equal_approx(float(p.camera.distance_m), 12.0), "pack overrides are clamped to the profile ranges")
	expect(is_equal_approx(float(p.camera.pitch_deg), 45.0), "a room (region) override wins over the pack")
	p = Readability.resolve({"combat": {"light": {"kicker": ["#ffffff", 1.0], "pool": {"strength": 1.0}}}}, {})
	var lighting: Dictionary = Rig.lighting()
	if lighting.has("actor"): expect(float(p.light.kicker[1]) <= float(lighting.actor.kicker_max) + 0.0001, "the kicker never exceeds lighting.actor.kicker_max")
	if lighting.has("lamp_pool"): expect(float(p.light.pool.strength) <= float(lighting.lamp_pool.max_strength) + 0.0001, "the floor pool never exceeds lamp_pool.max_strength")
	expect(int(d.camera.reduced_motion.blend_ticks) == 0 and float(d.camera.reduced_motion.lean_deg) == 0.0, "reduced motion cuts and never leans")
	# Telegraph windows: the glyph opens only when a roll's i-frames cover the whole contact.
	expect(Telegraph.dodge_open(3, 7) and not Telegraph.dodge_open(9, 7) and Telegraph.dodge_open(0, 15) and not Telegraph.dodge_open(-1, 1), "dodge window = contact inside the roll's i-frames")

func camera_profile() -> void:
	var view := FakeView.new()
	view.world = world
	view.player = player
	var authored := Camera3D.new()
	world.add_child(authored)
	authored.global_transform = Transform3D(Basis.looking_at(Vector3(8, 1, 8) - Vector3(8, 6, -4), Vector3.UP), Vector3(8, 6, -4))
	authored.fov = 60.0
	authored.current = true
	view.camera = authored
	var before: Transform3D = authored.global_transform
	var cam := CombatCamera.new()
	cam.attach(view)
	cam.configure(Readability.resolve({}, {}))
	player.position = Vector3(8, 0.02, 8)
	var focus := Vector3(8, 0, 10)
	cam.start()
	var weights := []
	for t in 30:
		cam.tick(player.position, focus, false, [focus])
		weights.append(snappedf(cam.weight, 0.0001))
	expect(weights[0] > 0.0 and weights[14] < 1.0 and is_equal_approx(weights[29], 1.0), "the combat view blends in over 30 ticks (0.5 s)")
	var c: Camera3D = cam.current()
	expect(c != authored and c.current, "the combat camera draws while blended")
	var near: float = c.global_position.distance_to(player.position)
	var far: float = authored.global_position.distance_to(player.position)
	expect(near < far * 0.55, "the combat framing is closer (%.2f m vs %.2f m)" % [near, far])
	expect(c.is_position_in_frustum(player.position + Vector3.UP) and c.is_position_in_frustum(focus + Vector3.UP), "player and focus stay in frame")
	expect(absf(c.global_transform.basis.x.y) < 0.001, "no camera roll")
	expect(authored.global_transform.is_equal_approx(before), "the authored camera is never moved")
	expect(c.global_position.y > player.position.y + 1.5 and c.global_position.z < player.position.z, "the view sits behind and above the player")
	report["camera"] = cam.last
	expect(absf(float(cam.last.lean_deg)) > 6.0 and float(cam.last.lift_deg) > 6.0, "a target lined up beyond the player leans and lifts the view (%.1f / %.1f deg)" % [float(cam.last.lean_deg), float(cam.last.lift_deg)])
	cam.stop()
	for t in 30: cam.tick(player.position, focus, false, [focus])
	expect(cam.weight == 0.0 and authored.current, "after the fight the view blends back to the authored camera")
	# A big robot standing between the camera and the player: the lean and lift spread the two apart on screen
	# compared with a flat framing (lean and lift off) of the same moment.
	var front := Vector3(8.3, 0, 6.2)
	var flat_profile: Dictionary = Readability.resolve({}, {}).duplicate(true)
	flat_profile.camera.lean_deg = 0.0
	flat_profile.camera.overlap_pitch_deg = 0.0
	var seps := []
	for p in [Readability.resolve({}, {}), flat_profile]:
		var cm := CombatCamera.new()
		cm.attach(view)
		cm.configure(p)
		cm.start()
		for t in 60: cm.tick(player.position, front, false, [front], 1.9)
		var cc: Camera3D = cm.current()
		seps.append(cc.unproject_position(player.position + Vector3.UP * 0.9).distance_to(cc.unproject_position(front + Vector3.UP * 1.2)))
		report["camera_front_%d" % seps.size()] = cm.last
		cm.reset()
	expect(seps[0] > seps[1] * 1.15, "a robot in front of the player is spread apart on screen (%.0f px vs %.0f px flat)" % [seps[0], seps[1]])
	# Reduced motion: a cut, no lean, no lift.
	var reduced := CombatCamera.new()
	reduced.attach(view)
	reduced.configure(Readability.resolve({}, {}))
	reduced.start()
	reduced.tick(player.position, Vector3(8.2, 0, 10), true, [])
	expect(reduced.weight == 1.0 and float(reduced.last.lean_deg) == 0.0 and float(reduced.last.lift_deg) == 0.0, "reduced motion cuts in at once with no lean or lift")
	reduced.reset()
	cam.reset()
	authored.free()

func run() -> void:
	game = preload("res://core/wire.gd").read_json("res://module-vectors.json")[0].game
	world = Node3D.new()
	root.add_child(world)
	player = Player.new()
	world.add_child(player)
	player.set_physics_process(false)
	var floor := StaticBody3D.new()
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(16, 0.2, 16)
	shape.shape = box
	floor.add_child(shape)
	world.add_child(floor)
	floor.position = Vector3(8, -0.1, 8)
	await physics_frame
	await walker()
	await brute()
	await drone()
	await boss()
	await determinism_and_restore()
	profile()
	camera_profile()
	world.free()
	var out := ""
	var args := OS.get_cmdline_user_args()
	var i := args.find("--report")
	if i >= 0 and i + 1 < args.size(): out = args[i + 1]
	if out != "":
		var file := FileAccess.open(out, FileAccess.WRITE)
		expect(file != null, "report file writable: " + out)
		if file != null:
			file.store_string(JSON.stringify({"checks": checks, "failures": failures, "report": report}, "  ", true))
			file.close()
	print("COMBAT_ROBOTS checks=%d failures=%d" % [checks, failures.size()])
	for f in failures: print("FAIL ", f)
	quit(0 if failures.is_empty() else 1)
