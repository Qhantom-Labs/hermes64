extends SceneTree
## Robot kit art seam (characters/combat/robotkit.json). Run by tools/robots_build.py (godot) on a confined runtime
## copy with city_arena_test's game, its walker / brute / drone archetypes renamed to one livery's robot kit ids, and
## the combat art staged by the production seam (characters.integration.stage_runtime -> combat.json).
## A: the module host's own lookup (host.gd enemy_art / robot_standin) resolves each of the three archetypes to the
##    robot kit row of its own id, with no stand-in; the boss archetype still resolves to the stock boss row; with
##    the robot kit rows removed the three fall back to the stock robot of their template (the check is not vacuous).
## B and C: the checks of tests/merge5_robots.gd on each robot kit GLB: production resolver load (hash check), every
##    FSM clip bound, every key of every enemy clip is the key on the skeleton, visor cells per clip, drone lift from
##    its own clips, measured triangles == the row and <= the cap (the recipe budget, passed as --cap).
const Host = preload("res://modules/host.gd")
const Resolver = preload("res://actors/assets.gd")
const AnimationState = preload("res://modules/animation_state.gd")
const ROBOT_TEMPLATES := ["walker_patrol_v1", "brute_slam_v1", "hover_drone_v1", "boss_phases_v1"]
var world: Node3D
var failures := []
var checks := 0
var report := {}

func expect(value: bool, label: String) -> void:
	checks += 1
	if not value: failures.append(label)

func _initialize() -> void:
	call_deferred("run")

func user_arg(name: String, fallback := "") -> String:
	var args := OS.get_cmdline_user_args()
	var at := args.find(name)
	return args[at + 1] if at >= 0 and at + 1 < args.size() else fallback

func robot_archetypes(game: Dictionary) -> Array:
	var out := []
	for module in game.get("gameplay", {}).get("modules", []):
		for row in module.get("entities", {}).get("archetypes", []):
			if str(row.get("fsm", {}).get("template", "")) in ROBOT_TEMPLATES: out.append(row)
	return out

## Every rotation track of the clip: the skeleton holds the value of the key at k/15 s (as tests/merge3_combat.gd).
func key_mismatches(actor, clip: String, key: int) -> Array:
	var anim: Animation = actor.animation.get_animation(clip)
	var bad := []
	var compared := 0
	for i in anim.get_track_count():
		if anim.track_get_type(i) != Animation.TYPE_ROTATION_3D: continue
		var bone := String(anim.track_get_path(i)).get_slice(":", 1)
		var index: int = actor.skeleton.find_bone(bone)
		if index < 0: continue
		compared += 1
		var expected: Quaternion = anim.track_get_key_value(i, anim.track_find_key(i, float(key) / 15.0))
		var actual: Quaternion = actor.skeleton.get_bone_pose_rotation(index)
		if not actual.is_equal_approx(expected) and not actual.is_equal_approx(-expected): bad.append("%s:%d:%s" % [clip, key, bone])
	if compared == 0: bad.append("%s: no rotation tracks compared" % clip)
	return bad

func triangles(node: Node) -> int:
	var total := 0
	if node is MeshInstance3D and node.mesh != null:
		for s in node.mesh.get_surface_count():
			var arrays: Array = node.mesh.surface_get_arrays(s)
			var index = arrays[Mesh.ARRAY_INDEX]
			total += (index.size() if index != null else arrays[Mesh.ARRAY_VERTEX].size()) / 3
	for child in node.get_children(): total += triangles(child)
	return total

func face_offset(actor) -> Vector2:
	if actor.faces.is_empty(): return Vector2(-1, -1)
	return actor.faces[0].material.get_shader_parameter("uv_offset")

func lookup(game: Dictionary, art: Dictionary) -> void:
	var host = Host.new()
	host.combat_art = art
	var kit: Array = art.get("robotkit_art", {}).get("rows", [])
	var stripped: Dictionary = art.duplicate(true)
	var rows := {}
	for row in robot_archetypes(game):
		var real = host.enemy_art(row)
		var got: String = str(real.id) if real is Dictionary else "null"
		if row.id in kit:
			expect(got == row.id and real.template == row.fsm.template, "%s resolves to the robot kit row of its own id and template (got %s)" % [row.id, got])
			stripped.enemies.erase(row.id)
		else:
			expect(got == art.get("templates", {}).get(row.fsm.template, ""), "%s (%s) still resolves to its stock template alias (got %s)" % [row.id, row.fsm.template, got])
		expect(host.robot_standin(row).is_empty(), "%s: no stand-in scale/lift" % row.id)
		rows[row.id] = {"template": row.fsm.template, "model": got}
	host.combat_art = stripped
	for row in robot_archetypes(game):
		if not row.id in kit: continue
		var fallback = host.enemy_art(row)
		var alias: String = art.get("templates", {}).get(row.fsm.template, "")
		expect(fallback is Dictionary and fallback.id == alias and alias != row.id, "%s falls back to the stock robot %s without its robot kit row" % [row.id, alias])
		rows[row.id]["without_robot_kit"] = alias
	host.free()
	expect(kit.size() == 3, "three robot kit rows staged (walker, brute, drone of one livery): %d" % kit.size())
	report["lookup"] = rows

