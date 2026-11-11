extends "res://playtest/module_runner.gd"
## FEEL4 wave-clear cue probe (windowed). Plays the game's own winning route with the production module bot (real
## Actions frames, playtest/module_runner.gd) and photographs the goal cue when the first fight is cleared: the tick
## of the clear, the bloom, and the open gate it then points at. Stops after that. Presentation evidence only.
##   godot --path <runtime> --resolution 960x720 --script res://tests/feel4_wave_clear.gd -- --shots=<dir>
## The runtime's playtest-config.json "output" must point at a scratch folder (the bot writes its receipts there).
var shots_dir := ""
var cleared_at := -1
var cue_rows := []
const MARKS := [0, 12, 24, 45, 90, 150]

func step(v := Vector2.ZERO, discrete := []) -> void:
	await super.step(v, discrete)
	if shots_dir == "":
		for arg in OS.get_cmdline_user_args():
			if str(arg).begins_with("--shots="): shots_dir = str(arg).trim_prefix("--shots=")
		if shots_dir == "": shots_dir = config.output
		DirAccess.make_dir_recursive_absolute(shots_dir)
	if cleared_at < 0 and view.runtime.state.modules.completed.size() > 0: cleared_at = tick
	if cleared_at < 0: return
	var k := tick - cleared_at
	if k in MARKS:
		var path := shots_dir.path_join("wave-clear-%03d.png" % k)
		await view.capture(path)
		var cue = view.world.get_node_or_null("goal_cue")
		cue_rows.append({"after_clear_ticks": k, "tick": tick, "file": path.get_file(), "room": view.runtime.state.location,
			"cue": cue.report() if cue != null else null, "gate_open": view.module_host == null or view.module_host.active_id == ""})
	if k >= MARKS[-1]:
		var f := FileAccess.open(shots_dir.path_join("wave-clear.json"), FileAccess.WRITE)
		f.store_string(JSON.stringify({"cleared_tick": cleared_at, "rows": cue_rows}, "  ")); f.close()
		print("FEEL4_WAVE_CLEAR ", JSON.stringify({"cleared_tick": cleared_at, "rows": cue_rows.size()}))
		quit(0)
