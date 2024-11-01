from copy import copy
from typing import List, Optional, Tuple

_mask = 0xFFFF_FFFF


def _precalc(a: int, b: int) -> List[Tuple[int, int]]:
    cache = []
    for i in range(0, 32):
        cache.append((a, b))
        a, b = a * a & _mask, (b * (1 + a)) & _mask
    return cache


def _calc_index(seed: int, a: int, b: int, order: int) -> int:
    if order == 0:
        return 0

    if (seed & 1) == 0:
        a, b = (a * a) & _mask, (((a + 1) * b) & _mask) // 2
        return _calc_index(seed // 2, a, b, order - 1) * 2
    else:
        seed = (a * seed + b) & _mask
        a, b = (a * a) & _mask, (((a + 1) * b) & _mask) // 2
        return _calc_index(seed // 2, a, b, order - 1) * 2 - 1


def define_lcg(a: int, b: int):
    """
    LCGの乗算定数`a`と加算定数`b`を指定してLCGクラスを生成します.
    最大周期にならないパラメータが渡された場合、例外が投げられます.
    """
    assert a % 4 == 1 and b % 2 == 1

    doubling = _precalc(a, b)

    a_rev, b_rev = 1, 0
    for _a, _b in doubling:
        b_rev = (b_rev + (a_rev * _b)) & _mask
        a_rev = (a_rev * _a) & _mask

    def _next(seed: int) -> int:
        return (a * seed + b) & _mask

    def _prev(seed: int) -> int:
        return (a_rev * seed + b_rev) & _mask

    def _jump(seed: int, n: int) -> int:
        for i in range(0, 32):
            if n & (1 << i):
                a, b = doubling[i]
                seed = (seed * a + b) & _mask
        return seed

    def _get_index(seed) -> int:
        return _calc_index(seed, a, b, 32)

    class LCG(object):
        def __init__(self, seed: int, offset: int = 0) -> None:
            offset &= _mask
            self._cnt: int = offset
            self.seed: int = _jump(seed, offset) if offset else seed

        def clone(self):
            return copy(self)

        def adv(self, n: Optional[int] = None):
            if n is None:
                self._cnt = (self._cnt + 1) & _mask
                self.seed = _next(self.seed)
                return self
            else:
                self._cnt = (self._cnt + n) & _mask
                self.seed = _jump(self.seed, n)
                return self

        def back(self, n: Optional[int] = None):
            if n is None:
                self._cnt = (self._cnt - 1) & _mask
                self.seed = _prev(self.seed)
                return self
            else:
                self._cnt = (self._cnt - n) & _mask
                self.seed = _jump(self.seed, (-n) & _mask)
                return self

        def rand(self, m: Optional[int] = None) -> int:
            rand = self.adv().seed >> 16
            return rand % m if m is not None else rand

        @property
        def index(self) -> int:
            return self._cnt

        def index_from(self, init_seed: int) -> int:
            return self.get_index(self.seed, init_seed)

        @staticmethod
        def gen_seed(seed: int, take: Optional[int] = None):
            if take is None:
                while True:
                    yield seed
                    seed = _next(seed)
            else:
                for _ in range(0, take):
                    yield seed
                    seed = _next(seed)

        @staticmethod
        def get_index(seed: int, init_seed: int) -> int:
            idx = _get_index(seed)
            base = _get_index(init_seed)
            return (idx - base) & _mask

    return LCG
