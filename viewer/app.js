import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";
import { PLYLoader } from "three/examples/jsm/loaders/PLYLoader.js";

const $ = (id) => document.getElementById(id);
const TINTS = [0xf2f6f7, 0x8fd3ff, 0xffb48a, 0xb8f2a0, 0xd9b8ff, 0xf2e08a, 0x8af2e0, 0xf28ab8];
const hex = (c) => "#" + c.toString(16).padStart(6, "0");
const fmt = (n) => Math.round(n).toLocaleString("en-US");

// ------------------------------------------------------------------ loading → layers
// A layer = { name, geom (world-space, indexed, position only), tris, area, openEdges, isPoints }
function collectFromObject(root, fallbackName) {
  root.updateMatrixWorld(true);
  const out = [];
  root.traverse((o) => {
    if (!(o.isMesh || o.isPoints) || !o.geometry?.attributes?.position) return;
    let g = new THREE.BufferGeometry();
    g.setAttribute("position", o.geometry.attributes.position.clone());
    if (o.geometry.index) g.setIndex(o.geometry.index.clone());
    g.applyMatrix4(o.matrixWorld);
    let name = o.name || o.parent?.name || fallbackName;
    out.push({ name, geom: g, isPoints: !!o.isPoints });
  });
  return out;
}

export async function parseFile(name, buf) {
  const lower = name.toLowerCase(), base = name.replace(/\.[^.]+$/, "");
  if (lower.endsWith(".glb") || lower.endsWith(".gltf")) {
    const gltf = await new Promise((res, rej) => new GLTFLoader().parse(buf, "", res, rej));
    return collectFromObject(gltf.scene, base);
  }
  if (lower.endsWith(".stl")) return [{ name: base, geom: new STLLoader().parse(buf), isPoints: false }];
  if (lower.endsWith(".obj")) return collectFromObject(new OBJLoader().parse(new TextDecoder().decode(buf)), base);
  if (lower.endsWith(".ply")) {
    const g = new PLYLoader().parse(buf);
    return [{ name: base, geom: g, isPoints: !g.index }];
  }
  throw new Error("Unsupported file type. Use GLB, STL, OBJ or PLY.");
}

/** ct2mesh-layers/1: {layers: [{name, positions: b64 float32, indices: b64 uint32}]} */
function parseLayersJSON(doc) {
  const b64 = (s) => { const bin = atob(s), u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i); return u.buffer; };
  return doc.layers.map(L => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(b64(L.positions)), 3));
    g.setIndex(new THREE.BufferAttribute(new Uint32Array(b64(L.indices)), 1));
    return { name: L.name, geom: g, isPoints: false };
  });
}

/** Weld bit-identical vertices (STL repeats every corner per triangle) with an open-addressing
    hash over the float bits. Far faster and lighter than a string-keyed map on big files. */
function weld(P, I) {
  const nIn = P.length / 3, bits = new Uint32Array(P.buffer, P.byteOffset, P.length);
  let size = 1; while (size < nIn * 2) size <<= 1;
  const mask = size - 1, table = new Int32Array(size).fill(-1), remap = new Uint32Array(nIn);
  const outBits = new Uint32Array(P.length); let nOut = 0;
  for (let i = 0; i < nIn; i++) {
    let x = bits[3*i], y = bits[3*i+1], z = bits[3*i+2];
    if (x === 0x80000000) x = 0; if (y === 0x80000000) y = 0; if (z === 0x80000000) z = 0;   // -0 == 0
    let h = (Math.imul(x, 73856093) ^ Math.imul(y, 19349663) ^ Math.imul(z, 83492791)) & mask;
    for (;;) {
      const j = table[h];
      if (j < 0) { table[h] = nOut; outBits[3*nOut] = x; outBits[3*nOut+1] = y; outBits[3*nOut+2] = z; remap[i] = nOut++; break; }
      if (outBits[3*j] === x && outBits[3*j+1] === y && outBits[3*j+2] === z) { remap[i] = j; break; }
      h = (h + 1) & mask;
    }
  }
  const pos = new Float32Array(outBits.buffer, 0, nOut * 3).slice();
  const n = I ? I.length : nIn, idx = new Uint32Array(n);
  for (let k = 0; k < n; k++) idx[k] = remap[I ? I[k] : k];
  return { pos, idx };
}

/** Count edges not shared by exactly two triangles (holes, non-manifold seams) by sorting edge keys. */
function openEdgeCount(I, nv) {
  const nt = I.length / 3, keys = new Float64Array(nt * 3);
  for (let t = 0; t < nt; t++) for (let e = 0; e < 3; e++) {
    const u = I[3*t+e], v = I[3*t+(e+1)%3];
    keys[3*t+e] = u < v ? u * nv + v : v * nv + u;
  }
  keys.sort();
  let open = 0;
  for (let i = 0; i < keys.length;) { let j = i + 1; while (j < keys.length && keys[j] === keys[i]) j++; if (j - i !== 2) open++; i = j; }
  return open;
}

