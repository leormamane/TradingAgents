import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CSS2DRenderer, CSS2DObject } from "three/addons/renderers/CSS2DRenderer.js";

const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------- the team
const AGENTS = {
  market:            { name: "Market Analyst",       shirt: "#3a86ff", pants: "#22324f", skin: "#f1c27d", hat: "cap",    hatColor: "#ffbe0b" },
  social:            { name: "Sentiment Analyst",    shirt: "#ff70a6", pants: "#3d2c5e", skin: "#e0ac69", hat: "phones", hatColor: "#222" },
  news:              { name: "News Analyst",         shirt: "#00b4d8", pants: "#2b2d42", skin: "#8d5524", hat: "visor",  hatColor: "#06d6a0" },
  fundamentals:      { name: "Fundamentals Analyst", shirt: "#8338ec", pants: "#2b2d42", skin: "#ffdbac", hat: "glasses" },
  bull:              { name: "Bull Researcher",      shirt: "#2ec46d", pants: "#1b4332", skin: "#c68642", hat: "horns",  hatColor: "#f8f3e6" },
  bear:              { name: "Bear Researcher",      shirt: "#e63946", pants: "#3b1f1f", skin: "#f1c27d", hat: "ears",   hatColor: "#6f4e37" },
  research_manager:  { name: "Research Manager",     shirt: "#6a4c93", pants: "#1d2433", skin: "#e0ac69", hat: "beret",  hatColor: "#1d2433" },
  trader:            { name: "Trader",               shirt: "#fb8500", pants: "#023047", skin: "#ffdbac", hat: "phones", hatColor: "#023047" },
  aggressive:        { name: "Aggressive Risk",      shirt: "#ff006e", pants: "#1d2433", skin: "#8d5524", hat: "band",   hatColor: "#ff006e" },
  conservative:      { name: "Conservative Risk",    shirt: "#457b9d", pants: "#1d3557", skin: "#ffdbac", hat: "glasses" },
  neutral:           { name: "Neutral Risk",         shirt: "#adb5bd", pants: "#495057", skin: "#c68642", hat: "cap",    hatColor: "#495057" },
  portfolio_manager: { name: "Portfolio Manager",    shirt: "#1d2433", pants: "#1d2433", skin: "#f1c27d", hat: "tophat", hatColor: "#111", tie: "#ffd60a" },
};
const ANALYSTS = ["market", "social", "news", "fundamentals"];
const RATING_COLORS = { Buy: "#2ec46d", Overweight: "#7bd88f", Hold: "#8d99ae", Underweight: "#f4a261", Sell: "#ef476f", REVIEW: "#ffb703" };

// ---------------------------------------------------------------- renderer
const host = document.getElementById("scene");
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.outputColorSpace = THREE.SRGBColorSpace;
host.appendChild(renderer.domElement);
const labels = new CSS2DRenderer();
labels.domElement.style.position = "absolute";
labels.domElement.style.inset = "0";
labels.domElement.style.pointerEvents = "none";
host.appendChild(labels.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color("#8ec9ff");
scene.fog = new THREE.Fog("#8ec9ff", 70, 130);
const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 300);
const HOME = { pos: new THREE.Vector3(14, 27, 31), target: new THREE.Vector3(0, 0, -1) };
if (innerWidth <= 860) HOME.pos.set(20, 44, 52);
camera.position.copy(HOME.pos);
const controls = new OrbitControls(camera, renderer.domElement);
controls.target.copy(HOME.target);
controls.enableDamping = true;
controls.maxPolarAngle = Math.PI * 0.46;
controls.minDistance = 10;
controls.maxDistance = 80;

scene.add(new THREE.HemisphereLight("#ffffff", "#8a7f6a", 1.1));
const sun = new THREE.DirectionalLight("#fff4dd", 2.2);
sun.position.set(18, 34, 16);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
Object.assign(sun.shadow.camera, { left: -30, right: 30, top: 24, bottom: -24, near: 1, far: 90 });
sun.shadow.bias = -0.0005;
scene.add(sun);

// ---------------------------------------------------------------- helpers
const mats = new Map();
function mat(color, extra = {}) {
  const key = color + JSON.stringify(extra);
  if (!mats.has(key)) mats.set(key, new THREE.MeshStandardMaterial({ color, roughness: 0.55, metalness: 0.02, ...extra }));
  return mats.get(key);
}
function box(w, h, d, color, x = 0, y = 0, z = 0, parent = scene, extra) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), typeof color === "string" ? mat(color, extra) : color);
  m.position.set(x, y, z);
  m.castShadow = true;
  m.receiveShadow = true;
  parent.add(m);
  return m;
}
function cyl(r, h, color, x, y, z, parent = scene, seg = 20) {
  const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, seg), mat(color));
  m.position.set(x, y, z);
  m.castShadow = m.receiveShadow = true;
  parent.add(m);
  return m;
}
function canvasTex(w, h, draw) {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  draw(c.getContext("2d"), w, h);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}
function studTex(base, light, dark) {
  const t = canvasTex(64, 64, (g) => {
    g.fillStyle = base; g.fillRect(0, 0, 64, 64);
    g.fillStyle = dark; g.beginPath(); g.arc(34, 34, 18, 0, Math.PI * 2); g.fill();
    g.fillStyle = light; g.beginPath(); g.arc(31, 31, 18, 0, Math.PI * 2); g.fill();
    g.fillStyle = base; g.beginPath(); g.arc(32, 32, 15, 0, Math.PI * 2); g.fill();
  });
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  return t;
}

