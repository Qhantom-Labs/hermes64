extends SceneTree
## Lifecycle integration assertions. Test arrangement is NOT a physical-bot receipt.
const View = preload("res://playtest/module_view.gd")
var checks := 0
var failures := []
var view
func expect(value: bool, label: String) -> void:
	checks += 1
	if not value: failures.append(label)
func frames(count: int) -> void:
	for i in count:
		await physics_frame
		await process_frame
func _initialize() -> void: call_deferred("run")
func run() -> void:
	view = View.new(); root.add_child(view)
	var game = preload("res://core/wire.gd").read_json("res://module-vectors.json")[3].game
	var booted: Dictionary = view.boot(game,{"save":"res://lifecycle-save.json"})
	expect(booted.ok,"real module presenter boots with fixture art")
	var host = view.module_host
	await frames(2)
	expect(not view.dispatch("assume:complete:gate_trial").ok,"view refuses analysis outcome")
	view.dispatch("interact:learn")
	var door: String = "move:hub:to_arena"
	view.player.position = host.anchor(door)
	var before: Dictionary = view.runtime.state.duplicate(true)
	expect(view.dispatch(door).ok,"portal starts staged preflight")
	var blocker := StaticBody3D.new()
	var collider := CollisionShape3D.new()
	var box := BoxShape3D.new(); box.size = Vector3(2,2,2)
	collider.shape = box; blocker.add_child(collider)
	host.pending.probe.add_child(blocker)
	blocker.position = host.pending.arrival + Vector3.UP * 0.7
	await frames(16)
	expect(view.runtime.state == before and host.transition_errors.size() == 1,"blocked arrival preserves complete prior state")
	view.player.position = host.anchor(door)
	expect(view.dispatch(door).ok,"safe portal retriable after rollback")
	await frames(16)
	expect(view.runtime.state.location == "arena","unblocked portal commits after physics clearance")
	var id := "challenge:start:gate_trial"
	view.player.position = host.anchor(id)
	expect(view.dispatch(id).ok,"challenge entry claims active host")
	expect(not view.save_game().ok,"active fight cannot save")
	var clock: int = host.attempt_tick
	host.set_modal(true); await frames(6)
	expect(host.attempt_tick == clock,"modal freezes challenge clock")
	host.set_modal(false)
	var old_generation: int = host.generation
	view.dispatch("challenge:abort:gate_trial")
	expect(host.generation > old_generation and host.combat == null,"abort destroys actors and invalidates generation")
	await frames(64)
	expect(view.runtime.state.modules.failed == "" and host.retry_ticks == 0,"automatic retry ready within 64 ticks")
	view.player.position = host.anchor(door)
	view.dispatch(door)
	await frames(16)
	view.player.position = host.anchor(id)
	view.dispatch(id)
	host.finish_attempt(true) # reducer idempotency only, not a bot-win claim
	var committed: Dictionary = view.runtime.state.duplicate(true)
	host.finish_attempt(true)
	expect(view.runtime.state == committed and committed.inventory.count("trail_key") == 1,"duplicate terminal notification grants reward once")
	view.player.position = host.anchor("checkpoint:arena_safe")
	view.dispatch("checkpoint:arena_safe")
	committed = view.runtime.state.duplicate(true)
	expect(view.save_game().ok,"ready checkpoint saves")
	var loaded: Dictionary = view.load_game()
	expect(loaded.ok and view.runtime.state == committed and host.combat == null,"load restores finite checkpoint, no live enemies")
	print("MODULE_LIFECYCLE checks=%d failures=%d" % [checks,failures.size()])
	for f in failures: print("FAIL ",f)
	await view.quit_cleanly(0 if failures.is_empty() else 1)
