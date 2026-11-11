extends SceneTree
## SCENES lane native proof on a staged non-demo game (tools/scenes_stage.py).
## Records a real-input route (action menu keys) with scenes watched, then replays it
## with scenes off and on; records it again skipping every scene by key; runs the
## known-bad controls (teleporting scene, mid-tick freeze, no freeze, never-ending card).
const Director = preload("res://view/scene_cards.gd")
const BestStore = preload("res://view/best_store.gd")
var failures := []
var checks := 0
var report := {}
var route: Array = []
var output := ""

func _initialize() -> void: call_deferred("run")

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures.append(message)
		print("FAIL ", message)

func frame() -> void:
	await physics_frame
	await process_frame

func boot(opts: Dictionary = {}) -> Node:
	var view = load("res://main.tscn").instantiate()
	root.add_child(view)
	var cfg := {"version":1}
	if opts.get("reduced", false):
		var p: Dictionary = preload("res://input/profile.gd").defaults()
		p.options.reduced_motion = true
		cfg = {"version":1, "preset":p.preset, "options":p.options}
	view.actions.configure(cfg)
	view.actions.set_source("bot")
	var d = view.scene_cards
	d.enabled = opts.get("scenes", true)
	d.fault = str(opts.get("fault", ""))
	d.best_path = "user://scenes-test/best-%d.json" % Time.get_ticks_usec()
	d.again_handler = func(): d.set_meta("again", true)
	return view

func drop(view) -> void:
	if is_instance_valid(view):
		view.get_parent().remove_child(view)
		view.queue_free()
	await process_frame
	await process_frame

func key(code: int) -> void:
	for pressed in [true, false]:
		var e := InputEventKey.new()
		e.physical_keycode = code
		e.keycode = code
		e.pressed = pressed
		Input.parse_input_event(e)
		await process_frame

## Wait until the game accepts input again (no scene, no doorway envelope).
func settle(view, skip := false, limit := 4000) -> bool:
	for i in limit:
		var d = view.scene_cards
		if d.phase == "results": return true
		if skip and d.phase in ["card_in", "card"] and not d.skipped:
			await key(KEY_SPACE)
			continue
		if d.started and d.phase == "idle" and not d.frozen and d.pending.is_empty() and not view.room_transition.active(): return true
		await frame()
	return false

func press(view, digital: Array) -> void:
	view.actions.submit_frame({"digital":digital})
	await frame()
	view.actions.submit_frame({"digital":[]})
	await frame()

func play_route(view, skip: bool) -> bool:
	for id in route:
		print("STEP ", id, " tick=", view.actions.tick, " phase=", view.scene_cards.phase, " room=", view.runtime.state.location)
		if not await settle(view, skip):
			expect(false, "route stalled before %s (phase %s, frozen %s, transition %s)" % [id, view.scene_cards.phase, view.scene_cards.frozen, view.room_transition.phase]); return false
		if view.scene_cards.phase == "results": break
		var idx := -1
		for i in view.ui_actions.size():
			if view.ui_actions[i].id == id: idx = i
		if idx < 0:
			expect(false, "route action not offered: " + str(id)); return false
		var before: Dictionary = view.runtime.state.duplicate(true)
		await press(view, ["action_menu"])
		var guard := 0
		while view.menu_index != idx and guard < 60:
			await press(view, ["move_down"]); guard += 1
		if not view.menu_open or view.menu_index != idx:
			expect(false, "menu could not select %s (open %s index %d want %d)" % [id, view.menu_open, view.menu_index, idx]); return false
		await press(view, ["primary"])
		if view.runtime.state == before:
			expect(false, "menu confirm did not dispatch " + str(id)); return false
	return await settle(view, skip, 6000) and view.scene_cards.phase == "results"

func record_route(label: String, opts: Dictionary, skip: bool) -> Dictionary:
	var view = boot(opts)
	var path := "user://scenes-test/%s.h64movie.json" % label
	expect(view.replay.start_record(path).ok, label + ": recording starts at boot")
	var finished := await play_route(view, skip)
	if view.replay.recording: view.replay.stop_record()
	var d = view.scene_cards
	var out := {"finished":finished, "code":str(d.results_receipt.get("code", "")), "receipts":d.receipts.duplicate(true),
		"results":d.results_receipt.duplicate(true), "movie":view.replay.movie.duplicate(true), "cursor":view.replay.cursor,
		"final":view.replay.digest(view.replay.state()), "cues":d.cue_log.duplicate(true), "watchdog":d.watchdog.size()}
	await drop(view)
	return out

func playback(label: String, movie: Dictionary, opts: Dictionary) -> Dictionary:
	var view = boot(opts)
	var begun: Dictionary = view.replay.begin_playback(movie, false)
	expect(begun.ok, label + ": playback accepted " + str(begun))
	for i in (movie.get("frames", []) as Array).size() + 4000:
		if view.replay.finished or not begun.ok: break
		await frame()
	await settle(view, false, 3000)
	var d = view.scene_cards
	var out := {"result":view.replay.result.duplicate(true), "final":view.replay.digest(view.replay.state()),
		"code":str(d.results_receipt.get("code", "")), "receipts":d.receipts.duplicate(true), "phase":d.phase}
	await drop(view)
	return out

