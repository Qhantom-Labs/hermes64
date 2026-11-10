extends Node
## Staged cover renderer (hermes64 cover 1.0.0). Builds a small diorama from validated cover-scene data with the real
## runtime pieces: the actor resolver (hash-checked kit GLBs and bound cast models, n64_world materials and the pack's
## material response), the look rig globals (vertex lighting, fog, grade), kit ground textures and the terrain vista.
## Rendered per output in an own-world SubViewport at the requested size (MSAA 4x standing in for the RDP's coverage AA,
## no dither, no sharpening); textures keep their painted texels with the convention's three-point/mip filtering.
## Deterministic: no TIME-driven shader input (uv scroll frozen, static seeded particles), actor clocks stopped at an
## explicit clip frame, fixed frame waits. No story state, no input; quits when the job is done.
const Wire = preload("res://core/wire.gd")
const Resolver = preload("res://actors/assets.gd")
const Rig = preload("res://look/rig.gd")
const Mat = preload("res://look/n64_mat.gd")
const SkyShader = preload("res://cover/sky.gdshader")
const DotShader = preload("res://cover/particles.gdshader")
const GlowShader = preload("res://shaders/n64_glow.gdshader")
const HaloShader = preload("res://shaders/n64_halo.gdshader")
const ShadowShader = preload("res://shaders/n64_shadow.gdshader")
const ASPECT := {"poster": 245.0 / 170.0, "banner": 2.0, "square": 1.0}
const DEPTH_SCALE := 120.0

var resolver
var job: Dictionary = {}
var report := {"format": "hermes64.cover_report/1", "status": "failed", "renders": [], "errors": []}
var remap_shader: Shader = null
var textures := {}

func _ready() -> void:
	var args := {}
	for arg in OS.get_cmdline_user_args():
		var parts := arg.split("=", true, 1)
		args[parts[0].trim_prefix("--")] = parts[1] if parts.size() > 1 else "1"
	var data = Wire.read_json(str(args.get("job", "")))
	if not data is Dictionary:
		print("COVER ERROR: supply --job=/absolute/path/job.json")
		get_tree().quit(2)
		return
	job = data
	var report_path := str(job.get("report", ""))
	if DisplayServer.get_name() == "headless":
		report.errors.append("headless display: covers need a real windowed renderer; dummy frames are never evidence")
		finish(report_path, 3)
		return
	resolver = Resolver.new()
	resolver.configure({"assets": job.get("assets", {}), "characters": job.get("characters", [])}, job.get("theme", {}))
	var ok := true
	for r in job.get("renders", []):
		var row: Dictionary = await render_one(r)
		report.renders.append(row)
		ok = ok and str(row.get("status", "")) == "rendered"
	report.status = "rendered" if ok and report.errors.is_empty() else "failed"
	report["missing_assets"] = resolver.missing.keys()
	report["engine"] = Engine.get_version_info().string
	report["renderer"] = RenderingServer.get_current_rendering_method()
	report["device"] = RenderingServer.get_video_adapter_name()
	report["display"] = DisplayServer.get_name()
	finish(report_path, 0 if report.status == "rendered" else 1)

func finish(path: String, code: int) -> void:
	if path != "":
		var f := FileAccess.open(path, FileAccess.WRITE)
		if f != null:
			f.store_string(JSON.stringify(report, "\t", true))
			f.close()
	print("COVER status=%s renders=%d errors=%d" % [report.status, report.renders.size(), report.errors.size()])
	if resolver != null: resolver.cache.clear()
	get_tree().quit(code)

static func vec(a) -> Vector3:
	return Vector3(float(a[0]), float(a[1]), float(a[2]))

static func col(v: String) -> Color:
	return Color.from_string(v, Color.MAGENTA)

## Display (sRGB) colour for a plain vec4 shader uniform. Godot 4.6 linearises a Color passed to a vec4 uniform; the
## N64 shaders treat these uniforms as display values and linearise once themselves, so pass the raw components.
static func raw(c: Color) -> Vector4:
	return Vector4(c.r, c.g, c.b, c.a)

## sky.exposure (moonlight): the painted sky and the fog colour dim together, so fogged distance still melts into
## the horizon; hues stay the style's palette colours, glow (moon/sun) and stars stay bright.
static func exposure(scene: Dictionary) -> float:
	return clampf(float(scene.sky.get("exposure", 1.0)), 0.3, 1.0)

