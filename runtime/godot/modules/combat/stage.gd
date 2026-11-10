extends RefCounted
## Combat stage (COMBAT lane): lighting, floor telegraphs, contact shadows, pre-attack flash, projectile and drop
## visuals, the dodge-window glyph state and audio cues. Presentation only: it reads the fixed-tick combat state
## after each tick and never writes it; nothing here is hashed, saved or collided.
##
## Lighting stays inside the N64 convention: the actor kicker (the only extra character light the convention allows)
## eases up to light.kicker (capped at lighting.actor.kicker_max), each fighter gets a camera-side fill through the
## existing per-material vertex point light (warm on the player, cool on enemies, so silhouettes separate by hue and
## value), the arena floor gets one soft painted light pool (lamp_pool.max_strength) and every fighter a dark contact
## disc. All of it eases in/out over light.blend_ticks and is gone once the attempt has ended.
const Readability = preload("res://modules/combat/readability.gd")
const Telegraph = preload("res://modules/combat/telegraph.gd")
const Rig = preload("res://look/rig.gd")
const MARKER = preload("res://shaders/n64_marker.gdshader")
const SHADOW = preload("res://shaders/n64_shadow.gdshader")
const SHAPES := {"disc": 0, "ring": 1, "lane": 2, "arc": 3}
var host
var profile := {}
var active := false
var weight := 0.0
var base_kicker := Vector4(0, 0, 0, 0.5)
var target_kicker := Vector4(0, 0, 0, 0.5)
var root: Node3D
var pool: MeshInstance3D
var markers := {}
var shadows := {}
var orbs := {}
var lit := {}
var arena := {}
## HUD inputs (read by modules/hud.gd each frame): dodge glyphs [{at: Vector3, open: bool}], edge flash ticks.
var glyphs := []
var edge_ticks := 0
## Audio cue ids requested this tick (played by the host through view/audio.gd).
var cues := []
var cued := {}
## Counters for tests/evidence.
var stats := {"markers": 0, "flashes": 0, "glyph_ticks": 0, "cues": 0}

func attach(module_host) -> void:
	host = module_host

func start(encounter: Dictionary) -> void:
	var view = host.presenter
	profile = Readability.resolve(view.theme, view.room_root.presentation if view.room_root != null else {})
	arena = encounter.get("arena", {})
	base_kicker = room_kicker()
	var k := Readability.term(profile.get("light", {}).get("kicker", []), 0.0)
	target_kicker = Vector4(maxf(k.r, base_kicker.x), maxf(k.g, base_kicker.y), maxf(k.b, base_kicker.z), float(profile.get("light", {}).get("kicker_up", base_kicker.w)))
	lights = bool(profile.get("light", {}).get("enabled", true))
	active = lights or bool(profile.get("telegraph", {}).get("enabled", true))
	cued.clear()
	ensure_root()
	warm_up(encounter.has("boss") or encounter.has("gate"))

## light.enabled (kicker, fills, pool, contact shadows, flash); telegraph.enabled gates decals, glyphs and cues.
var lights := true

## Particle motes (room look.exterior particles) that drift within light.mote_near_m of the closer combat lens would
## read as big discs; the field's near_cull hides them while combat is blended in (0 outside combat = unchanged).
func motes(s: float) -> void:
	var view = host.presenter
	if view.room_root == null: return
	var near := float(profile.get("light", {}).get("mote_near_m", 1.6)) * s
	for node in view.room_root.get_children():
		if node is MultiMeshInstance3D and node.get_meta("placed", "") == "particles" and node.material_override is ShaderMaterial:
			node.material_override.set_shader_parameter("near_cull", near)

