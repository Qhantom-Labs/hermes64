extends RefCounted
## Inject a provider, or explicitly inject deterministic test snapshots. No bindings.
const NAMES = ["move", "walk", "primary", "secondary", "focus", "dodge", "menu", "action_menu", "inventory", "quick_save", "quick_load", "reset"]
var provider
var movement := Vector2.ZERO
var held := []
var pressed := []
var suppressed := false
var awaiting_neutral := false
func begin_tick() -> void:
	if provider == null or not awaiting_neutral: return
	if provider.get_move().length() > 0.001: return
	for name in NAMES:
		if provider.is_pressed(name): return
	awaiting_neutral = false
func inject(move: Vector2, buttons: Array) -> void:
	movement = move.limit_length(1.0)
	pressed = []
	for name in buttons:
		if NAMES.has(name) and not held.has(name): pressed.append(name)
	held = buttons.duplicate()
func get_move() -> Vector2:
	if suppressed or awaiting_neutral: return Vector2.ZERO
	return provider.get_move().limit_length(1.0) if provider != null else movement
## Unsmoothed direction (keys: instant, no ramp/tail) for discrete executors such as puzzle grid steps.
func get_raw_move() -> Vector2:
	if suppressed or awaiting_neutral: return Vector2.ZERO
	return provider.get_raw_move().limit_length(1.0) if provider != null else movement
func is_pressed(name: String) -> bool:
	return false if suppressed or awaiting_neutral else (provider.is_pressed(name) if provider != null else held.has(name))
func just_pressed(name: String) -> bool:
	return false if suppressed or awaiting_neutral else (provider.just_pressed(name) if provider != null else pressed.has(name))
func clear() -> void:
	awaiting_neutral = provider != null
	movement = Vector2.ZERO
	held.clear()
	pressed.clear()
func consume() -> void:
	pressed.clear()