static func dim(c: Color, ex: float) -> Color:
	return Color(c.r * ex, c.g * ex, c.b * ex, c.a)

static func fog_hex(scene: Dictionary) -> String:
	return "#" + dim(col(scene.fog.color), exposure(scene)).to_html(false)

func render_one(r: Dictionary) -> Dictionary:
	var scene: Dictionary = r.scene
	var out_dir := str(r.out_dir)
	DirAccess.make_dir_recursive_absolute(out_dir)
	var row := {"id": scene.id, "status": "rendered", "outputs": [], "errors": []}
	for out in r.outputs:
		var res: Dictionary = await render_output(scene, r, out, out_dir)
		row.outputs.append(res)
		if not bool(res.get("ok", false)):
			row.status = "failed"
			row.errors.append_array(res.get("errors", []))
	return row

## VI resolve: the N64 video interface softened every edge over about one output pixel. Covers render at a higher
## internal resolution, so beauty captures pass a [1 2 1] x [1 2 1] / 16 tent at that resolution (no sharpening,
## deterministic texelFetch); data passes (depth, mask, subject) are captured raw.
const VI_SHADER := """
shader_type canvas_item;
render_mode unshaded;
uniform sampler2D src : filter_nearest;
void fragment() {
	ivec2 n = textureSize(src, 0);
	ivec2 p = clamp(ivec2(UV * vec2(n)), ivec2(0), n - 1);
	vec3 acc = vec3(0.0);
	for (int j = -1; j <= 1; j++) {
		for (int i = -1; i <= 1; i++) {
			float w = float((2 - abs(i)) * (2 - abs(j)));
			acc += w * texelFetch(src, clamp(p + ivec2(i, j), ivec2(0), n - 1), 0).rgb;
		}
	}
	COLOR = vec4(acc / 16.0, 1.0);
}
"""

func vi_resolve(vp: SubViewport, size: Vector2i) -> SubViewport:
	var vi := SubViewport.new()
	vi.size = size
	vi.transparent_bg = false
	vi.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	var rect := ColorRect.new()
	rect.size = Vector2(size)
	var sh := Shader.new()
	sh.code = VI_SHADER
	var m := ShaderMaterial.new()
	m.shader = sh
	m.set_shader_parameter("src", vp.get_texture())
	rect.material = m
	vi.add_child(rect)
	add_child(vi)
	return vi

func render_output(scene: Dictionary, r: Dictionary, out: Dictionary, out_dir: String) -> Dictionary:
	var size := Vector2i(int(out.size[0]), int(out.size[1]))
	var vp := SubViewport.new()
	vp.size = size
	vp.own_world_3d = true
	vp.transparent_bg = false
	vp.msaa_3d = Viewport.MSAA_4X
	vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	add_child(vp)
	var vi := vi_resolve(vp, size)
	var stage := Node3D.new()
	stage.name = "stage"
	vp.add_child(stage)
	var built: Dictionary = build(stage, scene, r, size)
	var p: Dictionary = apply_look(scene, built, r)
	var base := out_dir.path_join("%s-%s" % [scene.id, out.name])
	var files := {}
	var ok: bool = built.errors.is_empty()
	files["beauty"] = base + ".png"
	ok = (await grab(vi, files.beauty)) and ok
	var passes: Array = out.get("passes", [])
	if passes.has("noglow"):
		for n in built.glows: n.visible = false
		files["noglow"] = base + "-noglow.png"
		ok = (await grab(vi, files.noglow)) and ok
		for n in built.glows: n.visible = true
	if passes.has("classic"):
		RenderingServer.global_shader_parameter_set("n64_classic", Vector4(0, 0, 0, 0))
		files["classic"] = base + "-classic.png"
		ok = (await grab(vi, files.classic)) and ok
		RenderingServer.global_shader_parameter_set("n64_classic", Rig.classic)
	if passes.has("subject"):
		var hide: Array = []
		for n in stage.get_children():
			if n is Node3D and n.visible and not built.subject.has(n) and not n is Camera3D:
				n.visible = false
				hide.append(n)
		var clear: Color = built.env.environment.background_color
		built.env.environment.background_color = Color(1, 0, 1)
		vp.msaa_3d = Viewport.MSAA_DISABLED
		files["subject"] = base + "-subject.png"
		ok = (await grab(vp, files.subject)) and ok
		vp.msaa_3d = Viewport.MSAA_4X
		built.env.environment.background_color = clear
		for n in hide: n.visible = true
	for pass_name in ["depth", "mask"]:
		if not passes.has(pass_name): continue
		# capture debug passes of the shared world shader: x 1 = distance (white at DEPTH_SCALE m), 2 = region mask
		for n in built.glows + built.dots: n.visible = false
		var clear2: Color = built.env.environment.background_color
		built.env.environment.background_color = Color(1, 1, 1) if pass_name == "depth" else Color(0, 0, 0)
		vp.msaa_3d = Viewport.MSAA_DISABLED
		RenderingServer.global_shader_parameter_set("n64_debug", Vector4(1 if pass_name == "depth" else 2, DEPTH_SCALE, 0, 0))
		files[pass_name] = base + "-" + pass_name + ".png"
		ok = (await grab(vp, files[pass_name])) and ok
		RenderingServer.global_shader_parameter_set("n64_debug", Vector4(0, 0, 0, 0))
		vp.msaa_3d = Viewport.MSAA_4X
		built.env.environment.background_color = clear2
		for n in built.glows + built.dots: n.visible = true
	var cam: Camera3D = built.camera
	var subject_box := screen_box(cam, built.subject, size)
	var tri_subject := 0
	for n in built.subject: tri_subject += triangles(n)
	var res := {"name": out.name, "size": [size.x, size.y], "ok": ok, "files": files, "errors": built.errors,
		"camera": {"position": [snappedf(cam.global_position.x, 0.001), snappedf(cam.global_position.y, 0.001), snappedf(cam.global_position.z, 0.001)],
			"fov": snappedf(cam.fov, 0.001), "keep_aspect": "width" if cam.keep_aspect == Camera3D.KEEP_WIDTH else "height"},
		"subject_screen": subject_box, "subject_nodes": built.subject.size(), "actors": built.actors,
		"triangles": {"total": triangles(stage), "subject": tri_subject}, "lights": built.lights.size(),
		"look": {"fog": p.fog, "grade": p.grade}}
	vi.queue_free()
	vp.queue_free()
	await get_tree().process_frame
	return res

