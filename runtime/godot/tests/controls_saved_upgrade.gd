extends SceneTree
## Saved settings upgrade is deliberately NOT the movie/full-profile decoder.
const ActionsType=preload("res://input/actions.gd")
const Profile=preload("res://input/profile.gd")
var failures:=[]
var checks:=0
func check(ok: bool,label: String) -> void:
	checks+=1
	if not ok: failures.append(label); printerr("FAIL ",label)
func _initialize() -> void:
	var fixture: Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://tests/fixtures/feel2_legacy_input.json"))
	var a=ActionsType.new()
	var path:="res://../feel2-legacy-saved.json"
	for handed in ["left","right"]:
		var raw: Dictionary=fixture.cases[0].profile.duplicate(true)
		raw.preset=handed
		if handed=="right":
			for pair in [["primary",KEY_ENTER],["secondary",KEY_CTRL],["focus",KEY_SLASH],["dodge",KEY_ALT],["action_menu",KEY_BACKSPACE]]:
				raw.bindings[pair[0]]=[{"key":pair[1]}]+raw.bindings[pair[0]].filter(func(e):return not e.has("key"))
		check(Profile.validate(raw).ok and not Profile.validate(raw).profile.bindings.has("run"),handed+" original full movie profile still decodes as legacy")
		var file:=FileAccess.open(path,FileAccess.WRITE);file.store_string(JSON.stringify(raw));file.close()
		var before:=FileAccess.get_sha256(path)
		check(a.load_remap(path).ok,handed+" live saved settings load")
		check(a.profile.bindings.has("run") and a.binding_glyph("run")=="Sh" and a.binding_glyph("walk")=="Alt",handed+" live old defaults upgrade to Shift run / Alt precision")
		check(a.binding_glyph("camera_recenter")=="V" and a.binding_glyph("camera_up")=="U",handed+" saved defaults get free recenter and pitch keys")
		check(a.profile.options.run_mode=="hold",handed+" former default auto becomes FEEL2 hold default")
		check(FileAccess.get_sha256(path)==before,handed+" load upgrade does not overwrite saved bytes")
	var custom: Dictionary=fixture.cases[0].profile.duplicate(true)
	custom.bindings.walk=[{"key":KEY_B}];custom.bindings.primary=[{"key":KEY_SHIFT}]
	custom.options.run_mode="toggle"
	var file:=FileAccess.open(path,FileAccess.WRITE);file.store_string(JSON.stringify(custom));file.close()
	check(a.load_remap(path).ok and a.binding_glyph("primary")=="Sh" and a.binding_glyph("walk")=="B","upgrade preserves explicitly remapped old actions")
	check(a.profile.bindings.has("run") and a.binding_glyph("run")!="Sh" and a.profile.options.run_mode=="toggle","occupied new defaults choose an unused key without stealing the remap")
	var crowded: Dictionary=fixture.cases[0].profile.duplicate(true)
	crowded.bindings.primary=[KEY_ALT,KEY_G,KEY_H,KEY_N,KEY_B,KEY_HOME,KEY_END,KEY_INSERT].map(func(code): return {"key":code})
	file=FileAccess.open(path,FileAccess.WRITE);file.store_string(JSON.stringify(crowded));file.close()
	check(Profile.validate(crowded).ok,"eight-entry crowded legacy profile is valid")
	var crowded_result: Dictionary=a.load_remap(path)
	var crowded_expected: Dictionary=JSON.parse_string(FileAccess.get_file_as_string(path))
	check(crowded_result.ok and a.profile.bindings.has("run") and a.profile.bindings.primary==crowded_expected.bindings.primary,"crowded fallback upgrade finds another unused key without discarding custom remaps")
	var exhausted: Dictionary=fixture.cases[0].profile.duplicate(true)
	var used:=[]
	for action in exhausted.bindings:
		for entry in exhausted.bindings[action]:
			if entry.has("key"): used.append(int(entry.key))
	var todo:=[]
	for code in Profile.saved_key_candidates(KEY_ALT):
		if code not in used and code not in todo: todo.append(code)
	for action in exhausted.bindings:
		while exhausted.bindings[action].size()<8 and not todo.is_empty(): exhausted.bindings[action].append({"key":todo.pop_back()})
	check(Profile.validate(exhausted).ok and todo.is_empty(),"valid full saved profile can occupy every physical fallback candidate")
	file=FileAccess.open(path,FileAccess.WRITE);file.store_string(JSON.stringify(exhausted));file.close()
	var retained: Dictionary=a.load_remap(path)
	var exhausted_expected: Dictionary=JSON.parse_string(FileAccess.get_file_as_string(path))
	check(retained.ok and retained.has("warning") and a.profile.bindings==exhausted_expected.bindings and a.profile.options.run_mode==exhausted.options.run_mode,"true key exhaustion preserves complete saved remaps with explicit warning, never defaults")
	a.free()
	print("CONTROLS SAVED UPGRADE ",JSON.stringify({"checks":checks,"failures":failures}))
	quit(0 if failures.is_empty() else 1)
