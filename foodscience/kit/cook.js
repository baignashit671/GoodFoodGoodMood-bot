// "Didi": the GoodFoodGoodMood host, an Indian woman cook in a saree, built on the kit's Human (same rig + poses).
//   import { cook } from './core/cook.js';
//   const didi = cook();                      // or cook({ saree: '#1E7A5A', border: '#E9B53C', blouse: '#C1121F' })
//   didi.group.position.set(0, 0, -0.6); K.scene.add(didi.group); didi.pose({ ... })   // same pose() / setXray as Human
// Look: long dark hair with a middle parting, a long choti (plait) over the right shoulder with a red paranda, white gajra at the nape, kajal, red bindi, gold jhumkas + nose stud,
// short-sleeve blouse, saree (pleated lower drape with a gold border + pallu across the chest and down the back),
// glass bangles on both wrists, brown chappals. Keep the SAME colours every video (channel identity) unless a festival
// look is wanted. The saree hides the legs: she stands, turns and works at the counter; avoid big walking strides.
// Face material: clone only hero.parts.find(p => p.parent === hero.head) (the face), never the hair.
import * as THREE from 'three';
import { Human } from './human.js';
import { sphere, ellipsoid, capsule, smin, smax, ssub, noise3, mesh, rgb } from './sdf.js';

export const DIDI = { skin: '#B97D57', saree: '#C2185B', border: '#E9B53C', blouse: '#1F7A4D', hair: '#15100D', iris: '#2A1C12' };

const cache = new Map();
const once = (key, make) => { if (!cache.has(key)) cache.set(key, make()); return cache.get(key); };
const mixc = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
const sstep = (a, b, x) => { const t = Math.max(0, Math.min(1, (x - a) / (b - a))); return t * t * (3 - 2 * t); };

// the Human torso SDF (spine-local), copied so the pallu can hug it
function torso(p) {
  let d = ellipsoid(p, [0, 0.34, 0], [0.185, 0.165, 0.118]);
  d = smin(d, ellipsoid(p, [0, 0.13, 0.008], [0.162, 0.17, 0.112]), 0.08);
  d = smin(d, ellipsoid(p, [0, -0.04, 0], [0.165, 0.11, 0.108]), 0.07);
  return smin(d, capsule(p, [-0.165, 0.43, -0.005], [0.165, 0.43, -0.005], 0.062), 0.07);
}