func grab(vp: SubViewport, path: String) -> bool:
	for i in 3:
		await get_tree().process_frame
	await RenderingServer.frame_post_draw
	var img := vp.get_texture().get_image()
	if img == null or img.is_empty(): return false
	img.convert(Image.FORMAT_RGB8)
	return img.save_png(path) == OK

func triangles(node: Node) -> int:
	var total := 0
	if node is MeshInstance3D and node.mesh != null:
		for i in node.mesh.get_surface_count():
			var arrays: Array = node.mesh.surface_get_arrays(i)
			total += (arrays[Mesh.ARRAY_INDEX].size() if arrays[Mesh.ARRAY_INDEX] != null else arrays[Mesh.ARRAY_VERTEX].size()) / 3
	elif node is MultiMeshInstance3D and node.multimesh != null:
		total += node.multimesh.instance_count * 2
	for c in node.get_children(): total += triangles(c)
	return total

static func world_aabb(node: Node) -> AABB:
	var out := AABB()
	var first := true
	var stack: Array = [node]
	while not stack.is_empty():
		var n = stack.pop_back()
		if n is MeshInstance3D and n.mesh != null and n.visible and str(n.name) != "shadow_blob":
			var box: AABB = n.global_transform * n.get_aabb()
			if first: out = box
			else: out = out.merge(box)
			first = false
		for c in n.get_children(): stack.append(c)
	return out

func screen_box(cam: Camera3D, nodes: Array, size: Vector2i) -> Dictionary:
	var lo := Vector2(INF, INF)
	var hi := Vector2(-INF, -INF)
	var behind := 0
	for n in nodes:
		var a := world_aabb(n)
		if a.size == Vector3.ZERO: continue
		for k in 8:
			var p := a.get_endpoint(k)
			if cam.is_position_behind(p):
				behind += 1
				continue
			var s := cam.unproject_position(p)
			lo = lo.min(s)
			hi = hi.max(s)
	if lo.x == INF: return {"visible": false}
	return {"visible": true, "left": snappedf(lo.x / size.x, 0.0001), "top": snappedf(lo.y / size.y, 0.0001),
		"right": snappedf(hi.x / size.x, 0.0001), "bottom": snappedf(hi.y / size.y, 0.0001), "behind_corners": behind}

