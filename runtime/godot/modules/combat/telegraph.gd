extends RefCounted
## Telegraph language (COMBAT lane): pure functions of the fixed-tick combat state, shared by the floor markers,
## the dodge-window glyph, the module bot and the tests. Reading state only; nothing here changes the simulation.
##
## A marker is {shape, origin, dir, length, width, radius, inner, progress, danger, contact_in, open}:
##   shape    "lane" (dash/bump/projectile path), "disc" (reach or landing zone), "ring" (shockwave / sweep band)
##   origin   floor point the shape starts from (world), dir its horizontal direction (lanes)
##   progress windup elapsed 0..1 (the decal fills with it), danger true in the last ticks before the hit
##   contact_in physics ticks until the first tick that can deal damage (0 = the next tick), -1 when none
##   open     the "safe to dodge now" window: a roll pressed on the next tick keeps i-frames over the whole
##            contact window (or, for windows longer than the i-frames, over its start)
const ROLL_IFRAMES := 15

## Dodge window from the ticks before contact and the active (damaging) ticks: open iff a roll pressed on the next
## tick covers the whole contact window with its 15 i-frame ticks (the next tick is tick 1; the first contact tick
## is tick contact_in + 1).
static func dodge_open(contact_in: int, active: int) -> bool:
	if contact_in < 0: return false
	if active > ROLL_IFRAMES: return contact_in <= 2
	return contact_in + active <= ROLL_IFRAMES and contact_in >= 0

## Marker for an enemy this tick (after its tick), or {} when it shows no telegraph.
static func info(enemy, danger_ticks := 10) -> Dictionary:
	if enemy == null or enemy.hp <= 0: return {}
	if enemy.has_method("telegraph_info"): return enemy.telegraph_info(danger_ticks)
	return classic(enemy, danger_ticks)

## melee_approach_v1 / melee_dash_v1 (unchanged simulation): telegraph = windup_ticks, then active_ticks of contact.
## Approach hits anything within attack_range_m (no facing test), so its marker is the reach disc around it.
## Dash charges toward the point latched when the telegraph began at twice its speed, so its marker is that lane.
static func classic(enemy, danger_ticks := 10) -> Dictionary:
	var a: Dictionary = enemy.data.attack
	var w := int(a.windup_ticks)
	var act := int(a.active_ticks)
	var pos: Vector3 = enemy.body.position
	var out := {}
	if enemy.state == "telegraph":
		var age: int = enemy.age
		out = {"progress": clampf(float(age) / float(maxi(w, 1)), 0.0, 1.0), "contact_in": maxi(0, w - age)}
	elif enemy.state == "attack":
		out = {"progress": 1.0, "contact_in": 0 if not enemy.hit and enemy.age < act else -1}
	else:
		return {}
	out.danger = int(out.contact_in) >= 0 and int(out.contact_in) <= danger_ticks
	out.open = enemy.state == "telegraph" and dodge_open(int(out.contact_in), act)
	if str(enemy.data.fsm.template) == "melee_dash_v1":
		var to: Vector3 = enemy.latched - pos
		to.y = 0.0
		var reach: float = float(enemy.data.attack_range_m)
		var run := minf(to.length(), float(enemy.data.speed_mps) * 2.0 * float(act) / 60.0)
		out.merge({"shape": "lane", "origin": pos, "dir": to.normalized() if to.length() > 0.01 else Vector3(0, 0, 1),
			"length": run + reach, "width": 1.0})
	else:
		out.merge({"shape": "disc", "origin": pos, "radius": float(enemy.data.attack_range_m)})
	return out
