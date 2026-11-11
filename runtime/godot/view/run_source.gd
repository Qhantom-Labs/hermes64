extends RefCounted
## SCENES lane: read-only adapter from the game's run state to the results card.
## It never writes run state. Two sources, named in every receipt:
## - "combat2_run": `module_host.run` from the combat2 lane (fields ticks, deaths,
##   finished_tick, rules.death_penalty_ticks). Used when present and enabled.
## - "STUB_story_clock": games without a run block (or builds without combat2).
##   Time is the fixed-tick Actions clock at the finishing tick, deaths 0, no
##   penalty. Deterministic under replay because Actions.tick is movie state.

static func read(view, end_tick: int) -> Dictionary:
	var host = view.get("module_host") if view != null else null
	var run = host.get("run") if host != null else null
	if run != null and bool(run.get("enabled")) and run.has_method("snapshot"):
		var s: Dictionary = run.snapshot()
		var rules = run.get("rules")
		var per_death := int(rules.get("death_penalty_ticks", 0)) if rules is Dictionary else 0
		var finished := int(s.get("finished_tick", -1))
		var deaths := int(s.get("deaths", 0))
		return {"source":"combat2_run","ticks": finished if finished >= 0 else int(s.get("ticks", 0)),
			"deaths": deaths, "penalty_ticks": deaths * per_death, "penalty_rule": per_death, "finished": finished >= 0}
	return {"source":"STUB_story_clock","ticks": maxi(0, end_tick), "deaths": 0, "penalty_ticks": 0, "penalty_rule": 0, "finished": true}

## mm:ss.cc from 60 Hz ticks, integer arithmetic only (no float rounding drift).
static func clock(ticks: int) -> String:
	var t := maxi(0, ticks)
	var cs := (t * 100) / 60
	return "%02d:%02d.%02d" % [cs / 6000, (cs / 100) % 60, cs % 100]

static func seconds(ticks: int) -> String:
	var cs := (maxi(0, ticks) * 100) / 60
	return "%d.%02d" % [cs / 100, cs % 100]
