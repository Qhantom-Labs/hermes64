extends RefCounted
## Combat readability profile (COMBAT lane). Presentation only: the simulation never reads it.
## Resolution order: runtime defaults (readability.json) -> the pack view.json "combat" block -> the room's
## presentation "combat" block (per-region override, metadata.presentation.rooms[room].combat). Every numeric override
## is clamped to the defaults' "ranges"; light strengths are also capped by the N64 convention
## (lighting.actor.kicker_max for the kicker, lighting.lamp_pool.max_strength for the floor pool).
const DEFAULTS_PATH := "res://modules/combat/readability.json"
const Rig = preload("res://look/rig.gd")
static var cached := {}

static func defaults() -> Dictionary:
	if cached.is_empty() and FileAccess.file_exists(DEFAULTS_PATH):
		var d = JSON.parse_string(FileAccess.get_file_as_string(DEFAULTS_PATH))
		if d is Dictionary: cached = d
	return cached

## Deep merge: dictionaries merge key by key; anything else replaces (arrays included).
static func merge(base: Dictionary, over) -> Dictionary:
	var out := base.duplicate(true)
	if not over is Dictionary: return out
	for k in over:
		if out.get(k) is Dictionary and over[k] is Dictionary: out[k] = merge(out[k], over[k])
		elif k != "ranges": out[k] = over[k] if not over[k] is Dictionary else (over[k] as Dictionary).duplicate(true)
	return out

static func resolve(theme: Dictionary, room_presentation: Dictionary) -> Dictionary:
	var base := defaults()
	var p := merge(base, theme.get("combat", {}))
	p = merge(p, room_presentation.get("combat", {}))
	p["ranges"] = base.get("ranges", {}).duplicate(true)
	clamp_ranges(p)
	cap_light(p)
	return p

static func clamp_ranges(p: Dictionary) -> void:
	var ranges: Dictionary = p.get("ranges", {})
	for key in ranges:
		var parts: PackedStringArray = str(key).split(".")
		if parts.size() != 2 or not p.get(parts[0]) is Dictionary: continue
		var group: Dictionary = p[parts[0]]
		var r: Array = ranges[key]
		var v = group.get(parts[1])
		if v is float or v is int:
			var c := clampf(float(v), float(r[0]), float(r[1]))
			group[parts[1]] = int(round(c)) if (r[0] is int and r[1] is int) or str(parts[1]).ends_with("_ticks") or parts[1] == "edge_px" else c
		elif v != null:
			group[parts[1]] = r[0]

## Light strengths never exceed the N64 convention's bounds (the "style profile's allowed ranges").
static func cap_light(p: Dictionary) -> void:
	var light: Dictionary = p.get("light", {})
	var k = light.get("kicker", [])
	if k is Array and k.size() >= 2: light["kicker"] = [str(k[0]), Rig.capped(clampf(float(k[1]), 0.0, 1.0), "actor", "kicker_max")]
	var pool = light.get("pool", {})
	if pool is Dictionary:
		var s := clampf(float(pool.get("strength", 0.0)), 0.0, 1.0)
		var lp = Rig.lighting().get("lamp_pool", {})
		if lp is Dictionary and lp.has("max_strength"): s = minf(s, float(lp.max_strength))
		pool["strength"] = s
	for key in ["player_fill", "enemy_fill"]:
		var f = light.get(key, [])
		if f is Array and f.size() >= 2: light[key] = [str(f[0]), clampf(float(f[1]), 0.0, 1.2)]
	var shadow = light.get("contact_shadow", {})
	if shadow is Dictionary: shadow["strength"] = clampf(float(shadow.get("strength", 0.0)), 0.0, 0.8)

## Template presentation (decal kind, audio cue) with an archetype's own "telegraph" block on top.
static func template_info(p: Dictionary, data: Dictionary) -> Dictionary:
	var t: String = str(data.get("fsm", {}).get("template", ""))
	var row: Dictionary = p.get("templates", {}).get(t, {}).duplicate(true)
	var own = data.get("telegraph", {})
	if own is Dictionary:
		for k in own: row[k] = own[k]
	if not row.has("audio"): row["audio"] = p.get("telegraph", {}).get("audio", "")
	return row

static func colour(v, fallback := Color(1, 1, 1)) -> Color:
	if v is String: return Color.from_string(v, fallback)
	if v is Array and v.size() >= 1 and v[0] is String: return Color.from_string(v[0], fallback)
	return fallback

## ["#hex", strength] -> Color * strength (alpha 1)
static func term(v, fallback := 0.0) -> Color:
	if v is Array and v.size() >= 2:
		var c := colour(v[0])
		var k := float(v[1])
		return Color(c.r * k, c.g * k, c.b * k, 1.0)
	return Color(fallback, fallback, fallback, 1.0)