## ------------------------------------------------------------------ set building
func build(stage: Node3D, scene: Dictionary, r: Dictionary, size: Vector2i) -> Dictionary:
	var built := {"subject": [], "glows": [], "dots": [], "lights": [], "camera": null, "env": null, "errors": [], "actors": []}
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = col(fog_hex(scene))
	stage.add_child(env)
	built.env = env
	stage.add_child(make_sky(scene))
	var ground := make_ground(scene, r)
	if ground != null: stage.add_child(ground)
	else: built.errors.append("ground texture missing or hash mismatch for preset " + str(scene.ground.preset))
	if bool(scene.ground.vista):
		var v = resolver.resolve("terrain.vista")
		if v == null: built.errors.append("terrain.vista missing or hash mismatch")
		else:
			stage.add_child(v)
			# vista ring squashed vertically (cover convention): a lower horizon leaves the sky band for the title
			v.scale = Vector3(1.0, 0.6, 1.0) * float(scene.ground.vista_scale)
			v.set_meta("cover_kind", "vista")
			freeze(v)
			# N64 construction: the far ring takes the rig and the full fog, so it melts into the horizon colour
			for mi in v.find_children("*", "MeshInstance3D", true, false):
				for i in mi.mesh.get_surface_count():
					var vm = mi.get_surface_override_material(i)
					if vm is ShaderMaterial:
						vm.set_shader_parameter("lit", 1.0)
						vm.set_shader_parameter("fog_scale", 1.0)
	for h in scene.hero:
		var n := place_kit(stage, h, "hero", built)
		if n != null:
			built.subject.append(n)
			blob(stage, n)
	for pr in scene.props:
		var n2 := place_kit(stage, pr, "prop", built)
		if n2 != null: blob(stage, n2)
	for a in scene.cast:
		var c: Dictionary = r.get("cast", {}).get(str(a.id), {})
		var actor = resolver.character(c) if not c.is_empty() else null
		if actor == null or not actor.get_meta("real_character", false):
			built.errors.append("cast %s: no hash-verified bound model" % str(a.id))
			if actor != null: actor.queue_free()
			continue
		stage.add_child(actor)
		actor.set_process(false)
		actor.position = vec(a.at)
		actor.rotation.y = deg_to_rad(float(a.yaw))
		actor.scale = Vector3.ONE * float(a.scale)
		actor.play_clip(str(a.clip))
		if actor.animation != null and actor.clip != "":
			# the runtime's held-pose clock: frame n of the clip at the actor's pose rate (15 fps)
			var length: float = actor.animation.get_animation(actor.clip).length
			var t: float = float(a.frame) / float(actor.pose_fps)
			actor.animation.seek(fmod(t, length) if length > 0.0 else 0.0, true)
		actor.expression(0)
		actor.set_meta("cover_kind", "cast")
		built.subject.append(actor)
		built.actors.append({"id": str(a.id), "character_id": str(actor.get_meta("character_id", "")), "clip": actor.clip, "frame": int(a.frame)})
	for lamp in scene.light.lamps:
		var lc := col(lamp.color)
		built.lights.append({"pos": vec(lamp.at), "color": lc, "intensity": float(lamp.energy), "radius": float(lamp.radius_m), "source": "cover_lamp"})
		if float(lamp.halo) > 0.0:
			built.glows.append(halo(stage, vec(lamp.at), lc, float(lamp.halo)))
		var pool := glow_pool(stage, Vector3(float(lamp.at[0]), 0.035, float(lamp.at[2])), float(lamp.radius_m) * 0.8, lc, minf(0.22, 0.08 + 0.1 * float(lamp.energy)))
		built.glows.append(pool)
	var dots := make_particles(scene)
	if dots != null:
		stage.add_child(dots)
		built.dots.append(dots)
	built.camera = make_camera(stage, scene, size)
	var ramp = r.get("remap", null)
	if ramp is Array and ramp.size() == 5:
		for n in stage.get_children():
			if str(n.get_meta("cover_kind", "")) in ["hero", "prop", "vista", "ground"]:
				ramp_remap(n, ramp)
	return built

func place_kit(stage: Node3D, row: Dictionary, kind: String, built: Dictionary) -> Node3D:
	var n = resolver.resolve(str(row.kit))
	if n == null:
		built.errors.append("kit %s missing or hash mismatch" % str(row.kit))
		return null
	stage.add_child(n)
	n.position = vec(row.at)
	n.rotation_order = EULER_ORDER_YXZ
	n.rotation_degrees.y = float(row.yaw)
	n.scale = Vector3.ONE * float(row.scale)
	n.set_meta("cover_kind", kind)
	freeze(n)
	return n

