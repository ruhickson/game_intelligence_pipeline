const TILE = 30;
const LETTERS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"];
// Bottom avenue is the first tag group. The player digs upward.
// A–F tags, G coarse recency (4), H fine recency (3), I review score (5), J review count (3).
const MAP = [
  "###############",
  "#XXXXXXXXXXXXX#",
  "#XXXXXXXXXXXXX#",
  "#XXXXXXXXXXXXX#",
  "#XXXXXXXXXXXXX#",
  "#XXXXXXXXXXXXX#",
  "#XXXXXXXXXXXXX#",
  "#ddddddddddddd#",
  "#sssssssssssss#",
  "#J.J.J........#",
  "#ddddddddddddd#",
  "#I.I.I.I.I....#",
  "#sssssssssssss#",
  "#H.H.H........#",
  "#ddddddddddddd#",
  "#G.G.G.G......#",
  "#sssssssssssss#",
  "#F.F.F........#",
  "#ddddddddddddd#",
  "#E.E.E........#",
  "#sssssssssssss#",
  "#D.D.D........#",
  "#ddddddddddddd#",
  "#C.C.C........#",
  "#sssssssssssss#",
  "#B.B.B........#",
  "#ddddddddddddd#",
  "#A.A.A........#",
  "#sssssssssssss#",
  "#ddddddddddddd#",
  "#...........P.#",
  "###############",
];

const ROWS = MAP.length;
const COLS = MAP[0].length;
const DIRS = {
  up: { c: 0, r: -1 },
  down: { c: 0, r: 1 },
  left: { c: -1, r: 0 },
  right: { c: 1, r: 0 },
};
const KEY_DIR = {
  ArrowUp: "up",
  ArrowDown: "down",
  ArrowLeft: "left",
  ArrowRight: "right",
  w: "up",
  a: "left",
  s: "down",
  d: "right",
  W: "up",
  A: "left",
  S: "down",
  D: "right",
};
const MONSTER_COLORS = ["#e05a3c", "#3aa0d8", "#d8a13a", "#7dce6a", "#c57bdb"];

const canvas = document.getElementById("field");
const ctx = canvas.getContext("2d");
canvas.width = COLS * TILE;
canvas.height = ROWS * TILE;

const progressEl = document.getElementById("progress");
const messageEl = document.getElementById("message");
const promptEl = document.getElementById("prompt");
const optionsEl = document.getElementById("options");
const filtersEl = document.getElementById("filters");
const foundEl = document.getElementById("found");
const shortfallEl = document.getElementById("shortfall");
const sourceEl = document.getElementById("source");

const keys = new Set();
let blueprint = null;
let state = null;
let panelSig = "";
let lastMove = 0;
let queryToken = 0;

function fail(text) {
  promptEl.textContent = text;
  optionsEl.textContent = "";
}

function inBounds(c, r) {
  return c >= 0 && r >= 0 && c < COLS && r < ROWS;
}

function buildWorld() {
  for (const row of MAP) {
    if (row.length !== COLS) throw new Error("map row length mismatch");
  }
  const avenueRows = [];
  for (let r = ROWS - 1; r >= 0; r -= 1) {
    if ([...MAP[r]].some((ch) => LETTERS.includes(ch))) avenueRows.push(r);
  }
  if (!blueprint || avenueRows.length !== blueprint.encounters.length) {
    throw new Error("avenue count does not match the query");
  }
  const tiles = MAP.map((row) => row.split(""));
  const encounters = blueprint.encounters.map((enc, index) => ({
    id: enc.id,
    dimension: enc.dimension,
    prompt: enc.prompt,
    options: enc.options.map((option) => ({ ...option })),
    optionsByParent: enc.optionsByParent || null,
    skipWhen: enc.skipWhen || null,
    row: avenueRows[index],
    monsters: [],
    selection: null,
    skipped: false,
  }));
  let start = null;
  for (let r = 0; r < ROWS; r += 1) {
    for (let c = 0; c < COLS; c += 1) {
      const ch = tiles[r][c];
      if (ch === "P") {
        start = { c, r };
        tiles[r][c] = ".";
      } else if (LETTERS.includes(ch)) {
        const enc = encounters.find((item) => item.row === r);
        enc.monsters.push({ c, r, index: enc.monsters.length });
        tiles[r][c] = ".";
      }
    }
  }
  if (!start) throw new Error("map has no start");
  for (const enc of encounters) {
    if (enc.monsters.length !== enc.options.length) {
      throw new Error(`${enc.id} monster count does not match its options`);
    }
  }
  state = {
    tiles,
    encounters,
    player: { c: start.c, r: start.r },
    facing: "up",
    held: null,
    message: "Dig up to the first avenue.",
    debris: [],
    query: "idle",
    games: null,
    shortfall: null,
    queryError: "",
    wantOpen: false,
    crackStart: 0,
    opened: false,
  };
  panelSig = "";
}