export function cook(o = {}) {
  const c = { ...DIDI, ...o };
  const h = new Human({ skin: c.skin, shirt: c.blouse, pants: c.saree, shoes: '#6B3F22', hair: c.hair, iris: c.iris, scale: (o.scale || 1) * 0.96 });
  const K = JSON.stringify(c);
  const SA = rgb(c.saree), BO = rgb(c.border), HA = rgb(c.hair);
  const skinM = h.mat;
  const sareeM = new THREE.MeshPhysicalMaterial({ vertexColors: true, roughness: 0.42, sheen: 0.8, sheenRoughness: 0.35, sheenColor: new THREE.Color(c.border) });
  const hairM = new THREE.MeshPhysicalMaterial({ vertexColors: true, roughness: 0.38, clearcoat: 0.35, clearcoatRoughness: 0.4 });
  const gold = new THREE.MeshPhysicalMaterial({ color: '#E2B044', metalness: 0.9, roughness: 0.25 });
  const part = (parent, geo, mat, body = false) => { const m = new THREE.Mesh(geo, mat); m.castShadow = true; m.receiveShadow = true; parent.add(m); if (body) h.parts.push(m); return m; };

  // ── hair: hide the default short hair, sculpt long hair with a middle parting into a low bun ──
  const heads = h.parts.filter((p) => p.parent === h.head);
  if (heads[1]) { heads[1].visible = false; h.parts.splice(h.parts.indexOf(heads[1]), 1); h.head.remove(heads[1]); }
  part(h.head, once('dhair' + c.hair, () => mesh((p) => {
    let d = ellipsoid(p, [0, 0.165, -0.016], [0.123, 0.14, 0.133]);
    const line = 0.085 + 0.13 * sstep(-0.05, 0.11, p[2]);                                  // hairline: low at the back/sides, forehead clear
    d = smax(d, -(p[1] - line), 0.02);
    for (const s of [-1, 1]) {
      d = smin(d, ellipsoid(p, [s * 0.098, 0.17, 0.035], [0.034, 0.075, 0.07]), 0.035);     // soft side volume over the temples
      d = smin(d, ellipsoid(p, [s * 0.085, 0.095, -0.075], [0.04, 0.06, 0.05]), 0.03);      // hair tucked behind the ears
    }
    d = smin(d, ellipsoid(p, [0, 0.1, -0.12], [0.05, 0.045, 0.04]), 0.03);                  // where the choti starts
    d += 0.0025 * Math.abs(Math.sin((p[0] * 0.8 + p[2] * 0.4) * 230)) * sstep(0.1, 0.2, p[1]); // combed strands
    d = ssub(d, capsule(p, [0, 0.3, 0.02], [0, 0.235, 0.13], 0.004), 0.005);                // middle parting (maang)
    for (const s of [-1, 1]) d = Math.min(d, capsule(p, [s * 0.018, 0.16, 0.119], [s * 0.044, 0.168, 0.114], 0.0036, 0.0034), capsule(p, [s * 0.044, 0.168, 0.114], [s * 0.066, 0.16, 0.103], 0.0034, 0.0022)); // thin arched brows
    return d;
  }, [[-0.15, 0.02, -0.18], [0.15, 0.33, 0.16]], 0.0034, () => HA)), hairM);
  // choti: a long plait from the nape over the right shoulder, hanging down the front (on the spine so it follows the body)
  part(h.spine, once('choti' + c.hair, () => mesh((p) => {
    const P = [[0.04, 0.66, -0.1], [0.11, 0.6, -0.05], [0.15, 0.53, 0.04], [0.13, 0.43, 0.115], [0.115, 0.3, 0.135], [0.105, 0.17, 0.13], [0.1, 0.06, 0.12]];
    let d = 1;
    for (let i = 0; i < P.length - 1; i++) {
      const a = P[i], b = P[i + 1], r = 0.031 - i * 0.0026;
      for (let k = 0; k < 6; k++) { const t = (k + 0.5) / 6, q = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t], w = (i * 6 + k) % 2 ? 1 : -1;
        d = smin(d, ellipsoid(p, [q[0] + w * 0.0055, q[1], q[2]], [r, r * 1.15, r * 0.8]), 0.018); }
    }
    return d;
  }, [[-0.02, 0.0, -0.16], [0.21, 0.72, 0.18]], 0.0035, () => HA)), hairM);
  // paranda: red-and-gold tassel at the end of the choti
  { const t = new THREE.Group(); t.position.set(0.1, 0.045, 0.12); h.spine.add(t);
    const knot = new THREE.Mesh(new THREE.SphereGeometry(0.013, 12, 10), new THREE.MeshStandardMaterial({ color: '#C1121F', roughness: 0.4 })); t.add(knot);
    for (let i = 0; i < 3; i++) { const tas = new THREE.Mesh(new THREE.ConeGeometry(0.009, 0.05, 10), i === 1 ? gold : knot.material); tas.rotation.x = Math.PI; tas.position.set((i - 1) * 0.011, -0.03, 0); t.add(tas); } }
  // kajal on the upper lids + lip colour
  { const kajal = new THREE.MeshBasicMaterial({ color: '#120C0A' }), lipM = new THREE.MeshPhysicalMaterial({ color: '#A23B4C', roughness: 0.35, clearcoat: 0.5 });
    for (const s of [-1, 1]) { const k = new THREE.Mesh(new THREE.TorusGeometry(0.0236, 0.0016, 6, 24, Math.PI * 0.86), kajal); k.position.set(s * 0.041, 0.124, 0.093); k.rotation.set(0.12, 0, Math.PI * 0.07); h.head.add(k); }
    const up = new THREE.Mesh(new THREE.SphereGeometry(1, 20, 12), lipM); up.scale.set(0.022, 0.0055, 0.008); up.position.set(0, 0.046, 0.111); h.head.add(up);
    const lo = new THREE.Mesh(new THREE.SphereGeometry(1, 20, 12), lipM); lo.scale.set(0.019, 0.0065, 0.008); lo.position.set(0, 0.032, 0.109); h.head.add(lo); }
  // bindi, nose stud, jhumkas
  { const bindi = new THREE.Mesh(new THREE.CircleGeometry(0.0062, 24), new THREE.MeshStandardMaterial({ color: '#B3001B', roughness: 0.35 }));
    bindi.position.set(0, 0.164, 0.1175); bindi.rotation.x = -0.32; h.head.add(bindi);
    const stud = new THREE.Mesh(new THREE.SphereGeometry(0.0032, 10, 8), gold); stud.position.set(0.019, 0.083, 0.111); h.head.add(stud);
    for (const s of [-1, 1]) {
      const j = new THREE.Group(); j.position.set(s * 0.113, 0.066, -0.004);
      const top = new THREE.Mesh(new THREE.SphereGeometry(0.0045, 10, 8), gold); j.add(top);
      const bell = new THREE.Mesh(new THREE.ConeGeometry(0.011, 0.016, 16, 1, true), gold); bell.position.y = -0.013; bell.material.side = THREE.DoubleSide; j.add(bell);
      for (let i = 0; i < 6; i++) { const a = (i / 6) * Math.PI * 2, d = new THREE.Mesh(new THREE.SphereGeometry(0.0022, 6, 4), gold); d.position.set(Math.cos(a) * 0.011, -0.022, Math.sin(a) * 0.011); j.add(d); }
      h.head.add(j); (h.jhumka ||= []).push(j);
    }
  }
  // ── saree: pleated lower drape (on the hips) with a gold border ──
  part(h.hips, once('skirt' + K, () => mesh((p) => {
    const y = p[1], k = sstep(0.02, -0.86, y), r = 0.165 + 0.07 * k;                        // flares out towards the feet
    const a = Math.atan2(p[0], p[2]), pleat = 0.006 * Math.sin(a * 18) * sstep(0.35, 1.2, Math.cos(a)) * sstep(-0.1, -0.5, y);
    let d = ellipsoid([p[0], 0, p[2] - 0.005], [0, 0, 0], [r * 1.02, 1, r * 0.82]) * 1 + pleat;
    d = Math.max(d, y - 0.05, -0.875 - y);
    return d;
  }, [[-0.27, -0.9, -0.24], [0.27, 0.08, 0.26]], 0.006, (p) => (p[1] < -0.81 || (p[1] < -0.79 && p[1] > -0.8) ? BO : SA))), sareeM, true);
  // ── pallu: a band hugging the torso from the left shoulder across the chest to the right waist, then down the back ──
  part(h.spine, once('pallu' + K, () => mesh((p) => {
    const shell = Math.abs(torso(p) - 0.012) - 0.007;
    const n = [0.62, 0.78, 0], o = [-0.04, 0.27, 0];                                        // diagonal band (left shoulder → right hip)
    const band = Math.abs((p[0] - o[0]) * n[0] + (p[1] - o[1]) * n[1]) - 0.085;
    let d = smax(shell, band, 0.01);
    d = smax(d, -(p[1] + 0.02), 0.01);                                                      // ends at the waist
    let back = smax(shell, Math.max(Math.abs(p[0] + 0.115) - 0.075, p[2] + 0.01, -(p[1] + 0.06)), 0.008); // over the left shoulder and down the back
    back = smax(back, Math.max(-p[2] - 0.5, p[1] - 0.66), 0.001);
    d = Math.min(d, back);
    return d + 0.0012 * Math.sin(p[1] * 140 + p[0] * 60);
  }, [[-0.3, -0.12, -0.2], [0.3, 0.64, 0.2]], 0.0045, (p) => {
    const n = [0.62, 0.78], o = [-0.04, 0.27], e = Math.abs((p[0] - o[0]) * n[0] + (p[1] - o[1]) * n[1]);
    return e > 0.07 && p[2] > -0.1 ? BO : SA;                                               // gold border along both edges
  })), sareeM, true);
  // ── glass bangles (chudiyan) on both wrists ──
  for (const k of ['L', 'R']) {
    const cols = ['#E2B044', '#C1121F', '#1E8F4E', '#C1121F', '#E2B044'];
    cols.forEach((col, i) => {
      const t = new THREE.Mesh(new THREE.TorusGeometry(0.037, 0.0042, 8, 28), col === '#E2B044' ? gold : new THREE.MeshPhysicalMaterial({ color: col, roughness: 0.1, clearcoat: 1, transmission: 0.2 }));
      t.rotation.x = Math.PI / 2; t.position.set(0, -0.236 - i * 0.0095, 0.006); h.arm[k].el.add(t);
    });
  }
  h.isCook = true;
  return h;
}

