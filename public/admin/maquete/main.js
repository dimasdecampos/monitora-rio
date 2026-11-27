import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const city = await (await fetch('data/city.json')).json();
const T = city.terrain;
const SKY = 0xbcd7ee;

// ---------- utilidades ----------
function mulberry32(a) { return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
const rng = mulberry32(1769);
const pick = a => a[Math.floor(rng() * a.length)];
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

let hMin = Infinity; for (const v of T.data) if (v < hMin) hMin = v;
function hAt(x, z) {
  const fx = clamp((x - T.x0) / (T.x1 - T.x0), 0, 1) * (T.nx - 1), fz = clamp((z - T.z0) / (T.z1 - T.z0), 0, 1) * (T.ny - 1);
  const i = Math.min(T.nx - 2, Math.floor(fx)), j = Math.min(T.ny - 2, Math.floor(fz)), u = fx - i, v = fz - j, d = T.data, k = j * T.nx + i;
  return (d[k] * (1 - u) * (1 - v) + d[k + 1] * u * (1 - v) + d[k + T.nx] * (1 - u) * v + d[k + T.nx + 1] * u * v) - hMin;
}

const ROAD_W = { primary: 9, primary_link: 7, secondary: 8, tertiary: 7, residential: 6, unclassified: 6, pedestrian: 6, living_street: 6, service: 4, track: 3, footway: 1.6, path: 1.4, steps: 1.6 };
const roadMid = r => { const k = (r.p.length >> 2) * 2; return Math.hypot(r.p[k], r.p[k + 1]); };

function trace(ctx, p, s, ox, oz, close) {
  ctx.beginPath();
  for (let i = 0; i < p.length; i += 2) { const x = (p[i] - ox) * s, y = (p[i + 1] - oz) * s; i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }
  if (close) ctx.closePath();
}

// ---------- cena ----------
const canvas = document.getElementById('cena');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
const scene = new THREE.Scene();
scene.background = new THREE.Color(SKY);
scene.fog = new THREE.Fog(SKY, 1400, 5200);
const camera = new THREE.PerspectiveCamera(45, 1, 2, 9000);

scene.add(new THREE.HemisphereLight(0xdcebff, 0x7a8456, 1.15));
const sun = new THREE.DirectionalLight(0xfff1d6, 2.6);
sun.position.set(-700, 1000, -650); // sol ao norte (hemisfério sul)
sun.castShadow = true;
sun.shadow.mapSize.set(4096, 4096);
Object.assign(sun.shadow.camera, { left: -950, right: 950, top: 950, bottom: -950, near: 100, far: 3200 });
sun.shadow.bias = -0.0006; sun.shadow.normalBias = 0.6;
scene.add(sun, sun.target);

// ---------- textura do terreno (ruas, rio, vegetação) ----------
function terrainTexture() {
  const W = 4096, s = W / (T.x1 - T.x0), Hh = Math.round((T.z1 - T.z0) * s);
  const c = document.createElement('canvas'); c.width = W; c.height = Hh;
  const g = c.getContext('2d');
  g.fillStyle = '#86a65a'; g.fillRect(0, 0, W, Hh);
  const r2 = mulberry32(7);
  for (let i = 0; i < 26000; i++) { // manchas de pasto
    g.fillStyle = pick2(r2, ['rgba(120,150,70,.18)', 'rgba(160,180,95,.16)', 'rgba(95,135,65,.16)', 'rgba(175,170,100,.10)']);
    const rr = 6 + r2() * 26; g.beginPath(); g.ellipse(r2() * W, r2() * Hh, rr, rr * (.5 + r2() * .6), r2() * 3, 0, 7); g.fill();
  }
  const fill = (p, col) => { trace(g, p, s, T.x0, T.z0, true); g.fillStyle = col; g.fill(); };
  const GREEN = { wood: '#4e7a3b', grass: '#93b565', park: '#8dbb62', pitch: '#74b157', cemetery: '#bdb9a6' };
  for (const a of city.green) if (a.t === 'wood') fill(a.p, GREEN.wood);
  for (const a of city.green) if (a.t !== 'wood' && GREEN[a.t]) fill(a.p, GREEN[a.t]);
  g.lineCap = g.lineJoin = 'round';
  // chão urbano em volta das ruas com casas
  for (const r of city.roads) {
    if (!(r.t === 'residential' || r.t === 'pedestrian' || (roadMid(r) < 600 && !['track', 'path', 'footway', 'steps', 'primary'].includes(r.t)))) continue;
    trace(g, r.p, s, T.x0, T.z0); g.strokeStyle = 'rgba(200,190,165,.5)'; g.lineWidth = 46 * s; g.stroke();
  }
  // água
  for (const r of city.rivers) {
    trace(g, r.p, s, T.x0, T.z0); g.strokeStyle = '#5b93ad'; g.lineWidth = (r.t === 'river' ? (r.w || 20) : 2.5) * s; g.stroke();
  }
  for (const w of city.water) fill(w, '#5b93ad');
  for (const w of city.water) { trace(g, w, s, T.x0, T.z0, true); g.strokeStyle = 'rgba(210,200,160,.7)'; g.lineWidth = 2 * s; g.stroke(); }
  // ruas
  const order = ['path', 'footway', 'steps', 'track', 'service', 'unclassified', 'residential', 'living_street', 'pedestrian', 'tertiary', 'secondary', 'primary_link', 'primary'];
  const roads = [...city.roads].sort((a, b) => order.indexOf(a.t) - order.indexOf(b.t));
  const colOf = r => ['primary', 'primary_link', 'secondary'].includes(r.t) ? '#77777c' : r.t === 'track' ? '#b59a6c' : ['footway', 'path', 'steps'].includes(r.t) ? '#dccfb2' : roadMid(r) < 480 ? '#b5aa99' : '#8f8f90';
  for (const pass of [0, 1]) for (const r of roads) {
    const w = ROAD_W[r.t]; if (!w) continue;
    if (r.a) { if (pass) fill(r.p, colOf(r)); continue; }
    if (!pass && w < 4) continue;
    trace(g, r.p, s, T.x0, T.z0);
    g.strokeStyle = pass ? colOf(r) : 'rgba(225,218,200,.95)'; g.lineWidth = (pass ? w : w + 2.6) * s; g.stroke();
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
  return tex;
}
function pick2(r, a) { return a[Math.floor(r() * a.length)]; }

{ // malha do terreno
  const pos = new Float32Array(T.nx * T.ny * 3), uv = new Float32Array(T.nx * T.ny * 2), idx = [];
  for (let j = 0; j < T.ny; j++) for (let i = 0; i < T.nx; i++) {
    const k = j * T.nx + i;
    pos[k * 3] = T.x0 + (T.x1 - T.x0) * i / (T.nx - 1); pos[k * 3 + 1] = T.data[k] - hMin; pos[k * 3 + 2] = T.z0 + (T.z1 - T.z0) * j / (T.ny - 1);
    uv[k * 2] = i / (T.nx - 1); uv[k * 2 + 1] = 1 - j / (T.ny - 1);
    if (i < T.nx - 1 && j < T.ny - 1) idx.push(k, k + T.nx, k + 1, k + 1, k + T.nx, k + T.nx + 1);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3)); geo.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
  geo.setIndex(idx); geo.computeVertexNormals();
  const mesh = new THREE.Mesh(geo, new THREE.MeshLambertMaterial({ map: terrainTexture() }));
  mesh.receiveShadow = true; scene.add(mesh);
}

// ---------- máscara de ocupação (R = bloqueado, G = mata) ----------
const MS = 0.5, MW = Math.ceil((T.x1 - T.x0) * MS), MH = Math.ceil((T.z1 - T.z0) * MS);
const mask = (() => {
  const c = document.createElement('canvas'); c.width = MW; c.height = MH;
  const g = c.getContext('2d', { willReadFrequently: true });
  g.fillStyle = '#000'; g.fillRect(0, 0, MW, MH); g.globalCompositeOperation = 'lighter'; g.lineCap = g.lineJoin = 'round';
  g.fillStyle = '#00ff00'; for (const a of city.green) if (a.t === 'wood') { trace(g, a.p, MS, T.x0, T.z0, true); g.fill(); }
  g.fillStyle = g.strokeStyle = '#ff0000';
  for (const a of city.green) if (['park', 'pitch', 'cemetery'].includes(a.t)) { trace(g, a.p, MS, T.x0, T.z0, true); g.fill(); }
  for (const w of city.water) { trace(g, w, MS, T.x0, T.z0, true); g.fill(); g.lineWidth = 8 * MS; g.stroke(); }
  for (const r of city.rivers) { trace(g, r.p, MS, T.x0, T.z0); g.lineWidth = (r.t === 'river' ? 34 : 6) * MS; g.stroke(); }
  for (const r of city.roads) { const w = ROAD_W[r.t] || 3; trace(g, r.p, MS, T.x0, T.z0, !!r.a); if (r.a) g.fill(); g.lineWidth = (w + 2) * MS; g.stroke(); }
  for (const b of city.buildings) { trace(g, b.p, MS, T.x0, T.z0, true); g.fill(); g.lineWidth = 2 * MS; g.stroke(); }
  return g.getImageData(0, 0, MW, MH).data;
})();
const mIdx = (x, z) => { const i = Math.floor((x - T.x0) * MS), j = Math.floor((z - T.z0) * MS); return i < 0 || j < 0 || i >= MW || j >= MH ? -1 : (j * MW + i) * 4; };
const blocked = (x, z) => { const k = mIdx(x, z); return k < 0 || mask[k] > 110; };
const wooded = (x, z) => { const k = mIdx(x, z); return k >= 0 && mask[k + 1] > 128; };
function obbFree(o, shrink) {
  const hu = o.hu - shrink, hv = o.hv;
  for (let a = -hu; a <= hu + .01; a += Math.min(2, Math.max(.5, hu))) for (let b = -hv + 2.2; b <= hv + .01; b += 2) {
    const x = o.cx + o.ux * a + o.vx * b, z = o.cz + o.uz * a + o.vz * b;
    if (blocked(x, z) || wooded(x, z)) return false;
  }
  return true;
}
function obbStamp(o) {
  const r = Math.hypot(o.hu, o.hv);
  for (let x = o.cx - r; x <= o.cx + r; x += 1 / MS) for (let z = o.cz - r; z <= o.cz + r; z += 1 / MS) {
    const dx = x - o.cx, dz = z - o.cz;
    if (Math.abs(dx * o.ux + dz * o.uz) <= o.hu && Math.abs(dx * o.vx + dz * o.vz) <= o.hv) { const k = mIdx(x, z); if (k >= 0) mask[k] = 255; }
  }
}

// ---------- geometria das construções ----------
const W = { pos: [], col: [], uv: [] }, R = { pos: [], col: [] };
const BLANK = [0.06, 0.5];
const tmpC = new THREE.Color();
function tri(buf, a, b, c, color, ua, ub, uc) {
  buf.pos.push(a[0], a[1], a[2], b[0], b[1], b[2], c[0], c[1], c[2]);
  tmpC.set(color); for (let i = 0; i < 3; i++) buf.col.push(tmpC.r, tmpC.g, tmpC.b);
  if (buf.uv) buf.uv.push(...(ua || BLANK), ...(ub || BLANK), ...(uc || BLANK));
}
function quad(buf, a, b, c, d, color, ua, ub, uc, ud) { tri(buf, a, b, c, color, ua, ub, uc); tri(buf, a, c, d, color, ua, uc, ud); }
function wall(ax, az, bx, bz, yBot, yFloor, yTop, levels, color, plain) {
  const L = Math.hypot(bx - ax, bz - az);
  if (yFloor > yBot + .05) quad(W, [ax, yBot, az], [bx, yBot, bz], [bx, yFloor, bz], [ax, yFloor, az], color);
  const bays = plain || L < 2.2 ? 0 : Math.max(1, Math.round(L / 3.3));
  if (!bays) quad(W, [ax, yFloor, az], [bx, yFloor, bz], [bx, yTop, bz], [ax, yTop, az], color);
  else quad(W, [ax, yFloor, az], [bx, yFloor, bz], [bx, yTop, bz], [ax, yTop, az], color, [0, 0], [bays, 0], [bays, levels], [0, levels]);
}
function box(o, y0, y1, color) {
  const c = [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([a, b]) => [o.cx + o.ux * o.hu * a + o.vx * o.hv * b, o.cz + o.uz * o.hu * a + o.vz * o.hv * b]);
  for (let i = 0; i < 4; i++) { const p = c[i], q = c[(i + 1) % 4]; quad(W, [p[0], y0, p[1]], [q[0], y0, q[1]], [q[0], y1, q[1]], [p[0], y1, p[1]], color); }
  return c;
}
function pyramid(o, y, h, color, over = .3) {
  const hu = o.hu + over, hv = o.hv + over;
  const c = [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([a, b]) => [o.cx + o.ux * hu * a + o.vx * hv * b, y, o.cz + o.uz * hu * a + o.vz * hv * b]);
  for (let i = 0; i < 4; i++) tri(R, c[i], c[(i + 1) % 4], [o.cx, y + h, o.cz], color);
}
function gable(o, y, rh, roofCol, wallCol, over = .45) { // cumeeira ao longo do eixo u
  const P = (a, b, yy) => [o.cx + o.ux * a + o.vx * b, yy, o.cz + o.uz * a + o.vz * b];
  const hu = o.hu + over, hv = o.hv + over;
  quad(R, P(-hu, -hv, y - .1), P(hu, -hv, y - .1), P(hu, 0, y + rh), P(-hu, 0, y + rh), roofCol);
  quad(R, P(hu, hv, y - .1), P(-hu, hv, y - .1), P(-hu, 0, y + rh), P(hu, 0, y + rh), roofCol);
  for (const sgn of [-1, 1]) tri(W, P(sgn * o.hu, -o.hv, y), P(sgn * o.hu, o.hv, y), P(sgn * o.hu, 0, y + rh * (o.hv / hv)), wallCol);
}
function polyArea(p) { let a = 0; for (let i = 0, n = p.length; i < n; i += 2) { const j = (i + 2) % n; a += p[i] * p[j + 1] - p[j] * p[i + 1]; } return Math.abs(a) / 2; }
function minOBB(p) {
  let best = null; const n = p.length;
  for (let i = 0; i < n; i += 2) {
    const j = (i + 2) % n; let ux = p[j] - p[i], uz = p[j + 1] - p[i + 1]; const L = Math.hypot(ux, uz); if (L < .3) continue; ux /= L; uz /= L;
    let a0 = Infinity, a1 = -Infinity, b0 = Infinity, b1 = -Infinity;
    for (let k = 0; k < n; k += 2) { const a = p[k] * ux + p[k + 1] * uz, b = -p[k] * uz + p[k + 1] * ux; a0 = Math.min(a0, a); a1 = Math.max(a1, a); b0 = Math.min(b0, b); b1 = Math.max(b1, b); }
    const area = (a1 - a0) * (b1 - b0);
    if (!best || area < best.area) { const ca = (a0 + a1) / 2, cb = (b0 + b1) / 2; best = { area, cx: ca * ux - cb * uz, cz: ca * uz + cb * ux, ux, uz, vx: -uz, vz: ux, hu: (a1 - a0) / 2, hv: (b1 - b0) / 2 }; }
  }
  if (best && best.hv > best.hu) best = { ...best, ux: best.vx, uz: best.vz, vx: -best.ux, vz: -best.uz, hu: best.hv, hv: best.hu };
  return best;
}

const CORES_CENTRO = ['#f6d98b', '#f2e6c9', '#e8a48c', '#a9c7e0', '#b9d8b0', '#f7f2e8', '#e9c46a', '#d98f7a', '#8fb6d9', '#f0c9d2', '#ffffff', '#f3b562', '#9fd0c4', '#f7f2e8'];
const CORES_BAIRRO = ['#f3eee2', '#ffffff', '#ece3cf', '#e9d9b6', '#dfe8ee', '#f1d9c9', '#e6e6e0', '#f6e7b8'];
const casas = [];
const TELHAS = ['#b5552f', '#a84d2c', '#c0623a', '#9c4a30', '#b86a45', '#a3573a'];

function building(p, opt) {
  const n = p.length / 2; let cx = 0, cz = 0, gMin = Infinity, gMax = -Infinity;
  for (let i = 0; i < p.length; i += 2) { cx += p[i]; cz += p[i + 1]; const h = hAt(p[i], p[i + 1]); gMin = Math.min(gMin, h); gMax = Math.max(gMax, h); }
  cx /= n; cz /= n;
  const yFloor = Math.max(hAt(cx, cz), gMax - 1.2), yTop = yFloor + opt.h, yBot = gMin - .6;
  casas.push({ x: cx, z: cz, piso: yFloor + hMin }); // para a simulação de enchente (altitude do piso)
  for (let i = 0; i < p.length; i += 2) { const j = (i + 2) % p.length; wall(p[i], p[i + 1], p[j], p[j + 1], yBot, yFloor, yTop, opt.levels, opt.color, opt.plain); }
  const o = opt.obb || minOBB(p);
  if (o && (opt.obb || polyArea(p) / (4 * o.hu * o.hv) > .78)) gable(o, yTop, opt.rh ?? clamp(o.hv * .5, 1, 3.2), opt.roof, opt.color);
  else {
    const tris = THREE.ShapeUtils.triangulateShape(Array.from({ length: n }, (_, i) => new THREE.Vector2(p[i * 2], p[i * 2 + 1])), []);
    for (const t of tris) tri(R, ...t.map(i => [p[i * 2], yTop + .25, p[i * 2 + 1]]), opt.roof);
    for (let i = 0; i < p.length; i += 2) { const j = (i + 2) % p.length; quad(R, [p[i], yTop - .15, p[i + 1]], [p[j], yTop - .15, p[j + 1]], [p[j], yTop + .25, p[j + 1]], [p[i], yTop + .25, p[i + 1]], opt.roof); }
  }
  return { cx, cz, yFloor, yTop, o };
}

// construções reais do mapa
for (const b of city.buildings) {
  const dc = Math.hypot(b.p[0], b.p[1]), centro = dc < 420, area = polyArea(b.p);
  if (b.k === 'church') {
    const matriz = /matriz/i.test(b.n || ''), historic = /matriz|ros[aá]rio|merc[eê]s|prazeres|benedito/i.test(b.n || '');
    const h = b.h || (matriz ? 14 : historic ? 8.5 : 6);
    const r = building(b.p, { h, levels: 1, color: historic ? '#f7f1e3' : '#ebe6da', roof: '#a84d2c', plain: true });
    const o = r.o; if (!o || !historic) continue;
    const f = Math.sign((0 - o.cx) * o.ux + (0 - o.cz) * o.uz) || 1; // fachada voltada para o centro
    const ts = clamp(o.hv * .42, 1.6, 3.2), yB = hAt(o.cx, o.cz) - .6;
    const tower = (side, th) => { const t = { ...o, cx: o.cx + o.ux * f * (o.hu - ts) + o.vx * side * (o.hv - ts), cz: o.cz + o.uz * f * (o.hu - ts) + o.vz * side * (o.hv - ts), hu: ts, hv: ts }; box(t, yB, r.yFloor + th, '#fbf6ea'); pyramid(t, r.yFloor + th, ts * 2, '#8a5a3c'); };
    if (matriz) { tower(-1, 25); tower(1, 25); } else if (/ros[aá]rio/i.test(b.n)) tower(0, 19); else tower(0, h + 3.5);
    continue;
  }
  const levels = b.lv || (centro && area > 260 ? 2 : 1), fh = centro ? 3.9 : 3.3;
  building(b.p, { h: b.h || levels * fh + .3, levels, color: b.k === 'civic' ? '#f4ecd8' : pick(centro ? CORES_CENTRO : CORES_BAIRRO), roof: pick(TELHAS) });
}

// casario preenchido ao longo das ruas (o mapa aberto só tem parte das casas)
let geradas = 0;
for (const r of city.roads) {
  if (r.b || r.a) continue;
  const hw = (ROAD_W[r.t] || 0) / 2, p = r.p;
  const base = ['residential', 'pedestrian', 'living_street'].includes(r.t) ? 1 : ['tertiary', 'secondary', 'unclassified'].includes(r.t) ? 2 : r.t === 'primary' ? 3 : 0;
  if (!base) continue;
  for (let i = 0; i + 3 < p.length; i += 2) {
    const ax = p[i], az = p[i + 1], dx0 = p[i + 2] - ax, dz0 = p[i + 3] - az, L = Math.hypot(dx0, dz0); if (L < 5.6) continue;
    const ux = dx0 / L, uz = dz0 / L;
    for (const side of [1, -1]) {
      const vx = -uz * side, vz = ux * side; let s = rng() * 1.2;
      while (s + 4.6 < L) {
        const mx = ax + ux * s, mz = az + uz * s, dc = Math.hypot(mx, mz), centro = dc < 400;
        const w = centro ? 5 + rng() * 4.5 : 7 + rng() * 5; if (s + w > L - .3) break;
        const dep = centro ? 10 + rng() * 6 : 8.5 + rng() * 5;
        const prob = base === 1 ? (dc < 1400 ? .93 : .6) : base === 2 ? clamp(1.2 - dc / 750, 0, .93) : clamp(.9 - dc / 450, 0, .8);
        if (rng() < prob) {
          const off = hw + 1.5 + dep / 2 + (centro ? 0 : rng() * 3);
          const o = { cx: ax + ux * (s + w / 2) + vx * off, cz: az + uz * (s + w / 2) + vz * off, ux, uz, vx, vz, hu: w / 2, hv: dep / 2 };
          const hs = [[0, 0], [-1, -1], [1, -1], [1, 1], [-1, 1]].map(([a, b]) => hAt(o.cx + ux * o.hu * a + vx * o.hv * b, o.cz + uz * o.hu * a + vz * o.hv * b));
          if (Math.max(...hs) - Math.min(...hs) < 4.2 && obbFree(o, 1.5)) {
            obbStamp(o);
            const levels = rng() < (dc < 240 ? .34 : .07) ? 2 : 1, fh = centro ? 3.8 : 3.1;
            const c = [[-1, -1], [1, -1], [1, 1], [-1, 1]].flatMap(([a, b]) => [o.cx + ux * o.hu * a + vx * o.hv * b, o.cz + uz * o.hu * a + vz * o.hv * b]);
            building(c, { h: levels * fh + .3 + rng() * .5, levels, color: pick(centro ? CORES_CENTRO : CORES_BAIRRO), roof: pick(TELHAS), obb: o, rh: clamp(o.hv * .42, 1.2, 3) });
            geradas++;
          }
        }
        s += w + (centro ? (rng() < .12 ? 1.5 : 0) : 1.5 + rng() * 5);
      }
    }
  }
}

function facadeTexture() {
  const c = document.createElement('canvas'); c.width = c.height = 128; const g = c.getContext('2d');
  g.fillStyle = '#fff'; g.fillRect(0, 0, 128, 128);
  g.fillStyle = '#d9d9d9'; g.fillRect(0, 112, 128, 16);          // barrado
  g.fillStyle = '#ececec'; g.fillRect(0, 0, 128, 7);              // cimalha
  g.fillStyle = '#8d8d8d'; g.fillRect(41, 30, 46, 66);            // moldura
  g.fillStyle = '#27323d'; g.fillRect(46, 35, 36, 56);            // vidro
  g.fillStyle = '#8d8d8d'; g.fillRect(63, 35, 2, 56); g.fillRect(46, 62, 36, 2);
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t;
}
function meshFrom(buf, mat) {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(buf.pos, 3)); g.setAttribute('color', new THREE.Float32BufferAttribute(buf.col, 3));
  if (buf.uv) g.setAttribute('uv', new THREE.Float32BufferAttribute(buf.uv, 2));
  g.computeVertexNormals(); const m = new THREE.Mesh(g, mat); m.castShadow = m.receiveShadow = true; scene.add(m); return m;
}
meshFrom(W, new THREE.MeshLambertMaterial({ vertexColors: true, map: facadeTexture(), side: THREE.DoubleSide }));
meshFrom(R, new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide }));

