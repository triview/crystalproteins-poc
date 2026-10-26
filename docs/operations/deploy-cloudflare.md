# Operations: deploying the viewer on Cloudflare

Status: **written 2026-10-26, not yet executed.** The first deploy needs the owner's Cloudflare login, so it
happens in a session with him; update this document with what actually happened (URLs, the account, any
step that differed) and mark it executed.

Facts below were checked against Cloudflare's docs on 2026-10-26 (sources at the end). Re-check limits and
dashboard paths if this is followed much later; Cloudflare moves menus.

## What gets deployed

| Part | Where it runs | Cloudflare product | Cost |
|---|---|---|---|
| Viewer (`dist/viewer_standalone.html`) | The visitor's browser | Worker with static assets only (no Worker script) | Free plan |
| Access control for the POC | Cloudflare's edge | Cloudflare Access (Zero Trust) | Free under 50 users |
| Ingester (`ct2mesh.py`) | **Not deployed.** See "The ingester" below | — | — |

The viewer is one self-contained page: three.js and the sample are inside it, and files people open are read
in their browser and never uploaded. So hosting is just serving one static file.

Limits that matter (Workers, free plan): 25 MiB per static file (the page is about 4.7 MB), 20,000 files per
version.

## One-time setup

1. **Cloudflare account.** Use the account that already holds the Zero Trust team (shared by the owner's other
   projects). Note the account name here after the first deploy: `…`.
2. **Wrangler login** on the Mac, from the repo:
   ```bash
   npx wrangler login          # opens a browser to authorise wrangler for the account
   ```
3. **Config file.** Add `wrangler.jsonc` to the repo root (committed; it holds no secrets):
   ```jsonc
   {
     "name": "crystalproteins-poc",
     "compatibility_date": "2026-10-26",   // the date of the first deploy
     "assets": {
       "directory": "./dist/site"
     }
   }
   ```
   No `main` and no `binding`: there is no Worker script, only static assets.
4. **Site folder.** The deploy serves `dist/site/`, whose `index.html` is the standalone viewer. Build it with:
   ```bash
   npm run build && mkdir -p dist/site && cp dist/viewer_standalone.html dist/site/index.html
   ```
   (Iteration work may fold this into `npm run build`; if so, update this line.)

## Deploy by hand

```bash
. .venv/bin/activate                 # Python + trimesh are needed by the build (sample conversion)
npm install
npm run build && mkdir -p dist/site && cp dist/viewer_standalone.html dist/site/index.html
npx wrangler deploy
```

Wrangler prints the URL, `https://crystalproteins-poc.<account-subdomain>.workers.dev`. Record it in
HANDOFF's current state.

## Deploy from GitHub automatically (Workers Builds)

Dashboard: **Workers & Pages** → the Worker → **Settings** → **Build** → connect `triview/crystalproteins-poc`.

- **Production branch:** `main`. Every push to `main` runs the build command, then the deploy command.
- **Preview builds for `develop`:** enable under **Settings → Build → Branch control**; every push to a
  non-production branch then makes a preview build.
- **Build command:**
  ```bash
  pip install -r requirements.txt && npm run build && mkdir -p dist/site && cp dist/viewer_standalone.html dist/site/index.html
  ```
  (`requirements.txt` also lists the test packages; a slimmer `requirements-build.txt` with just `trimesh`
  and `numpy` would speed this up.)
- **Deploy command:** `npx wrangler deploy`.
- **Python version:** the build image's default Python is newer than what the tests ran on. Pin the tested one
  with a build variable `PYTHON_VERSION=3.13` (Settings → Build → Build Variables and Secrets) or a
  `.python-version` file.

Remember the branch rule: only the owner merges and pushes `main`, so a push to `main` is a release.

## Keep the POC private (Cloudflare Access)

