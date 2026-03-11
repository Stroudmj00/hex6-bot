"""Lightweight process and GPU resource sampling for training runs."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import platform
import subprocess
import threading
import time
from typing import Any

import torch


def _round_or_none(value: float | int | None, digits: int = 3) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _try_parse_float(raw: str) -> float | None:
    text = raw.strip()
    if not text or text.upper() in {"N/A", "[N/A]"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _windows_working_set_bytes() -> int | None:
    try:
        import ctypes
        from ctypes import byref, c_size_t, sizeof
        from ctypes import wintypes

        class _ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", c_size_t),
                ("WorkingSetSize", c_size_t),
                ("QuotaPeakPagedPoolUsage", c_size_t),
                ("QuotaPagedPoolUsage", c_size_t),
                ("QuotaPeakNonPagedPoolUsage", c_size_t),
                ("QuotaNonPagedPoolUsage", c_size_t),
                ("PagefileUsage", c_size_t),
                ("PeakPagefileUsage", c_size_t),
            ]

        psapi = ctypes.WinDLL("Psapi.dll")
        kernel32 = ctypes.WinDLL("Kernel32.dll")
        get_process_memory_info = psapi.GetProcessMemoryInfo
        get_process_memory_info.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        get_process_memory_info.restype = wintypes.BOOL
        handle = kernel32.GetCurrentProcess()
        counters = _ProcessMemoryCounters()
        counters.cb = sizeof(counters)
        if not get_process_memory_info(handle, byref(counters), counters.cb):
            return None
        return int(counters.WorkingSetSize)
    except Exception:
        return None


def _linux_working_set_bytes() -> int | None:
    status_path = Path("/proc/self/status")
    if not status_path.exists():
        return None
    try:
        for line in status_path.read_text(encoding="ascii").splitlines():
            if line.startswith("VmRSS:"):
                parts = line.split()
                if len(parts) >= 2:
                    return int(parts[1]) * 1024
    except Exception:
        return None
    return None


def _working_set_bytes() -> int | None:
    if os.name == "nt":
        return _windows_working_set_bytes()
    rss = _linux_working_set_bytes()
    if rss is not None:
        return rss
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        factor = 1 if platform.system() == "Darwin" else 1024
        return int(usage.ru_maxrss * factor)
    except Exception:
        return None


def _nvidia_smi_creationflags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _query_nvidia_smi(device_index: int | None) -> dict[str, float | int | None]:
    query = [
        "nvidia-smi",
        "--query-gpu=index,utilization.gpu,memory.used,memory.total,power.draw",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(
            query,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2.0,
            check=True,
            creationflags=_nvidia_smi_creationflags(),
        )
    except Exception:
        return {
            "gpu_device_index": device_index,
            "gpu_util_percent": None,
            "gpu_memory_used_mb": None,
            "gpu_memory_total_mb": None,
            "gpu_power_watts": None,
        }

    rows: list[dict[str, float | int | None]] = []
    for line in completed.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 5:
            continue
        row_index = None
        try:
            row_index = int(parts[0])
        except ValueError:
            row_index = None
        rows.append(
            {
                "gpu_device_index": row_index,
                "gpu_util_percent": _try_parse_float(parts[1]),
                "gpu_memory_used_mb": _try_parse_float(parts[2]),
                "gpu_memory_total_mb": _try_parse_float(parts[3]),
                "gpu_power_watts": _try_parse_float(parts[4]),
            }
        )
    if not rows:
        return {
            "gpu_device_index": device_index,
            "gpu_util_percent": None,
            "gpu_memory_used_mb": None,
            "gpu_memory_total_mb": None,
            "gpu_power_watts": None,
        }
    if device_index is None:
        return rows[0]
    for row in rows:
        if row["gpu_device_index"] == device_index:
            return row
    return rows[0]


def _mean_and_peak(samples: list[dict[str, Any]], key: str) -> tuple[float | None, float | None]:
    values = [float(sample[key]) for sample in samples if sample.get(key) is not None]
    if not values:
        return None, None
    return _round_or_none(sum(values) / len(values)), _round_or_none(max(values))


def summarize_resource_samples(
    samples: list[dict[str, Any]],
    *,
    poll_seconds: float,
    pid: int,
    device: str,
) -> dict[str, Any]:
    duration_seconds = None
    if len(samples) >= 2:
        duration_seconds = round(float(samples[-1]["wall_seconds"]) - float(samples[0]["wall_seconds"]), 3)

    avg_cpu, peak_cpu = _mean_and_peak(samples, "process_cpu_percent")
    avg_cpu_cores, peak_cpu_cores = _mean_and_peak(samples, "process_cpu_cores_used")
    avg_rss, peak_rss = _mean_and_peak(samples, "rss_mb")
    avg_gpu_util, peak_gpu_util = _mean_and_peak(samples, "gpu_util_percent")
    avg_gpu_mem, peak_gpu_mem = _mean_and_peak(samples, "gpu_memory_used_mb")
    avg_gpu_power, peak_gpu_power = _mean_and_peak(samples, "gpu_power_watts")
    avg_cuda_allocated, peak_cuda_allocated = _mean_and_peak(samples, "cuda_memory_allocated_mb")
    avg_cuda_reserved, peak_cuda_reserved = _mean_and_peak(samples, "cuda_memory_reserved_mb")
    _avg_max_cuda_allocated, peak_max_cuda_allocated = _mean_and_peak(samples, "cuda_max_memory_allocated_mb")
    _avg_max_cuda_reserved, peak_max_cuda_reserved = _mean_and_peak(samples, "cuda_max_memory_reserved_mb")

    return {
        "pid": pid,
        "device": device,
        "poll_seconds": poll_seconds,
        "sample_count": len(samples),
        "duration_seconds": duration_seconds,
        "avg_process_cpu_percent": avg_cpu,
        "peak_process_cpu_percent": peak_cpu,
        "avg_process_cpu_cores_used": avg_cpu_cores,
        "peak_process_cpu_cores_used": peak_cpu_cores,
        "avg_rss_mb": avg_rss,
        "peak_rss_mb": peak_rss,
        "avg_gpu_util_percent": avg_gpu_util,
        "peak_gpu_util_percent": peak_gpu_util,
        "avg_gpu_memory_used_mb": avg_gpu_mem,
        "peak_gpu_memory_used_mb": peak_gpu_mem,
        "avg_gpu_power_watts": avg_gpu_power,
        "peak_gpu_power_watts": peak_gpu_power,
        "avg_cuda_memory_allocated_mb": avg_cuda_allocated,
        "peak_cuda_memory_allocated_mb": peak_cuda_allocated,
        "avg_cuda_memory_reserved_mb": avg_cuda_reserved,
        "peak_cuda_memory_reserved_mb": peak_cuda_reserved,
        "peak_cuda_max_memory_allocated_mb": peak_max_cuda_allocated,
        "peak_cuda_max_memory_reserved_mb": peak_max_cuda_reserved,
    }


@dataclass
class ResourceMonitor:
    enabled: bool
    poll_seconds: float
    device: torch.device

    def __post_init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._samples: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._started_at: float | None = None
        self._previous_cpu_time: float | None = None
        self._previous_wall_time: float | None = None
        self._cpu_count = max(os.cpu_count() or 1, 1)
        self._pid = os.getpid()
        self._device_index = None
        if self.device.type == "cuda" and torch.cuda.is_available():
            self._device_index = torch.cuda.current_device()
        self._final_payload: dict[str, Any] | None = None

    def start(self) -> None:
        if not self.enabled:
            return
        self._started_at = time.perf_counter()
        self._previous_cpu_time = time.process_time()
        self._previous_wall_time = self._started_at
        if self.device.type == "cuda" and torch.cuda.is_available():
            try:
                torch.cuda.reset_peak_memory_stats(self.device)
            except Exception:
                pass
        self._record_sample()
        self._thread = threading.Thread(target=self._run, name="hex6-resource-monitor", daemon=True)
        self._thread.start()

    def stop(self, *, output_path: Path | None = None) -> dict[str, Any]:
        if not self.enabled:
            return {}
        if self._final_payload is not None:
            if output_path is not None:
                output_path.write_text(json.dumps(self._final_payload, indent=2), encoding="ascii")
            return self._final_payload
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(self.poll_seconds * 2.0, 1.0))
        self._record_sample()
        with self._lock:
            samples = list(self._samples)
        self._final_payload = {
            "summary": summarize_resource_samples(
                samples,
                poll_seconds=self.poll_seconds,
                pid=self._pid,
                device=str(self.device),
            ),
            "samples": samples,
        }
        if output_path is not None:
            output_path.write_text(json.dumps(self._final_payload, indent=2), encoding="ascii")
        return self._final_payload

    def _run(self) -> None:
        while not self._stop_event.wait(self.poll_seconds):
            self._record_sample()

    def _record_sample(self) -> None:
        wall_now = time.perf_counter()
        cpu_now = time.process_time()
        cpu_percent = None
        cpu_cores_used = None
        if self._previous_cpu_time is not None and self._previous_wall_time is not None:
            wall_delta = wall_now - self._previous_wall_time
            cpu_delta = cpu_now - self._previous_cpu_time
            if wall_delta > 0:
                cpu_cores_used = _round_or_none(cpu_delta / wall_delta)
                cpu_percent = _round_or_none((cpu_delta / (wall_delta * self._cpu_count)) * 100.0)
        self._previous_cpu_time = cpu_now
        self._previous_wall_time = wall_now

        rss_bytes = _working_set_bytes()
        sample: dict[str, Any] = {
            "wall_seconds": _round_or_none((wall_now - self._started_at) if self._started_at is not None else 0.0),
            "process_cpu_seconds": _round_or_none(cpu_now),
            "process_cpu_percent": cpu_percent,
            "process_cpu_cores_used": cpu_cores_used,
            "rss_mb": _round_or_none(rss_bytes / (1024 * 1024)) if rss_bytes is not None else None,
        }

        if self.device.type == "cuda" and torch.cuda.is_available():
            try:
                sample["cuda_memory_allocated_mb"] = _round_or_none(
                    torch.cuda.memory_allocated(self.device) / (1024 * 1024)
                )
                sample["cuda_memory_reserved_mb"] = _round_or_none(
                    torch.cuda.memory_reserved(self.device) / (1024 * 1024)
                )
                sample["cuda_max_memory_allocated_mb"] = _round_or_none(
                    torch.cuda.max_memory_allocated(self.device) / (1024 * 1024)
                )
                sample["cuda_max_memory_reserved_mb"] = _round_or_none(
                    torch.cuda.max_memory_reserved(self.device) / (1024 * 1024)
                )
            except Exception:
                sample["cuda_memory_allocated_mb"] = None
                sample["cuda_memory_reserved_mb"] = None
                sample["cuda_max_memory_allocated_mb"] = None
                sample["cuda_max_memory_reserved_mb"] = None
            sample.update(_query_nvidia_smi(self._device_index))
        else:
            sample["cuda_memory_allocated_mb"] = None
            sample["cuda_memory_reserved_mb"] = None
            sample["cuda_max_memory_allocated_mb"] = None
            sample["cuda_max_memory_reserved_mb"] = None
            sample["gpu_device_index"] = None
            sample["gpu_util_percent"] = None
            sample["gpu_memory_used_mb"] = None
            sample["gpu_memory_total_mb"] = None
            sample["gpu_power_watts"] = None

        with self._lock:
            self._samples.append(sample)
