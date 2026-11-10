extends RefCounted
## All contacts are resolved in stable spawn order; simultaneous KO loses.
## COMBAT lane (gameplay API 1.1.0): robot/boss archetypes (combat/robot.gd), fixed-tick projectiles and shockwaves,
## reward drops, tiny hit-stop, readable push/knockback slides, boss phases. An encounter that uses none of them
## (every 1.0.0 game) runs the exact original code path and hashes the original snapshot.
const Enemy = preload("res://modules/combat/enemy.gd")
const Robot = preload("res://modules/combat/robot.gd")
const Hazards = preload("res://modules/combat/hazards.gd")
const WINDUP := 8
const ACTIVE := 7
const RECOVERY := 15
const REACH := 1.65
const DAMAGE := 1
# Roll: 24 ticks, invulnerable for the first 15, moving for the first 18 (4 m/s). Hurt: 18 ticks.
const ROLL_TICKS := 24
const ROLL_IFRAMES := 15
const ROLL_MOVE := 18
const HURT_TICKS := 18
const ENEMY_HURT_TICKS := Enemy.HURT_TICKS
const PLAYER_RADIUS := 0.3
const PUSH_TICKS := 6
var enemies := []
var encounter := {}
var archetypes := {}
var world: Node3D
var player: CharacterBody3D
var health := 0
var max_health := 0
var age := -1
var roll_age := -1
var hurt_age := -1
var tick_index := 0
var swing_id := 0
var hit_ids := []
var defeated := []
var target := ""
var result := ""
var wave := 0
var damage_taken := 0
var blocks := 0
var rolls := 0
var swings := 0
var block_available := false
var blocking := false
var roll_direction := Vector3.ZERO
var seed_value := 0
var rng := RandomNumberGenerator.new()
var feedback := []
# Presentation only (never hashed or saved): the swing/roll/hurt age each gameplay check used this
# tick, -1 when none. clip_phases maps them to the shown keys, so a hit can only land while the
# swing shows its active keys and i-frames hold exactly while the roll shows its tuck keys.
var shown_swing := -1
var shown_roll := -1
var shown_hurt := -1
# 1.1.0 state (hashed and saved only when `extended`).
var extended := false
var projectiles := []
var shockwaves := []
var drops := []
var next_id := 0
var hitstop := 0
var buffered := ""
var push := Vector3.ZERO
var push_ticks := 0
var deflected := []
# Versioned opt-in. Legacy ticks and snapshot shapes are untouched when absent.
var profile := "legacy"
var moveset := ""
var move_kind := "jab"
var hold_ticks := 0
var primary_held := false
var chain_next := ""
var protection := 0
var protection_ticks := 18
var guard_age := -1
var parry_pose := 0
var staggered := {}
func parry_ready() -> bool:
	return brawler() and blocking and guard_age >= 0 and guard_age <= 8
func parry_attacker(enemy) -> void:
	if enemy.hp > 0:
		enemy.transition("hurt")
		staggered[enemy.identity] = 30
	parry_pose = 3
	feedback.append({"kind":"parry", "id":enemy.identity})
const MOVES = {"jab":[5,5,9,1,0.18], "cross":[5,5,9,1,0.18], "finisher":[8,7,16,1,0.3], "charge":[0,8,20,2,1.0], "running":[4,8,18,1,2.2]}
var attack_busy := false
var attack_release_tick := -1000000
func budget_refresh() -> int:
	var n := 0
	for e in enemies:
		if e.hp > 0 and e.state in ["telegraph","attack"]: n += 1
	if n == 0 and attack_busy: attack_release_tick = tick_index
	attack_busy = n > 0
	return n
var attack_waiting := []
var attack_requests := {}
func request_attack(enemy) -> bool:
	if not modern() or not encounter.has("attack_budget"): return true
	attack_requests[enemy.identity] = tick_index
	attack_waiting = attack_waiting.filter(func(id): return find_target(id) != null and tick_index - int(attack_requests.get(id, -100)) <= 2)
	if not attack_waiting.has(enemy.identity): attack_waiting.append(enemy.identity)
	var n := budget_refresh()
	if n >= int(encounter.attack_budget) or attack_waiting[0] != enemy.identity: return false
	if n == 0 and tick_index - attack_release_tick <= int(encounter.get("attack_gap_ticks", 0)): return false
	attack_waiting.erase(enemy.identity)
	attack_busy = true
	return true