## Lens clear: exterior rooms place "framing" dressing near the AUTHORED lens (room.gd compose_exterior) and other
## mounted dressing around the yard. Seen from the closer combat lens, a framing rock can fill half the frame and a
## post can stand between the camera and a fighter. While the combat view is mostly blended in (s >= 0.5) those
## pieces are hidden: every framing piece, and any dressing piece within camera.near_hide_m of the lens or crossing
## the lens -> fighter sight lines. Presentation only; restored as the view blends out or the attempt resets.
var hidden := {}
var dressing := []
func lens_clear(s: float, camera: Camera3D, targets: Array) -> void:
	var view = host.presenter
	if view.room_root == null or camera == null: return
	if dressing.is_empty():
		for node in view.room_root.get_children():
			if node is Node3D and node.get_meta("placed", "") in ["framing", "dressing"]:
				var box := merged_aabb(node)
				if box.size != Vector3.ZERO: dressing.append([node, box, str(node.get_meta("placed", ""))])
	var near := float(profile.get("camera", {}).get("near_hide_m", 2.2))
	var eye := camera.global_position
	for row in dressing:
		var node: Node3D = row[0]
		if not is_instance_valid(node): continue
		var hide := false
		if s >= 0.5:
			var box: AABB = row[1]
			hide = row[2] == "framing" or box.grow(near).has_point(eye)
			for t in targets:
				if hide: break
				hide = box.grow(0.15).intersects_segment(eye, t) != null
		var key := node.get_instance_id()
		if hide and not hidden.has(key):
			hidden[key] = node.visible
			node.visible = false
		elif not hide and hidden.has(key):
			node.visible = hidden[key]
			hidden.erase(key)

func restore_lens() -> void:
	for row in dressing:
		var node = row[0]
		if is_instance_valid(node) and hidden.has(node.get_instance_id()): node.visible = hidden[node.get_instance_id()]
	hidden.clear()
	dressing.clear()

## World-space bounds of a placed piece (all its meshes).
static func merged_aabb(node: Node3D) -> AABB:
	var out := AABB()
	var first := true
	var stack: Array = [node]
	while not stack.is_empty():
		var n = stack.pop_back()
		if n is VisualInstance3D:
			var box: AABB = n.global_transform * n.get_aabb()
			out = box if first else out.merge(box)
			first = false
		for c in n.get_children(): stack.append(c)
	return out

func stop() -> void:
	active = false
	clear_markers()

## Drop everything at once without touching shader globals (the room look was already re-applied on a room change).
func reset() -> void:
	active = false
	weight = 0.0
	clear_all()

## The room profile's own kicker, exactly as look/rig.gd applied it (legacy rooms: the neutral global).
func room_kicker() -> Vector4:
	var view = host.presenter
	if view.room_root == null or not Rig.has_look(view.theme) or not Rig.has_profile(view.theme, view.room_root.profile_name()):
		return Rig.GLOBALS["n64_kicker"]
	var p: Dictionary = Rig.profile(view.theme, view.room_root.profile_name(), view.room_root.presentation.get("look", {}))
	var ac: Dictionary = p.get("actors", {})
	var ka = ac.get("kicker", [])
	var kk := Rig.term([ka[0], Rig.capped(float(ka[1]), "actor", "kicker_max")] if ka is Array and ka.size() >= 2 else ka, 0.0)
	return Vector4(kk.x, kk.y, kk.z, float(ac.get("kicker_up", 0.5)))

func ensure_root() -> void:
	if is_instance_valid(root): return
	root = Node3D.new()
	root.name = "combat_stage"
	host.presenter.world.add_child(root)

func blend_ticks() -> int:
	return int(profile.get("light", {}).get("blend_ticks", 30))

## One physics tick after the combat runtime (combat may be null while blending out).
## Projectiles and drops are game objects, not readability aids: drawn even with the whole profile off.
static func hazards_live(combat) -> bool:
	if combat == null: return false
	var shots = combat.get("projectiles")
	var drops = combat.get("drops")
	return (shots != null and not shots.is_empty()) or (drops != null and not drops.is_empty())

