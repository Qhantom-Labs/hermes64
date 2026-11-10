extends "res://playtest/module_runner.gd"
## COMBAT lane filmstrips in the real renderer. Runs the ordinary module bot (production Actions input) and saves the
## 320x240 frame at the moments a reviewer needs: swing keys, the roll, hits, enemy telegraphs/attacks (with floor
## decals), the player hurt, projectiles, shockwaves, boss phase changes and the defeat beat. Every captured row also
## records the on-screen pixel height of the player and of the focused enemy (actor AABB projected through the camera
## drawing the frame) and the combat-camera blend weight, so frame scale is measured, not eyeballed.
## `readability_off` in playtest-config.json switches the COMBAT readability profile off (camera, light, telegraph):
## the same simulation shown the MERGE3 way, for the before/after sheet.
## Presentation evidence for review only: captures add readbacks, so this is not an acceptance receipt.
const Readability = preload("res://modules/combat/readability.gd")
const Room = preload("res://view/room.gd")
var shots := {}
var done := {}
var rows := []
var watched := {}
var pending := []
var skipped := 0
var phase_seen := -1
var wave_seen := -1
func run() -> void:
	var cfg = Wire.read_json("res://playtest-config.json")
	if cfg is Dictionary and cfg.get("readability_off", false):
		var d := Readability.defaults().duplicate(true)
		for group in ["camera", "light", "telegraph"]: d[group]["enabled"] = false
		Readability.cached = d
	await super.run()
func camera() -> Camera3D:
	var c = view.module_host.combat_camera.current() if view.module_host != null else null
	return c if c != null else view.camera
func px(at: Vector3) -> Array:
	var cam := camera()
	if cam.is_position_behind(at): return [-1, -1]
	var p: Vector2 = cam.unproject_position(at)
	return [roundi(p.x), roundi(p.y)]
## Pixel height of a node's visible meshes on screen (projected AABB corners), -1 when off screen.
func height_px(node) -> int:
	if node == null or not is_instance_valid(node): return -1
	var box: AABB = Room.world_aabb(node)
	if box.size == Vector3.ZERO: return -1
	var cam := camera()
	var lo := INF
	var hi := -INF
	for i in 8:
		var c := box.get_endpoint(i)
		if cam.is_position_behind(c): return -1
		var y: float = cam.unproject_position(c).y
		lo = minf(lo, y)
		hi = maxf(hi, y)
	return roundi(hi - lo)
func want(seq: String, label: String, limit: int, focus: Vector3, focus_node = null) -> void:
	var n: int = shots.get(seq, 0)
	if n >= limit:
		done[seq] = true
		return
	pending.append({"seq":seq, "label":label, "focus":focus, "focus_node":focus_node, "file":"%s_%02d_%s.png" % [seq, n, label]})
func watch(seq: String, active: bool, label: String, limit: int, focus: Vector3, focus_node = null) -> void:
	if done.get(seq, false): return
	if not active:
		if watched.has(seq): done[seq] = true
		return
	if watched.get(seq, "") == label: return
	want(seq, label, limit, focus, focus_node)
func flush(blocked: bool) -> void:
	if pending.is_empty(): return
	if blocked:
		skipped += 1
		pending.clear()
		return
	var folder: String = config.output.path_join("film")
	var first: String = folder.path_join(pending[0].file)
	measurement_boundary("filmstrip readback")
	var host = view.module_host
	if await view.capture_low(first):
		for i in pending.size():
			var row: Dictionary = pending[i]
			if i > 0: DirAccess.copy_absolute(first, folder.path_join(row.file))
			shots[row.seq] = int(shots.get(row.seq, 0)) + 1
			watched[row.seq] = row.label
			rows.append({"seq":row.seq, "file":row.file, "tick":tick, "label":row.label, "player_px":px(view.player.position + Vector3.UP * 0.8),
				"focus_px":px(row.focus + Vector3.UP * 0.8), "player_h_px":height_px(view.player.get_node_or_null("visual")),
				"focus_h_px":height_px(row.focus_node), "camera_weight":host.combat_camera.weight, "light_weight":host.stage.weight,
				"markers":host.stage.markers.size(), "glyphs":host.stage.glyphs.size(), "camera":host.combat_camera.last.duplicate(true)})
	pending.clear()
