from hex6.integration.colab_gpu import (
    canonicalize_gpu_tier,
    format_gpu_report,
    gpu_meets_minimum,
    parse_nvidia_smi_rows,
)


def test_canonicalize_gpu_tier_recognizes_known_colab_shapes() -> None:
    assert canonicalize_gpu_tier("NVIDIA A100-SXM4-40GB") == "A100"
    assert canonicalize_gpu_tier("Tesla V100-SXM2-16GB") == "V100"
    assert canonicalize_gpu_tier("NVIDIA L4") == "L4"
    assert canonicalize_gpu_tier("Tesla T4") == "T4"


def test_parse_nvidia_smi_rows_builds_gpu_info_records() -> None:
    rows = parse_nvidia_smi_rows("0, Tesla T4, 15360\n1, NVIDIA A100-SXM4-40GB, 40960\n")
    assert len(rows) == 2
    assert rows[0].tier == "T4"
    assert rows[1].tier == "A100"
    assert rows[1].memory_total_mb == 40960.0


def test_gpu_meets_minimum_uses_expected_ordering() -> None:
    gpu = parse_nvidia_smi_rows("0, Tesla V100-SXM2-16GB, 16384\n")[0]
    assert gpu_meets_minimum(gpu, "T4")
    assert gpu_meets_minimum(gpu, "V100")
    assert not gpu_meets_minimum(gpu, "A100")


def test_format_gpu_report_renders_human_readable_text() -> None:
    report = format_gpu_report(parse_nvidia_smi_rows("0, Tesla T4, 15360\n"))
    assert "Tesla T4" in report
    assert "tier=T4" in report
