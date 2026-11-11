"""STORY 1.3 (puzzle) runtime data shared by the puzzle bot (tools/puzzle_play.py) and hermes64_export (MERGE5).

The Godot runtime plays the lowered STORY 1.2 build plus two additions: ``puzzle.json`` (the compiled puzzle data
bound to both build hashes, the proved safe-checkpoint set and the pack's look data; loaded by
runtime/godot/modules/puzzle/controller.gd, which refuses a sidecar bound to another build) and the puzzle cue rows
in ``audio.json`` (shipped catalog WAVs, original stock sounds; no synthesis). The puzzle lane wrote these in
tools/puzzle_play.py; they live here so the exporter ships exactly what the bot played.
"""
import hashlib
import json
from pathlib import Path

# Cue event -> shipped audio catalog id (audio/catalog.json); no synthesis or new sounds.
AUDIO = {'puzzle_lever': 'core.lock.turn', 'puzzle_plate': 'core.chest.close', 'puzzle_door': 'core.door.metal.open',
         'puzzle_gate': 'core.gate.creak.open', 'puzzle_push': 'core.footstep.stone.02', 'puzzle_torch': 'core.nature.fire.crackle',
         'puzzle_key': 'core.key.jingle', 'puzzle_unlock': 'core.key.turn', 'puzzle_orb': 'core.magic.chime',
         'puzzle_solve': 'core.reward.fanfare.small', 'puzzle_reset': 'core.gate.creak.close'}


def _runtime_states(game13):
    if '.' in (__package__ or ''):
        from ..story.puzzle.saves import runtime_states
    else:
        from story.puzzle.saves import runtime_states
    return runtime_states(game13)


def sidecar(game13, root):
    """Runtime sidecar: the compiled puzzle data bound to both build hashes, the reachable (safe-checkpoint) set,
    plus the style pack's look data (palette and painted texture recipes) for the procedural props."""
    side = game13['puzzle']
    pack = game13.get('metadata', {}).get('style_pack', 'n64_v0')
    look_path = Path(root) / 'packs' / pack / 'look.json'
    out = {'api_version': side['api_version'], 'config': side['config'], 'puzzles': side['puzzles'],
           'game_hash': game13['game_hash'], 'lowered_game_hash': game13['lowered']['game_hash'],
           'reachable': _runtime_states(game13)}
    if look_path.is_file():
        out['look'] = json.loads(look_path.read_text(encoding='utf-8'))
    return out


def audio_rows(root):
    """Puzzle cue event -> {path, sha256} of the shipped catalog WAV (the build's audio.json rows)."""
    root = Path(root)
    catalog = {a['id']: a for a in json.loads((root / 'audio/catalog.json').read_text(encoding='utf-8'))['assets']}
    out = {}
    for event, aid in sorted(AUDIO.items()):
        path = root / 'audio' / catalog[aid]['file']
        out[event] = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    return out
