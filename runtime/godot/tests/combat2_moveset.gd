extends SceneTree
const Combat = preload("res://modules/combat/runtime.gd")
const Adapter = preload("res://modules/input_adapter.gd")
const Player = preload("res://view/player.gd")
const Saved = preload("res://modules/movie_state.gd")
var world: Node3D
var player
var checks := 0
var failures := []
var facts := {}
func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok: failures.append(label)
func _initialize() -> void: call_deferred("run")
func fight(modern := true, armor := false):
	var game: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://module-vectors.json"))[0].game
	var r = preload("res://core/runtime.gd").new(); r.configure(game)
	var kinds: Dictionary = r.modules.entities("combat", "archetypes").duplicate(true)
	var row: Dictionary = kinds.pitch_walker
	row.max_health = 40; row.robot.armor = "until_recover" if armor else "none"
	row.robot.knockback_m = 0; row.robot.hitstop_ticks = 0
	row.attack.recovery_ticks = 600
	player.position = Vector3(8, 0, 8); player.facing_yaw = 0; player.actual_velocity = Vector3.ZERO
	var enc := {"id":"test", "arena":{"min":[0,0,0],"max":[30,4,30]}, "spawns":[{"id":"target", "archetype":"pitch_walker", "position_m":[8,0,6.6], "wave":0}]}
	var c = Combat.new()
	c.begin(enc, kinds, player, world, 3, 11)
	# Property assignment is deliberate: baseline must reach real old behavior, not an absent API error.
	if c.get("profile") != null: c.profile = "combat2_v1"
	if not modern and c.get("profile") != null: c.profile = "legacy"
	if c.get("moveset") != null: c.moveset = "brawler_v1"
	c.enemies[0].transition("recover")
	return c
func step(c, a, buttons := []):
	a.inject(Vector2.ZERO, buttons)
	var out: Dictionary = c.tick(a); a.consume()
	player.position += out.impulse
	return out
func moves() -> void:
	var c = fight(); var a = Adapter.new(); var hits := []; var move_names := []
	for t in 80:
		var buttons := ["primary"] if t in [0, 12, 35] else []
		step(c, a, buttons)
		for f in c.feedback:
			if f.kind == "hit": hits.append(t)
			if f.kind == "move": move_names.append(f.move)
	expect(move_names == ["jab","cross","finisher"], "recovery presses chain jab/cross/finisher with mandatory recovery")
	expect(hits.size() == 3, "chain deals three discrete hits")
	facts.chain_hits = hits; facts.moves = move_names
	c.dispose()
	c = fight(true, true); a = Adapter.new()
	# Armoured outside recover: jab glances, charge must break it.
	c.enemies[0].transition("idle"); c.enemies[0].data.aggro_range_m = 0.1
	var charge_hits := 0
	for t in 65:
		step(c, a, ["primary"] if t < 28 else [])
		for f in c.feedback:
			if f.kind == "hit": charge_hits += 1
	expect(c.enemies[0].hp == 38 and charge_hits == 1, "release after 24 held ticks deals 2 and bypasses armour")
	c.dispose()
	c = fight(); a = Adapter.new(); player.actual_velocity = Vector3(0,0,-3)
	var at: Vector3 = player.position
	step(c, a, ["primary","run"])
	expect(c.get("move_kind") == "running", "primary while running above 2m/s chooses running strike")
	for t in 40: step(c, a)
	expect(absf(player.position.distance_to(at) - 2.2) < 0.01, "running strike displacement is 2.2m")
	c.dispose()
func timing_restore() -> void:
	var c = fight(); var a = Adapter.new()
	for t in 13: step(c, a, ["primary"] if t == 0 else [])
	var data: Dictionary = Saved.capture_combat(c); var at: Vector3 = player.position
	var trace := []
	for t in 35:
		step(c, a, ["primary"] if t == 0 else []); trace.append(c.snapshot())
	Saved.restore_combat(c, data); player.position = at; a = Adapter.new()
	var again := []
	for t in 35:
		step(c, a, ["primary"] if t == 0 else []); again.append(c.snapshot())
	expect(trace == again, "mid-recovery queued chain save restores identical snapshots")
	expect(c.extra_snapshot().has("combat2"), "new integer moveset state is captured")
	c.dispose()
	c = fight(false)
	expect(not c.snapshot().has("combat2"), "legacy snapshot has no new fields")
	c.dispose()
func clip_fallback() -> void:
	var a = preload("res://modules/animation_state.gd").new()
	# An actor without optional clips exercises the real placeholder fallback.
	var rig := Node3D.new()
	world.add_child(rig); a.bind(rig)
	for clip in ["swing2","swing3","charge","dash_attack","parry"]:
		a.show(clip, 5)
		expect(rig.get_meta("module_clip", "") == ("block" if clip == "parry" else "swing"), "optional clip resolves " + clip)
	rig.free()
