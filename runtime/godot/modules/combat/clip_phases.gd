extends RefCounted
## Phase-locked combat clip keys (MERGE3). Every clip is 16 STEP keys over 1 s (key k at k/15 s).
## The fixed-tick combat state chooses the key; a clip clock never drives gameplay.
## A phase spanning keys k0..k1 over `ticks` physics ticks shows k0 + min(n-1, floor(t*n/ticks)).
## The gameplay windows stay in combat/runtime.gd; these maps make the shown keys follow them:
## swing keys 5-7 exactly while the hit window is open, roll keys 2-9 exactly while i-frames hold.
const Combat = preload("res://modules/combat/runtime.gd")
const FPS := 15
const LAST := 15

static func phase_key(k0: int, k1: int, t: int, ticks: int) -> int:
	if ticks <= 0: return k1
	var n := k1 - k0 + 1
	return k0 + mini(n - 1, floori(float(maxi(t, 0) * n) / float(ticks)))

static func phase(meta: Dictionary, clip: String, name: String, fallback: Array) -> Array:
	var value = meta.get(clip, {}).get("phases", {}).get(name, fallback)
	return value if value is Array and value.size() == 2 else fallback

## Player swing: anticipation over the windup, active over the hit window, recovery after it.
static func swing_key(t: int, meta := {}) -> int:
	var a: Array = phase(meta, "swing", "anticipation", [1, 4])
	var h: Array = phase(meta, "swing", "active", [5, 7])
	var r: Array = phase(meta, "swing", "recovery", [8, 15])
	if t < Combat.WINDUP: return phase_key(a[0], a[1], t, Combat.WINDUP)
	if t < Combat.WINDUP + Combat.ACTIVE: return phase_key(h[0], h[1], t - Combat.WINDUP, Combat.ACTIVE)
	return phase_key(r[0], r[1], t - Combat.WINDUP - Combat.ACTIVE, Combat.RECOVERY)

## Optional brawler clips share phase ranges, but use the move's own fixed-tick windows.
static func move_key(t: int, frames: Array) -> int:
	if t < int(frames[0]): return phase_key(1, 4, t, int(frames[0]))
	if t < int(frames[0]) + int(frames[1]): return phase_key(5, 7, t - int(frames[0]), int(frames[1]))
	return phase_key(8, 15, t - int(frames[0]) - int(frames[1]), int(frames[2]))

## Player roll: the documented i-frame keys span exactly the runtime's invulnerable ticks; rise and
## ready follow. The one crouch key (1) is not shown because the runtime's roll is invulnerable from
## its first tick.
static func roll_key(t: int, meta := {}) -> int:
	var tuck: Array = meta.get("roll", {}).get("iframes", [2, 9])
	if Combat.iframe(t): return phase_key(tuck[0], tuck[1], t, Combat.ROLL_IFRAMES)
	return phase_key(tuck[1] + 1, LAST, t - Combat.ROLL_IFRAMES, Combat.ROLL_TICKS - Combat.ROLL_IFRAMES)

static func hurt_key(t: int) -> int:
	return phase_key(1, LAST, t, Combat.HURT_TICKS)

## Real-time clips at 15 fps from key 0; death holds its last key.
static func realtime_key(t: int) -> int:
	return mini(LAST, floori(float(maxi(t, 0)) * FPS / 60.0))

## Looping clips show keys 0-14 (key 15 == key 0).
static func loop_key(t: int) -> int:
	return floori(float(maxi(t, 0)) * FPS / 60.0) % LAST

## Block raises over two ticks (protection starts on the press tick, unchanged), then plays the guard
## keys in real time and holds the last one while the guard is held.
static func block_key(t: int, meta := {}) -> int:
	var guard: Array = meta.get("block", {}).get("guard_frames", [3, 15])
	if t < 2: return 1 + maxi(t, 0)
	return mini(guard[1], guard[0] + floori(float(t - 2) * FPS / 60.0))

## Enemy clip and key for an FSM state after the enemy's tick, from its saved FSM `age` (so a
## restored replay shows the same keys). Post-tick ages: telegraph/attack/recover run 1..N over their
## N ticks, hurt runs 0..12, dead never ticks (`dead_t` is the host's presentation count).
## telegraph: keys 1-15 over windup_ticks, ending on the hold keys; attack: only the documented
## hit-window keys over active_ticks, because every attack tick may land (launch/spring keys before
## the window are not shown); recover: keys 1-15 over recovery_ticks; hurt: keys 1-15 over 12 ticks;
## dead: real time from key 0, holding key 15; idle/approach loop keys 0-14 at 15 fps.
static func enemy_pose(row: Dictionary, data: Dictionary, state: String, age: int, dead_t := 0) -> Array:
	var clip: String = row.get("fsm_state_clip", {}).get(state, "idle")
	var attack: Dictionary = data.get("attack", {})
	match state:
		"telegraph": return [clip, phase_key(1, LAST, age - 1, int(attack.get("windup_ticks", 1)))]
		"attack": return [clip, phase_key(enemy_hit(row)[0], enemy_hit(row)[1], age - 1, int(attack.get("active_ticks", 1)))]
		"recover": return [clip, phase_key(1, LAST, age - 1, int(attack.get("recovery_ticks", 1)))]
		"hurt": return [clip, phase_key(1, LAST, age, int(data.get("hurt_ticks", Combat.ENEMY_HURT_TICKS)))]
		"dead": return [clip, realtime_key(dead_t)]
	return [clip, loop_key(age)]

static func enemy_hit(row: Dictionary) -> Array:
	var hit = row.get("phases", {}).get("attack", {}).get("hit_window", {}).get("frames", [1, LAST])
	return hit if hit is Array and hit.size() == 2 else [1, LAST]
