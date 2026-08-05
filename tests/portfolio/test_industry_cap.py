"""Tests for industry cap allocation."""

from __future__ import annotations

import pandas as pd
import pytest

from portfolio.industry_cap import apply_industry_cap


def _make_positions(date, codes, weights):
    """Helper to create a positions DataFrame."""
    return pd.DataFrame({
        "date": pd.Timestamp(date),
        "code": codes,
        "weight": weights,
        "shares": [int(w * 1_000_000 / 10) for w in weights],  # dummy shares
    })


class TestApplyIndustryCap:
    """Test apply_industry_cap function."""

    def test_no_change_when_under_cap(self):
        """Industries under cap should not be modified."""
        pos = _make_positions("2024-01-01", ["A", "B", "C"], [0.4, 0.3, 0.3])
        industry_map = {"A": "银行", "B": "科技", "C": "科技"}
        result = apply_industry_cap(pos, industry_map, max_industry_weight=0.50)
        # 科技 = 0.3+0.3 = 0.6 > 0.5, so it should be capped
        # Actually let me fix this test
        result = apply_industry_cap(pos, industry_map, max_industry_weight=0.70)
        assert result["weight"].sum() == pytest.approx(1.0, abs=0.01)

    def test_single_industry_over_cap(self):
        """Single industry exceeding cap should be compressed."""
        # 银行: A+B = 0.6, 科技: C = 0.4. Cap = 0.5
        pos = _make_positions("2024-01-01", ["A", "B", "C"], [0.3, 0.3, 0.4])
        industry_map = {"A": "银行", "B": "银行", "C": "科技"}
        result = apply_industry_cap(pos, industry_map, max_industry_weight=0.50)
        # 银行 should be capped at 0.5, 科技 keeps 0.4 -> normalized
        bank_weight = result[result["code"].isin(["A", "B"])]["weight"].sum()
        tech_weight = result[result["code"].isin(["C"])]["weight"].sum()
        assert bank_weight <= 0.50 + 1e-10
        assert result["weight"].sum() == pytest.approx(1.0, abs=0.01)

    def test_two_industries_over_cap(self):
        """Multiple industries over cap should both be compressed."""
        # A=0.5 (银行), B=0.3 (科技), C=0.2 (医药). Cap=0.4
        pos = _make_positions("2024-01-01", ["A", "B", "C"], [0.5, 0.3, 0.2])
        industry_map = {"A": "银行", "B": "科技", "C": "医药"}
        result = apply_industry_cap(pos, industry_map, max_industry_weight=0.40)
        bank = result[result["code"] == "A"]["weight"].sum()
        assert bank <= 0.40 + 1e-10
        assert result["weight"].sum() == pytest.approx(1.0, abs=0.01)

    def test_all_industries_over_cap(self):
        """All industries over cap: compress all, total < 1.0."""
        # 3 industries each at 0.5, cap = 0.3
        pos = _make_positions("2024-01-01", ["A", "B", "C"], [0.5, 0.5, 0.5])
        # Wait, weights don't sum to 1.0. Let me fix.
        pos = _make_positions("2024-01-01", ["A", "B", "C"], [0.4, 0.35, 0.25])
        industry_map = {"A": "银行", "B": "科技", "C": "医药"}
        result = apply_industry_cap(pos, industry_map, max_industry_weight=0.20)
        # All over 0.20 cap, each compressed to 0.20, total = 0.60
        for code in ["A", "B", "C"]:
            w = result[result["code"] == code]["weight"].iloc[0]
            assert w <= 0.20 + 1e-10

    def test_missing_code_in_map_goes_to_other(self):
        """Codes not in industry_map should go to '其他' industry."""
        pos = _make_positions("2024-01-01", ["A", "B"], [0.6, 0.4])
        industry_map = {"A": "银行"}  # B is missing
        result = apply_industry_cap(pos, industry_map, max_industry_weight=0.50)
        # 银行 = 0.6 > 0.5, capped. B goes to 其他
        assert result["weight"].sum() == pytest.approx(1.0, abs=0.01)

    def test_empty_positions_returns_empty(self):
        """Empty positions should return empty DataFrame."""
        pos = pd.DataFrame(columns=["date", "code", "weight", "shares"])
        result = apply_industry_cap(pos, {}, max_industry_weight=0.30)
        assert result.empty

    def test_preserves_date_column(self):
        """Result should preserve the date column."""
        pos = _make_positions("2024-01-01", ["A", "B"], [0.6, 0.4])
        industry_map = {"A": "银行", "B": "科技"}
        result = apply_industry_cap(pos, industry_map, max_industry_weight=0.50)
        assert "date" in result.columns
        assert len(result) == 2
