extends RefCounted
# Core texture generators (theme-agnostic). A pack recipe picks a generator, a size and palette
# indices; every texel is snapped to the pack palette. Deterministic: seed = hash(pack:name).

const Pack = preload("res://look/pack.gd")

static var cache := {}

static func clear() -> void:
	cache = {}

static func get_tex(name: String) -> ImageTexture:
	var key := Pack.current_id + ":" + name
	if cache.has(key):
		return cache[key]
	var img := make_image(name)
	var t := ImageTexture.create_from_image(img)
	cache[key] = t
	return t

# A SEPARATE texture object with the same texels, for the nearest/3-point sampler.
# Compatibility (GLES3) keeps filter state per texture object: binding one texture to two
# uniforms with different filter hints in one material makes one hint win (measured: the
# nearest and bilinear captures differed by 8 of 76800 px). Distinct objects fix it.
static func get_tex_nearest(name: String) -> ImageTexture:
	var key := Pack.current_id + ":" + name + "#nearest"
	if cache.has(key):
		return cache[key]
	var t := ImageTexture.create_from_image(get_tex(name).get_image())
	cache[key] = t
	return t

# Tileable value noise on an n x n lattice.
static func _lattice(rng: RandomNumberGenerator, n: int) -> PackedFloat32Array:
	var a := PackedFloat32Array()
	a.resize(n * n)
	for i in n * n:
		a[i] = rng.randf()
	return a

static func _vnoise(lat: PackedFloat32Array, n: int, u: float, v: float) -> float:
	var x := u * n
	var y := v * n
	var x0 := int(floor(x))
	var y0 := int(floor(y))
	var fx := x - x0
	var fy := y - y0
	fx = fx * fx * (3.0 - 2.0 * fx)
	fy = fy * fy * (3.0 - 2.0 * fy)
	var i00 := lat[posmod(y0, n) * n + posmod(x0, n)]
	var i10 := lat[posmod(y0, n) * n + posmod(x0 + 1, n)]
	var i01 := lat[posmod(y0 + 1, n) * n + posmod(x0, n)]
	var i11 := lat[posmod(y0 + 1, n) * n + posmod(x0 + 1, n)]
	return lerpf(lerpf(i00, i10, fx), lerpf(i01, i11, fx), fy)

static func make_image(name: String) -> Image:
	var r: Dictionary = Pack.recipe(name)
	if r.is_empty():
		r = {"gen": "noise", "c": [4, 5, 3]}
	var gen: String = r.get("gen", "noise")
	var size: int = int(r.get("size", 32))
	if gen == "face":
		return _face(r)
	if gen == "env":
		return _env(r, size)
	var C: Array[Color] = []
	for i in r.get("c", [0]):
		C.append(Pack.pal(int(i)))
	while C.size() < 6:
		C.append(C[C.size() - 1])
	var img := Image.create(size, size, false, Image.FORMAT_RGBA8)
	var rng := RandomNumberGenerator.new()
	rng.seed = hash(Pack.current_id + ":" + name) & 0x7fffffff
	var lat := _lattice(rng, 4)
	var lat2 := _lattice(rng, 8)
	var px: int = int(r.get("px", 8))
	for y in size:
		for x in size:
			var n1 := _vnoise(lat, 4, float(x) / size, float(y) / size)
			var n2 := _vnoise(lat2, 8, float(x) / size, float(y) / size)
			img.set_pixel(x, y, Pack.nearest(_sample(gen, x, y, size, px, n1, n2, C)))
	img.generate_mipmaps()
	return img

