extends Node
## GAPS2 G14: frame capture for a replayed module game (a developer/agent command; never part of play).
## main.gd attaches it for `--replay <movie> --capture_scenes=<folder>`: the replay then does not quit at its final
## hash. This node saves one frame per scene card (at half its hold), one per room entry (30 frames after the doorway
## envelope ends, when no scene plays) and the results card (45 frames after it shows), then writes
## <folder>/capture.json and quits. It reads state only: no input, no story or module writes.
## Frames need a rendered window (view.capture returns false when headless).

var view
var folder := ""
var tail_seconds := 90.0
var rows := []
var seen_cards := {}
var seen_rooms := {}
var busy := false
var room_id := ""
var room_wait := 0
var results_frames := -1
var after_finish := 0.0
var done := false

func attach(presenter, out_folder: String, tail: float) -> void:
	view = presenter
	folder = out_folder
	tail_seconds = maxf(1.0, tail)
	name = "scene_capture"
	process_priority = 300
	DirAccess.make_dir_recursive_absolute(folder)

func _process(delta: float) -> void:
	if done or busy or view == null or view.scene_cards == null: return
	var sc = view.scene_cards
	if view.replay != null and view.replay.finished:
		after_finish += delta
		if after_finish > tail_seconds:
			finish("tail_timeout")
			return
	if sc.phase == "results":
		results_frames += 1
		if results_frames == 45:
			await shot("results", {"kind": "results", "rows": sc.results_receipt.get("rows", []).size()})
			finish("results_captured")
		return
	if sc.phase == "card" and not sc.scene.is_empty():
		var sid := str(sc.scene.get("id", ""))
		var key := "%s:%d" % [sid, sc.card_index]
		if not seen_cards.has(key) and sc.card_time >= sc.card_hold * 0.5:
			seen_cards[key] = true
			var card: Dictionary = sc.card
			await shot("scene-%s-%d" % [sid, sc.card_index + 1], {"kind": "scene", "scene": sid, "card": sc.card_index + 1,
				"subtitle": card.get("subtitle") is Dictionary, "title": card.has("title"), "actors": (card.get("actors", []) as Array).size()})
		return
	var location: String = view.runtime.state.location
	if seen_rooms.has(location): return
	var settled: bool = sc.phase == "idle" and not sc.frozen and (view.room_transition == null or not view.room_transition.active())
	if not settled or location != room_id:
		room_id = location
		room_wait = 0
		return
	room_wait += 1
	if room_wait >= 30:
		seen_rooms[location] = true
		await shot("room-" + location, {"kind": "room", "room": location})

func shot(file_name: String, row: Dictionary) -> void:
	busy = true
	var ok: bool = await view.capture(folder.path_join(file_name + ".png"))
	row["file"] = file_name + ".png"
	row["ok"] = ok
	row["tick"] = int(view.actions.tick)
	row["replay_cursor"] = int(view.replay.cursor) if view.replay != null else -1
	row["text_box"] = bool(view.n64_ui != null and view.n64_ui.visible and view.n64_ui.dlg_on)
	row["room_name_card"] = view.room_transition != null and not view.room_transition.card_layout().is_empty()
	rows.append(row)
	busy = false

func finish(status: String) -> void:
	if done: return
	done = true
	var receipt := {"status": status, "frames": rows, "replay": view.replay.result if view.replay != null else {},
		"scenes": view.scene_cards.receipts, "display": DisplayServer.get_name(), "engine": Engine.get_version_info().string,
		"scope": "frames of a replayed bot movie; read-only observer"}
	var f := FileAccess.open(folder.path_join("capture.json"), FileAccess.WRITE)
	if f != null:
		f.store_string(JSON.stringify(receipt, "  ", true))
		f.close()
	print("SCENE_CAPTURE status=%s frames=%d" % [status, rows.size()])
	view.quit_cleanly(0 if status == "results_captured" else 1)
