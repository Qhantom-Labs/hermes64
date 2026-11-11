extends Node3D
## Presentation-only actor. World motion belongs to Player/follower controllers, never the clip clock.
var model: Node3D
var skeleton: Skeleton3D
var animation: AnimationPlayer
var pose_fps := 15.0
var pose_speed := 1.0
var manual_clock := false
var clock := 0.0
var pose_elapsed := 0.0
var pose_tick := -1
var sample_time := 0.0
var clip := ""
var materials := []
var faces := []
var ground_offset := 0.0
var base_expression := 0
## Baked locomotion (docs/LOCOMOTION.md): the `hermes64_locomotion` block of the character file. Empty = a file
## without baked locomotion, which plays exactly as before.
var locomotion := {}
var cycle_next := ""
## Continuous phase (docs/LOCOMOTION.md 6): tables read from the file's own keys by set_locomotion (empty = the
## stepped path, drive_step), and the sources shown while drive() owns the pose.
const LOCO_GRID := 4                 # samples per key in the take-over search
const LOCO_LIFT := 0.002             # m: a boot that changes contact inside a key interval stays this far above the band
const LOCO_START_S := 0.15           # idle -> cycle
const LOCO_STOP_S := 0.25            # cycle -> idle: per settle step (one or two steps)
const LOCO_STEP_MIN := 0.02          # m: a boot further than this from its idle place steps there (else it is eased)
const LOCO_STEP_UP := 0.03           # m: how high a settle step lifts the boot above the ground band
const LOCO_UPPER_S := 0.2            # spine, head and arms in a walk <-> run take-over
const LOCO_START_MPS := 0.12         # the idle pose's boots ride with the body: their share may move a boot this fast
const LOCO_WINDOW_KEYS := 4.0        # longest walk <-> run take-over, in keys of the cycle that hands over
static var loco_cache := {}
var loco := {}
var loco_on := false                 # drive() owns the skeleton (a cycle, or a fade)
var loco_cur := {}                   # {"clip": "walk"|"run", "phase": keys, "dphase"} or {"clip": "pose", "pose": [...]}
var loco_nxt := {}                   # the source fading in, or {}
var loco_fade := {}                  # {"kind": "start"|"gait"|"stop", "prog", "t", "d", "seconds"|"keys"}
var loco_speed := 0.0
var loco_want := "idle"
## COMBATFIX: a module walking the actor in a stance ({"clip", "key"}, e.g. idle_combat): spine, head and arms hold that
## key over the cycle, a stop settles into it. Empty = as before.
var hold := {}
static var hold_cache := {}
func configure(scene: Node3D, row: Dictionary) -> void:
	model = scene
	add_child(model)
	set_meta("real_character", true)
	set_meta("character_id", row.character_id)
	set_meta("placeholder", false)
	for n in model.find_children("*", "Skeleton3D", true, false): skeleton = n
	for n in model.find_children("*", "AnimationPlayer", true, false): animation = n
	if animation != null:
		animation.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		for name in animation.get_animation_list():
			var a := animation.get_animation(name)
			# Cached character instances share Animation resources: write only when the value
			# differs, because every write emits `changed` to every mixer using the clip.
			if a.loop_mode != Animation.LOOP_LINEAR: a.loop_mode = Animation.LOOP_LINEAR
			for i in a.get_track_count():
				if a.track_get_interpolation_type(i) != Animation.INTERPOLATION_NEAREST: a.track_set_interpolation_type(i, Animation.INTERPOLATION_NEAREST)
	# GLB is already Y-up, metres, floor-origin; retain optional small authored correction only.
	ground_offset = float(row.get("ground_offset",0.0))
	model.position.y = ground_offset
	var shadow := MeshInstance3D.new()
	shadow.name = "shadow_blob"
	var radius := 0.24 if row.source_rig == "quad16_v1" else 0.32
	var vertices := PackedVector3Array([Vector3.ZERO])
	var normals := PackedVector3Array([Vector3.UP])
	var indices := PackedInt32Array()
	for i in 12:
		var angle := TAU * float(i) / 12.0
		vertices.append(Vector3(cos(angle)*radius,0,sin(angle)*radius))
		normals.append(Vector3.UP)
		indices.append_array(PackedInt32Array([0,1+i,1+(i+1)%12]))
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_INDEX] = indices
	var disk := ArrayMesh.new()
	disk.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
	shadow.mesh = disk
	shadow.position.y = 0.012
	shadow.scale.z = 0.7
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.cull_mode = BaseMaterial3D.CULL_DISABLED
	m.albedo_color = Color(0.04,0.04,0.08,0.28)
	shadow.material_override = m
	shadow.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(shadow)
	play_clip("idle")
