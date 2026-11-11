extends "res://view/assets.gd"
## Additive resolver; shared environment pipeline stays unchanged.
const Actor = preload("res://actors/character.gd")
var actor_shader: Shader
# Parsed glTF (GLTFDocument + GLTFState) per verified path. Every instance is still
# built by generate_scene(), exactly as a fresh load builds it (a PackedScene copy
# binds BoneAttachment3D poses earlier, which moved people-framing cameras and broke
# replay determinism between cold and warm caches), and gets its own ShaderMaterials.
# Re-reading and decoding the file on every actor/follower/enemy spawn cost 3-8.5 ms.
var character_cache := {}
var mipless := {}
func clear_caches() -> void:
	super.clear_caches()
	character_cache.clear()
	mipless.clear()
func character(c: Dictionary) -> Node3D:
	for row in characters:
		if row.has("for_ids"):  # project cast (CHARBIND): bound by game id, staged ahead of every selector row
			if not row.for_ids.has(str(c.get("id", ""))): continue
		elif row.body_id != c.get("body_id", "") or row.base_rig_id != c.get("base_rig_id", "") or row.params != c.get("params", {}): continue
		if row.get("placeholder",true): return super.character(c)
		var path: String = row.get("path", "")
		if not FileAccess.file_exists(path):
			var fallback: Dictionary = row.get("fallback",{})
			var n = load_row(fallback)
			if n != null:
				n.set_meta("placeholder",true)
				placeholders[c.id] = "real model unavailable; exact original marker retained"
			return n
		if not verify_once(path, str(row.sha256)):
			missing["character:" + str(c.get("id","unknown"))] = true
			push_error("Character hash mismatch: " + path.get_file())
			return null
		var model := instance_glb(path)
		if model == null: return null
		var actor := Actor.new()
		actor.configure(model,row)
		actor.set_locomotion(locomotion_block(path))
		shade_character(model,actor)
		actor.expression(0)
		actor.set_meta("character_params", c.params.duplicate(true))
		loaded["character:" + str(c.get("id","unknown"))] = {"sha256":row.sha256,"placeholder":false,"character_id":row.character_id,"bone_names":row.bone_names,"animations":row.animations}
		return actor
	return super.character(c)
## A scene actor that is no story character (a boss, a bound CEO): its project cast row, as a character query; {} if none.
func cast_character(id: String) -> Dictionary:
	for row in characters:
		if row.has("for_ids") and row.for_ids.has(id): return {"id": id, "body_id": "", "base_rig_id": "", "params": {}}
	return {}
## Baked locomotion travels in the character file (root extras, docs/LOCOMOTION.md). No block = {} = legacy clips.
func locomotion_block(path: String) -> Dictionary:
	if not character_cache.has(path): return {}
	var extras = character_cache[path][1].json.get("extras", {})
	if not extras is Dictionary: return {}
	var block = extras.get("hermes64_locomotion", {})
	return block if block is Dictionary else {}
## One fresh scene per call from the cached parse of a verified GLB (see character_cache above).
func instance_glb(path: String) -> Node3D:
	if not character_cache.has(path):
		var doc := GLTFDocument.new()
		var state := GLTFState.new()
		if doc.append_from_file(path,state) != OK: return null
		character_cache[path] = [doc, state, state.unique_names.duplicate(), state.unique_animation_names.duplicate()]
	var entry: Array = character_cache[path]
	# generate_scene() registers node/bone/animation names in the state; restore the
	# post-parse sets so every instance gets the original names (no "_2" suffixes).
	entry[1].unique_names = entry[2].duplicate()
	entry[1].unique_animation_names = entry[3].duplicate()
	var model = entry[0].generate_scene(entry[1])
	if not model is Node3D:
		if model != null: model.free()
		return null
	return model
## Combat art (MERGE3): an enemy archetype model from res://combat.json, hash-checked once like
## every bound file. Presentation-only actor; the module FSM moves its body.
func enemy_actor(row: Dictionary) -> Node3D:
	var path: String = row.get("path", "")
	if path == "" or not FileAccess.file_exists(path) or not verify_once(path, str(row.get("sha256", ""))):
		missing["enemy:" + str(row.get("id", "unknown"))] = true
		push_error("Enemy model missing or hash mismatch: " + path.get_file())
		return null
	var model := instance_glb(path)
	if model == null: return null
	var actor := Actor.new()
	actor.configure(model, {"character_id": row.id, "source_rig": row.get("rig", ""), "ground_offset": 0.0})
	shade_character(model, actor)
	actor.expression(0)
	actor.set_meta("enemy_id", row.id)
	loaded["enemy:" + str(row.id)] = {"sha256": row.sha256, "placeholder": false, "rig": row.get("rig", ""), "animations": row.get("clips", [])}
	return actor
