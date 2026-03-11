(function attachRuleDemos(global) {
  const demos = {
    opening: {
      bounds: { min_q: -2, max_q: 2, min_r: -2, max_r: 2 },
      steps: [
        { focus: [{ q: 0, r: 0 }], stones: [] },
        { recent: [{ q: 0, r: 0 }], stones: [{ q: 0, r: 0, player: "x" }] },
        {
          focus: [
            { q: -1, r: 1 },
            { q: 1, r: 0 },
          ],
          stones: [{ q: 0, r: 0, player: "x" }],
        },
      ],
    },
    "double-turn": {
      bounds: { min_q: -2, max_q: 2, min_r: -2, max_r: 2 },
      steps: [
        {
          stones: [{ q: 0, r: 0, player: "x" }],
          focus: [
            { q: -1, r: 0 },
            { q: 1, r: -1 },
          ],
        },
        {
          stones: [
            { q: 0, r: 0, player: "x" },
            { q: -1, r: 0, player: "o" },
          ],
          recent: [{ q: -1, r: 0 }],
          focus: [{ q: 1, r: -1 }],
        },
        {
          stones: [
            { q: 0, r: 0, player: "x" },
            { q: -1, r: 0, player: "o" },
            { q: 1, r: -1, player: "o" },
          ],
          recent: [
            { q: -1, r: 0 },
            { q: 1, r: -1 },
          ],
        },
      ],
    },
    "mid-turn-win": {
      bounds: { min_q: -3, max_q: 3, min_r: -2, max_r: 2 },
      steps: [
        {
          stones: [
            { q: -2, r: 0, player: "x" },
            { q: -1, r: 0, player: "x" },
            { q: 0, r: 0, player: "x" },
            { q: 1, r: 0, player: "x" },
            { q: 2, r: 0, player: "x" },
            { q: -1, r: 1, player: "o" },
            { q: 1, r: -1, player: "o" },
          ],
          focus: [{ q: 3, r: 0 }],
        },
        {
          stones: [
            { q: -2, r: 0, player: "x" },
            { q: -1, r: 0, player: "x" },
            { q: 0, r: 0, player: "x" },
            { q: 1, r: 0, player: "x" },
            { q: 2, r: 0, player: "x" },
            { q: 3, r: 0, player: "x" },
            { q: -1, r: 1, player: "o" },
            { q: 1, r: -1, player: "o" },
          ],
          winning: [
            { q: -2, r: 0 },
            { q: -1, r: 0 },
            { q: 0, r: 0 },
            { q: 1, r: 0 },
            { q: 2, r: 0 },
            { q: 3, r: 0 },
          ],
          recent: [{ q: 3, r: 0 }],
          ghost: [{ q: 2, r: -1 }],
        },
        {
          stones: [
            { q: -2, r: 0, player: "x" },
            { q: -1, r: 0, player: "x" },
            { q: 0, r: 0, player: "x" },
            { q: 1, r: 0, player: "x" },
            { q: 2, r: 0, player: "x" },
            { q: 3, r: 0, player: "x" },
            { q: -1, r: 1, player: "o" },
            { q: 1, r: -1, player: "o" },
          ],
          winning: [
            { q: -2, r: 0 },
            { q: -1, r: 0 },
            { q: 0, r: 0 },
            { q: 1, r: 0 },
            { q: 2, r: 0 },
            { q: 3, r: 0 },
          ],
          recent: [{ q: 3, r: 0 }],
        },
      ],
    },
    "board-exhausted": {
      bounds: { min_q: -2, max_q: 1, min_r: -1, max_r: 2 },
      steps: [
        {
          stones: denseDemoStones(),
          focus: [{ q: 1, r: 2 }],
        },
        {
          stones: denseDemoStones(),
          overlay: "2 placements needed",
          focus: [{ q: 1, r: 2 }],
        },
        {
          stones: denseDemoStones(),
          overlay: "Draw: board exhausted",
          muted: true,
        },
      ],
    },
  };

  function denseDemoStones() {
    return [
      { q: -2, r: -1, player: "x" },
      { q: -1, r: -1, player: "o" },
      { q: 0, r: -1, player: "x" },
      { q: 1, r: -1, player: "o" },
      { q: -2, r: 0, player: "o" },
      { q: -1, r: 0, player: "x" },
      { q: 0, r: 0, player: "o" },
      { q: 1, r: 0, player: "x" },
      { q: -2, r: 1, player: "x" },
      { q: -1, r: 1, player: "o" },
      { q: 0, r: 1, player: "x" },
      { q: 1, r: 1, player: "o" },
      { q: -2, r: 2, player: "o" },
      { q: -1, r: 2, player: "x" },
      { q: 0, r: 2, player: "o" },
    ];
  }

  function cellKey(cell) {
    return `${cell.q},${cell.r}`;
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

  function createProjector(bounds, width, height) {
    const midQ = (bounds.min_q + bounds.max_q) / 2;
    const midR = (bounds.min_r + bounds.max_r) / 2;
    return (cell) => ({
      x: width / 2 + 30 * Math.sqrt(3) * ((cell.q - midQ) + (cell.r - midR) / 2),
      y: height / 2 + 30 * 1.5 * (cell.r - midR),
    });
  }

  function renderRuleBoard(svg, demo, tick) {
    const step = demo.steps[tick % demo.steps.length];
    svg.innerHTML = "";
    const focus = new Set((step.focus || []).map(cellKey));
    const recent = new Set((step.recent || []).map(cellKey));
    const winning = new Set((step.winning || []).map(cellKey));
    const ghost = new Set((step.ghost || []).map(cellKey));
    const stones = new Map((step.stones || []).map((stone) => [cellKey(stone), stone.player]));
    const project = createProjector(demo.bounds, svg.viewBox.baseVal.width, svg.viewBox.baseVal.height);

    for (let q = demo.bounds.min_q; q <= demo.bounds.max_q; q += 1) {
      for (let r = demo.bounds.min_r; r <= demo.bounds.max_r; r += 1) {
        const cell = { q, r };
        const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
        const key = cellKey(cell);
        const occupant = stones.get(key);
        const point = project(cell);
        const classes = ["demo-cell"];
        if (step.muted) {
          classes.push("is-muted");
        }
        if (focus.has(key)) {
          classes.push("is-focus");
        }
        if (recent.has(key)) {
          classes.push("is-recent");
        }
        if (winning.has(key)) {
          classes.push("is-winning");
        }
        if (ghost.has(key)) {
          classes.push("is-ghost");
        }
        group.setAttribute("class", classes.join(" "));
        group.setAttribute("transform", `translate(${point.x}, ${point.y})`);

        const polygon = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
        polygon.setAttribute("points", hexPoints(14));
        group.appendChild(polygon);

        if (occupant === "x") {
          group.appendChild(makeLine(-6, -7, 6, 7, "demo-token-x"));
          group.appendChild(makeLine(-6, 7, 6, -7, "demo-token-x"));
        } else if (occupant === "o") {
          const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
          circle.setAttribute("r", "7.5");
          circle.setAttribute("class", "demo-token-o");
          group.appendChild(circle);
        }

        svg.appendChild(group);
      }
    }

    if (step.overlay) {
      const overlay = document.createElementNS("http://www.w3.org/2000/svg", "text");
      overlay.setAttribute("x", String(svg.viewBox.baseVal.width / 2));
      overlay.setAttribute("y", String(svg.viewBox.baseVal.height - 18));
      overlay.setAttribute("text-anchor", "middle");
      overlay.setAttribute("class", "demo-overlay");
      overlay.textContent = step.overlay;
      svg.appendChild(overlay);
    }
  }

  function init(nodes) {
    const boards = Array.from(nodes || []);
    if (!boards.length) {
      return;
    }

    let tick = 0;
    const draw = () => {
      boards.forEach((svg, index) => {
        const demo = demos[svg.dataset.demo];
        if (demo) {
          renderRuleBoard(svg, demo, tick + index);
        }
      });
    };

    draw();
    window.setInterval(() => {
      tick += 1;
      draw();
    }, 1400);
  }

  global.Hex6RuleDemos = { init };
})(window);
