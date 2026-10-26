# Kickoff prompt for a crystalproteins-poc session

Paste one of these as the first message of a new session, then the field report (the current `docs/prompts/iteration-N.md`).

## Run locally on the Mac in Claude Code — VS Code extension, or the Claude desktop app's Code tab set to Local (iteration)

---

You're working on crystalproteins-poc, a proof of concept for a replacement 3D preview viewer and a file ingester/processor for laser-etched glass (crystalproteins.com). The repo is `~/Documents/triview/git/crystalproteins-poc`.

Before anything else, read `HANDOFF.md`, the top entry of `JOURNAL.md`, and `AGENTS.md`. They replace any earlier chat.

Then do the next thing, on `develop`:
- Tests for all new code; run them until green (`npm run test:fast` while working, `npm run build && npm test` before handing over).
- Verify vendor, format and library facts by web search and cite them; never guess.
- Singular names for schema objects. Never commit customer data. The mesh is the product; dots are the owner's job. Keep the viewer self-contained (no runtime CDN imports).
- Commit as you go with `git -c user.name="Pedro Morales" -c user.email="pedro@triview.com" commit …`. Never touch `main`.
- Checkpoint work in progress: a commit plus an "iteration N in progress" block at the top of HANDOFF's open items, so a session cut off by a usage limit loses nothing.
- End with the report in `docs/reports/`, a JOURNAL entry, HANDOFF's current state and open items, a blog draft if there's something worth telling, the next prompt `docs/prompts/iteration-(N+1).md`, and a commit.
- Ask before guessing at customer flow, file taxonomy, sharing rules or UI.

Tell me at the top of your first reply what you need from me.

Here's what happened since last time: …

---

## Run in a Claude app chat linked to the Mac — the Claude desktop app, web or phone, with the repo folder connected (research, review, blog)

---

You're working on crystalproteins-poc, a proof of concept for a replacement 3D preview viewer and a file ingester/processor for laser-etched glass (crystalproteins.com). The repo is `/Users/pedro/Documents/triview/git/crystalproteins-poc` on my Mac.

First request access to that folder and delete permission on it (git needs to remove its lock files). Then read `HANDOFF.md`, the top entry of `JOURNAL.md`, and `AGENTS.md`. They replace any earlier chat.

This session is for research, review or the blog:
- Findings go in a report under `docs/reports/` (or a review under `docs/reviews/`), with sources cited; vendor facts verified by web search.
- Code changes are not made here: they go to the next code session as `docs/prompts/iteration-N.md`, in the shape of the existing prompts. Point HANDOFF at it and give me the block to paste.
- Never commit customer data. Commit what you write with `git -c user.name="Pedro Morales" -c user.email="pedro@triview.com" commit …` on `develop`; I push.
- Ask before guessing at customer flow, file taxonomy, sharing rules or UI.

Tell me at the top of your first reply what you need from me.

Here's what happened since last time: …

---

<!-- Reviewer agents go below, one section each: "## The <reviewer> review — run …", who the reviewer is,
     how to run it, a short "Here's what happened" pointing at the current prompt's review step, then:
     an agent-body mirror block (agent-body comment with the agent's name, the brief, closing comment),
     kept in sync with .claude/agents/<name>.md by scripts/agent-sync.mjs. None yet. -->