function heldEncounter() {
  return state.encounters.find((enc) => enc.id === state.held) || null;
}

function requiredEncounters() {
  return state.encounters.filter((enc) => !enc.skipped);
}

function readyForQuery() {
  return state.encounters.every((enc) => enc.skipped || enc.selection);
}

function monsterAt(c, r) {
  for (const enc of state.encounters) {
    if (enc.selection || enc.skipped) continue;
    if (enc.monsters.some((monster) => monster.c === c && monster.r === r)) return true;
  }
  return false;
}

function adjacentToDiscover() {
  const { c, r } = state.player;
  for (let rr = 0; rr < ROWS; rr += 1) {
    for (let cc = 0; cc < COLS; cc += 1) {
      if (state.tiles[rr][cc] !== "X") continue;
      if (Math.abs(cc - c) + Math.abs(rr - r) === 1) return true;
    }
  }
  return false;
}

function puff(c, r, kind) {
  state.debris.push({ c, r, kind, born: performance.now() });
}

function tryMove(dir) {
  if (!state || state.held || state.opened) return;
  const step = DIRS[dir];
  const c = state.player.c + step.c;
  const r = state.player.r + step.r;
  if (!inBounds(c, r)) return;
  const tile = state.tiles[r][c];
  if (tile === "#" || tile === "X") return;
  if (monsterAt(c, r)) return;
  if (tile === "d" || tile === "s") {
    state.tiles[r][c] = ".";
    puff(c, r, tile);
  }
  state.player.c = c;
  state.player.r = r;
  state.facing = dir;
  const enc = state.encounters.find((item) => item.row === r && !item.selection && !item.skipped);
  if (enc) {
    state.held = enc.id;
    state.message = "The monsters block the avenue. Pick one.";
  }
}

function pick(index) {
  const enc = heldEncounter();
  if (!enc || enc.selection) return;
  const option = enc.options[index];
  if (!option) return;
  enc.selection = option.id;
  enc.monsters = [];
  state.held = null;
  state.message = `Added ${option.label}.`;
  if (enc.id === "recency") {
    const fine = state.encounters.find((item) => item.id === "recency-fine");
    if (option.id === "any") {
      fine.skipped = true;
      fine.monsters = [];
      fine.selection = null;
      state.message = "No recency clause. The next avenue stays open.";
    } else if (fine.optionsByParent && fine.optionsByParent[option.id]) {
      fine.skipped = false;
      fine.options = fine.optionsByParent[option.id];
    }
  }
  if (readyForQuery()) {
    state.message = "Every avenue added a filter. Dig up to the tile.";
    startQuery();
  }
}

function startQuery() {
  const token = ++queryToken;
  const choices = {};
  for (const enc of state.encounters) {
    if (enc.skipped) continue;
    choices[enc.id] = enc.selection;
  }
  state.query = "loading";
  state.queryError = "";
  state.games = null;
  state.shortfall = null;
  fetch("/api/discover", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ choices }),
  })
    .then(async (res) => {
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || "The query failed.");
      return data;
    })
    .then((data) => {
      if (token !== queryToken) return;
      state.games = data.games || [];
      state.shortfall = data.shortfall || null;
      state.query = "ready";
    })
    .catch((err) => {
      if (token !== queryToken) return;
      state.query = "error";
      state.queryError = err.message || "The query failed.";
      state.message = state.queryError;
    });
}

