extends SceneTree
const Runtime = preload("res://core/runtime.gd")
var assertions := 0
var failures := []
var positive_steps := 0
var negative_steps := 0

func check(ok: bool, msg: String) -> void:
	assertions += 1
	if not ok:
		failures.append(msg)
		if failures.size() < 20:
			print("DIVERGENCE ", msg)

func read_json(path: String):
	return preload("res://core/wire.gd").read_json(path)

func _initialize() -> void:
	var started := Time.get_ticks_usec()
	var args := OS.get_cmdline_user_args()
	if args.is_empty():
		print("Usage: --script res://tests/replay.gd -- /absolute/replays.json [graph.json]")
		quit(2)
		return
	var loaded = read_json(args[0])
	if not loaded is Dictionary:
		print("Invalid or missing replay JSON: ", args[0], "; use an absolute path")
		quit(2)
		return
	var data: Dictionary = loaded
	var game: Dictionary = read_json(data.game)
	for trace in data.traces:
		var r = Runtime.new()
		check(r.configure(game).ok, trace.name + " configure")
		for index in trace.steps.size():
			var step: Dictionary = trace.steps[index]
			var site: String = "%s step=%d %s" % [trace.name, index, step.action]
			check(r.state == step.before, site + " before")
			var choices: Array = r.actions(r.state)
			var ids := []
			for a in choices:
				ids.append(a.id)
				if a.id == step.action:
					check(a.label == step.label, site + " label")
			check(ids == step.available, site + " complete legal action list")
			for negative in step.negative:
				var before: Dictionary = r.state.duplicate(true)
				var rejection: Dictionary = r.step(negative.action)
				check(not rejection.ok and rejection.get("reason") == negative.reason and r.state == before, site + " negative " + negative.action)
				negative_steps += 1
			var result: Dictionary = r.step(step.action)
			check(result.ok, site + " accepted")
			check(r.state == step.after, site + " full effects")
			positive_steps += 1
		check(r.state == trace.final, trace.name + " final state")
		check(r.endings(r.state) == trace.terminal, trace.name + " terminal equals checker claim")
		print("REPLAY ", trace.name, " steps=", trace.steps.size(), " ending=", r.endings(r.state))
	var graph_states := 0
	var graph_edges := 0
	if args.size() > 1:
		var graph: Dictionary = read_json(args[1])
		var r = Runtime.new()
		r.configure(game)
		for case in graph.states:
			graph_states += 1
			check(r.endings(case.state) == case.endings, "graph endings %d" % graph_states)
			var actual: Array = r.actions(case.state)
			check(actual.size() == case.actions.size(), "graph action count %d" % graph_states)
			for i in mini(actual.size(), case.actions.size()):
				var expected: Dictionary = case.actions[i]
				if graph_states == 1 and actual[i].id == "wait":
					print("WAIT DIAGNOSTIC actual=", JSON.stringify(actual[i]), " expected=", JSON.stringify(expected), " state=", JSON.stringify(graph.states[int(expected.next)].state))
				check(actual[i].id == expected.id and actual[i].label == expected.label and actual[i].state == graph.states[int(expected.next)].state, "graph transition %d %s" % [graph_states, expected.id])
				graph_edges += 1
	var summary := {"assertions": assertions, "failures": failures, "witnesses": data.traces.size(), "positive_steps": positive_steps,
		"negative_steps": negative_steps, "graph_states": graph_states, "graph_edges": graph_edges, "elapsed_ms": (Time.get_ticks_usec() - started) / 1000.0}
	print("REPLAY SUMMARY assertions=%d failures=%d witnesses=%d positive=%d negative=%d graph_states=%d graph_edges=%d elapsed_ms=%.3f" % [assertions, failures.size(), data.traces.size(), positive_steps, negative_steps, graph_states, graph_edges, summary.elapsed_ms])
	var file := FileAccess.open(args[0].get_base_dir().path_join("godot-replay-result.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(summary, "\t"))
	file.close()
	quit(0 if failures.is_empty() else 1)