func short_record(label: String, opts: Dictionary, idle_ticks := 150) -> Dictionary:
	var view = boot(opts)
	expect(view.replay.start_record("user://scenes-test/%s.h64movie.json" % label).ok, label + ": record")
	await settle(view)
	for i in idle_ticks: await frame()
	view.replay.stop_record()
	var out := {"movie":view.replay.movie.duplicate(true), "receipts":view.scene_cards.receipts.duplicate(true)}
	await drop(view)
	return out

func clock_held(receipts: Array) -> bool:
	if receipts.is_empty(): return false
	for r in receipts:
		if int(r.tick_start) != int(r.tick_end) or int(r.cursor_start) != int(r.cursor_end): return false
	return true

func run() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--output="): output = a.trim_prefix("--output=")
	var data = JSON.parse_string(FileAccess.get_file_as_string("res://scenes_route.json"))
	route = data.actions
	report.route_actions = route.size()

	# Pure shot language: reduced motion uses the end framing; every kind is finite.
	for kind in Director.SHOTS:
		var s := {"kind":kind, "from":[1,2,3], "look":[4,1,2], "to":[2,2,2], "look_to":[5,1,5], "radius":3, "sweep_deg":90, "offset":[0,2,3]}
		var p0: Dictionary = Director.shot_pose(s, 0.0, Vector3(5, 0, 5))
		var p1: Dictionary = Director.shot_pose(s, 1.0, Vector3(5, 0, 5))
		expect(p0.from.is_finite() and p1.from.is_finite() and p0.look.is_finite(), "shot %s is finite" % kind)
		if kind in ["push", "pan", "orbit"]: expect(p0.from != p1.from or p0.look != p1.look, "shot %s moves" % kind)
	var bp := "user://scenes-test/best-unit.json"
	DirAccess.remove_absolute(bp)
	expect(BestStore.record("g", 900, "a", bp).new_best and not BestStore.record("g", 950, "b", bp).new_best and BestStore.record("g", 800, "c", bp).new_best and BestStore.best("g", bp) == 800, "local best keeps the lowest time")

	# A: record the real-input route, watching every scene.
	var a := await record_route("run-a", {}, false)
	report.a = {"finished":a.finished, "code":a.code, "cursor":a.cursor, "receipts":a.receipts, "results_rows":a.results.get("rows", []), "cues":a.cues}
	expect(a.finished, "A: route reaches the results card")
	var ids: Array = a.receipts.map(func(r): return r.id)
	expect(ids == ["arrival", "to_workstation", "night_ends"], "A: three scenes played in order " + str(ids))
	expect(clock_held(a.receipts), "A: no tick, movie frame or clock advanced while any card showed")
	expect(a.code.length() == 12 and a.code.is_valid_hex_number(), "A: 12-hex run code " + a.code)
	expect(a.results.get("run", {}).get("source", "") == "STUB_story_clock", "A: Thaw has no combat2 run; stub source named")
	expect(a.watchdog == 0, "A: no watchdog events on valid data")
	expect(a.cues.any(func(c): return c[0] == "results"), "A: results cue raised")
	expect(a.receipts.any(func(r): return r.travel), "A: the door scene ran inside the doorway envelope")

	# B/C: replay the same movie with scenes off and on.
	var b := await playback("B", a.movie, {"scenes":false})
	var c := await playback("C", a.movie, {"scenes":true})
	report.b = {"ok":b.result.get("ok", false), "code":b.code, "receipts":b.receipts.size()}
	report.c = {"ok":c.result.get("ok", false), "code":c.code, "receipts":c.receipts.size()}
	expect(b.result.get("ok", false), "B: replay with scenes OFF passes every state hash " + str(b.result.get("reason", "")))
	expect(c.result.get("ok", false), "C: replay with scenes ON passes every state hash " + str(c.result.get("reason", "")))
	expect(b.receipts.is_empty() and c.receipts.size() == 3, "B played no scenes, C played three")
	expect(b.final == a.final and c.final == a.final, "A/B/C final state digests equal")
	expect(b.code == a.code and c.code == a.code, "run code identical live, replay-off and replay-on")

	# D: same inputs, every scene skipped by a key press. Movie must be byte-identical.
	var d := await record_route("run-d", {}, true)
	report.d = {"finished":d.finished, "code":d.code, "skipped":d.receipts.map(func(r): return r.skipped)}
	expect(d.finished and d.receipts.size() == 3 and d.receipts.all(func(r): return r.skipped), "D: all three scenes skipped by key")
	expect(JSON.stringify(d.movie, "", true, true) == JSON.stringify(a.movie, "", true, true), "D: skipping changes no movie byte")
	expect(d.code == a.code and d.final == a.final, "D: same run code and final state as A")

	# Controls (each must be detected).
	var tele := await short_record("bad-teleport", {"fault":"teleport"})
	var tb := await playback("bad-teleport-replay", tele.movie, {"scenes":false})
	report.control_teleport = {"replay_ok":tb.result.get("ok", false), "reason":tb.result.get("reason", ""), "tick":tb.result.get("tick", -1)}
	expect(not tb.result.get("ok", true), "CONTROL: a scene that moves the player desyncs the replay and is caught")
	var nf := await short_record("bad-nofreeze", {"fault":"no_freeze"})
	report.control_no_freeze = {"clock_held":clock_held(nf.receipts), "receipts":nf.receipts}
	expect(not clock_held(nf.receipts), "CONTROL: a scene that does not freeze advances the clock and is caught")
	var fz := await record_route("bad-freeze-now", {"fault":"freeze_now"}, true)
	var fb := await playback("bad-freeze-now-replay", fz.movie, {"scenes":false})
	report.control_freeze_now = {"replay_ok":fb.result.get("ok", false), "reason":fb.result.get("reason", ""), "code_live":fz.code, "code_replay":fb.code}
	expect(not fb.result.get("ok", true) or fb.code != fz.code, "CONTROL: freezing inside the tick (no tail barrier) breaks replay equality")

	# Never-ending card: refused by validation; the runtime watchdog still ends it.
	var w = boot({})
	await settle(w, true)
	var forever := {"id":"forever", "trigger":{"on":"enter", "room":"pod_bay"}, "cards":[{"room":"pod_bay", "hold":1000000000, "shot":{"kind":"hold", "from":[7, 3, 10], "look":[7, 1, 6]}}]}
	w.scene_cards.request(forever)
	var frames := 0
	while w.scene_cards.phase != "idle" and frames < 2400:
		await frame(); frames += 1
	report.control_forever = {"frames":frames, "watchdog":w.scene_cards.watchdog.size()}
	expect(w.scene_cards.phase == "idle" and frames <= 1800 + 60 and w.scene_cards.watchdog.size() == 1, "CONTROL: never-ending card is flagged and ended by the watchdog (%d frames)" % frames)
	# Movement works after scenes (no softlock): walk forward for 30 ticks.
	var before: Vector3 = w.player.position
	for i in 30:
		w.actions.submit_frame({"digital":["move_up"]}); await frame()
	expect(w.player.position.distance_to(before) > 0.3, "player moves after scenes end (no softlock)")
	await drop(w)

	# Reduced motion: quick fades, end framing, same canonical outcome.
	var r = boot({"reduced":true})
	var t0 := 0
	while r.scene_cards.phase != "card" and t0 < 600:
		await frame(); t0 += 1
	var expect_pose: Dictionary = Director.shot_pose(r.scene_cards.shot, 1.0, Vector3.ZERO)
	var cam: Vector3 = r.scene_cards.stage_cam.global_position
	report.reduced = {"frames_to_card":t0, "reduced":r.scene_cards.reduced, "fade_kind":r.scene_cards.fade_kind}
	expect(r.scene_cards.reduced and t0 <= 12, "reduced motion: card shows after a quick fade (%d frames)" % t0)
	expect(cam.distance_to(expect_pose.from) < 0.01, "reduced motion: camera holds the end framing")
	await settle(r, true)
	await drop(r)

	# Results card: keys move the choice and confirm; Save replay writes the movie.
	var v = boot({})
	v.replay.start_record("user://scenes-test/run-k.h64movie.json")
	await play_route(v, true)
	var dd = v.scene_cards
	expect(dd.phase == "results", "results card shown at the ending")
	if dd.results == null:
		await finish(); return
	await key(KEY_RIGHT)
	expect(dd.results.selected() == "save", "Right selects SAVE REPLAY")
	await key(KEY_ENTER)
	var saved := str(dd.results_receipt.get("saved", ""))
	expect(saved != "" and FileAccess.file_exists(saved), "Save replay wrote " + saved)
	if saved != "":
		var back = JSON.parse_string(FileAccess.get_file_as_string(saved))
		expect(back is Dictionary and Director.canonical_text(back).sha256_text().substr(0, 12) == dd.results.code, "saved file hashes to the shown run code")
	await key(KEY_LEFT)
	await key(KEY_ENTER)
	expect(dd.has_meta("again"), "AGAIN calls the restart handler")
	report.results_rows = dd.results.rows()
	await drop(v)
	await finish()

func finish() -> void:
	report.ok = failures.is_empty()
	report.checks = checks
	report.failures = failures
	if output != "":
		var f := FileAccess.open(output, FileAccess.WRITE)
		f.store_string(JSON.stringify(report, "\t", true)); f.close()
	print("SCENES_FLOW checks=%d failures=%d" % [checks, failures.size()])
	quit(0 if failures.is_empty() else 1)
