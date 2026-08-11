from secmonitor.events import classify_items, refine_catchall_category


def test_classify_items_known_codes():
    tags = classify_items(["5.02", "9.01"])
    assert [t.category for t in tags] == ["leadership_change", "exhibits_only"]
    assert tags[0].weight == 3
    assert tags[1].weight == 1


def test_classify_items_unrecognized_code():
    tags = classify_items(["99.99"])
    assert tags[0].category == "other"
    assert "Unrecognized" in tags[0].label


def test_classify_items_ignores_blank_entries():
    tags = classify_items(["5.02", "", "  "])
    assert len(tags) == 1


def test_refine_catchall_category_detects_litigation():
    tags = classify_items(["8.01"])
    refined = refine_catchall_category(tags, "The Company received a subpoena related to an ongoing SEC inquiry.")
    assert refined[0].category == "litigation"
    assert refined[0].weight == 4


def test_refine_catchall_category_no_match_keeps_original():
    tags = classify_items(["8.01"])
    refined = refine_catchall_category(tags, "The Company issued a routine press release about a product launch.")
    assert refined[0].category == "other_material_event"
