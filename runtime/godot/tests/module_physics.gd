extends SceneTree
const Combat = preload("res://modules/combat/runtime.gd")
const Adapter = preload("res://modules/input_adapter.gd")
const Player = preload("res://view/player.gd")
var world: Node3D
var player
var failures := []
var checks := 0
var game: Dictionary
func expect(value: bool, label: String) -> void:
	checks += 1
	if not value: failures.append(label)
func _initialize() -> void:
	call_deferred("run")
func box(at: Vector3, size: Vector3) -> StaticBody3D:
	var body := StaticBody3D.new()
	var shape := CollisionShape3D.new()
	var mesh := BoxShape3D.new()
	mesh.size = size
	shape.shape = mesh
	body.add_child(shape)
	world.add_child(body)
	body.position = at
	return body
func fixture():
	var r = preload("res://core/runtime.gd").new()
	r.configure(game)
	var combat = Combat.new()
	var enc: Dictionary = r.modules.entities("combat","encounters").values()[0].duplicate(true)
	enc.spawns = [enc.spawns[0]]
	enc.spawns[0].position_m = [8,0,6.6]
	var kinds: Dictionary = r.modules.entities("combat","archetypes").duplicate(true)
	for e in kinds.values(): e.attack.windup_ticks = 60; e.max_health = 8
	player.position = Vector3(8,0.02,8)
	player.rotation = Vector3.ZERO
	player.velocity = Vector3.ZERO
	combat.begin(enc, kinds, player, world, 6, 7)
	return combat
func replay() -> Array:
	var combat = fixture()
	var input = Adapter.new()
	var hashes := []
	for tick in 120:
		input.inject(Vector2.ZERO, ["focus", "primary"] if tick % 32 == 0 else ["focus"])
		combat.tick(input)
		hashes.append(JSON.stringify(combat.snapshot(),"",true).sha256_text())
	combat.dispose()
	return hashes
func run() -> void:
	game = preload("res://core/wire.gd").read_json("res://module-vectors.json")[0].game
	world = Node3D.new()
	root.add_child(world)
	player = Player.new()
	world.add_child(player)
	player.set_physics_process(false)
	box(Vector3(8,-0.1,8), Vector3(16,0.2,16))
	await physics_frame
	await process_frame
	var input = Adapter.new()
	var combat = fixture()
	await physics_frame
	await process_frame
	input.inject(Vector2.ZERO, ["primary", "focus"])
	combat.tick(input)
	input.consume()
	for i in 7: combat.tick(input)
	expect(combat.enemies[0].hp == 8, "no windup damage")
	combat.tick(input)
	expect(combat.enemies[0].hp == 7, "active first tick damages once")
	for i in 6: combat.tick(input)
	expect(combat.enemies[0].hp == 7, "overlap deduplicates swing victim")
	combat.dispose()
	combat = fixture()
	var wall := box(Vector3(8,0.8,7.3), Vector3(2,2,0.1))
	await physics_frame
	await process_frame
	input.clear(); input.inject(Vector2.ZERO,["primary","focus"])
	combat.tick(input); input.consume()
	for i in 20: combat.tick(input)
	expect(combat.enemies[0].hp == 8 and combat.target == "", "wall occludes damage and targeting")
	wall.free(); combat.dispose()
	combat = fixture()
	combat.enemies[0].body.position = Vector3(8,0.02,7)
	combat.enemies[0].transition("attack")
	input.clear(); input.inject(Vector2.ZERO,["dodge","focus"])
	combat.tick(input)
	expect(combat.health == 6 and combat.rolls == 1, "roll iframe avoids real contact")
	combat.dispose()
	combat = fixture()
	combat.block_available = true
	combat.enemies[0].body.position = Vector3(8,0.02,7)
	combat.enemies[0].transition("attack")
	input.clear(); input.inject(Vector2.ZERO,["secondary"])
	combat.tick(input)
	expect(combat.health == 6 and combat.blocks == 1, "bound block avoids frontal damage")
	combat.dispose()
	combat = fixture()
	combat.health = 1; combat.enemies[0].hp = 1
	combat.enemies[0].body.position = Vector3(8,0.02,7)
	combat.enemies[0].transition("attack")
	combat.age = Combat.WINDUP
	input.clear(); input.inject(Vector2.ZERO,["focus"])
	combat.tick(input)
	expect(combat.health == 0 and combat.result == "failed", "simultaneous KO loses")
	combat.dispose()
	combat = fixture()
	combat.enemies[0].data.attack.windup_ticks = 2
	combat.enemies[0].data.attack.active_ticks = 1
	combat.enemies[0].body.position = Vector3(8,0.02,7)
	combat.enemies[0].transition("telegraph")
	var contact := []
	for i in 4: contact.append(combat.enemies[0].tick(player.position))
	expect(contact == [false,false,true,false], "one-tick enemy active window cannot disappear")
	combat.dispose()
	var first := replay()
	var second := replay()
	expect(first == second, "same fixed inputs exact state hashes")
	# Host and its presentation dependencies must compile, not merely exist.
	expect(load("res://modules/host.gd").can_instantiate(), "host script compiles")
	expect(load("res://modules/view.gd").can_instantiate(), "module entry compiles")
	world.free()
	print("MODULE_PHYSICS checks=%d failures=%d" % [checks,failures.size()])
	for f in failures: print("FAIL ",f)
	quit(0 if failures.is_empty() else 1)
