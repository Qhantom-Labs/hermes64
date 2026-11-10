extends Node3D
## Original data-driven melee templates. Tick transitions do not use pose clocks.
const HURT_TICKS := 12
var data := {}
var identity := ""
var home := Vector3.ZERO
var hp := 0
var state := "idle"
var age := 0
var attack_id := 0
var hit := false
var latched := Vector3.ZERO
var budget_ref: WeakRef
var body: CharacterBody3D
var visual: Node3D
var animation = preload("res://modules/animation_state.gd").new()
func configure(row: Dictionary, spawn: Dictionary, world: Node3D) -> void:
	data = row.duplicate(true)
	identity = spawn.id
	hp = row.max_health
	home = Vector3(spawn.position_m[0], spawn.position_m[1], spawn.position_m[2])
	body = CharacterBody3D.new()
	body.collision_layer = 4
	body.collision_mask = 1
	var shape := CollisionShape3D.new()
	var capsule := CapsuleShape3D.new()
	capsule.height = 1.3
	capsule.radius = 0.3
	shape.shape = capsule
	shape.position.y = 0.7
	body.add_child(shape)
	world.add_child(body)
	body.position = home
func transition(next: String) -> void:
	state = next
	age = 0
func move_toward_point(target: Vector3, speed: float) -> void:
	var d := target - body.position
	d.y = 0
	if d.length() > 0.01:
		body.move_and_collide(d.normalized() * minf(d.length(), speed / 60.0))
		body.rotation.y = atan2(-d.x, -d.z)
func damage(amount: int, from: Vector3) -> void:
	if hp <= 0: return
	hp = maxi(0, hp - amount)
	var knock := body.position - from
	knock.y = 0
	body.move_and_collide(knock.normalized() * 0.18)
	transition("dead" if hp == 0 else "hurt")
func tick(target: Vector3) -> bool:
	if state == "dead": return false
	var distance := body.position.distance_to(target)
	var a: Dictionary = data.attack
	var contact := false
	match state:
		"idle":
			if distance <= data.aggro_range_m: transition("approach")
		"approach":
			if body.position.distance_to(home) > data.leash_range_m:
				move_toward_point(home, data.speed_mps)
				if body.position.distance_to(home) < 0.2: transition("idle")
			elif distance <= data.attack_range_m:
				var combat = budget_ref.get_ref() if budget_ref != null else null
				if combat == null or combat.request_attack(self):
					latched = target
					attack_id += 1
					hit = false
					transition("telegraph")
			else: move_toward_point(target, data.speed_mps)
		"telegraph":
			if age >= a.windup_ticks:
				transition("attack")
				return tick(target)
		"attack":
			if age >= a.active_ticks: transition("recover")
			else:
				if data.fsm.template == "melee_dash_v1": move_toward_point(latched, data.speed_mps * 2.0)
				contact = not hit
		"recover":
			if age >= a.recovery_ticks: transition("approach")
		"hurt":
			if age >= HURT_TICKS: transition("approach")
	age += 1
	return contact
## Melee contact reach (used for 1.1.0 encounters; the 1.0.0 path inlines the same test).
func in_contact(distance: float) -> bool:
	return distance <= data.attack_range_m
func snapshot() -> Dictionary:
	return {"id":identity, "hp":hp, "state":state, "age":age, "attack_id":attack_id, "hit":hit, "position":[body.position.x,body.position.y,body.position.z]}
func dispose() -> void:
	if is_instance_valid(body): body.free()