function analyse(L) {
  if (L.analysed) return L;
  const src = L.geom;
  if (L.isPoints) {
    const g = new THREE.BufferGeometry(); g.setAttribute("position", src.attributes.position);
    return Object.assign(L, { geom: g, tris: 0, area: 0, openEdges: 0, cum: null, analysed: true });
  }
  const P0 = src.attributes.position.array instanceof Float32Array ? src.attributes.position.array : Float32Array.from(src.attributes.position.array);
  const { pos: P, idx: I } = weld(P0, src.index ? src.index.array : null);
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(P, 3)); g.setIndex(new THREE.BufferAttribute(I, 1));
  const nt = I.length / 3, cum = new Float64Array(nt); let A = 0;
  for (let t = 0; t < nt; t++) {
    const a = 3*I[3*t], b = 3*I[3*t+1], c = 3*I[3*t+2];
    const ux = P[b]-P[a], uy = P[b+1]-P[a+1], uz = P[b+2]-P[a+2], vx = P[c]-P[a], vy = P[c+1]-P[a+1], vz = P[c+2]-P[a+2];
    const cx = uy*vz - uz*vy, cy = uz*vx - ux*vz, cz = ux*vy - uy*vx;
    A += Math.sqrt(cx*cx + cy*cy + cz*cz) / 2; cum[t] = A;
  }
  return Object.assign(L, { geom: g, tris: nt, area: A, openEdges: openEdgeCount(I, P.length / 3), cum, analysed: true });
}

// ------------------------------------------------------------------ dots (preview)
function mulberry32(a) { return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a);
  t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }

/** Area-weighted uniform samples on a layer's surface (raw model space). */
function sampleLayer(L, n, rng) {
  const P = L.geom.attributes.position.array;
  if (L.isPoints) {
    const m = P.length / 3, out = new Float32Array(Math.min(n, m) * 3);
    for (let k = 0; k < out.length / 3; k++) { const i = Math.floor(rng() * m); out.set(P.subarray(3*i, 3*i+3), 3*k); }
    return out;
  }
  const I = L.geom.index.array, cum = L.cum, A = L.area, nt = cum.length, out = new Float32Array(n * 3);
  for (let k = 0; k < n; k++) {
    const r = rng() * A; let lo = 0, hi = nt - 1;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (cum[mid] < r) lo = mid + 1; else hi = mid; }
    let u = rng(), v = rng(); if (u + v > 1) { u = 1 - u; v = 1 - v; }
    const i0 = 3*I[3*lo], i1 = 3*I[3*lo+1], i2 = 3*I[3*lo+2];
    for (let d = 0; d < 3; d++) out[3*k+d] = P[i0+d] + u * (P[i1+d] - P[i0+d]) + v * (P[i2+d] - P[i0+d]);
  }
  return out;
}

/** Greedy min-distance thinning in a fixed random order.
    r is the physical floor: no two dots of any layers end up closer than r.
    share[L] sets a layer's relative density: its own dots keep r/sqrt(share) apart, so share 0.25
    gives roughly a quarter of the dots, independent of r. */
export function thin(pts, layer, order, r, layerOn, share) {
  const n = pts.length / 3, OFF = 1 << 20, NX = 1 << 21, acc = [];
  const grids = new Map();                       // radius -> {inv, r2, cells}
  const gridFor = (rad) => { let g = grids.get(rad); if (!g) { g = { inv: 1 / rad, r2: rad * rad, cells: new Map() }; grids.set(rad, g); } return g; };
  const floor = gridFor(r);
  const own = []; for (let L = 0; L < share.length; L++) own[L] = share[L] >= 0.999 ? null : { ...gridFor(r / Math.sqrt(Math.max(share[L], 1e-3))), cells: new Map() };
  const clash = (g, x, y, z) => {
    const cx = Math.floor(x * g.inv) + OFF, cy = Math.floor(y * g.inv) + OFF, cz = Math.floor(z * g.inv) + OFF;
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) for (let dz = -1; dz <= 1; dz++) {
      const lst = g.cells.get((cx + dx) + (cy + dy) * NX + (cz + dz) * NX * NX); if (!lst) continue;
      for (let k = 0; k < lst.length; k++) { const j = lst[k], ax = pts[3*j]-x, ay = pts[3*j+1]-y, az = pts[3*j+2]-z;
        if (ax*ax + ay*ay + az*az < g.r2) return true; }
    }
    return false;
  };
  const put = (g, i, x, y, z) => {
    const key = (Math.floor(x * g.inv) + OFF) + (Math.floor(y * g.inv) + OFF) * NX + (Math.floor(z * g.inv) + OFF) * NX * NX;
    const lst = g.cells.get(key); if (lst) lst.push(i); else g.cells.set(key, [i]);
  };
  for (let q = 0; q < n; q++) {
    const i = order[q], L = layer[i];
    if (!layerOn[L]) continue;
    const x = pts[3*i], y = pts[3*i+1], z = pts[3*i+2], g = own[L];
    if (clash(floor, x, y, z) || (g && clash(g, x, y, z))) continue;
    put(floor, i, x, y, z); if (g) put(g, i, x, y, z);
    acc.push(i);
  }
  return Uint32Array.from(acc);
}