func set_locomotion(block: Dictionary) -> void:
	locomotion = {}
	if animation == null or not block.has("walk") or not animation.has_animation("walk"): return
	if int(block.get("cycle_keys", 0)) < 2 or float(block.get("fps", 0.0)) <= 0.0 or float(block.walk.get("stride_mps", 0.0)) <= 0.0: return
	locomotion = block
	# A baked cycle is cycle_keys long (16 keys = 16/15 s) but its last key sits at 15/15 s, where the file's clip ends.
	# The clip gets the cycle's length here, so the last key is held for its 1/15 s like every other key; left at the
	# file's length the loop would wrap at that key and show key 0 twice.
	var period := float(block.cycle_keys) / float(block.fps)
	for name in ["walk", "run"]:
		if animation.has_animation(name) and not is_equal_approx(animation.get_animation(name).length, period): animation.get_animation(name).length = period
	loco = {}
	loco = loco_build()
## ---- Baked cycles at continuous phase (docs/LOCOMOTION.md 6) -----------------------------------------------------
## Read once per file from its own keys: every key of walk and run as bone poses; which boot is on the ground at each
## key (the block's toe and heel points under the bake's clearance, min(12 mm, 1.5 % of the hip height)); each boot's
## transform per key; the phases where one cycle takes over from the other with the planted boot in place, and where a
## cycle starts from idle. {} when the skeleton lacks the base's leg bones: drive() then takes the stepped path.
func loco_build() -> Dictionary:
	if skeleton == null or not locomotion.has("sole"): return {}
	var key := "%d:%d:%s" % [animation.get_animation("walk").get_instance_id(), animation.get_animation("run").get_instance_id() if animation.has_animation("run") else 0, JSON.stringify(locomotion)]
	if loco_cache.has(key): return loco_cache[key]
	var t := {"bone": {}, "keys": {}, "foot_t": {}, "planted": {}, "pts": {}, "parent": [], "low": [], "clips": ["walk"], "windows": {}, "start": {}}
	for b in ["thigh_l", "shin_l", "foot_l", "thigh_r", "shin_r", "foot_r"]:
		t.bone[b] = skeleton.find_bone(b)
		if t.bone[b] < 0: return {}
	for s in ["l", "r"]:
		if skeleton.get_bone_parent(t.bone["shin_" + s]) != t.bone["thigh_" + s] or skeleton.get_bone_parent(t.bone["foot_" + s]) != t.bone["shin_" + s]: return {}
	if animation.has_animation("run") and not locomotion.get("run", {}).is_empty() and float(locomotion.run.get("stride_mps", 0.0)) > 0.0: t.clips.append("run")
	var n := skeleton.get_bone_count()
	for i in n:
		t.parent.append(skeleton.get_bone_parent(i))
		t.low.append(false)
	# bones whose pose moves a boot: each thigh, every bone above it and every bone below it
	for i in n:
		var p := i
		while p >= 0 and p != t.bone.thigh_l and p != t.bone.thigh_r: p = t.parent[p]
		if p >= 0: t.low[i] = true
	for s in ["l", "r"]:
		var p: int = t.bone["thigh_" + s]
		while p >= 0:
			t.low[p] = true
			p = t.parent[p]
	var fps := float(locomotion.fps)
	var keys := int(locomotion.cycle_keys)
	var lo := INF
	var heights := {}
	var shown := loco_capture()                           # the pose on screen, put back at the end
	for c in t.clips:
		t.keys[c] = []
		t.foot_t[c] = []
		heights[c] = []
		for k in keys:
			t.keys[c].append(loco_sample(c, float(k) / fps))
			var ft := {}
			var h := {}
			for s in ["l", "r"]:
				ft[s] = skeleton.get_bone_global_pose(t.bone["foot_" + s])
				h[s] = loco_low_point(ft[s], s)
				lo = minf(lo, h[s])
			t.foot_t[c].append(ft)
			heights[c].append(h)
	t.idle = loco_sample("idle", 0.0)                      # idle key 0 (rest without an idle clip): where idle starts
	t.idle_foot = {"l": skeleton.get_bone_global_pose(t.bone.foot_l), "r": skeleton.get_bone_global_pose(t.bone.foot_r)}
	t.lo = lo
	t.clear = minf(0.012, 0.015 * float(locomotion.get("hip_height_m", 1.0)))
	for c in t.clips:
		t.planted[c] = {"l": [], "r": []}
		for k in keys:
			for s in ["l", "r"]: t.planted[c][s].append(float(heights[c][k][s]) < lo + t.clear)
	loco = t                                               # loco_pose reads it
	for c in t.clips:
		t.pts[c] = []
		for i in keys * LOCO_GRID: t.pts[c].append(loco_points(loco_pose(c, float(i) / LOCO_GRID)))
	t.idle_pts = loco_points(t.idle)
	if t.clips.size() == 2:
		t.windows["walk>run"] = loco_search("walk", "run")
		t.windows["run>walk"] = loco_search("run", "walk")
	for c in t.clips: t.start[c] = loco_start_phase(c)
	loco_apply(shown)
	loco_cache[key] = t
	return t
