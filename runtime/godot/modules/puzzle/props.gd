extends Node3D
## Puzzle room dressing in the pack's N64 look: low-poly procedural pieces with pack textures (stone, metal,
## planks, glass), baked top-down vertex light, the shared n64_world shader (fog, rig, point lights) and
## shipped kit pieces where they fit (prop.key, prop/blue_glass_sphere, prop/lens_crystal).
## Kit seam: a cave/temple kit replaces these builders by mapping the same element kinds to kit refs
## (docs/PUZZLES.md "Kit seam"). Presentation only; never a source of puzzle state.
const N64Mat = preload("res://look/n64_mat.gd")
const Pack = preload("res://look/pack.gd")
const KIT := {"key": "prop.key", "orb": "prop/blue_glass_sphere", "reward": "prop/lens_crystal"}
const BRONZE := Color(0.86, 0.62, 0.36)
const IRON := Color(0.62, 0.64, 0.70)
const EMBER := Color(1.0, 0.62, 0.25)
var rules
var resolver
var nodes := {}        # element id -> Node3D
var blocks := {}       # block id -> Node3D
var flames := {}       # torch id -> Node3D
var marker: Node3D
var reward_node: Node3D
var placeholder_count := 0
var kit_count := 0

static func shade(top: float, side: float, bottom: float, n: Vector3, y: float, h: float) -> float:
	if n.y > 0.5: return top
	if n.y < -0.5: return bottom
	return lerpf(bottom, side, clampf(y / maxf(h, 0.001), 0.0, 1.0))

## Box with UVs in metres and baked vertex light (top bright, sides graded toward the floor).
func box_mesh(size: Vector3, light := Vector3(1.0, 0.78, 0.46), tint := Color.WHITE) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var h := size / 2.0
	var faces := [
		[Vector3.UP, [Vector3(-h.x, h.y, -h.z), Vector3(h.x, h.y, -h.z), Vector3(h.x, h.y, h.z), Vector3(-h.x, h.y, h.z)]],
		[Vector3.DOWN, [Vector3(-h.x, -h.y, h.z), Vector3(h.x, -h.y, h.z), Vector3(h.x, -h.y, -h.z), Vector3(-h.x, -h.y, -h.z)]],
		[Vector3.FORWARD, [Vector3(h.x, -h.y, -h.z), Vector3(-h.x, -h.y, -h.z), Vector3(-h.x, h.y, -h.z), Vector3(h.x, h.y, -h.z)]],
		[Vector3.BACK, [Vector3(-h.x, -h.y, h.z), Vector3(h.x, -h.y, h.z), Vector3(h.x, h.y, h.z), Vector3(-h.x, h.y, h.z)]],
		[Vector3.LEFT, [Vector3(-h.x, -h.y, -h.z), Vector3(-h.x, -h.y, h.z), Vector3(-h.x, h.y, h.z), Vector3(-h.x, h.y, -h.z)]],
		[Vector3.RIGHT, [Vector3(h.x, -h.y, h.z), Vector3(h.x, -h.y, -h.z), Vector3(h.x, h.y, -h.z), Vector3(h.x, h.y, h.z)]]]
	for f in faces:
		var n: Vector3 = f[0]
		var q: Array = f[1]
		var uvs := []
		for v in q:
			var u := Vector2(v.x + v.z, -v.y) if absf(n.y) < 0.5 else Vector2(v.x, v.z)
			uvs.append(u)
		for i in [0, 1, 2, 0, 2, 3]:
			var v: Vector3 = q[i]
			var l := shade(light.x, light.y, light.z, n, v.y + h.y, size.y)
			st.set_color(Color(tint.r * l, tint.g * l, tint.b * l, 1.0))
			st.set_uv(uvs[i])
			st.set_normal(n)
			st.add_vertex(v)
	return st.commit()