// ------------------------------------------------------------------ export helpers
const enc = new TextEncoder();
function stlBytes(L, s, c) {
  const P = L.geom.attributes.position.array, I = L.geom.index.array, nt = I.length / 3;
  const buf = new ArrayBuffer(84 + nt * 50), dv = new DataView(buf);
  enc.encodeInto("crystal-etch-preview " + L.name, new Uint8Array(buf, 0, 80));
  dv.setUint32(80, nt, true);
  const v = [new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()], e1 = new THREE.Vector3(), e2 = new THREE.Vector3();
  for (let t = 0; t < nt; t++) {
    for (let k = 0; k < 3; k++) { const i = I[3*t+k]; v[k].set((P[3*i]-c[0])*s, (P[3*i+1]-c[1])*s, (P[3*i+2]-c[2])*s); }
    const nrm = e1.subVectors(v[1], v[0]).cross(e2.subVectors(v[2], v[0])).normalize();
    let o = 84 + t * 50;
    for (const w of [nrm, v[0], v[1], v[2]]) { dv.setFloat32(o, w.x, true); dv.setFloat32(o+4, w.y, true); dv.setFloat32(o+8, w.z, true); o += 12; }
  }
  return new Uint8Array(buf);
}
function plyDots(pts, layer, idx, names) {
  const hdr = ["ply", "format binary_little_endian 1.0", "comment crystal-etch-preview dots", "comment units mm",
    ...names.map((n, i) => `comment layer ${i} ${n}`), `element vertex ${idx.length}`,
    "property float x", "property float y", "property float z", "property uchar layer", "end_header", ""].join("\n");
  const h = enc.encode(hdr), body = new DataView(new ArrayBuffer(idx.length * 13));
  idx.forEach((i, k) => { const b = 13*k; body.setFloat32(b, pts[3*i], true); body.setFloat32(b+4, pts[3*i+1], true);
    body.setFloat32(b+8, pts[3*i+2], true); body.setUint8(b+12, layer[i]); });
  const out = new Uint8Array(h.length + body.byteLength); out.set(h); out.set(new Uint8Array(body.buffer), h.length); return out;
}
const CRC = (() => { const t = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
function crc32(u8) { let c = 0xFFFFFFFF; for (let i = 0; i < u8.length; i++) c = CRC[(c ^ u8[i]) & 0xFF] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; }
/** Minimal stored (uncompressed) zip. */
export function zip(files) {
  const chunks = [], central = []; let off = 0;
  for (const f of files) {
    const nm = enc.encode(f.name), crc = crc32(f.data), sz = f.data.length;
    const lh = new DataView(new ArrayBuffer(30));
    lh.setUint32(0, 0x04034b50, true); lh.setUint16(4, 20, true); lh.setUint16(12, 0x5821, true);
    lh.setUint32(14, crc, true); lh.setUint32(18, sz, true); lh.setUint32(22, sz, true); lh.setUint16(26, nm.length, true);
    chunks.push(new Uint8Array(lh.buffer), nm, f.data);
    const ch = new DataView(new ArrayBuffer(46));
    ch.setUint32(0, 0x02014b50, true); ch.setUint16(4, 20, true); ch.setUint16(6, 20, true); ch.setUint16(14, 0x5821, true);
    ch.setUint32(16, crc, true); ch.setUint32(20, sz, true); ch.setUint32(24, sz, true); ch.setUint16(28, nm.length, true);
    ch.setUint32(42, off, true);
    central.push(new Uint8Array(ch.buffer), nm);
    off += 30 + nm.length + sz;
  }
  const cd = central.reduce((a, c) => a + c.length, 0), eo = new DataView(new ArrayBuffer(22));
  eo.setUint32(0, 0x06054b50, true); eo.setUint16(8, files.length, true); eo.setUint16(10, files.length, true);
  eo.setUint32(12, cd, true); eo.setUint32(16, off, true);
  return new Blob([...chunks, ...central, new Uint8Array(eo.buffer)], { type: "application/zip" });
}

// ------------------------------------------------------------------ state
const S = {
  source: "", layers: [], dims: [50, 50, 80], margin: 4, scale: 1, centre: [0, 0, 0],
  mode: "glass", tint: true, box: true, upY: false,
  // dots
  cand: null, candLayer: null, order: null, pts: null, idx: new Uint32Array(0),
  spacing: 0.2, dot: 1, rate: 1000, layerKeep: [],
};
window.__etch = { S, thin, zip, parseFile };   // test hooks

// ------------------------------------------------------------------ scene
const canvas = $("gl"), stage = $("stage");
let renderer;
try { renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true }); }
catch (e) { throw new Error("WebGL isn't available in this browser, so the 3D view can't start. Turn on hardware acceleration (or try another browser) and reload."); }
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setClearColor(0x04070a, 1);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 5000);
camera.up.set(0, 0, 1);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true; controls.dampingFactor = 0.08; controls.autoRotateSpeed = 1.2;
scene.add(new THREE.HemisphereLight(0xdfefff, 0x0b1116, 1.1));
const sun = new THREE.DirectionalLight(0xffffff, 1.6); sun.position.set(-40, -80, 120); scene.add(sun);

