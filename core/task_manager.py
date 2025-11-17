from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from threading import Lock
from typing import Callable, Dict, Mapping, Sequence
from uuid import uuid4

from .ffmpeg_service import FFmpegService, ProgressCallback
from .ffmpeg_wrapper import InputSpec


class TaskType(Enum):
    CONVERT = auto()
    MERGE = auto()


class TaskStatus(Enum):
    QUEUED = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


@dataclass
class Task:
    task_id: str
    task_type: TaskType
    input_data: object
    output: Path
    params: Mapping[str, object]
    status: TaskStatus = TaskStatus.QUEUED
    error: str | None = None
    future: Future | None = None
    metadata: dict = field(default_factory=dict)


class TaskManager:
    """Threaded task runner coordinating FFmpeg jobs without blocking the GUI."""

    def __init__(
        self,
        service: FFmpegService | None = None,
        *,
        max_workers: int = 2,
        on_task_update: Callable[[Task], None] | None = None,
    ) -> None:
        self.service = service or FFmpegService()
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ffmpeg-task")
        self.on_task_update = on_task_update
        self.tasks: Dict[str, Task] = {}
        self._lock = Lock()

    def submit_conversion(
        self,
        input_file: str | Path,
        output_file: str | Path,
        params: Mapping[str, object] | None = None,
        *,
        duration: float | None = None,
        progress: ProgressCallback | None = None,
    ) -> Task:
        task = Task(str(uuid4()), TaskType.CONVERT, Path(input_file), Path(output_file), params or {})
        self._register_task(task)
        future = self.executor.submit(self._run_conversion, task, duration, progress)
        task.future = future
        return task

    def submit_merge(
        self,
        inputs: Sequence[InputSpec],
        output_file: str | Path,
        params: Mapping[str, object] | None = None,
        *,
        total_duration: float | None = None,
        progress: ProgressCallback | None = None,
    ) -> Task:
        task = Task(str(uuid4()), TaskType.MERGE, list(inputs), Path(output_file), params or {})
        self._register_task(task)
        future = self.executor.submit(self._run_merge, task, total_duration, progress)
        task.future = future
        return task

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _register_task(self, task: Task) -> None:
        with self._lock:
            self.tasks[task.task_id] = task
        self._update_task(task, TaskStatus.QUEUED)

    def _run_conversion(self, task: Task, duration: float | None, progress: ProgressCallback | None) -> None:
        self._update_task(task, TaskStatus.RUNNING)
        try:
            self.service.convert(task.input_data, task.output, task.params, duration=duration, callback=progress)
        except Exception as exc:  # noqa: BLE001
            task.error = str(exc)
            self._update_task(task, TaskStatus.FAILED)
        else:
            self._update_task(task, TaskStatus.COMPLETED)

    def _run_merge(self, task: Task, duration: float | None, progress: ProgressCallback | None) -> None:
        self._update_task(task, TaskStatus.RUNNING)
        try:
            self.service.merge(task.input_data, task.output, task.params, total_duration=duration, callback=progress)
        except Exception as exc:  # noqa: BLE001
            task.error = str(exc)
            self._update_task(task, TaskStatus.FAILED)
        else:
            self._update_task(task, TaskStatus.COMPLETED)

    def _update_task(self, task: Task, status: TaskStatus) -> None:
        task.status = status
        if self.on_task_update:
            self.on_task_update(task)
