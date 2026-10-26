# crystalproteins-poc — for Claude Code sessions

Proof of concept for a replacement 3D preview viewer and a file ingester/processor for laser-etched glass (crystalproteins.com): customer data in (meshes, CT/DICOM, segmentations, later proteins and image stacks), clean block-fitted meshes and a glass preview out.

Read `HANDOFF.md` first, then the top entry of `JOURNAL.md`, then `AGENTS.md` (the rules). `docs/KICKOFF-PROMPT.md` is the prompt the owner pastes to start a session; `docs/prompts/` holds the next session's field report for each line of work.

Non-negotiables, repeated here so they are never missed: branch `develop`; git identity per command (`-c user.name="Pedro Morales" -c user.email="pedro@triview.com"`), never written to config; tests for all new code, run until green before handing over; vendor and format facts verified by web search and cited, never guessed; singular names for every schema object (`layer.name`, not `layers.name`); customer files are confidential: never commit real customer data (keep it under the gitignored `samples/` or `field/inbox/`); the mesh is the primary product, the owner generates engraving dots himself.