## The bone poses of clip c at a time, read from the clip's own tracks; bones without a track stay at rest, as when the
## clip plays. The AnimationPlayer is not touched (its clip and playhead stay as they were), so building the tables
## changes nothing that a later play_clip() shows.
func loco_sample(c: String, time: float) -> Array:
	skeleton.reset_bone_poses()
	if animation.has_animation(c):
		var anim := animation.get_animation(c)
		for tr in anim.get_track_count():
			var kind := anim.track_get_type(tr)
			if kind != Animation.TYPE_POSITION_3D and kind != Animation.TYPE_ROTATION_3D and kind != Animation.TYPE_SCALE_3D: continue
			var bone := skeleton.find_bone(str(anim.track_get_path(tr).get_concatenated_subnames()))
			if bone < 0 or not anim.track_is_enabled(tr): continue
			if kind == Animation.TYPE_POSITION_3D: skeleton.set_bone_pose_position(bone, anim.position_track_interpolate(tr, time))
			elif kind == Animation.TYPE_ROTATION_3D: skeleton.set_bone_pose_rotation(bone, anim.rotation_track_interpolate(tr, time))
			else: skeleton.set_bone_pose_scale(bone, anim.scale_track_interpolate(tr, time))
	return loco_capture()
func loco_capture() -> Array:
	var n := skeleton.get_bone_count()
	var pos := PackedVector3Array()
	var scl := PackedVector3Array()
	var rot := []
	pos.resize(n)
	scl.resize(n)
	rot.resize(n)
	for i in n:
		pos[i] = skeleton.get_bone_pose_position(i)
		var q := skeleton.get_bone_pose_rotation(i)
		rot[i] = q if q.is_normalized() else q.normalized()
		scl[i] = skeleton.get_bone_pose_scale(i)
	return [pos, rot, scl]
func loco_apply(pose: Array) -> void:
	for i in pose[1].size():
		skeleton.set_bone_pose_position(i, pose[0][i])
		skeleton.set_bone_pose_rotation(i, pose[1][i])
		skeleton.set_bone_pose_scale(i, pose[2][i])
## Skeleton-space transform of bone i of a pose (memoised in g).
func loco_global(pose: Array, g: Array, i: int) -> Transform3D:
	if g[i] != null: return g[i]
	var local := Transform3D(Basis(pose[1][i]) * Basis.from_scale(pose[2][i]), pose[0][i])
	var p: int = loco.parent[i]
	g[i] = local if p < 0 else loco_global(pose, g, p) * local
	return g[i]
func loco_low_point(foot: Transform3D, s: String) -> float:
	var sole: Dictionary = locomotion.sole[s]
	return minf((foot * Vector3(sole.toe[0], sole.toe[1], sole.toe[2])).y, (foot * Vector3(sole.heel[0], sole.heel[1], sole.heel[2])).y)
## Toe and heel of both boots (skeleton space) for a pose.
func loco_points(pose: Array) -> Dictionary:
	var g := []
	g.resize(pose[1].size())
	var out := {}
	for s in ["l", "r"]:
		var f := loco_global(pose, g, loco.bone["foot_" + s])
		var sole: Dictionary = locomotion.sole[s]
		out[s] = [f * Vector3(sole.toe[0], sole.toe[1], sole.toe[2]), f * Vector3(sole.heel[0], sole.heel[1], sole.heel[2])]
	return out
## The pose of cycle c at a phase in keys: bone by bone between the two keys around it (rotations along the sphere).
## Inside a key interval where a boot touches down or lifts off, that boot goes the straight way from its transform at
## one key to the other (turning evenly), kept LOCO_LIFT above the ground band, and the thigh and shin are solved to
## reach it: a boot never skims the band while it moves. At a key the pose is that key, untouched.
func loco_pose(c: String, phase: float) -> Array:
	var keys := int(locomotion.cycle_keys)
	var x := fposmod(phase, float(keys))
	var k0 := int(floorf(x))
	var f := x - float(k0)
	if f > 0.999999999:
		k0 += 1
		f = 0.0
	k0 = posmod(k0, keys)
	var a: Array = loco.keys[c][k0]
	if f < 0.000000001: return [a[0].duplicate(), a[1].duplicate(), a[2].duplicate()]
	var k1 := (k0 + 1) % keys
	var b: Array = loco.keys[c][k1]
	var n: int = a[1].size()
	var pos := PackedVector3Array()
	var scl := PackedVector3Array()
	var rot := []
	pos.resize(n)
	scl.resize(n)
	rot.resize(n)
	for i in n:
		pos[i] = a[0][i].lerp(b[0][i], f)
		rot[i] = a[1][i].slerp(b[1][i], f)
		scl[i] = a[2][i].lerp(b[2][i], f)
	var pose := [pos, rot, scl]
	for s in ["l", "r"]:
		if loco.planted[c][s][k0] != loco.planted[c][s][k1]:
			var fa: Transform3D = loco.foot_t[c][k0][s]
			var fb: Transform3D = loco.foot_t[c][k1][s]
			var target := Transform3D(Basis(fa.basis.get_rotation_quaternion().slerp(fb.basis.get_rotation_quaternion(), f)), fa.origin.lerp(fb.origin, f))
			var need: float = float(loco.lo) + float(loco.clear) + LOCO_LIFT
			var low := loco_low_point(target, s)
			if low < need: target.origin.y += need - low
			loco_reach(pose, s, target)
	return pose
