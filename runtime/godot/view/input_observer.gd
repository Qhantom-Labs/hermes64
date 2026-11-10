extends Node
## Opt-in read-only native input receipt. Enabled only by --observe=/absolute/folder.
## Never injects input or mutates gameplay. Requests are capture/resize/clean quit only.
var view
var out := ""
var serial := ""
var os_events := []
func attach(presenter, folder: String) -> void:
	view=presenter; out=folder
	get_tree().root.window_input.connect(func(event):
		if event is InputEventKey: os_events.append({"key":event.physical_keycode,"down":event.pressed,"tick":view.actions.tick}))
	call_deferred("observe")
func observe() -> void:
	while true:
		await get_tree().create_timer(0.05).timeout
		var p: Vector3=view.player.position
		var b: Basis=view.player.move_basis()
		var c: Camera3D=view.viewport.get_camera_3d()
		var targets := {}
		for id in view.room_root.target_positions:
			var at: Vector3=view.room_root.target_positions[id]; targets[id]=[at.x,at.y,at.z]
		if view.module_host != null:
			for a in view.ui_actions:
				var at: Vector3=view.module_host.anchor(a.id)
				if at != Vector3.INF: targets[a.id]=[at.x,at.y,at.z]
		var host=view.module_host
		var state := {"pid":OS.get_process_id(),"tick":view.actions.tick,"room":view.runtime.state.location,"position":[p.x,p.y,p.z],"right":[b.x.x,b.x.z],"back":[b.z.x,b.z.z],"context":view.actions.context,"dialogue":view.dialogue_active(),"panel":view.n64_ui.dlg_on,"text":view.n64_ui.dlg_text,"page":view.page_index,"pages":view.text_pages.size(),"candidate":view.current_candidate.get("id",""),"targets":targets,"raw":view.actions.last_frame,"viewport":[view.viewport.size.x,view.viewport.size.y],"framed":c.is_position_in_frustum(p+Vector3.UP*0.7),"framed_body":c.is_position_in_frustum(p+Vector3.UP*0.05) and c.is_position_in_frustum(p+Vector3.UP*1.5),"active":host.active_id if host != null else "","swings":host.combat.swings if host != null and host.combat != null else 0,"os_events":os_events,"capture":serial}
		var f := FileAccess.open(out.path_join("state.tmp"),FileAccess.WRITE); f.store_string(JSON.stringify(state)); f.close()
		DirAccess.rename_absolute(out.path_join("state.tmp"),out.path_join("state.json"))
		var request := out.path_join("request.json")
		if FileAccess.file_exists(request):
			var command = JSON.parse_string(FileAccess.get_file_as_string(request))
			DirAccess.remove_absolute(request)
			if command.get("quit",false): await view.quit_cleanly(); return
			if command.has("size"): get_tree().root.size=Vector2i(command.size[0],command.size[1])
			if command.has("shot"):
				await view.capture(out.path_join(command.shot+".png"))
				serial=command.shot