## Water/scroll materials read TIME; a cover is a still, so every scroll is frozen.
func freeze(node: Node) -> void:
	for mi in node.find_children("*", "MeshInstance3D", true, false) + ([node] if node is MeshInstance3D else []):
		for i in mi.mesh.get_surface_count():
			var m = mi.get_surface_override_material(i)
			if m is ShaderMaterial: m.set_shader_parameter("uv_scroll", Vector2.ZERO)

func blob(stage: Node3D, n: Node3D) -> void:
	var a := world_aabb(n)
	if a.size == Vector3.ZERO or a.position.y > 0.1: return
	var sz := clampf(maxf(a.size.x, a.size.z) * 1.25, 0.5, 9.0)
	var mi := MeshInstance3D.new()
	var q := QuadMesh.new()
	q.size = Vector2(sz, sz)
	mi.mesh = q
	var m := ShaderMaterial.new()
	m.shader = ShadowShader
	m.set_shader_parameter("color", Vector4(0.02, 0.02, 0.05, 1.0))
	m.set_shader_parameter("strength", 0.68)
	mi.material_override = m
	mi.position = Vector3(a.get_center().x, 0.02, a.get_center().z)
	mi.rotation_degrees.x = -90.0
	mi.set_meta("cover_kind", "shadow")
	stage.add_child(mi)

func halo(stage: Node3D, pos: Vector3, c: Color, strength: float) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var q := QuadMesh.new()
	var lim := float(Rig.lighting().get("halo", {}).get("max_size_m", 1.2))
	q.size = Vector2(lim, lim)
	mi.mesh = q
	var m := ShaderMaterial.new()
	m.shader = HaloShader
	m.set_shader_parameter("color", raw(c))
	m.set_shader_parameter("strength", minf(strength, float(Rig.lighting().get("halo", {}).get("max_strength", 0.85))))
	m.set_shader_parameter("softness", 0.9)
	m.set_shader_parameter("pull", 0.35)
	mi.material_override = m
	mi.position = pos
	mi.set_meta("cover_kind", "glow")
	stage.add_child(mi)
	return mi

func glow_pool(stage: Node3D, pos: Vector3, size: float, c: Color, strength: float) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var q := QuadMesh.new()
	q.size = Vector2(size, size)
	mi.mesh = q
	var m := ShaderMaterial.new()
	m.shader = GlowShader
	m.set_shader_parameter("color", raw(c))
	m.set_shader_parameter("strength", strength)
	m.set_shader_parameter("mode", 0)
	mi.material_override = m
	mi.position = pos
	mi.rotation_degrees.x = -90.0
	mi.set_meta("cover_kind", "glow")
	stage.add_child(mi)
	return mi

func make_sky(scene: Dictionary) -> MeshInstance3D:
	var sky := MeshInstance3D.new()
	var sm := SphereMesh.new()
	sm.radius = 900.0
	sm.height = 1800.0
	sm.radial_segments = 48
	sm.rings = 24
	sky.mesh = sm
	var m := ShaderMaterial.new()
	m.shader = SkyShader
	var s: Dictionary = scene.sky
	var ex := exposure(scene)
	m.set_shader_parameter("zenith", raw(dim(col(s.zenith), ex)))
	m.set_shader_parameter("horizon", raw(dim(col(s.horizon), ex)))
	m.set_shader_parameter("glow", raw(col(s.glow)))
	m.set_shader_parameter("glow_strength", float(s.glow_strength))
	var ga := deg_to_rad(float(s.glow_azimuth_deg))
	var ge := deg_to_rad(float(s.glow_elevation_deg))
	m.set_shader_parameter("glow_dir", Vector3(sin(ga) * cos(ge), sin(ge), cos(ga) * cos(ge)))
	m.set_shader_parameter("stars", float(s.stars))
	m.set_shader_parameter("aurora", raw(dim(col(s.aurora), ex)))
	m.set_shader_parameter("aurora_strength", float(s.aurora_strength))
	m.set_shader_parameter("clouds", float(s.clouds))
	m.set_shader_parameter("cloud_color", raw(dim(col(s.cloud_color), ex)))
	m.set_shader_parameter("seed", float(int(scene.seed) % 997))
	# the painted gradient starts at the vista ridge (sin of its elevation), so the sky just above the far hills is
	# the horizon/fog colour and fogged distance melts into it (N64 construction)
	m.set_shader_parameter("horizon_y", 0.15 if bool(scene.ground.vista) else -0.01)
	m.set_shader_parameter("sky_span", 0.26)
	sky.material_override = m
	sky.set_meta("cover_kind", "sky")
	return sky

