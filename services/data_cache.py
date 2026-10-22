"""Parsed-data cache: the same file + codebook is parsed once per worker, not on every request.

The web app's live previews send the same file many times a minute; parsing a .sav (or coding
an Excel/CSV through its codebook) is the slow part of each request. Entries are keyed by the
file's bytes (sha256), its format and the codebook applied, expire with the file session TTL,
and are evicted oldest-first past a memory budget (settings.parsed_cache_mb).

Callers get their own copy (DataFrame + metadata), because tabulation adds columns
(_total_, custom groups) and value labels to the data it's given.
"""

import copy
import hashlib
import logging
import threading
import time
from collections import OrderedDict

from config import get_settings
from services.codebook.model import Codebook
from services.data_loader import file_format, load_data
from services.quantipy_engine import SPSSData

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_entries: "OrderedDict[tuple, tuple[float, int, SPSSData]]" = OrderedDict()  # key → (stored at, bytes, data)
stats = {"hits": 0, "misses": 0}


def _key(file_bytes: bytes, filename: str, codebook: Codebook | None) -> tuple:
    cb = hashlib.sha256(codebook.model_dump_json().encode()).hexdigest() if codebook is not None else ""
    return hashlib.sha256(file_bytes).hexdigest(), file_format(filename), cb


def _copy(data: SPSSData) -> SPSSData:
    return SPSSData(df=data.df.copy(), meta=copy.deepcopy(data.meta),
                    mrx_dataset=data.mrx_dataset, file_name=data.file_name)


def _size(data: SPSSData) -> int:
    return int(data.df.memory_usage(deep=True).sum())


def load_data_cached(file_bytes: bytes, filename: str = "upload.sav", codebook: Codebook | None = None) -> SPSSData:
    """load_data(), parsed once per worker. Blocking — call via run_in_executor()."""
    settings = get_settings()
    budget = settings.parsed_cache_mb * 1024 * 1024
    if budget <= 0:
        return load_data(file_bytes, filename, codebook)
    key = _key(file_bytes, filename, codebook)
    now = time.monotonic()
    with _lock:
        hit = _entries.get(key)
        if hit and now - hit[0] < settings.spss_session_ttl_seconds:
            _entries.move_to_end(key)
            stats["hits"] += 1
            return _copy(hit[2])
        if hit:
            del _entries[key]
    stats["misses"] += 1
    data = load_data(file_bytes, filename, codebook)  # parse outside the lock
    size = _size(data)
    if size <= budget:
        with _lock:
            _entries[key] = (now, size, data)
            _entries.move_to_end(key)
            while sum(e[1] for e in _entries.values()) > budget:
                old, _ = _entries.popitem(last=False)
                logger.info("Parsed-data cache: evicted %s", old[0][:12])
    return _copy(data)


def clear() -> None:
    with _lock:
        _entries.clear()
        stats.update(hits=0, misses=0)
