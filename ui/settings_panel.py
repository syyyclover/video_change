from __future__ import annotations

from typing import Callable

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class SettingsPanel(QWidget):
    """Parameter configuration stack for video/audio/advanced/output."""

    settingsChanged = pyqtSignal(dict)

    def __init__(self, on_change: Callable[[dict], None] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._on_change = on_change
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_video_tab(), "视频")
        self.tabs.addTab(self._build_audio_tab(), "音频")
        self.tabs.addTab(self._build_advanced_tab(), "高级")
        self.tabs.addTab(self._build_output_tab(), "输出")
        root.addWidget(self.tabs)

        self.status_label = QLabel("等待参数配置…")
        self.status_label.setProperty("class", "hint-label")
        root.addWidget(self.status_label)
        root.addStretch(1)

    def _build_video_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setSpacing(8)

        self.resolution = QComboBox()
        self.resolution.addItems(["自动", "1920x1080", "1280x720", "3840x2160"])
        self._register_change(self.resolution)
        layout.addRow("分辨率", self.resolution)

        self.frame_rate = QSpinBox()
        self.frame_rate.setRange(1, 240)
        self.frame_rate.setValue(30)
        self._register_change(self.frame_rate)
        layout.addRow("帧率", self.frame_rate)

        self.video_bitrate = QLineEdit()
        self.video_bitrate.setPlaceholderText("例如 8M 或 5000k")
        self._register_change(self.video_bitrate)
        layout.addRow("视频码率", self.video_bitrate)

        self.video_codec = QComboBox()
        self.video_codec.addItems(["自动", "h264", "hevc", "vp9"])
        self._register_change(self.video_codec)
        layout.addRow("视频编码器", self.video_codec)
        return widget

    def _build_audio_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setSpacing(8)

        self.sample_rate = QComboBox()
        self.sample_rate.addItems(["自动", "44100", "48000", "96000"])
        self._register_change(self.sample_rate)
        layout.addRow("采样率", self.sample_rate)

        self.channels = QComboBox()
        self.channels.addItems(["自动", "单声道", "立体声", "5.1"])
        self._register_change(self.channels)
        layout.addRow("声道数", self.channels)

        self.audio_codec = QComboBox()
        self.audio_codec.addItems(["自动", "aac", "mp3", "opus", "wav"])
        self._register_change(self.audio_codec)
        layout.addRow("音频编码", self.audio_codec)

        self.audio_bitrate = QLineEdit()
        self.audio_bitrate.setPlaceholderText("例如 192k")
        self._register_change(self.audio_bitrate)
        layout.addRow("音频码率", self.audio_bitrate)
        return widget

    def _build_advanced_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setSpacing(8)

        self.crf = QSpinBox()
        self.crf.setRange(0, 51)
        self.crf.setValue(23)
        self._register_change(self.crf)
        layout.addRow("CRF 值", self.crf)

        self.preset = QComboBox()
        self.preset.addItems(["auto", "ultrafast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"])
        self._register_change(self.preset)
        layout.addRow("编码预设", self.preset)

        self.tune = QComboBox()
        self.tune.addItems(["auto", "film", "animation", "grain", "fastdecode"])
        self._register_change(self.tune)
        layout.addRow("调优参数", self.tune)

        self.hardware = QComboBox()
        self.hardware.addItems(["自动", "CPU", "NVENC", "QuickSync", "AMF"])
        self._register_change(self.hardware)
        layout.addRow("硬件加速", self.hardware)
        return widget

    def _build_output_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setSpacing(8)

        self.container = QComboBox()
        self.container.addItems(["mp4", "mov", "mkv", "webm", "gif", "mp3", "wav", "aac"])
        self._register_change(self.container)
        layout.addRow("输出格式", self.container)

        self.output_path = QLineEdit()
        self.output_path.setPlaceholderText("输出路径或命名模板")
        self._register_change(self.output_path)

        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)
        row_layout.addWidget(self.output_path)

        browse = QPushButton("浏览…")
        browse.clicked.connect(self._choose_output_path)
        row_layout.addWidget(browse)

        layout.addRow("输出路径", row_widget)
        return widget

    def _choose_output_path(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(self, "选择输出文件", "", "媒体文件 (*.*)")
        if filename:
            self.output_path.setText(filename)
            self._emit_change()

    def _register_change(self, widget: QWidget) -> None:
        if hasattr(widget, "editingFinished"):
            widget.editingFinished.connect(self._emit_change)  # type: ignore[attr-defined]
        if hasattr(widget, "currentIndexChanged"):
            widget.currentIndexChanged.connect(lambda _idx: self._emit_change())  # type: ignore[attr-defined]
        if isinstance(widget, QSpinBox):
            widget.valueChanged.connect(lambda _val: self._emit_change())

    def _emit_change(self) -> None:
        payload = self.export_settings()
        self.settingsChanged.emit(payload)
        if self._on_change:
            self._on_change(payload)

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def set_output_path(self, path: str) -> None:
        self.output_path.setText(path)
        self._emit_change()

    def export_settings(self) -> dict:
        return {
            "video": {
                "resolution": self.resolution.currentText(),
                "frame_rate": self.frame_rate.value(),
                "bitrate": self.video_bitrate.text(),
                "codec": self.video_codec.currentText(),
            },
            "audio": {
                "sample_rate": self.sample_rate.currentText(),
                "channels": self.channels.currentText(),
                "bitrate": self.audio_bitrate.text(),
                "codec": self.audio_codec.currentText(),
            },
            "advanced": {
                "crf": self.crf.value(),
                "preset": self.preset.currentText(),
                "tune": self.tune.currentText(),
                "hardware": self.hardware.currentText(),
            },
            "output": {
                "format": self.container.currentText(),
                "path": self.output_path.text(),
            },
        }
