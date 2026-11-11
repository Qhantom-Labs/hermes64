extends Node
## FEEL4 controls hint, drawn by the shared UI5 key overlay (MERGEPREP: one keycap / prompt / hint component; see
## docs/UI5-HUNKS.md). This node draws nothing. For arena_run_v1 / premise games (default ON, as FEEL4 decided; older
## games are unchanged) it turns the UI5 corner hint on and shows FEEL4's two sets as res://input/keyhud.json moments,
## drawn by input/key_overlay.gd with input/keycaps.gd (keycaps from the live input map, icons, no words):
##   arena_start    move, run, camera, interact: after the opening cards, once gameplay has control
##   arena_combat   attack, block, dodge, lock-on: the first time a fight starts (without block when the fight has none)
## Each fades after its seconds or the first use of its `until` action; the pause menu (key_overlay) lists the controls.
## Data: game.metadata.presentation.controls_hint = {"enabled": bool}.
var presenter
var shown_ids := {}
var log := []           # [tick, event] rows (probe evidence)

static func wanted(game: Dictionary) -> bool:
	var meta: Dictionary = game.get("metadata", {})
	var cfg = meta.get("presentation", {}).get("controls_hint", null)
	if cfg is bool: return cfg
	if cfg is Dictionary and cfg.has("enabled"): return bool(cfg.enabled)
	return str(meta.get("template", "")) == "arena_run_v1" or meta.has("premise")

static func install(view) -> Node:
	if not wanted(view.runtime.game): return null
	if view.key_overlay == null: return null
	var hint = new()
	hint.name = "controls_hint"
	hint.presenter = view
	view.viewport.add_child(hint)
	view.key_overlay.hint_mode = "corner"
	return hint

func _ready() -> void:
	process_physics_priority = 61

func gameplay_ready() -> bool:
	var v = presenter
	if v.room_root == null or v.actions == null or v.actions.context != "gameplay": return false
	if v.room_transition != null and v.room_transition.active(): return false
	if v.scene_cards != null and str(v.scene_cards.phase) != "idle": return false
	return v.simulation_enabled

func show_set(id: String) -> void:
	if shown_ids.has(id): return
	shown_ids[id] = true
	if presenter.key_overlay.show_moment(id): log.append([presenter.actions.tick, "show:" + id])

func _physics_process(_delta: float) -> void:
	if presenter == null or presenter.key_overlay == null or not gameplay_ready(): return
	show_set("arena_start")
	var combat = presenter.module_host.combat if presenter.module_host != null else null
	if combat != null and not shown_ids.has("arena_combat"):
		# One combat set: FEEL4's set replaces the overlay's generic challenge moment for this game.
		presenter.key_overlay.hint.shown["challenge_started"] = true
		var with_block := true
		var block_flag = combat.get("block_available")
		if block_flag is bool: with_block = block_flag
		shown_ids["arena_combat"] = true
		var id := "arena_combat" if with_block else "arena_combat_no_block"
		if presenter.key_overlay.show_moment(id): log.append([presenter.actions.tick, "show:" + id])

func report() -> Dictionary:
	var overlay = presenter.key_overlay if presenter != null else null
	return {"drawn_by": "input/key_overlay.gd", "shown": shown_ids.keys(), "log": log,
		"hint_mode": overlay.hint_mode if overlay != null else "", "overlay_hint": overlay.last.get("hint", {}) if overlay != null else {}}
