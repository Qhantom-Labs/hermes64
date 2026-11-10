extends RefCounted
## Dev pacing is an integer tick gate, never Engine.time_scale or variable delta.
var enabled := false
var permitted := false
var paused := false
var settings_open := false
var slow := false
var input_overlay := false
var perf_overlay := false
var phase := 0
var sim_tick := 0
var checkpoint_ticks := 0
var pause_selection := 0

func configure(options: Dictionary) -> void:
	enabled = str(options.get("dev","0")) in ["1","true"] or ProjectSettings.get_setting("hermes64/dev_enabled",false)
	permitted = enabled or OS.has_feature("editor")

func advance(actions) -> bool:
	if permitted and actions.just_pressed("dev_toggle"): enabled = not enabled
	if actions.just_pressed("menu"):
		settings_open = not settings_open
		paused = settings_open
	var step := false
	if enabled:
		if actions.just_pressed("dev_pause"):
			paused = not paused
			settings_open = false
		if actions.just_pressed("dev_input"): input_overlay = not input_overlay
		if actions.just_pressed("dev_perf"): perf_overlay = not perf_overlay
		if actions.just_pressed("dev_slow"): slow = not slow
		step = paused and actions.just_pressed("dev_step")
	phase += 1
	var simulate := step or (not paused and (not slow or not enabled or phase % 4 == 0))
	if simulate:
		sim_tick += 1
		checkpoint_ticks = maxi(0,checkpoint_ticks-1)
	return simulate