function tryOpen() {
  if (!state || state.opened) return;
  if (!readyForQuery()) {
    state.message = "The avenues still want an answer.";
    return;
  }
  if (!adjacentToDiscover()) {
    state.message = "Dig up next to the tile, then click it.";
    return;
  }
  state.wantOpen = true;
  if (!state.crackStart) state.crackStart = performance.now();
  state.message = state.query === "ready" ? "The tile is cracking." : "The tile is cracking. The query is still running.";
  if (state.query === "error") startQuery();
}

function cellFromEvent(ev) {
  const rect = canvas.getBoundingClientRect();
  const x = (ev.clientX - rect.left) * (canvas.width / rect.width);
  const y = (ev.clientY - rect.top) * (canvas.height / rect.height);
  return { c: Math.floor(x / TILE), r: Math.floor(y / TILE) };
}

function fitText(text, max) {
  if (ctx.measureText(text).width <= max) return text;
  let cut = text;
  while (cut.length > 1 && ctx.measureText(`${cut}…`).width > max) cut = cut.slice(0, -1);
  return `${cut}…`;
}

function drawTile(c, r) {
  const x = c * TILE;
  const y = r * TILE;
  const tile = state.tiles[r][c];
  ctx.fillStyle = "#120c08";
  ctx.fillRect(x, y, TILE, TILE);
  if (tile === "#") {
    ctx.fillStyle = "#2c1d12";
    ctx.fillRect(x, y, TILE, TILE);
    ctx.fillStyle = "#3d2918";
    ctx.fillRect(x, y, TILE, 3);
  } else if (tile === "d") {
    ctx.fillStyle = "#7a4324";
    ctx.fillRect(x, y, TILE, TILE);
    ctx.fillStyle = "#5c3018";
    ctx.fillRect(x + 6, y + 8, 4, 3);
    ctx.fillRect(x + 16, y + 16, 4, 3);
  } else if (tile === "s") {
    ctx.fillStyle = "#e0c36a";
    ctx.fillRect(x, y, TILE, TILE);
    ctx.fillStyle = "#c4a24e";
    ctx.fillRect(x + 5, y + 7, 3, 3);
    ctx.fillRect(x + 16, y + 16, 3, 3);
  } else if (tile === "X") {
    ctx.fillStyle = "#1f6b4a";
    ctx.fillRect(x, y, TILE, TILE);
    ctx.strokeStyle = "#d7c07a";
    ctx.strokeRect(x + 2, y + 2, TILE - 4, TILE - 4);
  }
}

function slabBox() {
  let minC = COLS;
  let maxC = 0;
  let minR = ROWS;
  let maxR = 0;
  for (let r = 0; r < ROWS; r += 1) {
    for (let c = 0; c < COLS; c += 1) {
      if (state.tiles[r][c] !== "X") continue;
      minC = Math.min(minC, c);
      maxC = Math.max(maxC, c);
      minR = Math.min(minR, r);
      maxR = Math.max(maxR, r);
    }
  }
  return {
    x: minC * TILE,
    y: minR * TILE,
    w: (maxC - minC + 1) * TILE,
    h: (maxR - minR + 1) * TILE,
  };
}

