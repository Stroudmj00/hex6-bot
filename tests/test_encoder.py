import torch

from hex6.config import load_config
from hex6.game import GameState
from hex6.nn import cell_to_policy_index, encode_state


def test_encode_state_marks_stones_last_move_and_constant_planes() -> None:
    config = load_config("configs/fast.toml")
    state = GameState.initial(config.game)
    state = state.apply_placement((0, 0), config.game)

    encoded = encode_state(state, config, perspective="x")

    assert encoded.tensor.shape == (6, 13, 13)
    assert torch.all(encoded.tensor[3] == 1.0)
    assert torch.all(encoded.tensor[4] == 1.0)
    assert torch.all(encoded.tensor[5] == 1.0)

    x_index = cell_to_policy_index(encoded, (0, 0))

    assert x_index is not None

    side = config.model.board_crop_radius * 2 + 1
    x_row, x_col = divmod(x_index, side)

    assert encoded.tensor[0, x_row, x_col] == 1.0
    assert encoded.tensor[2, x_row, x_col] == 1.0


def test_encode_state_uses_last_move_when_history_is_not_recorded() -> None:
    config = load_config("configs/fast.toml")
    state = GameState.initial(config.game)
    state = state.apply_placement((0, 0), config.game, record_history=False)

    encoded = encode_state(state, config, perspective="x")
    index = cell_to_policy_index(encoded, (0, 0))

    assert index is not None
    side = config.model.board_crop_radius * 2 + 1
    row, col = divmod(index, side)
    assert state.move_history == ()
    assert state.last_move == (0, 0)
    assert encoded.tensor[2, row, col] == 1.0