func bosses() -> Array:
	var ids: Array = encounter.get("bosses", [encounter.get("boss", "")])
	var out := []
	for id in ids:
		var e = find_target(id)
		if e != null: out.append(e)
	return out
func modern() -> bool: return profile == "combat2_v1"
func brawler() -> bool: return modern() and moveset == "brawler_v1"
func frame_data() -> Array: return MOVES[move_kind] if brawler() else [WINDUP,ACTIVE,RECOVERY,DAMAGE,0.0]
func attack_window() -> bool:
	var f := frame_data()
	return window(age, f[0], f[1])
func start_move(kind: String) -> void:
	move_kind = kind; age = 0; swing_id += 1; swings += 1; hit_ids = []; chain_next = ""
	feedback.append({"kind":"move", "move":kind})
func moves_input(input) -> void:
	var held: bool = input.is_pressed("primary")
	if held: hold_ticks += 1
	var released := primary_held and not held
	if age >= 0 and input.just_pressed("primary"):
		var f := frame_data()
		if age >= int(f[0]) + int(f[1]):
			chain_next = "cross" if move_kind == "jab" else ("finisher" if move_kind == "cross" else "")
	if age < 0 and roll_age < 0 and hurt_age < 0 and not blocking:
		if released and hold_ticks >= 24: start_move("charge")
		elif pressed(input, "primary"):
			start_move("running" if input.is_pressed("run") and player.actual_velocity.length() > 2.0 else "jab")
	if not held: hold_ticks = 0
	primary_held = held
static func window(t: int, windup: int, active: int) -> bool:
	return t >= windup and t < windup + active
static func iframe(t: int) -> bool:
	return t >= 0 and t < ROLL_IFRAMES
func begin(data: Dictionary, kinds: Dictionary, body: CharacterBody3D, scene: Node3D, hp: int, seed: int) -> void:
	encounter = data.duplicate(true)
	archetypes = kinds
	player = body
	world = scene
	health = hp
	max_health = hp
	seed_value = seed
	rng.seed = seed
	extended = modern() or encounter.has("boss") or encounter.has("gate") or encounter.spawns.any(func(s): return Robot.is_robot_row(archetypes[s.archetype]))
	spawn_wave()
func spawn_wave() -> void:
	var rows: Array = encounter.spawns.duplicate(true)
	rows.sort_custom(func(a,b): return a.id < b.id)
	for row in rows:
		if row.wave != wave: continue
		var data: Dictionary = archetypes[row.archetype]
		var enemy = Robot.new() if Robot.is_robot_row(data) else Enemy.new()
		enemy.configure(data, row, world)
		if modern(): enemy.budget_ref = weakref(self)
		if Robot.is_robot_row(data): enemy.combat_ref = weakref(self)
		enemies.append(enemy)
func los(a: Vector3, b: Vector3) -> bool:
	var query := PhysicsRayQueryParameters3D.create(a + Vector3.UP * 0.7, b + Vector3.UP * 0.7, 1)
	query.exclude = [player.get_rid()]
	return world.get_world_3d().direct_space_state.intersect_ray(query).is_empty()
func find_target(id: String):
	for enemy in enemies:
		if enemy.identity == id and enemy.hp > 0: return enemy
	return null
## The live boss of this encounter (null when none or defeated).
func boss():
	var id: String = encounter.get("boss", "")
	return find_target(id) if id != "" else null
func focus(held: bool) -> void:
	if not held: target = ""; return
	var current = find_target(target)
	if current != null and player.position.distance_to(current.body.position) <= 6.0 and los(player.position, current.body.position): return
	target = ""
	var nearest := 5.0
	for enemy in enemies:
		var distance: float = player.position.distance_to(enemy.body.position)
		if enemy.hp > 0 and distance < nearest and los(player.position, enemy.body.position):
			nearest = distance
			target = enemy.identity