func step(v := Vector2.ZERO, discrete := []) -> void:
	var before := captures.size()
	await super.step(v, discrete)
	var host = view.module_host
	if host == null or DisplayServer.get_name() == "headless": return
	var combat = host.combat
	if combat == null:
		defeat_frames()
		await flush(captures.size() != before)
		return
	var actor = host.animation.actor
	var target = combat.find_target(combat.target)
	var focus: Vector3 = target.body.position if target != null else view.player.position
	var focus_node = target.visual if target != null else null
	if actor != null and is_instance_valid(actor):
		var clip: String = actor.get_meta("module_clip", "")
		var key: int = actor.get_meta("module_key", -1)
		watch("player_swing", clip == "swing", "swing_k%02d" % key, 16, focus, focus_node)
		watch("player_roll", clip == "roll", "roll_k%02d" % key, 16, focus, focus_node)
		watch("player_hurt", clip == "hurt", "hurt_k%02d" % key, 10, focus, focus_node)
	if combat.feedback.any(func(f): return f.kind == "hit") and not watched.has("hit_until"):
		watched["hit_until"] = tick + 6
	if watched.has("hit_until") and not done.get("hit", false):
		var victim = target
		for e in combat.enemies:
			if e.state in ["hurt", "dead"]: victim = e
		want("hit", "t%02d" % (tick - int(watched.hit_until) + 6), 7, victim.body.position if victim != null else focus, victim.visual if victim != null else null)
		if tick >= int(watched.hit_until): done["hit"] = true
	for enemy in combat.enemies:
		var visual = enemy.visual
		if visual == null or not is_instance_valid(visual): continue
		var eclip: String = visual.get_meta("module_clip", "")
		var ekey: int = visual.get_meta("module_key", -1)
		var name: String = str(enemy.data.fsm.template).split("_")[0] + "_" + enemy.identity
		watch("enemy_" + name, eclip in ["telegraph", "attack"], "%s_k%02d" % [eclip, ekey], 24, enemy.body.position, visual)
	var waves = combat.get("shockwaves")
	if waves != null and not waves.is_empty():
		watch("shockwave", true, "r%03d" % roundi(float(waves[0].radius) * 100.0), 8, waves[0].origin, null)
	elif watched.has("shockwave"): done["shockwave"] = true
	var shots_now = combat.get("projectiles")
	if shots_now != null and not shots_now.is_empty():
		watch("projectile", true, "a%03d" % int(shots_now[0].age), 10, shots_now[0].position, null)
	elif watched.has("projectile"): done["projectile"] = true
	var boss = combat.boss() if combat.has_method("boss") else null
	if boss != null:
		if int(boss.phase) != phase_seen:
			if phase_seen >= 0: watched.erase("boss_phase"); done.erase("boss_phase")
			phase_seen = int(boss.phase)
			want("boss_phase", "p%d" % phase_seen, 6, boss.body.position, boss.visual)
	# The defeat beat: the hit-stop, the burst ring and the clear, then the view blending back (combat ends meanwhile).
	for f in combat.feedback:
		if f.kind == "boss_defeated" and defeat_tick < 0:
			defeat_tick = tick
			defeat_at = Vector3(f.at[0], f.at[1], f.at[2]) if f.get("at") is Array else view.player.position
	defeat_frames()
	if int(combat.wave) != wave_seen:
		wave_seen = int(combat.wave)
		want("wave", "w%d" % wave_seen, 6, focus, focus_node)
	await flush(captures.size() != before)
var defeat_tick := -1
var defeat_at := Vector3.ZERO
## Every 3rd tick for 30 ticks after the boss falls (labels by offset, so frozen hit-stop ticks still differ).
func defeat_frames() -> void:
	if defeat_tick < 0 or tick > defeat_tick + 30 or (tick - defeat_tick) % 3 != 0: return
	want("boss_defeat", "t%02d" % (tick - defeat_tick), 11, defeat_at, null)
func finish() -> void:
	var file := FileAccess.open(config.output.path_join("film").path_join("film.json"), FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify({"rows":rows, "shots":shots, "skipped_ticks":skipped, "display":DisplayServer.get_name(), "renderer":RenderingServer.get_current_rendering_method(), "adapter":RenderingServer.get_video_adapter_name(), "readability_off":bool(config.get("readability_off", false))}, "  ", true))
		file.close()
	await super.finish()
