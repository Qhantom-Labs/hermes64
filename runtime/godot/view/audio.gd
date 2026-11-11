extends Node
## External WAV binding seam. No synthesis or theme names in the runtime.
## AUDIOPIPE: rows may also carry imported music/voice (docs/AUDIO-IMPORT.md):
##   music:default|menu|results|boss, music:scene:<room>, music:wave:<n>, music:event:<kind>  -> looping, crossfaded
##   voice:<line> (optional on_action / on_scene / on_event hooks)                             -> Voice bus
## Busses Music / Voice / SFX are created on demand and follow user://hermes64_audio.json volumes. Everything here is
## presentation: no story state, RNG or physics is read back from audio, so simulation and replays are unchanged.
const SETTINGS_PATH := "user://hermes64_audio.json"
const BUSSES := ["Music", "Voice", "SFX"]
var clips := {}
var report := {}
var rows := {}
var ambient: AudioStreamPlayer
var effect: AudioStreamPlayer
var music_players := []
var music_index := 0
var music_current := ""
var scene_key := ""
var event_key := ""
var menu_on := false
var results_on := false
var voice_player: AudioStreamPlayer
var settings := {"master": 1.0, "music": 1.0, "voice": 1.0, "sfx": 1.0}
# Dummy headless audio has no mixer to retire playback objects. Still load/hash
# WAVs for validation, but only create playback on a real display/audio run.
var playback_enabled := DisplayServer.get_name() != "headless"
func boot(path: String) -> void:
	ensure_busses()
	load_settings()
	ambient = AudioStreamPlayer.new()
	effect = AudioStreamPlayer.new()
	ambient.volume_db = -21
	effect.volume_db = -15
	ambient.bus = bus_or_master("SFX")
	effect.bus = bus_or_master("SFX")
	add_child(ambient)
	add_child(effect)
	for i in 2:
		var m := AudioStreamPlayer.new()
		m.bus = bus_or_master("Music")
		m.volume_db = -80
		add_child(m)
		music_players.append(m)
	voice_player = AudioStreamPlayer.new()
	voice_player.bus = bus_or_master("Voice")
	add_child(voice_player)
	if not FileAccess.file_exists(path): return
	var data = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not data is Dictionary: return
	for event in data:
		var row: Dictionary = data[event]
		if FileAccess.get_sha256(row.path) != row.sha256:
			push_error("WAV hash mismatch")
			continue
		var stream := AudioStreamWAV.load_from_file(row.path)
		if stream == null:
			push_error("WAV failed to load")
			continue
		if row.get("kind", "") == "music" and row.get("loop", false):
			stream.loop_mode = AudioStreamWAV.LOOP_FORWARD
			stream.loop_begin = 0
			stream.loop_end = int(row.get("loop_end", int(stream.get_length() * stream.mix_rate)))
		clips[event] = stream
		rows[event] = row
		report[event] = {"sha256":row.sha256,"seconds":stream.get_length(),"loaded":true}
	for event in sfx_keys(): sfx_banks[event.split(":")[1]] = sfx_banks.get(event.split(":")[1], []) + [event]
	if clips.has("ambient"):
		ambient.stream = clips.ambient
		ambient.stream.loop_mode = AudioStreamWAV.LOOP_FORWARD
		ambient.stream.loop_begin = 0
		ambient.stream.loop_end = int(ambient.stream.get_length()*ambient.stream.mix_rate)
		if rows.ambient.has("gain_db"): ambient.volume_db = float(rows.ambient.gain_db)
		if playback_enabled: ambient.play()
	if rows.has("interact") and rows.interact.has("gain_db"): effect.volume_db = float(rows.interact.gain_db)
	update_music()
func _exit_tree() -> void:
	stop_playback()
func stop_playback() -> void:
	for player in [ambient, effect, voice_player] + voices + music_players + sfx_pool:
		if is_instance_valid(player):
			player.stop()
			player.stream = null
	clips.clear()
	sfx_banks.clear()
func shutdown() -> void:
	stop_playback()
	if playback_enabled:
		playback_enabled = false
		# stop() retires mixer-owned WAV/playback references asynchronously.
		# Drain before quitting, not inside _exit_tree after the mixer has stopped.
		await get_tree().create_timer(0.1).timeout
func trigger() -> void:
	if playback_enabled and clips.has("interact"):
		effect.stream = clips.interact
		effect.play()
