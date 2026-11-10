extends CanvasLayer
## Presentation-only weather layer (L5 CYBER-ROOMS). Screen-space rain streaks drawn over the 3D view.
## OFF unless asked: the pack's theme sets look.weather.rain.enabled = true, or a room's presentation sets
## weather.rain (a room may also switch it off). It never reads or writes simulation state, input, the camera,
## collision or the clock; it only animates with frame delta. Deterministic streak layout from a fixed seed.
##
## Use (one call where a room's presentation is built; the integrator adds it, L5 does not edit room.gd):
##   var Weather = preload("res://view/weather.gd")
##   Weather.attach(self, Weather.config_from(theme, room_presentation))

const DEFAULTS := {"enabled": false, "streaks": 140, "color": "#a9b8ff", "alpha": 0.32, "length": 16.0,
	"speed": 820.0, "slant": 0.2, "width": 1.0, "seed": 7}

var cfg: Dictionary = {}
var _drops: PackedVector3Array = PackedVector3Array()   # x, y in 0..1 viewport fractions; z = speed factor
var _canvas: Control


static func config_from(theme: Dictionary, room_presentation: Dictionary = {}) -> Dictionary:
	var out: Dictionary = DEFAULTS.duplicate()
	var pack_rain = theme.get("look", {}).get("weather", {}).get("rain", {})
	if pack_rain is Dictionary:
		out.merge(pack_rain, true)
	var room_rain = room_presentation.get("weather", {}).get("rain", null)
	if room_rain is bool:
		out["enabled"] = room_rain
	elif room_rain is Dictionary:
		out.merge(room_rain, true)
	return out if bool(out.get("enabled", false)) else {}


static func attach(parent: Node, config: Dictionary) -> Node:
	if config.is_empty() or not bool(config.get("enabled", false)):
		return null
	var layer = load("res://view/weather.gd").new()
	layer.name = "weather"
	layer.setup(config)
	parent.add_child(layer)
	return layer


func setup(config: Dictionary) -> void:
	cfg = DEFAULTS.duplicate()
	cfg.merge(config, true)
	layer = 5
	var rng := RandomNumberGenerator.new()
	rng.seed = int(cfg.seed)
	_drops.resize(clampi(int(cfg.streaks), 0, 600))
	for i in _drops.size():
		_drops[i] = Vector3(rng.randf(), rng.randf(), rng.randf_range(0.75, 1.25))
	_canvas = Control.new()
	_canvas.name = "streaks"
	_canvas.set_anchors_preset(Control.PRESET_FULL_RECT)
	_canvas.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_canvas.draw.connect(_draw_streaks)
	add_child(_canvas)


func drop_count() -> int:
	return _drops.size()


func _process(delta: float) -> void:
	if _canvas == null:
		return
	var size := _canvas.get_viewport_rect().size
	if size.y <= 0.0:
		return
	var fall := float(cfg.speed) * delta / size.y
	for i in _drops.size():
		var d := _drops[i]
		d.y += fall * d.z
		d.x += fall * d.z * float(cfg.slant) * size.y / max(size.x, 1.0)
		if d.y > 1.0:
			d.y -= 1.0
		if d.x > 1.0:
			d.x -= 1.0
		_drops[i] = d
	_canvas.queue_redraw()


func _draw_streaks() -> void:
	var size := _canvas.get_viewport_rect().size
	var col := Color.from_string(String(cfg.color), Color(0.66, 0.72, 1.0))
	col.a = float(cfg.alpha)
	var slen := float(cfg.length)
	var dir := Vector2(float(cfg.slant), 1.0).normalized()
	for d in _drops:
		var p := Vector2(d.x * size.x, d.y * size.y)
		_canvas.draw_line(p, p + dir * slen * d.z, col, float(cfg.width))
