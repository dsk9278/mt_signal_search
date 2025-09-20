from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QPushButton, QWidget, QScrollArea, QSizePolicy
)
from PyQt5.QtCore import Qt

class FloatingMenu(QFrame):
    """左上に表示されるシンプルなメニュー。ボタン押下の処理は MainWindow 側で接続する。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet('''
            QFrame { background: white; border: 1px solid #ddd; border-radius: 8px; }
            QPushButton { border: none; padding: 16px 22px; text-align: left; font-size: 16px; }
            QPushButton:hover { background: #f5f5f5; }
        ''')
        self.setVisible(False)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Buttons
        self.btn_edit = QPushButton('編集')
        self.btn_save = QPushButton('保存')
        self.btn_fav  = QPushButton('お気に入り')

        for _b in (self.btn_edit, self.btn_save, self.btn_fav):
            _b.setMinimumHeight(52)
            _b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            layout.addWidget(_b)

        scroll.setWidget(content)
        outer.addWidget(scroll)

        # Size
        self.setFixedWidth(300)
        self.setMinimumHeight(200)
        self.setMaximumHeight(360)