function drawDiscover(now) {
  const box = slabBox();
  if (state.opened) {
    ctx.fillStyle = "#07140f";
    ctx.fillRect(box.x, box.y, box.w, box.h);
    ctx.strokeStyle = "#e2b657";
    ctx.strokeRect(box.x + 3, box.y + 3, box.w - 6, box.h - 6);
    const games = state.games || [];
    if (!games.length) {
      ctx.fillStyle = "#f6ead7";
      ctx.font = "700 14px Segoe UI, sans-serif";
      ctx.textAlign = "center";
      const note = state.shortfall ? state.shortfall.message : "The query returned no games.";
      wrapText(note, box.x + box.w / 2, box.y + 36, box.w - 28, 18);
      ctx.textAlign = "left";
      return;
    }
    const slot = (box.h - 16) / games.length;
    games.forEach((game, index) => {
      const gy = box.y + 8 + index * slot;
      ctx.fillStyle = "#143028";
      ctx.fillRect(box.x + 8, gy, box.w - 16, slot - 6);
      ctx.fillStyle = "#f6ead7";
      ctx.font = "700 13px Segoe UI, sans-serif";
      ctx.textAlign = "left";
      ctx.fillText(fitText(`${index + 1}. ${game.title}`, box.w - 32), box.x + 16, gy + 18);
      ctx.fillStyle = "#cbb89a";
      ctx.font = "11px Segoe UI, sans-serif";
      const meta = `${game.review_score} · ${game.released} · ${Number(game.total_reviews).toLocaleString()} reviews`;
      ctx.fillText(fitText(meta, box.w - 32), box.x + 16, gy + 34);
    });
    return;
  }
  ctx.fillStyle = "#f6ead7";
  ctx.font = "700 15px Segoe UI, sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("discover your", box.x + box.w / 2, box.y + box.h / 2 - 8);
  ctx.fillText("next games", box.x + box.w / 2, box.y + box.h / 2 + 14);
  ctx.textAlign = "left";
  if (state.wantOpen) {
    ctx.strokeStyle = "#f0d48a";
    ctx.beginPath();
    const crack = ((now - state.crackStart) / 650) % 1;
    ctx.moveTo(box.x + box.w * 0.2, box.y + 10);
    ctx.lineTo(box.x + box.w * (0.35 + crack * 0.2), box.y + box.h * 0.55);
    ctx.lineTo(box.x + box.w * 0.7, box.y + box.h - 12);
    ctx.stroke();
  }
}

function wrapText(text, x, y, max, lineHeight) {
  const words = text.split(" ");
  let line = "";
  let yy = y;
  for (const word of words) {
    const next = line ? `${line} ${word}` : word;
    if (ctx.measureText(next).width > max && line) {
      ctx.fillText(line, x, yy);
      line = word;
      yy += lineHeight;
    } else {
      line = next;
    }
  }
  if (line) ctx.fillText(line, x, yy);
}