func forward() -> Vector3:
	return Vector3(-sin(player.facing_yaw),0,-cos(player.facing_yaw))
func pose() -> String:
	if health <= 0: return "death"
	if hurt_age >= 0: return "hurt"
	if roll_age >= 0: return "roll"
	if age >= 0: return {"cross":"swing2", "finisher":"swing3", "charge":"charge", "running":"dash_attack"}.get(move_kind, "swing") if brawler() else "swing"
	if brawler() and parry_pose > 0: return "parry"
	if blocking: return "block"
	return "idle_combat"
func pressed(input, action: String) -> bool:
	if buffered == action:
		buffered = ""
		return true
	return input.just_pressed(action)
func tick(input, paused := false) -> Dictionary:
	feedback.clear()
	if paused or result != "": return {"impulse": Vector3.ZERO, "pose": pose()}
	# Shield is independent of animation hurt; hitstop still counts toward protection.
	if modern():
		protection = maxi(0, protection - 1)
		parry_pose = maxi(0, parry_pose - 1)
		if guard_age >= 0: guard_age += 1
		if input.just_pressed("secondary") and age < 0 and hurt_age < 0 and roll_age < 0: guard_age = 0
	if extended and hitstop > 0:
		# Hit-stop: the whole fight holds for a couple of ticks; a dodge/swing pressed meanwhile is kept for the
		# first tick after it.
		hitstop -= 1
		if buffered == "":
			if input.just_pressed("dodge"): buffered = "dodge"
			elif input.just_pressed("primary"): buffered = "primary"
		# The defeat beat holds the clear until its hit-stop has played.
		if hitstop == 0 and health > 0 and defeated.size() == encounter.spawns.size(): result = "completed"
		return {"impulse": Vector3.ZERO, "pose": pose()}
	tick_index += 1
	focus(input.is_pressed("focus"))
	blocking = block_available and input.is_pressed("secondary") and age < 0 and roll_age < 0 and hurt_age < 0
	if hurt_age >= 0:
		hurt_age += 1
		if hurt_age >= HURT_TICKS: hurt_age = -1
	if roll_age < 0 and age < 0 and hurt_age < 0 and (pressed(input, "dodge") if extended else input.just_pressed("dodge")):
		roll_age = 0
		rolls += 1
		roll_direction = player.direction(input.get_move())
		if roll_direction.length() < 0.1: roll_direction = -forward()
		roll_direction = roll_direction.normalized()
	if brawler(): moves_input(input)
	if not brawler() and age < 0 and roll_age < 0 and hurt_age < 0 and not blocking and (pressed(input, "primary") if extended else input.just_pressed("primary")):
		age = 0
		swing_id += 1
		swings += 1
		hit_ids = []
	if extended and buffered != "" and not (roll_age < 0 and age < 0 and hurt_age < 0): buffered = ""
	var impulse := roll_direction * (4.0 / 60.0) if roll_age >= 0 and roll_age < ROLL_MOVE else Vector3.ZERO
	if extended and push_ticks > 0:
		impulse += push
		push_ticks -= 1
	if brawler() and age >= 0:
		var frames := frame_data()
		if age < int(frames[0]) + int(frames[1]): impulse += forward() * float(frames[4]) / float(int(frames[0]) + int(frames[1]))
	shown_swing = age
	shown_roll = roll_age
	# Snapshot eligible contacts before applying damage; double KO is not order-dependent.
	var outgoing := []
	var incoming := []
	for enemy in enemies:
		var can_hit := false
		if modern() and enemy.hp > 0 and int(staggered.get(enemy.identity, 0)) > 0:
			staggered[enemy.identity] -= 1
			if int(staggered[enemy.identity]) == 0: enemy.transition("approach")
		else: can_hit = enemy.tick(player.position)
		var distance: float = enemy.body.position.distance_to(player.position)
		var visible := los(player.position, enemy.body.position)
		if attack_window() and enemy.hp > 0 and not hit_ids.has(enemy.identity) and distance <= REACH and visible:
			var direction: Vector3 = (enemy.body.position - player.position).normalized()
			if direction.dot(forward()) >= (-0.25 if brawler() and move_kind == "finisher" else 0.15) or target == enemy.identity: outgoing.append(enemy)
		if can_hit and enemy.hp > 0 and (distance <= enemy.data.attack_range_m if not extended else enemy.in_contact(distance)) and visible and not iframe(roll_age): incoming.append(enemy)
	var hazard_hits := []
	if extended: hazard_hits = tick_hazards()
	for enemy in outgoing:
		if brawler() and hit_ids.size() >= (3 if move_kind == "finisher" else 1): break
		hit_ids.append(enemy.identity)
		if extended and enemy.has_method("armored") and enemy.armored() and not (brawler() and move_kind == "charge"):
			feedback.append({"kind":"armor", "id":enemy.identity})
			continue
		enemy.damage(int(frame_data()[3]), player.position)
		if brawler():
			hitstop = maxi(hitstop, 2)
			if move_kind == "finisher" and enemy.get("knock") != null:
				enemy.knock = (enemy.body.position - player.position).normalized() * 1.2 / 6.0
				enemy.knock_ticks = 6
		feedback.append({"kind":"hit", "id":enemy.identity, "variant":rng.randi_range(0, 2)})
		if extended: struck(enemy)
		if enemy.hp == 0: defeated.append(enemy.identity)
	for enemy in incoming:
		enemy.hit = true
		if blocking and (enemy.body.position-player.position).normalized().dot(forward()) > 0.2:
			if parry_ready(): parry_attacker(enemy)
			else:
				blocks += 1
				feedback.append({"kind":"block"})
		elif hurt_age < 0 and (not modern() or protection == 0):
			var amount: int = mini(health, enemy.data.attack.damage if not extended or not enemy.has_method("current_attack") else int(enemy.current_attack().damage))
			health -= amount
			damage_taken += amount
			if modern(): protection = protection_ticks
			hurt_age = 0
			age = -1
			if extended and enemy.has_method("current_attack"):
				hurt_by(enemy.body.position, float(enemy.robot.get("push_m", 0.0)), int(enemy.robot.get("hitstop_ticks", 0)))
			else:
				impulse += (player.position-enemy.body.position).normalized() * 0.2
			feedback.append({"kind":"hurt"})
	for row in hazard_hits:
		if hurt_age >= 0 or iframe(roll_age) or (modern() and protection > 0): continue
		var amount: int = mini(health, int(row.damage))
		health -= amount
		damage_taken += amount
		if modern(): protection = protection_ticks
		hurt_age = 0
		age = -1
		hurt_by(row.origin, float(row.push), int(row.hitstop))
		feedback.append({"kind":"hurt", "source":row.kind})
	if extended: tick_drops()
	if age >= 0:
		age += 1
		var frames := frame_data()
		if age >= int(frames[0]) + int(frames[1]) + int(frames[2]):
			age = -1
			if brawler() and chain_next != "": start_move(chain_next)
	if roll_age >= 0:
		roll_age += 1
		if roll_age >= ROLL_TICKS: roll_age = -1
	shown_hurt = hurt_age
	if health <= 0: result = "failed"
	elif defeated.size() == encounter.spawns.size():
		if not extended or hitstop == 0: result = "completed"
	elif enemies.all(func(e): return e.hp <= 0):
		for enemy in enemies: release(enemy)
		enemies.clear()
		wave += 1
		spawn_wave()
	if modern(): budget_refresh()
	return {"impulse":impulse, "pose":pose()}
