const board = document.getElementById("board");
const newXButton = document.getElementById("new-x");
const newOButton = document.getElementById("new-o");
const clearButton = document.getElementById("clear-selection");
const submitButton = document.getElementById("submit-move");
const selectedCellsNode = document.getElementById("selected-cells");
const turnLabel = document.getElementById("turn-label");
const placementsLabel = document.getElementById("placements-label");
const winnerLabel = document.getElementById("winner-label");
const botMoveLabel = document.getElementById("bot-move-label");

const VIEWBOX = { width: 1000, height: 760 };
const HEX_RADIUS = 28;
const HEX_SPACING = 34;
const GRID_RADIUS = 14;

let sessionId = null;
let payload = null;
let selectedCells = [];
let camera = { x: 0, y: 0 };
let pointerState = null;

newXButton.addEventListener("click", () => newGame("x"));
newOButton.addEventListener("click", () => newGame("o"));
clearButton.addEventListener("click", clearSelection);
submitButton.addEventListener("click", submitMove);

board.addEventListener("pointerdown", startPan);
board.addEventListener("pointermove", continuePan);
board.addEventListener("pointerup", endPan);
board.addEventListener("pointerleave", endPan);
board.addEventListener("pointercancel", endPan);

async function newGame(human) {
  const response = await fetch("/api/new-game", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ human }),
  });
  payload = await response.json();
  sessionId = payload.session_id;
  selectedCells = [];
  camera = { x: 0, y: 0 };
  render();
}

