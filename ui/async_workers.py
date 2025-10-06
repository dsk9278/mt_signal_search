# -*- coding: utf-8 -*-
"""
ui/async_workers.py

役割:
    - 長時間処理（CSV/PDFインポート）を **別スレッド** で実行するワーカー群。
    - importer(I/O層) と repository(DB層) の橋渡しを行い、
      UI に対して以下のイベントをシグナルで通知する。

提供シグナル:
    - started()               : 処理開始
    - progress(int)           : 進捗（ページ数や件数など、呼び出し側の文脈で利用）
    - ask_confirm(str)        : 致命的エラー時に「続行/中止」をユーザーに確認するためのメッセージ
    - report(str, str)        : 警告のサマリとログファイルのパス（summary, log_path）
    - finished(...)           : 正常終了（CSV: 件数 / PDF: (signals, box_conns)）
    - error(str)              : 例外全文（traceback含む）
    - canceled()              : キャンセル終了

使い方(例):
    thread = QThread()
    worker = ImportCSVWorker(db_path, csv_path, mode="signals")
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(lambda n: thread.quit())
    worker.error.connect(lambda e: thread.quit())
    thread.start()

設計ポイント:
    - importer 側は UI 非依存の純粋関数 (process/import_file)。
      progress_cb / cancel_cb を渡すことで非同期制御できる。
    - 本ファイルは UI と importer の間で「進捗・キャンセル・確認・レポート」
      を仲介するだけに徹する。
"""

from __future__ import annotations

from typing import Optional, List
import os
import datetime
import traceback
import logging

from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot, QEventLoop

from mt_signal_search.repositories.sqlite_impl import SQLiteSignalRepository
from mt_signal_search.io_importers.csv_importers import (
    CSVSignalImporter,
    CSVBoxConnImporter,
)
from mt_signal_search.io_importers.pdf_importers import (
    SimplePDFProcessor,
    BoxPDFProcessor,
)


# ------------------------------------------------------------
# 共通のヘルパー
# ------------------------------------------------------------

def _now_tag() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def _ensure_log_dir() -> str:
    log_dir = os.path.join(os.path.expanduser("~"), "mt_signal_logs")
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


