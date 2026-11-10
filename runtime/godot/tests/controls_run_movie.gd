extends SceneTree
## Strict new-run movies, plus optional unchanged pre-FEEL2 cross-build fixture.
const View = preload("res://playtest/view.gd")
const Wire = preload("res://core/wire.gd")
const Movie = preload("res://input/movie.gd")
var view
var checks := 0
var failures := []
var receipts := []
func check(ok: bool, label: String) -> void:
	checks += 1
	if not ok: failures.append(label); printerr("FAIL ",label)
func _initialize() -> void: call_deferred("run")
func frame(digital := []) -> void:
	view.actions.submit_frame({"digital":digital})
	await physics_frame; await process_frame
func replay_twice(movie: Dictionary, label: String) -> void:
	var results := []
	for repeat in 2:
		var opened: Dictionary = view.replay.begin_playback(movie,false)
		check(opened.ok,label+" strict playback opens")
		if not opened.ok: return
		for i in movie.frames.size()+10:
			await physics_frame; await process_frame
			if view.replay.finished: break
		check(view.replay.finished and view.replay.result.get("ok",false),label+" every recorded checkpoint matches")
		results.append(view.replay.result.duplicate(true))
	check(results[0] == results[1],label+" two playbacks identical")
	receipts.append({"case":label,"ticks":movie.frames.size(),"checkpoints":movie.hashes.size(),"results":results})
func run() -> void:
	var legacy_path := ""
	var output := "res://../feel2-run-movies"
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--legacy-movie="): legacy_path = arg.trim_prefix("--legacy-movie=")
		if arg.begins_with("--evidence="): output = arg.trim_prefix("--evidence=")
	view = View.new(); root.add_child(view)
	check(view.boot(Wire.read_json("res://game.json"),{"pack":"res://theme.json","bindings":"res://bindings.json","test":true}).ok,"boot local movie fixture")
	view.actions.configure({"version":1}); view.actions.set_source("bot")
	for i in 5: await frame()
	var initial: Dictionary = view.replay.state()
	if legacy_path != "":
		var file_hash := FileAccess.get_sha256(legacy_path)
		var legacy: Dictionary = Wire.read_json(legacy_path)
		var frames_hash := Movie.digest(legacy.frames)
		var initial_hash := Movie.digest(legacy.header.initial)
		var checkpoints_hash := Movie.digest(legacy.hashes)
		check(not view.replay.validate_movie(legacy).ok,"production build guard still refuses old-build movie")
		# Test-only build rebinding; frames, expected hashes and initial state are immutable.
		legacy.header.build_hash = view.replay.build_hash()
		check(view.replay.validate_movie(legacy).ok,"legacy full profile and initial state remain accepted")
		await replay_twice(legacy,"pre-FEEL2 legacy")
		check(Movie.digest(legacy.frames) == frames_hash and Movie.digest(legacy.hashes) == checkpoints_hash and Movie.digest(legacy.header.initial) == initial_hash,"legacy frames/checkpoints/initial state were not rewritten")
		check(FileAccess.get_sha256(legacy_path) == file_hash,"legacy source file unchanged")
	for mode in ["hold","toggle","auto"]:
		check(view.actions.configure({"version":1,"options":{"run_mode":mode}}).ok,"configure new movie "+mode)
		view.actions.set_source("bot")
		check(view.replay.restore_state(initial).ok,"restore clean fixture for "+mode)
		view.set_physics_process(true); view.player.set_physics_process(true)
		for i in 5: await frame()
		if mode == "toggle": await frame(["run"]); await frame()
		var path := output.path_join("run-"+mode+".h64movie.json")
		check(view.replay.start_record(path,7).ok,"record new "+mode+" movie")
		for t in 180:
			var digital := ["move_right"] if t<60 else (["move_up"] if t<120 else ["move_left"])
			if t<30 or t==135: digital.append("run")
			if t>=80 and t<100: digital.append("walk")
			await frame(digital)
		check(view.replay.stop_record().ok,"finish new "+mode+" movie")
		var movie: Dictionary = Wire.read_json(path)
		check(movie.header.profile.bindings.has("run") and movie.frames.any(func(f): return "run" in f.digital),mode+" records appended run action without renaming precision")
		check(movie.header.initial.actions.get("run_toggle") is bool,mode+" run latch is serialized")
		if mode == "toggle": check(movie.header.initial.actions.run_toggle,"toggle movie starts with active latch")
		check(view.replay.validate_movie(movie).ok,mode+" new movie validates strictly")
		await replay_twice(movie,"new "+mode)
	print("CONTROLS RUN MOVIE ",JSON.stringify({"checks":checks,"failures":failures,"cases":receipts}))
	await view.quit_cleanly(0 if failures.is_empty() else 1)
