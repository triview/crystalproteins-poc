# Design: block shapes, placing the model, and text

Status: **agreed scope, not started** (owner, 2026-10-26). Planned for a local Claude Code session: iteration 2,
unless the owner moves it ahead of iteration 1's ingester work.

The owner asked for: "different block shapes / reorienting and resizing the 3d object / adding
text/font/sizing, orientation, multiple lines, multiple blocks of text". Answers to the follow-up questions:
all four shape families; text either flat or extruded, chosen per text block; a curated set of fonts plus
upload of her own.

Today the viewer (`viewer/app.js`) only knows a rectangular block (W×D×H + margin) and always scales the model
to fill it, centred. Everything below replaces that with one **design** the viewer edits, the exports carry,
and the Python side can read back.

## 1. The design document (one source of truth)

A JSON document saved with every export (`design.json`, replacing today's `settings.json`) and loadable back
into the viewer. Singular names for every object, so paths read naturally (`block.shape`, `text_block.font`):

```jsonc
{
  "format": "crystal-design/1",
  "block":     { "shape": "rectangular", "size_mm": [50, 50, 80], "margin_mm": 4, "preset": "narrow" },
  "placement": { "rotation_deg": [0, 0, 0], "scale": 1.0, "offset_mm": [0, 0, 0], "fit": "auto" },
  "layer":     [ { "name": "ribcage", "shown": true, "dot_share": 1.0 } ],
  "text_block": [
    { "id": "t1", "text": "Line one\nLine two", "font": "builtin:…", "size_mm": 4, "line_spacing": 1.2,
      "align": "center", "style": "flat", "depth_mm": 0.0,
      "position_mm": [0, -20, -30], "rotation_deg": [90, 0, 0] }
  ]
}
```

## 2. Block shapes

Shape families, each a parametric definition (size in mm), drawn by the viewer and used for fitting:

| Family | Shapes | Notes |
|---|---|---|
| Rectangular | her sizes as presets (Cube 80, Block, Large Cube 100, Large Block, Brick, Tower, Grand Tower, Slab, Narrow, Keychain) + custom W×D×H | sizes in `docs/reference/current-viewer.md` (her quote page); confirm Block 65×65×85 vs 90 |
| Corner cube | a cube with one corner cut off (80 and 100 mm on her quote page) | **ask** the cut size, which corner, and how it stands (on the cut face or upright) |
| Round and curved | cylinder, sphere, dome, heart | **ask** the sizes and exact profiles the etcher actually stocks |
| Faceted | diamond, octagon, obelisk / award shapes | **ask** the sizes and facet geometry the etcher stocks |

Rules:
- Every shape has an **engravable interior**: the shape inset by the margin. Implement shapes as a signed
  distance function (inside < 0) plus a mesh for drawing; the inset is `sdf + margin`.
- **Fit** = the largest uniform scale (for the current rotation) at which every model vertex is inside the
  interior. For non-box shapes, solve it numerically (bisection on scale, checking vertices against the SDF),
  not by bounding boxes.
- Don't invent catalogue dimensions. Rectangular sizes come from her quote page; every other shape's sizes come
  from the owner or the etcher, recorded in a `shapes.json` with its source.
- The viewer draws the shape (edges + faint faces) and the dashed interior, as it does for the box today.

## 3. Placing the model: reorient and resize

- **Reorient:** 90° turns about X/Y/Z (buttons), free rotation with a gizmo (three.js `TransformControls`,
  shipped in three r160 `examples/jsm/controls/`), a "lay flat on the base" helper, and the Z/Y up toggle kept.
- **Resize:** uniform scale as a percentage of the largest fit (100 % = fills the interior), plus an exact size
  in mm for the longest side; "Fit" resets to 100 %.
- **Move:** drag in the gizmo or type the offset; "Centre" resets.
- Show live: model size in mm of glass, the patient/model mm per glass mm, and **a red warning plus the
  offending area highlighted** when any part leaves the interior or comes closer than the margin.
- All of it lives in `design.placement`; exports (STL/GLB, dots) are written with the placement applied.
- Python parity: `ct2mesh.py --design design.json` applies the same block, placement and text, so a design made
  in the viewer can be rebuilt from the source data.

## 4. Text

- **Multiple text blocks**, each with multiple lines (`\n`), add / duplicate / delete / reorder.
- Per block: font, size (cap height in mm of glass), line spacing, alignment (left/centre/right), position and
  rotation (gizmo or typed; quick choices "reads from the front / back / left / right / top"), and **style**:
  - **flat**: lettering in a plane inside the glass (a closed, very thin solid so mesh tools treat it as
    closed; thickness configurable, default to be agreed with the owner's dot generator);
  - **extruded**: letters with depth (`depth_mm`), optional bevel off by default.
- **Fonts:** a curated set of open-licence fonts bundled in the page (verify each licence — SIL Open Font
  Licence or similar — and record it in `fonts/LICENCES.md`), plus **upload of her own TTF/OTF** read in the
  browser. three r160 ships `TTFLoader` (uses `examples/jsm/libs/opentype.module.js`) and `TextGeometry`;
  an uploaded font is never sent anywhere and is saved in `design.json` only by name (re-upload needed to edit).
- Warnings: text outside the interior, text overlapping the model (closer than a set gap), text too small or
  strokes too thin to etch legibly (threshold from the owner/etcher, not guessed).
- Each text block exports as its own layer (`text-1`, `text-2` …) in STL/GLB and dots.

## 5. Tests it needs

- Shape SDFs: points known inside/outside for every shape; the inset interior is the shape shrunk by the margin.
- Fit: a model fitted into each shape touches the interior (within a tolerance) and never crosses it, for
  several rotations.
- Placement round-trip: viewer export → `design.json` → reload gives the same transform; `ct2mesh.py --design`
  produces the same vertex positions (within 1e-4 mm) as the viewer's export.
- Text: multi-line layout (line count, spacing), flat vs extruded thickness, every glyph mesh closed, upload of
  a generated TTF works, text-outside and text-overlap warnings fire.
- Browser tests (Playwright) for the UI paths; pipeline tests (pytest) for Python parity.

## 6. Ask the owner before building

1. Exact dimensions and geometry of the corner cube, round/curved and faceted pieces that are actually
   offered, and where they come from (her catalogue or the etcher's).
2. Does his dot generator fill volumes or sample surfaces? This sets how flat text is represented
   (thin solid vs single surface) and its default thickness.
3. Minimum legible text size and stroke width in the glass.
4. Which fonts she uses today for inscriptions (so the curated set includes them or close open-licence matches).
5. Whether customers may edit text and placement themselves, or only see her layout.