## Octagonal prism (pedestals, plates, brazier bowls): 8 sides, capped.
func prism_mesh(radius: float, height: float, top_scale := 1.0, light := Vector3(1.0, 0.8, 0.5), tint := Color.WHITE) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var ring := []
	for i in 8:
		var a := TAU * (i + 0.5) / 8.0
		ring.append(Vector2(cos(a), sin(a)))
	for i in 8:
		var a: Vector2 = ring[i]
		var b: Vector2 = ring[(i + 1) % 8]
		var n := Vector3((a.x + b.x) * 0.5, 0, (a.y + b.y) * 0.5).normalized()
		var quad := [Vector3(a.x * radius, 0, a.y * radius), Vector3(b.x * radius, 0, b.y * radius),
			Vector3(b.x * radius * top_scale, height, b.y * radius * top_scale), Vector3(a.x * radius * top_scale, height, a.y * radius * top_scale)]
		var uv := [Vector2(i * 0.4, 0), Vector2((i + 1) * 0.4, 0), Vector2((i + 1) * 0.4, -height), Vector2(i * 0.4, -height)]
		for k in [0, 2, 1, 0, 3, 2]:
			var l := lerpf(light.z, light.y, quad[k].y / maxf(height, 0.001))
			st.set_color(Color(tint.r * l, tint.g * l, tint.b * l))
			st.set_uv(uv[k]); st.set_normal(n); st.add_vertex(quad[k])
		var top := [Vector3(0, height, 0), Vector3(b.x * radius * top_scale, height, b.y * radius * top_scale), Vector3(a.x * radius * top_scale, height, a.y * radius * top_scale)]
		for v in top:
			st.set_color(Color(tint.r * light.x, tint.g * light.x, tint.b * light.x))
			st.set_uv(Vector2(v.x, v.z)); st.set_normal(Vector3.UP); st.add_vertex(v)
	return st.commit()

func piece(parent: Node3D, label: String, mesh: Mesh, texture: String, pos: Vector3, tint := Color.WHITE) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	mi.name = label
	mi.mesh = mesh
	# Painted pack textures when the look is loaded, else flat vertex-lit surfaces (never a missing palette).
	var m: ShaderMaterial = N64Mat.make(texture if not Pack.palette().is_empty() and (texture == "flat" or texture.begins_with("env_") or not Pack.recipe(texture).is_empty()) else "flat")
	if tint != Color.WHITE: m.set_shader_parameter("tint", tint)
	mi.material_override = m
	mi.position = pos
	mi.set_meta("placed", "puzzle")
	parent.add_child(mi)
	return mi

func kit(parent: Node3D, ref: String, pos: Vector3, scale_by := Vector3.ONE) -> Node3D:
	var node: Node3D = resolver.resolve(ref) if resolver != null else null
	if node == null: return null
	parent.add_child(node)
	node.position = pos
	node.scale = scale_by
	node.set_meta("placed", "puzzle_kit")
	kit_count += 1
	return node

static func centre(c: Vector2i, y := 0.0) -> Vector3:
	return Vector3(c.x + 0.5, y, c.y + 0.5)

