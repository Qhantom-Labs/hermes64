extends RefCounted
## Manifest-only resolution: exact story identity + params; no rig aliasing.
const Mat = preload("res://look/n64_mat.gd")
const Rig = preload("res://look/rig.gd")
static var globals_registered := false
var root := ""
var mapping := {}
var characters := []
var missing := {}
var loaded := {}
var placeholders := {}
var theme := {}
var cache := {}
var verified := {}
var material_kinds := {}
var env_cache := {}
func configure(bindings: Dictionary, presentation: Dictionary) -> void:
	mapping = bindings.get("assets", {})
	characters = bindings.get("characters", [])
	theme = presentation
	# shared N64 look convention (kits/core/n64_look.json via theme.json "n64"); empty = legacy behaviour
	Rig.conv = theme.get("n64", {})
	Rig.ensure_globals()
	# Legacy defaults (packs without a "look" block render exactly as before: baked light, pack fog).
	legacy_globals(1.0 if Rig.has_look(theme) else 0.0)
	globals_registered = true

## Legacy globals: pack fog + light_rig, rig off unless rig_on. Also used per room when a pack's look block only
## defines some profiles (e.g. "exterior" only): rooms without a profile keep the legacy look exactly.
func legacy_globals(rig_on: float) -> void:
	var fog: Dictionary = theme.get("fog", {})
	var fc := Color.from_string(fog.get("color", "#333344"), Color.GRAY)
	var rig: Dictionary = theme.get("light_rig", {})
	var direction: Array = rig.get("key_dir", [0.3, -0.5, 0.8])
	var ambient: float = rig.get("ambient", 0.55)
	var key: float = rig.get("key", 0.45)
	for entry in [["n64_fog_color", Vector4(fc.r,fc.g,fc.b,1)], ["n64_fog", Vector4(fog.get("near",6),fog.get("far",28),1,1)], ["n64_mode", Vector4(Rig.world_filter(),1,1,rig_on)], ["n64_sun_dir",Vector4(direction[0],direction[2],-direction[1],0)], ["n64_sun_col",Vector4(key,key,key,1)], ["n64_ambient",Vector4(ambient,ambient,ambient,1)]]:
		RenderingServer.global_shader_parameter_set(entry[0],entry[1])
	for k in ["n64_sky", "n64_ground", "n64_fill_col", "n64_pl0_pos", "n64_pl0_col", "n64_pl1_pos", "n64_pl1_col", "n64_pl2_pos", "n64_pl2_col", "n64_pl3_pos", "n64_pl3_col"]:
		RenderingServer.global_shader_parameter_set(k, Vector4(0, 0, 0, 1) if k.ends_with("col") or k in ["n64_sky", "n64_ground"] else Vector4.ZERO)
	RenderingServer.global_shader_parameter_set("n64_rim", Vector4(0, 0, 0, 2))
	RenderingServer.global_shader_parameter_set("n64_spec", Vector4(0, 0, 0, 16))
	RenderingServer.global_shader_parameter_set("n64_grade", Vector4(1, 1, 1, 1))
	RenderingServer.global_shader_parameter_set("n64_lift", Vector4(0, 0, 0, 1))
	RenderingServer.global_shader_parameter_set("n64_gain", Vector4(1, 1, 1, 1))
	RenderingServer.global_shader_parameter_set("n64_bake", Vector4(0, 0, 0, 0))
	RenderingServer.global_shader_parameter_set("n64_debug", Vector4(0, 0, 0, 0))
	Rig.neutral_extras()
func resolve(asset: String) -> Node3D:
	var row = mapping.get(asset, {})
	if row is String: row = {"path":row}
	if row is Dictionary and row.has("path"):
		var node = load_row(row)
		if node != null:
			loaded[asset] = {"path":row.path,"sha256":row.get("sha256", ""),"tri_count":row.get("tri_count",0)}
			node.set_meta("asset_ref", asset)
			node.set_meta("kit_id", str(row.get("kit_id", "")))
			return node
	missing[asset] = true
	return null
func character(c: Dictionary) -> Node3D:
	for row in characters:
		if row.body_id == c.get("body_id", "") and row.base_rig_id == c.get("base_rig_id", "") and row.params == c.get("params", {}):
			var visual = load_row(row)
			if visual != null:
				visual.set_meta("character_params",c.params.duplicate(true))
				visual.set_meta("placeholder",row.get("placeholder",false))
				if row.get("placeholder",false): placeholders[c.get("id","unknown")] = row.reason
				loaded["character:"+str(c.get("id","unknown"))] = {"sha256":row.sha256,"placeholder":row.get("placeholder",false),"bone_names":row.bone_names,"animations":row.animations}
				return visual
	missing["character:"+str(c.get("id","unknown"))] = true
	return null
func clear_caches() -> void:
	cache.clear()
	verified.clear()
