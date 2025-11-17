from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from PyQt5.QtCore import QAbstractAnimation, QEasingCurve, QPropertyAnimation, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QDropEvent, QIcon
from PyQt5.QtWidgets import (
    QFileDialog,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

ICON_DIR = Path(__file__).resolve().parents[1] / "resources" / "icons"


class FileListWidget(QWidget):
    """媒体文件管理面板：支持拖拽、添加、移除、触发转换/合并。"""

    startRequested = pyqtSignal()
    mergeRequested = pyqtSignal()
    filesChanged = pyqtSignal(list)
    selectionChanged = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._busy = False
        self._build_ui()
        self.setAcceptDrops(True)
        self._setup_animations()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        heading = QLabel("媒体文件")
        heading.setProperty("class", "panel-heading")
        layout.addWidget(heading)

        button_row = QHBoxLayout()
        self.add_button = QPushButton("添加文件")
        self.add_button.setIcon(QIcon(str(ICON_DIR / "add.svg")))
        self.add_button.setIconSize(QSize(20, 20))
        self.add_button.clicked.connect(self._open_file_dialog)
        button_row.addWidget(self.add_button)

        self.remove_button = QPushButton("移除选中")
        self.remove_button.clicked.connect(self.remove_selected)
        button_row.addWidget(self.remove_button)
        layout.addLayout(button_row)

        action_row = QHBoxLayout()
        self.start_button = QPushButton("转换当前")
        self.start_button.clicked.connect(self.startRequested.emit)
        action_row.addWidget(self.start_button)

        self.merge_button = QPushButton("合并导出")
        self.merge_button.clicked.connect(self.mergeRequested.emit)
        action_row.addWidget(self.merge_button)
        layout.addLayout(action_row)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.itemSelectionChanged.connect(self._emit_selection)
        layout.addWidget(self.list_widget, stretch=1)

        self.hint_label = QLabel("拖放文件到此处即可加入任务")
        self.hint_label.setAlignment(Qt.AlignCenter)
        self.hint_label.setProperty("class", "hint-label")
        layout.addWidget(self.hint_label)
        self._update_state()

    def _setup_animations(self) -> None:
        self._hint_effect = QGraphicsOpacityEffect(self.hint_label)
        self.hint_label.setGraphicsEffect(self._hint_effect)
        self._pulse_anim = QPropertyAnimation(self._hint_effect, b"opacity", self)
        self._pulse_anim.setDuration(500)
        self._pulse_anim.setStartValue(0.4)
        self._pulse_anim.setEndValue(1.0)
        self._pulse_anim.setLoopCount(-1)
        self._pulse_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

    def _open_file_dialog(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "选择媒体文件")
        if files:
            self.add_files(files)

    def remove_selected(self) -> None:
        for item in self.list_widget.selectedItems():
            row = self.list_widget.row(item)
            self.list_widget.takeItem(row)
        self._update_state()

    def add_files(self, files: Iterable[str | Path]) -> None:
        for path in files:
            self.list_widget.addItem(QListWidgetItem(str(path)))
        self._stop_pulse()
        self._update_state()

    def get_files(self) -> List[str]:
        return [self.list_widget.item(i).text() for i in range(self.list_widget.count())]

    def get_selected_files(self) -> List[str]:
        return [item.text() for item in self.list_widget.selectedItems()]

    def dragEnterEvent(self, event: QDropEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._start_pulse()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        super().dragLeaveEvent(event)
        self._stop_pulse()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        if not event.mimeData().hasUrls():
            event.ignore()
            self._stop_pulse()
            return

        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        self.add_files(paths)
        event.acceptProposedAction()
        self._stop_pulse()

    def _start_pulse(self) -> None:
        if self._pulse_anim.state() != QAbstractAnimation.Running:
            self._pulse_anim.start()

    def _stop_pulse(self) -> None:
        if self._pulse_anim.state() == QAbstractAnimation.Running:
            self._pulse_anim.stop()
        self._hint_effect.setOpacity(1.0)

    def _emit_selection(self) -> None:
        item = self.list_widget.currentItem()
        self.selectionChanged.emit(item.text() if item else "")

    def _update_state(self) -> None:
        files = self.get_files()
        has_files = bool(files)
        has_multi = len(files) >= 2
        enabled = has_files and not self._busy
        self.start_button.setEnabled(enabled)
        self.merge_button.setEnabled(has_multi and not self._busy)
        self.remove_button.setEnabled(has_files and not self._busy)
        self.filesChanged.emit(files)

    def remove_file(self, path: str) -> None:
        matches = self.list_widget.findItems(path, Qt.MatchExactly)
        if matches:
            row = self.list_widget.row(matches[0])
            self.list_widget.takeItem(row)
            self._update_state()

    def clear_all(self) -> None:
        self.list_widget.clear()
        self._update_state()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.add_button.setEnabled(not busy)
        self._update_state()
