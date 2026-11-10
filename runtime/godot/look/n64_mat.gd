extends RefCounted
# Material cache + global look switches (shader globals shared by every N64 material).
# Material keys: "<texture>" | "<texture>@glow" | "flat" | "env_<name>" (sphere-map chrome/glass).

const TexGen = preload("res://look/texgen.gd")
const SHADER_PATH := "res://shaders/n64_world.gdshader"

static var _shader: Shader = null
static var _cache := {}

# Global look state (also used to describe a screenshot's settings in logs).
static var fx := {"filter": 1, "vcolor": true, "texture": true, "fog": true, "fog_begin": 4.0, "fog_end": 18.0,
	"fog_max": 1.0, "fog_color": Color("7895a8")}

static func shader() -> Shader:
	if _shader == null:
		_shader = load(SHADER_PATH)
	return _shader

static func clear() -> void:
	_cache = {}

static func _setup(m: ShaderMaterial, tex_name: String) -> void:
	m.shader = shader()
	if tex_name == "flat":
		m.set_shader_parameter("has_texture", false)
	elif tex_name.begins_with("env_"):
		m.set_shader_parameter("surface_mode", 1)
		m.set_shader_parameter("env_tex", TexGen.get_tex(tex_name))
	else:
		m.set_shader_parameter("tex_linear", TexGen.get_tex(tex_name))
		m.set_shader_parameter("tex_nearest", TexGen.get_tex_nearest(tex_name))

# For external textures (e.g. runtime-loaded glTF): mipmapped linear copy + separate nearest copy.
static func bind_external(m: ShaderMaterial, tex: Texture2D) -> void:
	var img := tex.get_image()
	var lin := img.duplicate()
	if not lin.has_mipmaps():
		lin.generate_mipmaps()
	var near := img.duplicate()
	if near.has_mipmaps():
		near.clear_mipmaps()
	m.set_shader_parameter("has_texture", true)
	m.set_shader_parameter("tex_linear", ImageTexture.create_from_image(lin))
	m.set_shader_parameter("tex_nearest", ImageTexture.create_from_image(near))

static func for_key(key: String) -> ShaderMaterial:
	if _cache.has(key):
		return _cache[key]
	var parts := key.split("@")
	var m := ShaderMaterial.new()
	_setup(m, parts[0])
	if parts[0] == "water":
		m.set_shader_parameter("uv_scroll", Vector2(0.03, 0.012))
	if parts.size() > 1 and parts[1] == "glow":
		m.set_shader_parameter("tint", Color(1.25, 1.2, 1.0))
	_cache[key] = m
	return m

# Fresh (uncached) material, e.g. per-character with dynamic light params.
static func make(tex_name: String, dynamic := false) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	_setup(m, tex_name)
	m.set_shader_parameter("dynamic_light", dynamic)
	return m

static func apply_fx() -> void:
	var rs := RenderingServer
	var fc: Color = fx.fog_color
	rs.global_shader_parameter_set("n64_fog_color", Vector4(fc.r, fc.g, fc.b, 1.0))
	rs.global_shader_parameter_set("n64_fog", Vector4(fx.fog_begin, fx.fog_end, 1.0 if fx.fog else 0.0, fx.fog_max))
	rs.global_shader_parameter_set("n64_mode", Vector4(fx.filter, 1.0 if fx.vcolor else 0.0, 1.0 if fx.texture else 0.0, 0.0))

static func set_room_light(ambient: Color, sun_dir: Vector3, sun_col: Color) -> void:
	var rs := RenderingServer
	var d := sun_dir.normalized()
	rs.global_shader_parameter_set("n64_sun_dir", Vector4(d.x, d.y, d.z, 0.0))
	rs.global_shader_parameter_set("n64_sun_col", Vector4(sun_col.r, sun_col.g, sun_col.b, 1.0))
	rs.global_shader_parameter_set("n64_ambient", Vector4(ambient.r, ambient.g, ambient.b, 1.0))

static func describe() -> String:
	return "filter=%s light=%s texture=%s fog=%s(%.1f-%.1f)" % [["nearest", "bilinear", "3point"][int(fx.filter)],
		fx.vcolor, fx.texture, fx.fog, fx.fog_begin, fx.fog_end]
