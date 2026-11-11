"""Absolute-path child entry; never imports bpy and never installs dependencies."""
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    kind,job = sys.argv[1:]
    try:
        if kind=='measure':
            from refpack.measure import main as measure
            return measure(job)
        if kind=='proof':
            from refpack.proof import main as proof
            return 0 if proof(job)['ok'] else 3
        raise ValueError('unknown worker '+kind)
    except ImportError as exc:
        data = json.loads(Path(job).read_text(encoding='utf-8'))
        reason = 'Configure python_path with Python 3.9+ and numpy (JPEG also needs Pillow): '+str(exc)
        Path(data['out']).write_text(json.dumps({'ok':False,'error':reason,'errors':[{'index':None,'reason':reason}]}), encoding='utf-8')
        return 2


if __name__=='__main__':
    sys.exit(main())