static func hash01(i: float) -> float:
	return fposmod(sin(i * 12.9898 + 78.233) * 43758.5453, 1.0)

static func vnoise(x: float, z: float, s: float) -> float:
	var ix := floorf(x)
	var iz := floorf(z)
	var fx := x - ix
	var fz := z - iz
	fx = fx * fx * (3.0 - 2.0 * fx)
	fz = fz * fz * (3.0 - 2.0 * fz)
	var a := hash01(ix * 57.0 + iz * 131.0 + s)
	var b := hash01((ix + 1.0) * 57.0 + iz * 131.0 + s)
	var c := hash01(ix * 57.0 + (iz + 1.0) * 131.0 + s)
	var d := hash01((ix + 1.0) * 57.0 + (iz + 1.0) * 131.0 + s)
	return lerpf(lerpf(a, b, fx), lerpf(c, d, fx), fz)

## Ground: a radial disc out to the staged radius, then an apron into the fog; painted low-frequency vertex light
## patches (convention bake.vertex_variation) and gentle relief only outside the staged centre.
func make_ground(scene: Dictionary, r: Dictionary) -> MeshInstance3D:
	var preset := str(scene.ground.preset)
	var row: Dictionary = job.get("textures", {}).get(preset, {})
	var path := str(row.get("path", ""))
	if path == "" or not FileAccess.file_exists(path) or FileAccess.get_sha256(path) != str(row.get("sha256", "")):
		return null
	if not textures.has(path):
		textures[path] = ImageTexture.create_from_image(Image.load_from_file(path))
	var R := float(scene.ground.radius_m)
	var amp: float = float({"dunes": 0.9, "snowfield": 0.35, "meadow": 0.18, "earth": 0.15, "ice": 0.05}.get(preset, 0.0))
	var radii := [0.0, R * 0.12, R * 0.25, R * 0.38, R * 0.5, R * 0.62, R * 0.75, R * 0.88, R, R * 1.35, R * 1.9, R * 2.8, 180.0]
	var seg := 64
	var s := float(int(scene.seed) % 991)
	var tile := float(row.get("tile_m", 3.0))
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var verts := []
	for ri in radii.size():
		var ring := []
		for k in seg:
			var a := TAU * float(k) / float(seg)
			var rr: float = radii[ri]
			var x := cos(a) * rr
			var z := sin(a) * rr
			var h := 0.0
			if rr > R * 0.55:
				h = amp * smoothstep(R * 0.55, R * 0.9, rr) * (vnoise(x / 7.0, z / 7.0, s) * 1.6 - 0.5 + 0.4 * sin(x * 0.21 + z * 0.13 + s))
			# painted vertex light: broad 9 m patches plus a finer 3 m mottle (convention bake.vertex_variation)
			var v := 0.86 + 0.2 * (vnoise(x / 9.0, z / 9.0, s + 17.0) - 0.5) + 0.12 * (vnoise(x / 3.0, z / 3.0, s + 29.0) - 0.5)
			ring.append([Vector3(x, h, z), Color(v, v, v)])
			if ri == 0: break
		verts.append(ring)
	for ri in range(1, radii.size()):
		var inner: Array = verts[ri - 1]
		var outer: Array = verts[ri]
		for k in seg:
			var k2 := (k + 1) % seg
			var a0: Array = inner[0] if inner.size() == 1 else inner[k]
			var a1: Array = inner[0] if inner.size() == 1 else inner[k2]
			var b0: Array = outer[k]
			var b1: Array = outer[k2]
			# Godot front faces wind clockwise seen from the front (here: from above)
			for tri in ([[a0, b0, b1]] if inner.size() == 1 else [[a0, b0, b1], [a0, b1, a1]]):
				for vtx in tri:
					var p: Vector3 = vtx[0]
					st.set_color(vtx[1])
					st.set_uv(Vector2(p.x, p.z) / tile)
					st.add_vertex(p)
	st.generate_normals()
	var mesh := st.commit()
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	var m := ShaderMaterial.new()
	m.shader = Mat.shader()
	m.set_shader_parameter("vcolor_is_linear", false)
	Mat.bind_external(m, textures[path])
	m.set_shader_parameter("mask_id", 5)
	m.set_meta("role", str(row.get("role", "ground")))
	m.set_meta("kind", "baked_unlit")
	var resp: Dictionary = job.get("theme", {}).get("look", {}).get("materials", {}).get(str(row.get("role", "")), {})
	if resp.has("tint"): m.set_shader_parameter("tint", Color.from_string(str(resp.tint), Color.WHITE))
	mi.set_surface_override_material(0, m)
	mi.set_meta("cover_kind", "ground")
	mi.name = "ground"
	return mi

