// ラボ収納マップ 3D — Blenderで組み直したラボのGLBを表示し、什器（収納ユニット）を選んで情報を見る。
// 座標: Blender(X=東, Y=北, Z=上) → three.js(x=東, y=上, z=南)。GLB書き出し時に変換済み。
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

const META = window.__LAB_META__;
const SPEC = window.__LAB_SPEC__ || {};   // 収納量（区画・段数）の個別指定。あとで追記する

const KIND = {
  fridge: { label: '冷蔵・冷凍庫', color: '#2f7fc1' },
  chestFreezer: { label: 'チェスト型フリーザー', color: '#1f5f99' },
  incubator: { label: 'インキュベーター', color: '#c2672b' },
  bench: { label: '実験台', color: '#3f8f5a' },
  table: { label: '机・台', color: '#7a9a3f' },
  shelf: { label: '棚', color: '#8a5fb0' },
  rack: { label: 'ワイヤーラック', color: '#a879c9' },
  cabinet: { label: 'キャビネット', color: '#b0477a' },
  sink: { label: '流し台', color: '#4f98a8' },
  hood: { label: 'ドラフト', color: '#7d6c56' },
  bsc: { label: '安全キャビネット', color: '#9a8a3a' },
  equipment: { label: '機器', color: '#6c7580' },
};
const COLD = new Set(['fridge', 'chestFreezer']);
const FACING = { N: '北向き', S: '南向き', E: '東向き', W: '西向き' };
const ROOM_ORDER = META.rooms.map((r) => r.name);

const $ = (s) => document.querySelector(s);
const el = (tag, cls, txt) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (txt != null) e.textContent = txt;
  return e;
};
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* プライベートモード等では保存しない */ } },
};

// ───────────────────────── レンダラー・シーン ─────────────────────────
const wrap = $('#view');
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.localClippingEnabled = true;
wrap.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color('#e9ecee');
const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
scene.environmentIntensity = 0.55;

const camera = new THREE.PerspectiveCamera(38, 1, 0.05, 200);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.09;
controls.maxPolarAngle = Math.PI * 0.49;
controls.minDistance = 1.2;
controls.maxDistance = 45;
controls.screenSpacePanning = false;

scene.add(new THREE.HemisphereLight('#ffffff', '#cfc8b8', 1.15));
const sun = new THREE.DirectionalLight('#fffaf0', 1.55);
sun.position.set(-7, 14, 6);
sun.castShadow = true;
sun.shadow.mapSize.set(4096, 4096);
Object.assign(sun.shadow.camera, { left: -10, right: 10, top: 10, bottom: -10, near: 1, far: 40 });
sun.shadow.bias = -0.0004;
sun.shadow.normalBias = 0.02;
scene.add(sun);
const fill = new THREE.DirectionalLight('#eef4ff', 0.35);
fill.position.set(8, 6, -6);
scene.add(fill);

// ───────────────────────── 状態 ─────────────────────────
const units = new Map();     // id → { id, meta, obj, mats, box, center }
const arch = { wall: [], wallLow: [], window: [], door: [], ceiling: [], floor: [], decor: [] };
let hovered = null;
let selected = null;
const selBox = new THREE.Box3Helper(new THREE.Box3(), new THREE.Color('#0a6194'));
selBox.visible = false;
selBox.material.depthTest = false;
selBox.renderOrder = 10;
scene.add(selBox);
const state = {
  walls: store.get('lab3d-walls', 'low'),     // full | low | off
  ceiling: false,
  colorize: store.get('lab3d-colorize', false),
  labels: store.get('lab3d-labels', true),
  storageOnly: false,
  room: 'all',
  query: '',
};
const notes = store.get('lab3d-notes-v1', {});

// ───────────────────────── GLB 読み込み ─────────────────────────
function b64ToBuf(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out.buffer;
}

