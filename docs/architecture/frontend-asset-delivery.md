# Frontend asset delivery

How the compiled React app reaches the user, and the caching contract that keeps
it working across upgrades.

## The pipeline

```
frontend/src            React sources, 31 routes behind React.lazy()
   │  vite build        code-splits into one content-hashed chunk per route
   ▼
frontend/dist           index.html + assets/<Name>-<hash>.js
   │  stage-backend.py  rmtree + copytree (never an in-place merge)
   ▼
backend/app/static      what `redforge start` serves from source
   │  stage-backend.py  assemble() -> desktop/resources/backend/app/static
   ▼                    (PyInstaller --collect-data also bakes a copy into
desktop/resources/…       _internal/app/static; the two must stay identical)
   │  electron-builder  extraResources
   ▼
<install>/resources/backend/app/static
   │  backend.js sets REDFORGE_STATIC_DIR to this directory
   ▼
FastAPI static_serving.py  ->  http://127.0.0.1:8760
```

`desktop/electron/backend.js` pins `REDFORGE_STATIC_DIR`, so the copy beside the
frozen binary is the one users load. `_internal/app/static` is only the fallback
for running `redforge-backend` directly; staging asserts the two are byte-equal
so a package can never contain two different UIs.

## The caching contract

Content-hashed output under `/assets/` is immutable — the filename *is* the
version — and is cached for a year. Everything else (`index.html`, favicons, the
web manifest) is served `no-cache, must-revalidate`.

That second half is not a nicety. The desktop app always loads the same origin,
`http://127.0.0.1:8760`, and Chromium's HTTP cache lives in the Electron profile,
which survives upgrades. **RedForge 2.0.3 shipped without any `Cache-Control` on
the shell.** Browsers then fall back to heuristic freshness (RFC 9111 §4.2.2) —
about 10% of the document's age — so a freshly installed build booted the
*previous* version's `index.html` and entry bundle straight from disk cache. The
old shell's lazy-import table named chunk hashes the new build no longer
contained, and the app failed like this:

```
TypeError: Failed to fetch dynamically imported module:
http://127.0.0.1:8760/assets/NewEvaluationPage-Ce21fyz1.js
```

The tell is the symptom pattern: the app **opened fine** (its shell was cached)
and only died when the user navigated to a route whose chunk had never been
fetched before, so it had to go to the network. Nothing was missing from the
package — the 2.0.3 installer contained a complete, internally consistent asset
set.

The header fix alone cannot repair a profile that is *already* poisoned: the
browser considers its cached copy fresh, so it never contacts the server and
never sees the new header. `desktop/electron/ui-cache.js` is what does that — it
drops the HTTP cache when the profile was last written by a different version,
before any window loads a URL.

**The version marker lives inside the Electron profile**, next to the cache it
describes, and that placement is the whole design. An earlier attempt keyed off
`installedVersion` in `desktop-state.json`, which lives under
`config.redforgeHome()`. For an installed build that sits inside the profile, so
it worked; for a **portable** build `redforgeHome()` is
`<portableDir>/RedForge-Data`, beside the executable, while the Chromium profile
stays in the per-user data directory. A freshly downloaded portable copy read
"no previous version — first run" and silently inherited the poisoned cache an
installed build had left behind. Keeping the marker with the cache makes
installed, portable and development builds answer the question identically,
because the two can never be separated.

A profile carrying a cache but no marker is treated as "written by an unknown
version" and cleared — which is exactly every 2.0.3 user, since the marker did
not exist before 2.0.4. The marker is written **only after** the clear succeeds,
so a failed invalidation is retried on the next launch instead of being
permanently forgotten. Only `clearCache()` is called: cookies, localStorage,
IndexedDB and the RedForge workspace are never touched.

## Missing assets must stay visible

The SPA catch-all returns `index.html` for client-side routes, but **never** for
a path whose extension names a build artefact (`.js`, `.css`, `.map`, images,
fonts — see `ASSET_SUFFIXES`). Serving HTML in place of a missing chunk turns a
packaging fault into an unrelated-looking MIME error deep inside the app. A
missing asset returns a 404 that says so.

## Gates

| gate | what it proves |
|---|---|
| `scripts/verify_frontend_assets.py <dir>` | every chunk referenced by `index.html` or by another chunk exists |
| `… <dir> --compare <other>` | two copies of the build are byte-identical — catches mixed builds |
| `scripts/smoke_packaged_app.py <bundle>` | the running backend serves all 55 chunks with the right status, MIME type and cache policy |
| `backend/tests/test_static.py` | the header and 404 contract, against a synthetic build |

CI runs the asset check after every frontend build; the release pipeline runs all
three, and the smoke test runs against the frozen binary before installers are
built.

## When you change the build

Nothing here needs updating for a normal route addition — a new `React.lazy`
route produces a new chunk and the gates pick it up automatically. Do revisit
this document if you change `vite.config.ts` (`base`, `assetsDir`,
`rollupOptions.output.*`), move where the frontend is staged, or add a target
that serves the UI from somewhere other than `static_serving.py`.
