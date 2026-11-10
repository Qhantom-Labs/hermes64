extends "res://tests/combat2_moveset.gd"
func budget(modern_profile: bool, classic := false) -> Dictionary:
	var c = fight(modern_profile); c.dispose()
	if classic:
		var row: Dictionary = c.archetypes.pitch_walker.duplicate(true)
		row.fsm.template = "melee_approach_v1"; row.attack_range_m = 8
		c.archetypes["chairbot"] = row
	c.encounter.spawns = []
	c.encounter["bosses"] = ["alpha","beta","gamma"]
	c.encounter["attack_budget"] = 1; c.encounter["attack_gap_ticks"] = 30
	for i in 3: c.encounter.spawns.append({"id":["alpha","beta","gamma"][i],"archetype":"chairbot","position_m":[4+i*4,0,4],"wave":0})
	c.spawn_wave(); c.health = 999
	for e in c.enemies:
		if not classic:
			e.data.boss.phases = [{"id":"one","health_permille":1000,"patterns":["memo"]}]
			e.data.boss.patterns = [e.data.boss.patterns[1]]
			e.data.boss.patterns[0].windup_ticks = 44
			e.data.boss.patterns[0].recovery_ticks = 60
		e.transition("approach")
	var a = Adapter.new(); var peak := 0; var last_busy := -100; var starts := []; var used := []
	for t in 700:
		var previous: Array = c.enemies.map(func(e): return e.state)
		step(c, a)
		var busy := 0
		for i in c.enemies.size():
			var e = c.enemies[i]
			if e.state in ["telegraph","attack"]: busy += 1
			if e.state == "telegraph" and previous[i] != "telegraph":
				starts.append({"id":e.identity,"tick":t,"gap":t-last_busy-1})
				if not used.has(e.identity): used.append(e.identity)
		peak = maxi(peak, busy)
		if busy > 0: last_busy = t
	var result := {"peak":peak,"starts":starts,"used":used}
	c.dispose(); return result
func run() -> void:
	world = Node3D.new(); root.add_child(world); player = Player.new(); world.add_child(player)
	await physics_frame
	var modern_result := budget(true); var legacy_result := budget(false)
	expect(modern_result.peak == 1, "shared trio budget permits one windup/active")
	expect(modern_result.used.size() == 3, "all bosses get a turn")
	expect(modern_result.starts.all(func(s): return s.gap >= 30), "30 full safe ticks between attacks")
	expect(legacy_result.peak == 3, "known bad unlimited old behavior overlaps all three")
	var classic_result := budget(true,true)
	expect(classic_result.peak == 1, "shared budget also gates original melee templates")
	var report := {"checks":checks,"failures":failures,"modern":modern_result,"legacy":legacy_result,"classic":classic_result}
	var args := OS.get_cmdline_user_args(); var i := args.find("--report")
	if i >= 0: var f = FileAccess.open(args[i+1], FileAccess.WRITE); f.store_string(JSON.stringify(report,"  "))
	print("COMBAT2_BOSSES ", JSON.stringify(report)); world.free(); quit(0 if failures.is_empty() else 1)