// ---------------------------------------------------------------- the building
const FLOOR_W = 44, FLOOR_D = 30;
{
  const t = studTex("#c9ced6", "#dde1e7", "#a9afb9");
  t.repeat.set(FLOOR_W, FLOOR_D);
  const floor = new THREE.Mesh(new THREE.BoxGeometry(FLOOR_W, 0.6, FLOOR_D), [
    mat("#9aa1ab"), mat("#9aa1ab"), new THREE.MeshStandardMaterial({ map: t, roughness: 0.7 }),
    mat("#9aa1ab"), mat("#9aa1ab"), mat("#9aa1ab")]);
  floor.position.y = -0.3;
  floor.receiveShadow = true;
  scene.add(floor);
  // grass baseplate around
  const g = studTex("#5bbf4a", "#74d162", "#479a39");
  g.repeat.set(120, 120);
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(120, 120), new THREE.MeshStandardMaterial({ map: g, roughness: 0.9 }));
  ground.rotation.x = -Math.PI / 2; ground.position.y = -0.62; ground.receiveShadow = true;
  scene.add(ground);
}
// Walls: back and left, with windows onto a blocky skyline.
{
  const H = 7, back = -FLOOR_D / 2, left = -FLOOR_W / 2;
  const wall = "#f4efe6", trim = "#3d5a80";
  box(FLOOR_W, 1.2, 0.6, wall, 0, 0.6, back);
  box(FLOOR_W, 1.6, 0.6, wall, 0, H - 0.8, back);
  for (let i = 0; i <= 8; i++) box(0.6, H, 0.6, trim, left + i * (FLOOR_W / 8), H / 2, back);
  const glass = new THREE.MeshStandardMaterial({ color: "#bfe3ff", transparent: true, opacity: 0.35, roughness: 0.1 });
  box(FLOOR_W, H - 2.8, 0.15, glass, 0, 1.2 + (H - 2.8) / 2, back);
  box(0.6, H, FLOOR_D, wall, left, H / 2, 0);
  box(0.62, 0.5, FLOOR_D, trim, left + 0.01, 0.25, 0);
  // skyline
  const rnd = mulberry(7);
  const tones = ["#6c8ebf", "#8aa6cf", "#5679a8", "#9fb7d9", "#7b93b8"];
  for (let x = -40; x < 40; x += 3.2) {
    const h = 6 + rnd() * 22, w = 2.4 + rnd() * 1.2;
    const b = box(w, h, 3, tones[Math.floor(rnd() * tones.length)], x, h / 2 - 0.6, back - 9 - rnd() * 10);
    b.castShadow = false;
  }
  // wall clock and art on the left wall
  const clock = cyl(1.1, 0.2, "#ffffff", left + 0.42, 4.6, -6);
  clock.rotation.z = Math.PI / 2;
  box(0.1, 0.9, 0.12, "#1d2433", left + 0.55, 4.85, -6);
  box(0.1, 0.12, 0.7, "#1d2433", left + 0.55, 4.6, -5.75);
  box(0.15, 2.2, 3.2, "#ffbe0b", left + 0.4, 4.2, 6);
  box(0.16, 1.6, 2.6, "#3a86ff", left + 0.45, 4.2, 6);
}
function mulberry(a) { return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }

// Zone rugs with painted names.
function rug(x, z, w, d, color, text) {
  const t = canvasTex(512, Math.round(512 * d / w), (g, W, H) => {
    g.fillStyle = color; g.fillRect(0, 0, W, H);
    g.strokeStyle = "rgba(255,255,255,.55)"; g.lineWidth = 10; g.strokeRect(14, 14, W - 28, H - 28);
    g.fillStyle = "rgba(255,255,255,.85)"; g.font = "700 46px Fredoka, sans-serif"; g.textAlign = "center";
    g.fillText(text, W / 2, H - 34);
  });
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, 0.08, d), [mat(color), mat(color), new THREE.MeshStandardMaterial({ map: t, roughness: 0.9 }), mat(color), mat(color), mat(color)]);
  m.position.set(x, 0.04, z); m.receiveShadow = true; scene.add(m);
}
rug(-13, 0.5, 15, 15, "#4d7cc7", "ANALYST BULLPEN");
rug(1.5, -8.5, 12, 10, "#5f9e6e", "RESEARCH ROOM");
rug(1.5, 6.5, 10, 7, "#d9822b", "TRADING DESK");
rug(14.5, -8.5, 12, 10, "#b5546d", "RISK ROOM");
rug(14.5, 6.5, 11, 8, "#3b3f58", "CORNER OFFICE");

// ---------------------------------------------------------------- furniture
function laptop(parent, x, y, z, rotY = 0) {
  const g = new THREE.Group(); g.position.set(x, y, z); g.rotation.y = rotY; parent.add(g);
  box(1.2, 0.08, 0.8, "#2b2d42", 0, 0.04, 0, g);
  const lid = new THREE.Group(); lid.position.set(0, 0.08, 0.4); lid.rotation.x = 0.35; g.add(lid);
  box(1.2, 0.8, 0.06, "#2b2d42", 0, 0.4, 0, lid);
  const screen = box(1.05, 0.66, 0.02, new THREE.MeshStandardMaterial({ color: "#0b132b", emissive: "#1b6ca8", emissiveIntensity: 0.25 }), 0, 0.4, -0.04, lid);
  return screen;
}
function chair(x, z, rotY, color = "#2b2d42") {
  const g = new THREE.Group(); g.position.set(x, 0, z); g.rotation.y = rotY; scene.add(g);
  cyl(0.12, 0.6, "#555", 0, 0.3, 0, g, 8);
  box(1.3, 0.2, 1.2, color, 0, 0.7, 0, g);
  box(1.3, 1.3, 0.2, color, 0, 1.4, -0.6, g);
  return g;
}
function desk(x, z, w = 3, d = 1.8, color = "#e9c46a", rotY = 0) {
  const g = new THREE.Group(); g.position.set(x, 0, z); g.rotation.y = rotY; scene.add(g);
  box(w, 0.2, d, color, 0, 1.3, 0, g);
  for (const sx of [-1, 1]) box(0.2, 1.2, d - 0.2, "#6c757d", sx * (w / 2 - 0.2), 0.6, 0, g);
  return g;
}
function plant(x, z, s = 1) {
  box(0.9 * s, 0.9 * s, 0.9 * s, "#b5651d", x, 0.45 * s, z);
  box(1.1 * s, 1.1 * s, 1.1 * s, "#2d6a4f", x, 1.4 * s, z);
  box(0.7 * s, 0.7 * s, 0.7 * s, "#40916c", x, 2.2 * s, z);
}

