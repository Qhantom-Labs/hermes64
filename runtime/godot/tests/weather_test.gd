extends SceneTree
## L5: weather layer is off by default, opt-in by pack theme or room, room can switch it off, presentation-only.
const Weather = preload("res://view/weather.gd")
var passed := 0
var failed := 0
func expect(ok: bool, label: String) -> void:
	if ok: passed += 1
	else: failed += 1
	print("PASS " if ok else "FAIL ", label)
func _initialize() -> void:
	call_deferred("run")
func run() -> void:
	expect(Weather.config_from({}).is_empty(), "no weather config -> off")
	expect(Weather.attach(root, Weather.config_from({})) == null, "attach with empty config adds nothing")
	var pack := {"look": {"weather": {"rain": {"enabled": true, "streaks": 90}}}}
	var cfg := Weather.config_from(pack)
	expect(not cfg.is_empty() and int(cfg.streaks) == 90, "pack asks for rain -> on with pack values")
	expect(Weather.config_from(pack, {"weather": {"rain": false}}).is_empty(), "room can switch pack rain off")
	expect(not Weather.config_from({}, {"weather": {"rain": true}}).is_empty(), "room can ask for rain")
	var before := root.get_child_count()
	var node = Weather.attach(root, cfg)
	expect(node != null and root.get_child_count() == before + 1 and node.drop_count() == 90, "attach adds one layer with 90 streaks")
	var a: PackedVector3Array = node._drops.duplicate()
	for i in 3:
		await process_frame
	expect(node._drops != a, "streaks animate on frames")
	var other = Weather.attach(root, cfg)
	var b: PackedVector3Array = other._drops
	var c = load("res://view/weather.gd").new()
	c.setup(cfg)
	expect(c._drops == a, "fixed seed -> identical layout")
	c.free()
	print("weather_test passed=%d failed=%d" % [passed, failed])
	quit(1 if failed else 0)
