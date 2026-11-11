extends RefCounted
## Module-aware combat bot for gameplay API 1.1.0 encounters (robots, projectiles, shockwaves, boss). It reads only
## what the player can see (the telegraph language of modules/combat/telegraph.gd: floor decals, the "safe to dodge
## now" window, projectile paths, shockwave rings, the brute/boss vulnerable recovery) and answers through the real
## Actions layer: hold Focus, walk out of a decal, roll through a ring or a shot on its i-frames, deflect a deflectable
## shot with a timed swing, and swing only while the target can be hurt. It never injects outcomes or state.
## Melee-only (1.0.0) encounters keep the original bot path in module_runner.gd, so their inputs are unchanged.
const Telegraph = preload("res://modules/combat/telegraph.gd")
const Robot = preload("res://modules/combat/robot.gd")   # FEEL4: ring width of non-brute slams
const REACH := 1.65
const BODY := 0.35

static func flat(v: Vector3) -> Vector2:
	return Vector2(v.x, v.z)

static func inside(t: Dictionary, p: Vector3) -> bool:
	match str(t.get("shape", "")):
		"disc":
			return flat(p).distance_to(flat(t.origin)) <= float(t.radius) + BODY
		"lane":
			var d := flat(t.dir).normalized()
			var rel := flat(p) - flat(t.origin)
			var along := rel.dot(d)
			return along >= -BODY and along <= float(t.length) + BODY and absf(rel.cross(d)) <= float(t.width) * 0.5 + BODY
	return false

## A point just outside the decal, on the player's side of it.
static func exit_point(t: Dictionary, p: Vector3) -> Vector3:
	if str(t.get("shape", "")) == "disc":
		var away := p - Vector3(t.origin)
		away.y = 0.0
		# A landing disc in front of its attacker: leave sideways (perpendicular to attacker -> disc), staying close
		# enough to strike in the recovery that follows.
		if t.has("from"):
			var axis := Vector3(t.origin) - Vector3(t["from"])
			axis.y = 0.0
			if axis.length() > 0.05:
				var perp := Vector3(-axis.z, 0.0, axis.x).normalized()
				away = perp * (1.0 if away.dot(perp) >= 0.0 else -1.0)
		if away.length() < 0.05: away = Vector3(1, 0, 0)
		return Vector3(t.origin) + away.normalized() * (float(t.radius) + 0.7)
	var d: Vector3 = t.dir
	var n := Vector3(-d.z, 0.0, d.x).normalized()
	var side := 1.0 if (p - Vector3(t.origin)).dot(n) >= 0.0 else -1.0
	return p + n * side * (float(t.width) * 0.5 + 1.2)

static func free_to_act(combat) -> bool:
	return combat.age < 0 and combat.roll_age < 0 and combat.hurt_age < 0 and combat.hitstop == 0

## FEEL4: a roll is vulnerable after its i-frames (roll ticks 15..23) and cannot be cancelled. Rolling out of a brute's
## landing disc let the ring that the same slam emits catch the body just as the i-frames ended (measured: both hits
## of a lost club wave). Predict the roll (the same 8 camera-relative inputs runner.gd steer() picks from, 4 m/s for
## ROLL_MOVE ticks) against every live ring, the ring each telegraphed slam will emit, every telegraphed decal whose
## first damaging tick falls in that tail, and the room boundary. Keep the original direction unless it is hit, else
## take the safe direction nearest to it. Nothing safe: null, and the caller waits (a later roll toward the slam centre
## clears slam and ring with one set of i-frames) until the last moment (contact <= LAST_CHANCE), then rolls as before.
## Reads only visible telegraph state.
const LAST_CHANCE := 1
static func safe_roll_aim(view, combat, toward: Vector3) -> Variant:
	var p: Vector3 = view.player.position
	var want := flat(toward - p)
	if want.length() < 0.01: return toward
	var player = view.player
	var basis: Basis = player.latched_basis if player.latched else player.camera_basis
	var options := []
	for x in [-1, 0, 1]:
		for y in [-1, 0, 1]:
			if x == 0 and y == 0: continue
			var input := Vector2(x, y)
			var b: Basis = basis
			if player.latched and absf(input.angle_to(player.last_input)) > 0.6: b = player.camera_basis
			var d := Vector3(b.x.x, 0.0, b.x.z) * float(x) + Vector3(b.z.x, 0.0, b.z.z) * float(y)
			if d.length() < 0.01: continue
			d = d.normalized()
			options.append([flat(d).dot(want.normalized()), d])
	options.sort_custom(func(a, b): return a[0] > b[0])
	for o in options:
		if roll_is_safe(view, combat, p, o[1]): return p + o[1] * 3.0
	return null

