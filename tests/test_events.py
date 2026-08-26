from secmonitor.events import ITEM_TAXONOMY, item_categories, normalize_items, primary_category

import pytest


def test_normalize_items_from_comma_string():
    assert normalize_items("5.02,9.01") == ["5.02", "9.01"]


def test_normalize_items_strips_whitespace():
    assert normalize_items(" 5.02 , 9.01 ") == ["5.02", "9.01"]


def test_normalize_items_from_list_passthrough():
    assert normalize_items(["5.02", "9.01"]) == ["5.02", "9.01"]


def test_item_categories_skips_unknown_codes():
    categories = item_categories("5.02,99.99")
    assert [c.code for c in categories] == ["5.02"]


def test_primary_category_prefers_substantive_over_administrative():
    primary = primary_category("5.02,9.01")
    assert primary.code == "5.02"


def test_primary_category_picks_highest_materiality_among_substantive():
    # 4.02 (restatement, materiality 9) should win over 2.02 (earnings, materiality 6)
    primary = primary_category("2.02,4.02")
    assert primary.code == "4.02"


def test_primary_category_falls_back_to_administrative_only_filing():
    primary = primary_category("9.01")
    assert primary.code == "9.01"


def test_primary_category_raises_on_unknown_only():
    with pytest.raises(ValueError):
        primary_category("99.99")


def test_taxonomy_scores_in_range():
    for code, category in ITEM_TAXONOMY.items():
        assert code == category.code
        assert 1 <= category.base_materiality <= 10
        assert 1 <= category.base_urgency <= 10