func tick(combat, camera: Camera3D) -> void:
	cues.clear()
	glyphs.clear()
	cool_down()
	if edge_ticks > 0: edge_ticks -= 1
	var b := blend_ticks()
	var before := weight
	if active: weight = 1.0 if b <= 0 else minf(1.0, weight + 1.0 / float(b))
	else: weight = 0.0 if b <= 0 else maxf(0.0, weight - 1.0 / float(b))
	if weight > 0.99999: weight = 1.0
	elif weight < 0.00001: weight = 0.0
	var s := smoothstep(0.0, 1.0, weight)
	# Only while blended (the last write restores the room's own kicker exactly); never outside combat.
	if weight > 0.0 or before > 0.0:
		if Rig.registered and lights: Rig.set_global("n64_kicker", base_kicker.lerp(target_kicker, s))
		motes(s)
		var sight := [host.presenter.player.position + Vector3.UP * 0.9]
		if combat != null:
			for enemy in combat.enemies:
				if enemy.hp > 0: sight.append(enemy.body.position + Vector3.UP * 0.9)
		lens_clear(smoothstep(0.0, 1.0, float(host.combat_camera.weight)), camera, sight)
	if weight <= 0.0 and not active and not hazards_live(combat):
		clear_all()
		return
	ensure_root()
	if lights: update_pool(s)
	else: s = 0.0
	var fighters := []
	var player = host.presenter.player
	fighters.append({"key": "player", "visual": player.get_node_or_null("visual"), "at": player.position, "fill": "player_fill", "scale": 1.0})
	if combat != null:
		for enemy in combat.enemies:
			if enemy.hp <= 0 or enemy.visual == null or not is_instance_valid(enemy.visual): continue
			fighters.append({"key": "enemy:" + enemy.identity, "visual": enemy.visual, "at": enemy.body.position, "fill": "enemy_fill", "scale": enemy.visual.scale.x, "enemy": enemy})
	var live := {}
	for f in fighters:
		if not lights: break
		live[f.key] = true
		shadow(f.key, f.at, float(f.scale))
		var flash := 0.0
		if f.has("enemy"): flash = flash_amount(f.enemy)
		fill(f.key, f.visual, f.at, str(f.fill), s, flash, camera)
	for key in shadows.keys():
		if not live.has(key): shadows[key].queue_free(); shadows.erase(key)
	for key in lit.keys():
		if not live.has(key): unlight(key)
	if combat != null and active: telegraphs(combat)
	else: clear_markers()
	if combat != null: projectiles(combat)

func update_pool(s: float) -> void:
	var cfg: Dictionary = profile.get("light", {}).get("pool", {})
	if arena.is_empty() or float(cfg.get("strength", 0.0)) <= 0.0: return
	if not is_instance_valid(pool):
		var lo: Array = arena.min
		var hi: Array = arena.max
		var size := maxf(float(hi[0]) - float(lo[0]), float(hi[2]) - float(lo[2])) * float(cfg.get("scale", 0.85))
		pool = disc(Vector3((float(lo[0]) + float(hi[0])) * 0.5, float(lo[1]) + 0.014, (float(lo[2]) + float(hi[2])) * 0.5), size,
			Readability.colour(cfg.get("color", "#fff0d4")), 0.0, "combat_pool", float(cfg.get("softness", 1.1)))
	pool.material_override.set_shader_parameter("strength", float(cfg.get("strength", 0.2)) * s)

func shadow(key: String, at: Vector3, scale: float) -> void:
	var cfg: Dictionary = profile.get("light", {}).get("contact_shadow", {})
	if float(cfg.get("strength", 0.0)) <= 0.0: return
	if not shadows.has(key):
		shadows[key] = disc(at, float(cfg.get("size_m", 1.0)) * scale, Readability.colour(cfg.get("color", "#05060c")), float(cfg.get("strength", 0.6)), "contact_" + key.replace(":", "_"), float(cfg.get("softness", 1.2)))
	var node: MeshInstance3D = shadows[key]
	node.position = Vector3(at.x, at.y + 0.018, at.z)

