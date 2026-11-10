extends RefCounted
## Fixed-tick combat hazards and pickups (COMBAT lane, gameplay API 1.1.0): projectiles, shockwave rings and
## reward drops. Pure state advanced once per physics tick by combat/runtime.gd; positions are plain arithmetic (no
## physics queries), so they are deterministic and fully captured by snapshot()/restore(). Presentation (stage.gd)
## only reads them.

## A slow straight shot. Damages the player once (unless i-frames hold) when their centres come within radius plus
## the player radius horizontally; a deflected shot flies back toward its owner and damages the first robot it reaches.
class Projectile:
	var id := 0
	var owner := ""
	var position := Vector3.ZERO
	var velocity := Vector3.ZERO
	var radius := 0.25
	var damage := 1
	var age := 0
	var lifetime := 240
	var deflectable := false
	var reflected := false
	var floor_y := 0.0
	var push := 0.0
	func tick() -> void:
		position += velocity
		age += 1
	func alive(lo: Array, hi: Array) -> bool:
		return age < lifetime and position.x >= float(lo[0]) - 1.0 and position.x <= float(hi[0]) + 1.0 and position.z >= float(lo[2]) - 1.0 and position.z <= float(hi[2]) + 1.0
	func touches(p: Vector3, other_radius: float) -> bool:
		return Vector2(position.x - p.x, position.z - p.z).length() <= radius + other_radius
	## Ticks before this shot's first contact with a body standing at p, in the telegraph convention (0 = the next
	## tick touches; see combat/telegraph.gd); -1 when its path misses or it has already passed.
	func contact_in(p: Vector3, other_radius := 0.3) -> int:
		var v := Vector2(velocity.x, velocity.z)
		var speed := v.length()
		if speed <= 0.0001: return 0 if touches(p, other_radius) else -1
		var to := Vector2(p.x - position.x, p.z - position.z)
		var along := to.dot(v / speed)
		var miss := absf(to.cross(v / speed))
		var reach := radius + other_radius
		if miss > reach: return -1
		var half := sqrt(maxf(0.0, reach * reach - miss * miss))
		if along + half < 0.0: return -1
		# Moves until touching (the shot moves, then contact is tested, each tick).
		return maxi(0, ceili((along - half) / speed) - 1)
	## Ticks a body at p spends inside this shot's reach as it passes.
	func pass_ticks(other_radius := 0.3) -> int:
		var speed := Vector2(velocity.x, velocity.z).length()
		return 0 if speed <= 0.0001 else ceili(2.0 * (radius + other_radius) / speed)
	func marker(danger_ticks := 10, player := Vector3.ZERO) -> Dictionary:
		var dir := Vector3(velocity.x, 0.0, velocity.z)
		var speed := dir.length()
		dir = dir.normalized() if speed > 0.0001 else Vector3(0, 0, 1)
		var left := lifetime - age
		var c := contact_in(player)
		# A shot still heading for the player shows its path (up to 4.5 m); one that will miss keeps a short stub.
		return {"shape": "lane", "origin": Vector3(position.x, floor_y, position.z), "dir": dir,
			"length": minf(speed * float(left), 4.5 if c >= 0 else 0.9), "width": radius * 2.0, "progress": 1.0,
			"danger": c >= 0 and c <= danger_ticks, "contact_in": c, "open": c >= 0 and c + pass_ticks() <= 15}
	func colour() -> Color:
		# Orange below the N64 gate's neon line (saturation >= 0.6 at value >= 0.92); pale blue once deflected.
		return Color(0.55, 0.85, 0.95) if reflected else Color(0.86, 0.56, 0.28)
	func snapshot() -> Dictionary:
		return {"id": id, "owner": owner, "p": [position.x, position.y, position.z], "v": [velocity.x, velocity.y, velocity.z],
			"r": radius, "dmg": damage, "age": age, "life": lifetime, "deflect": deflectable, "back": reflected, "floor": floor_y, "push": push}
	func restore(d: Dictionary) -> void:
		id = int(d.id); owner = str(d.owner); position = Vector3(d.p[0], d.p[1], d.p[2]); velocity = Vector3(d.v[0], d.v[1], d.v[2])
		radius = float(d.r); damage = int(d.dmg); age = int(d.age); lifetime = int(d.life); deflectable = bool(d.deflect)
		reflected = bool(d.back); floor_y = float(d.floor); push = float(d.push)

