extends SceneTree
## SCENES lane unit checks: run-state adapter against combat2's real run.gd (copied read-only
## into the staging as res://tests/fixtures/combat2_run.gd by tools/scenes_stage.py), clock
## formatting, results rows, wave label lookup, and the wait-for-key title card (R6).
const RunSource = preload("res://view/run_source.gd")
const Results = preload("res://view/results_card.gd")
var failures := []
var checks := 0
var report := {}
var output := ""

class FakeHost:
	var run
class FakeView:
	var module_host

class FakeModules:
	var challenges := {"wave_1":{"kind":"combat","subject":"enc_1"}, "course_a":{"kind":"course","label":"LAP ONE"}}
	func entities(_m, _c): return {"enc_1":{"label":"WAVE 1  IRON TIDE"}}

func _initialize() -> void: call_deferred("run")
func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok: failures.append(message); print("FAIL ", message)
func frame() -> void:
	await physics_frame
	await process_frame

func run() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--output="): output = a.trim_prefix("--output=")
	expect(RunSource.clock(0) == "00:00.00" and RunSource.clock(60) == "00:01.00" and RunSource.clock(13281) == "03:41.35", "clock mm:ss.cc from ticks")
	expect(RunSource.seconds(1200) == "20.00", "penalty seconds")
	var stub := RunSource.read(FakeView.new(), 777)
	expect(stub.source == "STUB_story_clock" and stub.ticks == 777 and stub.deaths == 0 and stub.penalty_rule == 0, "no run block: named stub source")

	if FileAccess.file_exists("res://tests/fixtures/combat2_run.gd"):
		var run = load("res://tests/fixtures/combat2_run.gd").new()
		run.configure({"death_penalty_ticks":600, "max_health":3, "hit_invulnerability_ticks":45}, true)
		for i in 10: run.advance(i > 2)     # control from tick 3: 7 counted ticks
		run.died(); run.died()
		for i in 5: run.advance(true)
		run.finish()
		for i in 9: run.advance(true)       # after the finish the clock is frozen
		var host := FakeHost.new(); host.run = run
		var view := FakeView.new(); view.module_host = host
		var r := RunSource.read(view, 99999)
		report.combat2 = r
		expect(r.source == "combat2_run", "combat2 run.gd recognised")
		expect(r.ticks == 7 + 1200 + 5 and r.deaths == 2 and r.penalty_ticks == 1200 and r.penalty_rule == 600 and r.finished, "combat2 fields: finished_tick, deaths, penalty " + str(r))
		var card := Results.new()
		card.configure("THE KEEP", r, 900, false, "0123456789ab")
		var rows := card.rows()
		report.rows = rows
		expect(rows.size() == 5 and rows[2] == ["PENALTY", "+20.00"] and rows[0][1] == RunSource.clock(1212), "results rows: TIME DEATHS PENALTY BEST RUN")
		run.configure({}, false)
		expect(RunSource.read(view, 5).source == "STUB_story_clock", "disabled run falls back to the stub")
	else:
		expect(false, "combat2 run.gd fixture missing (stage with --combat2)")
	var no_pen := Results.new()
	no_pen.configure("", {"ticks":120, "deaths":0, "penalty_rule":0}, -1, false, "")
	expect(no_pen.rows().map(func(x): return x[0]) == ["TIME", "DEATHS", "BEST"] and no_pen.rows()[2][1] == "--:--.--", "no penalty row without a penalty rule; no best yet")

	# Wave label consumer and R6 title card on the real presenter.
	var view = load("res://main.tscn").instantiate()
	root.add_child(view)
	view.actions.configure({"version":1})
	var d = view.scene_cards
	d.scenes.insert(0, {"id":"title", "trigger":{"on":"start"}, "cards":[{"room":"pod_bay", "hold":30, "wait":"key", "title":"PRESS START",
		"shot":{"kind":"orbit", "look":[7, 0.8, 6], "radius":6, "height":4, "sweep_deg":20}}]})
	view.actions.set_source("live")
	for i in 150: await frame()
	expect(d.phase == "card" and str(d.scene.get("id", "")) == "title", "title card waits for a key in live play (phase %s)" % d.phase)
	var e := InputEventKey.new(); e.physical_keycode = KEY_ENTER; e.keycode = KEY_ENTER; e.pressed = true
	Input.parse_input_event(e); await frame()
	e = InputEventKey.new(); e.physical_keycode = KEY_ENTER; e.keycode = KEY_ENTER; e.pressed = false
	Input.parse_input_event(e)
	for i in 600:
		if d.receipts.size() >= 1 and str(d.receipts[0].id) == "title": break
		await frame()
	expect(d.receipts.size() >= 1 and str(d.receipts[0].id) == "title", "any key ends the title card")
	var real_modules = view.runtime.modules
	view.runtime.set("modules", FakeModules.new())
	expect(d.label_for("wave_1") == "WAVE 1  IRON TIDE" and d.label_for("course_a") == "LAP ONE" and d.label_for("nope") == "", "wave label from encounter.label, else the challenge label")
	view.runtime.set("modules", real_modules)
	d.show_label("WAVE 1  IRON TIDE")
	expect(d.label_left > 0.0 and d.receipt().label == "WAVE 1  IRON TIDE", "label shows for its time")
	for i in 120: await frame()
	expect(d.label_left == 0.0, "label clears after 1.5 s")
	view.get_parent().remove_child(view); view.queue_free()
	await frame()

	report.ok = failures.is_empty(); report.checks = checks; report.failures = failures
	if output != "":
		var f := FileAccess.open(output, FileAccess.WRITE); f.store_string(JSON.stringify(report, "\t", true)); f.close()
	print("SCENES_UNITS checks=%d failures=%d" % [checks, failures.size()])
	quit(0 if failures.is_empty() else 1)
