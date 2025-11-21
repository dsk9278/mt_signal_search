from mt_signal_search.repositories.base import SignalRepository, FavoritesRepository


class SignalSearchService:
    def __init__(self, signal_repository: SignalRepository):
        self._signal_repository = signal_repository

    def search_signals(self, keyword: str):
        kw = (keyword or "").strip()
        return self._signal_repository.search_signals(kw) if kw else []

    def get_signals_for_logic(self, logic_name: str):
        return self._signal_repository.get_signals_by_logic_group(logic_name)

    def get_logic_expr(self, signal_id: str):
        return self._signal_repository.get_logic_expr(signal_id)

    def set_logic_expr(
        self, signal_id: str, raw_expr: str, source_label: str = "(ui)", source_page: int = None
    ):
        """UIからの条件式登録はソース不明として扱い、編集内容を登録する。"""
        return self._signal_repository.add_logic_equation(
            signal_id, raw_expr, source_label, source_page
        )

    def get_source_label(self, signal_id: str):
        return self._signal_repository.get_source_label(signal_id)


class FavoritesService:
    def __init__(self, repo: FavoritesRepository):
        self._repo = repo

    def toggle_favorite(self, logic_name: str) -> bool:
        return (
            self._repo.remove_favorite(logic_name)
            if self._repo.is_favorite(logic_name)
            else self._repo.add_favorite(logic_name)
        )

    def get_favorites(self):
        return self._repo.get_favorites()

    def is_favorite(self, logic_name: str):
        return self._repo.is_favorite(logic_name)


class LogicManagementService:
    def __init__(self, signal_repository: SignalRepository):
        self._signal_repository = signal_repository

    def get_all_logic_groups(self):
        return self._signal_repository.get_all_logic_groups()

    def get_logic_details(self, logic_name: str):
        return self._signal_repository.get_signals_by_logic_group(logic_name)
