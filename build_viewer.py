#!/usr/bin/env python3
"""Build the viewer into self-contained pages (no CDN, no network needed at runtime).

  viewer/index.html  page shell (markup, styles, startup guard, /*APP_BUNDLE*/ placeholder)
  viewer/app.js      the app, an ES module importing three.js
  viewer/sample.glb  sample model (ct2mesh output), embedded as base64 layer buffers

Outputs
  dist/artifact.html           page body for publishing as a claude.ai artifact
  dist/viewer_standalone.html  full document: open it straight from disk
  viewer/sample.json           the sample in the viewer's layer format

Needs node with three@0.160.0 and esbuild installed (npm install in the repo root),
or NODE_MODULES pointing at a node_modules folder that has them.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKELETON = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '</head><body>\n{body}\n</body></html>\n')


def node_modules() -> str:
    for cand in (os.environ.get("NODE_MODULES"), os.path.join(HERE, "node_modules")):
        if cand and os.path.exists(os.path.join(cand, "three")) and os.path.exists(os.path.join(cand, ".bin", "esbuild")):
            return cand
    sys.exit("three and esbuild not found: run `npm install` in the repo root (or set NODE_MODULES)")


def bundle_app() -> str:
    nm = node_modules()
    out = subprocess.run(
        [os.path.join(nm, ".bin", "esbuild"), os.path.join(HERE, "viewer", "app.js"), "--bundle",
         "--format=iife", "--minify", "--target=es2019", "--legal-comments=none", "--log-level=error"],
        check=True, capture_output=True, text=True, env={**os.environ, "NODE_PATH": nm}, cwd=os.path.dirname(nm))
    js = out.stdout
    return js.replace("</script", "<\\/script")          # never close the inline tag early


def glb_to_layers_json(glb_path: str) -> str:
    """The sample as base64 layer buffers (the viewer's own format), in the recipe's layer order."""
    import numpy as np
    import trimesh
    scene = trimesh.load(glb_path)
    layers = []
    for name, geom in scene.geometry.items():
        nodes = scene.graph.geometry_nodes.get(name, [name])
        m = geom.copy()
        m.apply_transform(scene.graph[nodes[0]][0])
        layers.append({"name": name,
                       "positions": base64.b64encode(np.asarray(m.vertices, "<f4").tobytes()).decode(),
                       "indices": base64.b64encode(np.asarray(m.faces, "<u4").tobytes()).decode()})
    return json.dumps({"format": "ct2mesh-layers/1", "units": "mm", "up": "+z", "layers": layers})


def main(sample_glb: str | None = None, dist: str = os.path.join(HERE, "dist")) -> str:
    os.makedirs(dist, exist_ok=True)
    with open(os.path.join(HERE, "viewer", "index.html"), encoding="utf-8") as f:
        body = f.read()
    assert "/*APP_BUNDLE*/" in body, "APP_BUNDLE placeholder missing from viewer/index.html"
    body = body.replace("/*APP_BUNDLE*/", bundle_app())
    src = sample_glb or os.path.join(HERE, "viewer", "sample.glb")
    tag = '<script type="application/json" id="sampleData"></script>'
    if os.path.exists(src):
        sample = glb_to_layers_json(src)
        with open(os.path.join(HERE, "viewer", "sample.json"), "w") as f:
            f.write(sample)
        body = body.replace(tag, f'<script type="application/json" id="sampleData">{sample}</script>')
    with open(os.path.join(dist, "artifact.html"), "w", encoding="utf-8") as f:
        f.write(body)
    out = os.path.join(dist, "viewer_standalone.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(SKELETON.format(body=body))
    return out


if __name__ == "__main__":
    print(main(sys.argv[1] if len(sys.argv) > 1 else None))
