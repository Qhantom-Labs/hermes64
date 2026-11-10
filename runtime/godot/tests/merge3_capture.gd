extends "res://playtest/module_runner.gd"
## MERGE3 combat filmstrips in the real renderer. Runs the ordinary module bot (production Actions
## input) and, while it fights, saves the 320x240 frame whenever a watched clip shows a new key.
## Presentation evidence for review only: it is not an acceptance receipt (captures add readbacks).
## Driven by tools/merge3_capture.py, which writes playtest-config.json with the capture output.
##
## At most one readback per tick: a second `await frame_post_draw` in the same step would let the next
## physics tick run before the bot submits its input. Sequences that want the same tick share one image;
## a tick on which the base runner already read back is skipped (the key is taken on the next tick).
var shots := {}
var done := {}
var rows := []
var watched := {}
var pending := []
var skipped := 0
func unproject(at: Vector3) -> Array:
	var p: Vector2 = view.camera.unproject_position(at)
	return [roundi(p.x), roundi(p.y)]
func want(seq: String, label: String, limit: int, focus: Vector3) -> void:
	var n: int = shots.get(seq, 0)
	if n >= limit:
		done[seq] = true
		return
	pending.append({"seq":seq, "label":label, "focus":focus, "file":"%s_%02d_%s.png" % [seq, n, label]})
## Capture each new key of a sequence once, until the sequence ends (then it is closed for good).
func watch(seq: String, active: bool, label: String, limit: int, focus: Vector3) -> void:
	if done.get(seq, false): return
	if not active:
		if watched.has(seq): done[seq] = true
		return
	if watched.get(seq, "") == label: return
	want(seq, label, limit, focus)
func flush(blocked: bool) -> void:
	if pending.is_empty(): return
	if blocked:
		skipped += 1
		pending.clear()
		return
	var folder: String = config.output.path_join("film")
	var first: String = folder.path_join(pending[0].file)
	measurement_boundary("filmstrip readback")
	if await view.capture_low(first):
		for i in pending.size():
			var row: Dictionary = pending[i]
			if i > 0: DirAccess.copy_absolute(first, folder.path_join(row.file))
			shots[row.seq] = int(shots.get(row.seq, 0)) + 1
			watched[row.seq] = row.label
			rows.append({"seq":row.seq, "file":row.file, "tick":tick, "label":row.label, "player_px":unproject(view.player.position + Vector3.UP * 0.8), "focus_px":unproject(row.focus + Vector3.UP * 0.8)})
	pending.clear()
func step(v := Vector2.ZERO, discrete := []) -> void:
	var before := captures.size()
	await super.step(v, discrete)
	var host = view.module_host
	if host == null or host.combat == null or DisplayServer.get_name() == "headless": return
	var combat = host.combat
	var actor = host.animation.actor
	if actor == null or not is_instance_valid(actor): return
	var clip: String = actor.get_meta("module_clip", "")
	var key: int = actor.get_meta("module_key", -1)
	var target = combat.find_target(combat.target)
	var focus: Vector3 = target.body.position if target != null else view.player.position
	watch("player_swing", clip == "swing", "swing_k%02d" % key, 16, focus)
	watch("player_roll", clip == "roll", "roll_k%02d" % key, 16, focus)
	watch("player_hurt", clip == "hurt", "hurt_k%02d" % key, 16, focus)
	if combat.feedback.any(func(f): return f.kind == "hit") and not watched.has("hit_until"):
		watched["hit_until"] = tick + 6
	if watched.has("hit_until") and not done.get("hit", false):
		var victim = target
		for e in combat.enemies:
			if e.state in ["hurt", "dead"]: victim = e
		want("hit", "t%02d" % (tick - int(watched.hit_until) + 6), 7, victim.body.position if victim != null else focus)
		if tick >= int(watched.hit_until): done["hit"] = true
	for enemy in combat.enemies:
		var visual = enemy.visual
		if visual == null or not is_instance_valid(visual): continue
		var eclip: String = visual.get_meta("module_clip", "")
		var ekey: int = visual.get_meta("module_key", -1)
		watch("enemy_" + enemy.identity, eclip in ["telegraph", "attack"], "%s_k%02d" % [eclip, ekey], 24, enemy.body.position)
	await flush(captures.size() != before)
func finish() -> void:
	var file := FileAccess.open(config.output.path_join("film").path_join("film.json"), FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify({"rows":rows, "shots":shots, "skipped_ticks":skipped, "display":DisplayServer.get_name(), "renderer":RenderingServer.get_current_rendering_method(), "adapter":RenderingServer.get_video_adapter_name()}, "  ", true))
		file.close()
	await super.finish()