const blockGroup = new THREE.Group(), modelGroup = new THREE.Group(); scene.add(blockGroup, modelGroup);

const glassMat = (color) => new THREE.ShaderMaterial({
  transparent: true, depthWrite: false, side: THREE.DoubleSide, blending: THREE.AdditiveBlending,
  uniforms: { uColor: { value: new THREE.Color(color) } },
  vertexShader: `varying vec3 vN; varying vec3 vV;
    void main() { vec4 mv = modelViewMatrix * vec4(position, 1.0); vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz);
      gl_Position = projectionMatrix * mv; }`,
  fragmentShader: `uniform vec3 uColor; varying vec3 vN; varying vec3 vV;
    void main() { float f = 1.0 - abs(dot(normalize(vN), normalize(vV))); float a = 0.04 + 0.55 * pow(f, 2.5);
      gl_FragColor = vec4(uColor * a, a); }`,
});
const solidMat = (color) => new THREE.MeshStandardMaterial({ color, roughness: 0.55, metalness: 0.0, side: THREE.DoubleSide });

const dotMat = new THREE.ShaderMaterial({
  transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  uniforms: { uSize: { value: 1 }, uScale: { value: 1 }, uTint: { value: 1 }, uTints: { value: TINTS.map(c => new THREE.Color(c)) } },
  vertexShader: `attribute float aLayer; uniform float uSize; uniform float uScale; uniform float uTint; uniform vec3 uTints[8]; varying vec3 vCol;
    void main() { int l = int(mod(aLayer + 0.5, 8.0)); vec3 c = vec3(1.0);
      for (int k = 0; k < 8; k++) if (k == l) c = uTints[k];
      vCol = mix(vec3(0.92, 0.97, 1.0), c, uTint);
      vec4 mv = modelViewMatrix * vec4(position, 1.0); gl_PointSize = max(1.0, uSize * uScale / -mv.z); gl_Position = projectionMatrix * mv; }`,
  fragmentShader: `varying vec3 vCol; void main() { vec2 p = gl_PointCoord * 2.0 - 1.0; float d = dot(p, p); if (d > 1.0) discard;
      float a = smoothstep(1.0, 0.0, d); a = a * a * 0.85; gl_FragColor = vec4(vCol * a, a); }`,
});
let dotsObj = null;

function buildBlock() {
  blockGroup.clear();
  if (!S.box) return;
  const [w, d, h] = S.dims, m = S.margin;
  blockGroup.add(
    new THREE.Mesh(new THREE.BoxGeometry(w, d, h), new THREE.MeshBasicMaterial({ color: 0x6fc2b4, transparent: true, opacity: 0.035, depthWrite: false, side: THREE.BackSide })),
    new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(w, d, h)), new THREE.LineBasicMaterial({ color: 0x6fc2b4, transparent: true, opacity: 0.55 })));
  if (m > 0 && Math.min(w, d, h) > 2 * m) {
    const inner = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(w - 2*m, d - 2*m, h - 2*m)),
      new THREE.LineDashedMaterial({ color: 0x3b5a5a, dashSize: 1.2, gapSize: 1.2 }));
    inner.computeLineDistances(); blockGroup.add(inner);
  }
}

function resize() {
  const w = stage.clientWidth, h = stage.clientHeight;
  renderer.setSize(w, h, false); camera.aspect = w / Math.max(h, 1); camera.updateProjectionMatrix();
  dotMat.uniforms.uScale.value = h * renderer.getPixelRatio() * 0.02;
}
new ResizeObserver(resize).observe(stage);

function setView(kind) {
  const R = Math.max(...S.dims) * 2.6;
  const v = { front: [0, -1, 0.0001], side: [1, 0, 0.0001], top: [0, -0.0001, 1], iso: [0.75, -1, 0.55] }[kind];
  const len = Math.hypot(...v);
  camera.position.set(v[0] / len * R, v[1] / len * R, v[2] / len * R);
  controls.target.set(0, 0, 0); controls.update();
}

