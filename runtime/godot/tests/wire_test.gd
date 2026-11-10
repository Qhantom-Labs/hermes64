extends SceneTree
const Wire = preload("res://core/wire.gd")
var passed := 0
var failed := 0
func expect(ok: bool, label: String) -> void:
	if ok: passed += 1
	else: failed += 1
	print("PASS " if ok else "FAIL ", label)
func parse_literal(text: String):
	var path := ProjectSettings.globalize_path("res://../evidence/wire-literal.json")
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(text)
	file.close()
	return Wire.read_json(path)
func _initialize() -> void:
	var data = parse_literal('{"tick":0,"timestamps":{"number":1.0},"label":"number 1.0, escaped \\\"tick\\\":1"}')
	expect(typeof(data.tick) == TYPE_INT, "CONTROL integer wire token becomes native int")
	expect(typeof(data.timestamps.number) == TYPE_FLOAT, "opaque timestamp float token remains float")
	data = parse_literal('{"tick":0.0,"nested":[1e0,-2,0.25,true,"3.0"]}')
	expect(typeof(data.tick) == TYPE_FLOAT, "integral float tick remains float for strict save rejection")
	expect(typeof(data.nested[0]) == TYPE_FLOAT, "scientific token remains float")
	expect(typeof(data.nested[1]) == TYPE_INT and data.nested[1] == -2, "CONTROL negative integer token preserved")
	expect(typeof(data.nested[2]) == TYPE_FLOAT and data.nested[2] == 0.25, "CONTROL fractional token preserved")
	expect(typeof(data.nested[3]) == TYPE_BOOL and data.nested[4] == "3.0", "CONTROL numeric-looking strings and bool not converted")
	print("WIRE SUMMARY passed=%d failed=%d" % [passed, failed])
	quit(0 if failed == 0 else 1)