{ // coreto da praça
  const y = hAt(0, 0), g = new THREE.Group(), white = new THREE.MeshLambertMaterial({ color: 0xf5efe2 });
  const basec = new THREE.Mesh(new THREE.CylinderGeometry(4.2, 4.5, 1.2, 8), white); basec.position.y = .6;
  const roof = new THREE.Mesh(new THREE.ConeGeometry(5.2, 2.2, 8), new THREE.MeshLambertMaterial({ color: 0x9c4a30, flatShading: true })); roof.position.y = 5.3;
  g.add(basec, roof);
  for (let i = 0; i < 8; i++) { const a = i / 8 * Math.PI * 2 + Math.PI / 8, c = new THREE.Mesh(new THREE.CylinderGeometry(.14, .14, 3.2, 6), white); c.position.set(Math.cos(a) * 3.9, 2.8, Math.sin(a) * 3.9); g.add(c); }
  g.traverse(m => { m.castShadow = true; }); g.position.set(0, y, 0); scene.add(g);
}

{ // árvores
  const pts = [];
  for (let i = 0; i < 90000 && pts.length < 15000; i++) {
    const x = T.x0 + rng() * (T.x1 - T.x0), z = T.z0 + rng() * (T.z1 - T.z0); if (blocked(x, z)) continue;
    if (wooded(x, z) ? rng() < .6 : (Math.hypot(x, z) > 260 && rng() < .022)) pts.push([x, z, 3 + rng() * 3.6]);
  }
  for (const a of city.green) if (a.t === 'park') { // arborização das praças
    let x0 = Infinity, x1 = -Infinity, z0 = Infinity, z1 = -Infinity;
    for (let i = 0; i < a.p.length; i += 2) { x0 = Math.min(x0, a.p[i]); x1 = Math.max(x1, a.p[i]); z0 = Math.min(z0, a.p[i + 1]); z1 = Math.max(z1, a.p[i + 1]); }
    const nT = Math.min(60, polyArea(a.p) / 140);
    for (let k = 0, tries = 0; k < nT && tries < 600; tries++) {
      const x = x0 + rng() * (x1 - x0), z = z0 + rng() * (z1 - z0); let inside = false;
      for (let i = 0, j = a.p.length - 2; i < a.p.length; j = i, i += 2) if ((a.p[i + 1] > z) !== (a.p[j + 1] > z) && x < (a.p[j] - a.p[i]) * (z - a.p[i + 1]) / (a.p[j + 1] - a.p[i + 1]) + a.p[i]) inside = !inside;
      if (inside && Math.hypot(x, z) > 9) { pts.push([x, z, 2.2 + rng() * 1.6]); k++; }
    }
  }
  const im = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(1, 0), new THREE.MeshLambertMaterial({ flatShading: true }), pts.length);
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler(), col = new THREE.Color();
  pts.forEach(([x, z, r], i) => {
    e.set(0, rng() * 6.3, 0); q.setFromEuler(e);
    m.compose(new THREE.Vector3(x, hAt(x, z) + r * .95, z), q, new THREE.Vector3(r, r * (1.1 + rng() * .5), r)); im.setMatrixAt(i, m);
    im.setColorAt(i, col.setHSL(.27 + rng() * .08, .42 + rng() * .2, .2 + rng() * .13));
  });
  im.castShadow = true; im.receiveShadow = true; scene.add(im);
}

