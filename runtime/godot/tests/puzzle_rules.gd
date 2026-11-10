extends SceneTree
## Replays tools/puzzle_vectors.py walks through modules/puzzle/rules.gd: keys, legality and events must match.
const Rules = preload("res://modules/puzzle/rules.gd")
var failures := []
var checks := 0

func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok and failures.size() < 20: failures.append(label)

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var text := FileAccess.get_file_as_string("res://puzzle-vectors.json")
	var data = JSON.parse_string(text)
	expect(data is Dictionary and data.get("version") == 1, "vector file present")
	if data is Dictionary:
		for row in data.puzzles:
			var r = Rules.new()
			r.configure(row.room, row.puzzle, row.config)
			for walk in row.walks:
				var label := "%s/%s/%s" % [row.source, row.puzzle.id, walk.entry]
				var c: Dictionary = r.ctx([], [], [], [], walk.ctx.inventory)
				var out: Array = r.canonical(c, walk.entry)
				var st: Dictionary = out[0]
				expect(str(r.key(st)) == walk.canonical, label + " canonical key")
				expect(out[1].map(func(e): return Rules.event_token(e)) == walk.canonical_events, label + " canonical events")
				if not out[1].is_empty():
					c = r.after(c, out[1])
					st = r.settle(st, c, 0)[0]
				var index := 0
				for step in walk.steps:
					var res = r.advance(st, c, step.token)
					expect((res != null) == bool(step.ok), "%s step %d %s legality" % [label, index, step.token])
					var events: Array = []
					if res != null:
						st = res[0]
						events = res[1]
						if not events.is_empty():
							c = r.after(c, events)
							var more: Array = r.settle(st, c, 0)
							st = more[0]
							events = events + more[1]
							if not more[1].is_empty(): c = r.after(c, more[1])
					expect(str(r.key(st)) == step.key, "%s step %d %s key %s != %s" % [label, index, step.token, str(r.key(st)), step.key])
					expect(events.map(func(e): return Rules.event_token(e)) == step.events, "%s step %d %s events" % [label, index, step.token])
					index += 1
	if failures.is_empty():
		print("PUZZLE_RULES ok checks=%d" % checks)
		quit(0)
	else:
		print("PUZZLE_RULES failed checks=%d first=%s" % [checks, str(failures)])
		quit(1)