func protection_window() -> void:
	var c = fight(); var a = Adapter.new()
	c.protection_ticks = 45
	var e = c.enemies[0]; e.body.position = player.position; e.data.walker.bump_speed_mps = 0
	var landed := []
	for t in 47:
		e.transition("attack"); e.hit = false
		var hp: int = c.health; step(c, a)
		if hp != c.health: landed.append(t)
	expect(landed == [0,45], "45 tick post-hit protection is independent of 18 tick hurt")
	facts.protection_hits = landed; c.dispose()
func parry_boundaries() -> void:
	for contact_tick in [8,9]:
		var c = fight(); var a = Adapter.new(); c.block_available = true
		var e = c.enemies[0]; e.body.position = player.position + Vector3(0,0,-0.6); e.data.walker.bump_speed_mps = 0
		var parried := false
		for t in range(contact_tick+1):
			if t == contact_tick: e.transition("attack"); e.hit = false
			step(c,a,["secondary"])
			for f in c.feedback:
				if f.kind == "parry": parried = true
		expect(parried == (contact_tick == 8), "parry boundary at " + str(contact_tick))
		if contact_tick == 8:
			expect(e.state == "hurt", "parry staggers melee attacker")
			for t in 29: step(c,a,["secondary"])
			expect(e.state == "hurt", "parry stagger holds 29 following ticks")
			step(c,a,["secondary"])
			expect(e.state == "approach", "parry stagger releases on tick 30")
		c.dispose()
	var c = fight(); var a = Adapter.new(); c.block_available = true
	var owner = c.enemies[0]
	c.spawn_shot(owner,Vector3(0,0,1),4.5,0.25,1,180,true,0)
	var shot = c.projectiles[0]; shot.position = player.position + Vector3(0,0.6,-0.3)
	step(c,a,["secondary"])
	expect(shot.reflected and c.health == 3, "timed secondary reflects a contacting deflectable shot")
	c.dispose()
func frame_and_charge_restore() -> void:
	var phases = preload("res://modules/combat/clip_phases.gd")
	for kind in ["jab","cross","finisher","charge","running"]:
		var c = fight(); var a = Adapter.new(); c.start_move(kind)
		var f: Array = c.frame_data(); var hits := 0
		for t in 65:
			var hp: int = c.enemies[0].hp; step(c,a)
			if c.shown_swing >= 0:
				var key: int = phases.move_key(c.shown_swing,f)
				var active: bool = Combat.window(c.shown_swing,int(f[0]),int(f[1]))
				expect(active == (key >= 5 and key <= 7), kind + " phase-locked active keys")
			if c.enemies[0].hp < hp:
				hits += hp-c.enemies[0].hp
				expect(Combat.window(c.shown_swing,int(f[0]),int(f[1])),kind+" damage only in its own frame window")
		expect(hits == int(f[3]),kind+" deals one bounded contact")
		c.dispose()
	var c = fight(); var a = Adapter.new()
	for t in 13: step(c,a,["primary"])
	var data: Dictionary = Saved.capture_combat(c); var at: Vector3 = player.position; var held: Array = a.held.duplicate()
	var trace := []
	for t in 55: step(c,a,["primary"] if t < 20 else []); trace.append(c.snapshot())
	Saved.restore_combat(c,data); player.position = at; a = Adapter.new(); a.held = held
	var again := []
	for t in 55: step(c,a,["primary"] if t < 20 else []); again.append(c.snapshot())
	expect(trace == again,"mid-hold save restores release, charge damage and RNG")
	c.dispose()
func finisher_three() -> void:
	var c = fight(); c.dispose(); c.encounter.spawns = []
	for i in 3: c.encounter.spawns.append({"id":"target_"+str(i),"archetype":"pitch_walker","position_m":[7.3+i*0.7,0,6.9],"wave":0})
	c.spawn_wave()
	for e in c.enemies: e.transition("recover")
	var a = Adapter.new(); c.start_move("finisher")
	for t in 40: step(c,a)
	expect(c.enemies.all(func(e): return e.hp == 39), "finisher hits three distinct targets once")
	c.dispose()
func run() -> void:
	world = Node3D.new(); root.add_child(world)
	player = Player.new(); world.add_child(player)
	await physics_frame
	moves(); timing_restore(); clip_fallback(); protection_window(); parry_boundaries(); frame_and_charge_restore(); finisher_three()
	var report := {"checks":checks,"failures":failures,"facts":facts}
	var args := OS.get_cmdline_user_args(); var i := args.find("--report")
	if i >= 0: var f = FileAccess.open(args[i+1], FileAccess.WRITE); f.store_string(JSON.stringify(report,"  "))
	print("COMBAT2 ", JSON.stringify(report))
	world.free(); quit(0 if failures.is_empty() else 1)
