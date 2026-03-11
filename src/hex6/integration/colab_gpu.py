"""Helpers for inspecting and gating Colab GPU runtimes."""

from __future__ import annotations

from dataclasses import dataclass
import shutil
import subprocess


GPU_TIER_ORDER = ("H100", "A100", "V100", "A10G", "L4", "T4", "P100", "K80", "OTHER")
GPU_TIER_RANK = {tier: index for index, tier in enumerate(GPU_TIER_ORDER)}


@dataclass(frozen=True)
class GpuInfo:
    index: int
    name: str
    tier: str
    memory_total_mb: float | None


def canonicalize_gpu_tier(name: str) -> str:
    normalized = name.upper()
    for tier in GPU_TIER_ORDER[:-1]:
        if tier in normalized:
            return tier
    return "OTHER"


def parse_nvidia_smi_rows(text: str) -> list[GpuInfo]:
    rows: list[GpuInfo] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 3:
            continue
        try:
            index = int(parts[0])
        except ValueError:
            continue
        memory_total_mb: float | None
        try:
            memory_total_mb = float(parts[2])
        except ValueError:
            memory_total_mb = None
        rows.append(
            GpuInfo(
                index=index,
                name=parts[1],
                tier=canonicalize_gpu_tier(parts[1]),
                memory_total_mb=memory_total_mb,
            )
        )
    return rows


def detect_runtime_gpus() -> list[GpuInfo]:
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi is None:
        return []
    completed = subprocess.run(
        [
            nvidia_smi,
            "--query-gpu=index,name,memory.total",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return []
    return parse_nvidia_smi_rows(completed.stdout)


def gpu_meets_minimum(gpu: GpuInfo, minimum_tier: str) -> bool:
    minimum = minimum_tier.upper()
    if minimum not in GPU_TIER_RANK:
        raise ValueError(f"unsupported minimum GPU tier: {minimum_tier}")
    return GPU_TIER_RANK[gpu.tier] <= GPU_TIER_RANK[minimum]


def format_gpu_report(gpus: list[GpuInfo]) -> str:
    if not gpus:
        return "No NVIDIA GPU detected."
    parts: list[str] = []
    for gpu in gpus:
        memory_text = "unknown"
        if gpu.memory_total_mb is not None:
            memory_text = f"{gpu.memory_total_mb:.0f} MiB"
        parts.append(f"GPU {gpu.index}: {gpu.name} [tier={gpu.tier}, memory={memory_text}]")
    return "\n".join(parts)