func disc(at: Vector3, size: float, col: Color, strength: float, label: String, softness := 1.4) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var q := QuadMesh.new()
	q.size = Vector2(size, size)
	mi.mesh = q
	var m := ShaderMaterial.new()
	m.shader = SHADOW
	m.set_shader_parameter("color", col)
	m.set_shader_parameter("strength", strength)
	m.set_shader_parameter("softness", softness)
	mi.material_override = m
	mi.name = label
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	root.add_child(mi)
	mi.position = at
	mi.rotation_degrees.x = -90.0
	return mi

## Pre-attack flash: 0..1 over the last telegraph.flash_ticks ticks before an enemy's contact window opens.
func flash_amount(enemy) -> float:
	var t: Dictionary = Telegraph.info(enemy, int(profile.get("telegraph", {}).get("danger_ticks", 10)))
	# attack_in (robots): ticks to the attack itself, so a drone flashes before it fires, not before the shot lands.
	var due := int(t.get("attack_in", t.get("contact_in", -1))) if not t.is_empty() else -1
	if due < 0: return 0.0
	var n := int(profile.get("telegraph", {}).get("flash_ticks", 10))
	if n <= 0 or due > n: return 0.0
	# A step pulse (two bands), never a rapid strobe: bright for the first half, softer for the second.
	return 1.0 if due > n / 2 else 0.6

## Defeat / phase beats: a short expanding floor ring at the robot (flat decal, no glow), BURST_TICKS long.
const BURST_TICKS := 24
var bursts := []
func effects(feedback: Array, _combat) -> void:
	ensure_root()
	for f in feedback:
		var kind := str(f.get("kind", ""))
		if not kind in ["boss_defeated", "phase", "defeated"] or not f.get("at") is Array: continue
		var p: Array = f.at
		bursts.append({"at": Vector3(p[0], p[1], p[2]), "age": 0, "size": 3.2 if kind == "boss_defeated" else (2.2 if kind == "phase" else 1.2), "n": stats.markers + bursts.size()})
	for b in bursts.duplicate():
		b.age += 1
		var key := "b:" + str(b.n)
		if b.age > BURST_TICKS:
			bursts.erase(b)
			if markers.has(key): markers[key].queue_free(); markers.erase(key)
			continue
		var k := float(b.age) / float(BURST_TICKS)
		marker(key, {"shape": "ring", "origin": b.at, "radius": 0.4 + float(b.size) * k, "inner": 0.82, "progress": 1.0 - k, "danger": true})

## Camera-side vertex fill on a fighter's own materials (per-instance; the shared room rig is untouched).
func fill(key: String, visual, at: Vector3, which: String, s: float, flash: float, camera: Camera3D) -> void:
	if visual == null or not is_instance_valid(visual) or visual.get("materials") == null: return
	var light: Dictionary = profile.get("light", {})
	var c := Readability.term(light.get(which, []), 0.0)
	if flash > 0.0:
		var fl := Readability.term(profile.get("telegraph", {}).get("flash_light", []), 0.0)
		c = c.lerp(fl, flash)
		stats.flashes += 1
	var off: Array = light.get("fill_offset_m", [1.7, 1.9])
	var toward := Vector3(0, 0, 1)
	if camera != null and is_instance_valid(camera):
		toward = camera.global_position - at
		toward.y = 0.0
		toward = toward.normalized() if toward.length() > 0.01 else Vector3(0, 0, 1)
	var p := at + toward * float(off[0]) + Vector3.UP * float(off[1])
	var radius := float(light.get("fill_radius_m", 4.6))
	for m in visual.materials:
		if m is ShaderMaterial:
			m.set_shader_parameter("point_light_pos", Vector4(p.x, p.y, p.z, radius))
			m.set_shader_parameter("point_light_col", Vector4(c.r * s, c.g * s, c.b * s, 1.0) if flash <= 0.0 else Vector4(c.r, c.g, c.b, 1.0))
	lit[key] = visual

