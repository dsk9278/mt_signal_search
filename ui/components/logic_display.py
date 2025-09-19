from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QMessageBox
from PyQt5.QtGui import QFont

class LogicDisplayComponent(QWidget):
    """ロジック表示（グレーのカード3段）"""
    def __init__(self, favorites_service, parent=None):
        super().__init__(parent)
        self._favorites_service = favorites_service
        self.setup_ui()

    def setup_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        for i in range(1, 4):
            layout.addWidget(self._create_logic_widget(f"ロジック{i}"))
        layout.addStretch()
        self.setLayout(layout)

    def _create_logic_widget(self, logic_name: str):
        w = QWidget()
        w.setStyleSheet("QWidget { background-color: #f5f5f5; border-radius: 8px; margin: 5px; }")
        w.setMinimumHeight(120)
        lay = QVBoxLayout()

        head = QHBoxLayout()
        title = QLabel(logic_name)
        f = QFont(); f.setBold(True); title.setFont(f)
        star_btn = QPushButton("⭐")
        star_btn.setFixedSize(30,30)
        self._update_star(star_btn, logic_name)
        star_btn.clicked.connect(lambda: self._toggle_fav(logic_name, star_btn))
        head.addWidget(title); head.addStretch(); head.addWidget(star_btn)
        lay.addLayout(head)

        placeholder = QFrame()
        placeholder.setMinimumHeight(160)
        placeholder.setStyleSheet('background-color: #d9d9d9; border-radius: 6px;')
        lay.addWidget(placeholder)

        lay.addStretch()
        w.setLayout(lay)
        return w

    def _update_star(self, b: QPushButton, logic_name: str):
        is_fav = self._favorites_service.is_favorite(logic_name)
        color = "#ffeb3b" if is_fav else "white"
        hover = "#fdd835" if is_fav else "#f0f0f0"
        b.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                border: 1px solid #ddd;
                border-radius: 15px;
            }}
            QPushButton:hover {{ background-color: {hover}; }}
        """)

    def _toggle_fav(self, logic_name: str, b: QPushButton):
        if self._favorites_service.toggle_favorite(logic_name):
            self._update_star(b, logic_name)
            QMessageBox.information(self, "お気に入り", f"'{logic_name}' を切り替えました。")