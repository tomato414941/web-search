import copy
import json
import logging
import os
import time
from collections.abc import Callable
from typing import Any


class SharedJsonTtlCache:
    def __init__(self, path: str, *, logger: logging.Logger, label: str) -> None:
        self.path = path
        self._logger = logger
        self._label = label
        self._data: Any = None
        self._expires = 0.0
        self._key: Any = None

    def clear_memory(self) -> None:
        self._data = None
        self._expires = 0.0
        self._key = None

    def clear(self) -> None:
        self.clear_memory()
        try:
            os.remove(self.path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            self._logger.warning("Failed to clear %s: %s", self._label, exc)

    def get_memory(
        self, *, now: float | None = None, cache_key: Any = None
    ) -> Any | None:
        current = time.monotonic() if now is None else now
        if (
            self._data is not None
            and self._key == cache_key
            and current < self._expires
        ):
            return copy.deepcopy(self._data)
        return None

    def get_shared(
        self,
        *,
        cache_key: Any = None,
        validator: Callable[[Any], bool] | None = None,
    ) -> Any | None:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as exc:
            self._logger.warning("Failed to read %s: %s", self._label, exc)
            return None

        data = payload.get("data")
        expires_at = float(payload.get("expires_at", 0.0))
        remaining_ttl = expires_at - time.time()
        if payload.get("cache_key") != cache_key or remaining_ttl <= 0:
            return None
        if validator is not None and not validator(data):
            return None

        self._set_memory(data, remaining_ttl, cache_key)
        return copy.deepcopy(data)

    def set(self, data: Any, ttl: float, *, cache_key: Any = None) -> None:
        if ttl < 1:
            return

        serialized = json.loads(json.dumps(data, default=str))
        self._set_memory(serialized, ttl, cache_key)
        payload = {
            "expires_at": time.time() + ttl,
            "cache_key": cache_key,
            "data": serialized,
        }
        tmp_path = f"{self.path}.{os.getpid()}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
            os.replace(tmp_path, self.path)
        except OSError as exc:
            self._logger.warning("Failed to write %s: %s", self._label, exc)
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    def _set_memory(self, data: Any, ttl: float, cache_key: Any) -> None:
        if ttl < 1:
            return
        self._data = copy.deepcopy(data)
        self._expires = time.monotonic() + ttl
        self._key = copy.deepcopy(cache_key)
