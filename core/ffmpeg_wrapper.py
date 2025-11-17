from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path
from typing import Callable, Iterable, List, Mapping, Sequence, Union

from . import progress_monitor
from .progress_monitor import ProgressUpdate
from .types import CommandResult, FFmpegError


InputSpec = Union[str, Path, Mapping[str, object]]


class FFmpegWrapper:
    """Utility facade for building and executing basic FFmpeg commands."""

    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe") -> None:
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def build_command(
        self,
        input_file: str | Path,
        output_file: str | Path,
        params: Mapping[str, object] | None = None,
    ) -> List[str]:
        params = dict(params or {})
        cmd: List[str] = [self.ffmpeg_path, "-hide_banner"]
        overwrite = params.get("overwrite", True)
        cmd.append("-y" if overwrite else "-n")

        # Input timing controls
        if (start := params.get("start")) is not None:
            cmd.extend(["-ss", str(start)])

        cmd.extend(["-i", str(input_file)])

        if (end := params.get("end")) is not None:
            cmd.extend(["-to", str(end)])

        video_params = params.get("video") or {}
        audio_params = params.get("audio") or {}

        self._apply_video_params(cmd, video_params)
        self._apply_audio_params(cmd, audio_params)

        extra = params.get("extra_args")
        if isinstance(extra, (list, tuple)):
            cmd.extend(str(arg) for arg in extra)

        cmd.append(str(output_file))
        return cmd

    def build_merge_command(
        self,
        inputs: Sequence[InputSpec],
        output_file: str | Path,
        params: Mapping[str, object] | None = None,
    ) -> List[str]:
        if len(inputs) < 2:
            raise ValueError("Merging requires at least two input files.")

        params = dict(params or {})
        specs = [self._normalize_input_spec(item) for item in inputs]

        cmd: List[str] = [self.ffmpeg_path, "-hide_banner"]
        overwrite = params.get("overwrite", True)
        cmd.append("-y" if overwrite else "-n")

        for spec in specs:
            if spec.get("start") is not None:
                cmd.extend(["-ss", str(spec["start"])])
            cmd.extend(["-i", spec["path"]])
            if spec.get("end") is not None:
                cmd.extend(["-to", str(spec["end"])])

        video_params = params.get("video") or {}
        audio_params = params.get("audio") or {}
        target_width, target_height = self._resolve_target_resolution(specs, video_params)
        audio_enabled = any(spec.get("has_audio", True) for spec in specs)
        audio_rate = int(audio_params.get("sample_rate") or 48000)

        filter_graph, video_label, audio_label = self._build_concat_filter(
            specs,
            target_width,
            target_height,
            audio_enabled,
            audio_rate,
        )
        cmd.extend(["-filter_complex", filter_graph, "-map", video_label])
        if audio_label:
            cmd.extend(["-map", audio_label])

        self._apply_video_params(cmd, video_params, allow_filters=False)
        self._apply_audio_params(cmd, audio_params)

        extra = params.get("extra_args")
        if isinstance(extra, (list, tuple)):
            cmd.extend(str(arg) for arg in extra)

        cmd.append(str(output_file))
        return cmd

    def run(
        self,
        input_file: str | Path,
        output_file: str | Path,
        params: Mapping[str, object] | None = None,
        *,
        check: bool = True,
    ) -> CommandResult:
        command = self.build_command(input_file, output_file, params)
        return self._execute(command, check=check)

    def run_with_progress(
        self,
        input_file: str | Path,
        output_file: str | Path,
        params: Mapping[str, object] | None,
        total_duration: float | None,
        callback: Callable[[ProgressUpdate], None],
        *,
        check: bool = True,
    ) -> CommandResult:
        command = self.build_command(input_file, output_file, params)
        return progress_monitor.run_with_progress(
            command,
            total_duration,
            callback,
            check=check,
        )

    def merge_files(
        self,
        inputs: Sequence[InputSpec],
        output_file: str | Path,
        params: Mapping[str, object] | None = None,
        *,
        check: bool = True,
    ) -> CommandResult:
        command = self.build_merge_command(inputs, output_file, params)
        return self._execute(command, check=check)

    def merge_with_progress(
        self,
        inputs: Sequence[InputSpec],
        output_file: str | Path,
        params: Mapping[str, object] | None,
        total_duration: float | None,
        callback: Callable[[ProgressUpdate], None],
        *,
        check: bool = True,
    ) -> CommandResult:
        command = self.build_merge_command(inputs, output_file, params)
        return progress_monitor.run_with_progress(
            command,
            total_duration,
            callback,
            check=check,
        )

    def probe(self, media_path: str | Path) -> dict:
        """Return ffprobe JSON output for the provided media file."""
        command = [
            self.ffprobe_path,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(media_path),
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=False,
        )
        if completed.returncode != 0:
            raise FFmpegError(
                f"ffprobe failed with code {completed.returncode}",
                command,
                completed.stdout,
                completed.stderr,
            )
        return json.loads(completed.stdout or "{}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _apply_video_params(
        self,
        cmd: List[str],
        video: Mapping[str, object],
        *,
        allow_filters: bool = True,
    ) -> None:
        codec = video.get("codec")
        if codec:
            cmd.extend(["-c:v", str(codec)])

        crf = video.get("crf")
        bitrate = video.get("bitrate")
        if crf is not None:
            cmd.extend(["-crf", str(crf)])
        elif bitrate:
            cmd.extend(["-b:v", str(bitrate)])

        if (fps := video.get("fps")) is not None:
            cmd.extend(["-r", str(fps)])
        if (resolution := video.get("resolution")):
            cmd.extend(["-s", str(resolution)])
        if (preset := video.get("preset")):
            cmd.extend(["-preset", str(preset)])
        if (tune := video.get("tune")):
            cmd.extend(["-tune", str(tune)])

        if allow_filters:
            if filters := self._build_video_filters(video):
                cmd.extend(["-vf", filters])

    def _apply_audio_params(self, cmd: List[str], audio: Mapping[str, object]) -> None:
        codec = audio.get("codec")
        if codec:
            cmd.extend(["-c:a", str(codec)])
        if (bitrate := audio.get("bitrate")):
            cmd.extend(["-b:a", str(bitrate)])
        if (sample_rate := audio.get("sample_rate")):
            cmd.extend(["-ar", str(sample_rate)])
        if (channels := audio.get("channels")):
            cmd.extend(["-ac", str(channels)])
        if afilters := self._build_audio_filters(audio):
            cmd.extend(["-af", afilters])

    def _build_video_filters(self, video: Mapping[str, object]) -> str:
        filters: list[str] = []
        crop = video.get("crop") or {}
        if crop:
            w = crop.get("w")
            h = crop.get("h")
            if w and h:
                x = crop.get("x", 0)
                y = crop.get("y", 0)
                filters.append(f"crop={w}:{h}:{x}:{y}")

        rotate = video.get("rotate")
        if rotate in {90, 180, 270}:
            mapping = {90: "transpose=1", 180: "transpose=2,transpose=2", 270: "transpose=2"}
            filters.append(mapping[int(rotate)])
        elif rotate and rotate % 360 != 0:
            # non right-angle rotation uses radians in FFmpeg
            filters.append(f"rotate={float(rotate)}*PI/180")

        color = video.get("color") or {}
        if color:
            brightness = float(color.get("brightness", 0)) / 100
            contrast = float(color.get("contrast", 0)) / 100 + 1
            saturation = float(color.get("saturation", 0)) / 100 + 1
            filters.append(f"eq=brightness={brightness}:contrast={contrast}:saturation={saturation}")

        return ",".join(filters)

    def _build_audio_filters(self, audio: Mapping[str, object]) -> str:
        filters: list[str] = []
        if audio.get("loudnorm"):
            target = audio["loudnorm"].get("target", -16)
            true_peak = audio["loudnorm"].get("true_peak", -1)
            filters.append(f"loudnorm=I={target}:TP={true_peak}:LRA=11")
        if audio.get("denoise"):
            strength = audio["denoise"].get("strength", 12)
            filters.append(f"afftdn=nr={strength}")
        return ",".join(filters)

    def _resolve_target_resolution(
        self,
        specs: Sequence[Mapping[str, object]],
        video_params: Mapping[str, object],
    ) -> tuple[int, int]:
        resolution = video_params.get("resolution")
        if resolution and isinstance(resolution, str) and resolution.lower() != "auto":
            try:
                width_str, height_str = resolution.lower().split("x")
                return int(width_str), int(height_str)
            except (ValueError, AttributeError):
                pass
        for spec in specs:
            if spec.get("width") and spec.get("height"):
                return int(spec["width"]), int(spec["height"])
        return 1920, 1080

    def _build_concat_filter(
        self,
        specs: Sequence[Mapping[str, object]],
        width: int,
        height: int,
        audio_enabled: bool,
        audio_rate: int,
    ) -> tuple[str, str, str | None]:
        parts: list[str] = []
        video_labels: list[str] = []
        audio_labels: list[str] = []

        for idx, spec in enumerate(specs):
            v_label = f"[v{idx}]"
            video_labels.append(v_label)
            parts.append(
                f"[{idx}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,setpts=PTS-STARTPTS{v_label}"
            )
            if audio_enabled:
                a_label = f"[a{idx}]"
                audio_labels.append(a_label)
                if spec.get("has_audio", True):
                    parts.append(f"[{idx}:a]aresample=async=1:first_pts=0{a_label}")
                else:
                    parts.append(
                        f"anullsrc=channel_layout=stereo:sample_rate={audio_rate},asetpts=PTS-STARTPTS{a_label}"
                    )

        concat_inputs = "".join(video_labels + (audio_labels if audio_enabled else []))
        concat_line = (
            f"{concat_inputs}concat=n={len(specs)}:v=1:a={1 if audio_enabled else 0}[vout]"
            + ("[aout]" if audio_enabled else "")
        )
        parts.append(concat_line)
        return ";".join(parts), "[vout]", "[aout]" if audio_enabled else None

    def _normalize_input_spec(self, item: InputSpec) -> dict:
        if isinstance(item, (str, Path)):
            return {"path": str(item)}
        if isinstance(item, Mapping):
            if "path" not in item:
                raise ValueError("Input mapping must include 'path'.")
            normalized = {"path": str(item["path"])}
            if item.get("start") is not None:
                normalized["start"] = item["start"]
            if item.get("end") is not None:
                normalized["end"] = item["end"]
            if item.get("width") is not None:
                normalized["width"] = item["width"]
            if item.get("height") is not None:
                normalized["height"] = item["height"]
            if item.get("has_audio") is not None:
                normalized["has_audio"] = bool(item["has_audio"])
            return normalized
        raise TypeError(f"Unsupported input type: {type(item)!r}")

    def _execute(self, command: List[str], *, check: bool) -> CommandResult:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=False,
        )
        result = CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            command=command,
        )

        if check and completed.returncode != 0:
            raise FFmpegError(
                f"FFmpeg exited with code {completed.returncode}",
                command,
                completed.stdout,
                completed.stderr,
            )
        return result

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------
    @staticmethod
    def stringify(command: Iterable[str]) -> str:
        """Return a shell-safe string for logging or debugging."""
        return " ".join(shlex.quote(str(part)) for part in command)
