extends SceneTree
## Authored start is subordinate to door/save entry and the native capsule check.
const View = preload("res://playtest/view.gd")
const Wire = preload("res://core/wire.gd")
var checks := 0
var failures := []
func check(ok: bool, label: String) -> void:
	checks += 1
	print("PASS " if ok else "FAIL ", label)
	if not ok: failures.append(label)
func _initialize() -> void: call_deferred("run")
func run() -> void:
	var view = View.new()
	root.add_child(view)
	var game: Dictionary = Wire.read_json("res://game.json")
	var booted: Dictionary = view.boot(game,{"pack":"res://theme.json","bindings":"res://bindings.json","test":true,"save":"user://tbuild-entry.json"})
	check(booted.ok,"ordinary shipped facade boots")
	if not booted.ok:
		await view.quit_cleanly(1)
		return
	view.simulation_enabled = false
	view.player.simulation_enabled = false
	var rid: String = view.runtime.state.location
	var legacy: Vector3 = view.player.position
	var target := legacy
	for shift in [Vector3(1,0,0),Vector3(-1,0,0),Vector3(0,0,1),Vector3(0,0,-1)]:
		if view.player.room_navigation.point_clear(legacy+shift):
			target = legacy+shift
			break
	check(target.distance_to(legacy)>0.5,"fixture has a distinct capsule-clear authored start")
	var rooms: Dictionary = view.runtime.game.metadata.get("presentation",{}).get("rooms",{})
	if not rooms.has(rid): rooms[rid] = {}
	view.runtime.game.metadata.get_or_add("presentation",{})["rooms"] = rooms
	rooms[rid]["player_start"] = [target.x,0,target.z]
	view.enter_room("")
	check(Vector2(view.player.position.x,view.player.position.z).distance_to(Vector2(target.x,target.z))<0.02,"authored start is consumed before final capsule placement")
	check(view.player.room_placement.ok,"authored start retains native capsule validation")
	var saved: Dictionary = view.physical_checkpoint()
	saved.position = [legacy.x,legacy.y,legacy.z]
	var restored: Dictionary = view.restore_checkpoint(saved)
	check(restored.ok and view.player.position.distance_to(legacy)<0.02,"disk checkpoint position wins over authored room start")
	# Re-enter this room through any reciprocal source door; door entry still wins.
	var door_tested := false
	for source in view.runtime.rooms.values():
		for door in source.doors:
			if door.to_room != rid: continue
			view.runtime.state.location = rid
			view.enter_room("move:"+str(source.id)+":"+str(door.id))
			check(Vector2(view.player.position.x,view.player.position.z).distance_to(Vector2(target.x,target.z))>0.1,"reciprocal door entry wins over authored room start")
			door_tested = true
			break
		if door_tested: break
	check(door_tested,"reciprocal door override exercised")
	rooms[rid].erase("player_start")
	view.enter_room("")
	check(view.player.position.distance_to(legacy)<0.02,"rooms without authored start retain legacy position")
	print("TBUILD_ENTRY ",JSON.stringify({"checks":checks,"failures":failures,"ok":failures.is_empty()}))
	await view.quit_cleanly(0 if failures.is_empty() else 1)
