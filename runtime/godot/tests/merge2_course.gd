extends SceneTree
const View = preload("res://playtest/view.gd")
var view
var failures := []
var checks := 0
func check(ok: bool, label: String) -> void:
	checks += 1
	if not ok: failures.append(label); print("FAIL ",label)
func frame(keys := []) -> void:
	view.actions.submit_frame({"digital":keys})
	await physics_frame; await process_frame
func _initialize() -> void: call_deferred("run")
func run() -> void:
	view = View.new(); root.add_child(view)
	view.boot(preload("res://core/wire.gd").read_json("res://module-vectors.json")[1].game,{"test":true})
	view.actions.set_source("bot")
	await frame()
	var at: Vector3 = view.player.position
	await frame(["dodge"]); await frame()
	check(view.player.position.distance_to(at)<0.05,"Space cannot dodge outside a challenge")
	view.dispatch("challenge:start:relay_trial")
	var host = view.module_host
	for i in 182: await frame()
	await frame(["dodge","move_left"])
	check(host.get("course_roll_age") != null and int(host.get("course_roll_age")) >= 0,"Space starts course dodge through Actions")
	var before: Vector3 = view.player.position
	for i in 17: await frame(["move_left"])
	check(view.player.position.distance_to(before) > 0.8,"course dodge sweeps actual body")
	check(host.course != null and host.course.invalid_motion == 0,"course dodge respects authored speed ceiling")
	await frame(["action_menu"]); await frame()
	await frame(["dodge"])
	check(not view.actions.just_pressed("dodge") and host.active_id == "","Space confirms Abort in action menu, never rolls")
	for i in 65: await frame()
	check(view.runtime.state.modules.failed == "" and host.retry_ticks == 0,"course abort refunds and releases")
	print("MERGE2_COURSE checks=%d failures=%d" % [checks,failures.size()])
	await view.quit_cleanly(0 if failures.is_empty() else 1)
