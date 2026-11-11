# Putting a hermes64 web export on Cloudflare Pages (steps for the owner)

No agent runs these steps. Deploying, the domain and the Cloudflare account are the owner's decisions, one by one.

## 1. Pack the export (local, no network)

```
python3 -B -m tools.site_pack <web export folder> <new site folder>
```

- Copies the export byte for byte, writes `_headers`, and splits any file above the per-file limit into `.partNNN` files plus `sitepack-loader.js`, which joins them in the browser. With today's exports that means `index.wasm` (37,695,054 bytes) becomes two parts of 20 MiB and 15.95 MiB.
- Prints a size report and writes `SITE-PACK.json` (every file with sha256, each part's sha256, a check that the joined parts equal the original).
- Exit code 0 only if every joined sha256 matches and no file is still over the limit.
- Options: `--headers none` (no cross-origin isolation headers), `--limit-mib N` (or env `SITE_PACK_LIMIT_MIB`), `--part-mib N`, `--splittable .wasm,.pck`. Only files the engine fetches with `fetch()` can be split; anything else over the limit stops the tool with a clear message.

## 2. Check it locally first

```
python3 -B -m tools.site_pack --serve <site folder> --port 8060          # sends the _headers file
python3 -B -m tools.site_pack --serve <site folder> --ignore-headers     # same, without headers
```

Open `http://127.0.0.1:8060/` in Chrome. Automatic check in headless Chrome (loopback only):

```
python3 -B -m tools.site_pack_smoke <site folder> <new output folder> [--ignore-headers]
```

## 3. Before uploading: confirm the limit

The per-file limit used by default, **25 MiB, was not read from Cloudflare's documentation** in this lane (no network was allowed). Look it up on Cloudflare's Pages limits page. If it is different, re-pack with `--limit-mib <value>` (and `--part-mib` at or below it). If Pages ever accepts the whole file, `--limit-mib 100` packs with no split and no loader.

## 4. Upload (the owner, in the Cloudflare dashboard)

Unverified outline from general knowledge; follow Cloudflare's current screens if they differ:

1. Workers & Pages, Create, Pages, **Upload assets** (direct upload, no Git connection needed).
2. Project name, for example `hermes64`. Upload the **contents** of the site folder (so `index.html` sits at the top level). `SITE-PACK.json` and `README.txt` are harmless if uploaded.
3. After the first deploy, project Custom domains, add `hermes64.qhantom.com`. If `qhantom.com` is on the same Cloudflare account the DNS record is offered automatically; otherwise add the CNAME it shows.
4. Command-line alternative (needs `wrangler` installed and logged in, which no agent has done): `npx wrangler pages deploy <site folder> --project-name hermes64`.

## 5. Check the live site

- Open the page in Chrome with the console open: no errors; the game reaches its first screen.
- In the console: `crossOriginIsolated` is `true` with the default headers; `window.sitePack.files` lists `index.wasm` when a split happened.
- Network tab: `index.wasm.part000` and `.part001` load with status 200; `index.wasm` itself is never requested from the server (the loader answers it).

## Headers: what was measured

Local Chrome (headless, SwiftShader), Thaw and Reedland Combat exports from `play-fix3/`, which use the **no-threads** Godot template (`GODOT_THREADS_ENABLED = false`):

| Served with | crossOriginIsolated | Boots | Console errors |
|---|---|---|---|
| COOP `same-origin` + COEP `require-corp` | true | yes | 0 |
| no headers (`--ignore-headers`, and a `--headers none` pack) | false | yes | 0 |
| original unsplit export, no headers (control) | false | yes | 0 |

So for these builds the headers are **not required**. They are kept by default because the brief asked for them and a threads build would need them. Cost of keeping them: COEP `require-corp` blocks cross-origin resources that do not send CORP/CORS headers (external fonts, analytics, embedded iframes). The exports load nothing cross-origin today. Pack with `--headers none` if the page ever embeds such things.

## Fallback if splitting is not wanted

Host the one large file on Cloudflare R2 behind the same domain and keep the rest on Pages. Not built or tested here.
