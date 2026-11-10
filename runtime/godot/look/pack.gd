extends RefCounted
# Theme pack loader. A pack is DATA only (lane-look/packs/<id>/pack.json):
#   palette (<=32 sRGB hex), named colours, texture recipes (generator + palette indices),
#   light/fog rigs, UI colours, env-map recipes. Core code never hard-codes theme colours.

static var current: Dictionary = {}
static var current_id := ""
static var _palette: Array[Color] = []

static func load_pack(dir: String, id: String) -> bool:
	var p := dir.path_join(id).path_join("pack.json")
	if not FileAccess.file_exists(p):
		push_error("pack not found: " + p)
		return false
	var d = JSON.parse_string(FileAccess.get_file_as_string(p))
	if typeof(d) != TYPE_DICTIONARY:
		push_error("pack is not a JSON object: " + p)
		return false
	current = d
	current_id = id
	_palette = []
	for h in d.get("palette", []):
		_palette.append(Color(str(h)))
	return true

static func palette() -> Array[Color]:
	return _palette

static func pal(i: int) -> Color:
	return _palette[clampi(i, 0, _palette.size() - 1)]

# "#hex"/"hex" or a named pack colour ("warm", "fog", ...) or "p<index>".
static func color(v, def := "ffffff") -> Color:
	if v == null:
		v = def
	var s := str(v)
	var named: Dictionary = current.get("colors", {})
	if named.has(s):
		return color(named[s], def)
	if s.begins_with("p") and s.substr(1).is_valid_int():
		return pal(int(s.substr(1)))
	return Color(s)

static func recipe(name: String) -> Dictionary:
	return current.get("textures", {}).get(name, {})

static func rig(name: String) -> Dictionary:
	return current.get("rigs", {}).get(name, {})

static func ui(key: String, def: String) -> Color:
	return color(current.get("ui", {}).get(key, def), def)

static func nearest(c: Color) -> Color:
	var best := Color.BLACK
	var bd := 1e9
	for p in _palette:
		var d := (p.r - c.r) * (p.r - c.r) * 0.30 + (p.g - c.g) * (p.g - c.g) * 0.59 + (p.b - c.b) * (p.b - c.b) * 0.11
		if d < bd:
			bd = d
			best = p
	return best

# KITS LUT layout: 256x16, x = b*16 + r, y = g (4-bit sRGB) -> nearest palette colour.
static func make_lut() -> ImageTexture:
	var img := Image.create(256, 16, false, Image.FORMAT_RGB8)
	for g in 16:
		for b in 16:
			for r in 16:
				img.set_pixel(b * 16 + r, g, nearest(Color(r / 15.0, g / 15.0, b / 15.0)))
	return ImageTexture.create_from_image(img)
