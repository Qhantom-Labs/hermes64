extends RefCounted
## Room light rig, fog and grade from pack data (view.json "look"). Theme-agnostic: no colour lives here
## except neutral fallbacks used when a pack supplies no "look" block (legacy packs keep their old look).

const GLOBALS := {
	"n64_fog_color": Vector4(0.15, 0.15, 0.2, 1), "n64_fog": Vector4(6, 28, 1, 1), "n64_mode": Vector4(1, 1, 1, 0),
	"n64_sun_dir": Vector4(0.3, 0.85, 0.45, 0), "n64_sun_col": Vector4(0.45, 0.45, 0.45, 1),
	"n64_ambient": Vector4(0.55, 0.55, 0.55, 1), "n64_sky": Vector4(0, 0, 0, 1), "n64_ground": Vector4(0, 0, 0, 1),
	"n64_fill_dir": Vector4(-0.5, 0.3, -0.4, 0), "n64_fill_col": Vector4(0, 0, 0, 1), "n64_rim": Vector4(0, 0, 0, 2),
	"n64_spec": Vector4(0, 0, 0, 16), "n64_pl0_pos": Vector4.ZERO, "n64_pl0_col": Vector4.ZERO,
	"n64_pl1_pos": Vector4.ZERO, "n64_pl1_col": Vector4.ZERO, "n64_pl2_pos": Vector4.ZERO, "n64_pl2_col": Vector4.ZERO,
	"n64_pl3_pos": Vector4.ZERO, "n64_pl3_col": Vector4.ZERO, "n64_grade": Vector4(1, 1, 1, 1),
	"n64_lift": Vector4(0, 0, 0, 1), "n64_gain": Vector4(1, 1, 1, 1), "n64_bake": Vector4(0, 0, 0, 0),
	"n64_debug": Vector4(0, 0, 0, 0),
	"n64_room": Vector4(0, 2, 3, 0), "n64_room2": Vector4(0.4, 0, 0, 0), "n64_chrome": Vector4(1, 0.9, 0.85, 1.4),
	"n64_actor": Vector4(0, 0, 0, 2.5), "n64_kicker": Vector4(0, 0, 0, 0.5), "n64_px": Vector4(0, 0, 0, 0),
	"n64_classic": Vector4(1, 1, 1, 1), "n64_lattice": Vector4(0, 0, 0, 0), "n64_filter": Vector4(0, 0, 0, 0),
}

## Current n64_classic gate (x per-pixel point lights, y specular glints, z fresnel rims, w per-pixel gloss; 1 = as
## the data says, 0 = off). Capture passes switch it off temporarily and restore this value.
static var classic := Vector4(1, 1, 1, 1)

## Shared N64 look convention (theme.json "n64" = kits/core/n64_look.json under the pack's explicit overrides).
## Empty for runtime-only test packs, which then keep the legacy behaviour exactly.
static var conv := {}

const FILTERS := {"nearest": 0.0, "bilinear": 1.0, "three_point": 2.0, "bilinear_nomip": 3.0, "n64": 4.0}

static func lighting() -> Dictionary:
	return conv.get("lighting", {})

## Convention gate on the non-N64 lighting features (data may only switch them on through an explicit pack override).
static func classic_gate() -> Vector4:
	var l := lighting()
	if l.is_empty(): return GLOBALS["n64_classic"]
	return Vector4(1.0 if bool(l.get("per_pixel_point_lights", true)) else 0.0, 1.0 if bool(l.get("specular_glints", true)) else 0.0,
		1.0 if bool(l.get("fresnel_rim", true)) else 0.0, 1.0 if bool(l.get("per_pixel_gloss", true)) else 0.0)

## Virtual vertex lattice for point lights on static surfaces (metres; 0 = per-vertex on the real mesh).
static func lattice() -> Vector4:
	return Vector4(float(lighting().get("lattice_m", 0.0)), 0, 0, 0)

## Texture filter for world surfaces: the room profile's explicit choice, else the convention's world filter.
static func world_filter(profile_filter = null) -> float:
	if profile_filter != null: return float(FILTERS.get(str(profile_filter), 1.0))
	return float(FILTERS.get(str(conv.get("filtering", {}).get("world", "bilinear")), 1.0))

## Character texture filter code for the derived actor shader (legacy: nearest).
static func actor_filter() -> float:
	return float(FILTERS.get(str(conv.get("filtering", {}).get("actors", "nearest")), 0.0))

## Upper bound from the convention (lighting.<group>.<key>), or the value itself when the convention is silent.
static func capped(v: float, group: String, key: String) -> float:
	var g = lighting().get(group, {})
	if g is Dictionary and g.has(key): return minf(v, float(g[key]))
	return v

