// Food props for GoodFoodGoodMood Shorts, in the Deep Dive clay look (sculpted with the kit's SDF mesher).
// Every function returns a THREE.Group sitting on y = 0 (scale it to taste: 1 unit = 1 m, real food sizes).
//   import * as FOOD from './core/food.js';
//   const o = FOOD.onion(); o.position.set(0, 0.95, -1.5); K.scene.add(o);
// onion({ cut }) · chili({ color }) · tomato() · kadai() (wok) · tawa() · plate() · bowl({ fill }) · knife() · glass({ fill })
// · cup() (chai) · spoon() · steam(n) → { group, update(t, k) } rising steam puffs · cubes(n, color, size) → small pieces (chopped)
import * as THREE from 'three';
import { sphere, ellipsoid, capsule, torus, rbox, smin, smax, ssub, noise3, mesh } from './sdf.js';

const phys = (color, o = {}) => new THREE.MeshPhysicalMaterial({ color, roughness: 0.45, clearcoat: 0.4, ...o });
const shade = (m) => { m.castShadow = true; m.receiveShadow = true; return m; };
const M = (f, b, step, mat) => shade(new THREE.Mesh(mesh(f, b, step), mat));
const G = (...ms) => { const g = new THREE.Group(); ms.forEach((m) => g.add(m)); return g; };

