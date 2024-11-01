import clr
import os
from typing import List, Tuple, Union
from System import ValueTuple


dll = os.path.join(os.path.dirname(__file__), "PokemonCOSeedDataBaseAPI.dll")
try:
    clr.AddReference(dll)
    from PokemonCOSeedDataBaseAPI import SeedSearcher, PlayerName, BattleTeam
except Exception as e:
    raise ImportError(f"DLL の読み込みに失敗しました: {dll}\n {e}")


class SeedSearcherWrapper:
    def __init__(self, db_path, mode="light"):
        if mode == "full":
            self.searcher = SeedSearcher.CreateFullDBSearcher(db_path)
            self._specified_number_of_key = 7
        elif mode == "light":
            self.searcher = SeedSearcher.CreateLightDBSearcher(db_path)
            self._specified_number_of_key = 8
        else:
            raise ValueError(f"無効なモードです: {mode}. 'light' または 'full' を指定してください")

    @property
    def specified_number_of_key(self):
        return self._specified_number_of_key

    def search(self, keys: List[Union[Tuple[int, int]]]) -> List[int]:
        keys = [ValueTuple[PlayerName, BattleTeam](PlayerName(key[0]), BattleTeam(key[1])) for key in keys]
        results = list(self.searcher.Search(keys))
        return results
