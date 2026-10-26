"""Tests for ct2mesh: loading, segmentation integration, meshing, refinement, fitting, export."""
import json
import os

import numpy as np
import pytest
import trimesh

import ct2mesh as cm
import make_phantom
from conftest import SIZE, SLICES, PIX, SL


# ------------------------------------------------------------------ loading

def test_dicom_sorted_by_position_not_filename(phantom_dir, phantom_arrays):
    vol = cm.load_dicom(str(phantom_dir / "dicom"))
    hu, _, _ = phantom_arrays
    assert vol.data.shape == hu.shape
    # filenames are shuffled; loader must restore exact slice order and rescale to HU
    assert np.allclose(vol.data, hu, atol=0.5)
    assert vol.spacing_kji == pytest.approx((SL, PIX, PIX))
    assert np.allclose(vol.affine, make_phantom.lps_affine(SIZE, SLICES, PIX, SL))


def test_list_series(phantom_dir):
    s = cm.list_series(str(phantom_dir / "dicom"))
    assert len(s) == 1 and s[0]["slices"] == SLICES and s[0]["description"] == "Synthetic chest phantom"


def test_series_selection_errors(phantom_dir):
    with pytest.raises(ValueError, match="no series matches"):
        cm.load_dicom(str(phantom_dir / "dicom"), "does-not-exist")
    assert cm.load_dicom(str(phantom_dir / "dicom"), "chest").data.shape[0] == SLICES


def test_segmentation_folder_and_multilabel_agree(phantom_dir):
    a = cm.Segmentation(str(phantom_dir / "seg"))
    b = cm.Segmentation(str(phantom_dir / "seg_ml.nii.gz"))   # sidecar json found automatically
    assert set(a.names) == set(b.names)
    for pat in (["heart"], ["rib_*"], ["vertebrae_T*", "sternum"]):
        ma, na = a.mask(pat)
        mb, nb = b.mask(pat)
        assert sorted(na) == sorted(nb)
        assert np.array_equal(ma, mb) and ma.any()


def test_segmentation_registered_to_dicom(phantom_dir, phantom_arrays):
    """RAS (NIfTI) -> LPS conversion must land masks on the same world grid as the CT."""
    vol = cm.load_dicom(str(phantom_dir / "dicom"))
    seg = cm.Segmentation(str(phantom_dir / "seg"))
    assert np.allclose(seg.affine, vol.affine, atol=1e-4)
    m, _ = seg.mask(["rib_*", "vertebrae_*", "sternum"])
    _, lab, _ = phantom_arrays
    assert m.shape == lab.shape
    # labelled bone voxels are bright in the CT
    assert np.median(vol.data[m]) > 450


def test_pattern_matching(phantom_dir):
    seg = cm.Segmentation(str(phantom_dir / "seg"))
    assert len(seg.match(["rib_*"])) == 24
    assert len(seg.match(["rib_left_*"])) == 12
    assert len(seg.match(["lung_*"])) == 5
    with pytest.raises(ValueError, match="Available"):
        seg.match(["kidney_*"])


# ------------------------------------------------------------------ meshing accuracy

def _sphere_volume(r=20.0, spacing=(1.0, 1.0, 1.0), n=64):
    k, j, i = np.mgrid[0:n, 0:n, 0:n].astype(float)
    c = (n - 1) / 2
    d = np.sqrt(((k - c) * spacing[0]) ** 2 + ((j - c) * spacing[1]) ** 2 + ((i - c) * spacing[2]) ** 2)
    A = np.eye(4)
    A[0, 0], A[1, 1], A[2, 2] = spacing[2], spacing[1], spacing[0]
    A[:3, 3] = [-c * spacing[2], -c * spacing[1], -c * spacing[0]]
    return d <= r, cm.Volume(np.zeros((n, n, n), np.float32), A)


@pytest.mark.parametrize("spacing", [(1.0, 1.0, 1.0), (2.0, 1.0, 1.0)])
def test_mask_to_mesh_sphere_ground_truth(spacing):
    r = 20.0
    m, vol = _sphere_volume(r, spacing, 64 if spacing[0] == 1 else 48)
    v, f = cm.mask_to_mesh(m, vol, smooth_mm=1.0)
    mesh = cm.refine(v, f, taubin=10, faces_target=None)
    radii = np.linalg.norm(mesh.vertices, axis=1)        # sphere centred at world origin
    assert abs(radii.mean() - r) < 0.6
    assert radii.std() < 0.6
    assert mesh.is_watertight
    assert mesh.volume == pytest.approx(4 / 3 * np.pi * r ** 3, rel=0.06)