const loader = new GLTFLoader();
loader.parse(b64ToBuf(window.__LAB_GLB__), '', (gltf) => {
  const root = gltf.scene;
  scene.add(root);
  root.traverse((o) => {
    if (o.isMesh) {
      const mats = Array.isArray(o.material) ? o.material : [o.material];
      for (const m of mats) {
        if (m.transparent) { m.depthWrite = false; o.renderOrder = 2; }
        if (m.map) m.map.anisotropy = renderer.capabilities.getMaxAnisotropy();
      }
    }
  });
  // ノードの extras（Blenderのカスタムプロパティ）で役割を判定する
  for (const node of root.children) {
    const ud = node.userData || {};
    const kind = ud.lab_kind;
    setShadows(node, kind);
    if (ud.lab_id) {
      registerUnit(node, ud);
    } else if (kind === 'wall') arch.wall.push(node);
    else if (kind === 'wall_low') arch.wallLow.push(node);
    else if (kind === 'window') arch.window.push(node);
    else if (kind === 'door') arch.door.push(node);
    else if (kind === 'ceiling') arch.ceiling.push(node);
    else if (kind === 'floor') arch.floor.push(node);
    else arch.decor.push(node);
  }
  buildFootprints();
  buildRoomLabels();
  buildList();
  applyWalls();
  applyCeiling();
  applyColorize();
  applyLabels();
  flyTo(viewPreset('overview'), 0);
  const hash = decodeURIComponent(location.hash.slice(1));
  if (hash && units.has(hash)) select(hash, true);
  $('#loading').remove();
}, (err) => {
  $('#loading').textContent = '3Dモデルの読み込みに失敗しました: ' + err;
});

function setShadows(node, kind) {
  node.traverse((o) => {
    if (!o.isMesh) return;
    o.castShadow = kind !== 'floor' && kind !== 'ceiling' && kind !== 'window';
    o.receiveShadow = kind !== 'ceiling';
  });
}

function registerUnit(node, ud) {
  const meta = META.units.find((u) => u.id === ud.lab_id) || { id: ud.lab_id, name: ud.lab_name, room: ud.lab_room, kind: ud.lab_kind };
  // ハイライト用にユニットごとのマテリアル複製を持つ（共有マテリアルを汚さない）
  const mats = [];
  node.traverse((o) => {
    if (!o.isMesh) return;
    o.material = Array.isArray(o.material) ? o.material.map((m) => m.clone()) : o.material.clone();
    for (const m of (Array.isArray(o.material) ? o.material : [o.material])) {
      m.userData.baseEmissive = m.emissive ? m.emissive.clone() : null;
      mats.push(m);
    }
    o.userData.unitId = ud.lab_id;
  });
  const box = new THREE.Box3().setFromObject(node);
  units.set(ud.lab_id, { id: ud.lab_id, meta, obj: node, mats, box, center: box.getCenter(new THREE.Vector3()) });
}

function tint(u, color, strength) {
  // color=null は「既定の見た目」に戻す。種別色分けモード中は種別色で薄く塗った状態が既定
  if (!color && state.colorize) {
    color = (KIND[u.meta.kind] || KIND.equipment).color;
    strength = u.meta.storage ? 0.55 : 0.25;
  }
  for (const m of u.mats) {
    if (!m.emissive) continue;
    if (color) { m.emissive.set(color); m.emissiveIntensity = strength; }
    else { m.emissive.copy(m.userData.baseEmissive); m.emissiveIntensity = 1; }
  }
}

// ───────────────────────── 床の色分け（種別）─────────────────────────
const footprints = new THREE.Group();
scene.add(footprints);
function buildFootprints() {
  for (const u of units.values()) {
    const s = u.box.getSize(new THREE.Vector3());
    const k = KIND[u.meta.kind] || KIND.equipment;
    const g = new THREE.PlaneGeometry(s.x + 0.06, s.z + 0.06);
    g.rotateX(-Math.PI / 2);
    const m = new THREE.MeshBasicMaterial({ color: k.color, transparent: true, opacity: u.meta.storage ? 0.55 : 0.25, depthWrite: false });
    const p = new THREE.Mesh(g, m);
    p.position.set(u.center.x, 0.004, u.center.z);
    p.renderOrder = 1;
    footprints.add(p);
  }
}

// ───────────────────────── ラベル（部屋名・選択中ユニット）─────────────────────────
const labelLayer = $('#labels');
const roomLabels = [];
function buildRoomLabels() {
  for (const r of META.rooms) {
    // 多角形の重心（面積重み）。Blender座標(x, y北) → three(x, -y)
    let a = 0, cx = 0, cy = 0;
    const p = r.poly;
    for (let i = 0; i < p.length; i++) {
      const [x0, y0] = p[i], [x1, y1] = p[(i + 1) % p.length];
      const c = x0 * y1 - x1 * y0;
      a += c; cx += (x0 + x1) * c; cy += (y0 + y1) * c;
    }
    a /= 2; cx /= 6 * a; cy /= 6 * a;
    const d = el('div', 'room-label', r.name);
    labelLayer.appendChild(d);
    roomLabels.push({ el: d, pos: new THREE.Vector3(cx, 0.02, -cy), room: r });
  }
}
const unitTag = el('div', 'unit-tag');
labelLayer.appendChild(unitTag);
const hoverTip = el('div', 'hover-tip');
hoverTip.hidden = true;
wrap.appendChild(hoverTip);

