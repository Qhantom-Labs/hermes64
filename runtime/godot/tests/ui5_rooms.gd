extends SceneTree
## UI5 room size measurement (headless, read-only): for every room of res://game.json, the runtime's own
## capsule-clear grid (view/solid_navigation.gd: 0.25 m cells, capsule radius/height and bounds margin from the
## input tuning, the room's boundary outline and solid footprints). Same clear-square definition as
## tools/room_clearance.py: largest square of reachable capsule-centre cells x 0.25 m + capsule diameter.
const View = preload("res://playtest/view.gd")
const Wire = preload("res://core/wire.gd")
const Nav = preload("res://view/solid_navigation.gd")

func _initialize() -> void: call_deferred("run")

func frame() -> void:
	view_ref.actions.submit_frame({})
	await physics_frame
	await process_frame

var view_ref

func wall_height(view) -> Dictionary:
	var shell: Dictionary = view.room_root.shell_info
	if not shell.is_empty() and shell.get("meta", {}).has("height"):
		return {"height_m": float(shell.meta.height), "source": "shell_meta"}
	var top := 0.0
	var found := false
	for n in view.room_root.find_children("*", "VisualInstance3D", true, false):
		var placed := ""
		var p: Node = n
		while p != null and p != view.room_root:
			if p.has_meta("placed"): placed = str(p.get_meta("placed")); break
			p = p.get_parent()
		if placed in ["wall", "shell"]:
			var box: AABB = n.global_transform * n.get_aabb()
			top = maxf(top, box.end.y); found = true
	if found: return {"height_m": snappedf(top, 0.01), "source": "wall_mesh_aabb"}
	if view.room_root.presentation.get("exterior", false): return {"height_m": 0.0, "source": "exterior"}
	return {"height_m": float(view.room_root.presentation.get("wall_height", 3.2)), "source": "presentation_default"}

func measure_room(view, room: Dictionary) -> Dictionary:
	var t: Dictionary = view.actions.profile.tuning
	var w := float(room.grid_size[0])
	var d := float(room.grid_size[1])
	var nav = Nav.new()
	nav.configure(view.room_root.solid_definitions, Vector2(w, d), float(t.capsule_radius_m), float(t.capsule_height_m), float(t.bounds_margin_m), view.room_root.boundary_outline)
	var nx: int = nav.grid.region.size.x
	var nz: int = nav.grid.region.size.y
	var start: Vector2i = nav.start_cell(view.player.position)
	var seen := {}
	if not nav.grid.is_point_solid(start):
		var stack := [start]
		seen[start] = true
		while not stack.is_empty():
			var c: Vector2i = stack.pop_back()
			for o in [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
				var q: Vector2i = c + o
				if q.x >= 0 and q.y >= 0 and q.x < nx and q.y < nz and not nav.grid.is_point_solid(q) and not seen.has(q):
					seen[q] = true
					stack.append(q)
	var best := 0
	var dp := []
	for i in nx + 1:
		var row := []
		row.resize(nz + 1)
		row.fill(0)
		dp.append(row)
	var lo := Vector2(INF, INF)
	var hi := Vector2(-INF, -INF)
	for i in nx:
		for j in nz:
			if seen.has(Vector2i(i, j)):
				dp[i + 1][j + 1] = 1 + mini(dp[i][j + 1], mini(dp[i + 1][j], dp[i][j]))
				best = maxi(best, dp[i + 1][j + 1])
				lo = Vector2(minf(lo.x, i), minf(lo.y, j)); hi = Vector2(maxf(hi.x, i), maxf(hi.y, j))
	var r := float(t.capsule_radius_m)
	var cell: float = nav.CELL
	var side := best * cell + 2.0 * r
	var extent := Vector2.ZERO if seen.is_empty() else (hi - lo + Vector2.ONE) * cell + Vector2.ONE * 2.0 * r
	var wh := wall_height(view)
	return {"room": room.id, "grid_m": [w, d], "boundary": view.room_root.boundary_source, "solids": view.room_root.solid_definitions.size(),
		"walkable_m2": snappedf(seen.size() * cell * cell, 0.01), "walkable_extent_m": [snappedf(extent.x, 0.01), snappedf(extent.y, 0.01)],
		"clear_square_m": snappedf(side, 0.01), "clear_square_body_widths": snappedf(side / (2.0 * r), 0.1),
		"body_width_m": 2.0 * r, "wall_height_m": wh.height_m, "wall_height_source": wh.source,
		"exterior": bool(view.room_root.presentation.get("exterior", false)), "shell": not view.room_root.shell_info.is_empty()}

func run() -> void:
	var out := ""
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--output="): out = a.get_slice("=", 1)
	var view = View.new()
	view_ref = view
	root.add_child(view)
	var booted: Dictionary = view.boot(Wire.read_json("res://game.json"), {"pack": "res://theme.json", "bindings": "res://bindings.json", "test": true})
	if not booted.ok:
		print("UI5 ROOMS ", JSON.stringify({"ok": false, "boot": booted}))
		await view.quit_cleanly(2)
		return
	view.actions.set_source("bot")
	var rows := []
	for room in view.runtime.game.rooms:
		if view.runtime.state.location != room.id:
			view.runtime.state.location = room.id
			view.enter_room("")
		for i in 3: await frame()
		rows.append(measure_room(view, room))
	var report := {"ok": true, "game": view.runtime.game.id, "metadata_template": view.runtime.game.metadata.get("template", ""), "rooms": rows}
	if out != "":
		var f := FileAccess.open(out, FileAccess.WRITE)
		f.store_string(JSON.stringify(report, "  "))
		f.close()
	print("UI5 ROOMS ", JSON.stringify(report))
	await view.quit_cleanly(0)
