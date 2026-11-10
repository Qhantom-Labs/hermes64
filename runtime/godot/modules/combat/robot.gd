extends "res://modules/combat/enemy.gd"
## Robot enemy templates and the data-only boss (COMBAT lane, gameplay API 1.1.0). One fixed-tick FSM over the same
## seven states and clip names as the melee templates (idle, approach, telegraph, attack, recover, hurt, dead); the
## template and its data choose the behaviour:
##   walker_patrol_v1  patrols, spots the player (a short pause), approaches, telegraphs a short bump lunge, recovers
##   brute_slam_v1     slow approach, overhead slam on the spot latched at the telegraph (landing disc) that sends a
##                     ground shockwave ring; armoured (hits glance off) except while it recovers
##   hover_drone_v1    keeps its distance and strafes, then aims and fires a slow projectile (dodge or deflect it)
##   boss_phases_v1    health phases; each phase cycles its list of patterns (bump, slam, shot, and the signature
##                     surge: a dash lane ending in a shockwave); armoured except while it recovers
## Gameplay never reads a clip clock; every transition is a function of the saved FSM fields below.
const Hazards = preload("res://modules/combat/hazards.gd")
const Telegraph = preload("res://modules/combat/telegraph.gd")
const ROBOTS := ["walker_patrol_v1", "brute_slam_v1", "hover_drone_v1", "boss_phases_v1"]
const KNOCK_TICKS := 6
const SURGE_WAVE_MPS := 6.0
const WAVE_WIDTH := 0.6
var combat_ref: WeakRef
var template := ""
var robot := {}
var kind := ""
var phase := 0
var pattern_index := 0
var mode := "patrol"
var mode_age := 0
var knock := Vector3.ZERO
var knock_ticks := 0
var strafe_sign := 1.0
var patrol_sign := 1.0
var impact := Vector3.ZERO
var lane := Vector3(0, 0, 1)
var lane_from := Vector3.ZERO
## Set by damage() when a boss crosses into its next phase; consumed by combat/runtime.gd in the same tick.
var phase_changed := false

static func is_robot_row(row: Dictionary) -> bool:
	return str(row.get("fsm", {}).get("template", "")) in ROBOTS

func configure(row: Dictionary, spawn: Dictionary, world: Node3D) -> void:
	super.configure(row, spawn, world)
	template = str(data.fsm.template)
	robot = data.get("robot", {})
	var shape: CollisionShape3D = body.get_child(0)
	var capsule: CapsuleShape3D = shape.shape
	if template == "brute_slam_v1":
		capsule.radius = 0.42; capsule.height = 1.9; shape.position.y = 0.95
	elif template == "boss_phases_v1":
		capsule.radius = 0.55; capsule.height = 2.3; shape.position.y = 1.15
	mode = "patrol" if template == "walker_patrol_v1" else ""
	kind = attack_kind()

func is_boss() -> bool:
	return template == "boss_phases_v1"

func attack_kind() -> String:
	match template:
		"walker_patrol_v1": return "bump"
		"brute_slam_v1": return "slam"
		"hover_drone_v1": return "shot"
	var p := pattern()
	return str(p.get("kind", ""))

func phase_patterns() -> Array:
	if not is_boss(): return []
	return data.boss.phases[phase].patterns

## The boss pattern in play ({} for robots or a phase without patterns).
func pattern() -> Dictionary:
	var ids := phase_patterns()
	if ids.is_empty(): return {}
	var pid: String = ids[pattern_index % ids.size()]
	for p in data.boss.patterns:
		if p.id == pid: return p
	return {}

## Timing of the attack in play: {windup_ticks, active_ticks, recovery_ticks, damage}.
func current_attack() -> Dictionary:
	if is_boss():
		var p := pattern()
		return p if not p.is_empty() else {"windup_ticks": 1, "active_ticks": 1, "recovery_ticks": 1, "damage": 1}
	return data.attack

## Clip pacing for clip_phases.enemy_pose (the attack in play and this robot's stagger length).
func pose_data() -> Dictionary:
	return {"attack": current_attack(), "hurt_ticks": int(robot.get("hurt_ticks", HURT_TICKS))}