# Generators: c[] are palette colours chosen by the pack.
static func _sample(gen: String, x: int, y: int, s: int, px: int, n1: float, n2: float, c: Array[Color]) -> Color:
	match gen:
		"boards":       # c: base, alt, seam, nail
			var board := x / px
			var tone: float = [0.0, 0.45, 0.15, 0.7][board % 4]
			var col := c[0].lerp(c[1], tone * 0.5).darkened((n2 - 0.5) * 0.35)
			if x % px == 0:
				col = c[2]
			if (y + board * 11) % s == 3 and x % px == px / 2:
				col = c[3]
			return col
		"blocks":       # c: base, alt, mortar
			var row := y / px
			var off := px if row % 2 == 1 else 0
			var bx := (x + off) % (px * 2)
			var col := c[0].lerp(c[1], n1).darkened((n2 - 0.5) * 0.3)
			if y % px == 0 or bx == 0:
				col = c[2]
			return col
		"cobbles":      # c: body, body2, mortar, edge, highlight
			var cx := (x + int(n1 * 3.0)) % px
			var cy := (y + int(n2 * 3.0)) % px
			var d := Vector2(cx - (px - 1) * 0.5, cy - (px - 1) * 0.5).length()
			var col := c[0].lerp(c[1], n2 * 0.8)
			if d > px * 0.45:
				col = c[2]
			elif d > px * 0.35:
				col = c[3]
			elif d < px * 0.15 and n1 > 0.6:
				col = c[4]
			return col
		"noise":        # c: a, b, stain
			var col := c[0].lerp(c[1], n1)
			return col.lerp(c[2], clampf((n2 - 0.62) * 2.5, 0.0, 1.0))
		"slates":       # c: a, b, line
			var row := y / px
			var off := px / 2 if row % 2 == 1 else 0
			var col := c[0].lerp(c[1], n1)
			if y % px == 0 or (x + off) % px == 0:
				col = c[2]
			return col
		"ripples":      # c: a, b, crest
			var w := sin((x + n1 * 8.0) * TAU / 16.0) * 0.5 + 0.5
			var col := c[0].lerp(c[1], n2)
			if w > 0.85 and (y % 4 == 0):
				col = c[2]
			return col
		"panel":        # c: base, alt, rivet
			var col := c[0].lerp(c[1], n1)
			if (x % 16 == 2 or x % 16 == 13) and (y % 16 == 2 or y % 16 == 13):
				col = c[2]
			return col
		"panes":        # c: glass a, glass b, frame, glint
			var col := c[0].lerp(c[1], n1 * 0.8 + (1.0 - float(y) / s) * 0.3)
			if x % 16 < 1 or y % 16 < 1:
				col = c[2]
			elif (x + y) % 11 == 0 and n2 > 0.55:
				col = c[3]
			return col
		"radial":       # c: centre, edge
			var d := Vector2(x - s / 2.0, y - s / 2.0).length() / (s / 2.0)
			return c[0].lerp(c[1], clampf(d, 0.0, 1.0))
		"quilt":        # c: a, b, seam  (diamond quilting, vinyl)
			var u := posmod(x + y, px)
			var v := posmod(x - y, px)
			var e := minf(minf(u, px - u), minf(v, px - v)) / (px * 0.5)
			var col := c[1].lerp(c[0], clampf(e * 1.6, 0.0, 1.0))
			if e < 0.12:
				col = c[2]
			return col
		"gloss":        # c: a, b, glint  (molded glossy surface)
			var col := c[0].lerp(c[1], n1 * 0.7 + float(y) / s * 0.3)
			if n2 > 0.78 and (x + y * 3) % 7 == 0:
				col = c[2]
			return col
		"stripes":      # c: a, b
			return c[0] if (y / maxi(px, 1)) % 2 == 0 else c[1]
		_:
			return c[0]

# Env map for chrome/glass (sphere map): vertical stops top -> bottom plus glints.
static func _env(r: Dictionary, size: int) -> Image:
	var stops: Array = r.get("stops", [7, 5, 3, 1])
	var img := Image.create(size, size, false, Image.FORMAT_RGBA8)
	for y in size:
		for x in size:
			var d := Vector2(x - size / 2.0, y - size / 2.0) / (size / 2.0)
			if d.length() > 1.0:
				img.set_pixel(x, y, Pack.pal(int(stops[stops.size() - 1])))
				continue
			var t := float(y) / (size - 1) * (stops.size() - 1)
			var i := clampi(int(floor(t)), 0, stops.size() - 2)
			var col := Pack.pal(int(stops[i])).lerp(Pack.pal(int(stops[i + 1])), t - i)
			img.set_pixel(x, y, Pack.nearest(col))
	for g in r.get("glints", []):
		var gx: int = int(g[0] * size)
		var gy: int = int(g[1] * size)
		for dy in range(-1, 2):
			for dx in range(-1, 2):
				if absi(dx) + absi(dy) <= 1:
					img.set_pixel(clampi(gx + dx, 0, size - 1), clampi(gy + dy, 0, size - 1), Pack.pal(int(r.get("glint", 7))))
	return img

# Face atlas: 32x16, two 16x16 frames (eyes open | blink). UV-swapped at runtime (no blendshapes).
static func _face(r: Dictionary) -> Image:
	var c: Array = r.get("c", [28, 15, 0, 31, 29, 27])   # skin, brow, eye, glint, shadow, mouth
	var img := Image.create(32, 16, false, Image.FORMAT_RGBA8)
	img.fill(Pack.pal(int(c[0])))
	for f in 2:
		var ox := f * 16
		for x in [4, 5, 10, 11]:
			img.set_pixel(ox + x, 5, Pack.pal(int(c[1])))
		if f == 0:
			for p in [Vector2i(4, 7), Vector2i(5, 7), Vector2i(10, 7), Vector2i(11, 7),
					Vector2i(4, 8), Vector2i(5, 8), Vector2i(10, 8), Vector2i(11, 8)]:
				img.set_pixel(ox + p.x, p.y, Pack.pal(int(c[2])))
			img.set_pixel(ox + 5, 7, Pack.pal(int(c[3])))
			img.set_pixel(ox + 11, 7, Pack.pal(int(c[3])))
		else:
			for x in [4, 5, 10, 11]:
				img.set_pixel(ox + x, 8, Pack.pal(int(c[4])))
		img.set_pixel(ox + 8, 10, Pack.pal(int(c[4])))
		for x in [6, 7, 8, 9]:
			img.set_pixel(ox + x, 12, Pack.pal(int(c[5])))
	return img