## A landed player hit on a robot: its hit-stop, a boss phase change, its defeat beat and reward drop.
func struck(enemy) -> void:
	if not enemy.has_method("current_attack"): return
	hitstop = maxi(hitstop, int(enemy.robot.get("hitstop_ticks", 0)))
	var at: Vector3 = enemy.body.position
	if enemy.phase_changed:
		enemy.phase_changed = false
		feedback.append({"kind":"phase", "id":enemy.identity, "phase":enemy.phase, "at":[at.x, at.y, at.z]})
		hitstop = maxi(hitstop, 3)
	if enemy.hp == 0: defeat(enemy)
func defeat(enemy) -> void:
	var at: Vector3 = enemy.body.position
	feedback.append({"kind":"defeated", "id":enemy.identity, "at":[at.x, at.y, at.z]})
	if enemy.is_boss():
		feedback.append({"kind":"boss_defeated", "id":enemy.identity, "at":[at.x, at.y, at.z]})
		hitstop = maxi(hitstop, int(enemy.data.boss.defeat_hitstop_ticks))
	var heal := int(enemy.robot.get("heal_drop", 0))
	if heal > 0:
		var d = Hazards.Drop.new()
		next_id += 1
		d.id = next_id
		d.position = Vector3(enemy.body.position.x, enemy.body.position.y + 0.35, enemy.body.position.z)
		d.floor_y = enemy.body.position.y
		d.heal = heal
		drops.append(d)
