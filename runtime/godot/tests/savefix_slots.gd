extends SceneTree
## SAVEFIX: per-game save slots and one-time legacy adoption in playtest/release.gd (docs/SAVES.md).
## godot --headless --path runtime/godot --script res://tests/savefix_slots.gd -- <scratch dir> <report.json>
## Also prints OS.get_user_data_dir() so the caller can check application/config/custom_user_dir_name resolution.
const Release = preload("res://playtest/release.gd")

func _initialize() -> void:
	call_deferred("run")

func write(path: String, text: String) -> void:
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var f := FileAccess.open(path, FileAccess.WRITE)
	f.store_string(text)
	f.close()

func run() -> void:
	var args := OS.get_cmdline_user_args()
	var scratch: String = args[0]
	var out := {"user_data_dir": OS.get_user_data_dir(), "checks": {}}
	var c: Dictionary = out.checks
	var a := {"id": "thaw", "game_hash": "ga", "spec_hash": "sa"}
	var b := {"id": "relay_combat", "game_hash": "gb", "spec_hash": "sb"}
	# Paths: desktop (dir already per game) and web (shared /userfs, id in path).
	c.desktop_a = Release.slot_path(a, false, "Hermes64/thaw")
	c.desktop_b = Release.slot_path(b, false, "Hermes64/relay_combat")
	c.web_a = Release.slot_path(a, true, "Hermes64/thaw")
	c.web_b = Release.slot_path(b, true, "Hermes64/relay_combat")
	c.misconfigured_a = Release.slot_path(a, false, "AdventureRuntime")
	c.misconfigured_b = Release.slot_path(b, false, "AdventureRuntime")
	c.bad_id = Release.slot_path({"id": "../x", "game_hash": "0123456789abcdef99"}, true, "")
	c.legacy_desktop = Release.legacy_paths(false, scratch.path_join("data"))
	c.legacy_web = Release.legacy_paths(true, "")
	# Migration on absolute paths under scratch.
	var legacy: String = scratch.path_join("data/Adventure Runtime/saves/slot1.json")
	var legacy_text := JSON.stringify({"game_hash": "ga", "spec_hash": "sa", "room": "kitchen"})
	write(legacy, legacy_text)
	write(legacy + ".controls.json", "{\"story\":1}")
	var cands := Release.legacy_paths(false, scratch.path_join("data"))
	var ta := scratch.path_join("data/Hermes64/thaw/saves/slot1.json")
	var tb := scratch.path_join("data/Hermes64/relay_combat/saves/slot1.json")
	c.migrate_a = Release.migrate_legacy(a, ta, cands)
	c.migrated_bytes_equal = FileAccess.get_file_as_string(ta) == legacy_text
	c.migrated_controls = FileAccess.file_exists(ta + ".controls.json")
	c.legacy_kept = FileAccess.get_file_as_string(legacy) == legacy_text
	c.migrate_b_other_build = Release.migrate_legacy(b, tb, cands)
	c.b_slot_exists = FileAccess.file_exists(tb)
	# Own slot present: never overwritten, even by a matching legacy save.
	write(ta, "{\"own\":true}")
	c.migrate_a_again = Release.migrate_legacy(a, ta, cands)
	c.own_kept = FileAccess.get_file_as_string(ta) == "{\"own\":true}"
	# Flat legacy layout (%APPDATA%\Adventure Runtime\slot1.json) is also adopted.
	var flat: String = scratch.path_join("data2/Adventure Runtime/slot1.json")
	write(flat, JSON.stringify({"game_hash": "gb", "spec_hash": "sb"}))
	var tb2 := scratch.path_join("data2/Hermes64/relay_combat/saves/slot1.json")
	c.migrate_flat = Release.migrate_legacy(b, tb2, Release.legacy_paths(false, scratch.path_join("data2")))
	# Corrupt legacy: ignored.
	var bad: String = scratch.path_join("data3/Adventure Runtime/saves/slot1.json")
	write(bad, "not json")
	c.migrate_corrupt = Release.migrate_legacy(a, scratch.path_join("data3/Hermes64/thaw/saves/slot1.json"), Release.legacy_paths(false, scratch.path_join("data3")))
	var f := FileAccess.open(args[1], FileAccess.WRITE)
	f.store_string(JSON.stringify(out, " ", true))
	f.close()
	quit(0)
