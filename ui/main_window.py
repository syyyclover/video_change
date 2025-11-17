from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QStatusBar,
    QWidget,
)

from src.core.ffmpeg_service import FFmpegService
from src.core.progress_monitor import ProgressUpdate
from src.core.task_manager import Task, TaskManager, TaskStatus
from .file_list import FileListWidget
from .preview_window import PreviewWindow
from .settings_panel import SettingsPanel
from .theme import apply_theme


@dataclass
class Job:
    kind: str  # "convert" or "merge"
    files: List[str]
    settings: Dict[str, Any]


class _UiSignals(QObject):
    progressChanged = pyqtSignal(float, str)
    statusChanged = pyqtSignal(str)
    taskFailed = pyqtSignal(str)
    taskCompleted = pyqtSignal()


class MainWindow(QMainWindow):
    """整合文件列表、预览窗口、参数面板并驱动 FFmpeg 任务队列。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FFmpeg 媒体工作台")
        self.resize(1400, 800)

        self.ffmpeg_service = FFmpegService()
        self.task_manager = TaskManager(self.ffmpeg_service, on_task_update=self._handle_task_update)
        self.signals = _UiSignals()
        self.signals.progressChanged.connect(self._apply_progress)
        self.signals.statusChanged.connect(self._set_status_text)
        self.signals.taskFailed.connect(self._on_task_failed)
        self.signals.taskCompleted.connect(self._on_task_completed)

        self.active_task_id: str | None = None
        self.pending_jobs: List[Job] = []
        self.current_job: Job | None = None
        self.current_progress = 0.0

        self._build_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.file_panel = FileListWidget()
        self.file_panel.setFixedWidth(320)
        layout.addWidget(self._wrap_panel(self.file_panel, "文件"))

        self.preview_panel = PreviewWindow()
        layout.addWidget(self._wrap_panel(self.preview_panel, "预览"), stretch=2)

        self.settings_panel = SettingsPanel()
        self.settings_panel.setFixedWidth(320)
        layout.addWidget(self._wrap_panel(self.settings_panel, "参数"))

        self.setCentralWidget(central)
        self._build_status_bar()

    def _connect_signals(self) -> None:
        self.file_panel.startRequested.connect(self._queue_conversions)
        self.file_panel.mergeRequested.connect(self._queue_merge)
        self.file_panel.selectionChanged.connect(self.preview_panel.load_media)

    def _wrap_panel(self, widget: QWidget, title: str) -> QWidget:
        container = QWidget()
        wrapper = QHBoxLayout(container)
        wrapper.setContentsMargins(0, 0, 0, 0)
        wrapper.addWidget(widget)
        container.setProperty("panelRole", "container")
        container.setProperty("title", title)
        return container

    def _build_status_bar(self) -> None:
        status = QStatusBar()
        self.status_message = QLabel("就绪")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedWidth(220)
        status.addWidget(self.status_message)
        status.addPermanentWidget(self.progress_bar)
        self.setStatusBar(status)

    # ------------------------------------------------------------------
    # Job queue helpers
    # ------------------------------------------------------------------
    def _queue_conversions(self) -> None:
        files = self.file_panel.get_selected_files() or self.file_panel.get_files()
        if not files:
            QMessageBox.information(self, "提示", "请先添加需要转换的文件。")
            return

        settings = self.settings_panel.export_settings()
        jobs = [Job("convert", [path], copy.deepcopy(settings)) for path in files]
        self._enqueue_jobs(jobs)

    def _queue_merge(self) -> None:
        files = self.file_panel.get_files()
        if len(files) < 2:
            QMessageBox.information(self, "提示", "至少选择两个文件才能合并。")
            return
        settings = copy.deepcopy(self.settings_panel.export_settings())
        self._enqueue_jobs([Job("merge", list(files), settings)])

    def _enqueue_jobs(self, jobs: List[Job]) -> None:
        self.pending_jobs.extend(jobs)
        self._start_next_job()

    def _start_next_job(self) -> None:
        if self.active_task_id or not self.pending_jobs:
            if not self.active_task_id:
                self.signals.statusChanged.emit("就绪")
            return

        job = self.pending_jobs.pop(0)
        self.current_job = job
        self.current_progress = 0.0
        if job.kind == "convert":
            self._execute_conversion_job(job)
        else:
            self._execute_merge_job(job)

    # ------------------------------------------------------------------
    # Job execution
    # ------------------------------------------------------------------
    def _execute_conversion_job(self, job: Job) -> None:
        file_path = Path(job.files[0])
        settings = job.settings
        params = self._build_params(settings)

        if not settings["output"]["path"].strip():
            default_target = file_path.with_suffix(f".{settings['output']['format']}")
            settings["output"]["path"] = str(default_target)

        try:
            output_path = self._resolve_output_path(file_path, settings)
        except OSError as exc:  # noqa: BLE001
            QMessageBox.critical(self, "输出路径错误", str(exc))
            self._finish_job(success=False)
            return

        duration = self._probe_duration(file_path)
        try:
            task = self.task_manager.submit_conversion(
                file_path,
                output_path,
                params,
                duration=duration,
                progress=self._progress_callback,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "任务提交失败", str(exc))
            self._finish_job(success=False)
            return

        self._mark_task_active(task.task_id)
        self.signals.statusChanged.emit(f"正在转换：{file_path.name}")

    def _execute_merge_job(self, job: Job) -> None:
        settings = job.settings
        params = self._build_params(settings)
        specs, durations = self._collect_media_specs(job.files)
        if not specs:
            QMessageBox.critical(self, "合并失败", "无法读取媒体信息。")
            self._finish_job(success=False)
            return

        first_path = Path(specs[0]["path"])  # type: ignore[index]
        if not settings["output"]["path"].strip():
            default_target = first_path.with_name(f"{first_path.stem}_merged.{settings['output']['format']}")
            settings["output"]["path"] = str(default_target)

        try:
            output_path = self._resolve_output_path(first_path, settings)
        except OSError as exc:  # noqa: BLE001
            QMessageBox.critical(self, "输出路径错误", str(exc))
            self._finish_job(success=False)
            return

        total_duration = sum(durations) if any(durations) else None

        try:
            task = self.task_manager.submit_merge(
                specs,
                output_path,
                params,
                total_duration=total_duration,
                progress=self._progress_callback,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "合并任务提交失败", str(exc))
            self._finish_job(success=False)
            return

        self._mark_task_active(task.task_id)
        self.signals.statusChanged.emit("正在合并…")

    def _mark_task_active(self, task_id: str) -> None:
        self.active_task_id = task_id
        self.file_panel.set_busy(True)
        self.progress_bar.setValue(0)

    # ------------------------------------------------------------------
    # Parameter & probe helpers
    # ------------------------------------------------------------------
    def _collect_media_specs(self, files: List[str]) -> Tuple[List[Dict[str, Any]], List[float]]:
        specs: List[Dict[str, Any]] = []
        durations: List[float] = []
        for path in files:
            info = self._probe_info(Path(path))
            width = height = None
            has_audio = False
            duration = 0.0
            if info:
                for stream in info.get("streams", []):
                    if stream.get("codec_type") == "video" and stream.get("width") and stream.get("height"):
                        width = int(stream["width"])
                        height = int(stream["height"])
                    elif stream.get("codec_type") == "audio":
                        has_audio = True
                try:
                    duration = float(info.get("format", {}).get("duration", 0) or 0)
                except (TypeError, ValueError):
                    duration = 0.0
            specs.append({"path": path, "width": width, "height": height, "has_audio": has_audio})
            durations.append(duration)
        return specs, durations

    def _probe_info(self, media_path: Path) -> Dict[str, Any] | None:
        try:
            return self.ffmpeg_service.probe(media_path)
        except Exception:  # noqa: BLE001
            return None

    def _build_params(self, settings: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        video_cfg = settings["video"]
        audio_cfg = settings["audio"]
        advanced_cfg = settings["advanced"]

        video_params: Dict[str, Any] = {"crf": advanced_cfg["crf"]}
        if video_cfg["codec"] != "自动":
            video_params["codec"] = video_cfg["codec"]
        if video_cfg["bitrate"]:
            video_params["bitrate"] = video_cfg["bitrate"].strip()
        if video_cfg["resolution"] != "自动":
            video_params["resolution"] = video_cfg["resolution"]
        if frame_rate := int(video_cfg["frame_rate"]):
            video_params["fps"] = frame_rate
        if advanced_cfg["preset"] != "auto":
            video_params["preset"] = advanced_cfg["preset"]
        if advanced_cfg["tune"] != "auto":
            video_params["tune"] = advanced_cfg["tune"]

        audio_params: Dict[str, Any] = {}
        if audio_cfg["codec"] != "自动":
            audio_params["codec"] = audio_cfg["codec"]
        if audio_cfg["bitrate"]:
            audio_params["bitrate"] = audio_cfg["bitrate"].strip()
        if audio_cfg["sample_rate"] != "自动":
            audio_params["sample_rate"] = int(audio_cfg["sample_rate"])
        if audio_cfg["channels"] != "自动":
            mapping = {"单声道": 1, "立体声": 2, "5.1": 6}
            audio_params["channels"] = mapping.get(audio_cfg["channels"], audio_cfg["channels"])

        return {"video": video_params, "audio": audio_params}

    def _resolve_output_path(self, input_path: Path, settings: Dict[str, Any]) -> Path:
        output_cfg = settings["output"]
        target = output_cfg["path"].strip()
        extension = output_cfg["format"]
        if target:
            target_path = Path(target)
            if target_path.is_dir():
                target_path = target_path / f"{input_path.stem}.{extension}"
        else:
            target_path = input_path.with_suffix(f".{extension}")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        return target_path

    def _probe_duration(self, media_path: Path) -> float | None:
        info = self._probe_info(media_path)
        if not info:
            return None
        try:
            return float(info.get("format", {}).get("duration", 0)) or None
        except (TypeError, ValueError):
            return None

    # ------------------------------------------------------------------
    # Progress callbacks
    # ------------------------------------------------------------------
    def _progress_callback(self, update: ProgressUpdate) -> None:
        percent = update.progress if update.progress is not None else self.current_progress
        if update.progress is not None:
            self.current_progress = update.progress
        eta_text = f" 剩余 {int(update.eta)}s" if update.eta and update.eta > 0 else ""
        message = f"处理进度 {self.current_progress * 100:4.1f}%{eta_text}"
        if update.done and update.return_code == 0:
            message = "任务完成"
        self.signals.progressChanged.emit(self.current_progress, message)

    def _handle_task_update(self, task: Task) -> None:
        if task.task_id != self.active_task_id:
            return
        if task.status == TaskStatus.COMPLETED:
            self.signals.taskCompleted.emit()
            self._finish_job(success=True)
        elif task.status == TaskStatus.FAILED:
            self.signals.taskFailed.emit(task.error or "未知错误")
            self._finish_job(success=False)

    def _finish_job(self, success: bool) -> None:
        self.active_task_id = None
        self.file_panel.set_busy(False)
        if success and self.current_job:
            for path in self.current_job.files:
                self.file_panel.remove_file(path)
            self.preview_panel.stop_preview()
        self.current_job = None
        self.current_progress = 0.0
        self.progress_bar.setValue(0)
        self._start_next_job()

    def _apply_progress(self, percent: float, message: str) -> None:
        self.progress_bar.setValue(int(max(0.0, min(1.0, percent)) * 100))
        self.status_message.setText(message)

    def _set_status_text(self, text: str) -> None:
        self.status_message.setText(text)

    def _on_task_failed(self, error: str) -> None:
        QMessageBox.critical(self, "任务失败", error)

    def _on_task_completed(self) -> None:
        QMessageBox.information(self, "完成", "任务已完成。")

    # ------------------------------------------------------------------
    # Qt events
    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802
        self.task_manager.shutdown()
        super().closeEvent(event)


def run() -> None:
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    window = MainWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    run()