const tmpV = new THREE.Vector3();
function placeLabel(div, pos) {
  tmpV.copy(pos).project(camera);
  const visible = tmpV.z < 1 && Math.abs(tmpV.x) < 1.1 && Math.abs(tmpV.y) < 1.1;
  div.style.display = visible ? '' : 'none';
  if (!visible) return;
  const w = wrap.clientWidth, h = wrap.clientHeight;
  div.style.transform = `translate(${(tmpV.x * 0.5 + 0.5) * w}px, ${(-tmpV.y * 0.5 + 0.5) * h}px) translate(-50%, -50%)`;
}
function updateLabels() {
  for (const r of roomLabels) {
    if (!state.labels) { r.el.style.display = 'none'; continue; }
    placeLabel(r.el, r.pos);
  }
  if (selected && state.labels) {
    const u = units.get(selected);
    placeLabel(unitTag, new THREE.Vector3(u.center.x, u.box.max.y + 0.18, u.center.z));
  } else unitTag.style.display = 'none';
}

// ───────────────────────── 表示切替 ─────────────────────────
function setVis(list, v) { for (const o of list) o.visible = v; }
function applyWalls() {
  const m = state.walls;
  setVis(arch.wall, m === 'full');
  setVis(arch.wallLow, m === 'low');
  setVis(arch.window, m === 'full');
  setVis(arch.door, m === 'full');
  for (const b of document.querySelectorAll('[data-walls]')) b.setAttribute('aria-pressed', String(b.dataset.walls === m));
  store.set('lab3d-walls', m);
}
function applyCeiling() {
  setVis(arch.ceiling, state.ceiling);
  $('#t-ceiling').setAttribute('aria-pressed', String(state.ceiling));
}
function applyColorize() {
  footprints.visible = state.colorize;
  for (const u of units.values()) {
    if (u.id === selected) tint(u, '#1f7fd1', 0.38);
    else tint(u, null);
  }
  $('#t-color').setAttribute('aria-pressed', String(state.colorize));
  $('#legend').hidden = !state.colorize;
  store.set('lab3d-colorize', state.colorize);
}
function applyLabels() {
  $('#t-labels').setAttribute('aria-pressed', String(state.labels));
  store.set('lab3d-labels', state.labels);
}

