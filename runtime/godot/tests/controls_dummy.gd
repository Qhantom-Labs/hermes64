extends Node
## TEST FIXTURE ONLY, not a shipped combat/course implementation.
## Exercises external consumers through non-consuming Actions edges + movie hooks.
var view
var mode := 0
var tick := 0
var hits := 0
var damage := 0
var invulnerable_until := -1
var active_until := -1
var hit_this_swing := false
var dead := false
var retry_tick := -1
var accepted := []
func reset(case_number: int) -> void:
	mode=case_number; tick=0; hits=0; damage=0; invulnerable_until=-1; active_until=-1; hit_this_swing=false; dead=false; retry_tick=-1; accepted=[]
func snapshot() -> Dictionary:
	return {"mode":mode,"tick":tick,"hits":hits,"damage":damage,"invulnerable_until":invulnerable_until,"active_until":active_until,"hit_this_swing":hit_this_swing,"dead":dead,"retry_tick":retry_tick,"accepted":accepted.duplicate()}
func restore(s: Dictionary) -> void:
	for key in s: set(key,s[key])
func _physics_process(_delta: float) -> void:
	tick += 1
	var a = view.actions
	if mode == 8:
		if tick == 4 and a.consume_buffer("primary",true): accepted.append("buffer3")
		if tick == 20 and a.consume_buffer("primary",false,a.tick-4): accepted.append("coyote4")
		if tick == 40 and a.consume_buffer("primary",true): accepted.append("expired9")
		if tick == 60 and a.consume_buffer("primary",false,a.tick-9): accepted.append("old_contact9")
	elif mode == 10:
		if a.just_pressed("primary") and not dead:
			active_until=tick+8; hit_this_swing=false
		if tick<active_until and not hit_this_swing: hits+=1; hit_this_swing=true
		if a.just_pressed("dodge"): invulnerable_until=tick+15
		# Fixed 24-tick telegraph to damage tick; one deterministic dummy only.
		if tick == 48 and tick>=invulnerable_until: damage+=1
		if tick == 90: dead=true
		if dead and a.just_pressed("reset"): dead=false; retry_tick=tick
