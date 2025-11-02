# -----------------------------------------------------------------------------
# MainWindow: 画面の土台・イベント配線・ワーカー起動の中枢
#  - ここでは UI ウィジェットの構築と、非同期ワーカー（CSV/PDF取込）との橋渡しを行う
#  - ImportCSVWorker / ImportPDFWorker を QThread で動かし、UI スレッドをブロックしない
#  - 進捗は QProgressDialog、完了後は検索結果を再描画する
# -----------------------------------------------------------------------------

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QFileDialog, QMessageBox, QDialog, QFormLayout,
    QLineEdit, QComboBox, QHBoxLayout, QPushButton, QListWidget, QListWidgetItem, QLabel, QProgressDialog
    ,QScrollArea, QSizePolicy
)
from PyQt5.QtGui import QFont, QDesktopServices
from PyQt5.QtCore import QThread, QUrl
from pytesseract.pytesseract import LANG_PATTERN
from mt_signal_search.domain.models import SignalInfo, SignalType
from mt_signal_search.ui.components.search_component import SearchComponent
from mt_signal_search.ui.components.logic_display import LogicDisplayComponent
from mt_signal_search.ui.components.floating_menu import FloatingMenu
from mt_signal_search.ui.components.gear_button import FloatingGearButton
from mt_signal_search.ui.dialogs.edit_signal_dialog import EditSignalDialog
from mt_signal_search.ui.async_workers import ImportCSVWorker, ImportPDFWorker
import csv

