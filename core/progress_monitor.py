from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from typing import Callable, Iterable, List

from .types import CommandResult, FFmpegError

TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+\.?\d*)")
FRAME_RE = re.compile(r"frame=\s*(\d+)")
SPEED_RE = re.compile(r"speed=\s*([\d\.]+)x")


@dataclass(slots=True)
class ProgressUpdate:
    progress: float | None
    current_time: float | None
    current_frame: int | None
    speed: float | None
    eta: float | None
    raw: str
    done: bool = False
    return_code: int | None = None


def _parse_timecode(match: re.Match[str]) -> float:
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def run_with_progress(
    command: List[str],
    total_duration: float | None,
    callback: Callable[[ProgressUpdate], None],
    *,
    check: bool = True,
) -> CommandResult:
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        encoding="utf-8",
        errors="ignore",
        bufsize=1,
    )

    start_time = time.time()
    last_progress = 0.0

    if process.stderr is None:
        raise RuntimeError("stderr pipe is required for progress monitoring")

    for line in process.stderr:
        progress = _create_progress_update(line.rstrip(), total_duration, start_time)
        if progress.progress is not None:
            last_progress = progress.progress
        callback(progress)

    return_code = process.wait()
    final_update = ProgressUpdate(
        progress=1.0 if return_code == 0 else last_progress,
        current_time=total_duration if return_code == 0 else None,
        current_frame=None,
        speed=None,
        eta=0 if return_code == 0 else None,
        raw=f"FFmpeg exited with code {return_code}",
        done=True,
        return_code=return_code,
    )
    callback(final_update)

    if check and return_code != 0:
        raise FFmpegError(
            f"FFmpeg exited with code {return_code}",
            command,
            stdout="",
            stderr="",
        )

    return CommandResult(return_code, "", "", command)


def _create_progress_update(line: str, total_duration: float | None, start_time: float) -> ProgressUpdate:
    current_time = None
    progress_value = None
    eta = None
    speed_val = None
    frame_val = None

    if match := TIME_RE.search(line):
        current_time = _parse_timecode(match)
        if total_duration and total_duration > 0:
            progress_value = min(current_time / total_duration, 1.0)

    if match := FRAME_RE.search(line):
        frame_val = int(match.group(1))

    if match := SPEED_RE.search(line):
        try:
            speed_val = float(match.group(1))
        except ValueError:
            speed_val = None

    if progress_value is not None:
        if speed_val and speed_val > 0 and total_duration:
            eta = max((total_duration - (current_time or 0)) / speed_val, 0)
        else:
            elapsed = time.time() - start_time
            if progress_value > 0:
                eta = max(elapsed / progress_value * (1 - progress_value), 0)

    return ProgressUpdate(
        progress=progress_value,
        current_time=current_time,
        current_frame=frame_val,
        speed=speed_val,
        eta=eta,
        raw=line,
    )