func unlight(key: String) -> void:
	var visual = lit.get(key)
	lit.erase(key)
	if visual == null or not is_instance_valid(visual) or visual.get("materials") == null: return
	for m in visual.materials:
		if m is ShaderMaterial:
			m.set_shader_parameter("point_light_pos", Vector4.ZERO)
			m.set_shader_parameter("point_light_col", Vector4.ZERO)

## Floor decals for every telegraphing enemy (and shockwave bands), the dodge glyphs and the telegraph cues.
func telegraphs(combat) -> void:
	var cfg: Dictionary = profile.get("telegraph", {})
	if not bool(cfg.get("enabled", true)): return
	var live := {}
	var danger_ticks := int(cfg.get("danger_ticks", 10))
	for enemy in combat.enemies:
		var t: Dictionary = Telegraph.info(enemy, danger_ticks)
		if t.is_empty() or not t.has("shape"): continue
		var tpl := Readability.template_info(profile, enemy.data)
		if str(tpl.get("decal", "")) == "none": continue
		var key: String = "t:" + str(enemy.identity)
		live[key] = true
		marker(key, t)
		# Slam / surge: a thin outer ring shows how far the coming shockwave will reach.
		if t.has("reach"):
			live[key + ":reach"] = true
			marker(key + ":reach", {"shape": "ring", "origin": t.get("reach_at", t.origin), "radius": float(t.reach), "inner": 0.95,
				"progress": float(t.get("progress", 0.0)) * 0.5, "danger": false})
		if t.get("open", false) and bool(cfg.get("dodge_glyph", true)):
			glyphs.append({"at": enemy.body.position + Vector3.UP * (1.9 * enemy.visual.scale.y if enemy.visual != null and is_instance_valid(enemy.visual) else 1.9), "open": true})
			stats.glyph_ticks += 1
		var token: String = str(enemy.identity) + ":" + str(enemy.attack_id)
		if enemy.state == "telegraph" and not cued.has(token):
			cued[token] = true
			var cue: String = enemy.telegraph_cue() if enemy.has_method("telegraph_cue") else ""
			if cue == "": cue = str(tpl.get("audio", ""))
			if cue != "": cues.append(cue); stats.cues += 1
	var player_at: Vector3 = host.presenter.player.position
	var waves = combat.get("shockwaves")
	for wave in (waves if waves != null else []):
		var key := "w:" + str(wave.id)
		live[key] = true
		marker(key, wave.marker(danger_ticks, player_at))
		if wave.glyph_open(player_at) and bool(cfg.get("dodge_glyph", true)):
			glyphs.append({"at": player_at + Vector3.UP * 2.1, "open": true})
			stats.glyph_ticks += 1
	# Projectiles: a lane ahead of each live shot (the path to step out of) and the glyph over the shot when a roll
	# now would carry the player through it on i-frames.
	var shots = combat.get("projectiles")
	for shot in (shots if shots != null else []):
		if shot.reflected: continue
		var key := "p:" + str(shot.id)
		live[key] = true
		var m: Dictionary = shot.marker(danger_ticks, player_at)
		marker(key, m)
		if m.get("open", false) and bool(cfg.get("dodge_glyph", true)):
			glyphs.append({"at": shot.position + Vector3.UP * 0.55, "open": true})
			stats.glyph_ticks += 1
	for key in markers.keys():
		if not live.has(key) and not key.begins_with("b:") and key != "warm": markers[key].queue_free(); markers.erase(key)