func build(r, asset_resolver) -> void:
	rules = r
	resolver = asset_resolver
	name = "puzzle_props"
	set_meta("placed", "puzzle")
	for y in rules.rows:
		for x in rules.cols:
			var c := Vector2i(x, y)
			match rules.terrain(c):
				"#": wall(c)
				"_": pit(c)
	for i in rules.ids:
		var e: Dictionary = rules.el[i]
		match str(e.kind):
			"switch": nodes[i] = lever(i, rules.cell(e.cell))
			"plate": nodes[i] = plate(i, rules.cell(e.cell))
			"torch": nodes[i] = brazier(i, rules.cell(e.cell), int(e.order))
			"lock": nodes[i] = bronze_door(i, rules.cell(e.cell))
			"key": nodes[i] = key_stand(i, rules.cell(e.cell))
			"block": blocks[i] = stone_block(i, rules.cell(e.cell), bool(e.pull))
			"bridge": nodes[i] = bridge(i, e.cells)
			"door", "timed_gate": nodes[i] = portcullis(i, rules.cell(e.cell), e.kind == "timed_gate")
			"orb": nodes[i] = orb(i, rules.cell(e.cell))
			"shutter": nodes[i] = shutter(i, rules.cell(e.cell), str(e.dir))
	marker = Node3D.new()
	marker.name = "focus_marker"
	add_child(marker)
	var gem := piece(marker, "gem", prism_mesh(0.16, 0.22, 0.05, Vector3(1.0, 0.95, 0.85), EMBER), "flat", Vector3.ZERO)
	gem.material_override.set_shader_parameter("emission", 0.35)
	gem.material_override.set_shader_parameter("lit", 0.0)
	var gem2 := piece(marker, "gem_low", prism_mesh(0.16, 0.22, 0.05, Vector3(0.9, 0.8, 0.7), EMBER), "flat", Vector3.ZERO)
	gem2.material_override.set_shader_parameter("lit", 0.0)
	gem2.rotation_degrees.x = 180
	marker.visible = false

func wall(c: Vector2i) -> void:
	var h := 1.5 + 0.18 * float((c.x * 7 + c.y * 13) % 3)
	piece(self, "wall_%d_%d" % [c.x, c.y], box_mesh(Vector3(1.0, h, 1.0), Vector3(1.12, 0.86, 0.48), Color(1.0, 0.94, 0.84)), "stone", centre(c, h / 2.0))
	# a warm capstone row breaks the silhouette like hand-laid masonry
	piece(self, "cap_%d_%d" % [c.x, c.y], box_mesh(Vector3(1.04, 0.14, 1.04), Vector3(1.05, 0.8, 0.55), Color(0.98, 0.9, 0.76)), "stone", centre(c, h + 0.07))

func pit(c: Vector2i) -> void:
	piece(self, "pit_%d_%d" % [c.x, c.y], box_mesh(Vector3(1.0, 0.04, 1.0), Vector3(0.10, 0.08, 0.06), Color(0.55, 0.6, 0.75)), "slate", centre(c, 0.005))
	piece(self, "pit_lip_%d_%d" % [c.x, c.y], box_mesh(Vector3(1.0, 0.06, 0.1), Vector3(0.7, 0.5, 0.4)), "stone", centre(c, 0.03) + Vector3(0, 0, -0.45))

func lever(id: String, c: Vector2i) -> Node3D:
	var root := Node3D.new(); root.name = id; root.position = centre(c); add_child(root)
	piece(root, "base", box_mesh(Vector3(0.62, 0.42, 0.62), Vector3(1.0, 0.8, 0.5)), "stone", Vector3(0, 0.21, 0))
	piece(root, "plate", box_mesh(Vector3(0.44, 0.06, 0.44), Vector3(1.0, 0.8, 0.6), BRONZE), "metal", Vector3(0, 0.45, 0))
	var arm := Node3D.new(); arm.name = "arm"; arm.position = Vector3(0, 0.46, 0); root.add_child(arm)
	piece(arm, "shaft", box_mesh(Vector3(0.08, 0.62, 0.08), Vector3(1.0, 0.85, 0.6), IRON), "metal", Vector3(0, 0.31, 0))
	piece(arm, "knob", prism_mesh(0.09, 0.14, 0.7, Vector3(1.2, 1.0, 0.8), Color(0.75, 0.2, 0.15)), "metal", Vector3(0, 0.6, 0))
	arm.rotation_degrees.x = -35
	return root

