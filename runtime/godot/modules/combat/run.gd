extends RefCounted
## Pure fixed-tick run authority. No wall time, UI clock, or per-game constants.
var enabled := false
var rules := {}
var ticks := 0
var deaths := 0
var finished_tick := -1
var started := false
var penalty_flash := 0
var checkpoint_flash := 0
func configure(data: Dictionary, active := true) -> void:
	rules = data.duplicate(true); enabled = active
	ticks = 0; deaths = 0; finished_tick = -1; started = false
	penalty_flash = 0; checkpoint_flash = 0
func advance(control: bool, paused := false) -> void:
	if not enabled or paused: return
	penalty_flash = maxi(0, penalty_flash - 1)
	checkpoint_flash = maxi(0, checkpoint_flash - 1)
	if finished_tick >= 0: return
	if control: started = true
	if started: ticks += 1
func died() -> void:
	if not enabled or finished_tick >= 0: return
	deaths += 1
	ticks += int(rules.get("death_penalty_ticks", 0))
	penalty_flash = 105
func checkpoint() -> void:
	if enabled: checkpoint_flash = 90
func finish() -> void:
	if enabled and finished_tick < 0: finished_tick = ticks
func snapshot() -> Dictionary:
	return {"ticks":ticks,"deaths":deaths,"finished_tick":finished_tick,"started":started,"penalty_flash":penalty_flash,"checkpoint_flash":checkpoint_flash}
func restore(data: Dictionary) -> void:
	for key in snapshot(): self.set(key, data[key])
