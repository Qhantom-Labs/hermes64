"""Python measurement worker, same measure_np math and structured failures."""
import json
import sys
from . import measure_np as M
from .decode import load_rgba
from .guard import GuardError


def main(job_path):
    with open(job_path, encoding='utf-8') as f:
        job = json.load(f)
    errors,images,decode = [],[],[]
    for spec in job['images']:
        try:
            rgba,info = load_rgba(spec['path'],spec['width'],spec['height'])
            images.append(dict(index=spec['index'],srgba=rgba,weight=spec.get('weight',1.),
                               use_palette=spec.get('use_palette',True),crop=spec.get('crop'),
                               exclude=spec.get('exclude',[]),regions=spec.get('regions',{})))
            decode.append(dict(info,index=spec['index']))
        except (M.MeasureError,GuardError,ValueError) as exc:
            errors.append({'index':spec['index'],'reason':str(exc)})
    result = {}
    if not errors:
        try:
            result = M.measure(images)
        except M.MeasureError as exc:
            msg = str(exc)
            index = None
            if msg.startswith('reference '):
                try:
                    index = int(msg.split()[1].rstrip(':'))
                except ValueError:
                    pass
            errors.append({'index':index,'reason':msg})
    out: dict = dict(schema='hermes64.refpack.measurements',version='1.0.0',ok=not errors)
    out.update({'errors':errors} if errors else dict(result,decode=decode))
    with open(job['out'],'w', encoding='utf-8') as f:
        json.dump(out,f,indent=1,sort_keys=True)
        f.write('\n')
    return 2 if errors else 0


if __name__=='__main__':
    sys.exit(main(sys.argv[1]))
