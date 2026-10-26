import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import make_phantom  # noqa: E402

# the viewer build needs three + esbuild; default to the repo's node_modules
os.environ.setdefault("NODE_MODULES", os.path.join(ROOT, "node_modules"))

SIZE, SLICES, PIX, SL = 128, 80, 3.0, 4.0   # small phantom (same anatomy, coarser) for fast tests


@pytest.fixture(scope="session")
def phantom_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("phantom")
    hu, lab, names = make_phantom.build_phantom(SIZE, SLICES, PIX, SL)
    make_phantom.write_dicom(hu, str(out / "dicom"), PIX, SL)
    make_phantom.write_segmentation(lab, names, str(out), make_phantom.lps_affine(SIZE, SLICES, PIX, SL))
    return out


@pytest.fixture(scope="session")
def phantom_arrays():
    return make_phantom.build_phantom(SIZE, SLICES, PIX, SL)