// ---------- rótulos e navegação ----------
const controls = new OrbitControls(camera, canvas);
Object.assign(controls, { enableDamping: true, dampingFactor: .08, maxPolarAngle: Math.PI * .47, minDistance: 35, maxDistance: 3200, zoomSpeed: 1.1 });

const curtos = [[/matriz/i, 'Igreja Matriz'], [/ros[aá]rio/i, 'Igreja do Rosário'], [/merc[eê]s/i, 'Capela das Mercês'], [/prazeres/i, 'Capela N. Sra. dos Prazeres'], [/benedito/i, 'Igreja São Benedito'],
  [/^praça doutor oswaldo cruz/i, 'Praça Oswaldo Cruz'], [/^casa de oswaldo cruz/i, 'Casa de Oswaldo Cruz'], [/largo do teatro/i, 'Largo do Teatro'], [/prefeitura/i, 'Prefeitura'],
  [/cruzeiro/i, 'Praça do Cruzeiro'], [/santa casa/i, 'Santa Casa'], [/museu/i, 'Museu'], [/f[oó]rum/i, 'Fórum']];
const lugares = [];
for (const [re, nome] of curtos) { const p = city.pois.find(p => re.test(p.n)); if (p) lugares.push({ nome, x: p.x, z: p.z, alto: /Igreja|Capela/.test(nome) ? 30 : 16 }); }
{ // ponto do rio mais próximo do centro
  const rio = city.rivers.find(r => r.t === 'river'); let best = null;
  if (rio) for (let i = 0; i < rio.p.length; i += 2) { const d = Math.hypot(rio.p[i] + 20, rio.p[i + 1] - 300); if (!best || d < best.d) best = { d, x: rio.p[i], z: rio.p[i + 1] }; }
  if (best) lugares.push({ nome: 'Rio Paraitinga', x: best.x, z: best.z, alto: 10 });
}
const rotulos = document.getElementById('rotulos'), botoes = document.getElementById('lugares');
for (const l of lugares) {
  l.pos = new THREE.Vector3(l.x, hAt(l.x, l.z) + l.alto, l.z);
  l.el = Object.assign(document.createElement('div'), { className: 'rotulo', textContent: l.nome }); rotulos.append(l.el);
}
let voo = null;
function voar(tx, tz, dist = 230, dur = 1600) {
  const t1 = new THREE.Vector3(tx, hAt(tx, tz) + 4, tz), dir = camera.position.clone().sub(controls.target).setY(0).normalize();
  const c1 = t1.clone().addScaledVector(dir, dist * .8); c1.y = t1.y + dist * .55;
  voo = { t0: performance.now(), dur, c0: camera.position.clone(), c1, g0: controls.target.clone(), g1: t1 };
}
const btn = (nome, fn) => { const b = Object.assign(document.createElement('button'), { textContent: nome }); b.onclick = fn; botoes.append(b); };
btn('Visão geral', () => voar(60, 60, 1500));
for (const l of lugares.slice(0, 8).concat(lugares.filter(l => l.nome === 'Rio Paraitinga'))) btn(l.nome, () => voar(l.x, l.z));