// ---------------------------------------------------------------- characters
function faceTex(skin) {
  return canvasTex(128, 128, (g) => {
    g.fillStyle = skin; g.fillRect(0, 0, 128, 128);
    g.fillStyle = "#1d2433";
    g.beginPath(); g.ellipse(42, 54, 8, 12, 0, 0, Math.PI * 2); g.fill();
    g.beginPath(); g.ellipse(86, 54, 8, 12, 0, 0, Math.PI * 2); g.fill();
    g.fillStyle = "#fff"; g.fillRect(39, 47, 4, 5); g.fillRect(83, 47, 4, 5);
    g.strokeStyle = "#1d2433"; g.lineWidth = 6; g.lineCap = "round";
    g.beginPath(); g.arc(64, 74, 22, 0.2 * Math.PI, 0.8 * Math.PI); g.stroke();
  });
}
function makeCharacter(spec) {
  const root = new THREE.Group();
  const body = new THREE.Group(); root.add(body);          // bobs and jumps
  const S = 0.48;
  body.scale.setScalar(S);
  const skin = mat(spec.skin), shirt = mat(spec.shirt), pants = mat(spec.pants);
  const parts = {};
  // legs pivot at the hips
  for (const side of [-1, 1]) {
    const hip = new THREE.Group(); hip.position.set(side * 0.5, 2, 0); body.add(hip);
    const leg = box(0.98, 2, 0.98, pants, 0, -1, 0, hip); leg.userData.agent = spec.id;
    parts[side < 0 ? "legL" : "legR"] = hip;
  }
  const torso = box(2, 2, 1, shirt, 0, 3, 0, body); torso.userData.agent = spec.id;
  if (spec.tie) box(0.35, 1.4, 0.05, spec.tie, 0, 3.2, 0.52, body);
  for (const side of [-1, 1]) {
    const sh = new THREE.Group(); sh.position.set(side * 1.5, 3.85, 0); body.add(sh);
    box(0.98, 0.9, 0.98, shirt, 0, -0.35, 0, sh);
    const hand = box(0.96, 1.1, 0.96, skin, 0, -1.35, 0, sh); hand.userData.agent = spec.id;
    parts[side < 0 ? "armL" : "armR"] = sh;
  }
  const neck = new THREE.Group(); neck.position.set(0, 4, 0); body.add(neck);
  const face = new THREE.MeshStandardMaterial({ map: faceTex(spec.skin), roughness: 0.6 });
  const head = new THREE.Mesh(new THREE.BoxGeometry(1.25, 1.25, 1.25), [skin, skin, skin, skin, face, skin]);
  head.position.y = 0.66; head.castShadow = true; head.userData.agent = spec.id; neck.add(head);
  parts.neck = neck;
  addHat(neck, spec);
  root.traverse((o) => { if (o.isMesh) o.userData.agent = spec.id; });
  return { root, body, parts, S };
}
function addHat(neck, spec) {
  const c = spec.hatColor || "#222";
  switch (spec.hat) {
    case "cap": box(1.35, 0.35, 1.35, c, 0, 1.42, 0, neck); box(1.3, 0.12, 0.7, c, 0, 1.3, 0.9, neck); break;
    case "phones": box(1.5, 0.18, 0.3, c, 0, 1.38, 0, neck); for (const s of [-1, 1]) box(0.25, 0.6, 0.6, c, s * 0.72, 0.66, 0, neck); break;
    case "visor": box(1.4, 0.15, 1.4, c, 0, 1.15, 0.05, neck); box(1.3, 0.1, 0.6, c, 0, 1.12, 0.9, neck); break;
    case "glasses": for (const s of [-1, 1]) box(0.42, 0.3, 0.06, "#1d2433", s * 0.3, 0.75, 0.65, neck); box(0.25, 0.06, 0.06, "#1d2433", 0, 0.78, 0.65, neck); break;
    case "horns": for (const s of [-1, 1]) { const h = box(0.25, 0.7, 0.25, c, s * 0.62, 1.45, 0, neck); h.rotation.z = -s * 0.5; } break;
    case "ears": for (const s of [-1, 1]) box(0.45, 0.45, 0.25, c, s * 0.55, 1.42, 0, neck); break;
    case "beret": { const b = box(1.45, 0.3, 1.45, c, 0.1, 1.42, 0, neck); b.rotation.z = -0.12; break; }
    case "band": box(1.32, 0.22, 1.32, c, 0, 1.05, 0, neck); break;
    case "tophat": box(1.5, 0.12, 1.5, c, 0, 1.33, 0, neck); box(1.05, 1.1, 1.05, c, 0, 1.9, 0, neck); box(1.07, 0.2, 1.07, "#c1121f", 0, 1.48, 0, neck); break;
  }
}

// ---------------------------------------------------------------- placing the team
const team = {};
function seat(id, x, z, rotY, { laptopOn = true, chairColor } = {}) {
  const spec = { id, ...AGENTS[id] };
  const c = makeCharacter(spec);
  c.root.position.set(x, 0, z);
  c.root.rotation.y = rotY;
  scene.add(c.root);
  chair(x - Math.sin(rotY) * 0.15, z - Math.cos(rotY) * 0.15, rotY, chairColor);
  // seated pose: hips on the chair, legs forward
  c.body.position.y = 0.85 - 2 * c.S;
  c.parts.legL.rotation.x = c.parts.legR.rotation.x = -Math.PI / 2;
  c.parts.armL.rotation.x = c.parts.armR.rotation.x = -0.9;
  let screen = null;
  if (laptopOn) {
    const fwd = new THREE.Vector3(Math.sin(rotY), 0, Math.cos(rotY));
    screen = laptop(scene, x + fwd.x * 1.4, 1.4, z + fwd.z * 1.4, rotY);
  }
  // labels
  const tagEl = document.createElement("div");
  tagEl.className = "tag"; tagEl.innerHTML = `<span class="dot"></span>${spec.name}`;
  const tag = new CSS2DObject(tagEl); tag.position.set(0, 3.1, 0); c.root.add(tag);
  const bubEl = document.createElement("div"); bubEl.className = "bubble";
  bubEl.addEventListener("click", () => openReader(id));
  const bub = new CSS2DObject(bubEl); bub.center.set(0.5, 1); bub.position.set(0, 3.7, 0); c.root.add(bub);
  // check badge
  const check = new THREE.Group(); check.visible = false; check.position.set(0, 3.0, 0); c.root.add(check);
  box(0.5, 0.5, 0.12, "#2ec46d", 0, 0, 0, check, { emissive: "#2ec46d", emissiveIntensity: 0.4 });
  team[id] = { ...c, spec, tagEl, bubEl, screen, check, state: "idle", talkT: 0, jumpT: 0, phase: Math.random() * 6, last: null, history: [] };
}

