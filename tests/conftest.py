"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_factor_cache(tmp_path, monkeypatch):
    """将因子磁盘缓存隔离到临时目录，避免测试污染 data/factors/。"""
    monkeypatch.setenv("FACTOR_CACHE_DIR", str(tmp_path / "factor_cache"))
    yield
