"""Browser tests for the bundled viewer (dist/viewer_standalone.html) in headless Chromium."""
import io
import json
import os
import zipfile

import numpy as np
import pytest
import trimesh

pw = pytest.importorskip("playwright.sync_api")
import build_viewer  # noqa: E402
from viewer_harness import serve, route_three  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, "viewer", "sample.glb")


@pytest.fixture(scope="module")
def page():
    if not os.path.exists(SAMPLE):
        pytest.skip("viewer/sample.glb missing — run ct2mesh first")
    dist = build_viewer.main()
    srv, url = serve(os.path.dirname(dist))
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"])
        pg = b.new_page(viewport={"width": 1280, "height": 800}, accept_downloads=True)
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        route_three(pg)
        pg.goto(url + "viewer_standalone.html")
        pg.wait_for_function("window.__etch && window.__etch.S.layers.length > 0", timeout=30000)
        pg.errors = errors
        yield pg
        b.close()
    srv.shutdown()


def S(pg, expr):
    return pg.evaluate(f"(() => {{ const S = window.__etch.S; return {expr}; }})()")


def hud_number(pg):
    return int(pg.locator("#hudCount").inner_text().replace(",", ""))


def unzip_export(pg):
    with pg.expect_download() as dl:
        pg.locator("#export").click()
    z = zipfile.ZipFile(io.BytesIO(open(dl.value.path(), "rb").read()))
    assert z.testzip() is None
    return z


def test_sample_loads_cleanly(page):
    assert page.errors == []
    assert page.locator("#busy").is_hidden()
    names = S(page, "S.layers.map(L => L.name)")
    assert names == ["ribcage", "spine", "heart", "airway", "skin"]
    assert S(page, "S.layers.every(L => L.openEdges === 0)")
    assert hud_number(page) == S(page, "S.layers.reduce((a, L) => a + L.tris, 0)")
    assert "all closed" in page.locator("#hudA").inner_text()


def test_layer_toggle(page):
    total = hud_number(page)
    page.locator("#lon4").uncheck()
    assert S(page, "S.layers[4].obj.visible") is False
    assert hud_number(page) == total - S(page, "S.layers[4].tris")
    page.locator("#lon4").check()
    assert hud_number(page) == total


def _model_bounds(pg):
    return S(pg, """(() => { let lo=[1e9,1e9,1e9], hi=[-1e9,-1e9,-1e9];
        for (const L of S.layers) { const P = L.geom.attributes.position.array;
          for (let i=0;i<P.length;i+=3) for (let d=0;d<3;d++) { const v=(P[i+d]-S.centre[d])*S.scale;
            if (v<lo[d]) lo[d]=v; if (v>hi[d]) hi[d]=v; } }
        return {lo, hi, dims: S.dims, m: S.margin}; })()""")


def test_refit_on_block_change(page):
    for id_, v in (("#cx", "40"), ("#cz", "100"), ("#cm", "2")):
        page.locator(id_).fill(v)
        page.locator(id_).dispatch_event("change")
    b = _model_bounds(page)
    half = [d / 2 - b["m"] for d in b["dims"]]
    assert b["dims"] == [40, 50, 100] and b["m"] == 2
    for d in range(3):
        assert b["lo"][d] >= -half[d] - 1e-3 and b["hi"][d] <= half[d] + 1e-3
    assert any(abs(b["hi"][d] - half[d]) < 1e-2 for d in range(3))


def test_mesh_export_is_block_fitted_and_closed(page, tmp_path):
    z = unzip_export(page)
    names = z.namelist()
    assert sorted(n for n in names if n.endswith(".stl")) == sorted(
        f"{n}.stl" for n in ["ribcage", "spine", "heart", "airway", "skin"])
    settings = json.loads(z.read("settings.json"))
    half = np.array(settings["block_mm"]) / 2 - settings["margin_mm"]
    for n in names:
        if not n.endswith(".stl"):
            continue
        p = tmp_path / n
        p.write_bytes(z.read(n))
        m = trimesh.load(p)
        assert m.is_watertight, n
        assert np.all(m.bounds[0] >= -half - 1e-3) and np.all(m.bounds[1] <= half + 1e-3), n