## Two-bone solve: thigh and shin turn so the ankle reaches target (knee in the plane of the leg as interpolated), the
## foot takes target's orientation.
func loco_reach(pose: Array, s: String, target: Transform3D) -> void:
	var th: int = loco.bone["thigh_" + s]
	var sh: int = loco.bone["shin_" + s]
	var ft: int = loco.bone["foot_" + s]
	var g := []
	g.resize(pose[1].size())
	var gt := loco_global(pose, g, th)
	var gs := loco_global(pose, g, sh)
	var gf := loco_global(pose, g, ft)
	var hip := gt.origin
	var knee := gs.origin
	var ank := gf.origin
	var l1 := hip.distance_to(knee)
	var l2 := knee.distance_to(ank)
	var normal := (knee - hip).cross(ank - hip)
	if normal.length() < 0.000001: normal = gt.basis.x
	normal = normal.normalized()
	var d := target.origin - hip
	var dl := clampf(d.length(), absf(l1 - l2) + 0.0001, l1 + l2 - 0.0001)
	var u := d.normalized()
	var along := (l1 * l1 - l2 * l2 + dl * dl) / (2.0 * dl)
	var up := sqrt(maxf(0.0, l1 * l1 - along * along))
	var out := normal.cross(u).normalized()
	if out.dot(knee - hip) < 0.0: out = -out
	var knee2 := hip + u * along + out * up
	var ank2 := hip + u * dl
	var rt := gt.basis.orthonormalized()
	var rt2 := Basis(Quaternion((knee - hip).normalized(), (knee2 - hip).normalized())) * rt
	var turn := rt2 * rt.inverse()
	var rs := turn * gs.basis.orthonormalized()
	var rs2 := Basis(Quaternion((turn * (ank - knee)).normalized(), (ank2 - knee2).normalized())) * rs
	var p: int = loco.parent[th]
	var rp := loco_global(pose, g, p).basis.orthonormalized() if p >= 0 else Basis()
	pose[1][th] = (rp.inverse() * rt2).get_rotation_quaternion()
	pose[1][sh] = (rt2.inverse() * rs2).get_rotation_quaternion()
	pose[1][ft] = (rs2.inverse() * target.basis.orthonormalized()).get_rotation_quaternion()
## Boot s on the ground and the other boot in the air at a phase of cycle c (contact changes count as in the air).
func loco_down(c: String, s: String, phase: float) -> bool:
	var keys := int(locomotion.cycle_keys)
	var x := fposmod(phase, float(keys))
	var k0 := int(floorf(x + 0.000000001))
	var f := x - float(k0)
	k0 = posmod(k0, keys)
	if f < 0.000000001: return loco.planted[c][s][k0]
	return loco.planted[c][s][k0] and loco.planted[c][s][(k0 + 1) % keys]
func loco_single(c: String, s: String, phase: float) -> bool:
	return loco_down(c, s, phase) and not loco_down(c, "r" if s == "l" else "l", phase)
func loco_pts_at(c: String, phase: float) -> Dictionary:
	var count: int = loco.pts[c].size()
	var x := fposmod(phase, float(locomotion.cycle_keys)) * LOCO_GRID
	var i := int(floorf(x + 0.000000001))
	var f := clampf(x - float(i), 0.0, 1.0)
	var a: Dictionary = loco.pts[c][posmod(i, count)]
	var b: Dictionary = loco.pts[c][posmod(i + 1, count)]
	return {"l": [a.l[0].lerp(b.l[0], f), a.l[1].lerp(b.l[1], f)], "r": [a.r[0].lerp(b.r[0], f), a.r[1].lerp(b.r[1], f)]}
## Largest coordinate difference between the toe / heel points on the ground in both poses (-1: none shared).
func loco_gap(pa: Dictionary, pb: Dictionary, s: String) -> float:
	var lim: float = float(loco.lo) + float(loco.clear)
	var out := -1.0
	for j in 2:
		if pa[s][j].y < lim and pb[s][j].y < lim:
			var d: Vector3 = (pb[s][j] - pa[s][j]).abs()
			out = maxf(out, maxf(d.x, maxf(d.y, d.z)))
	return out