// Bullpen: two rows of two desks, workers face the camera side (+z)
for (const [id, x, z] of [["market", -16.5, -3.5], ["social", -10, -3.5], ["news", -16.5, 3], ["fundamentals", -10, 3]]) {
  desk(x, z + 1.45, 3.2, 1.6, "#e9c46a");
  seat(id, x, z, 0);
}
plant(-20, -12.5); plant(-6.5, 7.5, 0.8);
// water cooler
box(1, 1.6, 1, "#e9ecef", -20.4 + 0.9, 0.8, 9.5); box(0.8, 1, 0.8, new THREE.MeshStandardMaterial({ color: "#7fd1ff", transparent: true, opacity: 0.7 }), -19.5, 2.1, 9.5);

// Research room: long table, bull vs bear, manager at the head
{
  box(6, 0.3, 2.6, "#8d5a3b", 1.5, 1.3, -8.5); box(0.4, 1.2, 0.4, "#5c3a24", -1, 0.6, -8.5); box(0.4, 1.2, 0.4, "#5c3a24", 4, 0.6, -8.5);
  seat("bull", -2.6, -8.5, Math.PI / 2, { laptopOn: false, chairColor: "#1b4332" });
  seat("bear", 5.6, -8.5, -Math.PI / 2, { laptopOn: false, chairColor: "#6a040f" });
  seat("research_manager", 1.5, -11.6, 0, { laptopOn: false, chairColor: "#3c096c" });
  laptop(scene, 1.5, 1.45, -9.3, 0);
  // whiteboard
  const wb = canvasTex(512, 256, (g, W, H) => {
    g.fillStyle = "#fff"; g.fillRect(0, 0, W, H);
    g.font = "700 40px Fredoka, sans-serif"; g.fillStyle = "#2ec46d"; g.fillText("BULL", 40, 70);
    g.fillStyle = "#e63946"; g.fillText("BEAR", 300, 70);
    g.strokeStyle = "#1d2433"; g.lineWidth = 5; g.beginPath(); g.moveTo(256, 30); g.lineTo(256, 230); g.stroke();
    g.strokeStyle = "#2ec46d"; g.beginPath(); g.moveTo(40, 200); g.lineTo(110, 150); g.lineTo(150, 170); g.lineTo(220, 100); g.stroke();
    g.strokeStyle = "#e63946"; g.beginPath(); g.moveTo(300, 100); g.lineTo(360, 150); g.lineTo(410, 130); g.lineTo(480, 200); g.stroke();
  });
  box(6, 3, 0.15, new THREE.MeshStandardMaterial({ map: wb }), 1.5, 4, -14.6);
}

// Trading desk: a wall of screens behind the trader
const tradingScreens = [];
{
  desk(1.5, 7.45, 4.4, 1.8, "#264653");
  seat("trader", 1.5, 6, 0, { chairColor: "#fb8500" });
  laptop(scene, 0, 1.4, 7.4, 0); laptop(scene, 3, 1.4, 7.4, 0);
  box(8, 0.3, 0.3, "#343a40", 1.5, 4.95, 3.3);
  box(0.3, 5, 0.3, "#343a40", -2.4, 2.5, 3.3); box(0.3, 5, 0.3, "#343a40", 5.4, 2.5, 3.3);
  for (let i = 0; i < 3; i++) {
    const tex = makeChartTex(i);
    const s = box(2.4, 1.6, 0.15, new THREE.MeshStandardMaterial({ map: tex.texture, emissive: "#ffffff", emissiveMap: tex.texture, emissiveIntensity: 0.55 }), -0.9 + i * 2.4, 3.9, 3.35);
    tradingScreens.push(tex);
  }
}
function makeChartTex(seed) {
  const c = document.createElement("canvas"); c.width = 256; c.height = 170;
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace;
  const rnd = mulberry(seed + 3);
  const pts = Array.from({ length: 40 }, (_, i) => 85 + Math.sin(i / 4 + seed) * 25 + (rnd() - 0.5) * 20);
  return { c, texture: tex, pts, rnd, mode: "flat" };
}
function drawChart(t) {
  const g = t.c.getContext("2d"), W = 256, H = 170;
  g.fillStyle = "#0b132b"; g.fillRect(0, 0, W, H);
  g.strokeStyle = "#1c2541"; g.lineWidth = 1;
  for (let y = 20; y < H; y += 30) { g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke(); }
  const up = t.mode !== "down";
  g.strokeStyle = t.mode === "flat" ? "#8d99ae" : up ? "#2ec46d" : "#ef476f"; g.lineWidth = 4;
  g.beginPath(); t.pts.forEach((p, i) => (i ? g.lineTo(i * 6.5, p) : g.moveTo(0, p))); g.stroke();
  g.fillStyle = "#ffffff"; g.font = "700 22px Fredoka, sans-serif"; g.fillText(currentTicker, 10, 28);
  t.texture.needsUpdate = true;
}
function tickCharts() {
  for (const t of tradingScreens) {
    const last = t.pts[t.pts.length - 1];
    const drift = t.mode === "up" ? -2.2 : t.mode === "down" ? 2.2 : 0;
    let n = last + drift + (t.rnd() - 0.5) * 12;
    n = Math.max(25, Math.min(160, n));
    if (n <= 26 || n >= 159) n = 85;
    t.pts.push(n); t.pts.shift();
    drawChart(t);
  }
}

// Risk room: three around a round table, open to the camera
{
  cyl(2.2, 0.25, "#6d597a", 14.5, 1.3, -8.2, scene, 28);
  cyl(0.3, 1.2, "#3d3d3d", 14.5, 0.6, -8.2, scene, 10);
  const cx = 14.5, cz = -8.2, r = 3.1;
  [["aggressive", 215], ["conservative", 270], ["neutral", 325]].forEach(([id, deg]) => {
    const a = THREE.MathUtils.degToRad(deg);
    const x = cx + Math.cos(a) * r, z = cz + Math.sin(a) * r;
    seat(id, x, z, Math.atan2(cx - x, cz - z), { laptopOn: false, chairColor: "#6d597a" });
  });
  plant(20.5, -12.5);
}

