extends SceneTree
## Native production-room regression: before FEEL2 these routes crossed a placed prop.
const Room = preload("res://view/room.gd")
const Player = preload("res://view/player.gd")
const Runtime = preload("res://core/runtime.gd")
const Resolver = preload("res://view/assets.gd")
const Wire = preload("res://core/wire.gd")
var failures := []
var checks := 0
var measurements := []
var trace := []
var room
var player
var actions
var runtime
var resolver

func check(ok: bool, label: String) -> void:
	checks += 1
	if not ok: failures.append(label); printerr("FAIL ", label)

func _initialize() -> void:
	call_deferred("run")

func fixture() -> void:
	runtime = Runtime.new()
	runtime.configure(Wire.read_json("res://game.json"))
	# Missing optional art is a real production fallback, not a test-only collider.
	resolver = Resolver.new()
	resolver.mapping = {}
	runtime.game.metadata.presentation.rooms["solid_test"] = {"floor":"", "kit_shell":true,"pieces":[{"asset":"optional_missing_terrain","position":[6,0,9],"scale":[3,1,1]}]}
	var data := {"id":"solid_test", "grid_size":[12,12], "props":[{"id":"crate", "asset":"optional_missing_crate", "position":[6,0,6], "rotation":[0,0,0]}], "doors":[], "character_ids":[], "cameras":[]}
	room = Room.new()
	room.build(data, runtime, resolver)
	root.add_child(room)
	actions = load("res://input/actions.gd").new()
	player = Player.new()
	player.actions = actions
	player.bounds = Vector2(12,12)
	root.add_child(player)
	player.set_physics_process(false)

func reset_player(at: Vector3) -> void:
	player.position = at
	player.velocity = Vector3.ZERO
	actions.restore({})

func tick(buttons := []) -> void:
	actions.advance({"digital":buttons})
	player.motion_tick()
	trace.append([player.position.x,player.position.y,player.position.z,player.velocity.x,player.velocity.y,player.velocity.z,player.facing_yaw])
	await physics_frame

func run() -> void:
	fixture()
	reset_player(Vector3(3,0.01,6))
	await physics_frame
	for i in 180: await tick(["move_right"])
	check(player.position.x < 5.5, "old crossed-prop route is blocked by Room.build in production motion_tick")
	check(player.actual_velocity.length() < 0.02, "blocked actor stops rather than walking in place")
	measurements.append({"case":"straight_prop", "position":str(player.position), "velocity":str(player.actual_velocity)})
	reset_player(Vector3(3,0.01,6))
	await physics_frame
	var hit: KinematicCollision3D = player.move_and_collide(Vector3(8,0,0))
	check(hit != null and player.position.x < 5.5, "module move_and_collide impulses cannot tunnel through room props")
	measurements.append({"case":"module_impulse", "position":str(player.position), "collided":hit != null})
	reset_player(Vector3(3,0.01,9))
	await physics_frame
	for i in 120: await tick(["move_right"])
	check(player.position.x < 5.0,"missing-art terrain fallback preserves the authored placement scale")
	reset_player(Vector3(4.5,0.01,5.5))
	await physics_frame
	var blocked_ticks := 0
	var max_blocked := 0
	var entered := false
	# Walk/run default is another FEEL2 lane's tuning; allow the slower legal
	# walk to clear the corner without relaxing the no-penetration/stick bound.
	for i in 240:
		var before: Vector3 = player.position
		await tick(["move_right","move_down"])
		blocked_ticks = blocked_ticks+1 if player.position.distance_to(before)<0.005 else 0
		max_blocked = maxi(max_blocked,blocked_ticks)
		entered = entered or (player.position.x>5.65 and player.position.x<6.35 and player.position.z>5.65 and player.position.z<6.35)
	check(not entered,"glancing diagonal never enters the solid prop")
	check(player.position.x>6.6 and player.position.z>7.2 and max_blocked<8,"glancing wall/corner slides smoothly without a sticking streak")
	measurements.append({"case":"glancing_slide","position":str(player.position),"longest_blocked_streak":max_blocked})
	# A visual transform is not a simulation input after geometry is frozen.
	room.get_node("props/crate").position = Vector3(1,0,6)
	reset_player(Vector3(3,0.01,6)); await physics_frame
	for i in 120: await tick(["move_right"])
	check(player.position.x<5.5,"changing a renderer node cannot move its immutable simulation footprint")
	print("FEEL2_SOLIDS ", JSON.stringify({"checks":checks, "failures":failures, "measurements":measurements,"motion_sha256":JSON.stringify(trace,"",true,true).sha256_text()}))
	player.free(); room.free(); actions.free()
	await process_frame
	quit(0 if failures.is_empty() else 1)
