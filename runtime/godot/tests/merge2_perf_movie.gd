extends "res://input/movie.gd"
## Perf-harness movie: identical playback/verification, plus two harness-only
## options. `pinned_build` lets an optimised build replay a movie recorded on the
## pre-optimisation build; the per-60-tick state hashes then PROVE the optimisation
## did not change the simulation (a divergence still fails the run). `hash_ticks`
## records which frames paid for a checkpoint hash so they can be reported apart.
var pinned_build := ""
var hash_ticks := {}
func build_hash() -> String:
	return pinned_build if pinned_build != "" else super.build_hash()
func real_build_hash() -> String:
	return super.build_hash()
func _physics_process(delta: float) -> void:
	if playing:
		for expected in movie.hashes:
			if int(expected.tick) == cursor + 1: hash_ticks[cursor + 1] = true
	super._physics_process(delta)
