from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List


class FFmpegError(RuntimeError):
    """Raised when an FFmpeg/ffprobe command fails."""

    def __init__(self, message: str, command: Iterable[str], stdout: str, stderr: str) -> None:
        super().__init__(message)
        self.command = list(command)
        self.stdout = stdout
        self.stderr = stderr


@dataclass(slots=True)
class CommandResult:
    """Thin wrapper around subprocess output for downstream consumers."""

    returncode: int
    stdout: str
    stderr: str
    command: List[str]