## Player hurt by a robot or hazard: a readable push slide away from `from` and the attacker's hit-stop.
func hurt_by(from: Vector3, distance: float, stop: int) -> void:
	var away := player.position - from
	away.y = 0.0
	if away.length() > 0.001 and distance > 0.0:
		push = away.normalized() * distance / float(PUSH_TICKS)
		push_ticks = PUSH_TICKS
	hitstop = maxi(hitstop, stop)
func spawn_shot(owner, dir: Vector3, speed_mps: float, radius: float, damage: int, lifetime: int, deflectable: bool, lift: float) -> void:
	var p = Hazards.Projectile.new()
	next_id += 1
	p.id = next_id
	p.owner = owner.identity
	p.floor_y = owner.body.position.y
	p.position = owner.body.position + dir * 0.5 + Vector3.UP * (0.6 + lift)
	p.velocity = dir.normalized() * speed_mps / 60.0
	p.radius = radius
	p.damage = damage
	p.lifetime = lifetime
	p.deflectable = deflectable
	p.push = float(owner.robot.get("push_m", 0.0))
	projectiles.append(p)
	feedback.append({"kind":"cue", "id":"core.combat.projectile.energy"})
func spawn_ring(owner, origin: Vector3, speed_mps: float, reach: float, width: float, damage: int) -> void:
	var w = Hazards.Shockwave.new()
	next_id += 1
	w.id = next_id
	w.owner = owner.identity
	w.origin = Vector3(origin.x, owner.body.position.y, origin.z)
	w.speed = speed_mps / 60.0
	w.max_radius = reach
	w.width = width
	w.damage = damage
	w.push = float(owner.robot.get("push_m", 0.0))
	shockwaves.append(w)
	feedback.append({"kind":"cue", "id":"core.combat.explosion.small"})
## Advance projectiles and rings; returns this tick's hazard contacts on the player, in id order. A swing in its hit
## window deflects a deflectable shot in front of the player; a deflected shot damages the first robot it reaches.
func tick_hazards() -> Array:
	var hits := []
	var lo: Array = encounter.arena.min
	var hi: Array = encounter.arena.max
	for p in projectiles.duplicate():
		p.tick()
		if not p.alive(lo, hi):
			projectiles.erase(p)
			continue
		if p.reflected:
			for enemy in enemies:
				if enemy.hp > 0 and enemy.has_method("current_attack") and p.touches(enemy.body.position, 0.5):
					projectiles.erase(p)
					enemy.damage(DAMAGE, p.position)
					feedback.append({"kind":"hit", "id":enemy.identity, "variant":rng.randi_range(0, 2), "source":"deflect"})
					struck(enemy)
					if enemy.hp == 0: defeated.append(enemy.identity)
					break
			continue
		var flat_p := Vector3(p.position.x, player.position.y, p.position.z)
		var swing_deflect := attack_window() and flat_p.distance_to(player.position) <= REACH
		var guard_deflect: bool = parry_ready() and p.touches(player.position, PLAYER_RADIUS)
		if p.deflectable and (swing_deflect or guard_deflect) and (flat_p - player.position).normalized().dot(forward()) >= 0.15:
			p.reflected = true
			p.age = 0
			var owner = find_target(p.owner)
			var back: Vector3 = (owner.body.position - p.position) if owner != null else -p.velocity
			back.y = 0.0
			p.velocity = back.normalized() * p.velocity.length() * 1.5
			feedback.append({"kind":"deflect"})
			continue
		# A roll's i-frames let a shot pass through; it lands if the pass outlasts them.
		if p.touches(player.position, PLAYER_RADIUS) and not iframe(roll_age):
			projectiles.erase(p)
			hits.append({"kind":"projectile", "damage":p.damage, "origin":p.position - p.velocity * 4.0, "push":p.push, "hitstop":2})
	for w in shockwaves.duplicate():
		w.tick()
		if not w.alive():
			shockwaves.erase(w)
			continue
		if not w.hit and w.touches(player.position, PLAYER_RADIUS) and absf(player.position.y - w.origin.y) < 0.6:
			if iframe(roll_age): continue
			w.hit = true
			hits.append({"kind":"shockwave", "damage":w.damage, "origin":w.origin, "push":w.push, "hitstop":2})
	return hits