func plate(id: String, c: Vector2i) -> Node3D:
	var root := Node3D.new(); root.name = id; root.position = centre(c); add_child(root)
	piece(root, "rim", prism_mesh(0.46, 0.05, 1.0, Vector3(0.9, 0.7, 0.5)), "stone", Vector3.ZERO)
	var top := piece(root, "top", prism_mesh(0.38, 0.08, 0.92, Vector3(1.05, 0.8, 0.6), BRONZE), "metal", Vector3(0, 0.02, 0))
	top.set_meta("rest_y", 0.02)
	var weight := int(rules.el[id].weight)
	for i in weight:  # one or two carved weight pips
		piece(root, "pip%d" % i, box_mesh(Vector3(0.08, 0.02, 0.08), Vector3(0.3, 0.3, 0.3)), "slate", Vector3(-0.08 + 0.16 * i if weight == 2 else 0.0, 0.105, 0))
	return root

func brazier(id: String, c: Vector2i, order: int) -> Node3D:
	var root := Node3D.new(); root.name = id; root.position = centre(c); add_child(root)
	piece(root, "column", prism_mesh(0.24, 0.72, 0.82, Vector3(0.95, 0.78, 0.45)), "stone", Vector3.ZERO)
	piece(root, "foot", prism_mesh(0.34, 0.12, 0.9, Vector3(0.9, 0.7, 0.45)), "stone", Vector3.ZERO)
	piece(root, "bowl", prism_mesh(0.22, 0.2, 1.7, Vector3(1.05, 0.8, 0.55), BRONZE), "metal", Vector3(0, 0.72, 0))
	for i in order:  # carved notches: the lighting order, read without text
		var a := TAU * float(i) / maxf(1.0, float(order)) + PI
		piece(root, "notch%d" % i, box_mesh(Vector3(0.07, 0.07, 0.03), Vector3(1.4, 1.2, 1.0), EMBER), "metal", Vector3(sin(a) * 0.05 * float(order > 1), 0.42 + 0.1 * i, 0.235))
	var flame := Node3D.new(); flame.name = "flame"; flame.position = Vector3(0, 0.95, 0); root.add_child(flame)
	for k in 3:
		# saturated painted-fire colours (outer red-orange, inner yellow); unlit, so they never wash out to white
		var tongue := piece(flame, "tongue%d" % k, prism_mesh(0.13 - 0.03 * k, 0.32 + 0.1 * k, 0.05, Vector3(1.0, 0.92, 0.78), Color(1.0, 0.36 + 0.22 * k, 0.08 + 0.06 * k)), "flat", Vector3(0.03 * (k - 1), 0, 0.02 * (k % 2)))
		tongue.material_override.set_shader_parameter("emission", 0.15)
		tongue.material_override.set_shader_parameter("lit", 0.0)
	flame.visible = false
	flames[id] = flame
	return root

func bronze_door(id: String, c: Vector2i) -> Node3D:
	var root := Node3D.new(); root.name = id; root.position = centre(c); add_child(root)
	var slab := Node3D.new(); slab.name = "slab"; root.add_child(slab)
	piece(slab, "leaf", box_mesh(Vector3(0.96, 1.5, 0.22), Vector3(1.0, 0.82, 0.5), BRONZE), "metal", Vector3(0, 0.75, 0))
	piece(slab, "band_top", box_mesh(Vector3(0.98, 0.1, 0.26), Vector3(0.9, 0.7, 0.5), IRON), "metal", Vector3(0, 1.3, 0))
	piece(slab, "band_low", box_mesh(Vector3(0.98, 0.1, 0.26), Vector3(0.9, 0.7, 0.5), IRON), "metal", Vector3(0, 0.25, 0))
	piece(slab, "keyhole", box_mesh(Vector3(0.12, 0.2, 0.25), Vector3(0.12, 0.1, 0.08)), "slate", Vector3(0, 0.78, 0))
	return root

