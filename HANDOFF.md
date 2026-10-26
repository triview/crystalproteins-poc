# crystalproteins-poc — handoff

Read this first. It replaces re-reading any earlier chat.

## Current state (update every iteration)

- **Repo:** `~/Documents/triview/git/crystalproteins-poc` on the Mac; remote `git@github.com:triview/crystalproteins-poc.git`; all work on `develop`, `main` merged and pushed only by the owner.
- **What exists (from the 2026-10-26 chat session, report `docs/reports/01-poc-from-chat.md`):**
  - `ct2mesh.py`: DICOM CT (+ optional TotalSegmentator masks) → one closed mesh per artistic layer, block-fitted; STL per layer, OBJ, GLB, report.json, optional dot cloud (PLY/XYZ/DXF).
  - `recipes/chest_art.json`: the recipe format (layers from HU thresholds or structure-name globs; smoothing, Taubin, decimation, outer shell).
  - `viewer/`: browser previewer (glass / solid / dots, layer toggles, block size, Z/Y up, hole check, block-fitted STL export). `viewer/index.html` is the shell, `viewer/app.js` the app; `build_viewer.py` bundles three.js into one self-contained page.
  - `make_phantom.py`: synthetic chest CT + masks named like TotalSegmentator output, for tests.
  - Tests: 24 pipeline + 20 browser = 44, all green on 2026-10-26 (cloud container, Python 3.13).
  - The 24 pipeline tests also pass on Python 3.10 (the bridge's Linux VM); the 20 browser tests have not run on the Mac yet (iteration 1, step 0).
  - `dist/` (gitignored) already holds a built `viewer_standalone.html`: open it from Finder.
- **Deployed:** the viewer is published as a claude.ai artifact ("Crystal Etch Preview", shared by link). Version 3 (2026-10-26) bundles three.js into the page after a public viewer hung at "Loading sample model"; not yet confirmed fixed on her machine.
- **Not in the repo:** `samples/` (gitignored) holds the phantom STL and DICOM zip for manual testing.

## Open items (newest first)

- **Queued, not started:** DICOM zip import in the viewer (in-browser, scan never leaves the customer's machine) — `docs/backlog/dicom-zip-import.md`. Waits for the owner's go.
- **Iteration 1 is next:** `docs/prompts/iteration-1.md` (ingester restructure + viewer parity with the current crystalproteins.com previews).
- Confirm the artifact fix on her machine (hard reload; if it still fails, the page now prints the error — get a screenshot into `field/`).
- Her STL that failed to load: get the file (or its size/source app) into `field/inbox/` so it becomes a test case.
- Current previews on crystalproteins.com appear to be Sketchfab embeds (see `docs/reference/current-viewer.md`); confirm with the owner.
- No reviewer agents yet; `node scripts/agent-sync.mjs` reports "no agent-body blocks" until the first one is added.

## Where sessions run

- **Run locally on the Mac in Claude Code** — the VS Code extension, the terminal, or the Claude desktop app's Code tab set to *Local*. Claude runs natively on macOS: the repo, Python/Node toolchains, git with the owner's SSH keys; it can push. Use for code iterations and anything that builds or tests. (The Code tab's *Cloud* sessions run on Anthropic's servers on GitHub repos only.)
- **Run in a Claude app chat linked to the Mac** — Claude works in a Linux container in Anthropic's cloud and reaches the Mac through the desktop app: a shell in a small Linux VM that sees only the connected folders (not macOS: no brew, no Mac apps, no SSH keys — it commits, the owner pushes; it cannot write `.claude/`), file copies, and, if approved, screen control and the browsers. Use for research, reviews, the blog, looking at things. Over this bridge, ask for delete permission on the repo folder before any git work (git removes `.git/index.lock`).
- Either way, the hand-off is the files; nothing lives only in a chat.
- **Prompts per line:** one line of work so far, `iteration` → `docs/prompts/iteration-N.md`, reports `docs/reports/NN-title.md`.
- **Reviewer agents:** none yet. When added: `.claude/agents/<name>.md`, mirrored in `docs/KICKOFF-PROMPT.md`, kept identical by `scripts/agent-sync.mjs`.

## The loop (one iteration)

1. The owner uses the thing (the viewer, real customer-style files) and drops files, screenshots and notes into `field/YYYY-MM-DD/` (loose notes in the gitignored `field/inbox/`).
2. New session: paste the kickoff block from `docs/KICKOFF-PROMPT.md`, then the prompt ("Here's what happened: …").
3. Anything unclear is asked, not guessed.
4. The session builds, tests, writes the report, the JOURNAL entry, updates this file, commits on `develop`.

## Test tiers

- **Fast (every change):** `npm run test:fast` — pipeline tests (≈10 s).
- **Full (before handing over):** `npm install && python -m playwright install chromium && npm run build && npm test` — pipeline + headless-browser viewer tests (≈2 min).
- **Field (what only real use proves):** a real CT from a hospital CD, a real customer STL/OBJ/PDB, the viewer on the owner's and her machines, and a print from the etcher compared to the preview.

## Rules for any session

See `AGENTS.md`. Most often forgotten: identity per command, never `main`; tests until green; cite vendor/format facts; never commit customer data; end with report + JOURNAL + HANDOFF + commit.