def test_dots_mode(page):
    page.locator("#mDots").click()
    page.wait_for_function("window.__etch.S.idx.length > 0", timeout=30000)
    assert page.locator("#dotsPanel").is_visible()
    n1 = S(page, "S.idx.length")
    assert hud_number(page) == n1
    page.locator("#spacing").fill("0.5")
    page.wait_for_timeout(300)
    n2 = S(page, "S.idx.length")
    assert n2 < n1
    pts = np.array(S(page, "Array.from(S.idx, i => [S.pts[3*i], S.pts[3*i+1], S.pts[3*i+2]])"))
    from scipy.spatial import cKDTree
    d, _ = cKDTree(pts).query(pts, k=2)
    assert d[:, 1].min() >= 0.5 - 1e-4


def test_dot_budget_and_layer_share(page):
    page.locator("#budget").fill("30000")
    page.locator("#fitBudget").click()
    page.wait_for_timeout(300)
    assert abs(S(page, "S.idx.length") - 30000) / 30000 < 0.03
    before = S(page, "S.idx.reduce((a, j) => a + (S.candLayer[j] === 2), 0)")
    page.locator("#lkeep2").fill("0.2")
    page.wait_for_timeout(300)
    after = S(page, "S.idx.reduce((a, j) => a + (S.candLayer[j] === 2), 0)")
    assert 0.1 * before < after < 0.35 * before          # density follows the share (~0.2x)
    # within that layer, dots keep r / sqrt(share) apart
    r = S(page, "S.spacing")
    pts = np.array(S(page, "Array.from(S.idx).filter(j => S.candLayer[j] === 2).map(i => [S.pts[3*i], S.pts[3*i+1], S.pts[3*i+2]])"))
    from scipy.spatial import cKDTree
    d, _ = cKDTree(pts).query(pts, k=2)
    assert d[:, 1].min() >= r / np.sqrt(0.2) - 1e-3
    page.locator("#lkeep2").fill("1")
    page.wait_for_timeout(200)


def test_dots_export(page):
    z = unzip_export(page)
    n = S(page, "S.idx.length")
    assert len(z.read("dots.xyz").decode().strip().splitlines()) == n
    assert z.read("dots.dxf").decode().count("\nPOINT\n") == n
    assert json.loads(z.read("settings.json"))["dots"]["count"] == n
    page.locator("#mGlass").click()


def test_load_multiple_stls_as_layers(page, tmp_path):
    a = trimesh.creation.icosphere(3, radius=10)
    b = trimesh.creation.box((8, 8, 30))
    b.apply_translation((20, 0, 0))
    a.export(tmp_path / "moon.stl")
    b.export(tmp_path / "tower.stl")
    page.locator("#file").set_input_files([str(tmp_path / "moon.stl"), str(tmp_path / "tower.stl")])
    page.wait_for_function("window.__etch.S.source === '2 files'")
    assert S(page, "S.layers.map(L => L.name)") == ["moon", "tower"]
    assert S(page, "S.layers.every(L => L.openEdges === 0)")
    assert page.locator("#hudWarn").is_hidden()


def test_open_mesh_is_flagged(page, tmp_path):
    s = trimesh.creation.icosphere(3, radius=10)
    keep = s.triangles_center[:, 2] > 0                   # hemisphere: open rim
    s.update_faces(keep)
    s.remove_unreferenced_vertices()
    s.export(tmp_path / "bowl.stl")
    page.locator("#file").set_input_files(str(tmp_path / "bowl.stl"))
    page.wait_for_function("window.__etch.S.source === 'bowl.stl'")
    assert S(page, "S.layers[0].openEdges") > 0
    assert page.locator("#hudWarn").is_visible()
    assert "open edges" in page.locator("#layers").inner_text()