camera.position.set(-420, hAt(0, 0) + 360, 640); controls.target.set(40, hAt(40, 30), 30);
{ // link direto para uma vista: #v=camX,camY,camZ,alvoX,alvoZ
  const m = location.hash.match(/v=([-\d.,]+)/), n = m ? m[1].split(',').map(Number) : [];
  if (n.length === 5 && n.every(Number.isFinite)) { camera.position.set(n[0], n[1], n[2]); controls.target.set(n[3], hAt(n[3], n[4]) + 4, n[4]); }
}
sun.target.position.set(100, 0, 100);

function resize() { const w = innerWidth, h = innerHeight; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); }
addEventListener('resize', resize); resize();

const v = new THREE.Vector3();
renderer.setAnimationLoop(() => {
  if (voo) {
    let k = clamp((performance.now() - voo.t0) / voo.dur, 0, 1); const e = k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
    camera.position.lerpVectors(voo.c0, voo.c1, e); controls.target.lerpVectors(voo.g0, voo.g1, e); if (k >= 1) voo = null;
  }
  controls.target.x = clamp(controls.target.x, T.x0 + 200, T.x1 - 200); controls.target.z = clamp(controls.target.z, T.z0 + 200, T.z1 - 200);
  controls.update();
  const ground = hAt(camera.position.x, camera.position.z) + 6; if (camera.position.y < ground) camera.position.y = ground;
  renderer.render(scene, camera);
  const w = innerWidth, h = innerHeight;
  for (const l of lugares) {
    v.copy(l.pos).project(camera); const d = camera.position.distanceTo(l.pos);
    const vis = v.z < 1 && Math.abs(v.x) < 1.05 && Math.abs(v.y) < 1.05 && d < 2600;
    l.el.style.opacity = vis ? (d > 1700 ? .55 : 1) : 0;
    if (vis) l.el.style.transform = `translate(-50%,-100%) translate(${((v.x + 1) / 2 * w).toFixed(1)}px,${((1 - v.y) / 2 * h - 14).toFixed(1)}px)`;
  }
});