// ───────────────────────── カメラ ─────────────────────────
// 指定方向から見たとき、箱の8隅がすべて画面内（余白込み）に入る最短距離を二分探索で求める
function fitDistance(box, target, dir, margin = 0.9) {
  const cam = camera.clone();
  cam.aspect = wrap.clientWidth / Math.max(1, wrap.clientHeight);
  cam.updateProjectionMatrix();
  const pts = [];
  for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) pts.push(new THREE.Vector3(x, y, z));
  const fits = (d) => {
    cam.position.copy(target).addScaledVector(dir, d);
    cam.up.set(0, 1, 0);
    if (Math.abs(dir.y) > 0.999) cam.up.set(0, 0, -1);
    cam.lookAt(target);
    cam.updateMatrixWorld();
    return pts.every((p) => { const v = p.clone().project(cam); return v.z < 1 && Math.abs(v.x) <= margin && Math.abs(v.y) <= margin; });
  };
  let lo = 1, hi = 120;
  for (let i = 0; i < 30; i++) { const m = (lo + hi) / 2; if (fits(m)) hi = m; else lo = m; }
  return hi;
}
const FLOOR_BOX = new THREE.Box3(new THREE.Vector3(-5.9, 0, -7.55), new THREE.Vector3(5.8, 2.0, 7.55));
function viewPreset(name, ref) {
  if (name === 'overview') {
    const c = FLOOR_BOX.getCenter(new THREE.Vector3()); c.y = 0;
    const dir = new THREE.Vector3(-0.42, 0.78, 0.47).normalize();
    return { pos: c.clone().addScaledVector(dir, fitDistance(FLOOR_BOX, c, dir, 0.92)), target: c };
  }
  if (name === 'top') {
    const c = FLOOR_BOX.getCenter(new THREE.Vector3()); c.y = 0;
    const dir = new THREE.Vector3(0, 1, 0.0008).normalize();
    return { pos: c.clone().addScaledVector(dir, fitDistance(FLOOR_BOX, c, dir, 0.94)), target: c };
  }
  if (name === 'box') {
    const c = ref.getCenter(new THREE.Vector3());
    const s = ref.getSize(new THREE.Vector3());
    const r = Math.max(s.x, s.z, s.y * 0.8, 1.6);
    const dir = camera.position.clone().sub(controls.target).setY(0).normalize();
    if (!isFinite(dir.x) || dir.lengthSq() < 0.5) dir.set(-0.6, 0, 0.8);
    const d = r * 1.6 + 1.6;
    return { pos: c.clone().addScaledVector(dir, d).setY(Math.max(2.4, c.y + d * 0.75)), target: c.clone().setY(Math.min(c.y, 0.9)) };
  }
}
let anim = null;
function flyTo(v, ms = 650) {
  if (!v) return;
  if (ms === 0) { camera.position.copy(v.pos); controls.target.copy(v.target); controls.update(); return; }
  anim = { t0: performance.now(), ms, p0: camera.position.clone(), t0v: controls.target.clone(), p1: v.pos, t1: v.target };
}
const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
function stepAnim(now) {
  if (!anim) return;
  const t = Math.min(1, (now - anim.t0) / anim.ms), e = ease(t);
  camera.position.lerpVectors(anim.p0, anim.p1, e);
  controls.target.lerpVectors(anim.t0v, anim.t1, e);
  if (t >= 1) anim = null;
}
function roomBox(room) {
  const b = new THREE.Box3();
  for (const [x, y] of room.poly) b.expandByPoint(new THREE.Vector3(x, 0, -y));
  b.max.y = 1.6;
  return b;
}

// ───────────────────────── ピッキング ─────────────────────────
const ray = new THREE.Raycaster();
const ndc = new THREE.Vector2();
let pickables = [];
function refreshPickables() {
  pickables = [];
  for (const u of units.values()) if (u.obj.visible) pickables.push(u.obj);
}
function pick(ev) {
  const r = renderer.domElement.getBoundingClientRect();
  ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(ndc, camera);
  refreshPickables();
  const hit = ray.intersectObjects(pickables, true)[0];
  if (!hit) return null;
  let o = hit.object;
  while (o && !o.userData.unitId) o = o.parent;
  return o ? o.userData.unitId : null;
}
function setHover(id, ev) {
  if (hovered === id) { if (id) moveTip(ev); return; }
  if (hovered && hovered !== selected) tint(units.get(hovered), null);
  hovered = id;
  renderer.domElement.style.cursor = id ? 'pointer' : '';
  if (id && id !== selected) tint(units.get(id), '#3b8fd0', 0.22);
  if (id) {
    const u = units.get(id);
    hoverTip.textContent = `${u.id}　${u.meta.name}${u.meta.temp ? '　' + u.meta.temp : ''}`;
    hoverTip.hidden = false;
    moveTip(ev);
  } else hoverTip.hidden = true;
}
function moveTip(ev) {
  if (!ev) return;
  const r = wrap.getBoundingClientRect();
  hoverTip.style.transform = `translate(${ev.clientX - r.left + 14}px, ${ev.clientY - r.top + 12}px)`;
}
let down = null;
renderer.domElement.addEventListener('pointerdown', (e) => { down = { x: e.clientX, y: e.clientY }; });
renderer.domElement.addEventListener('pointermove', (e) => { if (e.pointerType === 'mouse' && !e.buttons) setHover(pick(e), e); });
renderer.domElement.addEventListener('pointerleave', () => setHover(null));
renderer.domElement.addEventListener('pointerup', (e) => {
  if (!down || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 5) return;
  const id = pick(e);
  if (id) select(id, false);
  else select(null);
});
renderer.domElement.addEventListener('dblclick', (e) => {
  const id = pick(e);
  if (id) select(id, true);
});