# 画面本体。メニューや各ボタンの動作、検索→ロジック表示、取込ワーカーの起動を担当。
class MainWindow(QMainWindow):
    # Service/Repository の参照を保持（DB への保存・検索に利用）
    def __init__(self, search_service, favorites_service, logic_service, repo):
        super().__init__()
        self.search_service = search_service
        self.favorites_service = favorites_service
        self.logic_service = logic_service
        self._signal_repository = repo
        self._setup_ui()
        self._setup_menu()
    
    # ウィンドウとレイアウトの基本構成
    def _setup_ui(self) -> None:
        self.setWindowTitle("入出力プログラム検索アプリ")
        self.setGeometry(100, 100, 1400, 900)
        central = QWidget(); self.setCentralWidget(central)
        main_l = QVBoxLayout(); main_l.setSpacing(0); main_l.setContentsMargins(0,0,0,0)
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)

        #content = QWidget(scroll_area.setWidget(content))
        content = QWidget()
        content_l = QVBoxLayout(content); content_l.setContentsMargins(40,0,40,40)
        scroll_area.setWidget(content)

        self.search_component = SearchComponent(self.search_service)
        self.search_component.signal_selected.connect(self._handle_signal_selected)
        self.logic_display = LogicDisplayComponent(self.favorites_service)

        content_l.addWidget(self.search_component)
        content_l.addWidget(self.logic_display)
        content.setStyleSheet("background-color: white;")

        #main_l.addWidget(content); central.setLayout(main_l)
        main_l.addWidget(scroll_area)
        central.setLayout(main_l)

        # 左上フローティングUI
        self.fab = FloatingGearButton(self)
        self.fab_menu = FloatingMenu(self)
        self.fab.clicked.connect(self._toggle_fab_menu)
        self._place_fab()

        # ドロップダウンメニューの動作
        self.fab_menu.btn_edit.clicked.connect(self._open_edit_signal_dialog)
        self.fab_menu.btn_save.clicked.connect(self._export_data)
        self.fab_menu.btn_fav.clicked.connect(self._show_favorites_dialog)
        
        # メニューバー：ファイル系のコマンドを登録
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
        file_menu.addAction('ログを開く', self._open_app_log)
        file_menu.addAction('終了', self.close)

    def _handle_signal_selected(self, slot_no, signal):
        try:
            self.logic_display.add_signal(slot_no, signal)
        except Exception as exc:
            QMessageBox.critical(self, 'エラー', f'ロジックボックスへの追加に失敗しました: {exc}')

    # 画面左上からのマージンで歯車とメニューを配置
    def _place_fab(self):
        margin_left, margin_top = 10, 100
        self.fab.move(margin_left, margin_top)
        self.fab_menu.move(margin_left, margin_top + 56)

    # 歯車ボタンの ON/OFF でメニューの表示切替
    def _toggle_fab_menu(self):
        self.fab_menu.setVisible(not self.fab_menu.isVisible())

    # リサイズ時も歯車の位置を保つ（絶対座標）
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
            # SignalInfo を UPSERT 保存し、完了後に検索結果を更新
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

    # ---------- ワーカー共通ハンドラ ----------
    # ここから：非同期ワーカー（CSV/PDF取込）との橋渡し関数群
    # - _ensure_repo_db_path: ワーカーが DB に新規接続するためのファイルパス取得
    # - _connect_common_worker_signals: 各シグナルと UI の挙動を一括配線
    # - _on_worker_report/_error/_confirm: レポート表示・エラー表示・Yes/No 応答
    # - 進捗ダイアログの open/update/close
    def _ensure_repo_db_path(self) -> str:
        """リポジトリからDBパスを取得（ワーカーがスレッド内で新規接続するために必要）。"""
        db_path = getattr(self._signal_repository, 'db_path', None)
        if not db_path:
            raise RuntimeError('リポジトリの db_path が取得できません。')
        return db_path
        # ※ repo はUIスレッドに属するため、ワーカーはスレッド内で別のSQLite接続を開く

    def _connect_common_worker_signals(self, worker, thread, *, title='取り込み中', label='処理中…'):
        # 開始時: 進捗ダイアログを開く
        worker.started.connect(lambda: self._open_progress(title, label, worker))
        # 進捗
        worker.progress.connect(self._update_progress)
        # レポート/エラー/キャンセル/確認
        worker.report.connect(self._on_worker_report)
        worker.error.connect(self._on_worker_error)
        worker.canceled.connect(lambda: self.statusBar().showMessage('キャンセルされました'))
        worker.ask_confirm.connect(self._on_worker_confirm)
        # 終了時: ダイアログを閉じてスレッドを畳む。thread.quitが呼ばれるとスレッドを削除する（deleteLaterが動く）
        worker.finished.connect(lambda *args: self._close_progress())
        worker.error.connect(lambda *_: self._close_progress())
        worker.canceled.connect(lambda: self._close_progress())
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        worker.canceled.connect(thread.quit)

    def _on_worker_report(self, summary: str, log_path: str):
        #　取り込み後の警告メッセージ
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle('取り込みレポート')
        box.setText(summary or 'レポート')

        open_btn = None
        if log_path:
            box.setInformativeText(f"ログ: {log_path}")
            # QMessageBoxのボタンは　add Buttonで追加する
            open_btn = box.addButton('ログを開く', QMessageBox.ActionRole)
        ok_btn = box.addButton(QMessageBox.Ok)
        box.exec_()
        
        #ログを開くボタンが押されたら　OS 既定アプリで開く
        try:
            if log_path and open_btn is not None and box.clickedButton() == open_btn:
                QDesktopServices.openUrl(QUrl.fromLocalFile(log_path))
        except Exception:
            #開けなくてもアプリを落とさない
            pass

    def _on_worker_error(self, tb: str):
        QMessageBox.critical(self, 'エラー', tb)

    def _on_worker_confirm(self, message: str):
        # Yes/No をユーザーに問い合わせ、回答を現在のワーカーへ返す
        res = QMessageBox.question(self, '確認', message, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        try:
            worker = getattr(self, '_current_worker', None)
            if worker is not None:
                worker.set_user_decision(res == QMessageBox.Yes)
        except Exception:
            pass

    # ---------- 進捗ダイアログ制御 ----------
    def _open_progress(self, title: str, label: str, worker=None):
        # 既存があれば閉じる
        try:
            if hasattr(self, '_progress_dlg') and self._progress_dlg is not None:
                self._progress_dlg.close()
        except Exception:
            pass
        dlg = QProgressDialog(label, 'キャンセル', 0, 0, self)
        dlg.setWindowTitle(title)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.setMinimumWidth(420)
        dlg.setModal(True)
        # 0,0 は不確定（インジケータ）表示
        dlg.setRange(0, 0)
        # キャンセルクリック → ワーカーの cancel() スロットへ
        if worker is not None:
            dlg.canceled.connect(worker.cancel)
        self._progress_dlg = dlg
        dlg.show()

    def _update_progress(self, n: int):
        # 不確定進捗でもラベルを更新
        try:
            if hasattr(self, '_progress_dlg') and self._progress_dlg is not None:
                self._progress_dlg.setLabelText(f"処理中… 進捗: {n}")
        except Exception:
            pass

    def _close_progress(self):
        # 完了/エラー/キャンセルのいずれでも必ず閉じて参照を破棄
        try:
            if hasattr(self, '_progress_dlg') and self._progress_dlg is not None:
                self._progress_dlg.reset()
                self._progress_dlg.close()
        except Exception:
            pass
        self._progress_dlg = None

    # ---------- PDFインポート ----------
    # PDF ファイル選択 → QThread + ImportPDFWorker を起動
    def _import_pdf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, 'PDFファイルを選択', '', 'PDF Files (*.pdf)')
        if not path:
            return

    # ★ 同時起動ガード
        if getattr(self, "_current_worker", None):
            QMessageBox.warning(self, "実行中", "処理中の取り込みが完了するまでお待ちください。")
            return

        try:
            db_path = self._ensure_repo_db_path()
        except Exception as e:
            QMessageBox.critical(self, 'エラー', str(e))
            return
        #スレッドを作成し、ワーカーを所属させる。スレッドの起動準備
        thread = QThread(self)
        worker = ImportPDFWorker(db_path=db_path, pdf_path=path)
        worker.moveToThread(thread)
        #スレッドがスタートしたらワーカーのrun起動する
        thread.started.connect(worker.run)

    # ワーカーが終了したらワーカーとスレッドを破棄してメモリを軽くする
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._connect_common_worker_signals(worker, thread, title='PDF取り込み中', label='PDF を解析しています…')

        def _pdf_finished(sigs: int, boxes: int):
            parts = []
            if sigs:
                parts.append(f'信号 {sigs} 件')
            if boxes:
                parts.append(f'BOX配線 {boxes} 件')
            if parts:
                QMessageBox.information(self, 'PDFインポート', ' / '.join(parts) + ' を取り込みました。')
            else:
                QMessageBox.warning(self, 'PDFインポート', '取り込めるデータが見つかりませんでした。')
            self.search_component.refresh()
        # ★ UIの完了通知後に、ここでも参照を解除（同時起動ガードの解除）
            self._current_worker = None
            self._current_thread = None
        worker.finished.connect(_pdf_finished)

    # ★ スレッド完全終了時にワーカーとスレッドを元に戻す。インポート中ならNoneになるので二重起動にならない
        thread.finished.connect(lambda: setattr(self, '_current_worker', None))
        thread.finished.connect(lambda: setattr(self, '_current_thread', None))

        #ここがインポートのスタート地点。ここからワーカーを走らせる
        self._current_thread = thread
        self._current_worker = worker
        thread.start()
    

    # ---------- CSVインポート / テンプレ出力 ----------
    def _import_csv_signals(self):
        path, _ = QFileDialog.getOpenFileName(self, 'signals.csv を選択', '', 'CSV Files (*.csv)')
        if not path:
            return

        # 同時起動をガード。他のスレッドが動いていないか確認（動いていなければNoneが返ってくる）
        if getattr(self, "_current_worker", None):
            QMessageBox.warning(self, "実行中", "処理中の取り込みが完了するまでお待ちください。")
            return
        try:
            db_path = self._ensure_repo_db_path()
        except Exception as e:
            QMessageBox.critical(self, 'エラー', str(e))
            return

        thread = QThread(self)
        worker = ImportCSVWorker(db_path=db_path, csv_path=path, mode='signals')
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        # finishが呼ばれたらスレッドを安全な位置で破棄
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._connect_common_worker_signals(worker, thread, title='CSV取り込み中（信号）', label='signals.csv を読み込んでいます…')
        #取り込み中に起きた軽微なエラーを報告
        def _csv_finished(n: int):
            if n == 0:
                QMessageBox.warning(self, 'CSVインポート', '取り込めるレコードがありませんでした。')
            else:
                QMessageBox.information(self, 'CSVインポート', f'信号 {n} 件を取り込みました。')
            self.search_component.refresh()
            # 参照解除
            self._current_worker = None
            self._current_thread = None
        worker.finished.connect(_csv_finished)
        #スレッドとワーカーをNoneに戻す
        thread.finished.connect(lambda: setattr(self, '_current_worker', None))
        thread.finished.connect(lambda: setattr(self, '_current_thread', None))
        #インポートの発火地点
        self._current_thread = thread
        self._current_worker = worker
        thread.start()

    def _import_csv_box(self):
        path, _ = QFileDialog.getOpenFileName(self, 'box_connections.csv を選択', '', 'CSV Files (*.csv)')
        if not path:
            return
        
        # ★ 同時起動ガード
        if getattr(self, "_current_worker", None):
            QMessageBox.warning(self, "実行中", "処理中の取り込みが完了するまでお待ちください。")
            return

        try:
            db_path = self._ensure_repo_db_path()
        except Exception as e:
            QMessageBox.critical(self, 'エラー', str(e))
            return

        thread = QThread(self)
        worker = ImportCSVWorker(db_path=db_path, csv_path=path, mode='box')
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        # ★ 後始末
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._connect_common_worker_signals(worker, thread, title='CSV取り込み中（BOX配線）', label='box_connections.csv を読み込んでいます…')

        def _box_finished(n: int):
            if n == 0:
                QMessageBox.warning(self, 'CSVインポート', '取り込めるレコードがありませんでした。')
            else:
                QMessageBox.information(self, 'CSVインポート', f'BOX配線 {n} 件を取り込みました。')
        # ★ 参照解除（BOXは検索再描画なしでOKという現仕様のまま）
            self._current_worker = None
            self._current_thread = None
        worker.finished.connect(_box_finished)

        thread.finished.connect(lambda: setattr(self, '_current_worker', None))
        thread.finished.connect(lambda: setattr(self, '_current_thread', None))

        self._current_thread = thread
        self._current_worker = worker
        thread.start()

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

#-------------ログファイルの作成処理-------------
    def _open_app_log(self): 
        """アプリ全体ログ（~/.mt_signal_search/logs/app.log)をOS既定アプリで開く"""
        from pathlib import Path
        try:
            log_path = Path.home() / ".mt_signal_search" / "logs" / "app.log"
            if not log_path.exists():
                QMessageBox.information(
                    self, "ログ",
                    "まだログファイルが作成されていません。\(n(CSV/PDFの取り込みを一度実行すると作成されます。)"
                    )
                return
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_path)))
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"ログを開けませんでした: {e}")