export function onion({ cut = false, skin = '#8E3A59', flesh = '#F3E3EE' } = {}) {
  const body = (p) => smin(ellipsoid(p, [0, 0.045, 0], [0.045, 0.042, 0.045]), capsule(p, [0, 0.07, 0], [0, 0.1, 0], 0.006, 0.002), 0.02);
  if (!cut) return G(M(body, [[-0.06, -0.01, -0.06], [0.06, 0.11, 0.06]], 0.002, phys(skin, { roughness: 0.35, sheen: 0.4 })));
  // half onion: flat face with rings
  const half = (p) => smax(body(p), p[2], 0.002);
  const g = G(M(half, [[-0.06, -0.01, -0.06], [0.06, 0.11, 0.01]], 0.002, phys(skin, { roughness: 0.35 })));
  for (let r = 0.04; r > 0.006; r -= 0.007) { const ring = new THREE.Mesh(new THREE.RingGeometry(r - 0.0035, r, 48), new THREE.MeshStandardMaterial({ color: r > 0.035 ? '#C77BA0' : flesh, roughness: 0.3, side: THREE.DoubleSide })); ring.scale.y = 0.93; ring.position.set(0, 0.045, 0.0005); g.add(ring); }
  return g;
}
export function chili({ color = '#D62839' } = {}) {
  const f = (p) => { const b = 0.02 * Math.sin(p[0] * 25); return smin(capsule([p[0], p[1] - b, p[2]], [-0.06, 0.012, 0], [0.06, 0.012, 0], 0.011, 0.003), capsule(p, [-0.065, 0.012, 0], [-0.08, 0.025, 0], 0.004), 0.008); };
  const g = G(M(f, [[-0.09, -0.02, -0.02], [0.08, 0.05, 0.02]], 0.0015, phys(color, { roughness: 0.2, clearcoat: 1 })));
  const stem = new THREE.Mesh(new THREE.CapsuleGeometry(0.004, 0.02, 4, 8), phys('#4E8F3A')); stem.rotation.z = 1.2; stem.position.set(-0.085, 0.03, 0); g.add(stem); return g;
}
export function tomato() {
  const f = (p) => ellipsoid(p, [0, 0.03, 0], [0.034 + 0.002 * Math.cos(Math.atan2(p[2], p[0]) * 5), 0.03, 0.034]);
  const g = G(M(f, [[-0.045, -0.005, -0.045], [0.045, 0.065, 0.045]], 0.0018, phys('#E0442E', { roughness: 0.15, clearcoat: 1 })));
  for (let i = 0; i < 5; i++) { const l = new THREE.Mesh(new THREE.CapsuleGeometry(0.003, 0.012, 4, 8), phys('#3F7F33')); l.rotation.set(Math.PI / 2, 0, i * 1.26); l.position.set(Math.cos(i * 1.26) * 0.007, 0.06, Math.sin(i * 1.26) * 0.007); g.add(l); }
  return g;
}
export function kadai({ metal = '#3A3F45' } = {}) {
  const f = (p) => { let d = Math.abs(sphere(p, [0, 0.17, 0], 0.17)) - 0.004; d = smax(d, p[1] - 0.09, 0.004); for (const s of [-1, 1]) d = smin(d, torus(p, [s * 0.185, 0.085, 0], 0.025, 0.006), 0.006); return d; };
  return G(M(f, [[-0.23, -0.01, -0.18], [0.23, 0.12, 0.18]], 0.004, new THREE.MeshStandardMaterial({ color: metal, roughness: 0.35, metalness: 0.85 })));
}
export function tawa() {
  const g = G(shade(new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.14, 0.012, 64), new THREE.MeshStandardMaterial({ color: '#2B2E33', roughness: 0.5, metalness: 0.8 }))));
  const h = shade(new THREE.Mesh(new THREE.CapsuleGeometry(0.012, 0.14, 6, 12), phys('#5A3A22'))); h.rotation.z = Math.PI / 2; h.position.set(0.23, 0.01, 0); g.add(h); g.children[0].position.y = 0.006; return g;
}
export function plate({ color = '#F4F1EA', rim = '#D9B45A' } = {}) {
  const g = G(shade(new THREE.Mesh(new THREE.CylinderGeometry(0.13, 0.1, 0.015, 64), phys(color, { clearcoat: 1 }))));
  const r = new THREE.Mesh(new THREE.TorusGeometry(0.125, 0.004, 8, 64), new THREE.MeshStandardMaterial({ color: rim, metalness: 0.9, roughness: 0.3 })); r.rotation.x = Math.PI / 2; r.position.y = 0.015; g.add(r); g.children[0].position.y = 0.0075; return g;
}
export function bowl({ color = '#C8734A', fill = null, fillColor = '#E2A13B' } = {}) {
  const f = (p) => { let d = Math.abs(sphere(p, [0, 0.07, 0], 0.07)) - 0.004; return smax(d, p[1] - 0.065, 0.003); };
  const g = G(M(f, [[-0.08, -0.005, -0.08], [0.08, 0.075, 0.08]], 0.0025, phys(color, { clearcoat: 0.8 })));
  if (fill != null) { const y = 0.01 + fill * 0.05, rr = Math.sqrt(0.066 * 0.066 - (0.07 - y) * (0.07 - y)); const s = new THREE.Mesh(new THREE.CircleGeometry(rr, 48), phys(fillColor, { roughness: 0.2, clearcoat: 1 })); s.rotation.x = -Math.PI / 2; s.position.y = y; g.add(s); }
  return g;
}
export function knife() {
  const blade = shade(new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.035, 0.002), new THREE.MeshStandardMaterial({ color: '#D7DDE2', metalness: 1, roughness: 0.2 }))); blade.position.set(0.08, 0.018, 0);
  const handle = shade(new THREE.Mesh(new THREE.CapsuleGeometry(0.011, 0.09, 6, 12), phys('#2E2A26'))); handle.rotation.z = Math.PI / 2; handle.position.set(-0.05, 0.015, 0); return G(blade, handle);
}
export function glass({ fill = 0.7, fillColor = '#FFF6E8' } = {}) {
  const g = G(new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.03, 0.11, 48, 1, true), new THREE.MeshPhysicalMaterial({ color: '#FFFFFF', roughness: 0.05, transparent: true, opacity: 0.12, depthWrite: false, side: THREE.DoubleSide })));
  g.children[0].position.y = 0.055; const liq = shade(new THREE.Mesh(new THREE.CylinderGeometry(0.032, 0.029, 0.105 * fill, 48), phys(fillColor, { roughness: 0.15 }))); liq.position.y = 0.105 * fill / 2 + 0.002; g.add(liq); return g;
}
export function cup({ color = '#F4F1EA', tea = '#B87333' } = {}) {
  const c = shade(new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.026, 0.07, 48, 1, true), phys(color, { side: THREE.DoubleSide, clearcoat: 1 }))); c.position.y = 0.035;
  const t = new THREE.Mesh(new THREE.CircleGeometry(0.033, 48), phys(tea, { roughness: 0.1, clearcoat: 1 })); t.rotation.x = -Math.PI / 2; t.position.y = 0.06;
  const h = shade(new THREE.Mesh(new THREE.TorusGeometry(0.018, 0.005, 8, 24, Math.PI * 1.3), phys(color))); h.rotation.z = -Math.PI * 0.65; h.position.set(0.04, 0.04, 0);
  const b = shade(new THREE.Mesh(new THREE.CylinderGeometry(0.026, 0.026, 0.004, 32), phys(color))); b.position.y = 0.002; return G(c, t, h, b);
}
export function spoon() {
  const bowlM = M((p) => smax(ellipsoid(p, [0, 0, 0], [0.018, 0.006, 0.013]), -p[1] - 0.001, 0.002), [[-0.022, -0.01, -0.017], [0.022, 0.01, 0.017]], 0.0012, new THREE.MeshStandardMaterial({ color: '#CFD5DA', metalness: 1, roughness: 0.25 }));
  const st = shade(new THREE.Mesh(new THREE.CapsuleGeometry(0.003, 0.1, 4, 8), bowlM.material)); st.rotation.z = Math.PI / 2; st.position.x = 0.07; return G(bowlM, st);
}
/** rising steam (or smoke / gas: pass a colour). update(t, k) with k 0..1 amount */
export function steam(n = 24, color = '#FFFFFF') {
  const mat = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.25, depthWrite: false });
  const inst = new THREE.InstancedMesh(new THREE.SphereGeometry(1, 12, 8), mat, n); inst.frustumCulled = false; const g = G(inst);
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), v = new THREE.Vector3(), s = new THREE.Vector3();
  const r = (i) => { const x = Math.sin(i * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
  return { group: g, update(t, k = 1) { for (let i = 0; i < n; i++) { const ph = (t * 0.45 + r(i)) % 1; v.set((r(i + 3) - 0.5) * 0.06 + Math.sin(t * 2 + i) * 0.01 * ph, ph * 0.3, (r(i + 5) - 0.5) * 0.06); s.setScalar(k * (0.01 + 0.03 * ph)); m.compose(v, q, s); inst.setMatrixAt(i, m); } inst.instanceMatrix.needsUpdate = true; mat.opacity = 0.25 * k; } };
}
/** small chopped pieces scattered in a radius */
export function cubes(n = 20, color = '#F3E3EE', size = 0.008, radius = 0.05) {
  const r = (i) => { const x = Math.sin(i * 91.3 + 17.1) * 43758.5453; return x - Math.floor(x); };
  const g = new THREE.Group(), mat = phys(color);
  for (let i = 0; i < n; i++) { const c = shade(new THREE.Mesh(new THREE.BoxGeometry(size, size * 0.7, size), mat)); const a = r(i) * 6.28, d = Math.sqrt(r(i + 9)) * radius; c.position.set(Math.cos(a) * d, size * 0.35, Math.sin(a) * d); c.rotation.y = r(i + 4) * 3; g.add(c); }
  return g;
}
