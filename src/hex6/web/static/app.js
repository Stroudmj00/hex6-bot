const localGame = window.Hex6LocalGame.createHelpers(window.HEX6_BOOTSTRAP || {});
const GAME = localGame.game;

const board = document.getElementById("board");
const startLocalAiXButton = document.getElementById("start-local-ai-x");
const startLocalAiOButton = document.getElementById("start-local-ai-o");
const startFriendButton = document.getElementById("start-friend");
const startSpectatorButton = document.getElementById("start-spectator");
const autoplayButton = document.getElementById("toggle-autoplay");
const clearButton = document.getElementById("clear-selection");
const submitButton = document.getElementById("submit-move");
const stepBotButton = document.getElementById("step-bot");
const zoomOutButton = document.getElementById("zoom-out");
const zoomInButton = document.getElementById("zoom-in");
const resetViewButton = document.getElementById("reset-view");
const zoomLabel = document.getElementById("zoom-label");
const selectedCellsNode = document.getElementById("selected-cells");
const turnLabel = document.getElementById("turn-label");
const placementsLabel = document.getElementById("placements-label");
const pliesLabel = document.getElementById("plies-label");
const winnerLabel = document.getElementById("winner-label");
const responseLabel = document.getElementById("response-label");
const modeLabel = document.getElementById("mode-label");
const matchupLabel = document.getElementById("matchup-label");
const boardTitleNode = document.getElementById("board-title");
const boardSubtitleNode = document.getElementById("board-subtitle");
const boardHelperNode = document.getElementById("board-helper");
const turnHelperNode = document.getElementById("turn-helper");
const flashMessageNode = document.getElementById("flash-message");
const modeCards = document.querySelectorAll("[data-mode-card]");

const VIEWBOX = { width: 1000, height: 760 };
const HEX_RADIUS = 28;
const HEX_SPACING = 34;
const ZOOM_MIN = 0.35;
const ZOOM_MAX = 1.9;
const ZOOM_STEP = 1.14;
const LOCAL_AI_NAME = "Browser AI";

const appState = {
  currentMode: "idle",
  payload: null,
  sessionId: null,
  localState: null,
  localContext: null,
  selectedCells: [],
  camera: { x: 0, y: 0 },
  zoom: 1,
  pointerState: null,
  autoplayTimer: null,
  localAiTimer: null,
  stepInFlight: false,
  flashTimer: null,
};

startLocalAiXButton?.addEventListener("click", () => startLocalAiGame("x"));
startLocalAiOButton?.addEventListener("click", () => startLocalAiGame("o"));
startFriendButton?.addEventListener("click", startFriendGame);
startSpectatorButton?.addEventListener("click", startSpectatorGame);
autoplayButton?.addEventListener("click", toggleAutoplay);
clearButton?.addEventListener("click", clearSelection);
submitButton?.addEventListener("click", submitMove);
stepBotButton?.addEventListener("click", stepBots);
zoomOutButton?.addEventListener("click", () => zoomAt(1 / ZOOM_STEP));
zoomInButton?.addEventListener("click", () => zoomAt(ZOOM_STEP));
resetViewButton?.addEventListener("click", resetView);

board.addEventListener("pointerdown", startPan);
board.addEventListener("pointermove", continuePan);
board.addEventListener("pointerup", endPan);
board.addEventListener("pointerleave", endPan);
board.addEventListener("pointercancel", endPan);
board.addEventListener("wheel", handleWheelZoom, { passive: false });

function startLocalAiGame(humanPlayer) {
  stopAutoplay();
  cancelLocalAiTurn();
  appState.sessionId = null;
  appState.localState = localGame.createInitialLocalState();
  appState.localContext = {
    mode: "local_ai",
    humanPlayer,
    localAiPlayer: humanPlayer === "x" ? "o" : "x",
    lastResponse: [],
    players: humanPlayer === "x"
      ? { x: "You", o: LOCAL_AI_NAME }
      : { x: LOCAL_AI_NAME, o: "You" },
  };
  appState.currentMode = "local_ai";
  appState.selectedCells = [];
  appState.payload = localGame.buildLocalPayload(appState.localState, appState.localContext);
  resetView();
  render();

  if (humanPlayer === "x") {
    showMessage("Local AI match ready. You move first.");
  } else {
    showMessage("Local AI match ready. The browser AI will open.");
    scheduleLocalAiTurn();
  }
}

