# The current crystalproteins.com previews (what the POC replaces)

Researched 2026-10-26 from a Claude app chat. The site and claude.ai were blocked for the built-in browser and the container's network, so this comes from WebFetch's text extraction plus web search, not from the page source. Items marked *inferred* need confirming.

## What the site offers

- Laser-etched glass from 3D scientific data: proteins, small molecules, image stacks and other 3D data; light bases and inscriptions optional. Made with sculptor Bathsheba Grossman and the etcher Precision Crystal. ([home](https://crystalproteins.com/index.html))
- Order flow: describe the project on the quote page or email files → binding quote and ship date **with a 3D preview showing how the glass will look from all angles** → setup charge, then any quantity. ([home](https://crystalproteins.com/index.html))
- Inputs accepted ([quote](https://crystalproteins.com/quote.html)): a PDB code, an uploaded file or a link. For proteins a PyMOL session is ideal; PDB, MOL, CIF and ChimeraX files are accepted. Other 3D data in "just about any open format", e.g. OBJ, VRML, a CSV list of points. Uploads up to 20 MB; larger by email. DICOM, STL and image stacks are not mentioned on the quote page (the gallery does include an X-ray tomography stack).
- Styles offered for proteins: cartoon, wireframe, ball-and-stick, backbone, nucleic acid, molecular surface.

## Glass sizes (quote page, 2026-10-26)

| Name | mm | Name | mm |
|---|---|---|---|
| Cube | 80 | Brick | 60×80×120 |
| Block | 65×65×90 | Tower | 75×75×150 |
| Large Cube | 100 | Grand Tower | 100×100×200 |
| Large Block | 80×80×120 | Slab | 90×90×45 |
| Narrow | 50×50×80 | Keychain | 30×20×20 |
| Corner Cube | 80×80×80 (out of stock) | Large Corner Cube | 100×100×100 |

Light bases: square 90×90, rectangle 115×90, long 165×90, large square 115×115, giant 200×100 (wood, white LEDs).

Note: the gallery describes the radiolarian piece as a "65 x 65 x 85mm Block" while the quote page lists Block as 65×65×90 — ask which is current.

## The preview pages

- Gallery items link to per-piece previews, e.g. [preview-stylatractus.html](https://crystalproteins.com/gallery/preview-stylatractus.html), [preview-hemoglobin.html](https://crystalproteins.com/gallery/preview-hemoglobin.html), plus DNA, caffeine, rhinovirus, brain. ([gallery](https://crystalproteins.com/gallery/))
- Each preview shows six labels **FRONT, BACK, LEFT, RIGHT, TOP, BOTTOM** (face views of the block) and says it needs JavaScript.
- Where the viewer sits, the text contains a bare 32-hex id (e.g. `453c36b428334f1387ad71b7fa342cf1` on the radiolarian page, `1ff63361f126468d8db44d642ae42ac9` on hemoglobin).
- *Inferred:* these are **Sketchfab** model embeds driven by face-view buttons. Sketchfab model UIDs are 32-hex, and there is a public Sketchfab account "Crystal Proteins (@bathsheba)", Somerville MA, with 45 public models including a "Glass test (gudaba)". ([Sketchfab collection](https://sketchfab.com/bathsheba/collections/public-3b5c088a91ae4fb7aa405b985a01b9f8))

## What a replacement must at least match

1. Face views: FRONT / BACK / LEFT / RIGHT / TOP / BOTTOM (and free orbit).
2. The block drawn at the ordered size; the model placed as it will be etched.
3. Works for a customer opening a link, on any browser, without an account.
4. Loads from the files she already produces (meshes, PyMOL/PDB-derived geometry, CT/stack-derived surfaces).

What it can add: block-size presets from the quote page, glass/solid/dot looks, a light-base preview, open-edge warnings, the inscription's position, and a self-hosted page (no Sketchfab dependency).

## Open questions for the owner

- Confirm Sketchfab, and how a preview is produced today (which tool exports the model, how the "glass" look is set up).
- What the etcher (Precision Crystal) takes as input, and who turns meshes into dots today.
- Who will use the ingester: her, or customers uploading directly?
