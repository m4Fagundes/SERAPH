"""
Pure-Python shim for the nifty C++ graph library.

nifty (https://github.com/constantinpape/nifty) is only available via conda-forge
and cannot be installed with pip. This shim provides working implementations of
the nifty API surface used by elf.parallel (which micro_sam depends on):

    nifty.tools.blocking(begin, end, block_shape)
    nifty.tools.take(lut, indices)
    nifty.tools.takeDict(mapping_dict, arr)
    nifty.ufd.ufd(n)  →  UnionFind with .merge(pairs), .find(labels)

Inject before any elf/micro_sam import:
    from app.infrastructure.ml_models._nifty_shim import inject
    inject()
"""

import sys
import types
import itertools

import numpy as np


# ── nifty.tools.blocking ─────────────────────────────────────────────────────

class _Block:
    __slots__ = ("begin", "end")

    def __init__(self, begin, end):
        self.begin = list(begin)
        self.end = list(end)


class _Blocking:
    def __init__(self, begin, end, block_shape):
        self._begin = list(begin)
        self._end = list(end)
        self._block_shape = list(block_shape)
        self.blockShape = tuple(block_shape)

        self._blocks: list[_Block] = []
        self._grid_dims: list[int] = []
        self._build()
        self.numberOfBlocks = len(self._blocks)

    def _build(self):
        ranges = [range(b, e, s) for b, e, s in zip(self._begin, self._end, self._block_shape)]
        self._grid_dims = [len(r) for r in ranges]
        for starts in itertools.product(*ranges):
            ends = [min(s + bs, e) for s, bs, e in zip(starts, self._block_shape, self._end)]
            self._blocks.append(_Block(list(starts), list(ends)))

    def getBlock(self, block_id: int) -> _Block:
        return self._blocks[block_id]

    def getBlockWithHalo(self, block_id: int = None, halo=None, blockIndex: int = None) -> types.SimpleNamespace:
        if block_id is None:
            block_id = blockIndex
        if block_id is None:
            raise TypeError("getBlockWithHalo requires block_id or blockIndex")
        if halo is None:
            halo = [0] * len(self._begin)

        block = self.getBlock(block_id)
        outer_begin = [max(b0, b - h) for b0, b, h in zip(self._begin, block.begin, halo)]
        outer_end = [min(e0, e + h) for e0, e, h in zip(self._end, block.end, halo)]
        inner_local_begin = [b - ob for b, ob in zip(block.begin, outer_begin)]
        inner_local_end = [e - ob for e, ob in zip(block.end, outer_begin)]
        outer_block = _Block(outer_begin, outer_end)
        return types.SimpleNamespace(
            innerBlock=block,
            outerBlock=outer_block,
            innerBlockLocal=_Block(inner_local_begin, inner_local_end),
            outerBlockLocal=_Block([0] * len(outer_begin), [e - b for b, e in zip(outer_begin, outer_end)]),
        )

    def getNeighborId(self, block_id: int, axis: int, lower: bool) -> int:
        """Return the linear block id of the neighbor along `axis`, or -1 if out of bounds."""
        dims = self._grid_dims
        ndim = len(dims)

        # Decode linear id to per-axis coords
        coords = []
        remaining = block_id
        for d in reversed(dims):
            coords.insert(0, remaining % d)
            remaining //= d

        coords[axis] += -1 if lower else 1

        if not (0 <= coords[axis] < dims[axis]):
            return -1

        linear = 0
        for c, d in zip(coords, dims):
            linear = linear * d + c
        return linear


def _blocking(begin, end, block_shape):
    return _Blocking(begin, end, block_shape)


# ── nifty.tools.take / takeDict ───────────────────────────────────────────────

def _take(lut, indices):
    """Lookup-table application: equivalent to lut[indices]."""
    return np.asarray(lut)[indices]


