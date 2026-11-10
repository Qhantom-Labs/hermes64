extends SceneTree
## AUDIOPIPE probe: boots view/audio.gd on a staged audio.json (path after --), drives the presenter hooks and prints
## the music selection after each step as one JSON line. Headless: nothing is audible, selection/hash/bus logic is.
func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var path: String = args[0] if args.size() > 0 else ""
	var audio = preload("res://view/audio.gd").new()
	root.add_child(audio)
	audio.boot(path)
	var steps := []
	steps.append(["boot", audio.music_state().current])
	audio.on_scene("hall"); steps.append(["scene:hall", audio.music_state().current])
	audio.on_scene("yard"); steps.append(["scene:yard", audio.music_state().current])
	audio.on_event("wave_started", {"wave": 2}); steps.append(["wave2", audio.music_state().current])
	audio.on_event("boss_phase", {"phase": 1}); steps.append(["boss", audio.music_state().current])
	audio.on_menu(true); steps.append(["menu", audio.music_state().current])
	audio.on_menu(false); steps.append(["menu_closed", audio.music_state().current])
	audio.on_event("boss_defeated", {}); steps.append(["boss_defeated", audio.music_state().current])
	audio.on_action("talk:guide"); steps.append(["voice_action", audio.last_voice])
	audio.on_results(); steps.append(["results", audio.music_state().current])
	audio.on_scene("hall"); steps.append(["reload_hall", audio.music_state().current])
	var busses := {}
	for b in ["Music", "Voice", "SFX"]:
		busses[b] = AudioServer.get_bus_index(b) >= 0
	audio.set_volume("music", 0.5)
	var music_db := AudioServer.get_bus_volume_db(AudioServer.get_bus_index("Music"))
	var loops := {}
	for key in audio.clips:
		if str(key).begins_with("music:"):
			loops[key] = [audio.clips[key].loop_mode, audio.clips[key].loop_end]
	print("AUDIOPIPE " + JSON.stringify({"steps": steps, "busses": busses, "music_db_at_half": snappedf(music_db, 0.01),
		"voice_known": audio.voice("intro"), "voice_unknown": audio.voice("nope"), "loaded": audio.report.size(),
		"loops": loops}))
	audio.stop_playback()
	quit(0)