## ROOMLOOK r3 globals back to neutral (legacy rooms render exactly as before).
static func neutral_extras() -> void:
	for key in ["n64_room", "n64_room2", "n64_chrome", "n64_actor", "n64_kicker", "n64_px", "n64_classic", "n64_lattice", "n64_filter"]:
		set_global(key, GLOBALS[key])
	classic = classic_gate()
	set_global("n64_classic", classic)
	set_global("n64_lattice", lattice())
	set_global("n64_filter", Vector4(float(conv.get("filtering", {}).get("lod_bias", 0.0)), 0, 0, 0))

static var registered := false

## Global uniforms are added once per process (listing them is editor-only in Godot 4.6).
static func ensure_globals() -> void:
	if registered: return
	for key in GLOBALS:
		RenderingServer.global_shader_parameter_add(key, RenderingServer.GLOBAL_VAR_TYPE_VEC4, GLOBALS[key])
	registered = true

static func set_global(key: String, v: Vector4) -> void:
	RenderingServer.global_shader_parameter_set(key, v)

static func col(v, fallback := Color(1, 1, 1)) -> Color:
	if v is String: return Color.from_string(v, fallback)
	return fallback

## ["#hex", strength] -> Vector4(rgb * strength, 1)
static func term(v, fallback := 0.0) -> Vector4:
	if v is Array and v.size() >= 2:
		var c := col(v[0])
		var k := float(v[1])
		return Vector4(c.r * k, c.g * k, c.b * k, float(v[2]) if v.size() > 2 else 1.0)
	return Vector4(fallback, fallback, fallback, 1.0)

static func dir(v, fallback: Vector3) -> Vector4:
	if v is Array and v.size() == 3:
		var d := Vector3(float(v[0]), float(v[1]), float(v[2])).normalized()
		return Vector4(d.x, d.y, d.z, 0)
	return Vector4(fallback.x, fallback.y, fallback.z, 0)

## Merge pack profile + optional per-room overrides (presentation "look").
static func profile(theme: Dictionary, name: String, overrides: Dictionary = {}) -> Dictionary:
	var look: Dictionary = theme.get("look", {})
	var base: Dictionary = look.get("profiles", {}).get(name, look.get("profiles", {}).get("interior", {})).duplicate(true)
	for k in overrides: base[k] = overrides[k]
	return base

static func has_look(theme: Dictionary) -> bool:
	return theme.get("look", {}).has("profiles")

## A room uses the rig when its profile (or the "interior" fallback) exists in the pack look block.
static func has_profile(theme: Dictionary, name: String) -> bool:
	var profiles: Dictionary = theme.get("look", {}).get("profiles", {})
	return profiles.has(name) or profiles.has("interior")