function startFriendGame() {
  stopAutoplay();
  cancelLocalAiTurn();
  appState.sessionId = null;
  appState.localState = localGame.createInitialLocalState();
  appState.localContext = {
    mode: "local_friend",
    humanPlayer: null,
    localAiPlayer: null,
    lastResponse: [],
    players: { x: "Friend 1", o: "Friend 2" },
  };
  appState.currentMode = "local_friend";
  appState.selectedCells = [];
  appState.payload = localGame.buildLocalPayload(appState.localState, appState.localContext);
  resetView();
  render();
  showMessage("Friend match ready.");
}

async function startSpectatorGame() {
  stopAutoplay();
  cancelLocalAiTurn();
  try {
    const response = await fetch(apiPath("api/new-game"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ human: "watch" }),
    });
    const payload = await response.json();
    if (!response.ok || !payload?.state || !payload?.session_id) {
      showMessage(payload?.message || payload?.error || "Unable to start the engine spectator match.");
      return;
    }

    appState.payload = payload;
    appState.sessionId = payload.session_id;
    appState.localState = null;
    appState.localContext = null;
    appState.currentMode = "spectator";
    appState.selectedCells = [];
    resetView();
    render();
    startAutoplay();
    showMessage("Engine spectator match started.");
  } catch (error) {
    showMessage("Unable to start the engine spectator match.");
  }
}

async function submitMove() {
  if (!appState.payload || !appState.selectedCells.length) {
    return;
  }

  if (appState.payload.mode === "spectator") {
    showMessage("Spectator mode is engine-controlled.");
    return;
  }

  if (!isHumanInteractionTurn()) {
    showMessage("It is not your move.");
    return;
  }

  if (appState.localState) {
    submitLocalMove();
    return;
  }

  const response = await fetch(apiPath(`api/play/${appState.sessionId}`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cells: appState.selectedCells }),
  });
  const nextPayload = await response.json();
  if (!response.ok) {
    showMessage(nextPayload.message || nextPayload.error || "Move rejected.");
    return;
  }

  appState.payload = nextPayload;
  appState.selectedCells = [];
  render();
  if (appState.payload.state.is_terminal) {
    showMessage(localGame.resultMessage(appState.payload.state));
  }
}

function submitLocalMove() {
  const absoluteCells = appState.selectedCells.map(localGame.relativeToAbsolute);
  try {
    appState.localState = localGame.applyTurnToLocalState(appState.localState, absoluteCells);
    appState.localContext.lastResponse = [];
    appState.selectedCells = [];
    appState.payload = localGame.buildLocalPayload(appState.localState, appState.localContext);
    render();

    if (appState.payload.state.is_terminal) {
      showMessage(localGame.resultMessage(appState.payload.state));
      return;
    }

    if (
      appState.currentMode === "local_ai"
      && appState.localState.toPlay === appState.localContext.localAiPlayer
    ) {
      showMessage("Browser AI is taking its turn locally.");
      scheduleLocalAiTurn();
      return;
    }

    showMessage("Turn submitted.");
  } catch (error) {
    showMessage(error instanceof Error ? error.message : "Move rejected.");
  }
}