// Corner office: raised floor, glass walls, the big desk
{
  box(11, 0.3, 8, "#3b3f58", 14.5, 0.15, 6.5);
  const glass = new THREE.MeshStandardMaterial({ color: "#bfe3ff", transparent: true, opacity: 0.25, roughness: 0.05 });
  box(0.15, 3, 8, glass, 9, 1.8, 6.5);
  box(0.25, 3.1, 0.25, "#adb5bd", 9, 1.85, 2.6);
  box(0.25, 3.1, 0.25, "#adb5bd", 9, 1.85, 10.4);
  desk(14.5, 7.9, 5, 2.2, "#6f4518");
  box(1.8, 0.4, 0.15, "#ffd60a", 14.5, 1.0, 9.05, scene, { emissive: "#ffd60a", emissiveIntensity: 0.2 });
  seat("portfolio_manager", 14.5, 6.3, 0, { chairColor: "#7b2cbf" });
  team.portfolio_manager.root.position.y = 0.3;
  plant(19.8, 3.2, 0.9);
  // trophy
  box(0.6, 0.15, 0.6, "#adb5bd", 16.5, 1.47, 7.6); box(0.4, 0.6, 0.4, "#ffd60a", 16.5, 1.85, 7.6, scene, { metalness: 0.6, roughness: 0.3 });
}

// The big board on the back wall
const board = { c: document.createElement("canvas") };
board.c.width = 1024; board.c.height = 384;
board.tex = new THREE.CanvasTexture(board.c); board.tex.colorSpace = THREE.SRGBColorSpace;
box(11.2, 4.4, 0.3, "#1d2433", -12.5, 4.1, -14.6);
box(10.6, 3.8, 0.1, new THREE.MeshStandardMaterial({ map: board.tex, emissive: "#ffffff", emissiveMap: board.tex, emissiveIntensity: 0.6 }), -12.5, 4.1, -14.42);
let currentTicker = "NVDA";
function drawBoard(status = "MARKET CLOSED", rating = null) {
  const g = board.c.getContext("2d"), W = 1024, H = 384;
  g.fillStyle = "#0b132b"; g.fillRect(0, 0, W, H);
  g.fillStyle = "#ffb703"; g.font = "700 120px Fredoka, sans-serif"; g.fillText(currentTicker, 40, 140);
  g.fillStyle = "#8d99ae"; g.font = "600 44px Fredoka, sans-serif"; g.fillText(status, 40, 220);
  if (rating) {
    g.fillStyle = RATING_COLORS[rating] || "#ffb703";
    g.fillRect(40, 250, W - 80, 100);
    g.fillStyle = "#0b132b"; g.font = "700 76px Fredoka, sans-serif"; g.textAlign = "center";
    g.fillText(rating.toUpperCase(), W / 2, 327); g.textAlign = "left";
  }
  board.tex.needsUpdate = true;
}

// ---------------------------------------------------------------- confetti
const confetti = [];
function burst(at) {
  const colors = ["#ffbe0b", "#fb5607", "#ff006e", "#8338ec", "#3a86ff", "#2ec46d"];
  for (let i = 0; i < 90; i++) {
    const m = box(0.25, 0.25, 0.08, colors[i % colors.length], at.x, at.y + 3, at.z);
    m.castShadow = false;
    confetti.push({ m, v: new THREE.Vector3((Math.random() - 0.5) * 9, 6 + Math.random() * 6, (Math.random() - 0.5) * 9), r: Math.random() * 8, life: 3.5 });
  }
}