// ------------------------------------------------------------------ fit + render
let toastTimer;
function toast(msg) { const t = $("toast"); t.textContent = msg; t.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 4500); }

function refit() {
  const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
  for (const L of S.layers) {
    const P = L.geom.attributes.position.array;
    for (let i = 0; i < P.length; i += 3) for (let d = 0; d < 3; d++) { const v = P[i+d]; if (v < lo[d]) lo[d] = v; if (v > hi[d]) hi[d] = v; }
  }
  let s = Infinity;
  for (let d = 0; d < 3; d++) s = Math.min(s, (S.dims[d] - 2 * S.margin) / Math.max(hi[d] - lo[d], 1e-9));
  S.scale = s > 0 && isFinite(s) ? s : 1;
  S.centre = [0, 1, 2].map(d => (lo[d] + hi[d]) / 2);
  modelGroup.scale.setScalar(S.scale);
  modelGroup.position.set(-S.centre[0] * S.scale, -S.centre[1] * S.scale, -S.centre[2] * S.scale);
  if (S.cand) {   // dots live in glass mm
    S.pts = new Float32Array(S.cand.length);
    for (let i = 0; i < S.cand.length; i += 3) for (let d = 0; d < 3; d++) S.pts[i+d] = (S.cand[i+d] - S.centre[d]) * S.scale;
    rethin();
  }
  updateHud();
}

function buildMeshes() {
  modelGroup.clear();
  S.layers.forEach((L, i) => {
    const col = S.tint ? TINTS[i % TINTS.length] : 0xf2f6f7;
    let obj;
    if (L.isPoints) {
      obj = new THREE.Points(L.geom, new THREE.PointsMaterial({ color: col, size: 1.5, sizeAttenuation: false }));
    } else {
      if (!L.geom.attributes.normal) L.geom.computeVertexNormals();
      obj = new THREE.Mesh(L.geom, S.mode === "solid" ? solidMat(col) : glassMat(col));
      obj.renderOrder = i;
    }
    obj.visible = L.on && S.mode !== "dots";
    L.obj = obj; modelGroup.add(obj);
  });
  if (dotsObj) dotsObj.visible = S.mode === "dots";
}

function ensureCandidates() {
  if (S.cand) return;
  const totalArea = S.layers.reduce((a, L) => a + (L.isPoints ? 0 : L.area), 0);
  const N = 500000, rng = mulberry32(99), parts = [], labs = [];
  S.layers.forEach((L, i) => {
    const n = L.isPoints ? L.geom.attributes.position.count : Math.max(200, Math.round(N * L.area / Math.max(totalArea, 1e-9)));
    const p = sampleLayer(L, n, rng); parts.push(p); labs.push(new Uint8Array(p.length / 3).fill(i));
  });
  const tot = parts.reduce((a, p) => a + p.length, 0);
  S.cand = new Float32Array(tot); S.candLayer = new Uint8Array(tot / 3);
  let o = 0; parts.forEach((p, k) => { S.cand.set(p, o); S.candLayer.set(labs[k], o / 3); o += p.length; });
  const n = tot / 3;
  S.order = new Uint32Array(n);
  for (let i = 0; i < n; i++) S.order[i] = i;
  for (let i = n - 1; i > 0; i--) { const j = Math.floor(rng() * (i + 1)); const t = S.order[i]; S.order[i] = S.order[j]; S.order[j] = t; }
  refit();
}

function rethin() {
  if (!S.pts || S.mode !== "dots") return;
  const on = S.layers.map(L => L.on);
  S.idx = thin(S.pts, S.candLayer, S.order, S.spacing, on, S.layerKeep);
  const n = S.idx.length, pos = new Float32Array(n * 3), lay = new Float32Array(n);
  for (let k = 0; k < n; k++) { const i = S.idx[k]; pos.set(S.pts.subarray(3*i, 3*i+3), 3*k); lay[k] = S.candLayer[i]; }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3)); g.setAttribute("aLayer", new THREE.BufferAttribute(lay, 1));
  if (dotsObj) { dotsObj.geometry.dispose(); dotsObj.geometry = g; } else { dotsObj = new THREE.Points(g, dotMat); scene.add(dotsObj); }
  dotsObj.visible = true;
  updateHud();
}
let pending = 0;
function schedule() { cancelAnimationFrame(pending); pending = requestAnimationFrame(rethin); }

