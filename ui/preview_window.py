from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from PyQt5.QtCore import QAbstractAnimation, QEasingCurve, QPropertyAnimation, QSize, Qt, QUrl
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

ICON_DIR = Path(__file__).resolve().parents[1] / "resources" / "icons"


class PreviewWindow(QWidget):
    """中央预览面板，支持播放和缩略图回退。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._thumbnail_path: str | None = None
        self._build_ui()
        self._setup_animation()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.stack = QStackedWidget()
        self.placeholder = QLabel("预览窗口")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setStyleSheet(
            "border: 1px dashed #3a3f5a; padding: 40px; color: #7f88af; border-radius: 16px;"
        )
        self.stack.addWidget(self.placeholder)

        self.video_widget = QVideoWidget()
        self.stack.addWidget(self.video_widget)

        layout.addWidget(self.stack, stretch=1)

        controls = QHBoxLayout()
        controls.setSpacing(20)
        self.play_button = self._build_control_button("播放", ICON_DIR / "play.svg")
        self.pause_button = self._build_control_button("暂停", ICON_DIR / "pause.svg")
        self.stop_button = self._build_control_button("停止", ICON_DIR / "stop.svg")

        controls.addStretch(1)
        controls.addWidget(self.play_button)
        controls.addWidget(self.pause_button)
        controls.addWidget(self.stop_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.player = QMediaPlayer(self)
        self.player.setVideoOutput(self.video_widget)
        try:
            self.player.error.connect(self._handle_error)  # type: ignore[attr-defined]
            self.player.mediaStatusChanged.connect(self._handle_status)  # type: ignore[attr-defined]
        except AttributeError:
            pass
        self.play_button.clicked.connect(self.player.play)
        self.pause_button.clicked.connect(self.player.pause)
        self.stop_button.clicked.connect(self.stop_preview)

    def _build_control_button(self, tooltip: str, icon_path: Path) -> QPushButton:
        button = QPushButton()
        button.setIcon(QIcon(str(icon_path)))
        button.setIconSize(QSize(28, 28))
        button.setToolTip(tooltip)
        button.setFixedSize(56, 56)
        return button

    def _setup_animation(self) -> None:
        effect = QGraphicsOpacityEffect(self.placeholder)
        effect.setOpacity(1.0)
        self.placeholder.setGraphicsEffect(effect)
        self._glow_effect = effect

        self._glow_anim = QPropertyAnimation(self._glow_effect, b"opacity", self)
        self._glow_anim.setDuration(900)
        self._glow_anim.setStartValue(0.6)
        self._glow_anim.setEndValue(1.0)
        self._glow_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._glow_anim.setLoopCount(2)

    def load_media(self, path: str) -> None:
        if not path:
            self.stop_preview()
            return
        media = QMediaContent(QUrl.fromLocalFile(path))
        self.player.setMedia(media)
        self.stack.setCurrentWidget(self.video_widget)
        self.player.play()
        self._pulse_preview()

    def _pulse_preview(self) -> None:
        if self._glow_anim.state() == QAbstractAnimation.Running:
            self._glow_anim.stop()
        self._glow_anim.start()

    def stop_preview(self) -> None:
        self.player.stop()
        self.stack.setCurrentWidget(self.placeholder)
        self._glow_effect.setOpacity(1.0)
        self.placeholder.setPixmap(QPixmap())
        self.placeholder.setText("预览窗口")
        if self._thumbnail_path:
            Path(self._thumbnail_path).unlink(missing_ok=True)
            self._thumbnail_path = None

    def _handle_error(self, *_args) -> None:
        path = self.player.currentMedia().canonicalUrl().toLocalFile()
        thumb = self._generate_thumbnail(path)
        self.stack.setCurrentWidget(self.placeholder)
        if thumb:
            self.placeholder.setPixmap(QPixmap(thumb))
            self.placeholder.setScaledContents(True)
            self.placeholder.setText("")
        else:
            self.placeholder.setPixmap(QPixmap())
            self.placeholder.setText("无法播放预览，格式不受支持")

    def _handle_status(self, status) -> None:
        if status == QMediaPlayer.EndOfMedia:
            self.stop_preview()
        elif status == QMediaPlayer.InvalidMedia:
            self._handle_error()

    def _generate_thumbnail(self, media_path: str) -> str | None:
        if not media_path:
            return None
        try:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            tmp_path = tmp.name
            tmp.close()
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    "00:00:01",
                    "-i",
                    media_path,
                    "-frames:v",
                    "1",
                    tmp_path,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            self._thumbnail_path = tmp_path
            return tmp_path
        except (OSError, subprocess.CalledProcessError):
            return None
