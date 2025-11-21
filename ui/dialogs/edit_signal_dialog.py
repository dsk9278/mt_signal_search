from PyQt5.QtWidgets import (
    QDialog,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QHBoxLayout,
    QPushButton,
    QMessageBox,
)
from mt_signal_search.domain.models import SignalInfo, SignalType


class EditSignalDialog(QDialog):
    """信号全項目(条件式を含む)を編集・追加するためのダイアログ
    floating_menu の「編集」ボタンからMainWindow経由で起動
    既存選択があれば値をプリセット、新規なら空フォーム"""

    def __init__(self, parent=None, existing: SignalInfo = None, logic_expr: str = ""):
        super().__init__(parent)
        self.setWindowTitle("信号の編集/追加")
        self.setMinimumWidth(520)

        form = QFormLayout(self)

        # ------------フィールド------------
        self.id_edit = QLineEdit()
        self.id_edit.setPlaceholderText("例: Q101")

        self.type_combo = QComboBox()
        self.type_combo.addItems(
            [
                SignalType.INPUT.value,
                SignalType.OUTPUT.value,
                SignalType.INTERNAL.value,
            ]
        )
        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("説明（必須）")
        self.from_edit = QLineEdit()
        self.from_edit.setPlaceholderText("例: BOX3")
        self.via_edit = QLineEdit()
        self.via_edit.setPlaceholderText("カンマ区切り（例：BOX5,BOX6）")
        self.to_edit = QLineEdit()
        self.to_edit.setPlaceholderText("例: BOX7")
        self.addr_edit = QLineEdit()
        self.addr_edit.setPlaceholderText("例: Q101(未入力なら信号IDを使用)")
        self.group_edit = QLineEdit()
        self.group_edit.setPlaceholderText("例: ロジック2")
        self.logic_edit = QLineEdit()
        self.logic_edit.setPlaceholderText("例: !500 ^ 503 v 507")

        form.addRow("信号ID", self.id_edit)
        form.addRow("種別", self.type_combo)
        form.addRow("説明", self.desc_edit)
        form.addRow("From", self.from_edit)
        form.addRow("Via", self.via_edit)
        form.addRow("To", self.to_edit)
        form.addRow("アドレス", self.addr_edit)
        form.addRow("グループ", self.group_edit)
        form.addRow("条件式", self.logic_edit)

        # ------------既存値の反映------------
        if existing:
            self.id_edit.setText(existing.signal_id)
            # IDは基本変更しない想定だが、要件次第で編集不可にはしない
            try:
                idx = self.type_combo.findText(existing.signal_type.value)
                if idx >= 0:
                    self.type_combo.setCurrentIndex(idx)
            except Exception:
                pass
            self.desc_edit.setText(existing.description or " ")
            self.from_edit.setText(existing.from_box or " ")
            self.via_edit.setText(
                ",".join(existing.via_boxes) if getattr(existing, "via_boxes", None) else " "
            )
            self.to_edit.setText(existing.to_box or " ")
            self.addr_edit.setText(existing.program_address or existing.signal_id)
            self.group_edit.setText(existing.logic_group or " ")
        if logic_expr:
            self.logic_edit.setText(logic_expr)

        # ------------ボタン------------
        btn_row = QHBoxLayout()
        ok = QPushButton("保存")
        cancel = QPushButton("キャンセル")
        ok.clicked.connect(self._on_ok_)
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(ok)
        btn_row.addWidget(cancel)
        form.addRow(btn_row)

    def _on_ok_(self):
        """OKボタン押下時"""
        sid = self.id_edit.text().strip()
        desc = self.desc_edit.text().strip()
        if not sid or not desc:
            QMessageBox.warning(self, "入力エラー", "信号IDと説明は必須です。")
            return
        self.accept()

    def get_values(self):
        """編集結果をdictで返す。MainWindow側でSignalInfo/保村処理に変換する"""
        return {
            "signal_id": self.id_edit.text().strip(),
            "signal_type": self.type_combo.currentText().strip(),
            "description": self.desc_edit.text().strip(),
            "from_box": self.from_edit.text().strip(),
            "via_boxes": self.via_edit.text().strip(),
            "to_box": self.to_edit.text().strip(),
            "program_address": self.addr_edit.text().strip(),
            "logic_group": self.group_edit.text().strip(),
            "logic_expr": self.logic_edit.text().strip(),
        }
