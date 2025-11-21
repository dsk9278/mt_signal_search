import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont
from mt_signal_search.repositories.sqlite_impl import SQLiteSignalRepository
from mt_signal_search.repositories.favorites_json import JsonFavoritesRepository
from mt_signal_search.services.services import (
    SignalSearchService,
    FavoritesService,
    LogicManagementService,
)
from mt_signal_search.ui.main_window import MainWindow


def _setup_logging():
    """アプリ共通のロガーを初期化する処理。 ~/.mt_signal_search/logs/app.log にINFO以上をローテーション保存"""
    log_dir = Path.home() / ".mt_signal_search" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "app.log"

    root = logging.getLogger()
    # すでに　RotatingFileHandlerがついている場合は二重設定しない。
    # アプリを開いてロガーが初期されるたびに同じログが重複して記録していくのを防ぐ。同じログが記録されるのを防ぐ役割
    if any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        return

    root.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = RotatingFileHandler(str(log_path), maxBytes=2_000_000, backupCount=10, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)


class SignalTraceApplication:
    def run(self) -> int:
        _setup_logging()
        app = QApplication(sys.argv)
        logging.getLogger(__name__).info("Application started")
        font = QFont("Yu Gothic UI", 9)
        app.setFont(font)
        app.setStyleSheet("""
            QMainWindow { background-color: white; }
            QPushButton, QLabel { font-family: "Yu Gothic UI"; }
        """)

        # 依存関係の組み立て（Composition Root）
        repo = SQLiteSignalRepository()
        fav_repo = JsonFavoritesRepository()

        search_service = SignalSearchService(repo)
        favorites_service = FavoritesService(fav_repo)
        logic_service = LogicManagementService(repo)

        # MainWindow にサービスとリポジトリを注入
        w = MainWindow(search_service, favorites_service, logic_service, repo)
        w.show()
        return app.exec_()
