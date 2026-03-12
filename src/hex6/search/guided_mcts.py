"""AlphaZero-style guided MCTS over factorized Hex6 turns."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
import random
from typing import Iterable

import torch

from hex6.config import AppConfig
from hex6.game import Coord, GameState, IllegalMoveError, Player
from hex6.nn import HexPolicyValueNet, encode_state, load_compatible_state_dict

from .baseline import BaselineTurnSearch, ScoredTurn


@dataclass(frozen=True)
class RootTurnStat:
    cells: tuple[Coord, ...]
    visits: int
    prior: float
    mean_value: float


@dataclass(frozen=True)
class RootAnalysis:
    chosen_turn: ScoredTurn
    turn_stats: tuple[RootTurnStat, ...]
    cell_policy: tuple[tuple[Coord, float], ...]
    simulations: int


@dataclass
class _Edge:
    cells: tuple[Coord, ...]
    prior: float
    root_gumbel: float = 0.0
    visit_count: int = 0
    value_sum: float = 0.0
    child: _Node | None = None

    @property
    def mean_value(self) -> float:
        if self.visit_count == 0:
            return 0.0
        return self.value_sum / self.visit_count


@dataclass
class _Node:
    state: GameState
    visit_count: int = 0
    edges: list[_Edge] = field(default_factory=list)
    expanded: bool = False


@dataclass(frozen=True)
class _PolicyLookup:
    probabilities: torch.Tensor
    center: Coord
    radius: int


@dataclass
class _PendingSearch:
    root: _Node
    node_cache: dict[tuple[object, ...], _Node]
    root_player: Player
    path_nodes: list[_Node]
    path_edges: list[_Edge]
    leaf: _Node | None = None
    expand_leaf: bool = False
    add_root_noise: bool = False
    value: float | None = None


class GuidedMctsTurnSearch:
    """Policy/value-guided PUCT search over factorized turns."""

    def __init__(
        self,
        model: HexPolicyValueNet,
        *,
        device: torch.device,
        baseline: BaselineTurnSearch | None = None,
        seed: int = 0,
    ) -> None:
        self._model = model.eval()
        self._device = device
        self._baseline = baseline or BaselineTurnSearch()
        self._rng = random.Random(seed)
        self._policy_cache: dict[tuple[object, ...], _PolicyLookup] = {}
        self._value_cache: dict[tuple[object, ...], float] = {}

    @classmethod
    def from_checkpoint(
        cls,
        checkpoint_path: str | Path,
        config: AppConfig,
        *,
        device: torch.device | None = None,
        baseline: BaselineTurnSearch | None = None,
        seed: int = 0,
    ) -> "GuidedMctsTurnSearch":
        device = device or _select_device(config)
        checkpoint = torch.load(checkpoint_path, map_location=device)
        model = HexPolicyValueNet(
            input_channels=6,
            channels=config.model.channels,
            blocks=config.model.blocks,
        )
        load_compatible_state_dict(model, checkpoint["model_state_dict"])
        model.to(device)
        return cls(model, device=device, baseline=baseline, seed=seed)

    def choose_turn(self, state: GameState, config: AppConfig) -> ScoredTurn:
        analysis = self.analyze_root(state, config)
        return analysis.chosen_turn

    def choose_turns(self, states: Iterable[GameState], config: AppConfig) -> list[ScoredTurn]:
        return [analysis.chosen_turn for analysis in self.analyze_roots(states, config)]

    def analyze_root(
        self,
        state: GameState,
        config: AppConfig,
        *,
        sample: bool = False,
        temperature: float | None = None,
        add_root_noise: bool = False,
    ) -> RootAnalysis:
        return self.analyze_roots(
            (state,),
            config,
            sample=sample,
            temperature=temperature,
            add_root_noise=add_root_noise,
        )[0]

    def analyze_roots(
        self,
        states: Iterable[GameState],
        config: AppConfig,
        *,
        sample: bool = False,
        temperature: float | None = None,
        add_root_noise: bool = False,
    ) -> list[RootAnalysis]:
        state_list = list(states)
        analyses: list[RootAnalysis | None] = [None] * len(state_list)
        pending: list[tuple[int, _Node, dict[tuple[object, ...], _Node], Player]] = []

        for index, state in enumerate(state_list):
            shortcut = self._shortcut_analysis(state, config)
            if shortcut is not None:
                analyses[index] = shortcut
                continue
            node_cache: dict[tuple[object, ...], _Node] = {}
            root = self._node_for_state(state, node_cache, use_cache=config.search.use_transposition_table)
            pending.append((index, root, node_cache, state.to_play))

        if pending:
            simulations = max(1, config.search.root_simulations)
            wave_size = max(1, config.search.parallel_expansions_per_root)
            roots = [root for _, root, _, _ in pending]
            node_caches = [node_cache for _, _, node_cache, _ in pending]
            root_players = [root_player for _, _, _, root_player in pending]

            add_root_noise_for_wave = add_root_noise
            while any(root.visit_count < simulations for root in roots):
                traces = self._collect_wave_traces(
                    roots=roots,
                    node_caches=node_caches,
                    root_players=root_players,
                    config=config,
                    simulations=simulations,
                    wave_size=wave_size,
                    add_root_noise=add_root_noise_for_wave,
                )
                add_root_noise_for_wave = False
                if not traces:
                    break
                self._prime_pending_inference(traces, config)

                for trace in traces:
                    self._release_virtual_reservation(trace.path_nodes, trace.path_edges)
                    if trace.value is None:
                        if trace.leaf is None:
                            raise RuntimeError("pending search leaf was not resolved")
                        if trace.expand_leaf:
                            trace.value = self._expand_node(
                                trace.leaf,
                                config,
                                root_player=trace.root_player,
                                is_root=trace.leaf is trace.root,
                                add_root_noise=trace.add_root_noise and trace.leaf is trace.root,
                            )
                        else:
                            trace.value = self._evaluate_value(trace.leaf.state, config, trace.root_player)
                    self._backpropagate(trace.path_nodes, trace.path_edges, trace.value)

            for (index, root, _node_cache, _root_player) in pending:
                analyses[index] = self._finalize_root_analysis(
                    root,
                    config,
                    sample=sample,
                    temperature=temperature,
                )

        if any(analysis is None for analysis in analyses):
            raise RuntimeError("guided MCTS did not produce an analysis for every root state")
        return [analysis for analysis in analyses if analysis is not None]

    def _collect_wave_traces(
        self,
        *,
        roots: list[_Node],
        node_caches: list[dict[tuple[object, ...], _Node]],
        root_players: list[Player],
        config: AppConfig,
        simulations: int,
        wave_size: int,
        add_root_noise: bool,
    ) -> list[_PendingSearch]:
        traces: list[_PendingSearch] = []
        reserved_leaf_nodes: set[int] = set()

        for root, node_cache, root_player in zip(roots, node_caches, root_players, strict=True):
            remaining = max(0, simulations - root.visit_count)
            for reservation_index in range(min(wave_size, remaining)):
                trace = self._build_pending_search(
                    root=root,
                    node_cache=node_cache,
                    config=config,
                    root_player=root_player,
                    add_root_noise=add_root_noise and reservation_index == 0,
                )
                if trace.leaf is not None and trace.expand_leaf:
                    leaf_key = id(trace.leaf)
                    if leaf_key in reserved_leaf_nodes:
                        break
                    reserved_leaf_nodes.add(leaf_key)
                self._apply_virtual_reservation(trace.path_nodes, trace.path_edges)
                traces.append(trace)

                if trace.leaf is not None and not trace.leaf.expanded:
                    break

        return traces

    def clear_caches(self) -> None:
        self._policy_cache.clear()
        self._value_cache.clear()
        self._baseline.clear_caches()

    def _shortcut_analysis(self, state: GameState, config: AppConfig) -> RootAnalysis | None:
        if state.is_terminal:
            raise IllegalMoveError("cannot search from a terminal position")
        if not state.stones and state.placements_remaining == 1:
            opening = self._baseline.choose_turn(state, config)
            return RootAnalysis(
                chosen_turn=opening,
                turn_stats=(RootTurnStat(cells=opening.cells, visits=1, prior=1.0, mean_value=0.0),),
                cell_policy=((opening.cells[0], 1.0),),
                simulations=1,
            )

        tactical = self._tactical_override(state, config)
        if tactical is None:
            return None
        cells = tactical.cells
        return RootAnalysis(
            chosen_turn=tactical,
            turn_stats=(RootTurnStat(cells=cells, visits=1, prior=1.0, mean_value=0.0),),
            cell_policy=tuple((cell, round(1.0 / len(cells), 6)) for cell in cells),
            simulations=1,
        )

    def _build_pending_search(
        self,
        *,
        root: _Node,
        node_cache: dict[tuple[object, ...], _Node],
        config: AppConfig,
        root_player: Player,
        add_root_noise: bool,
    ) -> _PendingSearch:
        path_nodes: list[_Node] = [root]
        path_edges: list[_Edge] = []
        node = root

        while True:
            if node.state.is_terminal:
                return _PendingSearch(
                    root=root,
                    node_cache=node_cache,
                    root_player=root_player,
                    path_nodes=path_nodes,
                    path_edges=path_edges,
                    value=self._terminal_value(node.state, root_player),
                )

            if not node.expanded:
                return _PendingSearch(
                    root=root,
                    node_cache=node_cache,
                    root_player=root_player,
                    path_nodes=path_nodes,
                    path_edges=path_edges,
                    leaf=node,
                    expand_leaf=True,
                    add_root_noise=add_root_noise,
                )

            edge = self._select_edge(node, config, root_player=root_player, is_root=node is root)
            if edge is None:
                return _PendingSearch(
                    root=root,
                    node_cache=node_cache,
                    root_player=root_player,
                    path_nodes=path_nodes,
                    path_edges=path_edges,
                    leaf=node,
                    expand_leaf=False,
                )

            if edge.child is None:
                child_state = self._baseline.apply_cells(node.state, edge.cells, config)
                edge.child = self._node_for_state(
                    child_state,
                    node_cache,
                    use_cache=config.search.use_transposition_table,
                )
            node = edge.child
            path_edges.append(edge)
            path_nodes.append(node)

    def _prime_pending_inference(
        self,
        traces: list[_PendingSearch],
        config: AppConfig,
    ) -> None:
        requests: list[tuple[GameState, Player]] = []
        for trace in traces:
            if trace.value is not None or trace.leaf is None:
                continue
            requests.append((trace.leaf.state, trace.leaf.state.to_play))
        self._cache_inference_batch(requests, config)

    def _backpropagate(
        self,
        path_nodes: list[_Node],
        path_edges: list[_Edge],
        value: float,
    ) -> None:
        for visited_node in path_nodes:
            visited_node.visit_count += 1
        for edge in path_edges:
            edge.visit_count += 1
            edge.value_sum += value

    @staticmethod
    def _apply_virtual_reservation(path_nodes: list[_Node], path_edges: list[_Edge]) -> None:
        for visited_node in path_nodes:
            visited_node.visit_count += 1
        for edge in path_edges:
            edge.visit_count += 1

    @staticmethod
    def _release_virtual_reservation(path_nodes: list[_Node], path_edges: list[_Edge]) -> None:
        for visited_node in path_nodes:
            visited_node.visit_count = max(0, visited_node.visit_count - 1)
        for edge in path_edges:
            edge.visit_count = max(0, edge.visit_count - 1)

    def _finalize_root_analysis(
        self,
        root: _Node,
        config: AppConfig,
        *,
        sample: bool,
        temperature: float | None,
    ) -> RootAnalysis:
        simulations = max(1, config.search.root_simulations)
        if not root.edges:
            return RootAnalysis(
                chosen_turn=self._baseline.choose_turn(root.state, config),
                turn_stats=(),
                cell_policy=(),
                simulations=simulations,
            )

        weights = self._root_weights(root.edges, sample=sample, temperature=temperature)
        selected_edge = self._sample_edge(root.edges, weights) if sample else self._best_root_edge(root.edges, config)
        chosen_turn = ScoredTurn(
            cells=selected_edge.cells,
            score=round(selected_edge.mean_value, 4),
            reply_score=round(selected_edge.mean_value, 4),
            evaluation_score=round(selected_edge.prior, 4),
            reason="guided_mcts",
        )
        turn_stats = tuple(
            RootTurnStat(
                cells=edge.cells,
                visits=edge.visit_count,
                prior=round(edge.prior, 6),
                mean_value=round(edge.mean_value, 6),
            )
            for edge in sorted(root.edges, key=lambda item: (-item.visit_count, -item.mean_value, item.cells))
        )
        return RootAnalysis(
            chosen_turn=chosen_turn,
            turn_stats=turn_stats,
            cell_policy=self._cell_policy(root.edges, weights),
            simulations=simulations,
        )

    def _expand_node(
        self,
        node: _Node,
        config: AppConfig,
        *,
        root_player: Player,
        is_root: bool,
        add_root_noise: bool,
    ) -> float:
        if node.state.is_terminal:
            node.expanded = True
            return self._terminal_value(node.state, root_player)

        candidate_turns = self._baseline.enumerate_turns(
            node.state,
            config,
            player=node.state.to_play,
            first_width=config.prototype.first_stone_candidate_limit,
            second_width=config.prototype.second_stone_candidate_limit,
        )
        priors = self._turn_priors(node.state, candidate_turns, config)
        if add_root_noise and priors:
            priors = self._mix_root_noise(priors, config)
        node.edges = [
            _Edge(
                cells=turn.cells,
                prior=prior,
                root_gumbel=self._sample_gumbel() if is_root and self._use_gumbel_root(config) else 0.0,
            )
            for turn, prior in zip(candidate_turns, priors, strict=True)
        ]
        if is_root and self._use_gumbel_root(config):
            node.edges.sort(
                key=lambda edge: (
                    self._root_priority_score(edge, config),
                    edge.prior,
                    edge.cells,
                ),
                reverse=True,
            )
        node.expanded = True
        return self._evaluate_value(node.state, config, root_player)

    def _select_edge(
        self,
        node: _Node,
        config: AppConfig,
        *,
        root_player: Player,
        is_root: bool = False,
    ) -> _Edge | None:
        edges = self._candidate_edges_for_selection(node, config, is_root=is_root)
        if not edges:
            return None

        total_visits = max(1, node.visit_count)
        exploration = config.search.puct_exploration
        maximize = node.state.to_play == root_player
        best: _Edge | None = None
        best_score = float("-inf")
        for edge in edges:
            q_value = edge.mean_value if maximize else -edge.mean_value
            u_value = exploration * edge.prior * math.sqrt(total_visits) / (1 + edge.visit_count)
            score = q_value + u_value
            if is_root and self._use_gumbel_root(config):
                score += self._root_selection_bonus(edge, config)
            if (
                best is None
                or score > best_score
                or (score == best_score and edge.visit_count < best.visit_count)
            ):
                best = edge
                best_score = score
        return best

    def _candidate_edges_for_selection(
        self,
        node: _Node,
        config: AppConfig,
        *,
        is_root: bool,
    ) -> list[_Edge]:
        if not node.edges:
            return []
        if not config.search.use_progressive_widening:
            return node.edges
        limit = max(1, min(len(node.edges), int(math.sqrt(node.visit_count + 1)) + 1))
        if not is_root or not self._use_gumbel_root(config):
            return node.edges[:limit]
        ranked = sorted(
            node.edges,
            key=lambda edge: (
                self._root_priority_score(edge, config),
                edge.prior,
                edge.cells,
            ),
            reverse=True,
        )
        return ranked[:limit]

    def _turn_priors(
        self,
        state: GameState,
        candidate_turns: list[ScoredTurn],
        config: AppConfig,
    ) -> list[float]:
        if not candidate_turns:
            return []
        policy = self._policy_lookup(state, config, state.to_play)
        probabilities = policy.probabilities
        center = policy.center
        radius = policy.radius
        priors = [
            max(
                1e-6,
                sum(
                    float(probabilities[index])
                    if (index := _policy_index(center, radius, cell)) is not None
                    else 1e-6
                    for cell in turn.cells
                )
                / max(len(turn.cells), 1),
            )
            for turn in candidate_turns
        ]
        total = sum(priors)
        if total <= 0.0:
            return [1.0 / len(candidate_turns)] * len(candidate_turns)
        return [prior / total for prior in priors]

    def _policy_scores(
        self,
        state: GameState,
        config: AppConfig,
        perspective: Player,
    ) -> dict[Coord, float]:
        policy = self._policy_lookup(state, config, perspective)
        side = policy.radius * 2 + 1
        min_q = policy.center[0] - policy.radius
        min_r = policy.center[1] - policy.radius
        return {
            (min_q + col, min_r + row): float(policy.probabilities[(row * side) + col])
            for row in range(side)
            for col in range(side)
        }

    def _policy_lookup(
        self,
        state: GameState,
        config: AppConfig,
        perspective: Player,
    ) -> _PolicyLookup:
        key = ("policy", state.signature(), perspective)
        cached = self._policy_cache.get(key)
        if cached is None:
            self._cache_inference(state, config, perspective)
            cached = self._policy_cache[key]
        return cached

    def _evaluate_value(self, state: GameState, config: AppConfig, root_player: Player) -> float:
        if state.is_terminal:
            return self._terminal_value(state, root_player)

        perspective = state.to_play
        key = ("value", state.signature(), perspective)
        cached = self._value_cache.get(key)
        if cached is None:
            self._cache_inference(state, config, perspective)
            cached = self._value_cache[key]
        return cached if perspective == root_player else -cached

    def _cache_inference(
        self,
        state: GameState,
        config: AppConfig,
        perspective: Player,
    ) -> None:
        policy_key = ("policy", state.signature(), perspective)
        value_key = ("value", state.signature(), perspective)
        if policy_key in self._policy_cache and value_key in self._value_cache:
            return

        encoded = encode_state(state, config, perspective=perspective)
        with torch.inference_mode():
            policy_logits, value = self._model(encoded.tensor.unsqueeze(0).to(self._device))
        probs = torch.softmax(policy_logits.squeeze(0), dim=0).cpu()
        self._policy_cache[policy_key] = _PolicyLookup(
            probabilities=probs,
            center=encoded.center,
            radius=encoded.radius,
        )
        self._value_cache[value_key] = float(value.squeeze(0).cpu())

    def _cache_inference_batch(
        self,
        requests: Iterable[tuple[GameState, Player]],
        config: AppConfig,
    ) -> None:
        pending: list[tuple[tuple[object, ...], tuple[object, ...], object]] = []
        seen: set[tuple[object, ...]] = set()

        for state, perspective in requests:
            policy_key = ("policy", state.signature(), perspective)
            value_key = ("value", state.signature(), perspective)
            if policy_key in self._policy_cache and value_key in self._value_cache:
                continue
            dedupe_key = (state.signature(), perspective)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            encoded = encode_state(state, config, perspective=perspective)
            pending.append((policy_key, value_key, encoded))

        if not pending:
            return

        batch = torch.stack([encoded.tensor for _, _, encoded in pending]).to(self._device)
        with torch.inference_mode():
            policy_logits, values = self._model(batch)
        probabilities = torch.softmax(policy_logits, dim=1).cpu()
        values_cpu = values.cpu()

        for index, (policy_key, value_key, encoded) in enumerate(pending):
            self._policy_cache[policy_key] = _PolicyLookup(
                probabilities=probabilities[index],
                center=encoded.center,
                radius=encoded.radius,
            )
            self._value_cache[value_key] = float(values_cpu[index].squeeze())

    def _terminal_value(self, state: GameState, root_player: Player) -> float:
        if state.winner is None:
            return 0.0
        return 1.0 if state.winner == root_player else -1.0

    def _mix_root_noise(self, priors: list[float], config: AppConfig) -> list[float]:
        epsilon = config.search.dirichlet_epsilon
        if epsilon <= 0.0 or len(priors) <= 1:
            return priors
        alpha = max(1e-3, config.search.dirichlet_alpha)
        noise = [self._rng.gammavariate(alpha, 1.0) for _ in priors]
        total_noise = sum(noise)
        if total_noise <= 0.0:
            return priors
        normalized_noise = [value / total_noise for value in noise]
        return [
            ((1.0 - epsilon) * prior) + (epsilon * noisy)
            for prior, noisy in zip(priors, normalized_noise, strict=True)
        ]

    def _root_weights(
        self,
        edges: list[_Edge],
        *,
        sample: bool,
        temperature: float | None,
    ) -> list[float]:
        if not edges:
            return []
        if not sample:
            total = sum(edge.visit_count for edge in edges)
            if total <= 0:
                return [1.0 / len(edges)] * len(edges)
            return [edge.visit_count / total for edge in edges]

        temp = 1.0 if temperature is None else temperature
        if temp <= 1e-6:
            best = self._best_edge(edges)
            return [1.0 if edge is best else 0.0 for edge in edges]

        weights = [max(edge.visit_count, 1) ** (1.0 / temp) for edge in edges]
        total = sum(weights)
        return [weight / total for weight in weights]

    def _sample_edge(self, edges: list[_Edge], weights: list[float]) -> _Edge:
        threshold = self._rng.random()
        cumulative = 0.0
        for edge, weight in zip(edges, weights, strict=True):
            cumulative += weight
            if threshold <= cumulative:
                return edge
        return edges[-1]

    @staticmethod
    def _best_edge(edges: list[_Edge]) -> _Edge:
        return max(edges, key=lambda edge: (edge.visit_count, edge.mean_value, edge.prior, edge.cells))

    def _best_root_edge(self, edges: list[_Edge], config: AppConfig) -> _Edge:
        if not self._use_gumbel_root(config):
            return self._best_edge(edges)
        return max(
            edges,
            key=lambda edge: (
                edge.visit_count,
                edge.mean_value,
                self._root_priority_score(edge, config),
                edge.prior,
                edge.cells,
            ),
        )

    @staticmethod
    def _cell_policy(edges: list[_Edge], weights: list[float]) -> tuple[tuple[Coord, float], ...]:
        mass: dict[Coord, float] = {}
        for edge, weight in zip(edges, weights, strict=True):
            share = weight / max(len(edge.cells), 1)
            for cell in edge.cells:
                mass[cell] = mass.get(cell, 0.0) + share
        total = sum(mass.values())
        if total <= 0.0:
            return ()
        return tuple(
            (cell, round(value / total, 6))
            for cell, value in sorted(mass.items(), key=lambda item: (-item[1], item[0]))
        )

    @staticmethod
    def _node_for_state(
        state: GameState,
        node_cache: dict[tuple[object, ...], _Node],
        *,
        use_cache: bool,
    ) -> _Node:
        if not use_cache:
            return _Node(state=state)
        key = state.signature()
        cached = node_cache.get(key)
        if cached is None:
            cached = _Node(state=state)
            node_cache[key] = cached
        return cached

    def _tactical_override(self, state: GameState, config: AppConfig) -> ScoredTurn | None:
        if config.search.tactical_solver != "threat_search":
            return None

        immediate = self._baseline._find_immediate_turns(  # noqa: SLF001
            state,
            config,
            state.to_play,
            state.placements_remaining,
        )
        if immediate:
            return ScoredTurn(
                cells=immediate[0],
                score=config.heuristic.terminal_score,
                reply_score=0.0,
                evaluation_score=config.heuristic.terminal_score,
                reason="mcts_immediate_win",
            )

        opponent = state.opponent()
        opponent_immediate = self._baseline._find_immediate_turns(  # noqa: SLF001
            state,
            config,
            opponent,
            config.game.turn_placements,
        )
        if not opponent_immediate:
            return None

        defenses = self._baseline._defensive_turns(  # noqa: SLF001
            state,
            config,
            state.to_play,
            opponent_immediate,
        )
        if not defenses:
            return None
        return self._baseline._score_turns(  # noqa: SLF001
            state,
            config,
            state.to_play,
            defenses,
            reason="mcts_forced_defense",
        )

    @staticmethod
    def _use_gumbel_root(config: AppConfig) -> bool:
        return config.search.root_policy_mode == "gumbel"

    @staticmethod
    def _root_priority_score(edge: _Edge, config: AppConfig) -> float:
        scale = max(0.0, config.search.root_gumbel_scale)
        return math.log(max(edge.prior, 1e-6)) + (scale * edge.root_gumbel)

    @staticmethod
    def _root_selection_bonus(edge: _Edge, config: AppConfig) -> float:
        scale = max(0.0, config.search.root_gumbel_scale)
        return (scale * edge.root_gumbel) / (1 + edge.visit_count)

    def _sample_gumbel(self) -> float:
        uniform = min(max(self._rng.random(), 1e-9), 1.0 - 1e-9)
        return -math.log(-math.log(uniform))

def _select_device(config: AppConfig) -> torch.device:
    if config.runtime.preferred_device == "cuda" and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _policy_index(center: Coord, radius: int, cell: Coord) -> int | None:
    side = radius * 2 + 1
    min_q = center[0] - radius
    min_r = center[1] - radius
    col = cell[0] - min_q
    row = cell[1] - min_r
    if row < 0 or row >= side or col < 0 or col >= side:
        return None
    return (row * side) + col