function updateHud() {
  const vis = S.layers.filter(L => L.on);
  const open = vis.filter(L => !L.isPoints && L.openEdges > 0);
  if (S.mode === "dots") {
    const n = S.idx.length;
    $("hudCount").textContent = fmt(n); $("hudUnit").textContent = "dots";
    $("hudA").textContent = `≥ ${S.spacing.toFixed(2)} mm apart · ${vis.length} layer${vis.length === 1 ? "" : "s"}`;
    const secs = n / Math.max(S.rate, 1);
    $("hudB").textContent = `≈ ${secs < 90 ? secs.toFixed(0) + " s" : (secs / 60).toFixed(1) + " min"} at ${fmt(S.rate)} dots/s`;
  } else {
    $("hudCount").textContent = fmt(vis.reduce((a, L) => a + L.tris, 0)); $("hudUnit").textContent = "triangles";
    $("hudA").textContent = `${vis.length} of ${S.layers.length} layer${S.layers.length === 1 ? "" : "s"} shown · ${open.length ? open.length + " open" : "all closed"}`;
    $("hudB").textContent = `surface ${fmt(vis.reduce((a, L) => a + L.area, 0) * S.scale * S.scale)} mm² of glass`;
  }
  $("hudC").textContent = `1 mm glass = ${(1 / S.scale).toFixed(2)} model units`;
  const w = $("hudWarn");
  if (S.mode === "dots" && S.spacing < 0.1) { w.textContent = "Under 0.10 mm, neighbouring fractures tend to merge or crack."; w.hidden = false; }
  else if (S.mode !== "dots" && open.length) { w.textContent = `Open edges on ${open.map(L => L.name).join(", ")}: some engraver software needs closed meshes.`; w.hidden = false; }
  else w.hidden = true;
  document.querySelectorAll("[data-count]").forEach(el => {
    const i = +el.dataset.count;
    el.textContent = S.mode === "dots" ? fmt(S.idx.reduce((a, j) => a + (S.candLayer[j] === i), 0)) + " dots" : "";
  });
}

function buildLayerUI() {
  const box = $("layers"); box.innerHTML = "";
  S.layers.forEach((L, i) => {
    const el = document.createElement("div"); el.className = "layer";
    el.innerHTML = `<input type="checkbox" id="lon${i}" ${L.on ? "checked" : ""}>
      <label for="lon${i}" class="lbl"><span class="swatch" style="background:${hex(TINTS[i % TINTS.length])}"></span></label>
      <span class="val" data-count="${i}"></span>
      <div class="meta"></div>
      <input type="range" id="lkeep${i}" min="0.02" max="1" step="0.01" value="${S.layerKeep[i]}" ${S.mode === "dots" ? "" : "hidden"}>`;
    el.querySelector("label").append(document.createTextNode(L.name));
    const meta = el.querySelector(".meta");
    if (L.isPoints) meta.textContent = `${fmt(L.geom.attributes.position.count)} points`;
    else {
      meta.textContent = `${fmt(L.tris)} tris · `;
      const s = document.createElement("span");
      s.textContent = L.openEdges ? `${fmt(L.openEdges)} open edges` : "closed"; if (L.openEdges) s.className = "bad";
      meta.append(s);
    }
    const rng = el.querySelector("input[type=range]"); rng.setAttribute("aria-label", `${L.name} dot share`);
    el.querySelector("input[type=checkbox]").addEventListener("change", e => {
      L.on = e.target.checked; if (L.obj) L.obj.visible = L.on && S.mode !== "dots"; rethin(); updateHud(); });
    rng.addEventListener("input", e => { S.layerKeep[i] = +e.target.value; schedule(); });
    box.append(el);
  });
}

function setLayers(layers, label, upY = S.upY) {
  S.layers = layers.map(analyse).map(L => ({ ...L, on: true }));
  setUpButtons(upY);
  if (upY) S.layers.forEach(L => L.geom.rotateX(Math.PI / 2));   // file's +Y becomes +Z (up)
  S.layerKeep = S.layers.map(L => /skin|shell|outline|body/i.test(L.name) ? 0.35 : /airway|lung/i.test(L.name) ? 0.5 : 1);
  S.cand = null; S.pts = null; S.idx = new Uint32Array(0);
  if (dotsObj) dotsObj.visible = false;
  const tris = S.layers.reduce((a, L) => a + L.tris, 0);
  $("srcInfo").textContent = `${label} · ${S.layers.length} layer${S.layers.length === 1 ? "" : "s"} · ${fmt(tris)} triangles`;
  S.source = label;
  buildLayerUI(); buildMeshes(); refit();
  if (S.mode === "dots") { ensureCandidates(); rethin(); }
  $("busy").hidden = true;
}

function setUpButtons(upY) {
  S.upY = upY; $("upZ").setAttribute("aria-pressed", String(!upY)); $("upY").setAttribute("aria-pressed", String(upY));
}
function setUpAxis(upY) {
  if (upY === S.upY) return;
  const ang = upY ? Math.PI / 2 : -Math.PI / 2;
  S.layers.forEach(L => L.geom.rotateX(ang));
  setUpButtons(upY);
  S.cand = null; S.pts = null; S.idx = new Uint32Array(0);
  buildMeshes(); refit();
  if (S.mode === "dots") { ensureCandidates(); rethin(); }
  setView("iso");
}