def _takeDict(mapping_dict: dict, arr: np.ndarray) -> np.ndarray:
    """Apply a {old: new} dict mapping to every element of arr."""
    if not mapping_dict:
        return arr.copy()

    # Build a dense LUT for speed
    keys = np.array(list(mapping_dict.keys()), dtype=np.int64)
    vals = np.array(list(mapping_dict.values()), dtype=np.int64)
    max_key = int(keys.max())

    lut = np.arange(max_key + 1, dtype=np.int64)
    for k, v in zip(keys, vals):
        if 0 <= k <= max_key:
            lut[k] = v

    flat = arr.ravel().astype(np.int64)
    out = np.where(flat <= max_key, lut[np.minimum(flat, max_key)], flat)
    return out.reshape(arr.shape).astype(arr.dtype)


# ── nifty.ufd ────────────────────────────────────────────────────────────────

class _UnionFind:
    """Union-Find (disjoint-set) with path compression and union by rank."""

    def __init__(self, n: int):
        self._parent = np.arange(n, dtype=np.uint64)
        self._rank = np.zeros(n, dtype=np.uint64)

    def _find_one(self, x: int) -> int:
        root = x
        while self._parent[root] != root:
            root = int(self._parent[root])
        # Path compression
        while self._parent[x] != root:
            nxt = int(self._parent[x])
            self._parent[x] = root
            x = nxt
        return root

    def merge(self, pairs: np.ndarray) -> None:
        """Merge each (a, b) pair in the Nx2 array."""
        for a, b in pairs:
            ra = self._find_one(int(a))
            rb = self._find_one(int(b))
            if ra == rb:
                continue
            if self._rank[ra] < self._rank[rb]:
                ra, rb = rb, ra
            self._parent[rb] = ra
            if self._rank[ra] == self._rank[rb]:
                self._rank[ra] += 1

    def find(self, labels: np.ndarray) -> np.ndarray:
        """Return the representative for each element in `labels`."""
        result = np.empty_like(labels)
        for i, x in enumerate(labels.ravel()):
            result.ravel()[i] = self._find_one(int(x))
        return result


def _ufd(n: int) -> _UnionFind:
    return _UnionFind(n)


# ── nifty.ground_truth.overlap ───────────────────────────────────────────────

class _Overlap:
    def __init__(self, source: np.ndarray, target: np.ndarray):
        self._source = np.asarray(source)
        self._target = np.asarray(target)

    def overlapArrays(self, label_id: int, sorted: bool = True):
        mask = self._source == label_id
        ids, counts = np.unique(self._target[mask], return_counts=True)
        if sorted and len(counts):
            order = np.argsort(counts)[::-1]
            ids, counts = ids[order], counts[order]
        return ids.astype(np.uint64), counts.astype(np.uint64)

    def overlapArraysNormalized(self, label_id: int, sorted: bool = True):
        ids, counts = self.overlapArrays(label_id, sorted=sorted)
        total = float(counts.sum())
        values = counts.astype("float64") / total if total > 0 else counts.astype("float64")
        return ids, values


def _overlap(source, target):
    return _Overlap(source, target)


# ── Injection ─────────────────────────────────────────────────────────────────

def inject() -> None:
    """Inject the nifty shim into sys.modules if nifty is not already installed."""
    if "nifty" in sys.modules:
        return

    try:
        import nifty  # noqa: F401
        return
    except ImportError:
        pass

    # Build module hierarchy
    nifty_mod = types.ModuleType("nifty")
    nifty_mod.__path__ = []
    tools_mod = types.ModuleType("nifty.tools")
    ufd_mod = types.ModuleType("nifty.ufd")
    ground_truth_mod = types.ModuleType("nifty.ground_truth")

    # Attach API
    tools_mod.blocking = _blocking
    tools_mod.take = _take
    tools_mod.takeDict = _takeDict
    tools_mod.takedDict = _takeDict  # typo variant used in relabel.py

    ufd_mod.ufd = _ufd
    ground_truth_mod.overlap = _overlap

    nifty_mod.tools = tools_mod
    nifty_mod.ufd = ufd_mod
    nifty_mod.ground_truth = ground_truth_mod

    sys.modules["nifty"] = nifty_mod
    sys.modules["nifty.tools"] = tools_mod
    sys.modules["nifty.ufd"] = ufd_mod
    sys.modules["nifty.ground_truth"] = ground_truth_mod