async function stepBots() {
  if (
    !appState.sessionId
    || !appState.payload
    || appState.payload.mode !== "spectator"
    || appState.payload.state.is_terminal
    || appState.stepInFlight
  ) {
    return;
  }

  appState.stepInFlight = true;
  try {
    const response = await fetch(apiPath(`api/step/${appState.sessionId}`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    const nextPayload = await response.json();
    if (!response.ok) {
      stopAutoplay();
      showMessage(nextPayload.message || nextPayload.error || "Engine step failed.");
      return;
    }

    appState.payload = nextPayload;
    render();
    if (appState.payload.state.is_terminal) {
      stopAutoplay();
      showMessage(localGame.resultMessage(appState.payload.state));
    }
  } finally {
    appState.stepInFlight = false;
  }
}

function startAutoplay() {
  if (appState.autoplayTimer) {
    return;
  }
  appState.autoplayTimer = window.setInterval(() => {
    void stepBots();
  }, 500);
  autoplayButton.textContent = "Autoplay On";
}

function stopAutoplay() {
  if (!appState.autoplayTimer) {
    autoplayButton.textContent = "Autoplay Off";
    return;
  }
  window.clearInterval(appState.autoplayTimer);
  appState.autoplayTimer = null;
  autoplayButton.textContent = "Autoplay Off";
}

function toggleAutoplay() {
  if (!appState.payload || appState.payload.mode !== "spectator") {
    return;
  }
  if (appState.autoplayTimer) {
    stopAutoplay();
  } else {
    startAutoplay();
  }
}

function scheduleLocalAiTurn() {
  if (
    appState.localAiTimer
    || !appState.localState
    || appState.currentMode !== "local_ai"
    || appState.localState.toPlay !== appState.localContext.localAiPlayer
    || localGame.isTerminalState(appState.localState)
  ) {
    return;
  }

  appState.localAiTimer = window.setTimeout(() => {
    appState.localAiTimer = null;
    runLocalAiTurn();
  }, 280);
}

function cancelLocalAiTurn() {
  if (!appState.localAiTimer) {
    return;
  }
  window.clearTimeout(appState.localAiTimer);
  appState.localAiTimer = null;
}

function runLocalAiTurn() {
  if (
    !appState.localState
    || appState.currentMode !== "local_ai"
    || appState.localState.toPlay !== appState.localContext.localAiPlayer
    || localGame.isTerminalState(appState.localState)
  ) {
    return;
  }

  try {
    const turn = localGame.chooseLocalAiTurn(appState.localState, appState.localContext.localAiPlayer);
    appState.localState = localGame.applyTurnToLocalState(appState.localState, turn);
    appState.localContext.lastResponse = turn;
    appState.payload = localGame.buildLocalPayload(appState.localState, appState.localContext);
    render();
    if (appState.payload.state.is_terminal) {
      showMessage(localGame.resultMessage(appState.payload.state));
      return;
    }
    showMessage(`${LOCAL_AI_NAME} played ${localGame.formatTurn(turn.map(localGame.toRelativeCell))}.`);
  } catch (error) {
    showMessage(error instanceof Error ? error.message : "Local AI move failed.");
  }
}

function clearSelection() {
  appState.selectedCells = [];
  renderSelection();
  renderBoard();
}

function resetView() {
  appState.camera = { x: 0, y: 0 };
  appState.zoom = 1;
  renderZoom();
  renderBoard();
}

function startPan(event) {
  appState.pointerState = {
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    lastX: event.clientX,
    lastY: event.clientY,
    moved: false,
  };
  board.setPointerCapture(event.pointerId);
}

function continuePan(event) {
  if (!appState.pointerState || appState.pointerState.pointerId !== event.pointerId) {
    return;
  }

  const dx = event.clientX - appState.pointerState.lastX;
  const dy = event.clientY - appState.pointerState.lastY;
  appState.pointerState.lastX = event.clientX;
  appState.pointerState.lastY = event.clientY;
  const rect = board.getBoundingClientRect();
  const scaleX = VIEWBOX.width / rect.width;
  const scaleY = VIEWBOX.height / rect.height;

  if (!appState.pointerState.moved) {
    const totalDx = event.clientX - appState.pointerState.startX;
    const totalDy = event.clientY - appState.pointerState.startY;
    appState.pointerState.moved = Math.hypot(totalDx, totalDy) > 6;
  }

  if (appState.pointerState.moved) {
    appState.camera.x += dx * scaleX;
    appState.camera.y += dy * scaleY;
    renderBoard();
  }
}

function endPan(event) {
  if (!appState.pointerState || appState.pointerState.pointerId !== event.pointerId) {
    return;
  }
  board.releasePointerCapture(event.pointerId);
  const moved = appState.pointerState.moved;
  appState.pointerState = null;
  if (!moved && event.type === "pointerup") {
    handleBoardTap(event);
  }
}

function handleBoardTap(event) {
  if (!appState.payload) {
    return;
  }
  const point = clientToSvgPoint(event.clientX, event.clientY);
  const axial = pixelToAxial(point.x, point.y);
  const rounded = axialRound(axial.q, axial.r);
  toggleCell(rounded);
}

function toggleCell(cell) {
  if (!appState.payload || appState.payload.state.is_terminal || !isHumanInteractionTurn()) {
    return;
  }
  if (!isWithinBoardBounds(cell)) {
    return;
  }

  const key = localGame.cellKey(cell);
  const occupied = new Set(appState.payload.state.stones.map((stone) => localGame.cellKey(stone)));
  if (occupied.has(key)) {
    return;
  }

  const existingIndex = appState.selectedCells.findIndex((item) => localGame.cellKey(item) === key);
  if (existingIndex >= 0) {
    appState.selectedCells.splice(existingIndex, 1);
    renderSelection();
    renderBoard();
    return;
  }

  if (appState.selectedCells.length >= appState.payload.state.placements_remaining) {
    return;
  }

  appState.selectedCells.push({ q: cell.q, r: cell.r });
  renderSelection();
  renderBoard();
}

function handleWheelZoom(event) {
  event.preventDefault();
  const factor = event.deltaY > 0 ? 1 / ZOOM_STEP : ZOOM_STEP;
  const point = clientToSvgPoint(event.clientX, event.clientY);
  zoomAt(factor, point);
}

function zoomAt(factor, point = { x: VIEWBOX.width / 2, y: VIEWBOX.height / 2 }) {
  const nextZoom = clamp(appState.zoom * factor, ZOOM_MIN, ZOOM_MAX);
  if (Math.abs(nextZoom - appState.zoom) < 0.001) {
    return;
  }

  const centerX = VIEWBOX.width / 2;
  const centerY = VIEWBOX.height / 2;
  const boardX = (point.x - centerX - appState.camera.x) / appState.zoom;
  const boardY = (point.y - centerY - appState.camera.y) / appState.zoom;
  appState.zoom = nextZoom;
  appState.camera.x = point.x - centerX - boardX * appState.zoom;
  appState.camera.y = point.y - centerY - boardY * appState.zoom;
  renderZoom();
  renderBoard();
}

function render() {
  renderModeCards();
  renderContextCopy();
  renderStatus();
  renderSelection();
  renderZoom();
  renderBoard();
}

function renderModeCards() {
  modeCards.forEach((card) => {
    const cardMode = card.getAttribute("data-mode-card");
    card.classList.toggle("is-active", cardMode === appState.currentMode);
  });
}

function renderContextCopy() {
  if (!appState.payload) {
    boardTitleNode.textContent = GAME.boardTitle;
    boardSubtitleNode.textContent = "Start a local AI match, a friend match, or an engine spectator session.";
    boardHelperNode.textContent = "Tap empty cells to queue a turn. Drag to pan. Use the wheel or zoom controls to adjust the board.";
    turnHelperNode.textContent = "Choose a mode, then select cells on the board to build a turn.";
    return;
  }

  const mode = appState.payload.mode;
  if (mode === "local_ai") {
    boardTitleNode.textContent = "Play vs AI";
    boardSubtitleNode.textContent = "The lightweight AI runs on the visitor device instead of a hosted engine lane.";
  } else if (mode === "local_friend") {
    boardTitleNode.textContent = "Play vs Friend";
    boardSubtitleNode.textContent = "Hot-seat play on one device with the full Hex6 turn rules intact.";
  } else if (mode === "spectator") {
    boardTitleNode.textContent = "Watch Engine Match";
    boardSubtitleNode.textContent = `Hosted engine lane: ${GAME.botLabel}.`;
  }

  if (appState.payload.state.is_terminal) {
    boardHelperNode.textContent = "The game is finished. You can still inspect the board or start a new mode.";
  } else if (isHumanInteractionTurn()) {
    boardHelperNode.textContent = "Tap empty cells to queue the current turn. Winning lines stop the turn immediately.";
  } else if (mode === "local_ai") {
    boardHelperNode.textContent = "The browser AI is calculating locally. You can still pan and zoom the board.";
  } else if (mode === "spectator") {
    boardHelperNode.textContent = "Autoplay advances the engine match. Pause it if you want to inspect a position.";
  } else {
    boardHelperNode.textContent = "Use the board controls to inspect the current position.";
  }

  turnHelperNode.textContent = appState.payload.state.placements_remaining === 1
    ? "This turn needs one placement."
    : "This turn normally needs two placements. You may submit one stone early only if it wins immediately.";
}

function renderStatus() {
  if (!appState.payload) {
    turnLabel.textContent = "Not started";
    placementsLabel.textContent = "0";
    pliesLabel.textContent = "0";
    winnerLabel.textContent = "None";
    responseLabel.textContent = "None";
    modeLabel.textContent = "Idle";
    matchupLabel.textContent = "None";
    submitButton.disabled = true;
    clearButton.disabled = appState.selectedCells.length === 0;
    stepBotButton.disabled = true;
    autoplayButton.disabled = true;
    return;
  }

  turnLabel.textContent = appState.payload.state.to_play.toUpperCase();
  placementsLabel.textContent = String(appState.payload.state.placements_remaining);
  pliesLabel.textContent = String(appState.payload.state.ply_count);
  winnerLabel.textContent = appState.payload.state.winner
    ? appState.payload.state.winner.toUpperCase()
    : appState.payload.state.draw_reason
      ? `Draw (${appState.payload.state.draw_reason})`
      : "None";
  responseLabel.textContent = appState.payload.last_bot_turn.length
    ? localGame.formatTurn(appState.payload.last_bot_turn)
    : "None";
  modeLabel.textContent = modeDisplayName(appState.payload.mode);
  matchupLabel.textContent = `X: ${appState.payload.players.x} | O: ${appState.payload.players.o}`;

  submitButton.disabled = (
    !isHumanInteractionTurn()
    || appState.payload.state.is_terminal
    || appState.selectedCells.length === 0
    || appState.selectedCells.length > appState.payload.state.placements_remaining
  );
  clearButton.disabled = appState.selectedCells.length === 0;
  stepBotButton.disabled = appState.payload.mode !== "spectator" || appState.payload.state.is_terminal;
  autoplayButton.disabled = appState.payload.mode !== "spectator" || appState.payload.state.is_terminal;
}

function renderSelection() {
  selectedCellsNode.innerHTML = "";
  if (!appState.selectedCells.length) {
    const pill = document.createElement("div");
    pill.className = "pill subtle";
    pill.textContent = "No cells selected";
    selectedCellsNode.appendChild(pill);
    return;
  }

  appState.selectedCells.forEach((cell, index) => {
    const pill = document.createElement("div");
    pill.className = "pill";
    const label = document.createElement("span");
    label.textContent = `Stone ${index + 1} - ${localGame.formatCell(cell)}`;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "x";
    remove.addEventListener("click", () => {
      appState.selectedCells = appState.selectedCells.filter((item) => item !== cell);
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
  if (!appState.payload) {
    renderBoardPlaceholder("Choose a mode to begin.");
    return;
  }

  const occupied = new Map(appState.payload.state.stones.map((stone) => [localGame.cellKey(stone), stone.player]));
  const winning = new Set((appState.payload.state.winning_line || []).map((cell) => localGame.cellKey(cell)));
  const selected = new Set(appState.selectedCells.map((cell) => localGame.cellKey(cell)));
  const recent = new Set(appState.payload.last_bot_turn.map((cell) => localGame.cellKey(cell)));
  const cells = visibleCells();
  if (!cells.length) {
    renderBoardPlaceholder("No visible cells in the current view.");
    return;
  }

  cells.forEach((cell) => {
    const point = axialToPixel(cell.q, cell.r);
    const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
    const key = localGame.cellKey(cell);
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
    polygon.setAttribute("points", hexPoints(HEX_RADIUS * appState.zoom));
    group.appendChild(polygon);

    if (occupant === "x") {
      group.appendChild(makeLine(-12 * appState.zoom, -14 * appState.zoom, 12 * appState.zoom, 14 * appState.zoom, "token-x"));
      group.appendChild(makeLine(-12 * appState.zoom, 14 * appState.zoom, 12 * appState.zoom, -14 * appState.zoom, "token-x"));
    } else if (occupant === "o") {
      const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.setAttribute("r", String(15 * appState.zoom));
      circle.setAttribute("class", "token-o");
      group.appendChild(circle);
    }

    board.appendChild(group);
  });
}

function visibleCells() {
  const centerApprox = pixelToAxial(VIEWBOX.width / 2, VIEWBOX.height / 2);
  const center = axialRound(centerApprox.q, centerApprox.r);
  const cells = [];
  const boardSpan = Math.max(VIEWBOX.width, VIEWBOX.height) / (HEX_SPACING * appState.zoom);
  const radius = Math.max(10, Math.ceil(boardSpan / 1.2) + 3);

  for (let dq = -radius; dq <= radius; dq += 1) {
    const drMin = Math.max(-radius, -dq - radius);
    const drMax = Math.min(radius, -dq + radius);
    for (let dr = drMin; dr <= drMax; dr += 1) {
      const cell = { q: center.q + dq, r: center.r + dr };
      const point = axialToPixel(cell.q, cell.r);
      if (
        isWithinBoardBounds(cell)
        && point.x >= -80
        && point.x <= VIEWBOX.width + 80
        && point.y >= -80
        && point.y <= VIEWBOX.height + 80
      ) {
        cells.push(cell);
      }
    }
  }

  return cells;
}

function isWithinBoardBounds(cell) {
  const bounds = appState.payload?.config?.board_bounds;
  if (!bounds) {
    return true;
  }
  return (
    cell.q >= bounds.min_q
    && cell.q <= bounds.max_q
    && cell.r >= bounds.min_r
    && cell.r <= bounds.max_r
  );
}

function axialToPixel(q, r) {
  const scale = HEX_SPACING * appState.zoom;
  return {
    x: VIEWBOX.width / 2 + appState.camera.x + scale * Math.sqrt(3) * (q + r / 2),
    y: VIEWBOX.height / 2 + appState.camera.y + scale * 1.5 * r,
  };
}

function pixelToAxial(svgX, svgY) {
  const scale = HEX_SPACING * appState.zoom;
  const x = svgX - VIEWBOX.width / 2 - appState.camera.x;
  const y = svgY - VIEWBOX.height / 2 - appState.camera.y;
  return {
    q: (Math.sqrt(3) / 3 * x - y / 3) / scale,
    r: ((2 * y) / 3) / scale,
  };
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

function makeLine(x1, y1, x2, y2, className) {
  const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
  line.setAttribute("x1", String(x1));
  line.setAttribute("y1", String(y1));
  line.setAttribute("x2", String(x2));
  line.setAttribute("y2", String(y2));
  line.setAttribute("class", className);
  return line;
}

function renderZoom() {
  zoomLabel.textContent = `${Math.round(appState.zoom * 100)}%`;
}

function renderBoardPlaceholder(message) {
  const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
  text.setAttribute("x", String(VIEWBOX.width / 2));
  text.setAttribute("y", String(VIEWBOX.height / 2));
  text.setAttribute("text-anchor", "middle");
  text.setAttribute("fill", "rgba(17, 24, 27, 0.48)");
  text.setAttribute("font-size", "24");
  text.setAttribute("font-family", "Bahnschrift, Segoe UI, sans-serif");
  text.textContent = message;
  board.appendChild(text);
}

function isHumanInteractionTurn() {
  if (!appState.payload || appState.payload.state.is_terminal) {
    return false;
  }
  if (appState.payload.mode === "local_friend") {
    return true;
  }
  if (appState.payload.mode === "local_ai") {
    return appState.payload.state.to_play === appState.payload.human_player;
  }
  return appState.payload.mode === "human_vs_bot" && appState.payload.state.to_play === appState.payload.human_player;
}

function modeDisplayName(mode) {
  if (mode === "local_ai") {
    return "Play vs AI";
  }
  if (mode === "local_friend") {
    return "Play vs Friend";
  }
  if (mode === "spectator") {
    return "Watch Engine Match";
  }
  return "Idle";
}

function showMessage(message) {
  flashMessageNode.textContent = message;
  flashMessageNode.classList.add("visible");
  if (appState.flashTimer) {
    window.clearTimeout(appState.flashTimer);
  }
  appState.flashTimer = window.setTimeout(() => {
    flashMessageNode.classList.remove("visible");
  }, 2600);
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function apiPath(relativePath) {
  return new URL(relativePath, window.location.href).toString();
}

render();
window.Hex6RuleDemos.init(document.querySelectorAll(".rule-board"));