func verify_once(path: String, expected: String) -> bool:
	# Each bound file is hashed once per session (media are immutable while the game
	# runs; playtest receipts re-hash every resource after the run). Re-hashing every
	# kit piece on every room build cost milliseconds per transition.
	if verified.get(path, "") == expected: return true
	if FileAccess.get_sha256(path) != expected: return false
	verified[path] = expected
	return true
func load_row(row: Dictionary) -> Node3D:
	var path: String = row.get("path", "")
	if path == "" or not FileAccess.file_exists(path): return null
	if row.has("sha256") and not verify_once(path, str(row.sha256)):
		push_error("Asset hash mismatch: "+path.get_file())
		return null
	if cache.has(path): return cache[path].instantiate()
	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	if doc.append_from_file(path,state) != OK: return null
	var node = doc.generate_scene(state)
	if not node is Node3D: return null
	shade(node)
	var packed := PackedScene.new()
	if packed.pack(node) == OK: cache[path] = packed
	return node
func env_texture(name: String) -> Texture2D:
	if env_cache.has(name): return env_cache[name]
	var path: String = str(theme.get("env_root", "")).path_join(name.get_file() + ".png")
	var tex: Texture2D = null
	if FileAccess.file_exists(path): tex = ImageTexture.create_from_image(Image.load_from_file(path))
	env_cache[name] = tex
	return tex
## Region ids for capture passes (style gate exterior bands, golden-diff region masks).
const GROUND_ROLES := ["grass", "snow", "sand", "dirt", "path", "ice", "water"]
static func mask_for(kind: String, role: String) -> int:
	if kind in ["chrome_env", "glass_env"]: return 1
	if role == "sky": return 3
	if kind == "view_plane": return 2
	if kind == "emissive": return 4
	if role in GROUND_ROLES: return 5
	return 0
func shade(node: Node) -> void:
	var response: Dictionary = theme.get("look", {}).get("materials", {})
	if node is MeshInstance3D:
		for i in node.mesh.get_surface_count():
			var original = node.get_active_material(i)
			var m := ShaderMaterial.new()
			m.shader = Mat.shader()
			m.set_shader_parameter("has_texture",false)
			m.set_shader_parameter("vcolor_is_linear",false)
			if original is StandardMaterial3D:
				var info: Dictionary = original.get_meta("extras", {}).get("n64", {})
				var kind: String = info.get("kind", "baked_unlit")
				var role: String = info.get("role", "")
				m.set_meta("role", role)
				m.set_meta("kind", kind)
				material_kinds[kind] = int(material_kinds.get(kind,0))+1
				m.set_shader_parameter("tint",original.albedo_color)
				if original.albedo_texture != null: Mat.bind_external(m, original.albedo_texture)
				if kind in ["chrome_env","glass_env"]:
					var env = env_texture(str(info.get("env", "")))
					if env != null:
						m.set_shader_parameter("surface_mode",1)
						m.set_shader_parameter("env_tex",env)
				if kind == "card_alpha": m.set_shader_parameter("alpha_cut",0.5)
				m.set_shader_parameter("mask_id", mask_for(kind, role))
				if info.has("scroll"): m.set_shader_parameter("uv_scroll",Vector2(info.scroll[0],info.scroll[1]))
				if info.has("wobble"): m.set_shader_parameter("wobble",Vector4(info.wobble[0],info.wobble[1],info.wobble[2],0.0))
				# Pack-data material response (view.json look.materials[role]); kinds supply safe defaults.
				var r: Dictionary = response.get(role, {})
				if kind in ["emissive", "view_plane"]: m.set_shader_parameter("lit", float(r.get("lit", 0.0)))
				# convention lighting.unlit_level: painted light, unlit surfaces sit below full white (never clip)
				var ul = Rig.lighting().get("unlit_level", null)
				if ul != null: m.set_shader_parameter("unlit_level", float(ul))
				if kind == "view_plane": m.set_shader_parameter("fog_scale", float(r.get("fog_scale", theme.get("look", {}).get("view_fog_scale", 1.0))))
				for key in ["gloss", "spec", "rim_amt", "emission", "lit", "fog_scale"]:
					if r.has(key): m.set_shader_parameter(key, float(r[key]))
				# convention filtering.sky_vblur_texels: the sky card's palette bands read as one painted gradient
				var vb = Rig.conv.get("filtering", {}).get("sky_vblur_texels", null)
				if role == "sky" and vb != null: m.set_shader_parameter("tex_vblur", float(vb))
				# convention: emissive surfaces stay near their painted colour (no glow boost past emission_max)
				var em_max = Rig.lighting().get("emission_max", null)
				if em_max != null and r.has("emission"): m.set_shader_parameter("emission", minf(float(r.emission), float(em_max)))
				if r.has("tint"): m.set_shader_parameter("tint", Color.from_string(str(r.tint), Color.WHITE))
				if float(r.get("gloss", 0.0)) > 0.0:
					var genv = env_texture(str(r.get("env", "env_chrome")))
					if genv != null:
						m.set_shader_parameter("has_env", true)
						m.set_shader_parameter("env_tex", genv)
			node.set_surface_override_material(i,m)
	for child in node.get_children(): shade(child)
