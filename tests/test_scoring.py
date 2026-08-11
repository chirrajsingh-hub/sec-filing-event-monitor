from secmonitor.events import classify_items
from secmonitor.scoring import score_filing


def test_score_single_low_weight_item():
    tags = classify_items(["9.01"])
    result = score_filing(tags)
    assert result.score == 1
    assert result.level == "Informational"


def test_score_restatement_is_critical():
    tags = classify_items(["4.02"])
    result = score_filing(tags)
    assert result.score == 5
    assert result.level == "Critical"


def test_score_stacked_material_items_bumps_score():
    tags = classify_items(["5.02", "2.03"])  # leadership (3) + debt (3)
    result = score_filing(tags)
    assert result.score == 4  # base 3 + stacking bump
    assert "stacks additional material items" in result.rationale


def test_score_severe_keyword_bumps_score():
    tags = classify_items(["8.01"])
    result = score_filing(tags, text="The Company disclosed a material weakness in internal controls.")
    assert result.score == 3  # base 2 + keyword bump
    assert "high-severity language" in result.rationale


def test_score_is_capped_at_five():
    tags = classify_items(["4.02", "1.03"])  # both weight 5
    result = score_filing(tags, text="going concern bankruptcy chapter 11 restate")
    assert result.score == 5


def test_score_no_tags_is_informational():
    result = score_filing([])
    assert result.score == 1
    assert result.level == "Informational"