## The weapon prop (one rigid mesh), shaded like the wielder's other materials.
func weapon_node(row: Dictionary, actor) -> Node3D:
	var path: String = row.get("path", "")
	if path == "" or not FileAccess.file_exists(path) or not verify_once(path, str(row.get("sha256", ""))):
		missing["weapon:" + str(row.get("id", "unknown"))] = true
		push_error("Weapon missing or hash mismatch: " + path.get_file())
		return null
	var model := instance_glb(path)
	if model == null: return null
	shade_character(model, actor)
	loaded["weapon:" + str(row.id)] = {"sha256": row.sha256, "placeholder": false}
	return model
func character_shader() -> Shader:
	if actor_shader == null:
		# Derive the current room shader in memory, preserving room-look lighting/fog/grade updates.
		# Actors sample unmipmapped textures (face atlas cells never average) with their own filter code, not the
		# global n64_mode: legacy nearest, or the N64 convention's three-point filter (theme "n64".filtering.actors),
		# which softens costume and face texels like the scenery. Atlas cells clamp their filter footprint so a
		# soft filter never bleeds the neighbouring expression into a face.
		var code: String = Mat.shader().code
		code = code.replace("filter_linear_mipmap", "filter_nearest").replace("n64_mode.x", "%.1f" % Rig.actor_filter())
		code = code.replace("uniform vec2 uv_offset", "uniform vec2 character_uv_scale = vec2(1.0);\nuniform bool atlas_clamp = false;\nuniform vec2 uv_offset")
		code = code.replace("UV = UV + uv_offset", "UV = UV * character_uv_scale + uv_offset")
		code = code.replace("		vec2 suv = UV;", "		vec2 suv = UV;\n		if (atlas_clamp) {\n			vec2 hp = 0.5 / tsz;\n			suv = clamp(UV, uv_offset + hp, uv_offset + character_uv_scale - hp);\n		}")
		actor_shader = Shader.new()
		actor_shader.code = code
	return actor_shader
func no_mips(texture: Texture2D) -> Texture2D:
	# Source textures are shared by cached instances; convert each one once
	# (get_image() is a GPU readback on RD renderers). Read-only, so sharing is safe.
	var key := texture.get_instance_id()
	if mipless.has(key) and is_instance_valid(mipless[key][0]): return mipless[key][1]
	var image := texture.get_image().duplicate()
	if image.has_mipmaps(): image.clear_mipmaps()
	var converted := ImageTexture.create_from_image(image)
	mipless[key] = [texture, converted]
	return converted
func shade_character(node: Node, actor) -> void:
	if node is MeshInstance3D:
		for i in node.mesh.get_surface_count():
			var original = node.get_active_material(i)
			if not original is StandardMaterial3D: continue
			var info: Dictionary = original.get_meta("extras", {}).get("n64", {})
			var kind: String = info.get("kind","baked_unlit")
			var m := ShaderMaterial.new()
			m.shader = character_shader()
			m.set_meta("kind",kind)
			m.set_shader_parameter("vcolor_is_linear",true)
			m.set_shader_parameter("dynamic_light",true)
			m.set_shader_parameter("tint",original.albedo_color)
			m.set_shader_parameter("has_texture",original.albedo_texture != null)
			if original.albedo_texture != null:
				var tex := no_mips(original.albedo_texture)
				m.set_shader_parameter("tex_nearest",tex)
				m.set_shader_parameter("tex_linear",tex)
			m.set_shader_parameter("character_uv_scale",Vector2(original.uv1_scale.x,original.uv1_scale.y))
			m.set_shader_parameter("uv_offset",Vector2(original.uv1_offset.x,original.uv1_offset.y))
			if kind == "chrome_env":
				# Current exports omit the chrome texture binding; resolve the pack's env_chrome.
				# Prefer an embedded env if a later export supplies one (without renaming callers).
				var env = no_mips(original.albedo_texture) if original.albedo_texture != null else env_texture("env_chrome")
				m.set_shader_parameter("surface_mode",1)
				m.set_shader_parameter("env_tex",env)
				m.set_shader_parameter("mask_id",1)
			if kind == "face_atlas" and info.has("atlas"):
				var atlas: Dictionary = info.atlas
				m.set_shader_parameter("character_uv_scale",Vector2(1.0/float(atlas.cols),1.0/float(atlas.rows)))
				m.set_shader_parameter("atlas_clamp",true)
				actor.faces.append({"material":m,"cols":int(atlas.cols),"rows":int(atlas.rows)})
			actor.materials.append(m)
			material_kinds[kind] = int(material_kinds.get(kind,0)) + 1
			node.set_surface_override_material(i,m)
	for child in node.get_children(): shade_character(child,actor)
