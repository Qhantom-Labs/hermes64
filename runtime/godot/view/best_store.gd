extends RefCounted
## SCENES lane: local best time per game, keyed by game_hash. Local file only,
## never uploaded, never part of movie or save state. Replays do not write it.
const DEFAULT_PATH := "user://hermes64/best_times.json"
const MAX_ROWS := 256

static func _read(path: String) -> Dictionary:
	if not FileAccess.file_exists(path) or FileAccess.get_file_as_bytes(path).size() > 262144: return {}
	var data = JSON.parse_string(FileAccess.get_file_as_string(path))
	return data if data is Dictionary else {}

static func best(game_hash: String, path := DEFAULT_PATH) -> int:
	var row = _read(path).get(game_hash, null)
	if row is Dictionary and (row.get("ticks") is float or row.get("ticks") is int) and float(row.ticks) >= 0.0:
		return int(row.ticks)
	return -1

## Returns {"best": ticks, "previous": ticks or -1, "new_best": bool, "written": bool}.
static func record(game_hash: String, ticks: int, code: String, path := DEFAULT_PATH) -> Dictionary:
	var rows := _read(path)
	var previous := best(game_hash, path)
	var is_new := ticks >= 0 and (previous < 0 or ticks < previous)
	var written := false
	if is_new:
		rows[game_hash] = {"ticks": ticks, "code": code}
		while rows.size() > MAX_ROWS: rows.erase(rows.keys()[0])
		DirAccess.make_dir_recursive_absolute(path.get_base_dir())
		var f := FileAccess.open(path + ".tmp", FileAccess.WRITE)
		if f != null:
			f.store_string(JSON.stringify(rows, "", true)); f.close()
			written = DirAccess.rename_absolute(path + ".tmp", path) == OK
	return {"best": ticks if is_new else previous, "previous": previous, "new_best": is_new, "written": written}