func marker(key: String, t: Dictionary) -> void:
	var cfg: Dictionary = profile.get("telegraph", {})
	var shape := str(t.get("shape", "disc"))
	if not markers.has(key):
		var mi := MeshInstance3D.new()
		mi.mesh = QuadMesh.new()
		var m := ShaderMaterial.new()
		m.shader = MARKER
		m.set_shader_parameter("color", Readability.colour(cfg.get("color", "#d89a48")))
		m.set_shader_parameter("danger_color", Readability.colour(cfg.get("danger_color", "#d8583a")))
		m.set_shader_parameter("alpha", float(cfg.get("alpha", 0.5)))
		mi.material_override = m
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		mi.name = "telegraph_" + key.replace(":", "_")
		root.add_child(mi)
		markers[key] = mi
		stats.markers += 1
	var node: MeshInstance3D = markers[key]
	var mat: ShaderMaterial = node.material_override
	mat.set_shader_parameter("shape", int(SHAPES.get(shape, 0)))
	mat.set_shader_parameter("progress", float(t.get("progress", 0.0)))
	mat.set_shader_parameter("danger", 1.0 if t.get("danger", false) else 0.0)
	var origin: Vector3 = t.get("origin", Vector3.ZERO)
	var y := origin.y + 0.03
	if shape == "lane":
		var dir: Vector3 = t.get("dir", Vector3(0, 0, 1))
		var length := maxf(float(t.get("length", 1.0)), 0.1)
		var width := float(t.get("width", 1.0))
		(node.mesh as QuadMesh).size = Vector2(width, length)
		var mid := origin + dir * length * 0.5
		node.global_transform = Transform3D(Basis.IDENTITY, Vector3(mid.x, y, mid.z))
		# The quad lies flat after the -90 degree X turn with UV.y = 0 toward -Z and UV.y = 1 toward +Z; the yaw
		# then turns +Z onto dir, so the decal runs from the attacker (UV.y 0) to the tip (UV.y 1).
		node.rotation = Vector3(-PI / 2.0, atan2(dir.x, dir.z), 0.0)
		mat.set_shader_parameter("edge", clampf(0.05 / maxf(width, 0.2), 0.02, 0.2))
	else:
		var radius := maxf(float(t.get("radius", 1.0)), 0.1)
		(node.mesh as QuadMesh).size = Vector2(radius * 2.0, radius * 2.0)
		node.global_transform = Transform3D(Basis.IDENTITY, Vector3(origin.x, y, origin.z))
		node.rotation = Vector3(-PI / 2.0, 0.0, 0.0)
		mat.set_shader_parameter("inner", clampf(float(t.get("inner", 0.8)), 0.0, 0.98))
		mat.set_shader_parameter("edge", clampf(0.08 / radius, 0.015, 0.12))

## Projectile orbs with a ground dot, and reward drops (presentation copies of the runtime's lists).
func projectiles(combat) -> void:
	var live := {}
	for list_name in ["projectiles", "drops"]:
		var rows = combat.get(list_name)
		if rows == null: continue
		for row in rows:
			var key: String = str(list_name) + ":" + str(row.id)
			live[key] = true
			if not orbs.has(key):
				orbs[key] = orb(row.colour() if row.has_method("colour") else Color(0.85, 0.75, 0.4), float(row.radius) if row.get("radius") != null else 0.25, key)
			var node: Node3D = orbs[key]
			node.global_position = row.position
			# A deflected shot turns pale blue (it now flies back at its owner and can no longer hurt the player).
			if row.get("reflected") == true and not node.has_meta("turned"):
				node.set_meta("turned", true)
				for child in node.get_children():
					if child is MeshInstance3D and child.name != "dot": child.material_override = orb_material(row.colour())
			var dot: MeshInstance3D = node.get_node("dot")
			dot.global_position = Vector3(row.position.x, row.floor_y + 0.02 if row.get("floor_y") != null else 0.02, row.position.z)
	for key in orbs.keys():
		if not live.has(key): orbs[key].queue_free(); orbs.erase(key)

func orb(col: Color, radius: float, key: String) -> Node3D:
	var node := Node3D.new()
	node.name = "orb_" + key.replace(":", "_")
	var mi := MeshInstance3D.new()
	var sphere := SphereMesh.new()
	sphere.radius = radius
	sphere.height = radius * 2.0
	sphere.radial_segments = 8
	sphere.rings = 4
	mi.mesh = sphere
	mi.material_override = orb_material(col)
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	node.add_child(mi)
	root.add_child(node)
	var dot := disc(Vector3.ZERO, radius * 2.6, Color(0.02, 0.02, 0.05), 0.55, "dot", 1.2)
	dot.get_parent().remove_child(dot)
	node.add_child(dot)
	return node

