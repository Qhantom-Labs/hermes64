extends RefCounted
## Optional toolkit manifest; no paths/code come from STORY gameplay data.
const CLIPS = ["idle_combat","swing","hurt","death","roll","block"]
var rows := {}
var error := ""
func configure(data, resolver) -> bool:
	rows = {}
	error = ""
	if data == null: return true # conspicuous placeholder mode is admitted separately
	if not data is Dictionary or data.get("api_version") != "1.0.0" or not data.get("bindings") is Dictionary:
		error = "invalid combat binding manifest"; return false
	for identity in data.bindings:
		var pin = data.bindings[identity]
		if not pin is Dictionary or not pin.get("character_id") is String or not pin.get("sha256") is String:
			error = "invalid combat actor pin"; return false
		var found := false
		for row in resolver.characters:
			if row.character_id != pin.character_id: continue
			if row.get("placeholder",true) or row.sha256 != pin.sha256 or FileAccess.get_sha256(row.path) != pin.sha256:
				error = "combat actor missing/corrupt/placeholder"; return false
			for clip in CLIPS:
				if not row.animations.has(clip): error = "combat clip missing: "+clip; return false
			rows[identity] = {"id":identity,"body_id":row.body_id,"base_rig_id":row.base_rig_id,"params":row.params.duplicate(true)}
			found = true
		if not found: error = "unknown combat character_id"; return false
	return true
func character(identity: String, resolver):
	return resolver.character(rows[identity]) if rows.has(identity) else null
