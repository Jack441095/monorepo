from composition.arrangement_role_labels import arrangement_role_display_name


def test_arrangement_role_display_name_known() -> None:
    assert arrangement_role_display_name("a") == "VERSE (A)"
    assert arrangement_role_display_name("INTRO") == "INTRO"


def test_arrangement_role_display_name_unknown_upper() -> None:
    assert arrangement_role_display_name("bridge") == "BRIDGE"


def test_arrangement_role_display_name_empty() -> None:
    assert arrangement_role_display_name("") == ""