## Where cycle b takes over from cycle a: for every phase a0 of a with one boot down and the other in the air, the phase
## b0 of b (same boot down, other in the air) whose planted toe / heel is nearest; then the longest window (keys of a,
## both keeping that support while b advances stride_a / stride_b keys per key of a) and its cost: the largest move of
## the planted boot per key of a caused by the cross-fade. The cheapest window wins (longer within 0.5 mm per key).
func loco_search(a: String, b: String) -> Dictionary:
	var r := float(locomotion[a].stride_mps) / float(locomotion[b].stride_mps)
	var count := int(locomotion.cycle_keys) * LOCO_GRID
	var lim: float = float(loco.lo) + float(loco.clear)
	var out := {}
	for s in ["l", "r"]:
		var best := {}
		for i in count:
			var a0 := float(i) / LOCO_GRID
			if not loco_single(a, s, a0): continue
			var b0 := -1.0
			var near := INF
			var pa := loco_pts_at(a, a0)
			for i2 in count:
				var p2 := float(i2) / LOCO_GRID
				if not loco_single(b, s, p2): continue
				var gap := loco_gap(pa, loco_pts_at(b, p2), s)
				if gap >= 0.0 and gap < near:
					near = gap
					b0 = p2
			if b0 < 0.0: continue
			var length := LOCO_WINDOW_KEYS
			while length >= 0.5:
				var steps := int(roundf(length * LOCO_GRID))
				var ok := true
				for j in steps + 1:
					if not (loco_single(a, s, a0 + float(j) / LOCO_GRID) and loco_single(b, s, b0 + float(j) * r / LOCO_GRID)):
						ok = false
						break
				if ok:
					var cost := 0.0
					var prev := []
					for j in steps + 1:
						var qa := loco_pts_at(a, a0 + float(j) / LOCO_GRID)
						var qb := loco_pts_at(b, b0 + float(j) * r / LOCO_GRID)
						var w := smoothstep(0.0, 1.0, float(j) / float(steps))
						var row := [qa[s][0], qa[s][1], qb[s][0], qb[s][1], w]
						if j > 0:
							var shared := false
							for q in 2:
								if prev[q].y < lim and prev[2 + q].y < lim and row[q].y < lim and row[2 + q].y < lim:
									shared = true
									var e0: Vector3 = (prev[2 + q] - prev[q]) * float(prev[4])
									var e1: Vector3 = (row[2 + q] - row[q]) * w
									var dd := (e1 - e0).abs()
									cost = maxf(cost, maxf(dd.x, maxf(dd.y, dd.z)) * LOCO_GRID)
							if not shared:
								ok = false
								break
						prev = row
					if ok:
						if best.is_empty() or cost < float(best.cost) - 0.0005 or (cost < float(best.cost) + 0.0005 and length > float(best.keys)):
							best = {"a0": a0, "b0": b0, "keys": length, "cost": cost}
						break
				length -= 0.5
		out[s] = best
	return out
## The phase of cycle c where it starts from idle: one boot down, the other in the air, the planted toe and heel nearest
## (along the way of travel) to where they are in idle.
func loco_start_phase(c: String) -> float:
	var best := INF
	var out := 0.0
	for i in int(locomotion.cycle_keys) * LOCO_GRID:
		var phase := float(i) / LOCO_GRID
		for s in ["l", "r"]:
			if not loco_single(c, s, phase): continue
			var p: Dictionary = loco.pts[c][i]
			var d := maxf(absf(p[s][0].z - loco.idle_pts[s][0].z), absf(p[s][1].z - loco.idle_pts[s][1].z))
			if d < best:
				best = d
				out = phase
	return out
## Shows one cycle at one phase without a fade (frame strips, tests).
func show_cycle(c: String, phase: float) -> void:
	if loco.is_empty() or not loco.keys.has(c): return
	loco_on = true
	loco_cur = {"clip": c, "phase": phase, "dphase": 0.0}
	loco_nxt = {}
	loco_fade = {}
	loco_speed = 0.0
	clip = c
	sample_time = phase / float(locomotion.fps)
	loco_apply(loco_pose(c, phase))
## COMBATFIX: the held stance key as a pose (read from the clip's tracks, cached per clip and key; the pose shown is
## put back, so reading it changes nothing on screen).
func loco_held() -> Array:
	var c := str(hold.clip)
	var k := int(hold.get("key", 0))
	var key := "%d:%s:%d" % [animation.get_animation(c).get_instance_id() if animation.has_animation(c) else 0, c, k]
	if not hold_cache.has(key):
		var keep := loco_capture()
		hold_cache[key] = loco_sample(c, minf(float(k) / pose_fps, animation.get_animation(c).length - 0.000001) if animation.has_animation(c) else 0.0)
		loco_apply(keep)
	return hold_cache[key]
## Spine, head and arms (the bones that move no boot) from the held pose; legs, pelvis and root from the cycle.
func loco_upper(pose: Array, held: Array) -> Array:
	var pos: PackedVector3Array = pose[0].duplicate()
	var rot: Array = pose[1].duplicate()
	var scl: PackedVector3Array = pose[2].duplicate()
	for i in rot.size():
		if loco.low[i]: continue
		pos[i] = held[0][i]
		rot[i] = held[1][i]
		scl[i] = held[2][i]
	return [pos, rot, scl]
func loco_end() -> void:
	loco_on = false
	loco_cur = {}
	loco_nxt = {}
	loco_fade = {}
	clip = ""
