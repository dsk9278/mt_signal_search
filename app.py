import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont
from mt_signal_search.repositories.sqlite_impl import SQLiteSignalRepository
from mt_signal_search.repositories.favorites_json import JsonFavoritesRepository
from mt_signal_search.services.services import (
    SignalSearchService, FavoritesService, LogicManagementService
)
from mt_signal_search.ui.main_window import MainWindow

class SignalTraceApplication:
    def run(self) -> int:
        app = QApplication(sys.argv)
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