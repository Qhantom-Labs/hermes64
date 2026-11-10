extends SceneTree
## MOVE: replay a movie's frames (bot source, exact original frames) and write the
## per-tick room/position trace. Run on the control and MOVE stages to locate and
## explain the first divergence. Test-only; never re-pins or edits the movie.
const View = preload("res://playtest/view.gd")
const Wire = preload("res://core/wire.gd")
var view
var opts := {}
var original := {}
var rows := []
var cursor := 0

class Inject extends Node:
	var runner
	func _physics_process(_delta: float) -> void:
		var r = runner
		if r.cursor < r.original.frames.size(): r.view.actions.submit_frame(r.original.frames[r.cursor])

class Tail extends Node:
	var runner
	func _physics_process(_delta: float) -> void:
		var r = runner
		var p: Vector3 = r.view.player.position
		r.rows.append([r.cursor, str(r.view.runtime.state.location), snappedf(p.x,0.0001), snappedf(p.z,0.0001)])
		r.cursor += 1
		if r.cursor >= r.original.frames.size(): r.complete()

func _initialize() -> void: call_deferred("run")

func run() -> void:
	for arg in OS.get_cmdline_user_args():
		var parts := arg.trim_prefix("--").split("=",true,1)
		if parts.size() == 2: opts[parts[0]] = parts[1]
	view = View.new(); root.add_child(view)
	var boot: Dictionary = view.boot(Wire.read_json("res://game.json"),{"pack":"res://theme.json","bindings":"res://bindings.json","test":true})
	if not boot.ok: quit(2); return
	original = Wire.read_json(opts.movie)
	view.actions.configure(original.header.profile); view.actions.set_source("bot")
	var restored: Dictionary = view.replay.restore_state(original.header.initial)
	if not restored.ok: print("TRACE_RESTORE ",restored); quit(2); return
	view.set_physics_process(true); view.player.set_physics_process(true)
	var inject := Inject.new(); inject.runner = self; inject.process_physics_priority = -200; root.add_child(inject)
	var tail := Tail.new(); tail.runner = self; tail.process_physics_priority = 150; root.add_child(tail)

var done := false
func complete() -> void:
	if done: return
	done = true
	var out := {"ticks":rows.size(),"rows":rows,"final_room":str(view.runtime.state.location),"ended":view.runtime.state.get("ended",""),"flags":view.runtime.state.get("flags",{})}
	var f := FileAccess.open(opts.output,FileAccess.WRITE); f.store_string(JSON.stringify(out)); f.close()
	print("MOVE_TRACE ticks=",rows.size()," final_room=",out.final_room)
	view.quit_cleanly(0)