// ───────────────────────── 選択と詳細パネル ─────────────────────────
function select(id, fly) {
  if (selected && units.has(selected)) tint(units.get(selected), null);
  selected = id;
  for (const li of document.querySelectorAll('.unit-row')) li.setAttribute('aria-current', String(li.dataset.id === id));
  if (!id) {
    selBox.visible = false;
    $('#panel').hidden = true;
    history.replaceState(null, '', location.pathname + location.search);
    return;
  }
  const u = units.get(id);
  tint(u, '#1f7fd1', 0.38);
  selBox.box.copy(u.box).expandByScalar(0.03);
  selBox.visible = true;
  unitTag.textContent = u.id;
  renderPanel(u);
  history.replaceState(null, '', '#' + encodeURIComponent(id));
  const row = document.querySelector(`.unit-row[data-id="${CSS.escape(id)}"]`);
  if (row) row.scrollIntoView({ block: 'nearest' });
  if (fly) flyTo(viewPreset('box', u.box));
}

function fmt(n) { return (Math.round(n * 100) / 100).toFixed(2); }
function renderPanel(u) {
  const p = $('#panel');
  p.hidden = false;
  const m = u.meta;
  const k = KIND[m.kind] || { label: m.kind, color: '#666' };
  $('#p-id').textContent = m.id;
  $('#p-name').textContent = m.temp ? `${m.name}　${m.temp}` : m.name;
  $('#p-kind').textContent = k.label;
  $('#p-kind').style.setProperty('--chip', k.color);
  const s = u.box.getSize(new THREE.Vector3());
  const rows = [
    ['部屋', m.room],
    ...(m.temp || COLD.has(m.kind) ? [['温度', m.temp || '未設定']] : []),
    ['外形（東西×南北×高さ）', `${fmt(s.x)} × ${fmt(s.z)} × ${fmt(s.y)} m`],
    ['正面', FACING[m.facing] || '—'],
    ['収納対象', m.storage ? 'はい' : 'いいえ（機器・作業用）'],
  ];
  const dl = $('#p-props');
  dl.innerHTML = '';
  for (const [a, b] of rows) { dl.append(el('dt', '', a), el('dd', '', b)); }
  // 収納量（区画）: SPEC に定義があれば一覧、なければ未設定
  const cap = $('#p-cap');
  cap.innerHTML = '';
  const spec = SPEC[m.id];
  if (spec && spec.sections && spec.sections.length) {
    const ul = el('ul', 'sections');
    for (const sct of spec.sections) ul.append(el('li', '', `${sct.code}　${sct.name}${sct.capacity ? '（' + sct.capacity + '）' : ''}`));
    cap.append(ul);
  } else {
    cap.append(el('p', 'muted', m.storage ? '未設定 — 区画・段数・容量はあとで個別に指定します。' : 'この什器は収納の対象外として扱っています（必要なら指定してください）。'));
  }
  $('#p-note').textContent = m.note || '';
  $('#p-note').hidden = !m.note;
  const ta = $('#p-memo');
  ta.value = notes[m.id] || '';
  ta.dataset.id = m.id;
}
$('#p-memo').addEventListener('input', (e) => {
  const id = e.target.dataset.id;
  const v = e.target.value.trim();
  if (v) notes[id] = e.target.value; else delete notes[id];
  store.set('lab3d-notes-v1', notes);
  const row = document.querySelector(`.unit-row[data-id="${CSS.escape(id)}"]`);
  if (row) row.classList.toggle('has-memo', !!v);
  $('#memo-count').textContent = String(Object.keys(notes).length);
});
$('#p-close').addEventListener('click', () => select(null));
$('#p-focus').addEventListener('click', () => { if (selected) flyTo(viewPreset('box', units.get(selected).box)); });