Dashboard: **Workers & Pages** → the Worker → **Settings** → **Domains & Routes** → for `workers.dev` (and for
Preview URLs) click **Enable Cloudflare Access**. Then **Manage Cloudflare Access** to set the allowed emails:
the owner and her. Login method: one-time PIN by email (no accounts needed).

Known limit: Cloudflare recommends that the Worker also validates the Access JWT
(`Cf-Access-Jwt-Assertion`). An assets-only Worker has no code to do that, so the protection is Access at the
edge alone. Fine for a POC with no customer data on the server (there is none: files stay in the browser);
revisit if a Worker script or uploads are ever added.

Before the viewer is used by customers (who open a link without an account), Access comes off the production
URL, or a separate public Worker is deployed. Decide that with the owner; don't remove Access on your own.

## Custom domain (optional)

A Worker Custom Domain needs a zone that is **active on Cloudflare and owned by this account**, and the hostname
must not already have a CNAME record. Cloudflare then creates the DNS record and the certificate.

- On triview.com: only if triview.com's DNS is on this Cloudflare account.
- On her domain (e.g. a `preview.` hostname under crystalproteins.com): only if that zone is moved to
  Cloudflare under an account we can use. Check where its DNS lives first; ask, don't assume.

Config, then `npx wrangler deploy`:
```jsonc
"routes": [ { "pattern": "preview.example.com", "custom_domain": true } ]
```

## Roll back

- Dashboard: **Workers & Pages** → the Worker → **Deployments** → ⋯ next to an earlier version → **Rollback**.
- CLI: `npx wrangler rollback` (pick from recent versions interactively, or pass a version ID).
- Only the 100 most recent versions are available. Confirm on the first rollback that the static page rolls
  back with the version (the docs don't say outright), and note the answer here.

## Check after every deploy

1. Open the URL in a private window: the Access login appears (if enabled), then the sample chest loads
   (about 170,000 triangles, no "Loading…" left on screen).
2. Drop `samples/chest_phantom_50x50x80mm.stl`: it loads as one closed layer.
3. Export: a zip downloads with the STLs and `settings.json`.
4. Record the deployed commit and URL in HANDOFF's current state.

## The ingester (not deployed)

`ct2mesh.py` cannot run in a normal Worker: 128 MB memory per isolate, CPU capped at 10 ms per request on
Free (up to 5 minutes on Paid), and request bodies capped at 100 MB on Free/Pro accounts. Two ways forward,
decision pending with the owner:

- **In the browser** (`docs/backlog/dicom-zip-import.md`): the scan is processed on the visitor's machine;
  Cloudflare keeps serving a static page; patient data never reaches a server. Recommended.
- **Cloudflare Containers**: the Python pipeline (TotalSegmentator included, on CPU) in a container, uploads
  going to storage first. Needs the Workers Paid plan ($5/month); e.g. a `standard-2` instance (1 vCPU,
  6 GiB) — the plan's included usage covers on the order of fifty 5-minute jobs a month, then per-use billing.
  Patient scans would pass through a server we run. Only if server-side segmentation is wanted.

## Sources

- Static assets, no-script config, `wrangler deploy`: https://developers.cloudflare.com/workers/static-assets/migrate-from-pages/
- Limits (asset size, files, memory, CPU, request body): https://developers.cloudflare.com/workers/platform/limits
- Workers Builds, production and preview branches: https://developers.cloudflare.com/workers/ci-cd/builds/build-branches/
- Build image (Python, pip, npm, version variables): https://developers.cloudflare.com/workers/ci-cd/builds/build-image
- One-click Access for Workers: https://developers.cloudflare.com/changelog/2025-10-03-one-click-access-for-workers
- Access free plan (under 50 users): https://www.cloudflare.com/en-gb/products/zero-trust/access
- Custom Domains: https://developers.cloudflare.com/workers/configuration/routing/custom-domains/
- Rollbacks: https://developers.cloudflare.com/workers/configuration/versions-and-deployments/rollbacks
- Containers pricing: https://developers.cloudflare.com/containers/pricing/