func loco_source(src: Dictionary) -> Array:
	return src.pose if src.clip == "pose" else loco_pose(src.clip, float(src.phase))
## One tick of the baked cycles: phases advance with the ground speed, fades progress, take-overs start, pose applied.
func loco_tick(delta: float) -> void:
	clock += delta
	pose_elapsed += delta
	var keys := float(locomotion.cycle_keys)
	for src in [loco_cur, loco_nxt]:
		if src.has("phase"):
			src.dphase = float(locomotion.fps) * loco_speed / float(locomotion[src.clip].stride_mps) * delta
			src.phase = fposmod(float(src.phase) + float(src.dphase), keys)
	if loco_fade.get("kind", "") == "stop" and loco_want != "idle":
		loco_begin(loco_want)                              # moving again before idle is reached: start from the pose shown
	if not loco_fade.is_empty():
		loco_fade.t = float(loco_fade.t) + delta
		# a take-over follows the phase of the cycle handing over; when the body all but stops it also follows time
		if loco_fade.kind == "gait": loco_fade.prog = float(loco_fade.prog) + maxf(float(loco_cur.dphase) / float(loco_fade.keys), delta / LOCO_UPPER_S)
		else:
			loco_fade.prog = float(loco_fade.prog) + delta / float(loco_fade.seconds)
			loco_fade.d = float(loco_fade.d) + absf(loco_speed) * delta
		if float(loco_fade.prog) >= 1.0 and (loco_fade.kind != "gait" or float(loco_fade.t) >= LOCO_UPPER_S):
			if loco_fade.kind == "stop":
				loco_end()
				play_clip("idle" if hold.is_empty() else str(hold.clip))  # idle plays as before, from its key 0
				return
			loco_cur = loco_nxt
			loco_nxt = {}
			loco_fade = {}
	if loco_fade.is_empty():
		if loco_want == "idle": loco_stop()
		elif loco_cur.clip != loco_want: loco_take_over()
	loco_apply(loco_compose() if hold.is_empty() else loco_upper(loco_compose(), loco_held()))
	var main: Dictionary = loco_nxt if loco_nxt.has("phase") else loco_cur
	clip = "idle" if loco_fade.get("kind", "") == "stop" else str(main.clip)
	sample_time = float(main.get("phase", 0.0)) / float(locomotion.fps)
	var tick := floori((pose_elapsed + 0.000001) * pose_fps)
	if tick != pose_tick:
		pose_tick = tick
		if not faces.is_empty(): expression(1 if fmod(clock, 4.0) > 3.85 else base_expression)
## walk <-> run: on the tick the shown cycle reaches the start of a take-over window, the other cycle comes in at the
## matching phase (its planted boot where this one's is) and the two cross-fade over the window, each at its own
## phase rate, so the planted boot stays where it is in both. A file whose cycles have no such window switches at a
## contact key with the phase kept.
func loco_take_over() -> void:
	var keys := float(locomotion.cycle_keys)
	var w: Dictionary = loco.windows.get(str(loco_cur.clip) + ">" + loco_want, {})
	var any := false
	for s in ["l", "r"]:
		var win: Dictionary = w.get(s, {})
		if win.is_empty(): continue
		any = true
		var back := fposmod(float(loco_cur.phase) - float(win.a0), keys)
		if back < float(loco_cur.get("dphase", 0.0)) + 0.000000001:
			var r := float(locomotion[loco_cur.clip].stride_mps) / float(locomotion[loco_want].stride_mps)
			loco_nxt = {"clip": loco_want, "phase": fposmod(float(win.b0) + back * r, keys), "dphase": 0.0}
			loco_fade = {"kind": "gait", "prog": back / float(win.keys), "t": 0.0, "d": 0.0, "keys": float(win.keys)}
			return
	if any: return
	var half := keys / 2.0
	var before := float(loco_cur.phase) - float(loco_cur.get("dphase", 0.0))
	if floorf(before / half) != floorf(float(loco_cur.phase) / half): loco_cur = {"clip": loco_want, "phase": loco_cur.phase, "dphase": 0.0}