def test_point_cloud_ply(page, tmp_path):
    pts = np.random.default_rng(0).normal(size=(5000, 3)) * 10
    trimesh.PointCloud(pts).export(tmp_path / "cloud.ply")
    page.locator("#file").set_input_files(str(tmp_path / "cloud.ply"))
    page.wait_for_function("window.__etch.S.source === 'cloud.ply'")
    assert S(page, "S.layers[0].isPoints") is True
    page.locator("#mDots").click()
    page.wait_for_function("window.__etch.S.idx.length > 0")
    page.locator("#mGlass").click()


def test_bad_file_shows_message(page, tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("hello")
    page.locator("#file").set_input_files(str(p))
    page.wait_for_function("document.getElementById('srcInfo').textContent.includes('notes.txt')")
    assert "Could not read notes.txt" in page.locator("#srcInfo").inner_text()
    assert "Unsupported file type" in page.locator("#srcInfo").inner_text()


def test_sample_reload_renders(page, tmp_path):
    page.locator("#loadSample").click()
    page.wait_for_function("window.__etch.S.source.startsWith('sample chest')")
    page.locator("#vFront").click()
    page.wait_for_timeout(600)
    shot = tmp_path / "glass.png"
    page.locator("#gl").screenshot(path=str(shot))
    from skimage import io as skio
    img = skio.imread(shot)[..., :3].astype(float)
    assert (img.mean(2) > 60).mean() > 0.01, "canvas looks empty"
    assert page.errors == []


def test_phone_width_has_no_horizontal_scroll(page):
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(300)
    sw, cw = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
    assert sw <= cw
    page.set_viewport_size({"width": 1280, "height": 800})


def test_embedded_sample_needs_no_network_and_reloads(page):
    """The published page embeds the sample; it must load and reload with sample.json unreachable."""
    dist = build_viewer.main()
    srv, url = serve(os.path.dirname(dist))
    pg = page.context.browser.new_page(viewport={"width": 1280, "height": 800})
    errors, hits = [], []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    route_three(pg)
    pg.route("**/sample.json", lambda r: (hits.append(r.request.url), r.abort()))
    pg.goto(url + "viewer_standalone.html")
    pg.wait_for_function("window.__etch && window.__etch.S.layers.length === 5", timeout=30000)
    for _ in range(2):
        pg.evaluate("window.__etch.S.source = 'other'")
        pg.locator("#loadSample").click()
        pg.wait_for_function("window.__etch.S.source.startsWith('sample chest')")
    assert pg.locator("#busy").is_hidden()
    assert hits == [] and errors == []
    pg.close()
    srv.shutdown()


def test_open_stl_button_and_ascii_stl(page, tmp_path):
    m = trimesh.creation.capsule(height=30, radius=6)
    p = tmp_path / "bone.stl"
    p.write_text(trimesh.exchange.stl.export_stl_ascii(m))
    assert p.read_text().startswith("solid")
    with page.expect_file_chooser() as fc:
        page.locator("#openFiles").click()
    fc.value.set_files(str(p))
    page.wait_for_function("window.__etch.S.source === 'bone.stl'")
    assert S(page, "S.layers[0].openEdges") == 0
    assert S(page, "S.layers[0].tris") == len(m.faces)


def test_up_axis_toggle(page, tmp_path):
    # a tall box along Y (a Y-up file): after switching to "Y up" it must stand along Z
    b = trimesh.creation.box((10, 60, 10))
    b.export(tmp_path / "tower_y.stl")
    page.locator("#file").set_input_files(str(tmp_path / "tower_y.stl"))
    page.wait_for_function("window.__etch.S.source === 'tower_y.stl'")
    def extents():
        return S(page, """(() => { const P = S.layers[0].geom.attributes.position.array; const lo=[1e9,1e9,1e9], hi=[-1e9,-1e9,-1e9];
            for (let i=0;i<P.length;i+=3) for (let d=0;d<3;d++){ lo[d]=Math.min(lo[d],P[i+d]); hi[d]=Math.max(hi[d],P[i+d]); }
            return hi.map((h,d)=>h-lo[d]); })()""")
    e = extents()
    assert e[1] == pytest.approx(60, abs=1e-3) and e[2] == pytest.approx(10, abs=1e-3)
    page.locator("#upY").click()
    e = extents()
    assert e[2] == pytest.approx(60, abs=1e-3) and e[1] == pytest.approx(10, abs=1e-3)
    assert page.locator("#upY").get_attribute("aria-pressed") == "true"
    # the setting sticks for the next file, and the sample always comes in Z-up
    page.locator("#loadSample").click()
    page.wait_for_function("window.__etch.S.source.startsWith('sample chest')")
    assert page.locator("#upZ").get_attribute("aria-pressed") == "true"


def test_weld_and_open_edges_match_trimesh(page, tmp_path):
    """The fast welder + sorted-edge hole check must agree with trimesh on a holed mesh."""
    s = trimesh.creation.icosphere(4, radius=12)
    s.update_faces(np.arange(len(s.faces)) % 7 != 0)       # punch scattered holes
    s.remove_unreferenced_vertices()
    s.export(tmp_path / "holes.stl")
    from collections import Counter
    edges = Counter(tuple(sorted(e)) for e in s.edges)
    expected_open = sum(1 for c in edges.values() if c != 2)
    page.locator("#file").set_input_files(str(tmp_path / "holes.stl"))
    page.wait_for_function("window.__etch.S.source === 'holes.stl'")
    assert S(page, "S.layers[0].tris") == len(s.faces)
    assert S(page, "S.layers[0].geom.attributes.position.count") == len(s.vertices)
    assert S(page, "S.layers[0].openEdges") == expected_open
    assert "holes.stl" in page.locator("#srcInfo").inner_text()


def test_corrupt_stl_reports_error_in_panel(page, tmp_path):
    p = tmp_path / "broken.stl"
    p.write_bytes(b"\x00" * 80 + (1000000).to_bytes(4, "little") + b"\x01" * 60)   # claims 1M triangles
    page.locator("#file").set_input_files(str(p))
    page.wait_for_function("document.getElementById('srcInfo').textContent.includes('broken.stl')")
    assert page.locator("#busy").is_hidden()
    assert "Could not read broken.stl" in page.locator("#srcInfo").inner_text()


def test_runs_with_all_external_network_blocked(page):
    """Everything the viewer needs is inside the page: no CDN, no fonts required, no sample fetch."""
    dist = build_viewer.main()
    srv, url = serve(os.path.dirname(dist))
    pg = page.context.browser.new_page(viewport={"width": 1280, "height": 800})
    errors, external = [], []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    def guard(route):
        if route.request.url.startswith(url):
            route.continue_()
        else:
            external.append(route.request.url)
            route.abort()
    pg.route("**/*", guard)
    pg.goto(url + "viewer_standalone.html")
    pg.wait_for_function("window.__etchReady && window.__etch.S.layers.length === 5", timeout=30000)
    assert pg.locator("#busy").is_hidden()
    assert errors == []
    assert all("fonts.g" in u for u in external), external      # only the optional Google Fonts were tried
    pg.close()
    srv.shutdown()


def test_without_webgl_the_page_says_so(page):
    dist = build_viewer.main()
    srv, url = serve(os.path.dirname(dist))
    pg = page.context.browser.new_page(viewport={"width": 1280, "height": 800})
    pg.add_init_script("HTMLCanvasElement.prototype.getContext = function () { return null; };")
    pg.goto(url + "viewer_standalone.html")
    pg.wait_for_function("document.getElementById('busy').textContent.includes('WebGL')", timeout=15000)
    assert pg.locator("#busy").is_visible()
    txt = pg.locator("#busy").inner_text()
    assert "hardware acceleration" in txt and "Uncaught" not in txt
    pg.close()
    srv.shutdown()