func armored() -> bool:
	return str(robot.get("armor", "none")) == "until_recover" and state != "recover" and state != "dead"

## Robots decide contact geometrically in tick(); the runtime only adds line of sight and i-frames.
func in_contact(_distance: float) -> bool:
	return true

func phase_marks() -> Array:
	var out := []
	if is_boss():
		for i in range(1, data.boss.phases.size()): out.append(float(data.boss.phases[i].health_permille) / 1000.0)
	return out

func face(p: Vector3) -> void:
	var d := p - body.position
	d.y = 0.0
	if d.length() > 0.01: body.rotation.y = atan2(-d.x, -d.z)

func forward() -> Vector3:
	return Vector3(-sin(body.rotation.y), 0.0, -cos(body.rotation.y))

func flat(a: Vector3, b: Vector3) -> float:
	return Vector2(a.x - b.x, a.z - b.z).length()

func damage(amount: int, from: Vector3) -> void:
	if hp <= 0: return
	hp = maxi(0, hp - amount)
	var away := body.position - from
	away.y = 0.0
	var k := float(robot.get("knockback_m", 0.0))
	knock = away.normalized() * k / float(KNOCK_TICKS) if away.length() > 0.001 and k > 0.0 else Vector3.ZERO
	knock_ticks = KNOCK_TICKS if knock != Vector3.ZERO else 0
	if hp == 0:
		transition("dead")
		return
	if is_boss() and check_phase(): return
	if str(robot.get("armor", "none")) == "until_recover": return
	transition("hurt")

## Boss: advance through every phase threshold crossed (health <= health_permille / 1000 of max); a new phase
## restarts its pattern list from the top after a reset to approach.
func check_phase() -> bool:
	var phases: Array = data.boss.phases
	var changed := false
	while phase + 1 < phases.size() and hp * 1000 <= int(phases[phase + 1].health_permille) * int(data.max_health):
		phase += 1
		pattern_index = 0
		changed = true
	if changed:
		phase_changed = true
		kind = attack_kind()
		transition("approach")
	return changed

func tick(target: Vector3) -> bool:
	if state == "dead": return false
	if knock_ticks > 0:
		body.move_and_collide(knock)
		knock_ticks -= 1
		if knock_ticks == 0: knock = Vector3.ZERO
	return step(target)

func step(target: Vector3) -> bool:
	var distance := body.position.distance_to(target)
	var a := current_attack()
	var contact := false
	match state:
		"idle": idle(target, distance)
		"approach": approach(target, distance)
		"telegraph":
			face(latched)
			if age >= int(a.windup_ticks):
				transition("attack")
				return step(target)
		"attack":
			if age >= int(a.active_ticks): transition("recover")
			else: contact = attack_step(target)
		"recover":
			if age >= int(a.recovery_ticks):
				end_cycle()
				transition("approach")
		"hurt":
			if age >= int(robot.get("hurt_ticks", HURT_TICKS)): transition("approach")
	age += 1
	return contact

func idle(target: Vector3, distance: float) -> void:
	if template == "walker_patrol_v1":
		if mode == "patrol":
			var span := float(data.walker.patrol_m)
			if span > 0.0:
				var goal := Vector3(home.x + patrol_sign * span, body.position.y, home.z)
				move_toward_point(goal, float(data.speed_mps) * 0.6)
				if flat(body.position, goal) < 0.05: patrol_sign = -patrol_sign
			if distance <= float(data.aggro_range_m):
				mode = "spot"
				mode_age = 0
				face(target)
		elif mode == "spot":
			face(target)
			mode_age += 1
			if mode_age >= int(data.walker.spot_ticks):
				mode = ""
				mode_age = 0
				transition("approach")
		elif distance <= float(data.aggro_range_m):
			transition("approach")
		return
	if distance <= float(data.aggro_range_m):
		mode_age = 0
		transition("approach")