function drawMonster(monster, color, now, asking) {
  const bob = asking ? Math.sin(now / 160) * 2 : 0;
  const x = monster.c * TILE + TILE / 2;
  const y = monster.r * TILE + TILE / 2 + bob;
  if (asking) {
    ctx.strokeStyle = "#e2b657";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(x, y, 13, 0, Math.PI * 2);
    ctx.stroke();
    ctx.lineWidth = 1;
  }
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(x, y, 10, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#1a100b";
  ctx.fillRect(x - 5, y - 3, 3, 3);
  ctx.fillRect(x + 2, y - 3, 3, 3);
  ctx.fillStyle = "#f6ead7";
  ctx.font = "700 10px Segoe UI, sans-serif";
  ctx.textAlign = "center";
  ctx.fillText(String(monster.index + 1), x, y + 16);
  ctx.textAlign = "left";
}

function drawPlayer() {
  const x = state.player.c * TILE + TILE / 2;
  const y = state.player.r * TILE + TILE / 2;
  ctx.fillStyle = "#f4f0e6";
  ctx.beginPath();
  ctx.arc(x, y, 9, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#d64545";
  ctx.fillRect(x - 9, y - 3, 18, 4);
  ctx.fillStyle = "#f4f0e6";
  const nose = {
    up: [x, y - 14, x - 4, y - 5, x + 4, y - 5],
    down: [x, y + 14, x - 4, y + 5, x + 4, y + 5],
    left: [x - 14, y, x - 5, y - 4, x - 5, y + 4],
    right: [x + 14, y, x + 5, y - 4, x + 5, y + 4],
  }[state.facing];
  ctx.beginPath();
  ctx.moveTo(nose[0], nose[1]);
  ctx.lineTo(nose[2], nose[3]);
  ctx.lineTo(nose[4], nose[5]);
  ctx.fill();
}

function drawDebris(now) {
  state.debris = state.debris.filter((bit) => now - bit.born < 280);
  for (const bit of state.debris) {
    const age = (now - bit.born) / 280;
    ctx.globalAlpha = 1 - age;
    ctx.fillStyle = bit.kind === "s" ? "#e0c36a" : "#7a4324";
    ctx.fillRect(bit.c * TILE + 8, bit.r * TILE + 8 - age * 8, 5, 5);
    ctx.globalAlpha = 1;
  }
}

function draw(now) {
  for (let r = 0; r < ROWS; r += 1) {
    for (let c = 0; c < COLS; c += 1) drawTile(c, r);
  }
  drawDiscover(now);
  drawDebris(now);
  for (const enc of state.encounters) {
    const asking = enc.id === state.held;
    for (const monster of enc.monsters) {
      drawMonster(monster, MONSTER_COLORS[monster.index % MONSTER_COLORS.length], now, asking);
    }
  }
  drawPlayer();
}

function appendClause(el, text) {
  const parts = String(text).split(/(\d{4}-\d{2}-\d{2})/);
  for (const part of parts) {
    if (/^\d{4}-\d{2}-\d{2}$/.test(part)) {
      const date = document.createElement("span");
      date.style.whiteSpace = "nowrap";
      date.textContent = part;
      el.append(date);
    } else {
      el.append(document.createTextNode(part));
    }
  }
}

function choiceLine(enc) {
  const opt = enc.options.find((option) => option.id === enc.selection);
  if (!opt) return null;
  if (enc.id === "recency") {
    const fine = state.encounters.find((item) => item.id === "recency-fine");
    if (fine && fine.selection) {
      return { label: opt.label, detail: "replaced by the next cut" };
    }
  }
  return { label: opt.label, detail: opt.detail };
}

function renderPanel() {
  const required = requiredEncounters();
  const done = required.filter((enc) => enc.selection).length;
  progressEl.textContent = `Avenues ${done}/${required.length}`;
  messageEl.textContent = state.message;
  const enc = heldEncounter();
  if (enc) {
    promptEl.textContent = enc.prompt;
    optionsEl.replaceChildren(
      ...enc.options.map((opt, index) => {
        const btn = document.createElement("button");
        btn.className = "opt";
        btn.type = "button";
        btn.style.borderLeft = `6px solid ${MONSTER_COLORS[index % MONSTER_COLORS.length]}`;
        const strong = document.createElement("strong");
        strong.textContent = `${index + 1}. ${opt.label}`;
        const span = document.createElement("span");
        appendClause(span, opt.detail);
        btn.append(strong, span);
        btn.addEventListener("click", () => pick(index));
        return btn;
      }),
    );
  } else if (state.opened) {
    promptEl.textContent = state.games && state.games.length ? "Games from the query." : "The query came up short.";
    optionsEl.replaceChildren();
  } else if (readyForQuery()) {
    promptEl.textContent = "Click the discover tile.";
    optionsEl.replaceChildren();
  } else {
    promptEl.textContent = "Knock the dirt and sand aside.";
    optionsEl.replaceChildren();
  }

  filtersEl.replaceChildren();
  for (const item of state.encounters) {
    if (item.skipped || !item.selection) continue;
    const line = choiceLine(item);
    if (!line) continue;
    const row = document.createElement("p");
    row.className = "filter-line";
    row.append(`${line.label}: `);
    appendClause(row, line.detail);
    filtersEl.append(row);
  }

  foundEl.replaceChildren();
  shortfallEl.textContent = state.opened && state.shortfall ? state.shortfall.message : "";
  if (state.opened && state.games && state.games.length) {
    const heading = document.createElement("h2");
    heading.textContent = "Inside the tile";
    foundEl.append(heading);
    for (const game of state.games) {
      const card = document.createElement("article");
      card.className = "card";
      const title = document.createElement("h3");
      title.textContent = game.title;
      const body = document.createElement("p");
      body.textContent = [
        game.review_score,
        game.released,
        `${Number(game.total_reviews).toLocaleString()} reviews (${Number(game.positive).toLocaleString()} positive, ${Number(game.negative).toLocaleString()} negative)`,
        `app ${game.app_id}`,
      ].join(" · ");
      card.append(title, body);
      foundEl.append(card);
    }
  }
  sourceEl.textContent = "findGames on games and game_tags. The games inside the tile are the first rows of that query.";
}

function signature() {
  return JSON.stringify({
    held: state.held,
    sels: state.encounters.map((enc) => enc.selection),
    skipped: state.encounters.filter((enc) => enc.skipped).map((enc) => enc.id),
    options: state.encounters.map((enc) => enc.options.map((opt) => opt.id).join("|")),
    message: state.message,
    query: state.query,
    opened: state.opened,
    wantOpen: state.wantOpen,
    games: (state.games || []).map((game) => game.app_id),
    short: state.shortfall && state.shortfall.message,
  });
}

function frame(now) {
  if (state && keys.size && now - lastMove >= 145) {
    lastMove = now;
    tryMove(keys.values().next().value);
  }
  if (state && state.wantOpen && !state.opened && state.query === "ready" && Array.isArray(state.games)) {
    if (now - state.crackStart > 650) {
      state.opened = true;
      state.message = state.shortfall ? state.shortfall.message : "The tile broke open.";
    }
  }
  if (state) {
    draw(now);
    const sig = signature();
    if (sig !== panelSig) {
      panelSig = sig;
      renderPanel();
    }
  }
  requestAnimationFrame(frame);
}

window.addEventListener("keydown", (ev) => {
  if (!state) return;
  const dir = KEY_DIR[ev.key];
  if (dir) {
    ev.preventDefault();
    const now = performance.now();
    if (now - lastMove >= 145) {
      lastMove = now;
      tryMove(dir);
    }
    keys.add(dir);
    return;
  }
  if (ev.key >= "1" && ev.key <= "5") {
    ev.preventDefault();
    pick(Number(ev.key) - 1);
  }
});

window.addEventListener("keyup", (ev) => {
  const dir = KEY_DIR[ev.key];
  if (dir) keys.delete(dir);
});

canvas.addEventListener("click", (ev) => {
  canvas.focus();
  if (!state) return;
  const cell = cellFromEvent(ev);
  if (!inBounds(cell.c, cell.r)) return;
  const enc = heldEncounter();
  if (enc) {
    const monster = enc.monsters.find((item) => item.c === cell.c && item.r === cell.r);
    if (monster) {
      pick(monster.index);
      return;
    }
  }
  if (state.tiles[cell.r][cell.c] === "X") tryOpen();
});

window.__digdug = {
  choose(n) {
    pick(n - 1);
  },
  reset() {
    queryToken += 1;
    keys.clear();
    buildWorld();
    renderPanel();
  },
  snapshot() {
    if (!state) return null;
    return {
      c: state.player.c,
      r: state.player.r,
      facing: state.facing,
      held: state.held,
      query: state.query,
      opened: state.opened,
      wantOpen: state.wantOpen,
      message: state.message,
      adjacent: adjacentToDiscover(),
      dirt: state.tiles.flat().filter((tile) => tile === "d").length,
      sand: state.tiles.flat().filter((tile) => tile === "s").length,
      skipped: state.encounters.filter((enc) => enc.skipped).map((enc) => enc.id),
      selections: Object.fromEntries(state.encounters.map((enc) => [enc.id, enc.selection])),
      games: state.games,
      shortfall: state.shortfall,
      tile: state.tiles[state.player.r][state.player.c],
    };
  },
};

fetch("/api/level")
  .then((res) => {
    if (!res.ok) throw new Error("level failed");
    return res.json();
  })
  .then((level) => {
    blueprint = level;
    buildWorld();
    renderPanel();
    canvas.focus();
  })
  .catch(() => {
    fail("Could not load the avenues.");
  });

requestAnimationFrame(frame);