## cycle -> idle (the body has stopped): the pose eases to idle key 0, and each boot that is in the air or further than
## LOCO_STEP_MIN from its idle place takes a settle step there, one boot after the other (the one in the air first,
## then the one further away); a boot on the ground waits where it is until its step. A step lifts the boot above the
## ground band before it moves along the ground and sets it down after: no boot slides into the idle stance.
func loco_stop() -> void:
	var feet := {}
	var steppers := []
	var target: Array = loco.idle if hold.is_empty() else loco_held()
	var g := []
	g.resize(target[1].size())
	for s in ["l", "r"]:
		var a := skeleton.get_bone_global_pose(loco.bone["foot_" + s])
		var b: Transform3D = loco.idle_foot[s] if hold.is_empty() else loco_global(target, g, loco.bone["foot_" + s])
		var down := loco_low_point(a, s) < float(loco.lo) + float(loco.clear)
		var step := not down or a.origin.distance_to(b.origin) > LOCO_STEP_MIN
		feet[s] = {"a": a, "b": b, "step": step, "down": down, "far": a.origin.distance_to(b.origin), "w0": 0.0, "w1": 1.0}
		if step: steppers.append(s)
	if steppers.size() == 2 and (feet[steppers[1]].down == false and feet[steppers[0]].down or (feet[steppers[0]].down == feet[steppers[1]].down and float(feet[steppers[1]].far) > float(feet[steppers[0]].far))):
		steppers.reverse()
	var n := maxi(1, steppers.size())
	for i in steppers.size():
		feet[steppers[i]].w0 = float(i) / float(n)
		feet[steppers[i]].w1 = float(i + 1) / float(n)
	loco_nxt = {"clip": "pose", "pose": target}
	loco_fade = {"kind": "stop", "prog": 0.0, "t": 0.0, "d": 0.0, "seconds": LOCO_STOP_S * float(n), "feet": feet}
## The pose shown: the current source, or the cross-fade to the next one. Bones that move a boot (legs, pelvis, root)
## follow the fade weight; spine, head and arms follow a time weight in a take-over. In idle -> cycle the idle pose's
## boots ride with the body while the cycle's planted boot stays, so the idle share times the distance travelled may
## grow and shrink by at most LOCO_START_MPS. In cycle -> idle the boots follow their settle steps (loco_stop).
func loco_compose() -> Array:
	var a := loco_source(loco_cur)
	if loco_nxt.is_empty(): return a
	var b := loco_source(loco_nxt)
	var w_low := smoothstep(0.0, 1.0, float(loco_fade.prog))
	var w_up := w_low
	if loco_fade.kind == "gait": w_up = smoothstep(0.0, 1.0, float(loco_fade.t) / LOCO_UPPER_S)
	elif loco_fade.kind == "start":
		var seconds := float(loco_fade.seconds)
		var t := clampf(float(loco_fade.prog), 0.0, 1.0) * seconds
		var e := LOCO_START_MPS * minf(t, seconds - t)
		var d := float(loco_fade.d)
		w_low = 1.0 - (minf(1.0, e / d) if d > 0.000000001 else 1.0)
	var n: int = a[1].size()
	var pos := PackedVector3Array()
	var scl := PackedVector3Array()
	var rot := []
	pos.resize(n)
	scl.resize(n)
	rot.resize(n)
	for i in n:
		var w := w_low if loco.low[i] else w_up
		pos[i] = a[0][i].lerp(b[0][i], w)
		rot[i] = a[1][i].slerp(b[1][i], w)
		scl[i] = a[2][i].lerp(b[2][i], w)
	var pose := [pos, rot, scl]
	if loco_fade.kind == "stop":
		var prog := clampf(float(loco_fade.prog), 0.0, 1.0)
		for s in ["l", "r"]:
			var f: Dictionary = loco_fade.feet[s]
			var fa: Transform3D = f.a
			var fb: Transform3D = f.b
			var target: Transform3D
			if not f.step: target = fa.interpolate_with(fb, smoothstep(0.0, 1.0, prog))
			else:
				var u := clampf((prog - float(f.w0)) / (float(f.w1) - float(f.w0)), 0.0, 1.0)
				target = fa.interpolate_with(fb, smoothstep(0.2, 0.8, u))     # along the ground only while lifted
				target.origin.y += sin(PI * u) * (float(loco.clear) + LOCO_LIFT + LOCO_STEP_UP)
			loco_reach(pose, s, target)
	return pose
func loco_begin(want: String) -> void:
	loco_on = true
	loco_cur = {"clip": "pose", "pose": loco_capture()}
	loco_nxt = {"clip": want, "phase": float(loco.start.get(want, 0.0)), "dphase": 0.0}
	loco_fade = {"kind": "start", "prog": 0.0, "t": 0.0, "d": 0.0, "seconds": LOCO_START_S}
	clip = want
func cycle_clip(value: String) -> bool:
	return not locomotion.is_empty() and (value == "walk" or value == "run")
## Baked cycles loop on cycle_keys / fps seconds; the key index is taken in whole keys, so the seek lands on a key time.
func cycle_time() -> float:
	var fps := float(locomotion.fps)
	return float(posmod(floori((clock + 0.000001) * fps), int(locomotion.cycle_keys))) / fps
## Baked locomotion only: walk below run.enter_mps, run at or above it, back to walk below run.exit_mps (both scale with
## the leg). With the tables (loco) the cycles play at continuous phase (loco_tick); without them, stepped (drive_step).
func drive(speed: float, still_mps: float, back := false) -> void:  # back: the cycle plays backwards (COMBATFIX)
	if loco.is_empty():
		drive_step(speed, still_mps)
		return
	var shown := "idle"
	if loco_on: shown = str(loco_nxt.clip) if loco_nxt.has("phase") else (str(loco_cur.clip) if loco_cur.has("phase") else "idle")
	var want := "idle"
	if speed > still_mps:
		want = "walk"
		var run: Dictionary = locomotion.get("run", {})
		if loco.clips.size() == 2 and speed >= float(run.exit_mps if shown == "run" else run.enter_mps): want = "run"
	loco_speed = -speed if back else speed
	loco_want = want
	if loco_on: return
	pose_speed = 1.0
	if want == "idle": play_clip("idle")
	else: loco_begin(want)
