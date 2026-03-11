(function attachLocalGame(global) {
  function createHelpers(bootstrap) {
    const game = {
      boardMode: bootstrap.game?.boardMode || "sparse_bounded",
      boardWidth: bootstrap.game?.boardWidth || 15,
      boardHeight: bootstrap.game?.boardHeight || 15,
      winLength: bootstrap.game?.winLength || 6,
      openingPlacements: bootstrap.game?.openingPlacements || 1,
      turnPlacements: bootstrap.game?.turnPlacements || 2,
      boardBounds: bootstrap.game?.boardBounds || null,
      anchor: bootstrap.game?.anchor || { q: 0, r: 0 },
      boardTitle: bootstrap.boardTitle || "Board",
      botLabel: bootstrap.botLabel || "engine",
    };
    const lineAxes = [
      [1, 0],
      [0, 1],
      [1, -1],
    ];
    const ownWeights = buildWindowWeights([0, 2, 11, 42, 155, 920], 3.2);
    const enemyWeights = buildWindowWeights([0, 3, 14, 54, 200, 1200], 3.25);
    const absoluteBounds = game.boardBounds
      ? {
          min_q: game.boardBounds.min_q + game.anchor.q,
          max_q: game.boardBounds.max_q + game.anchor.q,
          min_r: game.boardBounds.min_r + game.anchor.r,
          max_r: game.boardBounds.max_r + game.anchor.r,
        }
      : null;
    const windowCache = new Map();

    function cellKey(cell) {
      return `${cell.q},${cell.r}`;
    }

    function parseCellKey(key) {
      const [q, r] = key.split(",").map(Number);
      return { q, r };
    }

    function formatCell(cell) {
      return `(${cell.q}, ${cell.r})`;
    }

    function formatTurn(cells) {
      return cells.map(formatCell).join(" then ");
    }

    function resultMessage(state) {
      if (state.winner) {
        return `${state.winner.toUpperCase()} wins.`;
      }
      if (state.draw_reason) {
        return `Draw by ${state.draw_reason}.`;
      }
      return "Game finished.";
    }

    function opponentOf(player) {
      return player === "x" ? "o" : "x";
    }

    function compareCells(a, b) {
      if (a.q !== b.q) {
        return a.q - b.q;
      }
      return a.r - b.r;
    }

    function addCell(a, direction) {
      return { q: a.q + direction[0], r: a.r + direction[1] };
    }

    function hexDistance(a, b) {
      const dq = a.q - b.q;
      const dr = a.r - b.r;
      const ds = (-a.q - a.r) - (-b.q - b.r);
      return Math.max(Math.abs(dq), Math.abs(dr), Math.abs(ds));
    }

    function isTerminalState(state) {
      return Boolean(state.winner || state.drawReason);
    }

    function isAbsoluteInBounds(cell) {
      if (!absoluteBounds) {
        return true;
      }
      return (
        cell.q >= absoluteBounds.min_q
        && cell.q <= absoluteBounds.max_q
        && cell.r >= absoluteBounds.min_r
        && cell.r <= absoluteBounds.max_r
      );
    }

    function remainingEmptyCells(state) {
      if (!absoluteBounds) {
        return null;
      }
      const totalCells = (
        (absoluteBounds.max_q - absoluteBounds.min_q + 1)
        * (absoluteBounds.max_r - absoluteBounds.min_r + 1)
      );
      return Math.max(0, totalCells - state.stones.size);
    }

    function withExhaustionDrawIfNeeded(state) {
      if (isTerminalState(state)) {
        return state;
      }
      const remaining = remainingEmptyCells(state);
      if (remaining === null || remaining >= state.placementsRemaining) {
        return state;
      }
      return {
        ...state,
        placementsRemaining: 0,
        winner: null,
        drawReason: "board_exhausted",
        winningLine: null,
      };
    }

    function createInitialLocalState() {
      return withExhaustionDrawIfNeeded({
        stones: new Map(),
        toPlay: "x",
        placementsRemaining: game.openingPlacements,
        turnIndex: 1,
        plyCount: 0,
        winner: null,
        drawReason: null,
        winningLine: null,
        moveHistory: [],
      });
    }

    function applyTurnToLocalState(state, cells) {
      if (cells.length === 0 || cells.length > state.placementsRemaining) {
        throw new Error(`expected ${state.placementsRemaining} placements, received ${cells.length}`);
      }

      let current = state;
      for (let index = 0; index < cells.length; index += 1) {
        current = applyPlacementToLocalState(current, cells[index]);
        if (isTerminalState(current) && index !== cells.length - 1) {
          throw new Error("turn continued after the game ended");
        }
        if (isTerminalState(current)) {
          return current;
        }
      }

      if (cells.length !== state.placementsRemaining) {
        throw new Error(`expected ${state.placementsRemaining} placements, received ${cells.length}`);
      }
      return current;
    }

    function applyPlacementToLocalState(state, cell) {
      if (isTerminalState(state)) {
        throw new Error("cannot place a stone after the game is over");
      }
      if (!isAbsoluteInBounds(cell)) {
        throw new Error(`cell ${formatCell(cell)} is outside the configured board bounds`);
      }

      const key = cellKey(cell);
      if (state.stones.has(key)) {
        throw new Error(`cell ${formatCell(cell)} is already occupied`);
      }

      const player = state.toPlay;
      const stones = new Map(state.stones);
      stones.set(key, player);
      const winningLine = findWinningLine(stones, cell, player);
      const remainingAfterMove = state.placementsRemaining - 1;
      const moveRecord = {
        player,
        cell,
        turnIndex: state.turnIndex,
        placementsRemainingAfter: Math.max(0, remainingAfterMove),
      };

      if (winningLine) {
        return {
          stones,
          toPlay: player,
          placementsRemaining: 0,
          turnIndex: state.turnIndex,
          plyCount: state.plyCount + 1,
          winner: player,
          drawReason: null,
          winningLine,
          moveHistory: [...state.moveHistory, moveRecord],
        };
      }

      if (remainingAfterMove > 0) {
        return withExhaustionDrawIfNeeded({
          stones,
          toPlay: player,
          placementsRemaining: remainingAfterMove,
          turnIndex: state.turnIndex,
          plyCount: state.plyCount + 1,
          winner: null,
          drawReason: null,
          winningLine: null,
          moveHistory: [...state.moveHistory, moveRecord],
        });
      }

      return withExhaustionDrawIfNeeded({
        stones,
        toPlay: opponentOf(player),
        placementsRemaining: game.turnPlacements,
        turnIndex: state.turnIndex + 1,
        plyCount: state.plyCount + 1,
        winner: null,
        drawReason: null,
        winningLine: null,
        moveHistory: [...state.moveHistory, moveRecord],
      });
    }

    function findWinningLine(stones, cell, player) {
      for (const axis of lineAxes) {
        const line = contiguousLine(stones, cell, player, axis);
        if (line.length >= game.winLength) {
          return line;
        }
      }
      return null;
    }

    function contiguousLine(stones, origin, player, axis) {
      const backward = walkLine(stones, origin, player, [-axis[0], -axis[1]]);
      const forward = walkLine(stones, origin, player, axis);
      return [...backward.reverse(), origin, ...forward];
    }

    function walkLine(stones, origin, player, direction) {
      const cells = [];
      let current = addCell(origin, direction);
      while (stones.get(cellKey(current)) === player) {
        cells.push(current);
        current = addCell(current, direction);
      }
      return cells;
    }

    function suggestedCenterAbsolute(state) {
      if (!state.stones.size) {
        return { ...game.anchor };
      }
      const cells = Array.from(state.stones.keys()).map(parseCellKey);
      const qs = cells.map((cell) => cell.q);
      const rs = cells.map((cell) => cell.r);
      return {
        q: Math.round((Math.min(...qs) + Math.max(...qs)) / 2),
        r: Math.round((Math.min(...rs) + Math.max(...rs)) / 2),
      };
    }

    function buildWindowWeights(seed, growth) {
      const weights = seed.slice(0, Math.min(seed.length, game.winLength));
      while (weights.length < game.winLength) {
        const last = weights[weights.length - 1] || 1;
        weights.push(Math.round(last * growth));
      }
      weights.push(1000000);
      return weights;
    }

    function relativeToAbsolute(cell) {
      return {
        q: cell.q + game.anchor.q,
        r: cell.r + game.anchor.r,
      };
    }

    function toRelativeCell(cell) {
      return {
        q: cell.q - game.anchor.q,
        r: cell.r - game.anchor.r,
      };
    }

    function buildLocalPayload(state, context) {
      const stones = Array.from(state.stones.entries())
        .map(([key, player]) => {
          const cell = parseCellKey(key);
          return { q: cell.q - game.anchor.q, r: cell.r - game.anchor.r, player };
        })
        .sort(compareCells);
      const suggestedCenter = state.stones.size ? suggestedCenterAbsolute(state) : { ...game.anchor };
      return {
        session_id: null,
        human_player: context.humanPlayer,
        bot_player: context.localAiPlayer,
        mode: context.mode,
        state: {
          stones,
          to_play: state.toPlay,
          placements_remaining: state.placementsRemaining,
          turn_index: state.turnIndex,
          ply_count: state.plyCount,
          winner: state.winner,
          draw_reason: state.drawReason,
          is_terminal: isTerminalState(state),
          winning_line: state.winningLine ? state.winningLine.map(toRelativeCell) : null,
        },
        last_bot_turn: context.lastResponse.map(toRelativeCell),
        players: context.players,
        view: {
          anchor: { ...game.anchor },
          suggested_center: toRelativeCell(suggestedCenter),
        },
        config: {
          board_mode: game.boardMode,
          board_bounds: game.boardBounds,
          win_length: game.winLength,
          opening_placements: game.openingPlacements,
          turn_placements: game.turnPlacements,
        },
      };
    }

    function listAnalysisBounds(state) {
      if (absoluteBounds) {
        return absoluteBounds;
      }
      const center = suggestedCenterAbsolute(state);
      return {
        min_q: center.q - 7,
        max_q: center.q + 7,
        min_r: center.r - 7,
        max_r: center.r + 7,
      };
    }

    function listEmptyCells(state) {
      const bounds = listAnalysisBounds(state);
      const empties = [];
      for (let q = bounds.min_q; q <= bounds.max_q; q += 1) {
        for (let r = bounds.min_r; r <= bounds.max_r; r += 1) {
          const cell = { q, r };
          if (isAbsoluteInBounds(cell) && !state.stones.has(cellKey(cell))) {
            empties.push(cell);
          }
        }
      }
      return empties;
    }

    function evaluationWindowsForState(state) {
      const bounds = listAnalysisBounds(state);
      const cacheKey = `${bounds.min_q}:${bounds.max_q}:${bounds.min_r}:${bounds.max_r}:${game.winLength}`;
      const cached = windowCache.get(cacheKey);
      if (cached) {
        return cached;
      }

      const windows = [];
      for (let q = bounds.min_q; q <= bounds.max_q; q += 1) {
        for (let r = bounds.min_r; r <= bounds.max_r; r += 1) {
          const start = { q, r };
          if (!isAbsoluteInBounds(start)) {
            continue;
          }
          for (const axis of lineAxes) {
            const end = {
              q: q + axis[0] * (game.winLength - 1),
              r: r + axis[1] * (game.winLength - 1),
            };
            if (!isAbsoluteInBounds(end)) {
              continue;
            }
            const cells = [];
            for (let offset = 0; offset < game.winLength; offset += 1) {
              cells.push({ q: q + axis[0] * offset, r: r + axis[1] * offset });
            }
            windows.push(cells);
          }
        }
      }

      windowCache.set(cacheKey, windows);
      return windows;
    }

    function evaluateLocalState(state, player) {
      if (state.winner === player) {
        return 1000000;
      }
      if (state.winner === opponentOf(player)) {
        return -1000000;
      }
      if (state.drawReason) {
        return -25;
      }

      const enemy = opponentOf(player);
      let total = 0;
      evaluationWindowsForState(state).forEach((window) => {
        let ownCount = 0;
        let enemyCount = 0;
        window.forEach((cell) => {
          const occupant = state.stones.get(cellKey(cell));
          if (occupant === player) {
            ownCount += 1;
          } else if (occupant === enemy) {
            enemyCount += 1;
          }
        });
        if (ownCount && enemyCount) {
          return;
        }
        if (ownCount) {
          total += ownWeights[ownCount];
        } else if (enemyCount) {
          total -= enemyWeights[enemyCount];
        }
      });

      const center = suggestedCenterAbsolute(state);
      state.stones.forEach((occupant, key) => {
        const cell = parseCellKey(key);
        const pull = Math.max(0, 8 - hexDistance(cell, center));
        total += occupant === player ? pull * 0.3 : -pull * 0.22;
      });
      return total;
    }

    function previewSinglePlacement(state, player, cell) {
      return simulateTurnForPlayer(state, player, [cell], 1);
    }

    function simulateTurnForPlayer(state, player, cells, placementsAvailable) {
      return applyTurnToLocalState(
        {
          stones: state.stones,
          toPlay: player,
          placementsRemaining: placementsAvailable,
          turnIndex: state.turnIndex,
          plyCount: state.plyCount,
          winner: null,
          drawReason: null,
          winningLine: null,
          moveHistory: state.moveHistory,
        },
        cells,
      );
    }

    function estimateCellPriority(state, cell, player) {
      try {
        const ownPreview = previewSinglePlacement(state, player, cell);
        if (ownPreview.winner === player) {
          return 1000000;
        }
        let score = evaluateLocalState(ownPreview, player);
        try {
          const enemyPreview = previewSinglePlacement(state, opponentOf(player), cell);
          if (enemyPreview.winner === opponentOf(player)) {
            score += 250000;
          }
        } catch (error) {
          // Ignore invalid enemy previews.
        }
        score -= hexDistance(cell, suggestedCenterAbsolute(state)) * 0.8;
        return score;
      } catch (error) {
        return -1000000;
      }
    }

    function buildCandidatePool(state, player, extraCells = []) {
      if (!state.stones.size) {
        return [{ ...game.anchor }];
      }

      const scored = listEmptyCells(state)
        .map((cell) => ({ cell, score: estimateCellPriority(state, cell, player) }))
        .sort((left, right) => {
          if (right.score !== left.score) {
            return right.score - left.score;
          }
          return compareCells(left.cell, right.cell);
        });

      const pool = [];
      const seen = new Set();
      [...extraCells, ...scored.map((entry) => entry.cell)].forEach((cell) => {
        const key = cellKey(cell);
        if (seen.has(key)) {
          return;
        }
        seen.add(key);
        pool.push(cell);
      });

      const limit = state.placementsRemaining === 1 ? 14 : 12;
      return pool.slice(0, Math.max(limit, extraCells.length));
    }

    function compareTurnKeys(left, right) {
      const leftKey = left.map(cellKey).join("|");
      const rightKey = right.map(cellKey).join("|");
      if (leftKey < rightKey) {
        return -1;
      }
      if (leftKey > rightKey) {
        return 1;
      }
      return 0;
    }

    function chooseBestOrderedSimulation(state, player, cells, placementsAvailable) {
      const orders = cells.length === 2 ? [cells, [cells[1], cells[0]]] : [cells];
      let best = null;
      orders.forEach((order) => {
        try {
          const resultState = simulateTurnForPlayer(state, player, order, placementsAvailable);
          const score = resultState.winner === player ? 1000000 : evaluateLocalState(resultState, player);
          if (!best || score > best.score || (score === best.score && compareTurnKeys(order, best.cells) < 0)) {
            best = { cells: order, resultState, score };
          }
        } catch (error) {
          // Ignore orderings that violate the immediate-stop rule.
        }
      });
      return best;
    }

    function enumerateTurnChoices(state, player, placementsAvailable, requireFullTurn, extraCells = []) {
      const sizes = requireFullTurn
        ? [placementsAvailable]
        : Array.from({ length: placementsAvailable }, (_, index) => index + 1);
      const choices = [];
      const seen = new Set();
      const pool = buildCandidatePool(state, player, extraCells);

      sizes.forEach((size) => {
        if (size === 1) {
          pool.forEach((cell) => {
            const choice = chooseBestOrderedSimulation(state, player, [cell], placementsAvailable);
            if (!choice) {
              return;
            }
            const key = choice.cells.map(cellKey).join("|");
            if (seen.has(key)) {
              return;
            }
            seen.add(key);
            choices.push(choice);
          });
          return;
        }

        for (let first = 0; first < pool.length; first += 1) {
          for (let second = first + 1; second < pool.length; second += 1) {
            const choice = chooseBestOrderedSimulation(
              state,
              player,
              [pool[first], pool[second]],
              placementsAvailable,
            );
            if (!choice) {
              continue;
            }
            const key = choice.cells.map(cellKey).join("|");
            if (seen.has(key)) {
              continue;
            }
            seen.add(key);
            choices.push(choice);
          }
        }
      });

      return choices;
    }

    function findImmediateTurns(state, player, placementsAvailable) {
      return enumerateTurnChoices(state, player, placementsAvailable, false)
        .filter((choice) => choice.resultState.winner === player)
        .sort((left, right) => {
          if (left.cells.length !== right.cells.length) {
            return left.cells.length - right.cells.length;
          }
          return compareTurnKeys(left.cells, right.cells);
        });
    }

    function combinations(items, size) {
      if (size === 0) {
        return [[]];
      }
      if (size > items.length) {
        return [];
      }
      const result = [];
      function build(startIndex, path) {
        if (path.length === size) {
          result.push([...path]);
          return;
        }
        for (let index = startIndex; index < items.length; index += 1) {
          path.push(items[index]);
          build(index + 1, path);
          path.pop();
        }
      }
      build(0, []);
      return result;
    }

    function blocksAllThreats(turn, threats) {
      return threats.every((threat) => threat.cells.some((cell) => turn.some((picked) => cellKey(picked) === cellKey(cell))));
    }

    function defensiveTurnChoices(state, player, threats) {
      const criticalCells = [];
      const seen = new Set();
      threats.forEach((threat) => {
        threat.cells.forEach((cell) => {
          const key = cellKey(cell);
          if (!state.stones.has(key) && !seen.has(key)) {
            seen.add(key);
            criticalCells.push(cell);
          }
        });
      });
      if (!criticalCells.length) {
        return [];
      }

      const blockingSets = [];
      for (let size = 1; size <= Math.min(state.placementsRemaining, criticalCells.length); size += 1) {
        const combos = combinations(criticalCells, size).filter((combo) => blocksAllThreats(combo, threats));
        if (combos.length) {
          blockingSets.push(...combos);
          break;
        }
      }
      if (!blockingSets.length) {
        return [];
      }

      const fillerPool = buildCandidatePool(state, player, criticalCells);
      const choices = [];
      const choiceKeys = new Set();
      blockingSets.forEach((combo) => {
        if (combo.length === state.placementsRemaining) {
          const choice = chooseBestOrderedSimulation(state, player, combo, state.placementsRemaining);
          if (!choice) {
            return;
          }
          const key = choice.cells.map(cellKey).join("|");
          if (!choiceKeys.has(key)) {
            choiceKeys.add(key);
            choices.push(choice);
          }
          return;
        }

        const fillers = fillerPool.filter((cell) => !combo.some((item) => cellKey(item) === cellKey(cell)));
        combinations(fillers, state.placementsRemaining - combo.length).forEach((extra) => {
          const choice = chooseBestOrderedSimulation(
            state,
            player,
            [...combo, ...extra],
            state.placementsRemaining,
          );
          if (!choice) {
            return;
          }
          const key = choice.cells.map(cellKey).join("|");
          if (!choiceKeys.has(key)) {
            choiceKeys.add(key);
            choices.push(choice);
          }
        });
      });
      return choices;
    }

    function scoreTurnChoice(choice, player) {
      if (choice.resultState.winner === player) {
        return 1000000;
      }
      const enemy = opponentOf(player);
      const ownThreats = findImmediateTurns(choice.resultState, player, game.turnPlacements).length;
      const enemyThreats = findImmediateTurns(choice.resultState, enemy, game.turnPlacements).length;
      const spreadPenalty = choice.cells.length === 2 ? hexDistance(choice.cells[0], choice.cells[1]) * 1.4 : 0;
      return evaluateLocalState(choice.resultState, player) + ownThreats * 2400 - enemyThreats * 3200 - spreadPenalty;
    }

    function pickBestChoice(choices, player) {
      return choices
        .map((choice) => ({ ...choice, turnScore: scoreTurnChoice(choice, player) }))
        .sort((left, right) => {
          if (right.turnScore !== left.turnScore) {
            return right.turnScore - left.turnScore;
          }
          if (left.cells.length !== right.cells.length) {
            return left.cells.length - right.cells.length;
          }
          return compareTurnKeys(left.cells, right.cells);
        })[0];
    }

    function chooseLocalAiTurn(state, player) {
      if (!state.stones.size && state.placementsRemaining === 1) {
        return [{ ...game.anchor }];
      }

      const immediateWins = findImmediateTurns(state, player, state.placementsRemaining);
      if (immediateWins.length) {
        return immediateWins[0].cells;
      }

      const threats = findImmediateTurns(state, opponentOf(player), game.turnPlacements);
      if (threats.length) {
        const defensiveChoices = defensiveTurnChoices(state, player, threats);
        if (defensiveChoices.length) {
          return pickBestChoice(defensiveChoices, player).cells;
        }
      }

      const fullChoices = enumerateTurnChoices(state, player, state.placementsRemaining, true);
      if (fullChoices.length) {
        return pickBestChoice(fullChoices, player).cells;
      }

      const fallbackChoices = enumerateTurnChoices(state, player, state.placementsRemaining, false);
      if (fallbackChoices.length) {
        return pickBestChoice(fallbackChoices, player).cells;
      }

      throw new Error("No legal local AI turn found.");
    }

    return {
      game,
      cellKey,
      formatCell,
      formatTurn,
      resultMessage,
      createInitialLocalState,
      applyTurnToLocalState,
      buildLocalPayload,
      chooseLocalAiTurn,
      isTerminalState,
      relativeToAbsolute,
      toRelativeCell,
    };
  }

  global.Hex6LocalGame = { createHelpers };
})(window);