// ---------------------------------------------------------------- behaviour
function setState(id, state) {
  const a = team[id]; if (!a) return;
  a.state = state;
  a.tagEl.className = "tag " + state;
  a.check.visible = state === "done";
  if (a.screen) a.screen.material.emissiveIntensity = state === "working" ? 1.1 : 0.25;
  if (state === "working") showBubble(id, "• • •", "think", 0);
  else if (a.bubEl.classList.contains("think")) hideBubble(id);
}
function showBubble(id, text, kind = "", seconds = 7) {
  const a = team[id]; if (!a) return;
  a.bubEl.className = "bubble show " + kind;
  a.bubEl.textContent = text;
  clearTimeout(a.bubTimer);
  if (seconds) a.bubTimer = setTimeout(() => {
    if (a.state === "working") showBubble(id, "• • •", "think", 0); else hideBubble(id);
  }, seconds * 1000);
}
function hideBubble(id) { const a = team[id]; if (a) a.bubEl.className = "bubble"; }
function snippet(md, n = 150) {
  const s = md.replace(/```[\s\S]*?```/g, " ").replace(/[#*_`>|]/g, "").replace(/\[(.*?)\]\(.*?\)/g, "$1").replace(/\s+/g, " ").trim();
  return s.length > n ? s.slice(0, n).replace(/\s\S*$/, "") + "…" : s;
}
let focusId = null;
function say(id, text) {
  const a = team[id]; if (!a) return;
  a.last = text; a.history.push(text);
  a.jumpT = 0.6; a.talkT = 5;
  showBubble(id, snippet(text, 90), "", 8);
  focusId = id;
  addFeed(id, text);
}

// ---------------------------------------------------------------- feed & reader
const items = document.getElementById("items");
const feedLog = [];
function addFeed(id, text, cls = "") {
  if (items.querySelector(".empty")) items.innerHTML = "";
  const spec = AGENTS[id];
  const el = document.createElement("div");
  el.className = "item " + cls;
  const color = spec ? spec.shirt : "#8d99ae";
  el.innerHTML = `<div class="av" style="background:${color}"></div><div><div class="who"></div><div class="txt"></div></div>`;
  el.querySelector(".who").textContent = spec ? spec.name : (cls === "err" ? "Error" : "Office");
  el.querySelector(".txt").textContent = snippet(text, 240);
  const idx = feedLog.push({ id, text }) - 1;
  el.addEventListener("click", () => openReader(id, feedLog[idx].text));
  items.appendChild(el);
  items.scrollTop = items.scrollHeight;
}
const reader = document.getElementById("reader");
function openReader(id, text) {
  const spec = AGENTS[id];
  const a = team[id];
  const body = text ?? (a && a.history.length ? a.history.join("\n\n---\n\n") : null);
  document.getElementById("rWho").textContent = spec ? spec.name : "Office";
  document.getElementById("rAv").style.background = spec ? spec.shirt : "#8d99ae";
  const html = body ? (window.marked ? marked.parse(body) : body.replace(/[<>&]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" })[c]))
                    : "<p><i>Nothing said yet.</i></p>";
  document.getElementById("rBody").innerHTML = window.DOMPurify ? DOMPurify.sanitize(html) : html.replace(/<script[\s\S]*?<\/script>/gi, "");
  reader.classList.add("show");
}
document.getElementById("rClose").onclick = () => reader.classList.remove("show");
reader.addEventListener("click", (e) => { if (e.target === reader) reader.classList.remove("show"); });
addEventListener("keydown", (e) => { if (e.key === "Escape") reader.classList.remove("show"); });

// click a worker in the scene
const ray = new THREE.Raycaster(), ptr = new THREE.Vector2();
let downAt = null;
renderer.domElement.addEventListener("pointerdown", (e) => (downAt = [e.clientX, e.clientY]));
renderer.domElement.addEventListener("pointerup", (e) => {
  if (!downAt || Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 5) return;
  const r = renderer.domElement.getBoundingClientRect();
  ptr.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(ptr, camera);
  const hit = ray.intersectObjects(scene.children, true).find((h) => h.object.userData.agent);
  if (hit) openReader(hit.object.userData.agent);
});

// ---------------------------------------------------------------- controls panel
$("date").value = new Date().toISOString().slice(0, 10);
$("deckToggle").onclick = () => $("deck").classList.toggle("collapsed");
$("reset").onclick = () => { focusId = null; camera.position.copy(HOME.pos); controls.target.copy(HOME.target); };
$("ticker").addEventListener("input", () => { currentTicker = $("ticker").value.toUpperCase() || "NVDA"; drawBoard(); });
let cfg = null;
async function loadConfig() {
  try {
    cfg = await (await fetch("/api/config")).json();
  } catch {
    cfg = null;
  }
  const sel = $("provider");
  if (!cfg) {
    sel.innerHTML = "<option>offline</option>"; sel.disabled = true;
    $("demo").checked = true; $("demo").disabled = true;
    $("keyWarn").hidden = false; $("keyWarn").textContent = "No server found, so only demo mode works here.";
    return;
  }
  sel.innerHTML = cfg.providers.map((p) => `<option value="${p.id}">${p.id}${p.key_set ? "" : " (no key)"}</option>`).join("");
  const firstWithKey = cfg.providers.find((p) => p.key_set && p.key_env);
  sel.value = (cfg.providers.find((p) => p.id === cfg.default_provider && p.key_set) || firstWithKey || { id: cfg.default_provider }).id;
  onProvider(true);
  if (!cfg.providers.some((p) => p.key_set && p.key_env)) $("demo").checked = true;
  updateWarn();
}
function onProvider(initial) {
  const p = cfg.providers.find((x) => x.id === $("provider").value); if (!p) return;
  const fill = (list, opts) => ($(list).innerHTML = opts.filter((o) => o.value !== "custom").map((o) => `<option value="${o.value}">${o.label}</option>`).join(""));
  fill("quickList", p.quick); fill("deepList", p.deep);
  const pick = (opts, def) => (initial && opts.some((o) => o.value === def) ? def : (opts.find((o) => o.value !== "custom") || { value: "" }).value);
  $("quick").value = pick(p.quick, cfg.default_quick);
  $("deep").value = pick(p.deep, cfg.default_deep);
  const hint = p.id === "openrouter" ? "e.g. anthropic/claude-sonnet-5" : "type a model ID";
  $("quick").placeholder = $("deep").placeholder = p.quick.length ? "" : hint;
  updateWarn();
}
function updateWarn() {
  const w = $("keyWarn");
  if (!cfg) return;
  const p = cfg.providers.find((x) => x.id === $("provider").value);
  if (!$("demo").checked && p && !p.key_set) {
    w.hidden = false;
    w.innerHTML = `Set <code>${p.key_env}</code> in your <code>.env</code> and restart the server, or turn on demo mode.`;
  } else w.hidden = true;
}
$("provider").onchange = () => onProvider(false);
$("demo").onchange = updateWarn;

// ---------------------------------------------------------------- running
let es = null, started = 0, running = false;
function resetOffice(analysts) {
  for (const id of Object.keys(team)) {
    const off = ANALYSTS.includes(id) && !analysts.includes(id);
    team[id].history = []; team[id].last = null;
    setState(id, off ? "off" : "idle");
    hideBubble(id);
    if (off) showBubble(id, "z z z", "think", 0);
  }
  items.innerHTML = ""; feedLog.length = 0;
  $("banner").classList.remove("show");
  $("ticket").hidden = true;
  tradingScreens.forEach((t) => (t.mode = "flat"));
}
function finish() {
  running = false;
  $("run").disabled = false; $("run").textContent = "▶ Run again";
  if (es) { es.close(); es = null; }
}
$("run").onclick = () => {
  if (running) return;
  const analysts = [...document.querySelectorAll(".analysts input:checked")].map((i) => i.value);
  if (!analysts.length) { alert("Pick at least one analyst."); return; }
  if (!$("demo").checked && cfg && (!$("quick").value.trim() || !$("deep").value.trim())) {
    alert("Enter a quick and a deep model ID (or turn on demo mode)."); return;
  }
  currentTicker = ($("ticker").value || "NVDA").toUpperCase();
  const demo = $("demo").checked || !cfg;
  resetOffice(analysts);
  drawBoard("ANALYZING…");
  running = true; started = performance.now();
  $("run").disabled = true; $("run").textContent = demo ? "Demo running…" : "Team at work…";
  const q = new URLSearchParams({ ticker: currentTicker, date: $("date").value, analysts: analysts.join(","),
    depth: $("depth").value, demo: demo ? "1" : "0", book: broker?.configured && $("book").checked ? "1" : "0" });
  if (cfg && !demo) { q.set("provider", $("provider").value); q.set("quick", $("quick").value.trim()); q.set("deep", $("deep").value.trim()); }
  if (!cfg) return localDemo(analysts);
  es = new EventSource("/api/run?" + q);
  es.onmessage = (m) => handle(JSON.parse(m.data));
  es.addEventListener("end", finish);
  es.onerror = () => { if (running) { addFeed(null, "Lost the connection to the server.", "err"); drawBoard("CONNECTION LOST"); finish(); } };
};
function handle(ev) {
  switch (ev.type) {
    case "status": setState(ev.agent, ev.state);
      if (ev.agent === "trader" && ev.state === "working") tradingScreens.forEach((t) => (t.mode = "up"));
      break;
    case "say": say(ev.agent, ev.text); break;
    case "tool":
      if (ev.agent && team[ev.agent]) showBubble(ev.agent, "📞 " + ev.name.replace(/^get_/, "").replace(/_/g, " "), "tool", 2.5);
      break;
    case "log": addFeed(null, ev.text, "sys"); break;
    case "error": addFeed(null, ev.message, "err"); drawBoard("SOMETHING BROKE"); break;
    case "decision": {
      drawBoard(`${ev.date}${ev.demo ? " · DEMO" : ""}`, ev.rating);
      const up = ["Buy", "Overweight"].includes(ev.rating), down = ["Sell", "Underweight"].includes(ev.rating);
      tradingScreens.forEach((t) => (t.mode = up ? "up" : down ? "down" : "flat"));
      $("bRating").textContent = ev.rating.toUpperCase();
      $("bRating").style.background = RATING_COLORS[ev.rating] || "#ffb703";
      $("bTicker").textContent = ev.ticker;
      $("bSub").textContent = ev.demo ? "Demo call (sample text)" : `Final call · ${ev.date}`;
      const link = $("bReport");
      if (ev.report) { link.href = ev.report; link.hidden = false; } else link.hidden = true;
      showTicket(ev);
      $("banner").classList.add("show");
      burst(team.portfolio_manager.root.position);
      for (const id of Object.keys(team)) if (team[id].state !== "off") team[id].jumpT = 0.6 + Math.random() * 0.3;
      focusId = "portfolio_manager";
      break;
    }
  }
}
// ---------------------------------------------------------------- Alpaca paper account
let broker = null, ticketPlan = null, ticketDecision = null;
const usd = (n) => (n == null ? "–" : n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }));
const esc = (t) => String(t).replace(/[<>&"]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" })[c]);
async function loadBroker() {
  const body = $("acctBody");
  try {
    broker = await (await fetch("/api/broker")).json();
  } catch {
    broker = null; body.textContent = "Needs the office server."; return;
  }
  $("bookTog").hidden = !(broker.configured && !broker.error);
  if (!broker.configured) { body.innerHTML = `Not connected. ${esc(broker.reason)}`; return; }
  if (broker.error) { body.innerHTML = `<span class="down">${esc(broker.error)}</span>`; return; }
  const pos = broker.positions.map((p) =>
    `<div class="pos"><span>${esc(p.symbol)} × ${p.qty}</span><span class="${p.unrealized_pl >= 0 ? "up" : "down"}">${usd(p.market_value)} (${p.unrealized_pl >= 0 ? "+" : ""}${usd(p.unrealized_pl)})</span></div>`).join("");
  body.innerHTML = `Equity <span class="num">${usd(broker.equity)}</span> · Cash <span class="num">${usd(broker.cash)}</span>
    ${pos || "<div>No positions yet.</div>"}
    <div style="margin-top:4px">Full Buy = ${broker.limits.max_position_pct}% of equity · max ${usd(broker.limits.max_order_usd)} per order</div>`;
}
$("acctRefresh").onclick = loadBroker;

function renderPlan(p) {
  ticketPlan = p;
  const verb = p.action === "buy" ? "BUY" : p.action === "sell" ? "SELL" : "NO ORDER";
  $("tkLine").textContent = p.action === "none" ? `${verb} · ${p.symbol}` : `${verb} ${p.qty} ${p.symbol}  ≈ ${usd(p.est_value)}`;
  $("tkLine").className = "tk-line " + (p.action === "buy" ? "up" : p.action === "sell" ? "down" : "");
  $("tkWhy").textContent = p.reason;
  $("tkPlace").hidden = p.action === "none";
  $("tkPlace").textContent = `Place paper ${p.action} order`;
  $("tkPlace").disabled = false;
}
async function post(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-Office": "1" }, body: JSON.stringify(body) });
  return { status: r.status, data: await r.json().catch(() => ({})) };
}
async function showTicket(ev) {
  const t = $("ticket");
  $("tkMsg").textContent = ""; $("tkPlace").hidden = true; ticketDecision = ev.decision_id;
  if (ev.demo || !ev.decision_id) {
    t.hidden = false; $("tkLine").textContent = "No order in demo mode"; $("tkLine").className = "tk-line";
    $("tkWhy").textContent = "Run a real analysis to get a paper order you can place."; return;
  }
  if (!ev.broker) {
    t.hidden = false; $("tkLine").textContent = "Paper trading is off"; $("tkLine").className = "tk-line";
    $("tkWhy").textContent = "Add your Alpaca paper keys to .env and restart to trade this call."; return;
  }
  t.hidden = false; $("tkLine").textContent = "Working out the order…"; $("tkWhy").textContent = "";
  const { status, data } = await post("/api/broker/plan", { decision_id: ev.decision_id });
  if (status === 200) renderPlan(data.plan);
  else { $("tkLine").textContent = "Could not plan an order"; $("tkWhy").textContent = data.error || `Error ${status}`; }
}
$("tkPlace").onclick = async () => {
  if (!ticketPlan || ticketPlan.action === "none") return;
  const b = $("tkPlace"); b.disabled = true; $("tkMsg").textContent = "Sending…"; $("tkMsg").className = "tk-msg";
  const { status, data } = await post("/api/broker/order", { decision_id: ticketDecision, action: ticketPlan.action, qty: ticketPlan.qty });
  if (status === 200) {
    const o = data.order;
    b.hidden = true;
    $("tkMsg").textContent = `Order sent: ${o.side} ${o.qty} ${o.symbol} (${o.status}).`; $("tkMsg").className = "tk-msg up";
    addFeed("trader", `Placed a paper ${o.side} order for ${o.qty} ${o.symbol} on Alpaca. Status: ${o.status}. Market orders fill at the next open if the market is closed.`);
    team.trader.jumpT = 0.6; focusId = "trader";
    tradingScreens.forEach((t) => (t.mode = o.side === "buy" ? "up" : "down"));
    setTimeout(loadBroker, 2500);
  } else {
    if (data.plan) renderPlan(data.plan); else b.disabled = false;
    $("tkMsg").textContent = data.error || `Error ${status}`; $("tkMsg").className = "tk-msg down";
  }
};

// Offline fallback: the same demo script, played in the page.
function localDemo(analysts) {
  const T = currentTicker, N = "\n\n_(Demo mode: sample text.)_";
  const steps = [];
  const at = (s, ev) => steps.push([s, ev]);
  let t = 0.3;
  analysts.forEach((a) => at(t, { type: "status", agent: a, state: "working" }));
  const texts = { market: `Momentum on ${T} is positive; RSI near 61.`, social: "Chatter is upbeat with some valuation worry.",
    news: "No company-specific shocks; rates steady.", fundamentals: "Strong growth, rich multiple." };
  analysts.forEach((a) => { t += 1.2; at(t, { type: "say", agent: a, text: texts[a] + N }); at(t, { type: "status", agent: a, state: "done" }); });
  const seq = [["bull", "Trend and growth say up."], ["bear", "Valuation leaves no room for a miss."], ["research_manager", "**Overweight**, sized for the risk."],
    ["trader", "**Buy**, scale in, 8% stop."], ["aggressive", "Full size now!"], ["conservative", "Half size, earnings soon."], ["neutral", "Scale in as planned."],
    ["portfolio_manager", `**Final rating: Overweight** on ${T}.`]];
  seq.forEach(([a, s]) => { at(t += 0.2, { type: "status", agent: a, state: "working" }); t += 1.8; at(t, { type: "say", agent: a, text: s + N }); at(t, { type: "status", agent: a, state: "done" }); });
  at(t + 0.5, { type: "decision", rating: "Overweight", ticker: T, date: $("date").value, demo: true });
  steps.forEach(([s, ev]) => setTimeout(() => handle(ev), s * 1000));
  setTimeout(finish, (t + 0.6) * 1000);
}

// ---------------------------------------------------------------- loop
function resize() {
  const w = innerWidth, h = innerHeight;
  renderer.setSize(w, h); labels.setSize(w, h);
  camera.aspect = w / h;
  // On wide screens, centre the office in the gap between the two side panels.
  if (w > 860) {
    const left = $("deck").getBoundingClientRect().right, right = $("feed").getBoundingClientRect().left;
    camera.setViewOffset(w, h, -Math.round((left + right) / 2 - w / 2), 0, w, h);
  } else {
    camera.clearViewOffset();
  }
  camera.updateProjectionMatrix();
}
addEventListener("resize", resize); resize();

const clock = new THREE.Clock();
let chartAcc = 0;
const want = new THREE.Vector3();
function frame() {
  const dt = Math.min(clock.getDelta(), 0.05), t = clock.elapsedTime;
  for (const a of Object.values(team)) {
    const p = a.parts;
    const typing = a.state === "working";
    if (a.state === "off") {
      p.neck.rotation.x = 0.45 + Math.sin(t * 1.2 + a.phase) * 0.05;   // dozing
      p.armL.rotation.x = p.armR.rotation.x = -0.6;
    } else if (typing) {
      p.armL.rotation.x = -1.2 + Math.sin(t * 18 + a.phase) * 0.18;
      p.armR.rotation.x = -1.2 + Math.cos(t * 18 + a.phase) * 0.18;
      p.neck.rotation.x = 0.12 + Math.sin(t * 3) * 0.04;
      p.neck.rotation.y = Math.sin(t * 0.9 + a.phase) * 0.2;
    } else if (a.talkT > 0) {
      a.talkT -= dt;
      p.armR.rotation.x = -1.6 + Math.sin(t * 7) * 0.5;
      p.armR.rotation.z = 0.2;
      p.armL.rotation.x = -0.8 + Math.sin(t * 5 + 1) * 0.3;
      p.neck.rotation.y = Math.sin(t * 2.5) * 0.25;
      p.neck.rotation.x = Math.sin(t * 9) * 0.05;
    } else {
      p.armL.rotation.x = p.armR.rotation.x = -0.85 + Math.sin(t * 1.5 + a.phase) * 0.04;
      p.armR.rotation.z = 0;
      p.neck.rotation.x = 0; p.neck.rotation.y *= 0.95;
    }
    let jump = 0;
    if (a.jumpT > 0) { a.jumpT -= dt; jump = Math.sin(Math.max(a.jumpT, 0) / 0.6 * Math.PI) * 0.9; }
    a.body.position.y = 0.85 - 2 * a.S + jump + Math.sin(t * 2 + a.phase) * 0.02;
    if (a.check.visible) a.check.rotation.y += dt * 2;
  }
  chartAcc += dt;
  if (chartAcc > 0.25) { chartAcc = 0; tickCharts(); }
  for (let i = confetti.length - 1; i >= 0; i--) {
    const c = confetti[i];
    c.v.y -= 12 * dt; c.m.position.addScaledVector(c.v, dt); c.m.rotation.x += c.r * dt; c.m.rotation.y += c.r * dt;
    if (c.m.position.y < 0.1) { c.m.position.y = 0.1; c.v.set(0, 0, 0); }
    if ((c.life -= dt) <= 0) { scene.remove(c.m); confetti.splice(i, 1); }
  }
  if ($("follow").checked && focusId && team[focusId]) {
    team[focusId].root.getWorldPosition(want);
    want.y = 1.5;
    controls.target.lerp(want, 0.025);
  }
  if (running) {
    const s = Math.floor((performance.now() - started) / 1000);
    $("clock").textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  }
  controls.update();
  renderer.render(scene, camera);
  labels.render(scene, camera);
  requestAnimationFrame(frame);
}
drawBoard();
tradingScreens.forEach(drawChart);
loadConfig();
loadBroker();
frame();
