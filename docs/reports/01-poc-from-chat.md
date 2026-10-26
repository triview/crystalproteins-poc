# 01 — CT → mesh POC and glass viewer, built in a Claude app chat

2026-10-26. Built in the cloud container, then copied into this repo.

## What was asked

Turn a CT scan (DICOM) into something a subsurface laser can etch into a glass block. Over the session the target moved from a point cloud to **a mesh as the primary output** (the owner generates dots himself), with **existing segmentation software** integrated and **artistic** rather than clinical control. Then: a browser viewer, STL loading, test files, and this repo as a POC for **a replacement preview viewer and file ingester/processor** for crystalproteins.com.

## What was found

- Raw DICOM can't be pulled out of a server-side streaming viewer (Fujifilm Synapse Mobility streams rendered JPEGs, "no image dataset is downloaded on devices"); request the study from the hospital in DICOM. ([Synapse Mobility](https://www.christieinnomed.com/healthcare-it-solutions/entreprise-imaging-solutions/diagnostic-entreprise-viewer/fujifilm-synapse-mobility/))
- Crystal engravers place dots with a minimum-distance rule; too many dots crack or cloud the glass, too few look faint; DXF `POINT` entities are a common import format. ([Bourke](https://paulbourke.net/miscellaneous/crystalengraving/posterA3.pdf)) Some engraver software instead takes STL/OBJ and makes its own dots. ([Fab Academy](https://fabacademy.org/2024/labs/inphb/students/nda-koffi/assignments/week15/))
- TotalSegmentator: `pip install TotalSegmentator`; input a NIfTI or a folder/zip of DICOM slices; default output one mask per class, `--ml` one multilabel file; `--fast` runs a 3 mm model; most tasks open, some need a licence (free non-commercial); not a medical device. ([README via ecosyste.ms](https://awesome.ecosyste.ms/projects/1147580), [NIH Biowulf](https://hpc.nih.gov/apps/totalsegmentator.html)) In 3D Slicer: about a minute on CPU in fast mode, 40–50 min full resolution without a GPU. ([SlicerTotalSegmentator](https://github.com/lassoan/SlicerTotalSegmentator)) Class names checked against a published label map. ([label2index.json](https://huggingface.co/ianpan/total-classifier/blob/main/label2index.json))
- The current crystalproteins.com previews: see `docs/reference/current-viewer.md` (likely Sketchfab, not confirmed).

## What was built

| Piece | What it does |
|---|---|
| `ct2mesh.py` | DICOM series (sorted by position, HU rescale) and/or TotalSegmentator masks (folder or `--ml` + JSON, RAS→LPS) → per-layer masks (HU threshold inside a body mask that drops the scanner table, or structure globs) → gaussian smoothing → marching cubes → Taubin smoothing → quadric decimation → closed meshes, one uniform fit into the block. Exports STL per layer, OBJ (named objects), GLB (named nodes), `report.json`, optional dots (PLY/XYZ/DXF) with a hard minimum spacing. |
| `recipes/chest_art.json` | Example art recipe: ribcage, spine, heart+aorta, airway, outer skin, each with its own smoothing and triangle budget. |
| `viewer/` + `build_viewer.py` | Glass / solid / dots preview inside the block; layer toggles and per-layer dot density; block size and margin; Z/Y up axis; open-edge check; block-fitted STL (and dots) export as a zip; drag-drop, file picker, paste. Bundled into one self-contained page with the sample embedded. |
| `make_phantom.py` | Synthetic chest CT (DICOM, shuffled filenames, table under the patient) + ground-truth masks named like TotalSegmentator output. |

## What was tested

44 tests, all green (cloud container, Python 3.13, Chromium headless with SwiftShader):
- **Pipeline (24):** slice order from shuffled names, HU values, affine; series listing/selection; folder vs multilabel masks identical; masks registered to the CT (RAS↔LPS); glob matching; sphere ground truth (radius, volume, watertight) at isotropic and anisotropic spacing; Taubin keeps volume where Laplacian shrinks; decimation target; speck removal; table excluded; outer skin is one closed shell; recipe/layer parsing; end-to-end outputs, closed meshes inside the block, layers registered, GLB names, OBJ groups, label surface vs HU surface within 2 mm; dots spacing and counts; exact greedy spacing; missing-source errors.
- **Viewer (20):** sample loads cleanly; layer toggle; refit on block change; exported STLs closed and inside the block; dots mode spacing; budget search ±3 %; per-layer density; dots export; multiple STLs as layers; open mesh flagged; point-cloud PLY; bad file message; render not empty; phone width; embedded sample with the network blocked; Open STL button + ASCII STL; up-axis toggle; welder and hole count agree with trimesh; corrupt STL reported; runs with all external network blocked; no WebGL → a clear message.
- **Load times** (headless, software GL): 170 k triangles 5 s, 770 k 8 s, 3.1 M (150 MB STL) 50 s — a real GPU is much faster.

## Owed by the owner

- A hard reload of the viewer link on her machine and a screenshot (the page now prints any startup error).
- Her STL (or its size and the app that made it) in `field/inbox/`.
- A real CT (thin "Body" series) to run through TotalSegmentator + a recipe.
- The etcher's input format and dot spacing; who will use the ingester.

## Checklist for the next real-world use

1. `npm run build`, open `dist/viewer_standalone.html` straight from Finder; drop `samples/chest_phantom_50x50x80mm.stl`.
2. Unzip `samples/chest_phantom_dicom.zip`; `python ct2mesh.py --dicom dicom --seg seg --recipe recipes/chest_art.json -o out`; drop `out/model.glb` on the viewer.
3. Try her STL the same way; note size, load time, what the hole check says.
