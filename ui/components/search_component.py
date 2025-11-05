from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QPushButton,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QInputDialog,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from html import escape

from mt_signal_search.ui.utils.formatters import display_with_overline



class SearchComponent(QWidget):
    """検索（大タイトル + ピル型検索バー + 結果テーブル From/Via/To）"""
    signal_selected = pyqtSignal(int, object)

    def __init__(self, search_service, parent=None):
        super().__init__(parent)
        self._search_service = search_service
        self._last_keyword = "" #直近の検索キーワード
        self._current_results = []
        self.setup_ui()
        self.connect_events()

    def setup_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(40,40,40,40)

        title = QLabel("入出力プログラム検索アプリ")
        f = QFont(); f.setPointSize(40); f.setBold(True); title.setFont(f)
        title.setAlignment(Qt.AlignCenter)

        search_layout = QHBoxLayout()
        pill = QFrame(); pill.setStyleSheet('QFrame { background: #eee4f0; border-radius: 18px; }')
        pill_l = QHBoxLayout(pill); pill_l.setContentsMargins(24,12,24,12) #検索バー内のオブジェクトの配置
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
        self.results_table.setMinimumHeight(300) #検索結果表示欄の縦サイズ
        self.results_table.setColumnCount(7)
        self.results_table.setHorizontalHeaderLabels(["信号ID","種別","説明","From","Via","To","条件式"])
        header = self.results_table.horizontalHeader()
        for i in range(6):
            header.setSectionResizeMode(i,QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6,QHeaderView.Stretch)
        self.results_table.setWordWrap(True)
        #　行の高さの変更
        self.results_table.verticalHeader().setDefaultSectionSize(40)
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
        self.results_table.itemDoubleClicked.connect(self._handle_result_double_click)

    def connect_events(self) -> None:
        self.search_button.clicked.connect(self._perform_search)
        self.search_input.returnPressed.connect(self._perform_search)

    def _perform_search(self) -> None:
        kw = self.search_input.text().strip()
        if not kw:
            return
        self._last_keyword = kw
        results = self._search_service.search_signals(kw)
        self._display_results(results)

    def refresh(self) -> None:
        """直近の検索キーワードで再検索"""
        if not self._last_keyword:
            return
        results = self._search_service.search_signals(self._last_keyword)
        self._display_results(results)

    def _display_results(self, results) -> None:
        self._current_results = list(results)
        self.results_table.setRowCount(len(results))
        for row, s in enumerate(results):
            self.results_table.setItem(row, 0, QTableWidgetItem(s.signal_id))
            self.results_table.setItem(row, 1, QTableWidgetItem(s.signal_type.value))
            self.results_table.setItem(row, 2, QTableWidgetItem(s.description or ""))
            self.results_table.setItem(row, 3, QTableWidgetItem(s.from_box or ""))
            self.results_table.setItem(row, 4, QTableWidgetItem(", ".join(s.via_boxes or [])))
            self.results_table.setItem(row, 5, QTableWidgetItem(s.to_box or ""))
            expr = self._search_service.get_logic_expr(s.signal_id) or ""
            label = self._search_service.get_source_label(s.signal_id) or ""
            label_safe = escape(label)
            text_base = display_with_overline(expr)
            text = (
                f"{text_base}<br><span style= 'color: glay; font-size: 10px;'>(出所: {label_safe})</span>"
                if label else text_base
            )
            lab = QLabel(text)
            lab.setTextFormat(Qt.RichText)
            lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lab.setWordWrap(True)
            self.results_table.setCellWidget(row, 6, lab) 
        self.results_table.resizeRowsToContents()
        #各行の高さが出所ラベルを収めるのに十分になるよう調整
        vh = self.results_table.verticalHeader()
        for row in range(self.results_table.rowCount()):
            current_height = self.results_table.rowHeight(row)
            if current_height < 60:
                self.results_table.setRowHeight(row, 60)
        self.results_label.setText(f"検索結果リスト ({len(results)}件)")

    def _handle_result_double_click(self, item) -> None:
        if item is None:
            return
        row = item.row()
        if row < 0 or row >= len(self._current_results):
            return
        signal = self._current_results[row]
        slot_no, ok = QInputDialog.getInt(
            self,
            "ロジックボックスを選択",
            "追加するボックス番号 (1〜3):",
            1,
            1,
            3,
            1,
        )
        if not ok:
            return
        self.signal_selected.emit(slot_no, signal)