## Apply a resolved profile + room lights (array of {pos: Vector3, color: Color, intensity, radius}).
static func apply(p: Dictionary, lights: Array) -> void:
	ensure_globals()
	set_global("n64_ambient", term(p.get("ambient"), 0.55))
	set_global("n64_sky", term(p.get("sky"), 0.0))
	set_global("n64_ground", term(p.get("ground"), 0.0))
	set_global("n64_sun_col", term(p.get("key"), 0.45))
	set_global("n64_sun_dir", dir(p.get("key_dir"), Vector3(0.3, 0.85, 0.45)))
	set_global("n64_fill_col", term(p.get("fill"), 0.0))
	set_global("n64_fill_dir", dir(p.get("fill_dir"), Vector3(-0.5, 0.3, -0.4)))
	var rim = p.get("rim", [])
	var r := term(rim, 0.0)
	set_global("n64_rim", Vector4(r.x, r.y, r.z, float(rim[2]) if rim is Array and rim.size() > 2 else 2.5))
	var sp = p.get("spec", [])
	var sc := col(sp[0] if sp is Array and sp.size() > 0 else "#000000", Color.BLACK)
	set_global("n64_spec", Vector4(sc.r, sc.g, sc.b, float(sp[1]) if sp is Array and sp.size() > 1 else 16.0))
	var fog: Dictionary = p.get("fog", {})
	if not fog.is_empty():
		var fc := col(fog.get("color", "#222233"))
		set_global("n64_fog_color", Vector4(fc.r, fc.g, fc.b, 1))
		set_global("n64_fog", Vector4(float(fog.get("near", 6)), float(fog.get("far", 28)), 1.0, float(fog.get("max", 1.0))))
	set_global("n64_bake", Vector4(float(p.get("bake_desaturate", 0.0)), 0, 0, 0))
	var g: Dictionary = p.get("grade", {})
	set_global("n64_grade", Vector4(float(g.get("contrast", 1.0)), float(g.get("saturation", 1.0)), float(g.get("gamma", 1.0)), float(g.get("exposure", 1.0))))
	var lift := col(g.get("lift", "#000000"), Color.BLACK)
	var gain := col(g.get("gain", "#ffffff"), Color.WHITE)
	set_global("n64_lift", Vector4(lift.r, lift.g, lift.b, 1))
	set_global("n64_gain", Vector4(gain.r, gain.g, gain.b, 1))
	set_global("n64_mode", Vector4(world_filter(p.get("filter", null)) if not conv.is_empty() else float(FILTERS.get(str(p.get("filter", "bilinear")), 1.0)), 1, 1, 1))
	# value structure: darker ceilings and wall bases against a lit floor (profile "room")
	var room: Dictionary = p.get("room", {})
	var cen: Array = room.get("centre", [0, 0])
	set_global("n64_room", Vector4(float(room.get("top_dark", 0.0)), float(room.get("top_from", 2.0)), float(room.get("top_to", 3.0)), float(room.get("base_ao", 0.0))))
	set_global("n64_room2", Vector4(float(room.get("base_height", 0.4)), float(room.get("floor_lift", 0.0)), float(cen[0]), float(cen[1])))
	var ch: Dictionary = p.get("chrome", {})
	# painted chrome (convention lighting.chrome): no white-hot boosts or fresnel catch beyond the convention bounds
	var hot_from := float(ch.get("hot_from", 0.9))
	var cg = lighting().get("chrome", {})
	if cg is Dictionary and cg.has("hot_from_min"): hot_from = maxf(hot_from, float(cg.hot_from_min))
	set_global("n64_chrome", Vector4(capped(float(ch.get("gamma", 1.0)), "chrome", "gamma_max"), hot_from,
		capped(float(ch.get("hot", 0.85)), "chrome", "hot_max"), capped(float(ch.get("rim", 1.4)), "chrome", "rim_max")))
	# characters: the world rig plus a modest kicker (convention lighting.actor bounds the rim and kicker)
	var ac: Dictionary = p.get("actors", {})
	var ra = ac.get("rim", [])
	var ka = ac.get("kicker", [])
	var ar := term([ra[0], capped(float(ra[1]), "actor", "rim")] if ra is Array and ra.size() >= 2 else ra, 0.0)
	var kk := term([ka[0], capped(float(ka[1]), "actor", "kicker_max")] if ka is Array and ka.size() >= 2 else ka, 0.0)
	set_global("n64_actor", Vector4(ar.x, ar.y, ar.z, float(ac.get("rim_exponent", 2.5))))
	set_global("n64_kicker", Vector4(kk.x, kk.y, kk.z, float(ac.get("kicker_up", 0.5))))
	set_global("n64_px", Vector4(1.0 if bool(p.get("pixel_lights", false)) else 0.0, 0, 0, 0))
	set_global("n64_classic", classic)
	set_global("n64_lattice", lattice())
	for i in 4:
		var pos := Vector4.ZERO
		var c4 := Vector4.ZERO
		if i < lights.size():
			var l: Dictionary = lights[i]
			var lp: Vector3 = l.pos
			var lc: Color = l.color
			var k := float(l.get("intensity", 1.0))
			pos = Vector4(lp.x, lp.y, lp.z, float(l.get("radius", 4.0)))
			c4 = Vector4(lc.r * k, lc.g * k, lc.b * k, 1)
		set_global("n64_pl%d_pos" % i, pos)
		set_global("n64_pl%d_col" % i, c4)

## Display colour of a value after the grade (used for the clear colour so void matches graded fog).
static func graded(c: Color, p: Dictionary) -> Color:
	var g: Dictionary = p.get("grade", {})
	var v := Vector3(c.r, c.g, c.b) * float(g.get("exposure", 1.0))
	var lift := col(g.get("lift", "#000000"), Color.BLACK)
	var gain := col(g.get("gain", "#ffffff"), Color.WHITE)
	v = Vector3(lift.r, lift.g, lift.b) + v * (Vector3(gain.r, gain.g, gain.b) - Vector3(lift.r, lift.g, lift.b))
	v = v.clamp(Vector3.ZERO, Vector3.ONE)
	var gm := 1.0 / maxf(float(g.get("gamma", 1.0)), 0.01)
	v = Vector3(pow(v.x, gm), pow(v.y, gm), pow(v.z, gm))
	var l := v.dot(Vector3(0.299, 0.587, 0.114))
	v = Vector3(l, l, l).lerp(v, float(g.get("saturation", 1.0)))
	v = (v - Vector3(0.5, 0.5, 0.5)) * float(g.get("contrast", 1.0)) + Vector3(0.5, 0.5, 0.5)
	v = v.clamp(Vector3.ZERO, Vector3.ONE)
	return Color(v.x, v.y, v.z)