func key_stand(id: String, c: Vector2i) -> Node3D:
	var root := Node3D.new(); root.name = id; root.position = centre(c); add_child(root)
	piece(root, "stand", prism_mesh(0.22, 0.78, 0.7, Vector3(0.95, 0.75, 0.45)), "stone", Vector3.ZERO)
	piece(root, "cushion", box_mesh(Vector3(0.3, 0.06, 0.3), Vector3(1.0, 0.8, 0.6), Color(0.55, 0.12, 0.12)), "cloth_red", Vector3(0, 0.81, 0))
	var holder := Node3D.new(); holder.name = "key"; holder.position = Vector3(0, 0.95, 0); root.add_child(holder)
	if kit(holder, KIT.key, Vector3.ZERO, Vector3.ONE * 0.9) == null:
		placeholder_count += 1
		piece(holder, "bow", prism_mesh(0.07, 0.03, 1.0, Vector3(1.2, 1.0, 0.8), BRONZE), "metal", Vector3(0, 0, -0.08))
		piece(holder, "shank", box_mesh(Vector3(0.03, 0.03, 0.2), Vector3(1.2, 1.0, 0.8), BRONZE), "metal", Vector3(0, 0, 0.05))
	return root

func stone_block(id: String, c: Vector2i, pull: bool) -> Node3D:
	var root := Node3D.new(); root.name = id; root.position = centre(c); add_child(root)
	piece(root, "cube", box_mesh(Vector3(0.94, 0.94, 0.94), Vector3(1.0, 0.8, 0.45), Color(0.92, 0.88, 0.8)), "stone", Vector3(0, 0.47, 0))
	piece(root, "rune", box_mesh(Vector3(0.36, 0.36, 0.96), Vector3(1.2, 1.0, 0.8), Color(0.45, 0.62, 0.8)), "slate", Vector3(0, 0.47, 0))
	if pull:  # iron grips: this block can also be pulled
		for s in [-1, 1]:
			piece(root, "grip%d" % s, box_mesh(Vector3(0.06, 0.2, 0.3), Vector3(1.0, 0.8, 0.6), IRON), "metal", Vector3(0.5 * s, 0.6, 0))
	return root

func bridge(id: String, cells: Array) -> Node3D:
	var root := Node3D.new(); root.name = id; add_child(root)
	for c in cells:
		var cc := Vector2i(int(c[0]), int(c[1]))
		var span := Node3D.new(); span.name = "span_%d_%d" % [cc.x, cc.y]; span.position = centre(cc); root.add_child(span)
		for k in 4:
			piece(span, "plank%d" % k, box_mesh(Vector3(0.92, 0.07, 0.22), Vector3(1.0, 0.8, 0.6)), "planks", Vector3(0, 0.0, -0.36 + 0.24 * k))
	root.visible = false
	return root

func portcullis(id: String, c: Vector2i, timed: bool) -> Node3D:
	var root := Node3D.new(); root.name = id; root.position = centre(c); add_child(root)
	piece(root, "lintel", box_mesh(Vector3(1.02, 0.2, 0.3), Vector3(0.95, 0.75, 0.5)), "stone", Vector3(0, 1.7, 0))
	var bars := Node3D.new(); bars.name = "bars"; root.add_child(bars)
	for k in 5:
		piece(bars, "bar%d" % k, box_mesh(Vector3(0.07, 1.6, 0.07), Vector3(1.0, 0.85, 0.55), IRON), "metal", Vector3(-0.36 + 0.18 * k, 0.8, 0))
	piece(bars, "rail", box_mesh(Vector3(0.9, 0.08, 0.08), Vector3(1.0, 0.85, 0.55), IRON), "metal", Vector3(0, 0.5, 0))
	if timed:
		var glass := piece(root, "hourglass", prism_mesh(0.1, 0.22, 0.2, Vector3(1.4, 1.2, 1.0), EMBER), "glass", Vector3(0, 1.85, 0))
		glass.material_override.set_shader_parameter("emission", 0.5)
	return root

