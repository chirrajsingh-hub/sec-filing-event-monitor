from secmonitor.scoring import MAX_SCORE, MIN_SCORE, score_filing

import pytest


def test_baseline_score_from_item_code_alone():
    score = score_filing("2.02")
    assert score.materiality == 6
    assert score.urgency == 4
    assert "baseline" in score.rationale[0].lower() or "2.02" in score.rationale[0]


def test_bankruptcy_scores_higher_than_earnings():
    bankruptcy = score_filing("1.03")
    earnings = score_filing("2.02")
    assert bankruptcy.materiality > earnings.materiality
    assert bankruptcy.urgency > earnings.urgency


def test_keyword_boost_applies_only_to_matching_category():
    # "ceo" boost is scoped to 5.02; should not fire on an 8.01 filing.
    with_ceo = score_filing("5.02", headline="Company appoints new Chief Executive Officer")
    without_ceo = score_filing("5.02", headline="Company appoints new VP of Sales")
    assert with_ceo.materiality > without_ceo.materiality

    unaffected = score_filing("8.01", headline="mentions Chief Executive Officer in passing")
    baseline = score_filing("8.01")
    assert unaffected.materiality == baseline.materiality


def test_going_concern_keyword_boosts_materiality_and_urgency():
    plain = score_filing("2.06")
    distressed = score_filing("2.06", snippet="substantial doubt, going concern")
    assert distressed.materiality > plain.materiality
    assert distressed.urgency > plain.urgency


def test_multiple_substantive_items_bump_materiality():
    single = score_filing("2.02")
    combined = score_filing("2.02,4.02")
    assert combined.materiality >= single.materiality


def test_score_is_clamped_to_valid_range():
    # Stack every applicable keyword rule to try to push past the ceiling.
    score = score_filing(
        "5.02",
        headline="CEO CFO resign resignation terminated removed",
        snippet="going concern chapter 11 bankruptcy material weakness restate",
    )
    assert MIN_SCORE <= score.materiality <= MAX_SCORE
    assert MIN_SCORE <= score.urgency <= MAX_SCORE


def test_score_filing_raises_on_no_recognized_items():
    with pytest.raises(ValueError):
        score_filing("99.99")


def test_rationale_text_nonempty():
    score = score_filing("2.02")
    assert score.rationale_text()