const tick = () => new Promise(r => setTimeout(r, 30));
const mb = (n) => (n / 1048576).toFixed(n < 10485760 ? 1 : 0) + " MB";
function busy(text) { const b = $("busy"); b.hidden = !text; if (text) b.textContent = text; }

async function loadFiles(files) {
  const label = files.length === 1 ? files[0].name : `${files.length} files`;
  try {
    const all = [];
    for (const f of files) {
      busy(`Reading ${f.name} (${mb(f.size)})…`); await tick();
      const buf = await f.arrayBuffer();
      busy(`Parsing ${f.name}…`); await tick();
      const layers = await parseFile(f.name, buf);
      for (const L of layers) {
        busy(`Checking ${L.name}: welding vertices and looking for holes…`); await tick();
        analyse(L);
      }
      all.push(...layers);
    }
    if (!all.length) throw new Error("no meshes or points found in it");
    const seen = {}; all.forEach(L => { seen[L.name] = (seen[L.name] || 0) + 1; if (seen[L.name] > 1) L.name += ` ${seen[L.name]}`; });
    busy("Building the preview…"); await tick();
    setLayers(all, label);
    busy("");
    toast(`Loaded ${label}`);
  } catch (e) {
    busy("");
    const msg = `Could not read ${label}: ${e?.message || e}`;
    $("srcInfo").textContent = msg;
    toast(msg);
    console.warn("load failed:", e);
  }
}

// The sample is embedded in the page (no network needed); a bare build falls back to sample.json.
let sampleDoc = null;
async function getSample() {
  if (sampleDoc) return sampleDoc;
  const inline = $("sampleData").textContent.trim();
  if (inline) sampleDoc = JSON.parse(inline);
  else { const r = await fetch("sample.json"); if (!r.ok) throw new Error(`sample.json: HTTP ${r.status}`); sampleDoc = await r.json(); }
  return sampleDoc;
}
async function loadSample() {
  $("busy").hidden = false; $("busy").textContent = "Loading sample model…";
  try {
    setLayers(parseLayersJSON(await getSample()), "sample chest (synthetic phantom)", false);
    setView("iso");
    toast("Loaded the sample chest");
  } catch (e) {
    $("busy").textContent = `Couldn't load the sample (${e.message}). Drop a GLB, STL, OBJ or PLY to start.`;
    toast(`Couldn't load the sample: ${e.message}`);
  }
}

function setMode(m) {
  S.mode = m;
  for (const [id, k] of [["mGlass", "glass"], ["mSolid", "solid"], ["mDots", "dots"]]) $(id).setAttribute("aria-pressed", String(k === m));
  $("dotsPanel").hidden = m !== "dots";
  document.querySelectorAll("[id^=lkeep]").forEach(r => { r.hidden = m !== "dots"; });
  $("expHint").textContent = m === "dots"
    ? "Saves the previewed dots (PLY, XYZ, DXF POINT entities) and each visible layer as a block-fitted STL, plus a settings file, in one zip."
    : "Saves each visible layer as an STL, scaled and positioned for the block, plus a settings file, in one zip.";
  buildMeshes();
  if (m === "dots") { ensureCandidates(); rethin(); } else if (dotsObj) dotsObj.visible = false;
  updateHud();
}

// ------------------------------------------------------------------ export
let downloads = null;
if (window.claude?.use) window.claude.use("downloads").then(d => { downloads = d; }).catch(() => {});
async function doExport() {
  const vis = S.layers.filter(L => L.on && !L.isPoints);
  if (!vis.length && S.mode !== "dots") { toast("Nothing to export. Load a model or show a layer."); return; }
  const files = vis.map(L => ({ name: `${L.name.replace(/[^\w.-]+/g, "_")}.stl`, data: stlBytes(L, S.scale, S.centre) }));
  const names = S.layers.map(L => L.name);
  const settings = { tool: "Crystal Etch Preview", source: S.source, block_mm: S.dims, margin_mm: S.margin,
    scale_glass_mm_per_model_unit: S.scale, coordinates: "mm, origin at block centre, +Z up, +Y away from the front face",
    layers: S.layers.map((L, i) => ({ name: L.name, shown: L.on, triangles: L.tris, open_edges: L.openEdges, dot_share: S.layerKeep[i] })) };
  if (S.mode === "dots" && S.idx.length) {
    const xyz = Array.from(S.idx, i => `${S.pts[3*i].toFixed(4)} ${S.pts[3*i+1].toFixed(4)} ${S.pts[3*i+2].toFixed(4)}`).join("\n") + "\n";
    const dxf = ["0\nSECTION\n2\nENTITIES\n", ...Array.from(S.idx, i => `0\nPOINT\n8\n${names[S.candLayer[i]]}\n10\n${S.pts[3*i].toFixed(4)}\n20\n${S.pts[3*i+1].toFixed(4)}\n30\n${S.pts[3*i+2].toFixed(4)}\n`), "0\nENDSEC\n0\nEOF\n"].join("");
    files.push({ name: "dots.ply", data: plyDots(S.pts, S.candLayer, S.idx, names) },
               { name: "dots.xyz", data: enc.encode(xyz) }, { name: "dots.dxf", data: enc.encode(dxf) });
    settings.dots = { count: S.idx.length, min_spacing_mm: +S.spacing.toFixed(4) };
  }
  files.push({ name: "settings.json", data: enc.encode(JSON.stringify(settings, null, 2)) });
  const blob = zip(files), filename = "crystal_block.zip";
  if (downloads) {
    try { await downloads.save({ filename, data: blob }); toast(`Saved ${filename}`); }
    catch (e) { toast(e?.code === "declined" ? "Export cancelled." : `Export isn't available in this view (${e?.code || "error"}).`); }
    return;
  }
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = filename;
  document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  toast(`Exported ${filename}`);
}

