# Iteration 1 — the field report to paste after the kickoff prompt

Run locally on the Mac in Claude Code. Paste `docs/KICKOFF-PROMPT.md`'s "Run locally" block first, then this, as one message. It may touch everything in the repo. Design: `docs/reference/current-viewer.md`. The hand-off so far: `docs/reports/01-poc-from-chat.md`, JOURNAL 2026-10-26.

---

Here's what happened since last time (2026-10-26 — a Claude app chat built the POC and bootstrapped this repo):

- `ct2mesh.py` turns a CT (and optional TotalSegmentator masks) into block-fitted meshes through a recipe; the viewer previews them in the glass block. 44 tests green in the cloud container (Python 3.13); not yet run on the Mac.
- The published viewer hung at "Loading sample model" for a public viewer (her screenshot: 0 triangles, first version of the page). Version 3 bundles three.js into the page and prints startup errors. Not yet confirmed on her machine.
- Her STL didn't load either (same hang, most likely); the file itself is untested.
- This is a POC for a replacement of the crystalproteins.com preview (apparently Sketchfab embeds with FRONT/BACK/LEFT/RIGHT/TOP/BOTTOM views) and for a file ingester/processor.
- [the owner: anything seen since — her result after a hard reload, her STL, a real CT, answers to the questions below] …

**Iteration 1: make it run on the Mac, then shape it into an ingester + a preview that can replace the current one.** Scope, in order:

0. **Run what exists first.** `python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && python -m playwright install chromium && npm install && npm run build && npm test`. Fix anything macOS-specific (Python version, paths, esbuild binary). Record the counts.
1. **Verify before building**, and cite in the report:
   - Sketchfab: is that what the current preview pages use, and how the face-view buttons work (Viewer API) — so the replacement matches behaviour, not guesses.
   - TotalSegmentator's licence for the `total` task in commercial use, and its current class names (the tests rely on `rib_left_1`, `vertebrae_T5`, `lung_upper_lobe_left`, `heart`, `aorta`, `sternum`, `trachea`, `spinal_cord`).
   - Libraries for the next inputs: OBJ/VRML/PLY/STL readers (trimesh), PDB/mmCIF (e.g. gemmi or Biopython: licence, surface generation), TIFF image stacks (tifffile).
2. **Ingester as a package.** Move `ct2mesh.py` into a package (e.g. `crystal/` with `ingest/`, `mesh/`, `fit/`, `export/`), one entry point `crystal ingest <file-or-folder> --recipe … --block <preset|WxDxH>`. A format registry decides by content, not extension: mesh files (STL ASCII/binary, OBJ, PLY, GLB, VRML), DICOM folders/zips, NIfTI masks, TIFF stacks, CSV point lists. Every input ends as the same thing: named layers of closed meshes in block millimetres + `report.json`. Tests per format with generated files (no customer data). Keep `ct2mesh.py`'s CLI working as a thin wrapper until the owner says otherwise.
3. **Block presets** from the quote page (`docs/reference/current-viewer.md`), by name (`--block cube`, `narrow`, `tower` …) in the CLI and as a picker in the viewer. Ask which Block size is current (65×65×85 vs 65×65×90).
4. **Viewer parity with the current previews:** FRONT / BACK / LEFT / RIGHT / TOP / BOTTOM views (replace the current Front/Side/Top/3-4 set, keep free orbit), the block at the preset size, and a link-friendly mode that opens straight into a given model with no editing panel (for customers). Keep it self-contained (bundled three.js), and keep the startup error display.
5. **Her STL** (if the owner has put it in `field/inbox/`): load it in the viewer and the ingester; turn whatever breaks into a test with a generated file of the same shape (size, ASCII/binary, units). Never commit the file.

**Not this iteration:** protein styles (cartoon, ball-and-stick…), dot generation beyond the preview, hosting on crystalproteins.com, ordering or billing, TotalSegmentator inside the app (it stays an external step).

**Ask the owner first:** who uses the ingester (her or customers); what the etcher takes as input; whether previews must keep working inside Sketchfab during the transition; which Block size is current.

**Wrap up, and queue the next one:** the report `docs/reports/02-…`, JOURNAL, HANDOFF, a blog draft if worth telling, the next prompt `docs/prompts/iteration-2.md` in this same shape, commits on `develop` (the owner merges and pushes).

Tell me at the top of your first reply what you need from me. End with the test counts, the report path and the block to paste for iteration 2.