func orb(id: String, c: Vector2i) -> Node3D:
	var root := Node3D.new(); root.name = id; root.position = centre(c); add_child(root)
	piece(root, "plinth", prism_mesh(0.28, 0.75, 0.75, Vector3(0.95, 0.75, 0.45)), "stone", Vector3.ZERO)
	var holder := Node3D.new(); holder.name = "sphere"; holder.position = Vector3(0, 1.05, 0); root.add_child(holder)
	if kit(holder, KIT.orb, Vector3.ZERO, Vector3.ONE * 0.8) == null:
		placeholder_count += 1
		var mi := MeshInstance3D.new()
		var sphere := SphereMesh.new(); sphere.radius = 0.24; sphere.height = 0.48; sphere.radial_segments = 8; sphere.rings = 4
		mi.mesh = sphere
		mi.material_override = N64Mat.make("env_chrome" if not Pack.palette().is_empty() else "flat")
		holder.add_child(mi)
	var glow := piece(root, "glow", prism_mesh(0.2, 0.4, 0.6, Vector3(1.0, 0.95, 0.85), Color(0.45, 0.75, 1.0)), "flat", Vector3(0, 0.88, 0))
	glow.material_override.set_shader_parameter("emission", 0.25)
	glow.material_override.set_shader_parameter("lit", 0.0)
	glow.visible = false
	return root

func shutter(id: String, c: Vector2i, dir: String) -> Node3D:
	var root := Node3D.new(); root.name = id; root.position = centre(c); add_child(root)
	root.rotation_degrees.y = {"n": 0.0, "s": 180.0, "e": -90.0, "w": 90.0}[dir]
	piece(root, "post_l", box_mesh(Vector3(0.14, 1.5, 0.14), Vector3(0.95, 0.75, 0.5)), "stone", Vector3(-0.45, 0.75, 0))
	piece(root, "post_r", box_mesh(Vector3(0.14, 1.5, 0.14), Vector3(0.95, 0.75, 0.5)), "stone", Vector3(0.45, 0.75, 0))
	var flap := Node3D.new(); flap.name = "flap"; flap.position = Vector3(0, 1.45, 0); root.add_child(flap)
	piece(flap, "boards", box_mesh(Vector3(0.78, 1.35, 0.08), Vector3(1.0, 0.8, 0.55)), "planks_dark", Vector3(0, -0.68, 0))
	# the flap leans the way it lets you pass: a readable one-way cue without text
	piece(flap, "chevron", box_mesh(Vector3(0.3, 0.3, 0.1), Vector3(1.3, 1.1, 0.9), EMBER), "metal", Vector3(0, -0.7, -0.06))
	flap.rotation_degrees.x = 12
	return root

func show_reward(cell: Vector2i) -> void:
	if reward_node != null: return
	reward_node = Node3D.new(); reward_node.name = "reward"; reward_node.position = centre(cell, 0.0); add_child(reward_node)
	piece(reward_node, "dais", prism_mesh(0.34, 0.5, 0.8, Vector3(1.0, 0.8, 0.5), Color(0.95, 0.9, 0.75)), "stone", Vector3.ZERO)
	var lens := Node3D.new(); lens.name = "lens"; lens.position = Vector3(0, 0.85, 0); reward_node.add_child(lens)
	if kit(lens, KIT.reward, Vector3.ZERO, Vector3.ONE * 0.9) == null:
		placeholder_count += 1
		piece(lens, "lens_glass", prism_mesh(0.16, 0.06, 1.0, Vector3(1.5, 1.4, 1.2), Color(1.0, 0.92, 0.6)), "glass", Vector3.ZERO)
	var sun := piece(reward_node, "sun", prism_mesh(0.22, 0.04, 1.0, Vector3(1.0, 0.95, 0.85), EMBER), "flat", Vector3(0, 1.25, 0))
	sun.material_override.set_shader_parameter("emission", 0.3)
	sun.material_override.set_shader_parameter("lit", 0.0)

