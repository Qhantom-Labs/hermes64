"""Summarise sweep failures: python3 tools/failsum.py reports/sweep/<tag>/samples.jsonl [gen]"""
import collections
import json
import re
import sys

path = sys.argv[1]
only = sys.argv[2] if len(sys.argv) > 2 else None
by = collections.defaultdict(collections.Counter)
examples = {}
for line in open(path):
    r = json.loads(line)
    if only and r["gen"] != only:
        continue
    if r["status"] == "passed":
        continue
    for k, v in (r.get("fails") or {}).items():
        for part in v.split("; "):
            key = re.sub(r"[-0-9.]+", "#", part)[:110]
            by[r["gen"]][k + ": " + key] += 1
            examples.setdefault((r["gen"], k + ": " + key), (r["i"], r["pack"], part[:160], r["params"]))
    if not r.get("fails"):
        by[r["gen"]]["status=" + r["status"]] += 1
for g, c in sorted(by.items()):
    print("==", g)
    for k, n in c.most_common(8):
        ex = examples.get((g, k))
        print("  %3d  %s" % (n, k))
        if ex and only:
            print("        e.g. i=%s %s %s" % (ex[0], ex[1], ex[2]))
            print("        params=%s" % json.dumps(ex[3], sort_keys=True)[:400])
