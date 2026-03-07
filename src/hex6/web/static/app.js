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
const manualQ = document.getElementById("manual-q");
const manualR = document.getElementById("manual-r");
const addManualButton = document.getElementById("add-manual");

let sessionId = null;
let payload = null;
let selectedCells = [];

newXButton.addEventListener("click", () => newGame("x"));
newOButton.addEventListener("click", () => newGame("o"));
clearButton.addEventListener("click", clearSelection);
submitButton.addEventListener("click", submitMove);
addManualButton.addEventListener("click", addManualCell);

async function newGame(human) {
  const response = await fetch("/api/new-game", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ human }),
  });
  payload = await response.json();
  sessionId = payload.session_id;
  selectedCells = [];
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

function toggleCell(cell) {
  if (!payload || payload.state.winner) {
    return;
  }

  const key = `${cell.q},${cell.r}`;
  const existingIndex = selectedCells.findIndex((item) => `${item.q},${item.r}` === key);
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

function addManualCell() {
  const q = Number.parseInt(manualQ.value, 10);
  const r = Number.parseInt(manualR.value, 10);
  if (Number.isNaN(q) || Number.isNaN(r)) {
    return;
  }
  toggleCell({ q, r });
  manualQ.value = "";
  manualR.value = "";
}

function clearSelection() {
  selectedCells = [];
  renderSelection();
  renderBoard();
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
    ? payload.last_bot_turn.map((cell) => `(${cell.q}, ${cell.r})`).join(" ")
    : "None";
  submitButton.disabled = payload.state.winner !== null;
  clearButton.disabled = selectedCells.length === 0;
}

function renderSelection() {
  selectedCellsNode.innerHTML = "";
  selectedCells.forEach((cell, index) => {
    const pill = document.createElement("div");
    pill.className = "pill";
    pill.innerHTML = `<span>${index + 1}. (${cell.q}, ${cell.r})</span>`;
    const remove = document.createElement("button");
    remove.textContent = "×";
    remove.addEventListener("click", () => {
      selectedCells = selectedCells.filter((item) => item !== cell);
      renderSelection();
      renderBoard();
    });
    pill.appendChild(remove);
    selectedCellsNode.appendChild(pill);
  });
}

function renderBoard() {
  board.innerHTML = "";
  if (!payload) {
    return;
  }

  const stones = new Map(payload.state.stones.map((stone) => [`${stone.q},${stone.r}`, stone.player]));
  const winning = new Set((payload.state.winning_line || []).map((cell) => `${cell.q},${cell.r}`));
  const selected = new Set(selectedCells.map((cell) => `${cell.q},${cell.r}`));

  payload.view.cells.forEach((cell) => {
    const point = axialToPixel(cell.q, cell.r, payload.view.center.q, payload.view.center.r);
    const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
    const classes = ["hex"];
    const key = `${cell.q},${cell.r}`;
    const occupant = stones.get(key);
    classes.push(occupant || "empty");
    if (selected.has(key)) {
      classes.push("selected");
    }
    if (winning.has(key)) {
      classes.push("winning");
    }
    group.setAttribute("class", classes.join(" "));
    group.setAttribute("transform", `translate(${point.x}, ${point.y})`);
    if (!occupant) {
      group.addEventListener("click", () => toggleCell(cell));
    }

    const polygon = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
    polygon.setAttribute("points", hexPoints(28));
    group.appendChild(polygon);

    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("text-anchor", "middle");
    label.setAttribute("dominant-baseline", "middle");
    label.setAttribute("y", "2");
    label.textContent = occupant ? occupant.toUpperCase() : `${cell.q},${cell.r}`;
    group.appendChild(label);

    board.appendChild(group);
  });
}

function axialToPixel(q, r, centerQ, centerR) {
  const size = 34;
  const x = 500 + size * Math.sqrt(3) * (q - centerQ + (r - centerR) / 2);
  const y = 380 + size * 1.5 * (r - centerR);
  return { x, y };
}

function hexPoints(radius) {
  const points = [];
  for (let i = 0; i < 6; i += 1) {
    const angle = (Math.PI / 180) * (60 * i - 30);
    points.push(`${Math.cos(angle) * radius},${Math.sin(angle) * radius}`);
  }
  return points.join(" ");
}
