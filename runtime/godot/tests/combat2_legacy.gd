extends "res://tests/combat2_moveset.gd"
## Fixed-input legacy reducer probe, not a substitute for missing historical game movies.
func run() -> void:
	world = Node3D.new(); root.add_child(world); player = Player.new(); world.add_child(player)
	await physics_frame
	var c = fight(false); var a = Adapter.new(); var rows := []
	for t in 500:
		var buttons := []
		if t % 32 == 0: buttons.append("primary")
		if t % 117 == 0: buttons.append("dodge")
		if t % 90 > 70: buttons.append("secondary")
		var out: Dictionary = step(c,a,buttons)
		rows.append({"state":c.snapshot(),"impulse":[out.impulse.x,out.impulse.y,out.impulse.z],"position":[player.position.x,player.position.y,player.position.z]})
	var report := {"checks":500,"failures":[],"sha256":JSON.stringify(rows,"",true,true).sha256_text(),"rows":rows}
	var args := OS.get_cmdline_user_args(); var i := args.find("--report")
	if i >= 0: var f = FileAccess.open(args[i+1],FileAccess.WRITE); f.store_string(JSON.stringify(report))
	print("LEGACY_PROBE ",report.sha256); c.dispose(); world.free(); quit()