## An expanding ground ring. Damages a grounded player once while the band [radius - width/2, radius + width/2]
## covers them (a roll's i-frames pass through it).
class Shockwave:
	var id := 0
	var owner := ""
	var origin := Vector3.ZERO
	var radius := 0.0
	var speed := 0.1
	var max_radius := 4.0
	var width := 0.6
	var damage := 1
	var age := 0
	var hit := false
	var push := 0.0
	func tick() -> void:
		radius += speed
		age += 1
	func alive() -> bool:
		return radius - width * 0.5 <= max_radius
	func distance(p: Vector3) -> float:
		return Vector2(p.x - origin.x, p.z - origin.z).length()
	func touches(p: Vector3, other_radius := 0.3) -> bool:
		var d := distance(p)
		return d + other_radius >= radius - width * 0.5 and d - other_radius <= radius + width * 0.5 and d - other_radius <= max_radius
	## Ticks before the band first covers a body at p (telegraph convention: 0 = the next tick); -1 when it is past
	## the body, beyond its reach, or has already landed.
	func contact_in(p: Vector3, other_radius := 0.3) -> int:
		var d := distance(p) - other_radius
		if d > max_radius or hit: return -1
		var outer := radius + width * 0.5
		if d <= outer: return 0 if distance(p) + other_radius >= radius - width * 0.5 else -1
		# The ring grows, then contact is tested, each tick.
		return maxi(0, ceili((d - outer) / maxf(speed, 0.0001)) - 1)
	func pass_ticks(other_radius := 0.3) -> int:
		return ceili((width + 2.0 * other_radius) / maxf(speed, 0.0001))
	func marker(danger_ticks := 10, player := Vector3.ZERO) -> Dictionary:
		var c := contact_in(player)
		var outer := radius + width * 0.5
		return {"shape": "ring", "origin": origin, "radius": maxf(outer, 0.1), "inner": clampf((radius - width * 0.5) / maxf(outer, 0.1), 0.0, 0.98),
			"progress": 1.0, "danger": c >= 0 and c <= danger_ticks, "contact_in": c, "open": glyph_open(player), "reach": max_radius}
	func glyph_open(player: Vector3) -> bool:
		var c := contact_in(player)
		return c >= 0 and c + pass_ticks() <= 15
	func snapshot() -> Dictionary:
		return {"id": id, "owner": owner, "o": [origin.x, origin.y, origin.z], "r": radius, "speed": speed, "max": max_radius,
			"w": width, "dmg": damage, "age": age, "hit": hit, "push": push}
	func restore(d: Dictionary) -> void:
		id = int(d.id); owner = str(d.owner); origin = Vector3(d.o[0], d.o[1], d.o[2]); radius = float(d.r); speed = float(d.speed)
		max_radius = float(d.max); width = float(d.w); damage = int(d.dmg); age = int(d.age); hit = bool(d.hit); push = float(d.push)

## Reward drop: restores `heal` health when the player walks within PICKUP_M; gone after LIFETIME ticks.
class Drop:
	const PICKUP_M := 0.7
	const LIFETIME := 900
	var id := 0
	var position := Vector3.ZERO
	var heal := 1
	var age := 0
	var radius := 0.18
	var floor_y := 0.0
	func tick() -> void:
		age += 1
	func alive() -> bool:
		return age < LIFETIME
	func colour() -> Color:
		return Color(0.55, 0.95, 0.6)
	func snapshot() -> Dictionary:
		return {"id": id, "p": [position.x, position.y, position.z], "heal": heal, "age": age, "floor": floor_y}
	func restore(d: Dictionary) -> void:
		id = int(d.id); position = Vector3(d.p[0], d.p[1], d.p[2]); heal = int(d.heal); age = int(d.age); floor_y = float(d.floor)