func models(art: Dictionary, cap: int) -> void:
	var resolver = Resolver.new()
	resolver.configure({"assets": {}, "characters": []}, {})
	var out := {}
	for id in art.get("robotkit_art", {}).get("rows", []):
		var row: Dictionary = art.enemies[id]
		var actor = resolver.enemy_actor(row)
		expect(actor != null, "robot GLB loads through the production resolver (hash-checked): " + id)
		if actor == null: continue
		world.add_child(actor)
		var state = AnimationState.new()
		state.face_cells = row.get("face_atlas", {}).get("clip_cells", {})
		state.bind(actor, row.clips)
		expect(not state.placeholder, "robot clips bound: " + id)
		for fsm in row.fsm_state_clip:
			expect(actor.animation.has_animation(row.fsm_state_clip[fsm]), "%s plays FSM state %s (%s)" % [id, fsm, row.fsm_state_clip[fsm]])
		var bad := []
		for clip in ["idle_combat", "move", "telegraph", "attack", "recover", "hurt", "death"]:
			for key in 16:
				state.show(clip, key)
				bad.append_array(key_mismatches(actor, clip, key))
		expect(bad.is_empty(), "%s every enemy clip key is the key on the skeleton (bad %s)" % [id, str(bad.slice(0, 6))])
		# Visor: calm at rest, flare on telegraph/attack, hurt, off at death (the GLB's own clip cells).
		var seen := {}
		for clip in ["idle_combat", "telegraph", "attack", "hurt", "death"]:
			state.show(clip, 0)
			seen[clip] = face_offset(actor)
		expect(not actor.faces.is_empty(), id + " has the visor face atlas (cast convention)")
		expect(seen.idle_combat != seen.telegraph and seen.telegraph == seen.attack and seen.hurt != seen.idle_combat and seen.death != seen.idle_combat, "%s visor changes per clip %s" % [id, str(seen)])
		state.show("idle_combat", 0)
		var root_bone: int = actor.skeleton.find_bone("root")
		var lift: float = actor.skeleton.get_bone_pose_position(root_bone).y if root_bone >= 0 else 0.0
		if row.template == "hover_drone_v1": expect(lift > 0.15, "%s hovers over its contact shadow from its own clips (root y %.3f)" % [id, lift])
		else: expect(absf(lift) < 0.05, "%s stands on the floor (root y %.3f)" % [id, lift])
		# The model as loaded (the actor's contact-shadow disk is not part of the GLB) == the GLB's own triangles.
		var tris := triangles(actor.model)
		expect(tris == int(row.tris_glb), "%s measured triangles %d == the GLB's %d" % [id, tris, int(row.tris_glb)])
		expect(tris <= cap, "%s triangles %d <= actor cap %d" % [id, tris, cap])
		var size: AABB = bounds(actor.model)
		out[id] = {"template": row.template, "clips": row.clips.size(), "tris": tris, "root_y_idle": snappedf(lift, 0.001),
				   "idle_height_m": snappedf(size.position.y + size.size.y, 0.001), "idle_bottom_m": snappedf(size.position.y, 0.001),
				   "visor_offsets": seen.values().map(func(v): return [snappedf(v.x, 0.01), snappedf(v.y, 0.01)])}
		state.release()
		actor.free()
	expect(resolver.missing.is_empty(), "no robot model missing or hash-mismatched (%s)" % str(resolver.missing.keys()))
	expect(out.size() == 3, "three robot kit models checked: %d" % out.size())
	report["models"] = out

## Rest-mesh bounds of the loaded model in the actor's space (unskinned vertices; the robots are rigid parts).
func bounds(node: Node) -> AABB:
	var box := AABB()
	var first := true
	for mesh in node.find_children("*", "MeshInstance3D", true, false):
		var b: AABB = mesh.get_aabb()
		box = b if first else box.merge(b)
		first = false
	return box

func run() -> void:
	var wire = preload("res://core/wire.gd")
	var game: Dictionary = wire.read_json("res://game.json")
	var art: Dictionary = wire.read_json("res://combat.json") if FileAccess.file_exists("res://combat.json") else {}
	expect(not art.is_empty(), "combat art staged (res://combat.json)")
	world = Node3D.new()
	root.add_child(world)
	await physics_frame
	if not art.is_empty():
		report["pack"] = art.get("pack", "")
		lookup(game, art)
		models(art, int(user_arg("--cap", "250")))
	world.free()
	var out := user_arg("--report")
	if out != "":
		var file := FileAccess.open(out, FileAccess.WRITE)
		expect(file != null, "report file writable: " + out)
		if file != null:
			file.store_string(JSON.stringify({"checks": checks, "failures": failures, "report": report}, "  ", true))
			file.close()
	print("ROBOTKIT checks=%d failures=%d" % [checks, failures.size()])
	for f in failures: print("FAIL ", f)
	quit(0 if failures.is_empty() else 1)
