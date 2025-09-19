from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton, QLineEdit, QTableWidget, QTableWidgetItem,QHeaderView
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

def display_with_overline(expr: str) -> str:
    if not expr:
        return ""
    parts = []
    for tok in expr.split():
        if tok.startswith("!"):
            parts.append(f"<span style='text-decoration: overline;'>{tok[1:]}</span>")
        else:
            parts.append(tok)
    return " ".join(parts)

class SearchComponent(QWidget):
    """検索（大タイトル + ピル型検索バー + 結果テーブル From/Via/To）"""
    def __init__(self, search_service, parent=None):
        super().__init__(parent)
        self._search_service = search_service
        self.setup_ui()
        self.connect_events()

    def setup_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(20,20,20,20)

        title = QLabel("入出力プログラム検索アプリ")
        f = QFont(); f.setPointSize(40); f.setBold(True); title.setFont(f)
        title.setAlignment(Qt.AlignCenter)

        search_layout = QHBoxLayout()
        pill = QFrame(); pill.setStyleSheet('QFrame { background: #eee4f0; border-radius: 18px; }')
        pill_l = QHBoxLayout(pill); pill_l.setContentsMargins(12,6,12,6)
        menu_icon = QPushButton('≡'); menu_icon.setFixedSize(28,28)
        menu_icon.setStyleSheet('QPushButton { background: transparent; border: none; font-size:16px; }')
        self.search_input = QLineEdit(); self.search_input.setPlaceholderText("信号ID/説明/BOXを入力")
        self.search_input.setStyleSheet('QLineEdit { border: none; background: transparent; padding: 6px; font-size: 14px; }')
        search_btn = QPushButton('🔍'); search_btn.setFixedSize(32,32)
        search_btn.setStyleSheet('QPushButton { background: #7b57a8; color: white; border: none; border-radius: 16px; }'
                                 '\nQPushButton:hover { background: #67439a; }')
        pill_l.addWidget(menu_icon); pill_l.addWidget(self.search_input, 1); pill_l.addWidget(search_btn)
        search_layout.addWidget(pill)

        self.results_label = QLabel("検索結果リスト")
        rf = QFont(); rf.setPointSize(16); rf.setBold(True); self.results_label.setFont(rf)

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(7)
        self.results_table.setHorizontalHeaderLabels(["信号ID","種別","説明","From","Via","To","条件式"])
        header = self.results_table.horizontalHeader()
        for i in range(6):
            header.setSectionResizeMode(i,QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6,QHeaderView.Stretch)
        self.results_table.setWordWrap(True)
        self.results_table.setStyleSheet("""
            QTableWidget { background-color: white; border: 1px solid #ddd; border-radius: 8px; gridline-color: #eee; }
            QTableWidget::item { padding: 8px; }
            QHeaderView::section {
                background-color: #f8f9fa; padding: 8px; border: none; border-bottom: 1px solid #ddd; font-weight: bold;
            }
        """)

        layout.addWidget(title); layout.addSpacing(20); layout.addLayout(search_layout)
        layout.addSpacing(20); layout.addWidget(self.results_label); layout.addWidget(self.results_table)
        self.setLayout(layout)
        self.search_button = search_btn

    def connect_events(self) -> None:
        self.search_button.clicked.connect(self._perform_search)
        self.search_input.returnPressed.connect(self._perform_search)

    def _perform_search(self) -> None:
        kw = self.search_input.text().strip()
        if not kw: return
        results = self._search_service.search_signals(kw)
        self._display_results(results)

    def _display_results(self, results) -> None:
        self.results_table.setRowCount(len(results))
        for row, s in enumerate(results):
            self.results_table.setItem(row, 0, QTableWidgetItem(s.signal_id))
            self.results_table.setItem(row, 1, QTableWidgetItem(s.signal_type.value))
            self.results_table.setItem(row, 2, QTableWidgetItem(s.description))
            self.results_table.setItem(row, 3, QTableWidgetItem(s.from_box))
            self.results_table.setItem(row, 4, QTableWidgetItem(", ".join(s.via_boxes)))
            self.results_table.setItem(row, 5, QTableWidgetItem(s.to_box))
            expr = self._search_service.get_logic_expr(s.signal_id) or ""
            label = self._search_service.get_source_label(s.signal_id) or ""
            text = f"{display_with_overline(expr)}<br><span style='color: gray; font-size: 10px;'>(出所: {label})</span>"if label else display_with_overline(expr)
            lab = QLabel(text)
            lab.setTextFormat(Qt.RichText)
            lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lab.setWordWrap(True)
            self.results_table.setCellWidget(row, 6, lab) 
        self.results_table.resizeRowsToContents()
        self.results_label.setText(f"検索結果リスト ({len(results)}件)")