def test_taubin_preserves_volume_better_than_laplacian():
    m, vol = _sphere_volume(15.0, n=48)
    v, f = cm.mask_to_mesh(m, vol, smooth_mm=0.0)
    raw = trimesh.Trimesh(v, f, process=True)
    taubin = cm.refine(v, f, taubin=30)
    lap = raw.copy()
    trimesh.smoothing.filter_laplacian(lap, iterations=30, volume_constraint=False)
    assert abs(taubin.volume - raw.volume) / raw.volume < 0.03
    assert abs(lap.volume - raw.volume) > abs(taubin.volume - raw.volume)


def test_decimation_hits_target_and_stays_closed():
    m, vol = _sphere_volume(20.0, n=64)
    v, f = cm.mask_to_mesh(m, vol, smooth_mm=1.0)
    mesh = cm.refine(v, f, taubin=5, faces_target=3000)
    assert abs(len(mesh.faces) - 3000) / 3000 < 0.1
    assert mesh.is_watertight


def test_clean_mask_drops_specks_and_keeps_largest():
    m = np.zeros((30, 30, 30), bool)
    m[5:15, 5:15, 5:15] = True          # 1000 vox
    m[20:24, 20:24, 20:24] = True       # 64 vox
    m[27, 27, 27] = True                # 1 vox
    out = cm.clean_mask(m, (1, 1, 1), min_component_mm3=10)
    assert out.sum() == 1064
    out = cm.clean_mask(m, (1, 1, 1), keep_largest=1)
    assert out.sum() == 1000


# ------------------------------------------------------------------ HU layers

def test_hu_bone_layer_excludes_scanner_table(phantom_dir):
    vol = cm.load_dicom(str(phantom_dir / "dicom"))
    body = cm.body_mask(vol.data)
    v, f = cm.hu_to_mesh(vol, 250, body, 1.0, 100, None, outer=False)
    assert len(f) > 0
    # the table sits at y ~ +122..128 mm (posterior); body ends near +110
    assert v[:, 1].max() < 115


def test_outer_skin_is_single_closed_shell(phantom_dir):
    vol = cm.load_dicom(str(phantom_dir / "dicom"))
    body = cm.body_mask(vol.data)
    v, f = cm.hu_to_mesh(vol, -400, body, 3.0, 100, 1, outer=True)
    outer = cm.refine(v, f, taubin=10, faces_target=20000)
    assert outer.is_watertight and outer.body_count == 1
    v2, f2 = cm.hu_to_mesh(vol, -400, body, 1.0, 100, None, outer=False)
    inner = trimesh.Trimesh(v2, f2, process=True)
    assert inner.body_count > 1          # without outer=True the lungs/airway surfaces appear too


# ------------------------------------------------------------------ recipe / layer parsing

def test_layer_parse():
    L = cm.LayerSpec.parse("ribs:labels=rib_*,sternum:smooth=1.5:faces=80000:largest=30")
    assert L.labels == ["rib_*", "sternum"] and L.smooth_mm == 1.5 and L.faces == 80000 and L.keep_largest == 30
    L = cm.LayerSpec.parse("skin:hu=-400:outer=1")
    assert L.hu == -400 and L.outer is True
    with pytest.raises(ValueError):
        cm.LayerSpec("x")                        # neither hu nor labels
    with pytest.raises(ValueError):
        cm.LayerSpec("x", hu=1, labels=["a"])   # both
    import argparse
    with pytest.raises(argparse.ArgumentTypeError):
        cm.LayerSpec.parse("x:colour=red")


def test_recipe_file_loads():
    r = cm.Recipe.load(os.path.join(os.path.dirname(cm.__file__), "recipes", "chest_art.json"))
    assert [L.name for L in r.layers] == ["ribcage", "spine", "heart", "airway", "skin"]
    assert r.block_mm == (50, 50, 80)


# ------------------------------------------------------------------ end to end