## COMBAT lane: short catalog cues staged as "cue:<catalog id>" (hash-checked like every other row). Two voices so a
## telegraph and a hit can overlap; the same cue restarts at most every 4 frames. Returns true when the cue exists.
var voices := []
var voice_index := 0
var last_cue := {}
func cue(id: String) -> bool:
	var key := "cue:" + id
	if not clips.has(key): return false
	if not playback_enabled: return true
	var now := Engine.get_physics_frames()
	if now - int(last_cue.get(key, -100)) < 4: return true
	last_cue[key] = now
	if voices.is_empty():
		for i in 2:
			var p := AudioStreamPlayer.new()
			p.volume_db = -14
			p.bus = bus_or_master("SFX")
			add_child(p)
			voices.append(p)
	var player: AudioStreamPlayer = voices[voice_index % voices.size()]
	voice_index += 1
	player.stream = clips[key]
	player.volume_db = float(rows[key].get("gain_db", -14))
	player.play()
	return true
## COMBATFIX: combat event sounds, rows "sfx:<event>:<n>" lowered from the project's audio slots combat_sfx
## (docs/AUDIO-IMPORT.md); a game without them has none and keeps its stock cues. One-shot: an event plays at most
## once per SFX_COOLDOWN ticks, at most SFX_VOICES sounds at once (the longest-playing one is cut), and the Music bus
## ducks SFX_DUCK dB for 0.35 s under heavy hits. Presentation only; sfx_stats counts what was asked and played.
const SFX_VOICES := 4
const SFX_COOLDOWN := {"punch_hit": 4, "punch_miss": 8, "robot_hit": 4, "boss_hit": 6, "player_hurt": 12, "dodge": 10, "block": 6, "robot_death": 10, "boss_telegraph": 30}
const SFX_DUCK := {"boss_hit": 4.0, "player_hurt": 3.0, "robot_death": 3.0}
var sfx_banks := {}
var sfx_last := {}
var sfx_pool := []
var sfx_stats := {"asked": 0, "played": 0, "cooldown": 0, "cut": 0, "max_voices": 0, "events": {}}
var duck_left := 0.0
var duck_db := 0.0
func sfx_keys() -> Array:
	var out := []
	for key in clips:
		if str(key).begins_with("sfx:") and str(key).count(":") == 2: out.append(key)
	out.sort()
	return out
func has_sfx() -> bool:
	return not sfx_banks.is_empty()
func sfx(event: String, variant := 0) -> bool:
	var bank: Array = sfx_banks.get(event, [])
	if bank.is_empty(): return false
	sfx_stats.asked += 1
	var now := Engine.get_physics_frames()
	if now - int(sfx_last.get(event, -1000)) < int(SFX_COOLDOWN.get(event, 4)):
		sfx_stats.cooldown += 1
		return true
	sfx_last[event] = now
	sfx_stats.played += 1
	sfx_stats.events[event] = int(sfx_stats.events.get(event, 0)) + 1
	if not playback_enabled: return true
	if sfx_pool.is_empty():
		for i in SFX_VOICES:
			var p := AudioStreamPlayer.new()
			p.bus = bus_or_master("SFX")
			add_child(p)
			sfx_pool.append(p)
	var player: AudioStreamPlayer = null
	for p in sfx_pool:
		if not p.playing: player = p; break
	if player == null:
		sfx_stats.cut += 1
		player = sfx_pool[0]
		for p in sfx_pool:
			if p.get_playback_position() > player.get_playback_position(): player = p
	var key: String = bank[posmod(variant, bank.size())]
	player.stream = clips[key]
	player.volume_db = float(rows[key].get("gain_db", -6))
	player.play()
	var busy := 0
	for p in sfx_pool:
		if p.playing: busy += 1
	sfx_stats.max_voices = maxi(int(sfx_stats.max_voices), busy)
	if SFX_DUCK.has(event):
		duck_db = maxf(duck_db if duck_left > 0.0 else 0.0, float(SFX_DUCK[event]))
		duck_left = 0.35
	return true
func _process(delta: float) -> void:
	if duck_left <= 0.0: return
	duck_left = maxf(0.0, duck_left - delta)
	var idx := AudioServer.get_bus_index("Music")
	if idx >= 0: AudioServer.set_bus_volume_db(idx, linear_to_db(maxf(float(settings.music), 0.001)) - duck_db * minf(1.0, duck_left / 0.15))

# ------------------------------------------------------------------ AUDIOPIPE: busses + settings
func bus_or_master(bus_name: String) -> String:
	return bus_name if AudioServer.get_bus_index(bus_name) >= 0 else "Master"
func ensure_busses() -> void:
	for bus_name in BUSSES:
		if AudioServer.get_bus_index(bus_name) < 0:
			AudioServer.add_bus()
			var idx := AudioServer.bus_count - 1
			AudioServer.set_bus_name(idx, bus_name)
			AudioServer.set_bus_send(idx, "Master")