## Orb materials are shared and kept for the whole process. A freed StandardMaterial3D releases its generated
## shader, so the next orb recompiled it: measured as a ~65 ms render stall on GL Compatibility at every boss shot
## (evidence/combat/perf-diag-*). Shot orange, deflected pale blue, drop green.
static var orb_materials := {}
static func orb_material(col: Color) -> StandardMaterial3D:
	var key := col.to_html()
	if not orb_materials.has(key):
		var m := StandardMaterial3D.new()
		m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		m.albedo_color = col
		orb_materials[key] = m
	return orb_materials[key]
const ORB_COLOURS := [Color(0.86, 0.56, 0.28), Color(0.55, 0.85, 0.95), Color(0.55, 0.95, 0.6)]

## Warm-up at the fight's start (the camera blend hides it): one sub-pixel orb per colour, marker and disc drawn for a
## couple of frames at the player's feet, so the renderer compiles their shaders now instead of at the first
## telegraph, shot or drop mid-fight.
var warm: Node3D
var warm_ticks := 0
func warm_up(with_orbs: bool) -> void:
	ensure_root()
	if is_instance_valid(warm): return
	warm = Node3D.new()
	warm.name = "warm_up"
	# Outside the stage root: clear_all() (profile off, nothing to show yet) must not drop it before it is drawn.
	host.presenter.world.add_child(warm)
	# 2 m in front of the drawing camera (inside its frustum, so it is really drawn; the player may stand outside the
	# authored view at the start of a fight).
	var cam: Camera3D = host.combat_camera.current() if host.combat_camera != null else null
	if cam == null: cam = host.presenter.camera
	warm.global_position = cam.global_position - cam.global_transform.basis.z * 2.0 if cam != null else host.presenter.player.position
	for col in (ORB_COLOURS if with_orbs else []):
		var mi := MeshInstance3D.new()
		var sphere := SphereMesh.new()
		sphere.radius = 0.002
		sphere.height = 0.004
		sphere.radial_segments = 8
		sphere.rings = 4
		mi.mesh = sphere
		mi.material_override = orb_material(col)
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		warm.add_child(mi)
	# The contact-disc shader also draws every orb's floor dot, so it is warmed whenever orbs can appear.
	if lights or with_orbs:
		var d := disc(Vector3.ZERO, 0.004, Color(0.02, 0.02, 0.05), 0.55, "warm_disc", 1.2)
		d.get_parent().remove_child(d)
		warm.add_child(d)
	if bool(profile.get("telegraph", {}).get("enabled", true)):
		marker("warm", {"shape": "disc", "origin": warm.global_position, "radius": 0.002, "inner": 0.0, "progress": 0.0, "danger": false})
	warm_ticks = 3

func cool_down() -> void:
	if warm_ticks <= 0: return
	warm_ticks -= 1
	if warm_ticks == 0:
		if is_instance_valid(warm): warm.queue_free()
		warm = null
		if markers.has("warm"): markers["warm"].queue_free(); markers.erase("warm")

## Telegraph decals go at once; defeat/phase bursts (b:*) finish their few ticks unless `everything`.
func clear_markers(everything := false) -> void:
	for key in markers.keys():
		if not everything and key.begins_with("b:"): continue
		if is_instance_valid(markers[key]): markers[key].queue_free()
		markers.erase(key)
	if everything: bursts.clear()
	glyphs.clear()

func clear_all() -> void:
	clear_markers(true)
	restore_lens()
	for key in lit.keys(): unlight(key)
	for node in shadows.values() + orbs.values():
		if is_instance_valid(node): node.queue_free()
	shadows.clear()
	orbs.clear()
	if is_instance_valid(pool): pool.queue_free()
	pool = null
	if is_instance_valid(root): root.queue_free()
	root = null

func dispose() -> void:
	clear_all()
	host = null
