import json
from mt_signal_search.repositories.base import FavoritesRepository

class JsonFavoritesRepository(FavoritesRepository):
    def __init__(self, file_path: str = "favorites.json"):
        self.file_path = file_path

    def get_favorites(self) -> list[str]:
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('favorites', [])
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def add_favorite(self, logic_name: str) -> bool:
        favs = self.get_favorites()
        if logic_name not in favs:
            favs.append(logic_name)
            self._save(favs)
            return True
        return False

    def remove_favorite(self, logic_name: str) -> bool:
        favs = self.get_favorites()
        if logic_name in favs:
            favs.remove(logic_name)
            self._save(favs)
            return True
        return False

    def is_favorite(self, logic_name: str) -> bool:
        return logic_name in self.get_favorites()

    def _save(self, favs: list[str]) -> None:
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump({'favorites': favs}, f, ensure_ascii=False, indent=2)