## Pose every element from the logical state (t = 0..1 eases the change from `before`). Deterministic.
func pose(before: Dictionary, now: Dictionary, c: Dictionary, t: float, tick: int) -> void:
	var e_t := t * t * (3.0 - 2.0 * t)
	for i in blocks:
		var n: int = rules.blocks.find(i)
		var a: Vector2i = before.blocks[n]
		var b: Vector2i = now.blocks[n]
		blocks[i].position = centre(a).lerp(centre(b), e_t)
	for i in nodes:
		var e: Dictionary = rules.el[i]
		var node: Node3D = nodes[i]
		match str(e.kind):
			"switch":
				var was: bool = rules.has(before, i) or c.latched.has(i)
				var on: bool = rules.has(now, i) or c.latched.has(i)
				node.get_node("arm").rotation_degrees.x = lerpf(35.0 if was else -35.0, 35.0 if on else -35.0, e_t)
			"plate":
				var pressed: bool = rules.source(now, c, i)
				var top: Node3D = node.get_node("top")
				top.position.y = lerpf(float(top.position.y), -0.03 if pressed else 0.02, 0.5 if t < 1.0 else 1.0)
			"torch":
				var lit: bool = rules.has(now, i)
				var flame: Node3D = flames[i]
				flame.visible = lit
				if lit:
					var k := float(tick % 24) / 24.0
					flame.scale = Vector3(1.0 + 0.08 * sin(k * TAU), 1.0 + 0.16 * sin(k * TAU * 2.0 + 1.3), 1.0 + 0.08 * cos(k * TAU))
					flame.rotation.y = 0.35 * sin(k * TAU)
			"lock":
				var open: bool = c.opened.has(i)
				node.get_node("slab").position.y = lerpf(float(node.get_node("slab").position.y), -1.55 if open else 0.0, e_t if open else 1.0)
			"key":
				node.get_node("key").visible = not c.taken.has(i)
				node.get_node("key").rotation.y = float(tick % 240) / 240.0 * TAU
			"door", "timed_gate":
				var was_open: bool = rules.has(before, i, "open")
				var is_open: bool = rules.has(now, i, "open")
				node.get_node("bars").position.y = lerpf(1.55 if was_open else 0.0, 1.55 if is_open else 0.0, e_t)
			"bridge":
				var bridge_open: bool = rules.has(now, i, "open")
				node.visible = bridge_open or rules.has(before, i, "open")
				for span in node.get_children():
					span.scale = Vector3(1.0, 1.0, lerpf(0.05, 1.0, e_t) if bridge_open and not rules.has(before, i, "open") else (1.0 if bridge_open else lerpf(1.0, 0.05, e_t)))
			"orb":
				var lit_orb: bool = rules.has(now, i)
				node.get_node("glow").visible = lit_orb
				node.get_node("sphere").position.y = 1.05 + 0.04 * sin(float(tick % 120) / 120.0 * TAU) * float(lit_orb)
			"shutter":
				var at: Vector2i = rules.cell(e.cell)
				var moved: Vector2i = now.p - before.p
				var passing: bool = absi(moved.x) + absi(moved.y) == 2 and (before.p + now.p) / 2 == at
				node.get_node("flap").rotation_degrees.x = 12.0 + (68.0 * sin(t * PI) if passing else 0.0)

func show_marker(id: String, tick: int) -> void:
	if id == "" or not rules.el.has(id):
		marker.visible = false
		return
	var e: Dictionary = rules.el[id]
	var at: Vector3
	if e.kind == "block": at = blocks[id].position
	elif e.kind == "bridge": at = centre(rules.cell(e.cells[0]))
	else: at = centre(rules.cell(e.cell))
	marker.visible = true
	marker.position = at + Vector3(0, 1.9 + 0.08 * sin(float(tick % 60) / 60.0 * TAU), 0)
	marker.rotation.y = float(tick % 90) / 90.0 * TAU
