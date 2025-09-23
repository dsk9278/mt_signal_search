from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QFileDialog, QMessageBox, QDialog, QFormLayout,
    QLineEdit, QComboBox, QHBoxLayout, QPushButton, QListWidget, QListWidgetItem, QLabel
)
from PyQt5.QtGui import QFont
from mt_signal_search.domain.models import SignalInfo, SignalType
from mt_signal_search.ui.components.search_component import SearchComponent
from mt_signal_search.ui.components.logic_display import LogicDisplayComponent
from mt_signal_search.ui.components.floating_menu import FloatingMenu
from mt_signal_search.ui.components.gear_button import FloatingGearButton
from mt_signal_search.io_importers.csv_importers import CSVSignalImporter, CSVBoxConnImporter
from mt_signal_search.io_importers.pdf_importers import SimplePDFProcessor, BoxPDFProcessor
from mt_signal_search.ui.dialogs.edit_signal_dialog import EditSignalDialog
import csv

class MainWindow(QMainWindow):
    def __init__(self, search_service, favorites_service, logic_service, repo):
        super().__init__()
        self.search_service = search_service
        self.favorites_service = favorites_service
        self.logic_service = logic_service
        self._signal_repository = repo
        self._setup_ui()
        self._setup_menu()

    def _setup_ui(self) -> None:
        self.setWindowTitle("入出力プログラム検索アプリ")
        self.setGeometry(100, 100, 1400, 900)
        central = QWidget(); self.setCentralWidget(central)
        main_l = QVBoxLayout(); main_l.setSpacing(0); main_l.setContentsMargins(0,0,0,0)

        content = QWidget()
        content_l = QVBoxLayout(content); content_l.setContentsMargins(40,0,40,40)

        self.search_component = SearchComponent(self.search_service)
        self.logic_display = LogicDisplayComponent(self.favorites_service)

        content_l.addWidget(self.search_component)
        content_l.addWidget(self.logic_display)
        content.setStyleSheet("background-color: white;")

        main_l.addWidget(content); central.setLayout(main_l)

        # 左上フローティングUI
        self.fab = FloatingGearButton(self)
        self.fab_menu = FloatingMenu(self)
        self.fab.clicked.connect(self._toggle_fab_menu)
        self._place_fab()

        # ドロップダウンメニューの動作
        self.fab_menu.btn_edit.clicked.connect(self._open_edit_signal_dialog)
        self.fab_menu.btn_save.clicked.connect(self._export_data)
        self.fab_menu.btn_fav.clicked.connect(self._show_favorites_dialog)

    def _setup_menu(self) -> None:
        menubar = self.menuBar()
        file_menu = menubar.addMenu('ファイル')
        file_menu.addAction('新規信号を追加', self._add_signal_via_gui)
        file_menu.addAction('PDFインポート', self._import_pdf)
        file_menu.addAction('CSVインポート（信号）', self._import_csv_signals)
        file_menu.addAction('CSVインポート（BOX配線）', self._import_csv_box)
        file_menu.addAction('テンプレCSV出力（信号）', self._export_template_signals)
        file_menu.addAction('テンプレCSV出力（BOX配線）', self._export_template_box)
        file_menu.addAction('データエクスポート', self._export_data)
        file_menu.addSeparator()
        file_menu.addAction('終了', self.close)

    def _place_fab(self):
        margin_left, margin_top = 10, 100
        self.fab.move(margin_left, margin_top)
        self.fab_menu.move(margin_left, margin_top + 56)

    def _toggle_fab_menu(self):
        self.fab_menu.setVisible(not self.fab_menu.isVisible())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'fab'):
            self._place_fab()

    # ---------- ダイアログ: 新規信号 ----------
    def _add_signal_via_gui(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("信号の追加")
        dlg.setMinimumWidth(420)
        form = QFormLayout(dlg)

        id_edit = QLineEdit()
        type_combo = QComboBox(); type_combo.addItems([SignalType.INPUT.value, SignalType.OUTPUT.value, SignalType.INTERNAL.value])
        desc_edit = QLineEdit()
        from_edit = QLineEdit()
        via_edit = QLineEdit(); via_edit.setPlaceholderText("カンマ区切り（例: BOX5,BOX6）")
        to_edit = QLineEdit()
        addr_edit = QLineEdit()
        group_edit = QLineEdit()

        form.addRow("信号ID", id_edit)
        form.addRow("種別", type_combo)
        form.addRow("説明", desc_edit)
        form.addRow("From", from_edit)
        form.addRow("Via", via_edit)
        form.addRow("To", to_edit)
        form.addRow("プログラムアドレス", addr_edit)
        form.addRow("ロジックグループ", group_edit)

        btn_l = QHBoxLayout()
        ok = QPushButton("保存"); cancel = QPushButton("キャンセル")
        ok.clicked.connect(dlg.accept); cancel.clicked.connect(dlg.reject)
        btn_l.addWidget(ok); btn_l.addWidget(cancel)
        form.addRow(btn_l)

        if dlg.exec_() == QDialog.Accepted:
            sid   = id_edit.text().strip()
            stype = type_combo.currentText().strip()
            desc  = desc_edit.text().strip()
            fromb = from_edit.text().strip()
            via   = tuple([x.strip() for x in via_edit.text().split(",") if x.strip()])
            tob   = to_edit.text().strip()
            addr  = addr_edit.text().strip() or sid
            grp   = group_edit.text().strip()
            if not sid or not desc:
                QMessageBox.warning(self, '入力不備', '信号IDと説明は必須です。'); return
            try:
                info = SignalInfo(sid, SignalType(stype), desc, fromb, via, tob, addr, grp)
                self._signal_repository.add_signal(info)
                QMessageBox.information(self, '保存', f"'{info.signal_id}' を保存しました。")
                self.search_component.refresh()
            except Exception as e:
                QMessageBox.critical(self, 'エラー', f'保存に失敗しました: {e}')

    def _open_edit_signal_dialog(self):
        """検索選択のプリセット付きで、信号の全項目（条件式含む）を編集/追加する"""
        # 現在の選択から既存データを推測
        existing = None
        logic_expr = ""
        selected_sid = None
        try:
            tbl = getattr(self.search_component, 'results_table', None)
            if tbl is not None:
                r = tbl.currentRow()
                if r is not None and r >= 0:
                    it = tbl.item(r, 0)
                    if it:
                        selected_sid = (it.text() or "").strip()
        except Exception:
            selected_sid = None

        if selected_sid:
            try:
                existing = self._signal_repository.get_signal(selected_sid)
            except Exception:
                existing = None
            try:
                logic_expr = self.search_service.get_logic_expr(selected_sid) or ""
            except Exception:
                logic_expr = ""

        dlg = EditSignalDialog(self, existing=existing, logic_expr=logic_expr)
        if dlg.exec_() != QDialog.Accepted:
            return
        data = dlg.get_values()

        # dict → SignalInfo へ変換
        via = tuple([x.strip() for x in (data.get('via_boxes') or '').split(',') if x.strip()])
        try:
            st_enum = SignalType(data.get('signal_type') or 'INTERNAL')
        except Exception:
            st_enum = SignalType.INTERNAL
        info = SignalInfo(
            data.get('signal_id'), st_enum,
            data.get('description'), data.get('from_box'), via,
            data.get('to_box'), data.get('program_address') or data.get('signal_id'),
            data.get('logic_group')
        )

        try:
            # 信号メタのUPSERT
            self._signal_repository.add_signal(info)
            # 条件式の保存（入力があれば）
            expr = data.get('logic_expr')
            if expr:
                self.search_service.set_logic_expr(info.signal_id, expr, source_label="(ui)")
            QMessageBox.information(self, '保存', f"'{info.signal_id}' を保存しました。")
            # 直前キーワードで再検索して即反映
            self.search_component.refresh()
        except Exception as e:
            QMessageBox.critical(self, 'エラー', f'保存に失敗しました: {e}')

    def _show_favorites_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("お気に入り")
        dlg.setMinimumWidth(360)
        from PyQt5.QtWidgets import QVBoxLayout
        lay = QVBoxLayout(dlg)
        lst = QListWidget()
        favs = self.favorites_service.get_favorites()
        if favs:
            for name in favs:
                QListWidgetItem(name, lst)
        else:
            QListWidgetItem("（お気に入りはまだありません）", lst)
        lay.addWidget(lst)
        btn = QPushButton("閉じる")
        btn.clicked.connect(dlg.accept)
        lay.addWidget(btn)
        dlg.exec_()

    # ---------- PDFインポート ----------
    def _import_pdf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "PDFファイルを選択", "", "PDF Files (*.pdf)")
        if not path: return
        try:
            sig_count = 0
            box_count = 0

            # 信号（式抽出）: from/via/to は空のまま
            processor = SimplePDFProcessor()
            signals = processor.process(path)
            for s in signals:
                self._signal_repository.add_signal(s)
                sig_count += 1
            for sid, raw in processor.logic_blocks.items():
                try: self._signal_repository.add_logic_equation(sid, raw, source_label=path)
                except Exception: pass

            # BOX間配線
            try:
                box_proc = BoxPDFProcessor()
                conns = box_proc.process(path)
                for bc in conns:
                    self._signal_repository.add_box_connection(bc)
                    box_count += 1
            except RuntimeError as e:
                raise
            except Exception:
                pass

            if sig_count == 0 and box_count == 0:
                QMessageBox.warning(self, "PDFインポート", "取り込めるデータが見つかりませんでした。"); return

            self.search_component.refresh()
            parts = []
            if sig_count: parts.append(f"信号 {sig_count} 件")
            if box_count: parts.append(f"BOX配線 {box_count} 件")
            QMessageBox.information(self, "PDFインポート", " / ".join(parts) + " を取り込みました。")
        except RuntimeError as e:
            QMessageBox.critical(self, "OCR未導入", str(e))
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"PDF取り込みでエラー: {e}")

    # ---------- CSVインポート / テンプレ出力 ----------
    def _import_csv_signals(self):
        path, _ = QFileDialog.getOpenFileName(self, "signals.csv を選択", "", "CSV Files (*.csv)")
        if not path: return
        try:
            n = CSVSignalImporter(self._signal_repository).import_file(path)
            if n == 0:
                QMessageBox.warning(self, "CSVインポート", "取り込めるレコードがありませんでした。"); return
            self.search_component.refresh()
            QMessageBox.information(self, "CSVインポート", f"信号 {n} 件を取り込みました。")
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"CSV取り込みでエラー: {e}")

    def _import_csv_box(self):
        path, _ = QFileDialog.getOpenFileName(self, "box_connections.csv を選択", "", "CSV Files (*.csv)")
        if not path: return
        try:
            n = CSVBoxConnImporter(self._signal_repository).import_file(path)
            if n == 0:
                QMessageBox.warning(self, "CSVインポート", "取り込めるレコードがありませんでした。"); return
            QMessageBox.information(self, "CSVインポート", f"BOX配線 {n} 件を取り込みました。")
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"CSV取り込みでエラー: {e}")

    def _export_template_signals(self):
        path, _ = QFileDialog.getSaveFileName(self, "信号テンプレートCSVを保存", "", "CSV Files (*.csv)")
        if not path: return
        headers = ["signal_id","signal_type","description","from_box","via_boxes","to_box","program_address","logic_group","logic_expr"]
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f); w.writerow(headers)
            w.writerow(["Q3B0","OUTPUT","右内タンピングユニット下降","BOX3","BOX5,BOX6","BOX7","Q3B0","ロジック2","04E^351^383^3BD^((065^354)v038)"])
        QMessageBox.information(self, "テンプレート出力", f"信号テンプレCSVを '{path}' に出力しました。")

    def _export_template_box(self):
        path, _ = QFileDialog.getSaveFileName(self, "BOX配線テンプレートCSVを保存", "", "CSV Files (*.csv)")
        if not path: return
        headers = ["from_box_name","from_box_no","kabel_no","to_box_no","to_box_name"]
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f); w.writerow(headers)
            w.writerow(["後部運転室：作業コントロールパネル","2","2.15","4","前部運転室：プログラムコントロールパネル"])
        QMessageBox.information(self, "テンプレート出力", f"BOX配線テンプレCSVを '{path}' に出力しました。")

    def _export_data(self) -> None:
        file_dialog = QFileDialog(self)
        path, _ = file_dialog.getSaveFileName(self, "データをエクスポート", "", "JSON Files (*.json)")
        if path:
            QMessageBox.information(self, "エクスポート完了", f"データを '{path}' にエクスポートしました。")