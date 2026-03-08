from pathlib import Path

from hex6.eval.search_matrix import run_search_variant_matrix


def test_run_search_variant_matrix_reports_progress(tmp_path: Path) -> None:
    matrix_path = tmp_path / "matrix.toml"
    base_config = (Path.cwd() / "configs" / "fast.toml").resolve().as_posix()
    matrix_path.write_text(
        "\n".join(
            [
                f'base_config = "{base_config}"',
                "games = 1",
                "",
                "[[variants]]",
                'name = "reply_depth"',
                'description = "Test-only search tweak."',
                "",
                "[variants.overrides.search]",
                "shallow_reply_width = 2",
                "",
            ]
        ),
        encoding="ascii",
    )

    events: list[dict[str, object]] = []
    summary = run_search_variant_matrix(
        matrix_path,
        output_dir=tmp_path / "search_matrix",
        progress_callback=events.append,
    )

    assert summary["best_variant"] == "reply_depth"
    assert events[0]["stage"] == "search_matrix"
    assert events[0]["completed_variants"] == 0
    assert events[-1]["completed_variants"] == 1
    assert events[-1]["current_variant"] == "reply_depth"
    assert (tmp_path / "search_matrix" / "summary.json").exists()
