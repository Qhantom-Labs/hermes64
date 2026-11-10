extends SceneTree
## Combined production Actions/host assertions; arranged contacts are not bot wins.
const View = preload("res://playtest/view.gd")
var view
var checks := 0
var failures := []
func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok: failures.append(label); print("FAIL ",label)
func frame(keys := []) -> void:
	view.actions.submit_frame({"digital":keys})
	await physics_frame
	await process_frame
func _initialize() -> void: call_deferred("run")
func run() -> void:
	view = View.new(); root.add_child(view)
	var game = preload("res://core/wire.gd").read_json("res://module-vectors.json")[3].game
	var booted: Dictionary = view.boot(game,{"save":"res://merge2-save.json","test":true})
	expect(booted.ok and view.has_meta("module_host"),"ordinary production entry installs module host")
	if not view.has_meta("module_host"):
		await view.quit_cleanly(1); return
	var host = view.get_meta("module_host")
	expect(host.input.provider == view.actions,"real singleton is sole module provider")
	view.actions.set_source("bot")
	await frame()
	view.dispatch("interact:learn")
	view.player.position = host.anchor("move:hub:to_arena")
	view.dispatch("move:hub:to_arena")
	await frame(["menu"])
	var transition_tick: int = host.pending.ticks
	for i in 20: await frame(["move_right"])
	expect(not host.pending.is_empty() and host.pending.ticks == transition_tick,"Esc freezes region preflight as well as player")
	await frame(["menu"]); await frame()
	for i in 16: await frame()
	expect(view.runtime.state.location == "arena","preflight resumes and commits")
	view.player.position = host.anchor("challenge:start:gate_trial")
	await frame()
	expect(view.context_candidate().get("id","") == "challenge:start:gate_trial","physical challenge anchor participates in E prompts")
	await frame(["primary"]); await frame()
	expect(host.combat != null,"E starts real combat")
	if host.combat == null:
		await view.quit_cleanly(1); return
	var original_story: Dictionary = view.runtime.state.duplicate(true)
	await frame(["focus","primary"])
	expect(host.combat.swings == 1 and view.runtime.state == original_story,"combat E swings without story dispatch")
	expect(view.player.rotation == Vector3.ZERO,"combat focus preserves axis-aligned capsule")
	await frame(["inventory"])
	var clock: int = host.attempt_tick
	var position: Vector3 = view.player.position
	for i in 10: await frame(["move_right","primary","dodge"])
	expect(host.attempt_tick == clock and view.player.position == position,"inventory freezes module timers and mover")
	await frame(["secondary"]); await frame()
	for i in 35: await frame()
	await frame(["action_menu"])
	clock = host.attempt_tick
	await frame()
	expect(host.attempt_tick == clock,"Tab pauses real combat")
	await frame(["secondary"]); await frame()
	expect(host.combat != null,"cancel menu preserves live combat for dodge assertion")
	# Arrange an imminent contact, then send the actual Space semantic input.
	if host.combat != null:
		host.combat.age = -1; host.combat.hurt_age = -1
		var enemy = host.combat.enemies[0]
		enemy.body.position = view.player.position + Vector3(0,0,-0.8)
		enemy.transition("attack")
		var hp: int = host.combat.health
		await frame(["dodge","focus"])
		expect(host.combat.rolls > 0 and host.combat.health == hp,"real Actions dodge iframe protects actual contact")
		var after: Vector3 = view.player.position
		await frame(["menu"])
		for i in 12: await frame(["move_right"])
		expect(view.player.position == after,"pause freezes an in-progress module impulse")
		await frame(["menu"]); await frame()
	view.dispatch("challenge:abort:gate_trial")
	for i in 65: await frame()
	expect(host.combat == null and host.retry_ticks == 0 and view.runtime.state.modules.failed == "","failure auto-refund ready within 65 ticks")
	expect(view.replay.extensions.has("modules"),"movies hash and restore module authority")
	print("MERGE2_CONTROLS checks=%d failures=%d" % [checks,failures.size()])
	await view.quit_cleanly(0 if failures.is_empty() else 1)