const TAIL := [14, 27]   # roll ticks checked: the vulnerable tail (15..23) with a tick of margin either side
const BODY_R := 0.35

static func roll_point(p: Vector3, dir: Vector3, k: int) -> Vector3:
	return p + dir * (4.0 / 60.0) * float(mini(k + 1, 18))

static func band_touch(d: float, r: float, width: float, reach: float) -> bool:
	return r - width * 0.5 <= reach and d + BODY_R >= r - width * 0.5 and d - BODY_R <= r + width * 0.5 and d - BODY_R <= reach

## Rings: live ones [origin, radius now, speed/tick, width, reach, 0], and the ring each telegraphed slam emits on its
## first attack tick (contact_in + 1 ticks from now) [origin, 0, speed, width, reach, contact_in + 1].
static func rings(combat) -> Array:
	var out := []
	for w in combat.shockwaves:
		if not w.hit: out.append([w.origin, w.radius, w.speed, w.width, w.max_radius, 0])
	for e in combat.enemies:
		if e.hp <= 0 or str(e.get("state")) != "telegraph" or str(e.get("kind")) != "slam" or not e.has_method("current_attack"): continue
		var t: Dictionary = Telegraph.info(e)
		if not t.has("origin") or int(t.get("contact_in", -1)) < 0: continue
		var a: Dictionary = e.current_attack()
		if str(e.get("template")) == "brute_slam_v1":
			out.append([t.origin, 0.0, float(e.data.brute.wave_speed_mps) / 60.0, float(e.data.brute.wave_width_m), float(e.data.brute.wave_max_m), int(t.contact_in) + 1])
		else:
			out.append([t.origin, 0.0, float(a.get("speed_mps", 0.0)) / 60.0, Robot.WAVE_WIDTH, float(a.get("size_m", 0.0)), int(t.contact_in) + 1])
	return out

static func roll_is_safe(view, combat, p: Vector3, dir: Vector3) -> bool:
	var outline: PackedVector2Array = view.room_root.boundary_outline if view.room_root != null and view.room_root.get("boundary_outline") != null else PackedVector2Array()
	if outline.size() >= 3 and not Geometry2D.is_point_in_polygon(flat(roll_point(p, dir, 17)), outline): return false
	var waves := rings(combat)
	for k in range(TAIL[0], TAIL[1] + 1):
		var at := roll_point(p, dir, k)
		for w in waves:
			var ticks := k + 1 - int(w[5])   # ticks this ring has grown by roll tick k (live rings: k + 1)
			if ticks < 1: continue
			if band_touch(flat(at).distance_to(flat(w[0])), float(w[1]) + float(w[2]) * ticks, float(w[3]), float(w[4])): return false
	# Decals whose first damaging tick (contact_in + 1 ticks from now = roll tick contact_in) lands in the tail.
	for e in combat.enemies:
		if e.hp <= 0: continue
		var t: Dictionary = Telegraph.info(e)
		var c := int(t.get("contact_in", -1))
		if t.has("shape") and c >= TAIL[0] and c <= TAIL[1] and inside(t, roll_point(p, dir, c)): return false
	return true