// ------------------------------------------------------------------ wiring
function readDims() {
  const v = ["cx", "cy", "cz"].map(id => Math.max(5, +$(id).value || 5));
  S.dims = v; S.margin = Math.max(0, Math.min(+$("cm").value || 0, Math.min(...v) / 2 - 0.5));
  buildBlock(); if (S.layers.length) refit();
}
["cx", "cy", "cz", "cm"].forEach(id => $(id).addEventListener("change", readDims));
$("mGlass").onclick = () => setMode("glass"); $("mSolid").onclick = () => setMode("solid"); $("mDots").onclick = () => setMode("dots");
$("tint").onclick = () => { S.tint = !S.tint; $("tint").setAttribute("aria-pressed", String(S.tint)); dotMat.uniforms.uTint.value = S.tint ? 1 : 0; buildMeshes(); };
$("showBox").onclick = () => { S.box = !S.box; $("showBox").setAttribute("aria-pressed", String(S.box)); buildBlock(); };
$("spacing").addEventListener("input", e => { S.spacing = +e.target.value; $("spacingVal").textContent = S.spacing.toFixed(2); schedule(); });
$("fitBudget").addEventListener("click", () => {
  if (!S.pts) return;
  const b = Math.max(100, +$("budget").value || 0), on = S.layers.map(L => L.on);
  let lo = 0.08, hi = 1.5, best = { r: S.spacing, err: Infinity };
  for (let it = 0; it < 22; it++) {
    const mid = Math.sqrt(lo * hi), n = thin(S.pts, S.candLayer, S.order, mid, on, S.layerKeep).length, err = Math.abs(n - b);
    if (err < best.err) best = { r: mid, err };
    if (err / b < 0.01) break;
    if (n > b) lo = mid; else hi = mid;
  }
  S.spacing = best.r; $("spacing").value = best.r; $("spacingVal").textContent = best.r.toFixed(2); rethin();
  if (Math.abs(S.idx.length - b) / b > 0.05) toast(`Closest reachable: ${fmt(S.idx.length)} dots at ${best.r.toFixed(2)} mm.`);
});
$("dot").addEventListener("input", e => { S.dot = +e.target.value; $("dotVal").textContent = S.dot.toFixed(1); dotMat.uniforms.uSize.value = S.dot; });
$("rate").addEventListener("input", e => { S.rate = Math.max(1, +e.target.value || 1); updateHud(); });
$("vFront").onclick = () => setView("front"); $("vSide").onclick = () => setView("side");
$("vTop").onclick = () => setView("top"); $("vIso").onclick = () => setView("iso");
$("vSpin").onclick = () => { controls.autoRotate = !controls.autoRotate; $("vSpin").setAttribute("aria-pressed", String(controls.autoRotate)); };
$("export").addEventListener("click", doExport);
$("loadSample").addEventListener("click", loadSample);
$("openFiles").addEventListener("click", () => $("file").click());
$("upZ").onclick = () => setUpAxis(false); $("upY").onclick = () => setUpAxis(true);
$("file").addEventListener("change", e => { if (e.target.files.length) loadFiles([...e.target.files]); e.target.value = ""; });
document.addEventListener("paste", e => { const fs = [...(e.clipboardData?.files || [])]; if (fs.length) { e.preventDefault(); loadFiles(fs); } });
$("drop").addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("file").click(); } });
for (const tgt of [$("drop"), stage]) {
  tgt.addEventListener("dragover", e => { e.preventDefault(); $("drop").classList.add("over"); });
  tgt.addEventListener("dragleave", () => $("drop").classList.remove("over"));
  tgt.addEventListener("drop", e => { e.preventDefault(); $("drop").classList.remove("over"); if (e.dataTransfer.files.length) loadFiles([...e.dataTransfer.files]); });
}

dotMat.uniforms.uSize.value = S.dot;
buildBlock(); resize(); setView("iso");
renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene, camera); });
window.__etchReady = true;
loadSample();