@pytest.fixture(scope="module")
def built(phantom_dir, tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    rc = cm.main(["--dicom", str(phantom_dir / "dicom"), "--seg", str(phantom_dir / "seg"),
                  "--recipe", os.path.join(os.path.dirname(cm.__file__), "recipes", "chest_art.json"),
                  "--block", "60x40x80", "--margin", "3", "--points", "15000", "--min-spacing", "0.25",
                  "-o", str(out)])
    assert rc == 0
    return out


def test_outputs_exist(built):
    for f in ["ribcage.stl", "spine.stl", "heart.stl", "airway.stl", "skin.stl", "model.obj", "model.glb",
              "dots.ply", "dots.xyz", "dots.dxf", "report.json"]:
        assert (built / f).stat().st_size > 0, f


def test_meshes_closed_and_inside_block(built):
    rep = json.load(open(built / "report.json"))
    half = np.array([60, 40, 80]) / 2 - 3
    lo_all, hi_all = [], []
    for L in rep["layers"]:
        m = trimesh.load(built / f"{L['name']}.stl")
        assert m.is_watertight, L["name"]
        assert len(m.faces) <= (L["params"]["faces"] or 1e12) * 1.02
        lo_all.append(m.bounds[0]); hi_all.append(m.bounds[1])
    lo, hi = np.min(lo_all, 0), np.max(hi_all, 0)
    assert np.all(lo >= -half - 1e-3) and np.all(hi <= half + 1e-3)
    assert np.any(np.isclose(hi, half, atol=0.05))   # fitted snugly on the limiting axis


def test_layers_stay_registered(built):
    """Heart must sit inside the ribcage and in front of the spine, after scaling."""
    rib = trimesh.load(built / "ribcage.stl")
    heart = trimesh.load(built / "heart.stl")
    spine = trimesh.load(built / "spine.stl")
    c = heart.centroid
    assert np.all(c[:2] > rib.bounds[0][:2]) and np.all(c[:2] < rib.bounds[1][:2])
    assert c[1] < spine.centroid[1]               # anterior (-Y) of the spine
    assert c[0] > spine.centroid[0]               # heart sits to the patient's left (+X)


def test_glb_has_named_layers(built):
    scene = trimesh.load(built / "model.glb")
    assert set(scene.geometry.keys()) >= {"ribcage", "spine", "heart", "airway", "skin"}


def test_obj_groups(built):
    txt = open(built / "model.obj").read()
    assert all(f"o {n}\n" in txt for n in ["ribcage", "spine", "heart", "airway", "skin"])
    m = trimesh.load(built / "model.obj", force="mesh")
    assert len(m.faces) > 1000


def test_label_and_hu_surfaces_agree(phantom_dir):
    """Vertebrae from the label masks should lie on the bone iso-surface from the CT — an end-to-end
    check that segmentation and CT are in the same patient space."""
    vol = cm.load_dicom(str(phantom_dir / "dicom"))
    seg = cm.Segmentation(str(phantom_dir / "seg"))
    m, _ = seg.mask(["vertebrae_*"])
    v1, _ = cm.mask_to_mesh(m, seg.volume(m), smooth_mm=0.0)
    v2, _ = cm.hu_to_mesh(vol, 250, cm.body_mask(vol.data), 0.0, 100, None, outer=False)
    from scipy.spatial import cKDTree
    d, _ = cKDTree(v2).query(v1)
    assert np.median(d) < 2.0


def test_dots_respect_spacing_and_count(built):
    pts, lay = cm.read_ply_points(str(built / "dots.ply"))
    assert cm.min_pairwise_distance(pts) >= 0.25 - 1e-4
    assert 0.6 * 15000 <= len(pts) <= 1.05 * 15000
    assert set(np.unique(lay)) <= set(range(5))
    assert open(built / "dots.dxf").read().count("\nPOINT\n") == len(pts)
    assert len(np.loadtxt(built / "dots.xyz")) == len(pts)


def test_min_spacing_mask_is_exact():
    rng = np.random.default_rng(1)
    p = rng.random((20000, 3)) * 10
    k = cm.min_spacing_mask(p, 0.3)
    assert cm.min_pairwise_distance(p[k]) >= 0.3
    # maximal: every removed point has a kept neighbour within r
    from scipy.spatial import cKDTree
    d, _ = cKDTree(p[k]).query(p[~k])
    assert np.all(d < 0.3)


def test_missing_source_errors():
    with pytest.raises(ValueError, match="no --dicom"):
        cm.build(cm.Recipe([cm.LayerSpec("b", hu=250)]))
    with pytest.raises(ValueError, match="no --seg"):
        cm.build(cm.Recipe([cm.LayerSpec("h", labels=["heart"])]))
