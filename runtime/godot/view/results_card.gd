extends RefCounted
## SCENES lane: results card model + drawing. Digits only: title, TIME, DEATHS,
## PENALTY (only when the game has a death penalty), BEST, the run code and two
## choices. No explanation text. Data in, draw calls out; no game state access.
const PixelFont = preload("res://look/pixel_font.gd")
const Pack = preload("res://look/pack.gd")
const RunSource = preload("res://view/run_source.gd")
const CHOICES := ["again", "save"]
var title := ""
var run := {}
var best := -1
var new_best := false
var code := ""
var choice := 0
var saved := false
var labels := {"time":"TIME","deaths":"DEATHS","penalty":"PENALTY","best":"BEST","code":"RUN","again":"AGAIN","save":"SAVE REPLAY","saved":"SAVED"}

func configure(card_title: String, run_state: Dictionary, best_ticks: int, is_new_best: bool, run_code: String, overrides: Dictionary = {}) -> void:
	title = card_title; run = run_state.duplicate(true); best = best_ticks; new_best = is_new_best; code = run_code
	for k in overrides:
		if labels.has(k) and overrides[k] is String and str(overrides[k]).length() <= 16: labels[k] = overrides[k]
	choice = 0; saved = false

## Plain rows (also the test/browser receipt). The penalty is already inside TIME.
func rows() -> Array:
	var out := [[labels.time, RunSource.clock(int(run.get("ticks", 0)))], [labels.deaths, str(int(run.get("deaths", 0)))]]
	if int(run.get("penalty_rule", 0)) > 0: out.append([labels.penalty, "+" + RunSource.seconds(int(run.get("penalty_ticks", 0)))])
	out.append([labels.best, RunSource.clock(best) if best >= 0 else "--:--.--"])
	if code != "": out.append([labels.code, code])
	return out

func choice_labels() -> Array:
	return [labels.again, labels.saved if saved else labels.save]

func move(step: int) -> void:
	choice = posmod(choice + step, CHOICES.size())

func selected() -> String:
	return CHOICES[choice]

func draw(ci: CanvasItem, width: int, alpha: float) -> void:
	var font = PixelFont.get_font()
	var ink := Pack.ui("ink", "#0b0d12")
	var text := Pack.ui("text", "#e8e0cc")
	var accent := Pack.ui("accent", "#f0c060")
	ci.draw_rect(Rect2(0, 0, width, 240), Color(0, 0, 0, 0.8 * alpha))
	var shadow := Color(ink, 0.8 * alpha)
	var y := 52
	if title != "":
		var tw: int = font.measure(title) * 2
		ci.draw_set_transform(Vector2(roundf((width - tw) / 2.0), y), 0.0, Vector2(2, 2))
		font.draw(ci, Vector2.ZERO, title, Color(text, alpha), shadow)
		ci.draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)
		y += 32
	var box := 150
	var left := roundf((width - box) / 2.0)
	for row in rows():
		var colour := text
		if row[0] == labels.best and new_best: colour = accent
		font.draw(ci, Vector2(left, y), row[0], Color(text, alpha), shadow)
		font.draw(ci, Vector2(left + box - font.measure(row[1]), y), row[1], Color(colour, alpha), shadow)
		y += 13
	y += 12
	var names := choice_labels()
	var gap := 18
	var total: int = font.measure(names[0]) + font.measure(names[1]) + gap
	var x := roundf((width - total) / 2.0)
	for i in names.size():
		var on := i == choice
		var w: int = font.measure(names[i])
		if on: ci.draw_rect(Rect2(x - 3, y - 2, w + 6, 13), Color(accent, 0.28 * alpha))
		font.draw(ci, Vector2(x, y), names[i], Color(accent if on else text, alpha), shadow)
		x += w + gap