# ------------------------------------------------------------
# CSV インポート用ワーカー
# ------------------------------------------------------------
class ImportCSVWorker(QObject):
    # UIへ通知するシグナル
    started = pyqtSignal()
    progress = pyqtSignal(int)
    ask_confirm = pyqtSignal(str)   # UIでYes/Noを聞き、set_user_decision()で返す
    report = pyqtSignal(str, str)   # (summary, log_path)
    finished = pyqtSignal(int)      # インポート件数
    error = pyqtSignal(str)
    canceled = pyqtSignal()

    def __init__(self, db_path: str, csv_path: str, mode: str = "signals") -> None:
        super().__init__()
        self.db_path = db_path
        self.csv_path = csv_path
        self.mode = mode  # "signals" or "box"
        self._cancel = False
        self._decision: Optional[bool] = None  # ユーザー回答
        self._warnings: List[str] = []
        self._log = logging.getLogger(f"mt_signal.import.{self.__class__.__name__}")

    # ---- UIからキャンセル/回答を受け取るスロット ----
    @pyqtSlot()
    def cancel(self):
        self._cancel = True

    @pyqtSlot(bool)
    def set_user_decision(self, ok: bool):
        # _confirm() 内のローカルイベントループを抜けるための回答
        self._decision = bool(ok)
        try:
            # ここで loop.quit() を直接呼べないため、_confirm 内でポーリングせず
            # ループ参照を閉じている（後述）。
            pass
        except Exception:
            pass

    # ---- 内部ユーティリティ ----
    def _confirm(self, message: str) -> bool:
        """致命的エラー発生時、UIにYes/Noを問い合わせて同期待ちする。
        QEventLoop を用いる。UI側は ask_confirm を受けて QMessageBox で質問し、
        set_user_decision(True/False) を呼ぶことで回答を返す。
        """
        self._decision = None
        self.ask_confirm.emit(message)
        loop = QEventLoop()

        # set_user_decision が呼ばれるまで待つ
        # QEventLoop を終了させるタイミングは、以下のtickで監視する
        from PyQt5.QtCore import QTimer
        def _tick():
            if self._decision is not None:
                loop.quit()
        timer = QTimer()
        timer.timeout.connect(_tick)
        timer.start(50)
        loop.exec_()
        timer.stop()
        return bool(self._decision)

    def _write_warnings_log(self, prefix: str, warnings: List[str]) -> str:
        log_dir = _ensure_log_dir()
        path = os.path.join(log_dir, f"{prefix}_import_{_now_tag()}.log")
        with open(path, "w", encoding="utf-8") as f:
            for w in warnings:
                f.write(w.rstrip() + "\n")
        return path

    # ---- 進捗/キャンセルコールバック（importer に渡す）----
    def _progress_cb(self, n: int):
        self.progress.emit(int(n))

    def _cancel_cb(self) -> bool:
        return self._cancel

    # ---- メイン処理 ----
    @pyqtSlot()
    def run(self):
        self.started.emit()
        try:
            self._log.info("CSV import start: path=%s mode=%s", self.csv_path, self.mode)
            repo = SQLiteSignalRepository(self.db_path)
            imported = 0
            try:
                if self.mode == "signals":
                    importer = CSVSignalImporter(repo)
                    imported = importer.import_file(self.csv_path, progress_cb=self._progress_cb, cancel_cb=self._cancel_cb)
                else:
                    importer = CSVBoxConnImporter(repo)
                    imported = importer.import_file(self.csv_path, progress_cb=self._progress_cb, cancel_cb=self._cancel_cb)
            except Exception as e:
                # 致命的（ファイル壊れ/列不整合など）: ユーザーに続行(=スキップ)か中止かを確認、_confirmでユーザーの回答を待つ
                if self._confirm(f"CSV取り込み中に致命的エラーが発生しました。\n{e}\n\nこのファイルをスキップして続行しますか？"):
                    self._warnings.append(str(e))
                    imported = 0
                else:
                    raise

            if self._cancel:
                self.canceled.emit()
                return

            # importer 側で行単位の軽微エラーを warnings に溜める設計であれば拾う
            try:
                wlist = getattr(importer, "warnings", None)
                if wlist:
                    self._warnings.extend([str(w) for w in wlist])
            except Exception:
                pass

            if self._warnings:
                self._log.warning("CSV import warnings: count=%d", len(self._warnings))
                log_path = self._write_warnings_log("csv", self._warnings)
                self.report.emit(f"警告 {len(self._warnings)} 件（詳細はログ参照）", log_path)
            self._log.info("CSV import done: imported=%d", imported)
            self.finished.emit(int(imported))

        except Exception:
            self._log_exception("CSV import failed")
            self.error.emit(traceback.format_exc())