func approach(target: Vector3, distance: float) -> void:
	if body.position.distance_to(home) > float(data.leash_range_m):
		move_toward_point(home, float(data.speed_mps))
		if body.position.distance_to(home) < 0.2:
			mode = "patrol" if template == "walker_patrol_v1" else ""
			transition("idle")
		return
	match template:
		"walker_patrol_v1":
			var reach := float(data.attack_range_m) + float(data.walker.bump_speed_mps) * float(data.attack.active_ticks) / 60.0 * 0.8
			if distance <= reach: start_attack(target)
			else: move_toward_point(target, float(data.speed_mps))
		"brute_slam_v1":
			if distance <= float(data.attack_range_m): start_attack(target)
			else: move_toward_point(target, float(data.speed_mps))
		"hover_drone_v1":
			hover_move(target, distance)
			mode_age += 1
			if mode_age >= int(data.hover.strafe_ticks) and distance <= float(data.aggro_range_m): start_attack(target)
		"boss_phases_v1":
			var p := pattern()
			if p.is_empty():
				move_toward_point(target, float(data.speed_mps))
				return
			var engage := float(data.attack_range_m)
			if p.kind == "shot": engage = float(data.aggro_range_m)
			elif p.kind == "surge": engage = float(data.attack_range_m) * 3.0
			elif p.kind == "bump": engage = float(data.attack_range_m) + float(p.speed_mps) * float(p.active_ticks) / 60.0 * 0.8
			if distance <= engage: start_attack(target)
			else: move_toward_point(target, float(data.speed_mps))

## Drone: back off inside keep_distance, close in beyond it, otherwise strafe around the player; always facing it.
func hover_move(target: Vector3, distance: float) -> void:
	var keep := float(data.hover.keep_distance_m)
	var to := target - body.position
	to.y = 0.0
	var dir := to.normalized() if to.length() > 0.01 else Vector3(0, 0, -1)
	if distance < keep - 0.4: body.move_and_collide(-dir * float(data.speed_mps) / 60.0)
	elif distance > keep + 0.4: body.move_and_collide(dir * float(data.speed_mps) / 60.0)
	else: body.move_and_collide(Vector3(-dir.z, 0.0, dir.x) * strafe_sign * float(data.hover.strafe_mps) / 60.0)
	face(target)

func start_attack(target: Vector3) -> void:
	var combat = combat_ref.get_ref() if combat_ref != null else null
	if combat != null and not combat.request_attack(self): return
	latched = target
	attack_id += 1
	hit = false
	kind = attack_kind()
	lane_from = body.position
	var to := target - body.position
	to.y = 0.0
	lane = to.normalized() if to.length() > 0.01 else forward()
	if kind == "slam": impact = body.position + lane * minf(to.length(), float(data.attack_range_m))
	face(target)
	transition("telegraph")

func slam_radius() -> float:
	return float(data.brute.slam_radius_m) if template == "brute_slam_v1" else maxf(0.6, float(pattern().get("size_m", 1.5)) * 0.4)

func bump_reach() -> float:
	return float(data.attack_range_m) if template == "walker_patrol_v1" else float(pattern().get("size_m", 1.0))

func bump_speed() -> float:
	return float(data.walker.bump_speed_mps) if template == "walker_patrol_v1" else float(pattern().get("speed_mps", 4.0))

## One attack tick (age 0 is the first). Returns true when this tick's melee contact can land.
func attack_step(target: Vector3) -> bool:
	var a := current_attack()
	var combat = combat_ref.get_ref() if combat_ref != null else null
	match kind:
		"bump":
			body.move_and_collide(lane * bump_speed() / 60.0)
			return not hit and body.position.distance_to(target) <= bump_reach()
		"slam":
			if age == 0:
				if combat != null:
					if template == "brute_slam_v1":
						combat.spawn_ring(self, impact, float(data.brute.wave_speed_mps), float(data.brute.wave_max_m), float(data.brute.wave_width_m), int(a.damage))
					else:
						combat.spawn_ring(self, impact, float(a.speed_mps), float(a.size_m), WAVE_WIDTH, int(a.damage))
				return not hit and flat(impact, target) <= slam_radius()
		"shot":
			if age == 0 and combat != null:
				if template == "hover_drone_v1":
					var s: Dictionary = data.hover.shot
					combat.spawn_shot(self, lane, float(s.speed_mps), float(s.radius_m), int(a.damage), int(s.lifetime_ticks), bool(s.deflectable), float(data.hover.hover_m))
				else:
					var n := int(a.get("count", 1))
					for i in n:
						var turn := deg_to_rad(18.0) * (float(i) - float(n - 1) * 0.5)
						combat.spawn_shot(self, lane.rotated(Vector3.UP, turn), float(a.speed_mps), float(a.size_m), int(a.damage), 240, bool(a.get("deflectable", false)), 0.6)
		"surge":
			if age < int(a.active_ticks) - 1:
				body.move_and_collide(lane * float(a.speed_mps) / 60.0)
				return not hit and body.position.distance_to(target) <= 1.0
			if combat != null:
				combat.spawn_ring(self, body.position, SURGE_WAVE_MPS, float(a.size_m), WAVE_WIDTH, int(a.damage))
	return false