func make_particles(scene: Dictionary) -> MultiMeshInstance3D:
	var p: Dictionary = scene.particles
	if str(p.kind) == "none" or int(p.count) <= 0: return null
	var area := vec(p.area)
	var cam: Dictionary = scene.camera
	var centre := vec(cam.target)
	var az := deg_to_rad(float(cam.azimuth_deg))
	var el := deg_to_rad(float(cam.elevation_deg))
	var eye := centre + Vector3(sin(az) * cos(el), sin(el), cos(az) * cos(el)) * float(cam.distance_m)
	var rng := RandomNumberGenerator.new()
	rng.seed = int(scene.seed) * 7919 + 17
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	var q := QuadMesh.new()
	q.size = Vector2(2, 2)
	mm.mesh = q
	var xs := []
	var tries := 0
	while xs.size() < int(p.count) and tries < int(p.count) * 8:
		tries += 1
		var pos := Vector3(centre.x + rng.randf_range(-area.x / 2, area.x / 2), rng.randf_range(0.15, area.y), centre.z + rng.randf_range(-area.z / 2, area.z / 2))
		var sc := rng.randf_range(0.55, 1.45)
		if pos.distance_to(eye) < 2.2: continue
		if str(p.kind) == "fireflies": pos.y = rng.randf_range(0.3, minf(area.y, 3.5))
		xs.append(Transform3D(Basis().scaled(Vector3(sc, sc, sc)), pos))
	mm.instance_count = xs.size()
	for i in xs.size(): mm.set_instance_transform(i, xs[i])
	var mi := MultiMeshInstance3D.new()
	mi.multimesh = mm
	mi.custom_aabb = AABB(centre - Vector3(area.x, 2, area.z), Vector3(area.x * 2, area.y + 4, area.z * 2))
	var m := ShaderMaterial.new()
	m.shader = DotShader
	m.set_shader_parameter("color", raw(col(p.color)))
	m.set_shader_parameter("size", float(p.size_m) * 0.5)
	m.set_shader_parameter("glow", 0.55 if str(p.kind) in ["fireflies", "embers"] else 0.0)
	mi.material_override = m
	mi.set_meta("cover_kind", "particles")
	mi.name = "particles"
	return mi

func make_camera(stage: Node3D, scene: Dictionary, size: Vector2i) -> Camera3D:
	var c: Dictionary = scene.camera
	var target := vec(c.target)
	var az := deg_to_rad(float(c.azimuth_deg))
	var el := deg_to_rad(float(c.elevation_deg))
	var cam := Camera3D.new()
	stage.add_child(cam)
	cam.position = target + Vector3(sin(az) * cos(el), sin(el), cos(az) * cos(el)) * float(c.distance_m)
	cam.look_at(target, Vector3.UP)
	cam.rotate_object_local(Vector3(0, 0, 1), deg_to_rad(float(c.roll_deg)))
	var vfov := 2.0 * atan(12.0 / float(c.focal_mm))
	var composed: float = ASPECT.get(str(c.framing), ASPECT.poster)
	var aspect := float(size.x) / float(size.y)
	if aspect + 0.001 < composed:
		cam.keep_aspect = Camera3D.KEEP_WIDTH
		cam.fov = rad_to_deg(2.0 * atan(tan(vfov / 2.0) * composed))
	else:
		cam.keep_aspect = Camera3D.KEEP_HEIGHT
		cam.fov = rad_to_deg(vfov)
	cam.near = 0.08
	cam.far = 2400.0
	cam.current = true
	return cam

