const TILE = 40;
const MAP = [
  "###############",
  "#R#R#R#########",
  "###############",
  "#A.A.A........#",
  "###############",
  "#R#R#R#########",
  "###############",
  "#B.B.B........#",
  "#R#R#R#########",
  "###############",
  "#C.C.C........#",
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
const LETTERS = ["A", "B", "C"];

const canvas = document.getElementById("field");
const ctx = canvas.getContext("2d");
canvas.width = COLS * TILE;
canvas.height = ROWS * TILE;

const scoreEl = document.getElementById("score");
const livesEl = document.getElementById("lives");
const leftEl = document.getElementById("left");
const messageEl = document.getElementById("message");
const promptEl = document.getElementById("prompt");
const optionsEl = document.getElementById("options");
const meterEl = document.getElementById("meter");
const foundEl = document.getElementById("found");
const sourceEl = document.getElementById("source");

const keys = new Set();
let blueprint = null;
let state = null;
let panelSig = "";
let lastMove = 0;
let lastPump = 0;
let lastPatrol = 0;
let loopId = 0;

function fail(text) {
  promptEl.textContent = text;
  optionsEl.textContent = "";
}

function cloneEncounters(data) {
  return data.encounters.map((enc) => ({
    id: enc.id,
    dimension: enc.dimension,
    prompt: enc.prompt,
    options: enc.options,
    monsters: [],
    row: 0,
    resolved: false,
    selection: null,
    inflate: 0,
    deflateAt: 0,
    via: null,
  }));
}

function buildWorld() {
  for (const row of MAP) {
    if (row.length !== COLS) throw new Error("map row length mismatch");
  }
  const tiles = [];
  const rocks = [];
  const spawns = { A: [], B: [], C: [] };
  let start = { c: 1, r: 1 };
  for (let r = 0; r < ROWS; r += 1) {
    tiles[r] = [];
    for (let c = 0; c < COLS; c += 1) {
      const ch = MAP[r][c];
      const border = r === 0 || c === 0 || r === ROWS - 1 || c === COLS - 1;
      if (ch === "R" && !border) {
        tiles[r][c] = "dirt";
        rocks.push({ c, r, state: "idle", timer: 0, fell: false });
        continue;
      }
      if ((ch === "A" || ch === "B" || ch === "C") && !border) {
        tiles[r][c] = "tunnel";
        spawns[ch].push({ c, r });
        continue;
      }
      if (ch === "." || ch === "P") {
        tiles[r][c] = border ? "wall" : "tunnel";
        if (ch === "P") start = { c, r };
        continue;
      }
      tiles[r][c] = border ? "wall" : "dirt";
    }
  }
  const encounters = cloneEncounters(blueprint);
  encounters.forEach((enc, index) => {
    const slots = spawns[LETTERS[index]] || [];
    if (slots.length < enc.options.length) {
      throw new Error(`not enough tunnels for ${enc.dimension}`);
    }
    enc.row = slots[0].r;
    enc.monsters = enc.options.map((option, optionIndex) => ({
      c: slots[optionIndex].c,
      r: slots[optionIndex].r,
      home: slots[optionIndex].c,
      dir: optionIndex % 2 === 0 ? 1 : -1,
      alive: true,
      optionIndex,
    }));
  });
  for (const rock of rocks) {
    const below = tiles[rock.r + 1] && tiles[rock.r + 1][rock.c];
    const supported = below === "dirt" || below === "wall" || rocks.some((other) => other !== rock && other.c === rock.c && other.r === rock.r + 1);
    if (!supported) throw new Error(`rock at ${rock.c},${rock.r} starts in the air`);
  }
  return {
    tiles,
    rocks,
    encounters,
    player: { c: start.c, r: start.r, dir: "up", invulnUntil: 0 },
    score: 0,
    lives: 3,
    status: "play",
    message: "",
    messageUntil: 0,
    log: [],
    particles: [],
    floats: [],
    shake: 0,
  };
}

function say(text, now) {
  state.message = text;
  state.messageUntil = now + 2200;
}

function tileAt(c, r) {
  if (r < 0 || c < 0 || r >= ROWS || c >= COLS) return "wall";
  return state.tiles[r][c];
}

function rockAt(c, r) {
  return state.rocks.find((rock) => rock.c === c && rock.r === r) || null;
}

function monsterAt(c, r) {
  for (const enc of state.encounters) {
    for (const monster of enc.monsters) {
      if (monster.alive && monster.c === c && monster.r === r) return { enc, monster };
    }
  }
  return null;
}

function encounterOnRow(r) {
  return state.encounters.find((enc) => !enc.resolved && enc.row === r) || null;
}

function hurt(now, reason, respawn) {
  if (now < state.player.invulnUntil || state.status !== "play") return;
  state.lives -= 1;
  state.shake = 10;
  say(reason, now);
  if (state.lives <= 0) {
    state.status = "dead";
    return;
  }
  state.player.invulnUntil = now + 1500;
  if (respawn) {
    const home = spawnCell();
    state.player.c = home.c;
    state.player.r = home.r;
  }
}

function spawnCell() {
  const row = MAP.findIndex((line) => line.includes("P"));
  const preferred = Math.max(MAP[row].indexOf("P"), 1);
  const order = [preferred, ...Array.from({ length: COLS }, (_, index) => index)];
  for (const c of order) {
    if (tileAt(c, row) === "tunnel" && !rockAt(c, row)) return { c, r: row };
  }
  return { c: preferred, r: row };
}

function tryMove(dirName, now) {
  if (state.status !== "play") return;
  const dir = DIRS[dirName];
  state.player.dir = dirName;
  const c = state.player.c + dir.c;
  const r = state.player.r + dir.r;
  if (rockAt(c, r)) return;
  const asking = encounterOnRow(state.player.r);
  if (monsterAt(c, r)) {
    if (!asking) hurt(now, "The monsters got you.", false);
    return;
  }
  const tile = tileAt(c, r);
  if (tile === "wall") return;
  if (tile === "dirt") {
    state.tiles[r][c] = "tunnel";
    state.score += 10;
    state.floats.push({ text: "+10", c, r, life: 1 });
  }
  if (tileAt(c, r) !== "tunnel") return;
  state.player.c = c;
  state.player.r = r;
}

function dirFromKeys() {
  if (keys.has("arrowup") || keys.has("w")) return "up";
  if (keys.has("arrowdown") || keys.has("s")) return "down";
  if (keys.has("arrowleft") || keys.has("a")) return "left";
  if (keys.has("arrowright") || keys.has("d")) return "right";
  return null;
}

function choose(index) {
  if (!state || state.status !== "play") return;
  const enc = encounterOnRow(state.player.r);
  if (!enc || index < 1 || index > enc.options.length) return;
  enc.selection = index - 1;
  enc.deflateAt = performance.now() + 900;
  renderPanel(true);
}

function pump(now) {
  const enc = encounterOnRow(state.player.r);
  if (!enc) return;
  if (enc.selection === null) {
    say("Press a number to choose, then pump.", now);
    return;
  }
  const chosen = enc.monsters.find((monster) => monster.alive && monster.optionIndex === enc.selection);
  if (!chosen) {
    say("That one is already buried. Pick another.", now);
    return;
  }
  enc.inflate = Math.min(3, enc.inflate + 1);
  enc.deflateAt = now + 900;
  if (enc.inflate >= 3) resolveEncounter(enc, enc.selection, "pump", now);
}

function resolveEncounter(enc, optionIndex, via, now) {
  if (enc.resolved || state.status !== "play") return;
  const option = enc.options[optionIndex];
  if (!option) return;
  enc.resolved = true;
  enc.via = via;
  enc.inflate = 0;
  const points = via === "crush" ? 1000 : 500;
  state.score += points;
  for (const monster of enc.monsters) {
    if (monster.alive) burst(monster.c, monster.r, via === "crush" ? "#d0d4da" : "#e07a3d");
    monster.alive = false;
  }
  state.floats.push({ text: `+${points}`, c: state.player.c, r: state.player.r, life: 1 });
  state.log.push({
    dimension: enc.dimension,
    prompt: enc.prompt,
    label: option.label,
    games: option.games,
    via,
  });
  say(via === "crush" ? `The rock chose ${option.label}.` : `Pumped: ${option.label}.`, now);
  if (state.encounters.every((item) => item.resolved)) {
    state.score += 2000;
    state.status = "win";
    state.floats.push({ text: "+2000", c: state.player.c, r: state.player.r, life: 1.4 });
  }
  renderPanel(true);
}

function burst(c, r, color) {
  for (let i = 0; i < 8; i += 1) {
    state.particles.push({
      x: c * TILE + TILE / 2,
      y: r * TILE + TILE / 2,
      vx: (Math.random() - 0.5) * 80,
      vy: (Math.random() - 0.5) * 80,
      life: 0.6,
      color,
    });
  }
}

function rockComingDown(monster) {
  return state.rocks.some((rock) => rock.c === monster.home && rock.r < monster.r && rock.state !== "idle");
}

function patrol(now) {
  if (now - lastPatrol < 650) return;
  lastPatrol = now;
  for (const enc of state.encounters) {
    if (enc.resolved || state.player.r === enc.row) continue;
    for (const monster of enc.monsters) {
      if (!monster.alive || rockComingDown(monster)) continue;
      const next = monster.c + monster.dir;
      const blocked = next < monster.home - 1
        || next > monster.home + 1
        || tileAt(next, monster.r) !== "tunnel"
        || rockAt(next, monster.r)
        || monsterAt(next, monster.r);
      if (blocked) monster.dir *= -1;
      else monster.c = next;
    }
  }
}

function updateRocks(now) {
  const ordered = state.rocks.slice().sort((a, b) => b.r - a.r);
  for (const rock of ordered) {
    const supported = supportUnder(rock);
    if (rock.state === "idle") {
      if (!supported) {
        rock.state = "wobble";
        rock.timer = now + 480;
      }
      continue;
    }
    if (rock.state === "wobble") {
      if (supported) rock.state = "idle";
      else if (now >= rock.timer) rock.state = "fall";
      continue;
    }
    if (now < rock.timer) continue;
    rock.timer = now + 110;
    if (supported) {
      rock.state = "idle";
      continue;
    }
    const destR = rock.r + 1;
    const playerThere = state.player.c === rock.c && state.player.r === destR;
    const hit = monsterAt(rock.c, destR);
    state.tiles[rock.r][rock.c] = "tunnel";
    rock.r = destR;
    rock.fell = true;
    state.shake = 6;
    if (playerThere) hurt(now, "A rock flattened you.", true);
    if (hit && hit.monster.alive && !hit.enc.resolved) {
      burst(rock.c, rock.r, "#d0d4da");
      resolveEncounter(hit.enc, hit.monster.optionIndex, "crush", now);
    }
  }
}

function supportUnder(rock) {
  const below = tileAt(rock.c, rock.r + 1);
  if (below === "dirt" || below === "wall") return true;
  return state.rocks.some((other) => other !== rock && other.c === rock.c && other.r === rock.r + 1);
}

function deflate(now) {
  for (const enc of state.encounters) {
    if (enc.resolved || enc.inflate <= 0 || now < enc.deflateAt) continue;
    enc.inflate -= 1;
    enc.deflateAt = now + 380;
  }
}

function tick(now) {
  if (state.status === "play") {
    if (now - lastMove >= 145) {
      const dir = dirFromKeys();
      if (dir) {
        tryMove(dir, now);
        lastMove = now;
      }
    }
    if (keys.has(" ") && now - lastPump >= 240) {
      pump(now);
      lastPump = now;
    }
    updateRocks(now);
    patrol(now);
    deflate(now);
  }
  for (const particle of state.particles) {
    particle.life -= 0.016;
    particle.x += particle.vx * 0.016;
    particle.y += particle.vy * 0.016;
  }
  state.particles = state.particles.filter((particle) => particle.life > 0);
  for (const item of state.floats) item.life -= 0.016;
  state.floats = state.floats.filter((item) => item.life > 0);
  if (state.shake > 0) state.shake -= 1;
  if (state.message && now > state.messageUntil) state.message = "";
  draw(now);
  renderPanel(false);
  loopId = requestAnimationFrame(tick);
}

function draw(now) {
  const shakeX = state.shake ? (Math.random() - 0.5) * state.shake : 0;
  const shakeY = state.shake ? (Math.random() - 0.5) * state.shake : 0;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.save();
  ctx.translate(shakeX, shakeY);
  for (let r = 0; r < ROWS; r += 1) {
    for (let c = 0; c < COLS; c += 1) drawTile(c, r);
  }
  for (const rock of state.rocks) drawRock(rock, now);
  for (const enc of state.encounters) {
    const asking = !enc.resolved && state.player.r === enc.row;
    for (const monster of enc.monsters) {
      if (!monster.alive) continue;
      drawMonster(monster, enc, asking, now);
    }
  }
  drawPlayer(now);
  for (const particle of state.particles) {
    ctx.globalAlpha = Math.max(particle.life, 0);
    ctx.fillStyle = particle.color;
    ctx.fillRect(particle.x, particle.y, 4, 4);
    ctx.globalAlpha = 1;
  }
  ctx.fillStyle = "#f2d48a";
  ctx.font = "bold 14px sans-serif";
  for (const item of state.floats) {
    ctx.globalAlpha = Math.max(item.life, 0);
    ctx.fillText(item.text, item.c * TILE + 8, item.r * TILE + 16 - (1 - item.life) * 16);
  }
  ctx.globalAlpha = 1;
  if (state.status !== "play") {
    ctx.fillStyle = "rgba(8, 5, 3, 0.72)";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#f6ead7";
    ctx.font = "bold 28px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(state.status === "win" ? "Level clear" : "Game over", canvas.width / 2, canvas.height / 2 - 8);
    ctx.font = "16px sans-serif";
    ctx.fillText("Press R to dig again", canvas.width / 2, canvas.height / 2 + 22);
    ctx.textAlign = "left";
  }
  ctx.restore();
}

function drawTile(c, r) {
  const tile = state.tiles[r][c];
  const x = c * TILE;
  const y = r * TILE;
  if (tile === "tunnel") {
    ctx.fillStyle = "#1a120c";
    ctx.fillRect(x, y, TILE, TILE);
    return;
  }
  if (tile === "wall") {
    ctx.fillStyle = "#2c241c";
    ctx.fillRect(x, y, TILE, TILE);
    ctx.strokeStyle = "#3d342a";
    ctx.strokeRect(x + 0.5, y + 0.5, TILE - 1, TILE - 1);
    return;
  }
  const shades = ["#6e4124", "#7d4c2b", "#8b5733", "#734626"];
  ctx.fillStyle = shades[(c * 5 + r * 3) % shades.length];
  ctx.fillRect(x, y, TILE, TILE);
  ctx.fillStyle = "rgba(0,0,0,0.18)";
  ctx.fillRect(x + ((c * 13 + r) % 18), y + ((r * 11 + c) % 20), 3, 2);
}

function drawRock(rock, now) {
  const wobble = rock.state === "wobble" ? Math.sin(now / 40) * 3 : 0;
  const x = rock.c * TILE + TILE / 2 + wobble;
  const y = rock.r * TILE + TILE / 2;
  ctx.fillStyle = "#b7bdc4";
  ctx.beginPath();
  ctx.arc(x, y, 14, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#eceff3";
  ctx.beginPath();
  ctx.arc(x - 4, y - 4, 4, 0, Math.PI * 2);
  ctx.fill();
}

function drawMonster(monster, enc, asking, now) {
  const selected = enc.selection === monster.optionIndex;
  const scale = selected ? 1 + enc.inflate * 0.22 : 1;
  const bob = asking ? Math.sin(now / 180 + monster.optionIndex) * 2 : 0;
  const x = monster.c * TILE + TILE / 2;
  const y = monster.r * TILE + TILE / 2 + bob;
  const colors = ["#e07a3d", "#d24b4b", "#7e9b4a"];
  ctx.fillStyle = colors[monster.optionIndex % colors.length];
  ctx.beginPath();
  ctx.arc(x, y, 12 * scale, 0, Math.PI * 2);
  ctx.fill();
  if (selected) {
    ctx.strokeStyle = "#f2d48a";
    ctx.lineWidth = 2;
    ctx.stroke();
  }
  ctx.fillStyle = "#1a120c";
  ctx.font = "bold 14px sans-serif";
  ctx.textAlign = "center";
  ctx.fillText(String(monster.optionIndex + 1), x, y + 5);
  ctx.textAlign = "left";
}

function drawPlayer(now) {
  const blink = now < state.player.invulnUntil && Math.floor(now / 120) % 2 === 0;
  if (blink) return;
  const x = state.player.c * TILE + TILE / 2;
  const y = state.player.r * TILE + TILE / 2;
  ctx.fillStyle = "#f2c14e";
  ctx.beginPath();
  ctx.arc(x, y, 11, 0, Math.PI * 2);
  ctx.fill();
  const dir = DIRS[state.player.dir];
  ctx.strokeStyle = "#f6ead7";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(x, y);
  ctx.lineTo(x + dir.c * 16, y + dir.r * 16);
  ctx.stroke();
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function renderPanel(force) {
  const asking = state.status === "play" ? encounterOnRow(state.player.r) : null;
  const sig = JSON.stringify({
    score: state.score,
    lives: state.lives,
    status: state.status,
    message: state.message,
    ask: asking ? asking.id : null,
    selection: asking ? asking.selection : null,
    inflate: asking ? asking.inflate : 0,
    log: state.log.map((entry) => entry.label),
    left: state.encounters.filter((enc) => !enc.resolved).length,
  });
  if (!force && sig === panelSig) return;
  panelSig = sig;
  scoreEl.textContent = `Score ${state.score}`;
  livesEl.textContent = `Lives ${state.lives}`;
  leftEl.textContent = `Packs left ${state.encounters.filter((enc) => !enc.resolved).length}`;
  messageEl.textContent = state.message || "";
  optionsEl.textContent = "";
  meterEl.textContent = "";
  if (state.status === "win") {
    promptEl.textContent = "Level clear. Every pack got an answer.";
  } else if (state.status === "dead") {
    promptEl.textContent = "Out of lives.";
  } else if (asking) {
    promptEl.textContent = asking.prompt;
    asking.options.forEach((option, index) => {
      const button = el("button", asking.selection === index ? "opt selected" : "opt");
      button.type = "button";
      button.append(el("strong", null, `${index + 1}. ${option.label}`));
      button.append(el("span", null, option.detail));
      button.addEventListener("click", () => choose(index + 1));
      optionsEl.append(button);
    });
    if (asking.selection !== null) {
      meterEl.textContent = `Pump ${asking.inflate}/3`;
    }
  } else {
    promptEl.textContent = "Dig up into a tunnel. The monsters will make you choose.";
  }
  foundEl.textContent = "";
  if (state.log.length) {
    foundEl.append(el("h2", null, "From the Find a Game list"));
    for (const entry of state.log) {
      const wrap = el("div", "card");
      wrap.append(el("h3", null, entry.label));
      const how = entry.via === "crush" ? "A rock settled it." : "You pumped them.";
      wrap.append(el("p", null, how));
      for (const game of entry.games) {
        const card = el("div", "card");
        card.append(el("h3", null, game.title));
        for (const field of game.fields) {
          card.append(el("p", null, `${field.label}: ${field.value}`));
        }
        card.append(el("p", null, `App ${game.app_id}`));
        wrap.append(card);
      }
      foundEl.append(wrap);
    }
  }
}

function reset() {
  state = buildWorld();
  panelSig = "";
  lastMove = 0;
  lastPump = 0;
  lastPatrol = 0;
  renderPanel(true);
  canvas.focus();
}

const MOVE_KEYS = {
  arrowup: "up",
  w: "up",
  arrowdown: "down",
  s: "down",
  arrowleft: "left",
  a: "left",
  arrowright: "right",
  d: "right",
};

function onKeyDown(event) {
  if (!state) return;
  const key = event.key.toLowerCase();
  if (MOVE_KEYS[key] || key === " ") event.preventDefault();
  if (key === "r" && !event.ctrlKey && !event.metaKey && state.status !== "play") {
    event.preventDefault();
    reset();
    return;
  }
  if (state.status !== "play") return;
  const now = performance.now();
  if (MOVE_KEYS[key] && now - lastMove >= 145) {
    tryMove(MOVE_KEYS[key], now);
    lastMove = now;
  }
  if (key >= "1" && key <= "9" && !event.repeat) choose(Number(key));
  if (key === " " && !event.repeat) {
    pump(now);
    lastPump = now;
  }
  keys.add(key);
}

function onKeyUp(event) {
  keys.delete(event.key.toLowerCase());
}

window.addEventListener("keydown", onKeyDown);
window.addEventListener("keyup", onKeyUp);
canvas.addEventListener("pointerdown", () => canvas.focus());

async function boot() {
  try {
    const response = await fetch("/api/level");
    if (!response.ok) throw new Error(`game list request failed (${response.status})`);
    blueprint = await response.json();
    if (!blueprint.encounters || blueprint.encounters.length < 1) {
      throw new Error("the game list did not include any choices");
    }
    sourceEl.textContent = `${blueprint.row_count} games from the Find a Game for Me list (recent_top_games).`;
    reset();
    cancelAnimationFrame(loopId);
    loopId = requestAnimationFrame(tick);
    window.__digdug = {
      get state() { return state; },
      choose,
      reset,
    };
  } catch (error) {
    fail(error.message || "Could not load games.");
  }
}

boot();