func tick_drops() -> void:
	for d in drops.duplicate():
		d.tick()
		if not d.alive():
			drops.erase(d)
		elif Vector2(d.position.x - player.position.x, d.position.z - player.position.z).length() <= Hazards.Drop.PICKUP_M and health > 0:
			health = mini(max_health, health + d.heal)
			drops.erase(d)
			feedback.append({"kind":"heal", "amount":d.heal})
## Presentation hook (the host keeps a defeated enemy's model as a corpse); never changes gameplay.
var on_release := Callable()
func release(enemy) -> void:
	if on_release.is_valid(): on_release.call(enemy)
	enemy.dispose()
	enemy.free()
func snapshot() -> Dictionary:
	var rows := []
	for e in enemies: rows.append(e.snapshot())
	var out := {"tick":tick_index,"health":health,"age":age,"roll":roll_age,"hurt":hurt_age,"target":target,"wave":wave,"defeated":defeated.duplicate(),"enemies":rows,"rng":str(rng.state),"result":result}
	if extended: out.merge(extra_snapshot())
	return out
## 1.1.0 state in hashes and movie/save captures.
func extra_snapshot() -> Dictionary:
	var out := {"projectiles":projectiles.map(func(p): return p.snapshot()), "shockwaves":shockwaves.map(func(w): return w.snapshot()),
		"drops":drops.map(func(d): return d.snapshot()), "next_id":next_id, "hitstop":hitstop, "buffered":buffered,
		"push":[push.x, push.y, push.z], "push_ticks":push_ticks}
	if modern(): out["combat2"] = {"profile":profile,"moveset":moveset,"move_kind":move_kind,"hold_ticks":hold_ticks,"primary_held":primary_held,"chain_next":chain_next,"protection":protection,"protection_ticks":protection_ticks,"attack_busy":attack_busy,"attack_release_tick":attack_release_tick,"attack_waiting":attack_waiting.duplicate(),"attack_requests":attack_requests.duplicate(),"guard_age":guard_age,"parry_pose":parry_pose,"staggered":staggered.duplicate()}
	return out
func restore_extra(d: Dictionary) -> void:
	projectiles.clear(); shockwaves.clear(); drops.clear()
	for row in d.projectiles:
		var p = Hazards.Projectile.new(); p.restore(row); projectiles.append(p)
	for row in d.shockwaves:
		var w = Hazards.Shockwave.new(); w.restore(row); shockwaves.append(w)
	for row in d.drops:
		var x = Hazards.Drop.new(); x.restore(row); drops.append(x)
	next_id = int(d.next_id); hitstop = int(d.hitstop); buffered = str(d.buffered)
	push = Vector3(d.push[0], d.push[1], d.push[2]); push_ticks = int(d.push_ticks)
	if d.has("combat2"):
		for key in d.combat2:
			var value = d.combat2[key]
			self.set(key, value.duplicate(true) if value is Array or value is Dictionary else value)
func dispose() -> void:
	for enemy in enemies: release(enemy)
	enemies.clear()