## The stepped baked path (before continuous phase): walk at speed / walk.stride_mps; run at or above run.enter_mps, back
## to walk below run.exit_mps; a pose is held until the cycle reaches the next key, and the key changes on a tick, so a
## boot slides whenever the body is not at the cycle's own stride. Used when loco is empty (and as the known-bad control).
func drive_step(speed: float, still_mps: float) -> void:
	var want := "idle"
	if speed > still_mps:
		want = "walk"
		var run: Dictionary = locomotion.get("run", {})
		if not run.is_empty() and animation.has_animation("run") and speed >= float(run.exit_mps if clip == "run" else run.enter_mps): want = "run"
	# walk <-> run changes one pose for another in one tick (no cross-fade here), so it waits for the cycle to reach
	# a contact key (key 0 or half a cycle later), where the two cycles are closest: advance_pose makes the switch
	# on the tick that key comes up, so the key is held for its full time in the new cycle.
	cycle_next = ""
	if cycle_clip(want) and cycle_clip(clip) and want != clip:
		cycle_next = want
		want = clip
	pose_speed = speed / float(locomotion[want].stride_mps) if want != "idle" else 1.0
	play_clip(want)
func play_clip(value: String) -> void:
	if animation == null: return
	if loco_on: loco_end()                                 # any clip asked for by name ends the continuous cycles
	if not animation.has_animation(value): value = "idle"
	if value == clip: return
	var keep_phase := cycle_clip(clip) and cycle_clip(value)
	clip = value
	if not keep_phase: clock = 0.0
	pose_elapsed = 0.0
	pose_tick = -1
	sample_time = 0.0
	# Godot's glTF import keeps a channel only where it leaves the rest pose, so a bone a clip holds at rest has no
	# track in it and would keep the previous clip's pose (a leg stays bent after sit -> idle). Start every clip from
	# rest so each plays exactly as authored.
	if skeleton != null: skeleton.reset_bone_poses()
	animation.play(clip)
	if keep_phase: sample_time = cycle_time()
	animation.seek(sample_time, true)
func advance_pose(delta: float) -> void:
	if loco_on:
		if clip == "":                                     # cleared from outside (a module's held pose): nothing plays
			loco_end()
			return
		loco_tick(delta)
		return
	if animation == null or clip == "": return
	clock += delta * pose_speed
	pose_elapsed += delta
	var next_tick := floori((pose_elapsed+0.000001)*pose_fps)
	# A baked cycle shows every key in turn: the pose changes when the cycle reaches the next key, so a boot on the
	# ground moves back one key's worth for one key's worth of travel at any speed. On the fixed 15 Hz gate below a
	# cycle played faster than authored would skip keys (1 in 4 at 3.2 m/s on a 2.43 m/s run) and the boot would jump.
	if cycle_clip(clip): next_tick = floori((clock + 0.000001) * float(locomotion.fps))
	if next_tick == pose_tick: return
	if cycle_clip(clip) and cycle_next != "" and posmod(next_tick, int(locomotion.cycle_keys) / 2) == 0:
		var to := cycle_next
		cycle_next = ""
		play_clip(to)                                     # keeps the phase; shows the contact key of the new cycle
		pose_tick = next_tick
		return
	pose_tick = next_tick
	var length := animation.get_animation(clip).length
	var held := floorf((clock + 0.000001) * pose_fps) / pose_fps
	sample_time = fmod(held, length) if length > 0.0 else 0.0
	if cycle_clip(clip): sample_time = cycle_time()
	animation.seek(sample_time, true)
	if clip == "talk" and not faces.is_empty() and int(faces[0].cols) * int(faces[0].rows) >= 4:
		expression(2 + int(floor(clock * 5)) % 2)
	elif not faces.is_empty():
		expression(1 if fmod(clock, 4.0) > 3.85 else base_expression)
func _process(delta: float) -> void:
	if not manual_clock: advance_pose(delta)
func face_velocity(velocity: Vector3) -> void:
	if Vector2(velocity.x,velocity.z).length() > 0.01:
		rotation.y = atan2(velocity.x, velocity.z)
func expression(cell: int) -> void:
	for face in faces:
		var cols: int = face.cols
		var rows: int = face.rows
		var chosen := clampi(cell,0,cols*rows-1)
		# glTF V is down; Blender's atlas cells were indexed bottom-up.
		face.material.set_shader_parameter("uv_offset", Vector2(float(chosen % cols) / cols, float(rows - 1 - chosen / cols) / rows))
