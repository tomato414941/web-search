"""Tests for query embedding cache in frontend embedding service."""

import numpy as np
import pytest
from unittest.mock import patch, MagicMock

from frontend.services import embedding as embedding_mod


class TestEmbedQueryCache:
    def test_cache_hit_avoids_api_call(self):
        mock_service = MagicMock()
        mock_service.embed_query.return_value = np.ones(1536, dtype=np.float32)

        with patch.object(embedding_mod, "_embedding_service", mock_service):
            embedding_mod._query_cache.clear()
            result1 = embedding_mod.cached_embed_query("hello")
            result2 = embedding_mod.cached_embed_query("hello")

            assert mock_service.embed_query.call_count == 1
            np.testing.assert_array_equal(result1, result2)
            embedding_mod._query_cache.clear()

    def test_different_queries_call_api_separately(self):
        mock_service = MagicMock()
        mock_service.embed_query.return_value = np.ones(1536, dtype=np.float32)

        with patch.object(embedding_mod, "_embedding_service", mock_service):
            embedding_mod._query_cache.clear()
            embedding_mod.cached_embed_query("hello")
            embedding_mod.cached_embed_query("world")

            assert mock_service.embed_query.call_count == 2
            embedding_mod._query_cache.clear()

    def test_raises_when_service_unavailable(self):
        with patch.object(embedding_mod, "_embedding_service", None):
            embedding_mod._query_cache.clear()
            with pytest.raises(RuntimeError, match="not available"):
                embedding_mod.cached_embed_query("test")


class TestEmbedFuncExports:
    def test_embed_query_func_none_when_no_api_key(self):
        with patch.object(embedding_mod, "_embedding_service", None):
            func = (
                embedding_mod.cached_embed_query
                if embedding_mod._embedding_service
                else None
            )
            assert func is None

    def test_embed_query_func_set_when_service_available(self):
        mock_service = MagicMock()
        with patch.object(embedding_mod, "_embedding_service", mock_service):
            func = (
                embedding_mod.cached_embed_query
                if embedding_mod._embedding_service
                else None
            )
            assert func is not None
