extends SceneTree
const ActionsType = preload("res://input/actions.gd")
var failures := []
var checks := 0
func check(ok: bool, label: String) -> void:
	checks += 1
	if not ok: failures.append(label); printerr("FAIL ",label)
func _initialize() -> void:
	var a := ActionsType.new()
	var path := "res://../bad-controls.json"
	for raw in ["{", "null", "[]", '{"version":1.5}', '{"version":1,"bindings":{"primary":[{"button":true}]}}', '{"version":1,"bindings":{"primary":[{"axis":0,"sign":0}]}}', '{"version":1,"bindings":{"primary":[{"button":0,"ctrl":true}]}}', '{"version":1,"bindings":{"primary":[{"axis":0,"sign":1,"with":2}]}}']:
		var f := FileAccess.open(path,FileAccess.WRITE); f.store_string(raw); f.close()
		check(not a.load_remap(path).ok,"reject malformed remap file "+raw)
		check(a.binding_glyph("primary")=="E","safe defaults after bad file")
	var f := FileAccess.open(path,FileAccess.WRITE); f.store_string(" ".repeat(65537)); f.close()
	check(not a.load_remap(path).ok,"reject oversized file")
	check(a.save_remap({"version":1,"preset":"right"},path).ok,"atomic preset save")
	check(a.load_remap(path).ok and a.binding_glyph("primary")=="Ent","right-hand persisted")
	# Pause settings save full profiles, including pad axis signs parsed as floats.
	for preset in ["left","right"]:
		check(a.configure({"version":1,"preset":preset,"options":{"run_mode":"toggle"},"bindings":{"run":[{"key":KEY_G}],"walk":[{"key":KEY_N}]}}).ok,preset+" full run profile configures")
		var cfg := {"version":1,"preset":preset,"bindings":a.profile.bindings.duplicate(true),"options":a.profile.options.duplicate(),"tuning":a.profile.tuning.duplicate()}
		check(a.save_remap(cfg,path).ok,preset+" full run profile saves")
		a.configure({"version":1})
		var loaded: Dictionary = a.load_remap(path)
		check(loaded.ok,"%s full run profile reloads: %s" % [preset,loaded.get("reason","")])
		check(a.profile.options.run_mode == "toggle" and a.binding_glyph("run") == "G" and a.binding_glyph("walk") == "N",preset+" saved mode and both independent remaps survive reload")
	# Bonus pad chords suppress their component actions while held and on release.
	a.configure({"version":1}); a.set_source("live")
	Input.action_press("h64_key_move_up"); Input.action_press("h64_key_primary")
	a.advance(a.sample_live())
	check(a.is_pressed("primary") and a.get_move().y<0,"real InputMap sampled into same semantic provider")
	Input.action_release("h64_key_move_up"); Input.action_release("h64_key_primary")
	for i in 6: a.advance(a.sample_live())
	check(a.get_move()==Vector2.ZERO and not a.is_pressed("primary"),"real InputMap release")
	a.configure({"version":1,"options":{"run_mode":"toggle"}}); a.restore({})
	a.advance({"digital":["run"]}); a.advance({})
	check(a.is_pressed("run"),"toggle run persists")
	a.advance({"digital":["run"]}); check(not a.is_pressed("run"),"toggle run off")
	a.configure({"version":1,"options":{"run_mode":"hold"}}); a.restore({}); a.set_context("pause")
	a.advance({}); check(not a.just_pressed("run"),"pause settings do not auto-activate run")
	a.advance({"digital":["run"]}); check(a.just_pressed("run"),"pause settings Shift uses physical run press")
	a.configure({"version":1,"bindings":{"quick_save":[{"button":JOY_BUTTON_DPAD_LEFT}]}}); a.restore({})
	Input.action_press("h64_pad_quick_save"); a.advance(a.sample_live())
	check(a.just_pressed("quick_save"),"single-button pad save remap needs no implicit chord")
	Input.action_release("h64_pad_quick_save")
	a.free(); DirAccess.remove_absolute(path)
	print("CONTROLS REMAP ",JSON.stringify({"checks":checks,"failures":failures}))
	quit(0 if failures.is_empty() else 1)
