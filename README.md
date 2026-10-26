# crystalproteins-poc

Proof of concept for two things behind laser-etched glass (crystalproteins.com):

1. **A file ingester/processor.** Customer data goes in and clean, closed, block-fitted meshes come out, one per artistic layer. Today it handles CT (DICOM) plus TotalSegmentator masks. Mesh files, image stacks and proteins come next (`docs/prompts/iteration-1.md`).
2. **A replacement 3D preview.** A self-contained browser page that shows the model inside the glass block, as glass, solid or a rough dot preview, with block-fitted STL export.

The mesh is the product. Engraving dots are generated with the owner's own tooling.

Working on this repo with Claude: start at `HANDOFF.md`.

## Setup (Mac)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium     # browser tests
npm install                               # three.js + esbuild for the viewer build
npm run build                             # -> dist/viewer_standalone.html, dist/artifact.html
npm test                                  # pipeline + viewer tests
```

## CT → meshes

```bash
python ct2mesh.py --dicom /path/to/CD --list                 # pick the thin "Body" series
TotalSegmentator -i /path/to/series_folder -o seg/           # optional; --fast is ~1 min on CPU
python ct2mesh.py --seg seg/ --list-structures
python ct2mesh.py --dicom /path/to/series_folder --series 3 --seg seg/ \
    --recipe recipes/chest_art.json --block 50x50x80 --margin 4 -o out/
```

Without segmentation, Hounsfield thresholds alone:

```bash
python ct2mesh.py --dicom study/ --layer bone:hu=250 --layer skin:hu=-400:outer=1:smooth=4 -o out/
```

Outputs: `<layer>.stl` (closed), `model.obj` (named objects), `model.glb` (named nodes), `report.json`, and with `--points N` a preview dot cloud (`dots.ply/.xyz/.dxf`, minimum spacing enforced). Units are mm of glass. +X is the patient's left, +Y is posterior (away from the front face), +Z is up. The origin is the block centre.

### Recipes

Each layer is either `labels` (globs over segmentation structure names such as `rib_*` or `vertebrae_T*`) or `hu` (a threshold). Every layer also gets its own artistic controls:

| Key | Effect |
|---|---|
| `smooth_mm` | Blur before meshing: 0–1 keeps detail, 3–5 gives sculptural forms |
| `taubin` | Smoothing passes that don't shrink the shape |
| `faces` | Triangle budget after decimation |
| `outer` | (`hu` layers) Outer skin only, every cavity filled |
| `min_component_mm3`, `keep_largest` | Drop specks, or keep the N biggest pieces |
| `weight` | Share of dots in the optional preview cloud |

## Viewer

Open `dist/viewer_standalone.html` straight from Finder (everything is inside the page), then drop STL/GLB/OBJ/PLY files on it. Several STLs become layers. There is a Z/Y up-axis toggle, a hole check per layer, and export of block-fitted STLs (plus dots in dot mode) as a zip. Source: `viewer/index.html` (shell) and `viewer/app.js` (app). `build_viewer.py` bundles three.js into the page so nothing loads from a CDN at runtime.

## Test data

`python make_phantom.py sample/` writes a synthetic chest CT (`sample/dicom`) and masks named like TotalSegmentator output (`sample/seg`, `sample/seg_ml.nii.gz` + `.json`). `samples/` (gitignored) holds a ready-made chest STL and DICOM zip. Real customer files never go in git.