## Optional user volumes {"master","music","voice","sfx"} as 0..1 linear. Missing/invalid keys keep 1.0. Never
## written by the runtime (replays and bots must not change a player's settings).
func load_settings() -> void:
	if FileAccess.file_exists(SETTINGS_PATH):
		var raw = JSON.parse_string(FileAccess.get_file_as_string(SETTINGS_PATH))
		if raw is Dictionary:
			for key in settings:
				var v = raw.get(key)
				if (v is float or v is int) and is_finite(float(v)):
					settings[key] = clampf(float(v), 0.0, 1.0)
	apply_settings()
func apply_settings() -> void:
	var targets := {"Master": settings.master, "Music": settings.music, "Voice": settings.voice, "SFX": settings.sfx}
	for bus_name in targets:
		var idx := AudioServer.get_bus_index(bus_name)
		if idx < 0: continue
		var v: float = targets[bus_name]
		AudioServer.set_bus_mute(idx, v <= 0.001)
		AudioServer.set_bus_volume_db(idx, linear_to_db(maxf(v, 0.001)))
func set_volume(bus_key: String, value: float) -> void:
	if settings.has(bus_key):
		settings[bus_key] = clampf(value, 0.0, 1.0)
		apply_settings()

# ------------------------------------------------------------------ AUDIOPIPE: music selection + crossfade
## Priority: results > menu > event (boss / wave / music:event:<kind>) > scene > default.
func pick_music() -> String:
	for key in ["music:results" if results_on else "", "music:menu" if menu_on else "", event_key, scene_key, "music:default"]:
		if key != "" and clips.has(key): return key
	return ""
func update_music() -> void:
	var key := pick_music()
	if key == music_current: return
	var fade := 1.5
	if rows.has(key): fade = float(rows[key].get("fade_s", 1.5))
	elif rows.has(music_current): fade = float(rows[music_current].get("fade_s", 1.5))
	music_current = key
	if not playback_enabled or music_players.is_empty() or not is_inside_tree(): return
	var old: AudioStreamPlayer = music_players[music_index % 2]
	if old.playing:
		var out := create_tween()
		out.tween_property(old, "volume_db", -80.0, maxf(fade, 0.01))
		out.tween_callback(old.stop)
	if key == "": return
	music_index += 1
	var fresh: AudioStreamPlayer = music_players[music_index % 2]
	var gain := float(rows[key].get("gain_db", -6))
	fresh.stop()
	fresh.stream = clips[key]
	fresh.volume_db = -80.0 if fade > 0.0 else gain
	fresh.play()
	if fade > 0.0: create_tween().tween_property(fresh, "volume_db", gain, fade)
func music_state() -> Dictionary:
	return {"current": music_current, "scene": scene_key, "event": event_key, "menu": menu_on, "results": results_on}

# ------------------------------------------------------------------ AUDIOPIPE: presenter hooks
func on_scene(room_id: String) -> void:
	scene_key = "music:scene:" + room_id
	event_key = ""
	results_on = false
	play_hooked("on_scene", room_id)
	update_music()
func on_event(kind: String, payload: Dictionary) -> void:
	var wave_key := "music:wave:%s" % str(payload.get("wave", ""))
	if clips.has("music:event:" + kind):
		event_key = "music:event:" + kind
	elif kind == "boss_phase" and clips.has("music:boss"):
		event_key = "music:boss"
	elif kind == "wave_started" and clips.has(wave_key):
		event_key = wave_key
	elif kind in ["boss_defeated", "encounter_cleared"] and (event_key == "music:boss" or event_key.begins_with("music:wave:")):
		event_key = ""
	play_hooked("on_event", kind)
	update_music()
## SCENES passes the exact runtime slot name; absent cues retain the current room music.
func on_cutscene_music(slot: String) -> void:
	if not slot.begins_with("music:") or not clips.has(slot): return
	event_key = slot
	update_music()
func stop_voice() -> void:
	if is_instance_valid(voice_player):
		voice_player.stop()
		voice_player.stream = null
func on_action(action_id: String) -> void:
	play_hooked("on_action", action_id)
func on_menu(open: bool) -> void:
	if open == menu_on: return
	menu_on = open
	update_music()
func on_results() -> void:
	results_on = true
	update_music()
## Plays voice:<line>. Returns true when the line exists (also in headless runs, where nothing is audible).
func voice(line: String) -> bool:
	var key := "voice:" + line
	if not clips.has(key): return false
	if playback_enabled:
		voice_player.stream = clips[key]
		voice_player.volume_db = float(rows[key].get("gain_db", -3))
		voice_player.play()
	return true
var last_voice := ""
func play_hooked(hook: String, value: String) -> void:
	if value == "": return
	for key in rows:
		if key.begins_with("voice:") and str(rows[key].get(hook, "")) == value:
			last_voice = key.substr(6)
			voice(last_voice)
			return