console.log(`[cidade3d] ${city.buildings.length} construções do mapa + ${geradas} casas geradas ao longo das ruas`);
// ---------- simulação de enchente (aba do painel, /cidade3d/?embed) ----------
// Modelo "banheira conectada": a água fica num nível plano (altitude em metros) e só ocupa o que está abaixo desse nível
// E ligado ao Rio Paraitinga por terreno também abaixo dele (baixadas isoladas ficam secas). Usa a mesma grade de relevo.
const sementesRio = (() => {
  const s = new Set(), dx = (T.x1 - T.x0) / (T.nx - 1), dz = (T.z1 - T.z0) / (T.ny - 1);
  for (const r of city.rivers) {
    if (r.t !== 'river') continue;
    for (let k = 0; k + 3 < r.p.length; k += 2) {
      const n = Math.ceil(Math.hypot(r.p[k + 2] - r.p[k], r.p[k + 3] - r.p[k + 1]) / 5);
      for (let q = 0; q <= n; q++) {
        const i = Math.round((r.p[k] + (r.p[k + 2] - r.p[k]) * q / n - T.x0) / dx), j = Math.round((r.p[k + 1] + (r.p[k + 3] - r.p[k + 1]) * q / n - T.z0) / dz);
        if (i >= 0 && j >= 0 && i < T.nx && j < T.ny) s.add(j * T.nx + i);
      }
    }
  }
  return [...s];
})();
let agua = null;
const corRasa = new THREE.Color('#8fa9a6'), corFunda = new THREE.Color('#3f5560'), corTmp = new THREE.Color();
function enchente(nivel) {
  if (agua) { scene.remove(agua); agua.geometry.dispose(); agua = null; }
  const { nx, ny, data } = T, f = new Uint8Array(nx * ny), fila = [];
  for (const s of sementesRio) if (data[s] < nivel && !f[s]) { f[s] = 1; fila.push(s); }
  while (fila.length) {
    const s = fila.pop(), i = s % nx, j = (s - i) / nx;
    if (i > 0 && !f[s - 1] && data[s - 1] < nivel) { f[s - 1] = 1; fila.push(s - 1); }
    if (i < nx - 1 && !f[s + 1] && data[s + 1] < nivel) { f[s + 1] = 1; fila.push(s + 1); }
    if (j > 0 && !f[s - nx] && data[s - nx] < nivel) { f[s - nx] = 1; fila.push(s - nx); }
    if (j < ny - 1 && !f[s + nx] && data[s + nx] < nivel) { f[s + nx] = 1; fila.push(s + nx); }
  }
  // superfície plana em cada célula que toca um ponto alagado; o próprio terreno esconde a parte acima da água (margem exata da malha)
  const vert = new Int32Array(nx * ny).fill(-1), pos = [], col = [], idx = [], y = nivel - hMin;
  const v = k => {
    if (vert[k] < 0) {
      vert[k] = pos.length / 3; const i = k % nx, j = (k - i) / nx;
      pos.push(T.x0 + (T.x1 - T.x0) * i / (nx - 1), y, T.z0 + (T.z1 - T.z0) * j / (ny - 1));
      corTmp.lerpColors(corRasa, corFunda, clamp((nivel - data[k]) / 6, 0, 1)); col.push(corTmp.r, corTmp.g, corTmp.b);
    }
    return vert[k];
  };
  let pontos = 0;
  for (let j = 0; j < ny - 1; j++) for (let i = 0; i < nx - 1; i++) {
    const k = j * nx + i; if (f[k]) pontos++;
    if (f[k] || f[k + 1] || f[k + nx] || f[k + nx + 1]) idx.push(v(k), v(k + nx), v(k + 1), v(k + 1), v(k + nx), v(k + nx + 1));
  }
  if (idx.length) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
    g.setIndex(idx); g.computeVertexNormals();
    agua = new THREE.Mesh(g, new THREE.MeshPhongMaterial({ vertexColors: true, transparent: true, opacity: .9, shininess: 70, specular: 0x55504a }));
    agua.receiveShadow = true; agua.renderOrder = 2; scene.add(agua);
  }
  // o que a água alcança: casas (pelo piso) e lugares com nome
  const no = (x, z) => { const i = Math.round((x - T.x0) / (T.x1 - T.x0) * (nx - 1)), j = Math.round((z - T.z0) / (T.z1 - T.z0) * (ny - 1)); return i < 0 || j < 0 || i >= nx || j >= ny ? -1 : j * nx + i; };
  const molhado = (x, z) => { const k = no(x, z); return k >= 0 && (f[k] || f[k + 1] || f[k - 1] || f[k + nx] || f[k - nx]); };
  let atingidas = 0; for (const c of casas) if (nivel - c.piso > .2 && molhado(c.x, c.z)) atingidas++;
  const sitios = lugares.filter(l => l.nome !== 'Rio Paraitinga').map(l => ({ nome: l.nome, prof: molhado(l.x, l.z) ? Math.max(0, nivel - (hAt(l.x, l.z) + hMin)) : 0 }));
  return { area: pontos * (T.x1 - T.x0) / (nx - 1) * (T.z1 - T.z0) / (ny - 1), casas: atingidas, totalCasas: casas.length, lugares: sitios };
}
if (new URLSearchParams(location.search).has('embed')) document.body.classList.add('embutida');

window.__cidade = { mapeadas: city.buildings.length, geradas, renderer, enchente, voar, altitude: (x, z) => hAt(x, z) + hMin };
const car = document.getElementById('carregando'); car.style.opacity = 0; setTimeout(() => car.remove(), 700);