## Profile styles without built kits of their own: kit geometry from the matching built pack, its painted texels
## re-coloured through the profile's 5-stop light ramp (cover-only; documented, not a runtime kit claim).
func ramp_remap(node: Node, ramp: Array) -> void:
	if remap_shader == null:
		var code: String = Mat.shader().code
		code = code.replace("varying vec3 v_light;", "uniform bool remap_on = false;\nuniform vec4 ramp0;\nuniform vec4 ramp1;\nuniform vec4 ramp2;\nuniform vec4 ramp3;\nuniform vec4 ramp4;\nvec3 cover_ramp(float l) {\n\tfloat x = clamp(l, 0.0, 1.0) * 4.0;\n\tif (x < 1.0) return mix(ramp0.rgb, ramp1.rgb, x);\n\tif (x < 2.0) return mix(ramp1.rgb, ramp2.rgb, x - 1.0);\n\tif (x < 3.0) return mix(ramp2.rgb, ramp3.rgb, x - 2.0);\n\treturn mix(ramp3.rgb, ramp4.rgb, x - 3.0);\n}\nvarying vec3 v_light;")
		# surface colour (texel x baked vertex colour x role tint) -> its luma through the profile ramp, before the
		# rig lights it; emissive/unlit surfaces (lit < 0.5) keep their painted colour
		code = code.replace("		c = tc.rgb * v_albedo * lc * tint.rgb;\n", "		vec3 surf = tc.rgb * v_albedo * tint.rgb;\n		if (remap_on && lit > 0.5) {\n			surf = cover_ramp(dot(surf, vec3(0.299, 0.587, 0.114)) * ramp_gain);\n		}\n		c = surf * lc;\n")
		code = code.replace("		c = envc * tint.rgb * lum;\n", "		c = (remap_on ? cover_ramp(dot(envc * tint.rgb, vec3(0.299, 0.587, 0.114)) * ramp_gain) : envc * tint.rgb) * lum;\n")
		code = code.replace("uniform bool remap_on = false;", "uniform bool remap_on = false;\nuniform float ramp_gain = 1.0;")
		if not code.contains("vec3 surf = tc.rgb") or not code.contains("cover_ramp(dot(envc"):
			push_error("cover: n64_world.gdshader changed; profile ramp hooks not applied")
		remap_shader = Shader.new()
		remap_shader.code = code
	for mi in node.find_children("*", "MeshInstance3D", true, false) + ([node] if node is MeshInstance3D else []):
		for i in mi.mesh.get_surface_count():
			var m = mi.get_surface_override_material(i)
			if not m is ShaderMaterial or m.shader != Mat.shader(): continue
			var mm := ShaderMaterial.new()
			mm.shader = remap_shader
			for prop in m.shader.get_shader_uniform_list():
				var v = m.get_shader_parameter(prop.name)
				if v != null: mm.set_shader_parameter(prop.name, v)
			mm.set_shader_parameter("remap_on", true)
			for k in 5: mm.set_shader_parameter("ramp%d" % k, raw(col(str(ramp[k]))))
			for key in m.get_meta_list(): mm.set_meta(key, m.get_meta(key))
			mi.set_surface_override_material(i, mm)

## ------------------------------------------------------------------ look rig
func apply_look(scene: Dictionary, built: Dictionary, r: Dictionary) -> Dictionary:
	var li: Dictionary = scene.light
	var fog: Dictionary = scene.fog
	var sky: Dictionary = scene.sky
	var ka := deg_to_rad(float(li.key_azimuth_deg))
	var ke := deg_to_rad(float(li.key_elevation_deg))
	var remapped: bool = r.get("remap", null) is Array
	var p := {
		"ambient": [li.ambient, float(li.ambient_energy)],
		"sky": [sky.horizon, float(li.sky_bounce)],
		"ground": [li.fill, float(li.ground_bounce)],
		"key": [li.key, float(li.key_energy)],
		"key_dir": [sin(ka) * cos(ke), sin(ke), cos(ka) * cos(ke)],
		"fill": [li.fill, float(li.fill_energy)],
		"fill_dir": [-sin(ka) * 0.8, 0.35, -cos(ka) * 0.8],
		"fog": {"color": fog_hex(scene), "near": float(fog.near_m), "far": float(fog.far_m), "max": float(fog.density)},
		"grade": {"contrast": float(r.get("grade", {}).get("contrast", 1.08)), "saturation": float(r.get("grade", {}).get("saturation", 1.0)),
			"gamma": 1.0, "exposure": 1.0, "lift": "#000000", "gain": "#ffffff"},
		"bake_desaturate": 1.0 if remapped else 0.45,
		"chrome": {"gamma": 1.25, "hot": 0.2, "hot_from": 0.94, "rim": 0.0},
		"actors": {"kicker": [li.kicker, float(li.kicker_energy)], "kicker_up": 0.6},
	}
	Rig.apply(p, built.lights)
	built.env.environment.background_color = Rig.graded(col(fog_hex(scene)), p)
	return p
