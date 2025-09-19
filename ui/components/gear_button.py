from PyQt5.QtWidgets import QPushButton

class FloatingGearButton(QPushButton):
    """左上に重ねる丸いギアボタン"""
    def __init__(self, parent=None):
        super().__init__('⚙', parent)
        self.setFixedSize(44,44)
        self.setStyleSheet('''
            QPushButton { background: #7b57a8; color: white; border: none; border-radius: 22px; font-size: 18px; }
            QPushButton:hover { background: #67439a; }
        ''')