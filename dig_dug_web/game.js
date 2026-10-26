const TILE = 32;
const LETTERS = ["A", "B", "C", "H", "I", "J", "K"];
const MAP = [
  "###############",
  "#XXXXXXXXXXXXX#",
  "#XXXXXXXXXXXXX#",
  "#XXXXXXXXXXXXX#",
  "#XXXXXXXXXXXXX#",
  "#XXXXXXXXXXXXX#",
  "#XXXXXXXXXXXXX#",
  "#sssssssssssss#",
  "#ddddddddddddd#",
  "#K.K..........#",
  "#sssssssssssss#",
  "#J.J..........#",
  "#ddddddddddddd#",
  "#I.I..........#",
  "#sssssssssssss#",
  "#H.H..........#",
  "#ddddddddddddd#",
  "#C.C.C........#",
  "#sssssssssssss#",
  "#B.B.B........#",
  "#ddddddddddddd#",
  "#A.A.A........#",
  "#sssssssssssss#",
  "#ddddddddddddd#",
  "#......P......#",
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
const MONSTER_COLORS = ["#e05a3c", "#3aa0d8", "#d8a13a"];

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
    options: enc.options,
    row: avenueRows[index],
    monsters: [],
    selection: null,
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

function chosenCount() {
  return state.encounters.filter((enc) => enc.selection).length;
}

function monsterAt(c, r) {
  for (const enc of state.encounters) {
    if (enc.selection) continue;
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
  const enc = state.encounters.find((item) => item.row === r && !item.selection);
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
  if (state.encounters.every((item) => item.selection)) {
    state.message = "Every avenue added a filter. Dig up to the tile.";
    startQuery();
  }
}

function startQuery() {
  const token = ++queryToken;
  const choices = {};
  for (const enc of state.encounters) choices[enc.id] = enc.selection;
  state.query = "loading";
  state.queryError = "";
  state.games = null;
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
      state.query = "ready";
      if (state.wantOpen && state.games.length < 3) {
        state.message = "The query returned fewer than three games.";
      }
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
  if (state.encounters.some((enc) => !enc.selection)) {
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

function drawTile(c, r, now) {
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
    ctx.fillRect(x + 18, y + 18, 5, 3);
    ctx.fillRect(x + 12, y + 22, 3, 3);
  } else if (tile === "s") {
    ctx.fillStyle = "#e0c36a";
    ctx.fillRect(x, y, TILE, TILE);
    ctx.fillStyle = "#c4a24e";
    ctx.fillRect(x + 5, y + 7, 3, 3);
    ctx.fillRect(x + 16, y + 14, 3, 3);
    ctx.fillRect(x + 10, y + 22, 3, 3);
  } else if (tile === "X") {
    ctx.fillStyle = "#1f6b4a";
    ctx.fillRect(x, y, TILE, TILE);
    ctx.strokeStyle = "#d7c07a";
    ctx.strokeRect(x + 2, y + 2, TILE - 4, TILE - 4);
  }
}

function drawSlabLabel() {
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
  const x = minC * TILE;
  const y = minR * TILE;
  const w = (maxC - minC + 1) * TILE;
  const h = (maxR - minR + 1) * TILE;
  return { x, y, w, h };
}

function drawDiscover(now) {
  const box = drawSlabLabel();
  if (state.opened && state.games) {
    ctx.fillStyle = "#07140f";
    ctx.fillRect(box.x, box.y, box.w, box.h);
    ctx.strokeStyle = "#e2b657";
    ctx.strokeRect(box.x + 3, box.y + 3, box.w - 6, box.h - 6);
    const slot = (box.h - 16) / Math.max(state.games.length, 1);
    state.games.forEach((game, index) => {
      const gy = box.y + 8 + index * slot;
      ctx.fillStyle = "#143028";
      ctx.fillRect(box.x + 8, gy, box.w - 16, slot - 6);
      ctx.fillStyle = "#f6ead7";
      ctx.font = "700 14px Segoe UI, sans-serif";
      ctx.textAlign = "left";
      ctx.fillText(fitText(`${index + 1}. ${game.title}`, box.w - 32), box.x + 16, gy + 20);
      ctx.fillStyle = "#cbb89a";
      ctx.font = "12px Segoe UI, sans-serif";
      const meta = `${game.review_score} · ${game.released} · ${Number(game.total_reviews).toLocaleString()} reviews`;
      ctx.fillText(fitText(meta, box.w - 32), box.x + 16, gy + 38);
    });
    return;
  }
  ctx.fillStyle = "#f6ead7";
  ctx.font = "700 16px Segoe UI, sans-serif";
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
    ctx.moveTo(box.x + box.w * 0.8, box.y + 16);
    ctx.lineTo(box.x + box.w * 0.5, box.y + box.h * 0.7);
    ctx.stroke();
  }
}

function drawMonster(monster, color, now, asking) {
  const bob = asking ? Math.sin(now / 160) * 2 : 0;
  const x = monster.c * TILE + TILE / 2;
  const y = monster.r * TILE + TILE / 2 + bob;
  if (asking) {
    ctx.strokeStyle = "#e2b657";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(x, y, 14, 0, Math.PI * 2);
    ctx.stroke();
    ctx.lineWidth = 1;
  }
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(x, y, 11, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#1a100b";
  ctx.fillRect(x - 6, y - 3, 3, 4);
  ctx.fillRect(x + 2, y - 3, 3, 4);
  ctx.fillStyle = "#f6ead7";
  ctx.font = "700 11px Segoe UI, sans-serif";
  ctx.textAlign = "center";
  ctx.fillText(String(monster.index + 1), x, y + 18);
  ctx.textAlign = "left";
}

function drawPlayer() {
  const x = state.player.c * TILE + TILE / 2;
  const y = state.player.r * TILE + TILE / 2;
  ctx.fillStyle = "#f4f0e6";
  ctx.beginPath();
  ctx.arc(x, y, 10, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#d64545";
  ctx.fillRect(x - 10, y - 4, 20, 4);
  ctx.fillStyle = "#f4f0e6";
  const nose = {
    up: [x, y - 16, x - 4, y - 6, x + 4, y - 6],
    down: [x, y + 16, x - 4, y + 6, x + 4, y + 6],
    left: [x - 16, y, x - 6, y - 4, x - 6, y + 4],
    right: [x + 16, y, x + 6, y - 4, x + 6, y + 4],
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
    ctx.fillRect(bit.c * TILE + 8, bit.r * TILE + 8 - age * 10, 6, 6);
    ctx.fillRect(bit.c * TILE + 18, bit.r * TILE + 16 - age * 8, 5, 5);
    ctx.globalAlpha = 1;
  }
}

function draw(now) {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  for (let r = 0; r < ROWS; r += 1) {
    for (let c = 0; c < COLS; c += 1) drawTile(c, r, now);
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
  const parts = text.split(/(\d{4}-\d{2}-\d{2})/);
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

function renderPanel() {
  const total = state.encounters.length;
  const done = chosenCount();
  progressEl.textContent = `Avenues ${done}/${total}`;
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
    promptEl.textContent = "Three games from the query.";
    optionsEl.replaceChildren();
  } else if (done === total) {
    promptEl.textContent = "Click the discover tile.";
    optionsEl.replaceChildren();
  } else {
    promptEl.textContent = "Knock the dirt and sand aside.";
    optionsEl.replaceChildren();
  }

  filtersEl.replaceChildren();
  for (const item of state.encounters) {
    if (!item.selection) continue;
    const opt = item.options.find((option) => option.id === item.selection);
    const line = document.createElement("p");
    line.className = "filter-line";
    line.append(`${opt.label}: `);
    appendClause(line, opt.detail);
    filtersEl.append(line);
  }

  foundEl.replaceChildren();
  if (state.opened && state.games) {
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
  sourceEl.textContent = "findGames on games and game_tags. The three games are the first rows of that query, drawn inside the broken tile and listed here.";
}

function signature() {
  return JSON.stringify({
    held: state.held,
    sels: state.encounters.map((enc) => enc.selection),
    message: state.message,
    query: state.query,
    opened: state.opened,
    wantOpen: state.wantOpen,
    games: (state.games || []).map((game) => game.app_id),
  });
}

function frame(now) {
  if (state && keys.size && now - lastMove >= 145) {
    lastMove = now;
    tryMove(keys.values().next().value);
  }
  if (state && state.wantOpen && !state.opened && state.query === "ready" && state.games && state.games.length >= 1) {
    if (now - state.crackStart > 650) {
      state.opened = true;
      state.message = "The tile broke open.";
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
  if (ev.key === "1" || ev.key === "2" || ev.key === "3") {
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
      selections: Object.fromEntries(state.encounters.map((enc) => [enc.id, enc.selection])),
      games: state.games,
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