// Desi touches for SETS.kitchen(E): a 2-burner gas stove (with optional blue flames), a steel masala dabba with 7 spices,
// a tiled backsplash and a steel lota. desiKitchen(K.scene) → { stove, flame(on), dabba, burners: [Vector3, Vector3] }
// The kitchen worktop is at y ≈ 0.955 and spans x -1.5..1.9, z -2.1..-1.4; the stove sits at x ≈ 0.15 (put the kadai on a burner).
export function desiKitchen(scene, o = {}) {
  const steel = new THREE.MeshPhysicalMaterial({ color: '#C9CED6', metalness: 0.95, roughness: 0.22 });
  const black = new THREE.MeshPhysicalMaterial({ color: '#1A1C20', metalness: 0.4, roughness: 0.3, clearcoat: 0.8 });
  const sh = (m) => { m.castShadow = true; m.receiveShadow = true; return m; };
  const x0 = o.x ?? 0.15, y0 = 0.955, z0 = o.z ?? -1.62;
  // tiles
  const tileTex = (() => { const cv = document.createElement('canvas'); cv.width = cv.height = 256; const g = cv.getContext('2d'); g.fillStyle = '#F4EFE6'; g.fillRect(0, 0, 256, 256); g.strokeStyle = '#D9CDB8'; g.lineWidth = 6; for (let i = 0; i <= 4; i++) { g.beginPath(); g.moveTo(i * 64, 0); g.lineTo(i * 64, 256); g.moveTo(0, i * 64); g.lineTo(256, i * 64); g.stroke(); } g.fillStyle = '#2F7F8F'; for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) if ((i + j) % 2) { g.beginPath(); g.arc(i * 64 + 32, j * 64 + 32, 9, 0, 7); g.fill(); } const t = new THREE.CanvasTexture(cv); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(8, 1.6); t.colorSpace = THREE.SRGBColorSpace; return t; })();
  const tiles = new THREE.Mesh(new THREE.PlaneGeometry(3.4, 0.62), new THREE.MeshStandardMaterial({ map: tileTex, roughness: 0.35 })); tiles.position.set(0.2, y0 + 0.31, -2.09); scene.add(tiles);
  // gas stove
  const stove = new THREE.Group(); stove.position.set(x0, y0, z0); scene.add(stove);
  const body = sh(new THREE.Mesh(new THREE.BoxGeometry(0.62, 0.07, 0.36), steel)); body.position.y = 0.035; stove.add(body);
  const top = sh(new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.008, 0.34), black)); top.position.y = 0.073; stove.add(top);
  const burners = [], flames = [];
  for (const s of [-1, 1]) {
    const bx = s * 0.15, ring = sh(new THREE.Mesh(new THREE.TorusGeometry(0.05, 0.008, 8, 24), black)); ring.rotation.x = Math.PI / 2; ring.position.set(bx, 0.085, 0); stove.add(ring);
    const cap = sh(new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.032, 0.012, 20), black)); cap.position.set(bx, 0.088, 0); stove.add(cap);
    for (let i = 0; i < 4; i++) { const a = i * Math.PI / 2 + Math.PI / 4, arm = sh(new THREE.Mesh(new THREE.BoxGeometry(0.09, 0.008, 0.008), black)); arm.position.set(bx + Math.cos(a) * 0.06, 0.1, Math.sin(a) * 0.06); arm.rotation.y = -a; stove.add(arm); }
    const knob = sh(new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.018, 0.02, 16), black)); knob.rotation.x = Math.PI / 2; knob.position.set(bx, 0.035, 0.19); stove.add(knob);
    const f = new THREE.Group(); f.position.set(bx, 0.095, 0); stove.add(f); f.visible = false; flames.push(f);
    const fm = new THREE.MeshBasicMaterial({ color: new THREE.Color('#3D7BFF').multiplyScalar(2.2), transparent: true, opacity: 0.85 });
    for (let i = 0; i < 14; i++) { const a = i / 14 * Math.PI * 2, c = new THREE.Mesh(new THREE.ConeGeometry(0.008, 0.035, 8), fm); c.position.set(Math.cos(a) * 0.036, 0.015, Math.sin(a) * 0.036); c.rotation.set(Math.sin(a) * 0.5, 0, -Math.cos(a) * 0.5); f.add(c); }
    burners.push(new THREE.Vector3(x0 + bx, y0 + 0.105, z0));
  }
  // masala dabba: round steel tin, 7 spice bowls
  const dabba = new THREE.Group(); dabba.position.set(o.dabbaX ?? -0.55, y0, -1.6); scene.add(dabba);
  const tin = sh(new THREE.Mesh(new THREE.CylinderGeometry(0.13, 0.13, 0.06, 40, 1, true), steel)); tin.position.y = 0.03; tin.material.side = THREE.DoubleSide; dabba.add(tin);
  const base = sh(new THREE.Mesh(new THREE.CylinderGeometry(0.13, 0.13, 0.006, 40), steel)); base.position.y = 0.003; dabba.add(base);
  const spices = ['#E8A317', '#B3261E', '#6B3E1F', '#F2D16B', '#3F5E2A', '#8B4A2B', '#D9A066'];
  spices.forEach((col, i) => { const a = i / 6 * Math.PI * 2, r = i === 6 ? 0 : 0.078, x = Math.cos(a) * r, z = Math.sin(a) * r;
    const bowl = sh(new THREE.Mesh(new THREE.CylinderGeometry(0.036, 0.03, 0.045, 24, 1, true), steel)); bowl.material.side = THREE.DoubleSide; bowl.position.set(x, 0.03, z); dabba.add(bowl);
    const pile = new THREE.Mesh(new THREE.SphereGeometry(0.033, 20, 10, 0, Math.PI * 2, 0, Math.PI / 2), new THREE.MeshStandardMaterial({ color: col, roughness: 0.95 })); pile.scale.y = 0.4; pile.position.set(x, 0.042, z); dabba.add(pile); });
  // steel lota
  const lota = sh(new THREE.Mesh(new THREE.LatheGeometry([[0, 0], [0.05, 0.005], [0.075, 0.06], [0.06, 0.11], [0.035, 0.14], [0.045, 0.165], [0.044, 0.17]].map(([x, y]) => new THREE.Vector2(x, y)), 32), steel));
  lota.position.set(o.lotaX ?? 1.0, y0, -1.75); scene.add(lota);
  return { stove, dabba, burners, flame(on = true, t = 0) { flames.forEach((f) => { f.visible = on; f.scale.setScalar(1 + 0.08 * Math.sin(t * 30)); }); } };
}