## {aim: world point or null, buttons: [...]} for this tick. Focus (a slower, locked strafe) is held only near the
## target or to face an incoming deflectable shot; escapes and chases run at full speed without it.
static func decide(view, combat) -> Dictionary:
	var p: Vector3 = view.player.position
	var ready := free_to_act(combat)
	var target = combat.find_target(combat.target)
	if target == null:
		var best := INF
		for e in combat.enemies:
			var d: float = e.body.position.distance_to(p)
			if e.hp > 0 and d < best: target = e; best = d
	# 1. Shockwave rings: roll through the band toward its centre when the i-frames cover the pass.
	var waiting := false   # FEEL4: a roll was due but none is safe yet; stay ready (no swing) and re-check next tick
	for w in combat.shockwaves:
		if w.glyph_open(p) and w.contact_in(p) <= 3 and ready:
			var aim1 = safe_roll_aim(view, combat, w.origin)
			if aim1 != null or w.contact_in(p) <= LAST_CHANCE: return {"aim": aim1 if aim1 != null else w.origin, "buttons": ["dodge"]}
			waiting = true
	# 2. Shots: deflect a deflectable one from the locked target; otherwise sidestep, rolling at the last moment.
	for s in combat.projectiles:
		if s.reflected: continue
		var c: int = s.contact_in(p)
		if c < 0: continue
		var n := Vector3(-s.velocity.z, 0.0, s.velocity.x).normalized()
		if (p - s.position).dot(n) < 0.0: n = -n
		var toward := Vector3(s.position.x - p.x, 0.0, s.position.z - p.z).normalized()
		var facing: bool = target != null and s.owner == target.identity and toward.dot(combat.forward()) >= 0.3
		if s.deflectable and facing:
			if ready and c >= 10 and c <= 16: return {"aim": null, "buttons": ["focus", "primary"]}
			if c > 16: return {"aim": null, "buttons": ["focus"]}
		if c <= 5 and ready and c + s.pass_ticks() <= 15:
			var aim2 = safe_roll_aim(view, combat, p + n * 2.0)
			if aim2 != null or c <= LAST_CHANCE: return {"aim": aim2 if aim2 != null else p + n * 2.0, "buttons": ["dodge"]}
		if c <= 40: return {"aim": p + n * 2.0, "buttons": []}
	# 3. Floor decals (lanes, landing discs): run out while there is time, roll out when the window is open.
	for enemy in combat.enemies:
		if enemy.hp <= 0: continue
		var t: Dictionary = Telegraph.info(enemy)
		if combat.brawler() and enemy.get("template") == "boss_phases_v1" and enemy.get("kind") == "slam" and t.get("shape", "") == "disc":
			t = t.duplicate()
			# The visible landing disc also emits a ring. Do not voluntarily
			# chase back through that ring's future radius during its windup.
			t.radius = maxf(float(t.radius), float(enemy.data.brute.wave_max_m) if enemy.template == "brute_slam_v1" else float(enemy.pattern().size_m))
		if t.is_empty() or not t.has("shape") or int(t.get("contact_in", -1)) < 0 or not inside(t, p): continue
		var out := exit_point(t, p)
		if int(t.contact_in) <= 7 and t.get("open", false) and ready:
			var aim3 = safe_roll_aim(view, combat, out)
			if aim3 != null or int(t.contact_in) <= LAST_CHANCE: return {"aim": aim3 if aim3 != null else out, "buttons": ["dodge"]}
		return {"aim": out, "buttons": []}
	# 4. Offense: armoured targets are only struck while they recover (bait their attack, then wait clear of it).
	if target == null or waiting: return {"aim": null, "buttons": []}
	var distance: float = target.body.position.distance_to(p)
	var near := ["focus"] if distance <= REACH + 0.25 else []
	if combat.brawler():
		# New profile only: charge breaks armour, chain presses queue in recovery.
		# Legacy movies retain the original decisions below.
		if target.has_method("armored") and target.armored() and distance <= REACH + 0.25:
			if combat.primary_held and combat.hold_ticks < 24: return {"aim":null,"buttons":["focus","primary"]}
			if combat.primary_held: return {"aim":null,"buttons":["focus"]}
			if ready: return {"aim":null,"buttons":["focus","primary"]}
		if distance > 2.0 and distance < 3.6 and ready:
			return {"aim":target.body.position,"buttons":["run","primary"] if view.player.actual_velocity.length() > 2.0 else ["run"]}
		if combat.age >= 0 and combat.move_kind in ["jab","cross"] and combat.chain_next == "" and not combat.primary_held:
			var f: Array = combat.frame_data()
			if combat.age >= int(f[0]) + int(f[1]): return {"aim":null,"buttons":["focus","primary"]}
	if target.has_method("armored") and target.armored():
		if target.state in ["idle", "approach"]:
			if distance > float(target.data.attack_range_m) * 0.85: return {"aim": target.body.position, "buttons": near}
			return {"aim": null, "buttons": ["focus"]}
		# Mid-attack with its decal elsewhere: hold here, facing it (the ring is rolled through toward it, which
		# lands the player close for the recovery).
		return {"aim": null, "buttons": ["focus"] if distance <= 6.0 else []}
	var aim = target.body.position if distance > 1.3 else null
	var buttons: Array = near
	if distance <= REACH and ready: buttons = ["focus", "primary"]
	return {"aim": aim, "buttons": buttons}
