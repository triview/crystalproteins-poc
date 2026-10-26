#!/usr/bin/env python3
"""
ct2mesh — CT DICOM (+ optional TotalSegmentator masks) -> artistic, crystal-ready meshes.

The output is a set of clean meshes, one per *layer* you define, already scaled and centred for
a glass/crystal block and registered to each other. Generating the engraving point cloud from
them is left to you (an optional --points stage is included for previews).

Layers come from either source and can be mixed in one recipe:
  hu      a Hounsfield iso-value on the DICOM volume       (bone ~250, skin/air boundary ~-400)
  labels  glob patterns over segmentation structure names (rib_*, vertebrae_T*, heart, ...)

Artistic controls per layer (these are what make it sculpture rather than radiology):
  smooth_mm   gaussian blur of the mask/field before meshing — rounds off voxel steps and noise
  taubin      Taubin smoothing passes on the mesh — smooths without shrinking
  faces       target triangle count after decimation
  outer       (hu layers) keep only the outer skin, fill every cavity inside it
  min_component_mm3 / keep_largest   drop specks or keep just the N biggest pieces

Pipeline
  0 load      DICOM series -> HU volume + voxel->LPS affine; NIfTI masks -> LPS affine
  1 select    per layer: HU threshold (inside the body mask, so the scanner table never appears)
              or the union of the matched structure masks; drop small pieces; crop
  2 mesh      gaussian smooth -> marching cubes -> patient-space mesh (mm, LPS)
  3 refine    merge/clean -> Taubin smoothing -> quadric decimation -> fix normals / fill holes
  4 fit       one uniform scale + translation for all layers into the block minus margin
  5 export    per-layer STL, combined OBJ (named groups), GLB (named nodes), report.json,
              optional dot cloud (PLY/XYZ/DXF) via --points

Block coordinates: millimetres, +X = patient left, +Y = posterior (away from the front face),
+Z = superior (up). Origin at the block centre, or its min corner with --origin corner.

Examples
  python ct2mesh.py --dicom study/ --layer bone:hu=250 --layer skin:hu=-400:outer=1 -o out
  python ct2mesh.py --dicom study/ --seg seg/ --recipe recipes/chest_art.json -o out
  python ct2mesh.py --seg seg_ml.nii.gz --seg-names seg_ml.json --layer heart:labels=heart -o out
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import struct
import sys
import time
from dataclasses import dataclass, field, asdict, fields

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree
from skimage import measure

try:
    import pydicom
except ImportError:  # pragma: no cover
    pydicom = None

RAS_TO_LPS = np.diag([-1.0, -1.0, 1.0, 1.0])


# =========================================================================== stage 0: load

@dataclass
class Volume:
    """A 3-D array stored (k, j, i) = (slice, row, col) and a 4x4 affine mapping voxel
    (i, j, k, 1) to patient LPS millimetres."""
    data: np.ndarray
    affine: np.ndarray
    description: str = ""

    @property
    def spacing_kji(self):
        return tuple(float(np.linalg.norm(self.affine[:3, c])) for c in (2, 1, 0))

    def kji_to_lps(self, kji: np.ndarray) -> np.ndarray:
        ijk1 = np.c_[kji[:, 2], kji[:, 1], kji[:, 0], np.ones(len(kji))]
        return (ijk1 @ self.affine.T)[:, :3]


def _read_headers(folder: str):
    if pydicom is None:
        sys.exit("pydicom is required: pip install pydicom")
    groups: dict[str, list] = {}
    for root, _, files in os.walk(folder):
        for f in files:
            p = os.path.join(root, f)
            try:
                ds = pydicom.dcmread(p, stop_before_pixels=True)
            except Exception:
                continue  # DICOMDIR, readme, viewer binaries on a CD ...
            if not hasattr(ds, "ImagePositionPatient") or not hasattr(ds, "PixelSpacing"):
                continue
            groups.setdefault(str(ds.SeriesInstanceUID), []).append((p, ds))
    return groups


def list_series(folder: str) -> list[dict]:
    out = []
    for uid, items in _read_headers(folder).items():
        ds = items[0][1]
        out.append({"uid": uid, "number": int(getattr(ds, "SeriesNumber", -1) or -1),
                    "description": str(getattr(ds, "SeriesDescription", "")), "slices": len(items),
                    "rows": int(ds.Rows), "cols": int(ds.Columns),
                    "slice_thickness": float(getattr(ds, "SliceThickness", 0) or 0)})
    return sorted(out, key=lambda s: s["number"])


def load_dicom(folder: str, select: str | None = None) -> Volume:
    """Load one series as HU. `select` = series number, UID or description substring;
    default = the series with the most slices."""
    groups = _read_headers(folder)
    if not groups:
        raise ValueError(f"no image DICOM files with geometry under {folder}")
    if select is None:
        uid = max(groups, key=lambda u: len(groups[u]))
    else:
        cand = [u for u, it in groups.items()
                if u == select or str(getattr(it[0][1], "SeriesNumber", "")) == select
                or select.lower() in str(getattr(it[0][1], "SeriesDescription", "")).lower()]
        if not cand:
            raise ValueError(f"no series matches {select!r}; run with --list")
        uid = max(cand, key=lambda u: len(groups[u]))
    items = groups[uid]
    ds0 = items[0][1]
    iop = np.array(ds0.ImageOrientationPatient, dtype=float)
    row_dir, col_dir = iop[:3], iop[3:]
    normal = np.cross(row_dir, col_dir)
    # order by position along the slice normal; never trust filenames or InstanceNumber
    items.sort(key=lambda t: float(np.dot(np.array(t[1].ImagePositionPatient, float), normal)))
    pos = np.array([np.dot(np.array(d.ImagePositionPatient, float), normal) for _, d in items])
    keep = np.concatenate([[True], np.diff(pos) > 1e-3])          # drop duplicate positions
    items, pos = [it for it, k in zip(items, keep) if k], pos[keep]
    if len(items) < 2:
        raise ValueError("series has fewer than 2 slices; need a volume")
    gaps = np.diff(pos)
    dk = float(np.median(gaps))
    if np.max(np.abs(gaps - dk)) > 0.1 * dk:
        print(f"warning: uneven slice spacing {gaps.min():.2f}-{gaps.max():.2f} mm, using median {dk:.2f}",
              file=sys.stderr)
    dj, di = (float(v) for v in ds0.PixelSpacing)        # [row spacing, column spacing]
    slices = []
    for p, _ in items:
        ds = pydicom.dcmread(p)
        try:
            arr = ds.pixel_array.astype(np.float32)
        except Exception as e:
            raise RuntimeError(f"cannot decode pixels in {p} ({ds.file_meta.TransferSyntaxUID.name}); "
                               "pip install pylibjpeg pylibjpeg-libjpeg pylibjpeg-openjpeg") from e
        slices.append(arr * float(getattr(ds, "RescaleSlope", 1) or 1)
                      + float(getattr(ds, "RescaleIntercept", 0) or 0))
    A = np.eye(4)
    A[:3, 0], A[:3, 1], A[:3, 2] = row_dir * di, col_dir * dj, normal * dk
    A[:3, 3] = np.array(items[0][1].ImagePositionPatient, dtype=float)
    return Volume(np.stack(slices).astype(np.float32), A, str(getattr(ds0, "SeriesDescription", "")))


class Segmentation:
    """TotalSegmentator output in either form:
       a folder of <structure>.nii(.gz) binary masks (default output), or
       one multilabel .nii(.gz) (--ml output) plus a {id: name} JSON.
    Masks from 3D Slicer exports work the same way."""

    def __init__(self, path: str, names_json: str | None = None):
        import nibabel as nib
        self._nib = nib
        self.path = path
        self.files: dict[str, str] = {}
        self.ml = None
        self.ml_names: dict[int, str] = {}
        if os.path.isdir(path):
            for f in sorted(os.listdir(path)):
                if f.endswith(".nii.gz") or f.endswith(".nii"):
                    self.files[f[:-7] if f.endswith(".nii.gz") else f[:-4]] = os.path.join(path, f)
            if not self.files:
                raise ValueError(f"no .nii/.nii.gz masks in {path}")
            ref = nib.load(next(iter(self.files.values())))
        else:
            ref = nib.load(path)
            if names_json is None:
                stem = path[:-7] if path.endswith(".nii.gz") else os.path.splitext(path)[0]
                names_json = stem + ".json" if os.path.exists(stem + ".json") else None
            if names_json:
                with open(names_json) as f:
                    self.ml_names = {int(k): v for k, v in json.load(f).items()}
            else:
                ids = np.unique(np.asarray(ref.dataobj)).astype(int)
                self.ml_names = {int(i): f"label_{int(i)}" for i in ids if i}
        self.shape_ijk = ref.shape[:3]
        self.affine = RAS_TO_LPS @ ref.affine        # voxel (i,j,k) -> LPS

    @property
    def names(self) -> list[str]:
        return sorted(self.files) if self.files else [self.ml_names[k] for k in sorted(self.ml_names)]

    def match(self, patterns: list[str]) -> list[str]:
        hit = [n for n in self.names if any(fnmatch.fnmatchcase(n, p) for p in patterns)]
        if not hit:
            raise ValueError(f"no structures match {patterns}. Available: {', '.join(self.names[:60])}"
                             + (" ..." if len(self.names) > 60 else ""))
        return hit

    def mask(self, patterns: list[str]) -> tuple[np.ndarray, list[str]]:
        """Union of all matched structures, as bool (k, j, i)."""
        names = self.match(patterns)
        if self.files:
            m = np.zeros(self.shape_ijk, dtype=bool)
            for n in names:
                img = self._nib.load(self.files[n])
                if img.shape[:3] != self.shape_ijk or not np.allclose(RAS_TO_LPS @ img.affine, self.affine, atol=1e-3):
                    raise ValueError(f"mask {n} is on a different grid than the others")
                m |= np.asarray(img.dataobj) > 0
        else:
            if self.ml is None:
                self.ml = np.asarray(self._nib.load(self.path).dataobj).astype(np.int32)
            ids = [k for k, v in self.ml_names.items() if v in names]
            m = np.isin(self.ml, ids)
        return np.ascontiguousarray(m.transpose(2, 1, 0)), names

    def volume(self, m_kji: np.ndarray) -> Volume:
        return Volume(m_kji, self.affine)


# =========================================================================== stage 1: select

def body_mask(hu: np.ndarray, air_hu: float = -500.0, dilate: int = 2) -> np.ndarray:
    """Largest air-separated object (the patient) with holes filled per slice.
    Excludes the scanner table, pads and cables."""
    m = hu > air_hu
    lab, n = ndimage.label(m)
    if n == 0:
        return np.zeros_like(m)
    sizes = ndimage.sum_labels(m, lab, index=np.arange(1, n + 1))
    m = lab == (1 + int(np.argmax(sizes)))
    for k in range(m.shape[0]):
        m[k] = ndimage.binary_fill_holes(m[k])
    return ndimage.binary_dilation(m, iterations=dilate) if dilate else m


def clean_mask(m: np.ndarray, spacing_kji, min_component_mm3: float = 0.0,
               keep_largest: int | None = None) -> np.ndarray:
    lab, n = ndimage.label(m)
    if n == 0:
        return m
    sizes = ndimage.sum_labels(m, lab, index=np.arange(1, n + 1)) * float(np.prod(spacing_kji))
    keep = sizes >= min_component_mm3
    if keep_largest:
        order = np.argsort(-sizes)
        top = np.zeros(n, dtype=bool)
        top[order[:keep_largest]] = True
        keep &= top
    lut = np.concatenate([[False], keep])
    return lut[lab]


def _bbox_crop(m: np.ndarray, pad: int):
    idx = np.argwhere(m)
    if len(idx) == 0:
        return None
    lo = np.maximum(idx.min(0) - pad, 0)
    hi = np.minimum(idx.max(0) + pad + 1, m.shape)
    return tuple(slice(a, b) for a, b in zip(lo, hi)), lo


# =========================================================================== stage 2: mesh

def _sigma_vox(smooth_mm: float, spacing_kji):
    return tuple(smooth_mm / s for s in spacing_kji) if smooth_mm > 0 else None


def field_to_mesh(fld: np.ndarray, level: float, vol: Volume, offset_kji=(0, 0, 0), fill=-1024.0):
    """Marching cubes on a (cropped) field; returns (verts LPS, faces). Pads so surfaces close."""
    if not (fld.min() < level < fld.max()):
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    padded = np.pad(fld, 1, constant_values=fill)
    v, f, _, _ = measure.marching_cubes(padded, level=level, allow_degenerate=False)
    v = v - 1.0 + np.asarray(offset_kji, float)
    return vol.kji_to_lps(v), f.astype(np.int64)


def mask_to_mesh(m: np.ndarray, vol: Volume, smooth_mm: float = 1.0):
    """Binary mask (k,j,i) -> smooth surface. Blurs the mask then takes the 0.5 iso-surface."""
    sig = _sigma_vox(smooth_mm, vol.spacing_kji)
    pad = int(np.ceil(3 * max(sig))) + 2 if sig else 2
    c = _bbox_crop(m, pad)
    if c is None:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    sl, lo = c
    f = m[sl].astype(np.float32)
    if sig:
        f = ndimage.gaussian_filter(f, sig)
    return field_to_mesh(f, 0.5, vol, lo, fill=0.0)


def hu_to_mesh(vol: Volume, iso: float, body: np.ndarray, smooth_mm: float, min_component_mm3: float,
               keep_largest: int | None, outer: bool):
    """HU iso-surface inside the body. outer=True -> only the outer shell (cavities filled)."""
    above = (vol.data > iso) & body
    above = clean_mask(above, vol.spacing_kji, min_component_mm3, keep_largest)
    if outer:
        filled = ndimage.binary_fill_holes(above)
        for k in range(filled.shape[0]):       # also close cavities open at the volume's top/bottom
            filled[k] = ndimage.binary_fill_holes(filled[k])
        return mask_to_mesh(filled, vol, smooth_mm)
    sig = _sigma_vox(smooth_mm, vol.spacing_kji)
    pad = int(np.ceil(3 * max(sig))) + 2 if sig else 2
    c = _bbox_crop(above, pad)
    if c is None:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    sl, lo = c
    fld = vol.data[sl]
    if sig:
        fld = ndimage.gaussian_filter(fld, sig)
    # suppress everything that was not kept (outside body, removed specks) so it makes no surface
    keep_zone = ndimage.binary_dilation(above[sl], iterations=2)
    fld = np.where(keep_zone, fld, -1024.0).astype(np.float32)
    return field_to_mesh(fld, iso, vol, lo)


# =========================================================================== stage 3: refine

def refine(verts, faces, taubin: int = 10, faces_target: int | None = None):
    """Clean, smooth (Taubin: no shrinkage), decimate, orient. Returns a trimesh.Trimesh."""
    import trimesh
    m = trimesh.Trimesh(verts, faces, process=True)
    m.update_faces(m.nondegenerate_faces())
    m.remove_unreferenced_vertices()
    if taubin > 0 and len(m.faces):
        trimesh.smoothing.filter_taubin(m, lamb=0.5, nu=0.53, iterations=int(taubin))
    if faces_target and len(m.faces) > faces_target:
        import fast_simplification
        reduction = 1.0 - faces_target / len(m.faces)
        v, f = fast_simplification.simplify(np.asarray(m.vertices, np.float32),
                                            np.asarray(m.faces, np.int32), target_reduction=reduction)
        m = trimesh.Trimesh(v.astype(np.float64), f, process=True)
        m.update_faces(m.nondegenerate_faces())
        m.remove_unreferenced_vertices()
    if not m.is_watertight:
        trimesh.repair.fill_holes(m)
    trimesh.repair.fix_normals(m)
    return m


# =========================================================================== stage 4: fit

def fit_transform(points: np.ndarray, block_mm, margin_mm: float):
    """Uniform scale + translation centring `points` in the block with margin on every side.
    glass = points * scale + offset."""
    lo, hi = points.min(0), points.max(0)
    extent = np.maximum(hi - lo, 1e-9)
    usable = np.asarray(block_mm, float) - 2 * margin_mm
    if np.any(usable <= 0):
        raise ValueError("margin too large for the block")
    scale = float(np.min(usable / extent))
    return scale, -(lo + hi) / 2 * scale


# =========================================================================== optional dots

def sample_surface(verts, faces, n: int, rng) -> np.ndarray:
    if len(faces) == 0 or n <= 0:
        return np.zeros((0, 3))
    a, b, c = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    tri = rng.choice(len(faces), size=n, p=area / area.sum())
    u, v = rng.random(n), rng.random(n)
    flip = u + v > 1
    u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
    return a[tri] + u[:, None] * (b[tri] - a[tri]) + v[:, None] * (c[tri] - a[tri])


def voxel_downsample(points: np.ndarray, voxel: float) -> np.ndarray:
    if len(points) == 0:
        return points
    keys = np.floor(points / voxel).astype(np.int64)
    _, inv, counts = np.unique(keys, axis=0, return_inverse=True, return_counts=True)
    inv = inv.ravel()
    return np.stack([np.bincount(inv, weights=points[:, d]) / counts for d in range(3)], 1)


def min_spacing_mask(points: np.ndarray, r: float) -> np.ndarray:
    """Greedy thinning keep-mask: earlier points win; no two kept points closer than r."""
    keep = np.ones(len(points), dtype=bool)
    if r <= 0 or len(points) < 2:
        return keep
    pairs = cKDTree(points).query_pairs(r, output_type="ndarray")
    if len(pairs) == 0:
        return keep
    order = np.lexsort((pairs[:, 0], pairs[:, 1]))
    pairs = pairs[order]                     # grouped by the later index j
    j_vals, starts = np.unique(pairs[:, 1], return_index=True)
    ends = np.r_[starts[1:], len(pairs)]
    for j, s, e in zip(j_vals, starts, ends):
        if keep[pairs[s:e, 0]].any():
            keep[j] = False
    return keep


def downsample_to_count(points, target: int, min_spacing: float = 0.0, tol: float = 0.03, iters: int = 40):
    """Voxel size search so ~target points survive downsampling *and* the min-spacing rule."""
    def reduce(vox):
        cur = voxel_downsample(points, vox)
        return cur[min_spacing_mask(cur, min_spacing)]
    if len(points) <= target:
        return points[min_spacing_mask(points, min_spacing)]
    ext = float(np.max(points.max(0) - points.min(0)))
    lo, hi = max(1e-4 * ext, min_spacing * 0.5), ext
    densest = reduce(lo)
    if len(densest) <= target:
        return densest
    best, best_err = densest, np.inf
    for _ in range(iters):
        mid = float(np.sqrt(lo * hi))
        cur = reduce(mid)
        err = abs(len(cur) - target) / target
        if err < best_err:
            best, best_err = cur, err
        if err <= tol or hi / lo < 1.0005:
            break
        lo, hi = (mid, hi) if len(cur) > target else (lo, mid)
    return best


def min_pairwise_distance(points: np.ndarray) -> float:
    if len(points) < 2:
        return float("inf")
    d, _ = cKDTree(points).query(points, k=2)
    return float(d[:, 1].min())


# =========================================================================== stage 5: export

def write_ply_points(path, points, layer=None, layer_names=None):
    hdr = ["ply", "format binary_little_endian 1.0", "comment ct2mesh", "comment units mm", "comment up +z"]
    hdr += [f"comment layer {i} {n}" for i, n in enumerate(layer_names or [])]
    hdr += [f"element vertex {len(points)}", "property float x", "property float y", "property float z"]
    if layer is not None:
        hdr.append("property uchar layer")
    hdr.append("end_header")
    rec = np.zeros(len(points), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4")]
                   + ([("l", "u1")] if layer is not None else []))
    rec["x"], rec["y"], rec["z"] = points[:, 0], points[:, 1], points[:, 2]
    if layer is not None:
        rec["l"] = layer
    with open(path, "wb") as f:
        f.write(("\n".join(hdr) + "\n").encode("ascii"))
        f.write(rec.tobytes())


def read_ply_points(path):
    with open(path, "rb") as f:
        n, props, fmt, inv = 0, [], "", False
        while True:
            line = f.readline().decode("ascii").strip()
            t = line.split()
            if t and t[0] == "format":
                fmt = t[1]
            elif t and t[0] == "element":
                inv = t[1] == "vertex"
                n = int(t[2]) if inv else n
            elif t and t[0] == "property" and inv:
                props.append((t[1], t[2]))
            elif line == "end_header":
                break
        assert fmt == "binary_little_endian", "reader handles the binary PLYs this tool writes"
        tmap = {"float": "<f4", "uchar": "u1", "double": "<f8"}
        dt = np.dtype([(nm, tmap[t]) for t, nm in props])
        rec = np.frombuffer(f.read(n * dt.itemsize), dtype=dt)
    pts = np.stack([rec["x"], rec["y"], rec["z"]], 1).astype(np.float64)
    return pts, (np.asarray(rec["layer"]) if "layer" in rec.dtype.names else None)


def write_dxf_points(path, points, layer=None, layer_names=None):
    with open(path, "w") as f:
        f.write("0\nSECTION\n2\nENTITIES\n")
        for k, (x, y, z) in enumerate(points):
            ln = layer_names[int(layer[k])] if (layer_names and layer is not None) else "0"
            f.write(f"0\nPOINT\n8\n{ln}\n10\n{x:.4f}\n20\n{y:.4f}\n30\n{z:.4f}\n")
        f.write("0\nENDSEC\n0\nEOF\n")


def write_obj(path, meshes: list[tuple[str, object]]):
    """One OBJ, one named object per layer (no materials)."""
    with open(path, "w") as f:
        f.write("# ct2mesh — units mm, +Z up\n")
        base = 1
        for name, m in meshes:
            f.write(f"o {name}\n")
            np.savetxt(f, m.vertices, fmt="v %.4f %.4f %.4f")
            np.savetxt(f, m.faces + base, fmt="f %d %d %d")
            base += len(m.vertices)


def write_glb(path, meshes: list[tuple[str, object]]):
    import trimesh
    scene = trimesh.Scene()
    for name, m in meshes:
        scene.add_geometry(m, node_name=name, geom_name=name)
    scene.export(path, file_type="glb")


# =========================================================================== orchestration

@dataclass
class LayerSpec:
    name: str
    hu: float | None = None
    labels: list | None = None
    outer: bool = False
    smooth_mm: float = 1.0
    taubin: int = 10
    faces: int | None = 60000
    min_component_mm3: float = 100.0
    keep_largest: int | None = None
    weight: float = 1.0          # share of dots in the optional --points stage

    def __post_init__(self):
        if (self.hu is None) == (self.labels is None):
            raise ValueError(f"layer {self.name!r}: give exactly one of hu= or labels=")
        if isinstance(self.labels, str):
            self.labels = [s for s in self.labels.split(",") if s]

    @staticmethod
    def parse(s: str) -> "LayerSpec":
        """NAME:key=val:key=val  e.g. ribs:labels=rib_*,sternum:smooth=1.5:faces=80000"""
        parts = s.split(":")
        kw = {"name": parts[0]}
        alias = {"smooth": "smooth_mm", "min_component": "min_component_mm3", "largest": "keep_largest"}
        valid = {f.name: f for f in fields(LayerSpec)}
        for p in parts[1:]:
            if "=" not in p:
                raise argparse.ArgumentTypeError(f"bad layer option {p!r} (want key=value)")
            k, v = p.split("=", 1)
            k = alias.get(k, k)
            if k not in valid:
                raise argparse.ArgumentTypeError(f"unknown layer option {k!r}")
            if k == "labels":
                kw[k] = v
            elif k == "outer":
                kw[k] = v.lower() in ("1", "true", "yes")
            elif k in ("taubin", "faces", "keep_largest"):
                kw[k] = int(float(v))
            else:
                kw[k] = float(v)
        return LayerSpec(**kw)


@dataclass
class Recipe:
    layers: list
    block_mm: tuple = (50.0, 50.0, 80.0)
    margin_mm: float = 4.0
    origin: str = "center"

    @staticmethod
    def load(path: str) -> "Recipe":
        with open(path) as f:
            d = json.load(f)
        layers = [LayerSpec(**L) for L in d.pop("layers")]
        if "block_mm" in d:
            d["block_mm"] = tuple(d["block_mm"])
        return Recipe(layers=layers, **d)


def build(recipe: Recipe, ct: Volume | None = None, seg: Segmentation | None = None, log=print):
    """Run stages 1-4. Returns {'meshes': [(name, trimesh)], 'scale': s, 'report': {...}}."""
    t0 = time.time()
    body = None
    raw = []
    for L in recipe.layers:
        t1 = time.time()
        if L.hu is not None:
            if ct is None:
                raise ValueError(f"layer {L.name!r} uses hu= but no --dicom was given")
            if body is None:
                body = body_mask(ct.data)
                log(f"[1] body mask: {body.mean()*100:.1f}% of volume (table and air excluded)")
            v, f = hu_to_mesh(ct, L.hu, body, L.smooth_mm, L.min_component_mm3, L.keep_largest, L.outer)
            source = {"hu": L.hu, "outer": L.outer}
        else:
            if seg is None:
                raise ValueError(f"layer {L.name!r} uses labels= but no --seg was given")
            m, names = seg.mask(L.labels)
            vol = seg.volume(m)
            m = clean_mask(m, vol.spacing_kji, L.min_component_mm3, L.keep_largest)
            v, f = mask_to_mesh(m, vol, L.smooth_mm)
            source = {"labels": L.labels, "structures": names}
        if len(f) == 0:
            log(f"[2] {L.name}: nothing to mesh — skipped")
            raw.append((L, None, source))
            continue
        mesh = refine(v, f, L.taubin, L.faces)
        log(f"[3] {L.name}: {len(f):,} -> {len(mesh.faces):,} triangles, "
            f"{'watertight' if mesh.is_watertight else 'OPEN'}, {mesh.body_count} piece(s)  ({time.time()-t1:.1f}s)")
        raw.append((L, mesh, source))

    meshes = [m for _, m, _ in raw if m is not None]
    if not meshes:
        raise ValueError("no layer produced a surface; check thresholds / label patterns")
    allv = np.vstack([m.vertices for m in meshes])
    scale, offset = fit_transform(allv, recipe.block_mm, recipe.margin_mm)
    shift = offset + (np.asarray(recipe.block_mm) / 2 if recipe.origin == "corner" else 0)
    log(f"[4] scale {scale:.4f}: 1 mm of glass = {1/scale:.2f} mm of patient")

    out, rep = [], []
    for L, m, source in raw:
        entry = {"name": L.name, "source": source,
                 "params": {k: v for k, v in asdict(L).items() if k not in ("name", "hu", "labels")}}
        if m is None:
            entry["skipped"] = True
            rep.append(entry)
            continue
        m = m.copy()
        m.apply_scale(scale)
        m.apply_translation(shift)
        out.append((L.name, m))
        entry.update({"triangles": int(len(m.faces)), "vertices": int(len(m.vertices)),
                      "watertight": bool(m.is_watertight), "pieces": int(m.body_count),
                      "area_mm2": round(float(m.area), 1),
                      "volume_mm3": round(float(m.volume), 1) if m.is_watertight else None,
                      "bbox_mm": np.round(m.bounds, 3).tolist()})
        rep.append(entry)
    report = {"block_mm": list(recipe.block_mm), "margin_mm": recipe.margin_mm, "origin": recipe.origin,
              "scale_glass_per_patient_mm": scale, "layers": rep, "seconds": round(time.time() - t0, 1)}
    return {"meshes": out, "scale": scale, "report": report}


def dots_from_meshes(meshes, specs: list[LayerSpec], total: int, min_spacing: float, seed: int = 0):
    """Optional preview cloud: area-sampled dots split across layers by weight, min-spacing enforced."""
    rng = np.random.default_rng(seed)
    w = {L.name: L.weight for L in specs}
    wsum = sum(w.get(n, 1.0) for n, _ in meshes)
    pts, lay = [], []
    for i, (name, m) in enumerate(meshes):
        want = max(1, int(round(total * w.get(name, 1.0) / wsum)))
        dense = sample_surface(np.asarray(m.vertices), np.asarray(m.faces), want * 6, rng)
        p = downsample_to_count(dense[rng.permutation(len(dense))], want, min_spacing)
        pts.append(p)
        lay.append(np.full(len(p), i, np.uint8))
    pts, lay = np.vstack(pts), np.concatenate(lay)
    order = rng.permutation(len(pts))
    pts, lay = pts[order], lay[order]
    keep = min_spacing_mask(pts, min_spacing)
    return pts[keep], lay[keep]


def parse_block(s: str):
    v = [float(x) for x in s.lower().split("x")]
    v = v * 3 if len(v) == 1 else v
    if len(v) != 3:
        raise argparse.ArgumentTypeError("block must look like 50 or 50x50x80")
    return tuple(v)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dicom", help="folder holding the CT series (searched recursively)")
    ap.add_argument("--series", help="series number, UID or description substring")
    ap.add_argument("--list", action="store_true", help="list the series in --dicom and exit")
    ap.add_argument("--seg", help="TotalSegmentator output: mask folder, or multilabel .nii.gz")
    ap.add_argument("--seg-names", help="JSON {id: name} for a multilabel file")
    ap.add_argument("--list-structures", action="store_true", help="list structure names in --seg and exit")
    ap.add_argument("--recipe", help="JSON recipe (block, margin, layers)")
    ap.add_argument("--layer", action="append", type=LayerSpec.parse,
                    help="NAME:hu=250 or NAME:labels=rib_*,sternum plus :smooth=MM :taubin=N :faces=N "
                         ":outer=1 :min_component=MM3 :largest=N  (repeatable; overrides recipe layers)")
    ap.add_argument("--block", type=parse_block, help="block size mm, WxDxH (default 50x50x80)")
    ap.add_argument("--margin", type=float, help="clear border inside the block, mm (default 4)")
    ap.add_argument("--origin", choices=["center", "corner"])
    ap.add_argument("--formats", default="stl,obj,glb", help="mesh formats: stl,obj,glb")
    ap.add_argument("--points", type=int, default=0, help="also write a preview dot cloud of ~N dots")
    ap.add_argument("--min-spacing", type=float, default=0.2, help="dot spacing floor for --points, mm")
    ap.add_argument("-o", "--out", default="out")
    a = ap.parse_args(argv)

    if a.list:
        for s in list_series(a.dicom):
            print(f"  #{s['number']:>3}  {s['slices']:>4} slices  {s['rows']}x{s['cols']}  "
                  f"{s['slice_thickness']:.2f} mm  {s['description']}")
        return 0
    seg = Segmentation(a.seg, a.seg_names) if a.seg else None
    if a.list_structures:
        print("\n".join(seg.names))
        return 0

    recipe = Recipe.load(a.recipe) if a.recipe else Recipe(layers=[])
    if a.layer:
        recipe.layers = a.layer
    if not recipe.layers:
        recipe.layers = [LayerSpec("bone", hu=250.0)]
    if a.block:
        recipe.block_mm = a.block
    if a.margin is not None:
        recipe.margin_mm = a.margin
    if a.origin:
        recipe.origin = a.origin

    ct = None
    if a.dicom:
        print(f"[0] loading {a.dicom}")
        ct = load_dicom(a.dicom, a.series)
        print(f"[0] {ct.description!r}: {ct.data.shape[0]} slices of {ct.data.shape[1]}x{ct.data.shape[2]}, "
              f"spacing {tuple(round(x, 3) for x in ct.spacing_kji)} mm (k,j,i)")
    if seg:
        print(f"[0] segmentation {a.seg}: {len(seg.names)} structures")

    res = build(recipe, ct, seg)
    os.makedirs(a.out, exist_ok=True)
    fmts = {x.strip() for x in a.formats.split(",") if x.strip()}
    files = []
    if "stl" in fmts:
        for name, m in res["meshes"]:
            m.export(os.path.join(a.out, f"{name}.stl"))
            files.append(f"{name}.stl")
    if "obj" in fmts:
        write_obj(os.path.join(a.out, "model.obj"), res["meshes"])
        files.append("model.obj")
    if "glb" in fmts:
        write_glb(os.path.join(a.out, "model.glb"), res["meshes"])
        files.append("model.glb")
    if a.points:
        pts, lay = dots_from_meshes(res["meshes"], recipe.layers, a.points, a.min_spacing)
        names = [n for n, _ in res["meshes"]]
        write_ply_points(os.path.join(a.out, "dots.ply"), pts, lay, names)
        np.savetxt(os.path.join(a.out, "dots.xyz"), pts, fmt="%.4f")
        write_dxf_points(os.path.join(a.out, "dots.dxf"), pts, lay, names)
        files += ["dots.ply", "dots.xyz", "dots.dxf"]
        res["report"]["dots"] = {"count": int(len(pts)), "min_spacing_mm": a.min_spacing,
                                 "measured_min_distance_mm": round(min_pairwise_distance(pts), 4)}
        print(f"[5] {len(pts):,} preview dots, min spacing {a.min_spacing} mm")
    res["report"]["files"] = files
    with open(os.path.join(a.out, "report.json"), "w") as f:
        json.dump(res["report"], f, indent=2)
    print(f"[5] wrote {', '.join(files)}, report.json -> {a.out}/  ({res['report']['seconds']} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
