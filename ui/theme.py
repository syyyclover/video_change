from __future__ import annotations

from typing import Any

THEME_QSS = """
* {
    color: #C7CCE5;
    background: transparent;
    font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
}

QMainWindow {
    background-color: #0F1220;
}

QWidget[panelRole="container"] {
    background: #151A2E;
    border-right: 1px solid #1F2640;
}

QLabel[class="panel-heading"] {
    color: #F5F7FF;
    font-size: 14px;
    letter-spacing: 0.8px;
    text-transform: uppercase;
}

QLabel[class="hint-label"] {
    color: #7E86B3;
    font-size: 12px;
}

QTabWidget::pane {
    border: 1px solid #242B45;
    background: #151A2E;
}

QTabBar::tab {
    background: #1C2135;
    color: #8EA0D5;
    padding: 8px 16px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}

QTabBar::tab:selected {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1E66FF, stop:1 #40A9FF);
    color: #FFFFFF;
}

QPushButton {
    background: #1E66FF;
    color: white;
    border-radius: 16px;
    padding: 8px 20px;
}

QPushButton:hover {
    background: #3483FF;
}

QListWidget {
    background: #161B2E;
    border: 1px solid #242B45;
    border-radius: 12px;
    padding: 8px;
}

QLineEdit, QComboBox, QSpinBox {
    background: #11162B;
    border: 1px solid #2A3254;
    border-radius: 12px;
    padding: 6px 10px;
}

QLineEdit:focus,
QComboBox:focus,
QSpinBox:focus {
    border-color: #1E66FF;
}

QStatusBar {
    background: #14182A;
    color: #8EA0D5;
    border-top: 1px solid #242B45;
}

QProgressBar {
    background: #1B2033;
    border: 1px solid #2A3254;
    border-radius: 10px;
    text-align: center;
}

QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1E66FF, stop:1 #40A9FF);
    border-radius: 10px;
}
"""


def apply_theme(app: Any) -> None:
    """Apply global stylesheet to a QApplication instance."""
    app.setStyleSheet(THEME_QSS)
