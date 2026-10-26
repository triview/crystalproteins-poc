# Backlog: DICOM zip import in the viewer

Status: **queued, not started** (decided 2026-10-26; the owner: "let's push to later. leave the dicom.zip file processing a process to be completed").
Pick it up in an iteration after the owner says so; copy the scope below into that iteration's prompt.

## Why

A zip is one file a customer can hand over without understanding a hospital CD. Doing the conversion
in the browser keeps the scan on the customer's own machine (medical data never uploaded), avoids the
site's 20 MB upload limit (a CT zip is often hundreds of MB), and keeps the viewer a single page with no server.

## Scope agreed so far

1. Drop or choose a `.zip` in the viewer → unzip in the page → find the DICOM slices (any folder depth, ignore DICOMDIR and viewer software on the disc) → pick the largest series (offer a choice when there are several) → sort by position along the slice normal, apply rescale slope/intercept → HU volume.
2. Resample to about 1.5 mm for meshing (enough for a 50–80 mm block, where 1 mm of glass is about 4–8 mm of patient).
3. Layers from density only: bone, outer skin (cavities filled), lungs/airway; the same artistic controls as the recipe (smoothing, outer shell, speck removal); body mask so the scanner table never shows.
4. If the zip also holds TotalSegmentator masks (`seg/` folder or `--ml` file + JSON), offer them as label layers.
5. Uncompressed DICOM first (the test zip is Explicit VR Little Endian). Compressed discs (JPEG / JPEG 2000) get a clear message until decoders are added; collect real discs first to see what they use.
6. Same output as the Python pipeline: named, block-fitted, closed meshes the existing viewer and STL export already handle.

## Verify before building

- Licences and sizes of the libraries to bundle (zip reader, DICOM parser, optional codecs) — cite them.
- Which transfer syntaxes real hospital discs use (from the owner's own disc and any others).
- Memory and time on a full-resolution CT in Safari and Chrome on the Mac.

## Tests it needs

- The phantom zip (`samples/chest_phantom_dicom.zip`, or `make_phantom.py` + zip in the test) loads to the same layers as `ct2mesh.py` within a tolerance (surface distance), table excluded.
- Shuffled filenames, nested folders, a DICOMDIR, two series in one zip, a compressed slice (clear error), a zip with no DICOM.

## Not part of it

TotalSegmentator running in the browser; uploading scans to a server (a possible later "premium" path).