func end_cycle() -> void:
	if is_boss():
		pattern_index += 1
	elif template == "hover_drone_v1":
		strafe_sign = -strafe_sign
	mode_age = 0
	kind = attack_kind()

## Floor telegraph for this robot (see combat/telegraph.gd for the marker fields). attack_in counts ticks to the
## attack's first tick (the pre-attack flash); contact_in to its first damaging tick.
func telegraph_info(danger_ticks := 10) -> Dictionary:
	if hp <= 0: return {}
	var a := current_attack()
	var w := int(a.windup_ticks)
	var act := int(a.active_ticks)
	var out := {}
	if state == "telegraph":
		out = {"progress": clampf(float(age) / float(maxi(w, 1)), 0.0, 1.0), "contact_in": maxi(0, w - age), "attack_in": maxi(0, w - age)}
	elif state == "attack" and (kind == "bump" or kind == "surge"):
		out = {"progress": 1.0, "contact_in": 0 if not hit and age < act else -1, "attack_in": -1}
	else:
		return {}
	match kind:
		"bump":
			out.merge({"shape": "lane", "origin": lane_from, "dir": lane, "length": bump_speed() * float(act) / 60.0 + bump_reach(), "width": bump_reach() * 1.4})
		"slam":
			out.merge({"shape": "disc", "origin": impact, "radius": slam_radius(), "from": lane_from, "reach": float(data.brute.wave_max_m) if template == "brute_slam_v1" else float(a.size_m)})
			act = 1
		"shot":
			var speed := float(data.hover.shot.speed_mps) if template == "hover_drone_v1" else float(a.speed_mps)
			var radius := float(data.hover.shot.radius_m) if template == "hover_drone_v1" else float(a.size_m)
			var travel := ceili(flat(lane_from, latched) / maxf(speed / 60.0, 0.0001))
			out.contact_in = int(out.contact_in) + travel
			out.merge({"shape": "lane", "origin": lane_from, "dir": lane, "length": minf(speed * 4.0, 8.0), "width": radius * 2.0})
			act = 9999
		"surge":
			var run := float(a.speed_mps) * float(act) / 60.0
			out.merge({"shape": "lane", "origin": lane_from, "dir": lane, "length": run + 1.0, "width": 2.0, "reach": float(a.size_m), "reach_at": lane_from + lane * run})
	out.danger = int(out.contact_in) >= 0 and int(out.contact_in) <= danger_ticks
	out.open = state == "telegraph" and kind != "shot" and Telegraph.dodge_open(int(out.contact_in), act)
	return out

## Telegraph cue: the robot's own catalog id, else the boss pattern's ('' = the readability profile default).
func telegraph_cue() -> String:
	if is_boss() and str(pattern().get("cue", "")) != "": return str(pattern().cue)
	return str(robot.get("cue", ""))

func snapshot() -> Dictionary:
	var s := super.snapshot()
	s.merge(capture_extra())
	return s

const EXTRA := ["kind", "phase", "pattern_index", "mode", "mode_age", "knock_ticks", "strafe_sign", "patrol_sign"]
func capture_extra() -> Dictionary:
	var out := {}
	for key in EXTRA: out[key] = get(key)
	for key in ["knock", "impact", "lane", "lane_from", "latched"]:
		var v: Vector3 = get(key)
		out[key] = [v.x, v.y, v.z]
	return out

func restore_extra(d: Dictionary) -> void:
	for key in EXTRA: set(key, d[key])
	for key in ["knock", "impact", "lane", "lane_from", "latched"]:
		set(key, Vector3(d[key][0], d[key][1], d[key][2]))
