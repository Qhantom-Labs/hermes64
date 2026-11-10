extends RefCounted
## Module-aware combat bot for gameplay API 1.1.0 encounters (robots, projectiles, shockwaves, boss). It reads only
## what the player can see (the telegraph language of modules/combat/telegraph.gd: floor decals, the "safe to dodge
## now" window, projectile paths, shockwave rings, the brute/boss vulnerable recovery) and answers through the real
## Actions layer: hold Focus, walk out of a decal, roll through a ring or a shot on its i-frames, deflect a deflectable
## shot with a timed swing, and swing only while the target can be hurt. It never injects outcomes or state.
## Melee-only (1.0.0) encounters keep the original bot path in module_runner.gd, so their inputs are unchanged.
const Telegraph = preload("res://modules/combat/telegraph.gd")
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
	for w in combat.shockwaves:
		if w.glyph_open(p) and w.contact_in(p) <= 3 and ready:
			return {"aim": w.origin, "buttons": ["dodge"]}
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
		if c <= 5 and ready and c + s.pass_ticks() <= 15: return {"aim": p + n * 2.0, "buttons": ["dodge"]}
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
		if int(t.contact_in) <= 7 and t.get("open", false) and ready: return {"aim": out, "buttons": ["dodge"]}
		return {"aim": out, "buttons": []}
	# 4. Offense: armoured targets are only struck while they recover (bait their attack, then wait clear of it).
	if target == null: return {"aim": null, "buttons": []}
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
