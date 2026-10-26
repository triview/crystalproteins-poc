# crystalproteins-poc — Engineering Journal

Decisions, reversals, and traps. Newest entries first.

This file exists because the *reasoning* behind a decision is not reconstructable from the diff. Reports under `docs/reports/` hold the analysis; this file holds what was decided and why.

---

## 2026-10-26 (afternoon, 15:24) — block shapes, model placement and text scoped for iteration 2

**Asked by the owner:** "can you also add the ability to support / different block shapes / reorienting and resizing the 3d object / adding text/font/sizing, orientation, multiple lines, multiple blocks of text"

**Decided (owner):** plan it for a local session (not built in chat); all four shape families (her rectangular sizes, corner cube, round/curved, faceted); text flat or extruded, chosen per text block; curated open-licence fonts plus upload of her own.

**Decided (session, proposed):** one `design.json` (block, placement, layer, text_block — singular names) is the source of truth, exported with every file and readable by `ct2mesh.py --design`; shapes as signed distance functions so fitting works for non-box glass; iteration 1 models the block as a shape definition so iteration 2 slots in. Scope, tests and owner questions in `docs/design/block-placement-text.md`.

**Not verified:** shape catalogue dimensions (not guessed; owed by the owner/etcher); font licences (to verify per font).

**Owed by the owner:** the answers in section 6 of the design doc.

---

## 2026-10-26 (afternoon, 15:20) — Cloudflare deployment documented

**Asked by the owner:** "what would it take to deploy this on cloudflare?" … "please document the deployment in an operation document."

**Decided (session, proposed):** the viewer goes on Cloudflare as a Worker with static assets only, behind Cloudflare Access while it is a POC; the ingester is not deployed (Workers' memory/CPU/body limits); in-browser processing is the recommended path, Containers only if server-side segmentation is wanted. Written up in `docs/operations/deploy-cloudflare.md` with sources.

**Not verified:** nothing was deployed; whether static assets roll back with a Worker version; where crystalproteins.com's DNS lives.

**Owed by the owner:** a session with his Cloudflare login for the first deploy; which domain; when Access comes off for customers.

---

## 2026-10-26 (afternoon, 15:18) — viewer version 3 confirmed working

**Asked by the owner:** "is the link working now?" … "it looks like it's working. i can view and load the stl file that she sent to me"

**Decided:** the startup hang was the runtime CDN module import (or something it depended on); bundling three.js into the page fixed it. Keep the viewer self-contained (already in AGENTS.md).

**Not verified:** her own machine and browser; her STL in the Python ingester.

---

## 2026-10-26 (afternoon, later) — DICOM zip import queued, not built

**Asked by the owner:** "sounds like it might be easier for the app to accept a dicom zip file" … "that's fine. i'm still learning the process. let's push to later. leave the dicom.zip file processing a process to be completed"

**Decided (owner):** the viewer should eventually take a DICOM zip directly; not now.

**Decided (session, proposed and not objected to):** when it is built, the conversion runs in the browser (privacy, no upload limit, no server), density layers first, TotalSegmentator stays an external step, uncompressed DICOM first. Scope, checks and tests are in `docs/backlog/dicom-zip-import.md`.

**Built:** nothing; the backlog note, a HANDOFF open item and a line in iteration 1's "Not this iteration".

**Owed by the owner:** the go-ahead, and a real hospital disc to see which compression it uses.

---

## 2026-10-26 (afternoon) — repo bootstrapped; CT → mesh POC and viewer moved in from the chat

**Asked by the owner:**
- "is it possible to download the raw ct file from the viewer?" → "i'll just request dicom file. are there dicom to point cloud solutions?"
- "ultimate output is point cloud that can be used for glass cube etching", then "can you poc the entire thing with a sample dicom file?"
- "i think integration of an existing segmentation software would be beneficial / medical segmentation might be not optimal for artistic purposes"
- "also the primary output / a mesh and generate the point cloud myself"
- "also can you have this open stl files, too"
- "the error on her end is it's stuck at "loading sample model""
- "i've created git repository /Users/pedro/Documents/triview/git/crystalproteins-poc for this, can you apply the bootstrap skill to this directory and copy the code there. check the viewer on crystalproteins.com for a reference. this is a poc for a replacement view and file ingester/processor"
- "commit identity should be pedro@triview.com"

**Decided (owner):** mesh is the primary output, dots are the owner's job; integrate an existing segmenter rather than write one; the POC is a replacement viewer plus file ingester/processor for crystalproteins.com.

**Decided (session):**
- Segmentation = TotalSegmentator (open source, CPU-capable, NIfTI masks), consumed as its default folder output or `--ml` file. Medical labels only *select*; art lives in a recipe layer (grouping, smoothing, Taubin, decimation, outer shell).
- The viewer bundles three.js into the page (esbuild) instead of importing modules from a CDN, and shows startup errors on screen.
- Defaults taken because the owner had no preference: one line of work (`iteration`), no reviewer agents yet, blog drafts allowed (`draft: true`, owner publishes, no customer data), no product lens.

**Built:** `ct2mesh.py`, `recipes/chest_art.json`, `viewer/` (+ `build_viewer.py`), `make_phantom.py`, 44 tests, the handoff scaffolding.

**Trap:**
- A public viewer of the artifact sat on "Loading sample model" with 0 triangles: the module script never ran (CDN ES-module imports and/or WebGL). Bundled now; the page also prints the reason if it ever fails again.
- Artifact hosting does not serve `.glb` (nor `.zip`/`.stl` downloads): the sample ships as base64 JSON inside the page; exports are offered as a zip through the downloads capability.
- Viewer dot-share slider first used random keep fractions, which did nothing once spacing was the limit; it now scales each layer's own spacing (share 0.25 → about a quarter of the dots).
- Over the bridge, `crystalproteins.com` and `claude.ai` are blocked for the built-in browser and the container's network; the site's viewer was studied through WebFetch text only.

**Not verified:**
- That version 3 of the artifact loads on her machine.
- That the current previews are Sketchfab embeds (inferred from 32-hex model IDs on the preview pages and the public Sketchfab account "Crystal Proteins (@bathsheba)").
- TotalSegmentator on a real scan (not runnable in the chat container).
- Why her STL failed: almost certainly the same startup hang, but her file has not been tested.

**Owed by the owner:** her STL (or its size and source app); a real CT; the etcher's input format and dot spacing; whether customers or she will use the ingester; a screenshot from her machine after a hard reload.
