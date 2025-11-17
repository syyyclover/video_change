from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from .ffmpeg_wrapper import FFmpegWrapper, InputSpec
from .progress_monitor import ProgressUpdate
from .types import CommandResult

ProgressCallback = Callable[[ProgressUpdate], None]


class FFmpegService:
    """High-level façade that drives FFmpeg via subprocess with optional progress reporting."""

    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe") -> None:
        self.wrapper = FFmpegWrapper(ffmpeg_path, ffprobe_path)

    def convert(
        self,
        input_file: str | Path,
        output_file: str | Path,
        params: Mapping[str, object] | None = None,
        *,
        duration: float | None = None,
        callback: ProgressCallback | None = None,
    ) -> CommandResult:
        if callback:
            return self.wrapper.run_with_progress(input_file, output_file, params, duration, callback)
        return self.wrapper.run(input_file, output_file, params)

    def merge(
        self,
        inputs: Sequence[InputSpec],
        output_file: str | Path,
        params: Mapping[str, object] | None = None,
        *,
        total_duration: float | None = None,
        callback: ProgressCallback | None = None,
    ) -> CommandResult:
        if callback:
            return self.wrapper.merge_with_progress(inputs, output_file, params, total_duration, callback)
        return self.wrapper.merge_files(inputs, output_file, params)

    def probe(self, media_path: str | Path) -> dict:
        return self.wrapper.probe(media_path)
