"""UUIDv7 generation (time ordered), RFC 9562. Python 3.12 has no uuid.uuid7()."""

import os
import threading
import time
from uuid import UUID

_MAX_COUNTER = 0xFFF  # 12 bits of rand_a are used as a per millisecond counter
_lock = threading.Lock()
_last_ms = 0
_counter = 0


def uuid7() -> UUID:
    """Return a time ordered UUID: 48 bit unix ms timestamp, version 7, random tail.

    Values created inside the same millisecond keep their order because ``rand_a`` is
    used as a counter (RFC 9562, monotonic random). Useful as a primary key: inserts
    stay at the right edge of the index instead of scattering like uuid4.
    """
    global _last_ms, _counter

    with _lock:
        now_ms = time.time_ns() // 1_000_000
        if now_ms > _last_ms:
            _last_ms = now_ms
            _counter = int.from_bytes(os.urandom(2), "big") & 0x0FF  # leave room to grow
        else:
            _counter += 1
            if _counter > _MAX_COUNTER:
                # Counter exhausted: borrow the next millisecond rather than repeat one.
                _last_ms += 1
                _counter = 0
            now_ms = _last_ms
        counter = _counter

    rand_b = int.from_bytes(os.urandom(8), "big") & 0x3FFFFFFFFFFFFFFF
    value = (now_ms & 0xFFFFFFFFFFFF) << 80
    value |= 0x7 << 76
    value |= counter << 64
    value |= 0b10 << 62
    value |= rand_b
    return UUID(int=value)