// ───────────────────────── 一覧（左サイドバー）─────────────────────────
function buildList() {
  const chips = $('#rooms');
  const mk = (val, label) => {
    const b = el('button', 'chip', label);
    b.dataset.room = val;
    b.onclick = () => {
      state.room = val;
      renderList();
      if (val === 'all') flyTo(viewPreset('overview'));
      else flyTo(viewPreset('box', roomBox(META.rooms.find((r) => r.name === val))));
    };
    chips.append(b);
  };
  mk('all', 'すべて');
  for (const r of META.rooms) mk(r.name, r.name);
  renderList();
  $('#memo-count').textContent = String(Object.keys(notes).length);
}
function renderList() {
  for (const b of document.querySelectorAll('#rooms .chip')) b.setAttribute('aria-pressed', String(b.dataset.room === state.room));
  const q = state.query.trim().toLowerCase();
  const list = $('#list');
  list.innerHTML = '';
  let n = 0;
  for (const room of ROOM_ORDER) {
    if (state.room !== 'all' && state.room !== room) continue;
    const us = [...units.values()].filter((u) => u.meta.room === room)
      .filter((u) => !state.storageOnly || u.meta.storage)
      .filter((u) => !q || `${u.id} ${u.meta.name} ${u.meta.temp || ''} ${(KIND[u.meta.kind] || {}).label || ''} ${notes[u.id] || ''}`.toLowerCase().includes(q))
      .sort((a, b) => a.id.localeCompare(b.id, 'ja', { numeric: true }));
    if (!us.length) continue;
    const h = el('li', 'group', `${room}（${us.length}）`);
    list.append(h);
    for (const u of us) {
      const li = el('li', 'unit-row');
      li.dataset.id = u.id;
      li.setAttribute('aria-current', String(u.id === selected));
      if (notes[u.id]) li.classList.add('has-memo');
      const k = KIND[u.meta.kind] || { color: '#777', label: u.meta.kind };
      const dot = el('span', 'dot');
      dot.style.background = k.color;
      li.append(dot, el('span', 'uid', u.id), el('span', 'uname', u.meta.name));
      if (u.meta.temp) li.append(el('span', 'temp', u.meta.temp));
      if (!u.meta.storage) li.append(el('span', 'tag', '機器'));
      li.onclick = () => select(u.id, true);
      li.onmouseenter = () => { if (u.id !== selected) tint(u, '#3b8fd0', 0.22); };
      li.onmouseleave = () => { if (u.id !== selected) tint(u, null); };
      list.append(li);
      n++;
    }
  }
  if (!n) list.append(el('li', 'empty', '該当する什器がありません'));
  $('#count').textContent = `${n} 件`;
}
$('#q').addEventListener('input', (e) => { state.query = e.target.value; renderList(); });
$('#storage-only').addEventListener('change', (e) => { state.storageOnly = e.target.checked; renderList(); });

// ───────────────────────── ツールバー ─────────────────────────
for (const b of document.querySelectorAll('[data-walls]')) b.onclick = () => { state.walls = b.dataset.walls; applyWalls(); };
$('#t-ceiling').onclick = () => { state.ceiling = !state.ceiling; applyCeiling(); };
$('#t-color').onclick = () => { state.colorize = !state.colorize; applyColorize(); };
$('#t-labels').onclick = () => { state.labels = !state.labels; applyLabels(); };
$('#v-overview').onclick = () => flyTo(viewPreset('overview'));
$('#v-top').onclick = () => flyTo(viewPreset('top'));
$('#v-shot').onclick = () => {
  renderer.render(scene, camera);
  const a = document.createElement('a');
  a.href = renderer.domElement.toDataURL('image/png');
  a.download = `lab3d_${new Date().toISOString().slice(0, 10)}.png`;
  a.click();
};
$('#export-memo').onclick = () => {
  const out = { exportedAt: new Date().toISOString(), memos: Object.entries(notes).map(([id, memo]) => ({ id, name: units.get(id)?.meta.name, memo })) };
  const blob = new Blob([JSON.stringify(out, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'lab3d_収納量メモ.json';
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
};
$('#toggle-side').onclick = () => document.body.classList.toggle('side-open');

// 凡例
{
  const lg = $('#legend');
  for (const [k, v] of Object.entries(KIND)) {
    if (![...META.units].some((u) => u.kind === k)) continue;
    const d = el('span', 'lg');
    const sw = el('i');
    sw.style.background = v.color;
    d.append(sw, document.createTextNode(v.label));
    lg.append(d);
  }
}

window.addEventListener('hashchange', () => {
  const id = decodeURIComponent(location.hash.slice(1));
  if (id && units.has(id) && id !== selected) select(id, true);
});
window.addEventListener('keydown', (e) => {
  if (e.target.matches('input, textarea')) return;
  if (e.key === 'Escape') select(null);
  if (e.key === 'f' && selected) flyTo(viewPreset('box', units.get(selected).box));
});

// ───────────────────────── ループ ─────────────────────────
function resize() {
  const w = wrap.clientWidth, h = wrap.clientHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / Math.max(1, h);
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(wrap);
resize();
function loop(now) {
  stepAnim(now);
  controls.update();
  renderer.render(scene, camera);
  updateLabels();
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);
// デバッグ・検証用（ブラウザから状態を読む）
window.__lab = { units, select, state, camera, controls, flyTo, viewPreset };