async function submitMove() {
  if (!sessionId || !payload) {
    return;
  }

  const expected = payload.state.placements_remaining;
  if (selectedCells.length !== expected) {
    alert(`Expected ${expected} placement(s).`);
    return;
  }

  const response = await fetch(`/api/play/${sessionId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cells: selectedCells }),
  });
  const nextPayload = await response.json();
  if (!response.ok) {
    alert(nextPayload.message || nextPayload.error || "Move rejected.");
    return;
  }

  payload = nextPayload;
  selectedCells = [];
  render();
}

function clearSelection() {
  selectedCells = [];
  renderSelection();
  renderBoard();
}

function startPan(event) {
  const svgPoint = clientToSvgPoint(event.clientX, event.clientY);
  pointerState = {
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    lastX: event.clientX,
    lastY: event.clientY,
    startSvgX: svgPoint.x,
    startSvgY: svgPoint.y,
    moved: false,
  };
  board.setPointerCapture(event.pointerId);
}

function continuePan(event) {
  if (!pointerState || pointerState.pointerId !== event.pointerId) {
    return;
  }

  const dx = event.clientX - pointerState.lastX;
  const dy = event.clientY - pointerState.lastY;
  pointerState.lastX = event.clientX;
  pointerState.lastY = event.clientY;
  const rect = board.getBoundingClientRect();
  const scaleX = VIEWBOX.width / rect.width;
  const scaleY = VIEWBOX.height / rect.height;

  if (!pointerState.moved) {
    const totalDx = event.clientX - pointerState.startX;
    const totalDy = event.clientY - pointerState.startY;
    pointerState.moved = Math.hypot(totalDx, totalDy) > 6;
  }

  if (pointerState.moved) {
    camera.x += dx * scaleX;
    camera.y += dy * scaleY;
    renderBoard();
  }
}

function endPan(event) {
  if (!pointerState || pointerState.pointerId !== event.pointerId) {
    return;
  }
  board.releasePointerCapture(event.pointerId);
  const moved = pointerState.moved;
  pointerState = null;
  if (!moved && event.type === "pointerup") {
    handleBoardTap(event);
  }
}

function toggleCell(cell) {
  if (!payload || payload.state.winner) {
    return;
  }

  const key = cellKey(cell);
  const occupied = new Set(payload.state.stones.map((stone) => cellKey(stone)));
  if (occupied.has(key)) {
    return;
  }

  const existingIndex = selectedCells.findIndex((item) => cellKey(item) === key);
  if (existingIndex >= 0) {
    selectedCells.splice(existingIndex, 1);
    renderSelection();
    renderBoard();
    return;
  }

  if (selectedCells.length >= payload.state.placements_remaining) {
    return;
  }

  selectedCells.push({ q: cell.q, r: cell.r });
  renderSelection();
  renderBoard();
}

function handleBoardTap(event) {
  if (!payload) {
    return;
  }
  const point = clientToSvgPoint(event.clientX, event.clientY);
  const axial = pixelToAxial(
    point.x - VIEWBOX.width / 2 - camera.x,
    point.y - VIEWBOX.height / 2 - camera.y,
  );
  const rounded = axialRound(axial.q, axial.r);
  toggleCell(rounded);
}

function render() {
  renderStatus();
  renderSelection();
  renderBoard();
}

function renderStatus() {
  if (!payload) {
    turnLabel.textContent = "Not started";
    placementsLabel.textContent = "0";
    winnerLabel.textContent = "None";
    botMoveLabel.textContent = "None";
    submitButton.disabled = true;
    clearButton.disabled = true;
    return;
  }

  turnLabel.textContent = payload.state.to_play.toUpperCase();
  placementsLabel.textContent = String(payload.state.placements_remaining);
  winnerLabel.textContent = payload.state.winner ? payload.state.winner.toUpperCase() : "None";
  botMoveLabel.textContent = payload.last_bot_turn.length
    ? `${payload.last_bot_turn.length} stone${payload.last_bot_turn.length > 1 ? "s" : ""}`
    : "None";
  submitButton.disabled = payload.state.winner !== null;
  clearButton.disabled = selectedCells.length === 0;
}

function renderSelection() {
  selectedCellsNode.innerHTML = "";
  if (!selectedCells.length) {
    const pill = document.createElement("div");
    pill.className = "pill subtle";
    pill.textContent = "No cells selected";
    selectedCellsNode.appendChild(pill);
    return;
  }

  selectedCells.forEach((cell, index) => {
    const pill = document.createElement("div");
    pill.className = "pill";
    const label = document.createElement("span");
    label.textContent = `Stone ${index + 1}`;
    const remove = document.createElement("button");
    remove.textContent = "x";
    remove.addEventListener("click", () => {
      selectedCells = selectedCells.filter((item) => item !== cell);
      renderSelection();
      renderBoard();
    });
    pill.appendChild(label);
    pill.appendChild(remove);
    selectedCellsNode.appendChild(pill);
  });
}

function renderBoard() {
  board.innerHTML = "";
  if (!payload) {
    return;
  }

  const occupied = new Map(payload.state.stones.map((stone) => [cellKey(stone), stone.player]));
  const winning = new Set((payload.state.winning_line || []).map((cell) => cellKey(cell)));
  const selected = new Set(selectedCells.map((cell) => cellKey(cell)));
  const recent = new Set(payload.last_bot_turn.map((cell) => cellKey(cell)));
  const cells = visibleCells();

  cells.forEach((cell) => {
    const point = axialToPixel(cell.q, cell.r);
    const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
    const key = cellKey(cell);
    const occupant = occupied.get(key);
    const classes = ["hex", occupant || "empty"];
    if (selected.has(key)) {
      classes.push("selected");
    }
    if (winning.has(key)) {
      classes.push("winning");
    } else if (recent.has(key)) {
      classes.push("recent");
    }
    group.setAttribute("class", classes.join(" "));
    group.setAttribute("transform", `translate(${point.x}, ${point.y})`);

    const polygon = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
    polygon.setAttribute("points", hexPoints(HEX_RADIUS));
    group.appendChild(polygon);

    if (occupant === "x") {
      group.appendChild(xStroke(-12, -14, 12, 14));
      group.appendChild(xStroke(-12, 14, 12, -14));
    } else if (occupant === "o") {
      const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.setAttribute("r", "15");
      circle.setAttribute("class", "token-o");
      group.appendChild(circle);
    }

    board.appendChild(group);
  });
}

function visibleCells() {
  const centerApprox = pixelToAxial(-camera.x, -camera.y);
  const center = axialRound(centerApprox.q, centerApprox.r);
  const cells = [];

  for (let dq = -GRID_RADIUS; dq <= GRID_RADIUS; dq += 1) {
    const drMin = Math.max(-GRID_RADIUS, -dq - GRID_RADIUS);
    const drMax = Math.min(GRID_RADIUS, -dq + GRID_RADIUS);
    for (let dr = drMin; dr <= drMax; dr += 1) {
      const cell = { q: center.q + dq, r: center.r + dr };
      const point = axialToPixel(cell.q, cell.r);
      if (
        point.x >= -80 &&
        point.x <= VIEWBOX.width + 80 &&
        point.y >= -80 &&
        point.y <= VIEWBOX.height + 80
      ) {
        cells.push(cell);
      }
    }
  }

  return cells;
}

function axialToPixel(q, r) {
  const x =
    VIEWBOX.width / 2 +
    camera.x +
    HEX_SPACING * Math.sqrt(3) * (q + r / 2);
  const y = VIEWBOX.height / 2 + camera.y + HEX_SPACING * 1.5 * r;
  return { x, y };
}

function pixelToAxial(x, y) {
  const q = (Math.sqrt(3) / 3 * x - 1 / 3 * y) / HEX_SPACING;
  const r = (2 / 3 * y) / HEX_SPACING;
  return { q, r };
}

function clientToSvgPoint(clientX, clientY) {
  const rect = board.getBoundingClientRect();
  return {
    x: ((clientX - rect.left) / rect.width) * VIEWBOX.width,
    y: ((clientY - rect.top) / rect.height) * VIEWBOX.height,
  };
}

function axialRound(q, r) {
  let x = q;
  let z = r;
  let y = -x - z;

  let rx = Math.round(x);
  let ry = Math.round(y);
  let rz = Math.round(z);

  const xDiff = Math.abs(rx - x);
  const yDiff = Math.abs(ry - y);
  const zDiff = Math.abs(rz - z);

  if (xDiff > yDiff && xDiff > zDiff) {
    rx = -ry - rz;
  } else if (yDiff > zDiff) {
    ry = -rx - rz;
  } else {
    rz = -rx - ry;
  }

  return { q: rx, r: rz };
}

function hexPoints(radius) {
  const points = [];
  for (let index = 0; index < 6; index += 1) {
    const angle = (Math.PI / 180) * (60 * index - 30);
    points.push(`${Math.cos(angle) * radius},${Math.sin(angle) * radius}`);
  }
  return points.join(" ");
}

function xStroke(x1, y1, x2, y2) {
  const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
  line.setAttribute("x1", String(x1));
  line.setAttribute("y1", String(y1));
  line.setAttribute("x2", String(x2));
  line.setAttribute("y2", String(y2));
  line.setAttribute("class", "token-x");
  return line;
}

function cellKey(cell) {
  return `${cell.q},${cell.r}`;
}
