#!/usr/bin/env python3
"""
Generate a synthetic chest CT for testing ct2mesh: a DICOM series plus ground-truth
segmentation masks written exactly the way TotalSegmentator writes its output.

The phantom (real Hounsfield units, LPS geometry) contains a torso with a fat layer, five lung
lobes, heart, aorta (ascending, arch, descending), trachea, 12 vertebrae with discs, spinal
cord, sternum, 24 individually labelled ribs, and a scanner table that the pipeline must strip.

Outputs
  OUT/dicom/IMxxxx.dcm         one CT slice per file, uncompressed, filenames shuffled
  OUT/seg/<structure>.nii.gz   one binary mask per structure (TotalSegmentator default output)
  OUT/seg_ml.nii.gz            single multilabel volume (TotalSegmentator --ml output)
  OUT/seg_ml.json              {label_id: structure_name} for the multilabel file

Structure names follow TotalSegmentator's class names (rib_left_1, vertebrae_T5,
lung_upper_lobe_left, heart, aorta, sternum, trachea, spinal_cord).

Usage:  python make_phantom.py OUT [--size 256] [--slices 160]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import random

import numpy as np
from scipy import ndimage
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

HU = dict(air=-1000, fat=-100, tissue=40, heart=45, blood=40, lung=-850, bone=700, rib=600,
          sternum=500, disc=70, table=300)


class Labels:
    def __init__(self):
        self.names: dict[int, str] = {}

    def id(self, name: str) -> int:
        for k, v in self.names.items():
            if v == name:
                return k
        k = len(self.names) + 1
        self.names[k] = name
        return k


def _tube(shape, centre_mm, radius_mm, spacing):
    """Boolean mask of a tube of radius_mm around a polyline given as (N,3) points in index-mm
    (z, y, x mm from the volume corner), plus nearest-centreline-point indices."""
    line = np.zeros(shape, dtype=bool)
    idx = np.round(centre_mm / np.asarray(spacing)).astype(int)
    ok = np.all((idx >= 0) & (idx < np.asarray(shape)), axis=1)
    idx = idx[ok]
    line[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    dist, near = ndimage.distance_transform_edt(~line, sampling=spacing, return_indices=True)
    return dist <= radius_mm, near


def build_phantom(size: int = 256, slices: int = 160, pixel_mm: float = 1.5,
                  slice_mm: float = 2.0, seed: int = 7):
    """Return (hu int16 (k,j,i), labels uint8 (k,j,i), {id: name}).
    k = slice (inferior->superior), j = row (anterior->posterior), i = col (right->left)."""
    rng = np.random.default_rng(seed)
    spacing = (slice_mm, pixel_mm, pixel_mm)
    shape = (slices, size, size)
    hu = np.full(shape, HU["air"], dtype=np.int16)
    lab = np.zeros(shape, dtype=np.uint8)
    L = Labels()

    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    x = (xx - size / 2) * pixel_mm          # + = patient left
    y = (yy - size / 2) * pixel_mm          # + = posterior
    zc = (np.arange(slices) - slices / 2) * slice_mm
    zmin, zmax = float(zc.min()), float(zc.max())

    def tfrac(z):
        return (z - zmin) / (zmax - zmin)

    def half_axes(t):
        return 160 - 15 * t, 110 - 10 * t

    # vertebra numbering: 26 mm pitch, counted down from the top as T1..T12, then L1..
    n_vert = int(np.ceil((zmax - zmin) / 26.0)) + 1
    vert_names = [f"vertebrae_T{i}" if i <= 12 else f"vertebrae_L{i-12}" for i in range(1, n_vert + 1)]

    for k, z in enumerate(zc):
        t = tfrac(z)
        a, b = half_axes(t)
        sl, sv = hu[k], lab[k]
        body = (x / a) ** 2 + (y / b) ** 2 <= 1.0
        inner = (x / (a - 12)) ** 2 + (y / (b - 12)) ** 2 <= 1.0
        sl[body] = HU["fat"]
        sl[inner] = HU["tissue"]

        # lungs, split into lobes by height (right lung has a middle lobe)
        lung_scale = np.clip(np.sin(np.pi * (0.1 + 0.85 * t)), 0.25, 1.0)
        for side in (-1, 1):
            cx = side * 65
            la, lb = 52 * lung_scale, 80 * lung_scale
            lung = (((x - cx) / la) ** 2 + ((y + 5) / lb) ** 2 <= 1.0) & inner
            sl[lung] = HU["lung"]
            if side > 0:   # patient left
                name = "lung_upper_lobe_left" if t > 0.5 else "lung_lower_lobe_left"
            else:
                name = ("lung_upper_lobe_right" if t > 0.62 else
                        "lung_middle_lobe_right" if t > 0.42 else "lung_lower_lobe_right")
            sv[lung] = L.id(name)

        if t < 0.6:
            hr = 55 * np.sin(np.pi * (t / 0.6)) + 5
            heart = ((x - 15) / hr) ** 2 + ((y + 25) / (hr * 0.85)) ** 2 <= 1.0
            sl[heart] = HU["heart"]
            sv[heart] = L.id("heart")

        if t > 0.6:
            tr = (x ** 2 + (y + 30) ** 2) <= 9 ** 2
            wall = ((x ** 2 + (y + 30) ** 2) <= 11 ** 2) & ~tr
            sl[tr] = HU["air"]
            sl[wall] = HU["tissue"]
            sv[tr | wall] = L.id("trachea")

        vnum = int((zmax - z) // 26.0)
        in_disc = ((zmax - z) % 26.0) > 21.0
        vb = (x ** 2 + ((y - (b - 45)) * 1.2) ** 2) <= 20 ** 2
        canal = (x ** 2 + (y - (b - 20)) ** 2) <= 8 ** 2
        ring = ((x ** 2 + (y - (b - 20)) ** 2) <= 15 ** 2) & ~canal
        if in_disc:
            sl[vb] = HU["disc"]
        else:
            sl[vb | ring] = HU["bone"]
            sv[vb | ring] = L.id(vert_names[min(vnum, len(vert_names) - 1)])
        sl[canal] = HU["tissue"]
        sv[canal] = L.id("spinal_cord")

        if t > 0.3:
            st = ((x / 14) ** 2 + ((y + (b - 18)) / 6) ** 2) <= 1.0
            sl[st] = HU["sternum"]
            sv[st] = L.id("sternum")

    origin_mm = np.array([zmin, -size / 2 * pixel_mm, -size / 2 * pixel_mm])  # index-mm offset

    # aorta: ascending from the heart, arch over to the left-posterior, descending beside the spine
    pts = []
    t_arch = 0.74
    z_arch = zmin + t_arch * (zmax - zmin)
    for zz in np.arange(zmin + 0.35 * (zmax - zmin), z_arch, 1.0):
        pts.append((zz, -12.0, 8.0))
    for th in np.linspace(0, np.pi, 160):
        yy_ = -12.0 + (52.0 + 12.0) * (1 - np.cos(th)) / 2
        pts.append((z_arch + 22 * np.sin(th), yy_, 8.0 + 14.0 * (1 - np.cos(th)) / 2))
    for zz in np.arange(zmin, z_arch, 1.0):
        pts.append((zz, 52.0, 22.0))
    pts = np.array(pts) - origin_mm
    aorta, _ = _tube(shape, pts, 11.0, spacing)
    hu[aorta] = HU["blood"]
    lab[aorta] = L.id("aorta")

    # ribs: 12 pairs, each its own label, sloping down anteriorly
    centre, rib_id = [], []
    for i in range(12):
        z_back = zmax - (zmax - zmin) * (0.10 + 0.068 * i)
        t = tfrac(z_back)
        a, b = half_axes(t)
        a, b = a - 20, b - 20
        for side, sname in ((1, "left"), (-1, "right")):
            rid = L.id(f"rib_{sname}_{i+1}")
            for th in np.linspace(0.08, np.pi * 0.80, 240):
                centre.append((z_back - 34 * (th / np.pi) ** 1.3, b * np.cos(th), side * a * np.sin(th)))
                rib_id.append(rid)
    centre = np.array(centre) - origin_mm
    rib_id = np.array(rib_id, dtype=np.uint8)
    idx = np.round(centre / np.asarray(spacing)).astype(int)
    ok = np.all((idx >= 0) & (idx < np.asarray(shape)), axis=1)
    idx, rib_id = idx[ok], rib_id[ok]
    line = np.zeros(shape, dtype=bool)
    line[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    owner = np.zeros(shape, dtype=np.uint8)
    owner[idx[:, 0], idx[:, 1], idx[:, 2]] = rib_id
    dist, near = ndimage.distance_transform_edt(~line, sampling=spacing, return_indices=True)
    rib = dist <= 4.0
    hu[rib] = HU["rib"]
    lab[rib] = owner[near[0][rib], near[1][rib], near[2][rib]]

    # scanner table, posterior and separate from the body — not labelled
    hu[:, (np.abs(y - 125) <= 3) & (np.abs(x) <= 170)] = HU["table"]

    hu = hu.astype(np.float32) + rng.normal(0, 12, shape).astype(np.float32)
    return np.clip(hu, -1024, 3071).astype(np.int16), lab, dict(L.names)


def lps_affine(size: int, slices: int, pixel_mm: float, slice_mm: float) -> np.ndarray:
    """4x4 voxel(i=col, j=row, k=slice) -> LPS mm, matching what write_dicom writes."""
    A = np.eye(4)
    A[:3, 0] = [pixel_mm, 0, 0]
    A[:3, 1] = [0, pixel_mm, 0]
    A[:3, 2] = [0, 0, slice_mm]
    A[:3, 3] = [-(size / 2) * pixel_mm, -(size / 2) * pixel_mm, -(slices / 2) * slice_mm]
    return A


def write_dicom(hu: np.ndarray, out_dir: str, pixel_mm: float, slice_mm: float,
                shuffle_names: bool = True) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    n, rows, cols = hu.shape
    study, series, frame = generate_uid(), generate_uid(), generate_uid()
    now = _dt.datetime(2026, 1, 1, 12, 0, 0)
    slope, intercept = 1.0, -1024.0
    order = list(range(n))
    if shuffle_names:  # filenames deliberately do not follow slice order
        random.Random(3).shuffle(order)
    paths = []
    for k in range(n):
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = CTImageStorage
        meta.MediaStorageSOPInstanceUID = generate_uid()
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        fname = os.path.join(out_dir, f"IM{order[k]:04d}.dcm")
        ds = FileDataset(fname, {}, file_meta=meta, preamble=b"\0" * 128)
        ds.SOPClassUID, ds.SOPInstanceUID = CTImageStorage, meta.MediaStorageSOPInstanceUID
        ds.StudyInstanceUID, ds.SeriesInstanceUID, ds.FrameOfReferenceUID = study, series, frame
        ds.Modality = "CT"
        ds.PatientName, ds.PatientID = "PHANTOM^SYNTHETIC", "PHANTOM0001"
        ds.StudyDate = ds.SeriesDate = now.strftime("%Y%m%d")
        ds.StudyTime = ds.SeriesTime = now.strftime("%H%M%S")
        ds.SeriesDescription, ds.SeriesNumber, ds.InstanceNumber = "Synthetic chest phantom", 3, k + 1
        ds.ImageType = ["ORIGINAL", "PRIMARY", "AXIAL"]
        ds.ImagePositionPatient = [-(cols / 2) * pixel_mm, -(rows / 2) * pixel_mm, (k - n / 2) * slice_mm]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing = [pixel_mm, pixel_mm]
        ds.SliceThickness = slice_mm
        ds.Rows, ds.Columns = rows, cols
        ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
        ds.BitsAllocated = ds.BitsStored = 16
        ds.HighBit, ds.PixelRepresentation = 15, 0
        ds.RescaleSlope, ds.RescaleIntercept, ds.RescaleType = slope, intercept, "HU"
        ds.WindowCenter, ds.WindowWidth = -550, 1500
        ds.PixelData = ((hu[k].astype(np.float32) - intercept) / slope).round().astype(np.uint16).tobytes()
        ds.save_as(fname, enforce_file_format=True)
        paths.append(fname)
    return paths


def write_segmentation(lab: np.ndarray, names: dict, out: str, affine_lps: np.ndarray):
    """TotalSegmentator-style output: OUT/seg/<name>.nii.gz per structure and OUT/seg_ml.nii.gz."""
    import nibabel as nib
    ras = np.diag([-1.0, -1.0, 1.0, 1.0]) @ affine_lps     # NIfTI stores RAS world coordinates
    data = np.ascontiguousarray(lab.transpose(2, 1, 0))     # (k,j,i) -> (i,j,k)
    seg_dir = os.path.join(out, "seg")
    os.makedirs(seg_dir, exist_ok=True)
    for k, name in names.items():
        nib.save(nib.Nifti1Image((data == k).astype(np.uint8), ras), os.path.join(seg_dir, f"{name}.nii.gz"))
    nib.save(nib.Nifti1Image(data, ras), os.path.join(out, "seg_ml.nii.gz"))
    with open(os.path.join(out, "seg_ml.json"), "w") as f:
        json.dump({str(k): v for k, v in names.items()}, f, indent=1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--size", type=int, default=256)
    ap.add_argument("--slices", type=int, default=160)
    ap.add_argument("--pixel-mm", type=float, default=1.5)
    ap.add_argument("--slice-mm", type=float, default=2.0)
    a = ap.parse_args()
    hu, lab, names = build_phantom(a.size, a.slices, a.pixel_mm, a.slice_mm)
    write_dicom(hu, os.path.join(a.out, "dicom"), a.pixel_mm, a.slice_mm)
    write_segmentation(lab, names, a.out, lps_affine(a.size, a.slices, a.pixel_mm, a.slice_mm))
    print(f"wrote {a.slices} DICOM slices and {len(names)} structure masks to {a.out}/")


if __name__ == "__main__":
    main()