# ------------------------------------------------------------
# PDF インポート用ワーカー
# ------------------------------------------------------------
class ImportPDFWorker(QObject):
    started = pyqtSignal()
    progress = pyqtSignal(int)
    ask_confirm = pyqtSignal(str)
    report = pyqtSignal(str, str)
    finished = pyqtSignal(int, int)  # (signals, box_conns)
    error = pyqtSignal(str)
    canceled = pyqtSignal()

    def __init__(self, db_path: str, pdf_path: str) -> None:
        super().__init__()
        self.db_path = db_path
        self.pdf_path = pdf_path
        self._cancel = False
        self._decision: Optional[bool] = None
        self._warnings: List[str] = []
        self._log = logging.getLogger(f"mt_signal.import.{self.__class__. __name__}")

    @pyqtSlot()
    def cancel(self):
        self._cancel = True

    @pyqtSlot(bool)
    def set_user_decision(self, ok: bool):
        self._decision = bool(ok)

    def _confirm(self, message: str) -> bool:
        self._decision = None
        self.ask_confirm.emit(message)
        loop = QEventLoop()
        from PyQt5.QtCore import QTimer
        def _tick():
            if self._decision is not None:
                loop.quit()
        timer = QTimer()
        timer.timeout.connect(_tick)
        timer.start(50)
        loop.exec_()
        timer.stop()
        return bool(self._decision)

    def _write_warnings_log(self, prefix: str, warnings: List[str]) -> str:
        log_dir = _ensure_log_dir()
        path = os.path.join(log_dir, f"{prefix}_import_{_now_tag()}.log")
        with open(path, "w", encoding="utf-8") as f:
            for w in warnings:
                f.write(w.rstrip() + "\n")
        return path

    def _progress_cb(self, n: int):
        self.progress.emit(int(n))

    def _cancel_cb(self) -> bool:
        return self._cancel

    @pyqtSlot()
    def run(self):
        self.started.emit()
        try:
            self._log.info("PDF import start: path=%s", self.pdf_path)
            repo = SQLiteSignalRepository(self.db_path)

            # 1) 信号式の抽出
            sig_count = 0
            processor = SimplePDFProcessor()
            try:
                signals = processor.process(self.pdf_path, progress_cb=self._progress_cb, cancel_cb=self._cancel_cb)
            except Exception as e:
                if self._confirm(f"PDF取り込み中に致命的エラーが発生しました。\n{e}\n\nこのファイルをスキップして続行しますか？"):
                    self._warnings.append(str(e))
                    signals = []
                else:
                    raise

            # DB保存（キャンセル可能）
            for s in signals:
                if self._cancel:
                    self.canceled.emit()
                    return
                try:
                    repo.add_signal(s)
                    sig_count += 1
                except Exception as ee:
                    self._warnings.append(f"signal保存失敗: {s.signal_id}: {ee}")

            for sid, raw in processor.logic_blocks.items():
                try:
                    # 出所ラベルにPDFパスを残す
                    try:
                        repo.add_logic_equation(sid, raw, source_label=self.pdf_path, source_page=None)
                    except TypeError:
                        repo.add_logic_equation(sid, raw, source_label=self.pdf_path)
                except Exception as ee:
                    self._warnings.append(f"式保存失敗: {sid}: {ee}")

            # 2) BOX配線（同じPDFに含まれる場合だけ。別PDFなら別ワーカーでOK）
            box_count = 0
            try:
                box_proc = BoxPDFProcessor()
                try:
                    conns = box_proc.process(self.pdf_path, progress_cb=self._progress_cb, cancel_cb=self._cancel_cb)
                except Exception as e2:
                    if self._confirm(f"BOX配線の抽出で致命的エラーが発生しました。\n{e2}\n\nBOX配線の抽出をスキップして続行しますか？"):
                        self._warnings.append(f"BOX抽出失敗: {e2}")
                        conns = []
                    else:
                        raise

                for bc in conns:
                    if self._cancel:
                        self.canceled.emit()
                        return
                    try:
                        repo.add_box_connection(bc)
                        box_count += 1
                    except Exception as ee:
                        self._warnings.append(f"BOX保存失敗: {bc}: {ee}")
            except Exception:
                # BoxPDFProcessor が未整備の環境でも落とさない
                pass

            # warnings をまとめてログ
            if self._warnings:
                self._log.warning("PDF import warnings: count=%d", len(self._warnings))
                log_path = self._write_warnings_log("pdf", self._warnings)
                self.report.emit(f"警告 {len(self._warnings)} 件（詳細はログ参照）", log_path)

            self._log.info("PDF import done: signals=%d box_conns=%d", sig_count,box_count)
            self.finished.emit(int(sig_count), int(box_count))

        except Exception:
            self._log.exception("PDF import failed")
            self.error.emit(traceback.format_exc())
