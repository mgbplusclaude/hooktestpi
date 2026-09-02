"""The structural checks: div ordering and xml:id uniqueness."""

import pytest

from hooktestpi.capitains.cts import CTSText_TestUnit
from tests.conftest import build_text, section


def unit_for(tmp_path, divs, **kwargs):
    path = tmp_path / "text.xml"
    path.write_text(build_text(divs), encoding="utf-8")
    unit = CTSText_TestUnit(str(path), **kwargs)
    assert next(unit.parsable()) is not False
    return unit


def run(unit, name):
    return False not in list(getattr(unit, name)())


# --------------------------------------------------------------- ordering


def test_ascending_divs_pass(tmp_path):
    unit = unit_for(tmp_path, "\n".join(section(i) for i in (1, 2, 3)))
    assert run(unit, "sequential_divs") is True
    assert unit.sequence_errors == []


def test_out_of_order_divs_fail(tmp_path):
    unit = unit_for(tmp_path, "\n".join(section(i) for i in (1, 3, 2)))
    assert run(unit, "sequential_divs") is False
    assert any("ascending" in problem for problem in unit.sequence_errors)


def test_repeated_div_numbers_fail(tmp_path):
    unit = unit_for(tmp_path, "\n".join(section(i) for i in (1, 2, 2)))
    assert run(unit, "sequential_divs") is False
    assert any("repeated" in problem for problem in unit.sequence_errors)


def test_gaps_are_reported_but_do_not_fail(tmp_path):
    """A commentary on selected verses skips numbers legitimately."""
    unit = unit_for(tmp_path, "\n".join(section(i) for i in (1, 2, 5)))
    assert run(unit, "sequential_divs") is True
    assert unit.sequence_errors == []
    assert any("gap" in gap for gap in unit.sequence_gaps)


def test_gaps_fail_when_contiguity_is_required(tmp_path):
    unit = unit_for(
        tmp_path, "\n".join(section(i) for i in (1, 2, 5)),
        require_contiguous_divs=True,
    )
    assert run(unit, "sequential_divs") is False


def test_non_numeric_references_are_not_ordered(tmp_path):
    """References like praefatio or Gen_1_1 have no numeric order."""
    divs = section("praefatio") + section("Gen_1_1") + section("alpha")
    unit = unit_for(tmp_path, divs)
    assert run(unit, "sequential_divs") is True


def test_non_numeric_references_still_must_be_unique(tmp_path):
    unit = unit_for(tmp_path, section("praefatio") + section("praefatio"))
    assert run(unit, "sequential_divs") is False


def test_a_single_div_is_never_out_of_order(tmp_path):
    unit = unit_for(tmp_path, section(7))
    assert run(unit, "sequential_divs") is True


# ------------------------------------------------------------------- ids


def test_unique_xml_ids_pass(tmp_path):
    divs = section(1, extra=' xml:id="a"') + section(2, extra=' xml:id="b"')
    unit = unit_for(tmp_path, divs)
    assert run(unit, "unique_xml_ids") is True


def test_duplicate_xml_ids_fail(tmp_path):
    divs = section(1, extra=' xml:id="dup"') + section(2, extra=' xml:id="dup"')
    unit = unit_for(tmp_path, divs)
    assert run(unit, "unique_xml_ids") is False
    assert unit.id_errors == ["dup"]


def test_duplicate_ids_are_listed_once_each(tmp_path):
    divs = (
        section(1, extra=' xml:id="x"')
        + section(2, extra=' xml:id="x"')
        + section(3, extra=' xml:id="x"')
    )
    unit = unit_for(tmp_path, divs)
    assert run(unit, "unique_xml_ids") is False
    assert unit.id_errors == ["x"]


# ----------------------------------------------------------- conventions


@pytest.mark.parametrize(
    "project,expected", [("generic", True), ("perseus", True), ("pta", False)]
)
def test_version_identifier_is_checked_per_project(tmp_path, project, expected):
    from hooktestpi.projects import get_profile

    unit = unit_for(tmp_path, section(1), profile=get_profile(project))
    unit.guidelines = "2.epidoc"
    assert next(unit.has_urn()) is True          # urn:...perseus-lat1
    assert run(unit, "project_conventions") is expected


# ------------------------------------------------- independently numbered series


def _lyric(subtype, number):
    return (
        '<div type="textpart" subtype="{0}" n="{1}"><p>x</p></div>'
    ).format(subtype, number)


def test_sibling_series_are_numbered_independently(tmp_path):
    """Greek drama interleaves strophe/antistrophe under one parent.

    Each subtype is its own sequence, so 'strophe 1, antistrophe 1' is not a
    repeat. Compared as a single list it reads as one, which fails every text
    in Perseus' Sophocles — all of them valid.
    """
    divs = "".join([
        _lyric("strophe", 1), _lyric("antistrophe", 1),
        _lyric("strophe", 2), _lyric("antistrophe", 2),
    ])
    unit = unit_for(tmp_path, divs)
    assert run(unit, "sequential_divs") is True
    assert unit.sequence_errors == []


def test_a_repeat_within_one_series_still_fails(tmp_path):
    """Grouping by subtype must not hide a genuine duplicate."""
    divs = "".join([
        _lyric("strophe", 1), _lyric("antistrophe", 1), _lyric("strophe", 1),
    ])
    unit = unit_for(tmp_path, divs)
    assert run(unit, "sequential_divs") is False
    assert any("strophe" in problem for problem in unit.sequence_errors)


def test_ordering_is_checked_within_a_series(tmp_path):
    """Out-of-order values inside one subtype are still an error."""
    divs = "".join([
        _lyric("strophe", 1), _lyric("antistrophe", 9),
        _lyric("strophe", 3), _lyric("strophe", 2),
    ])
    unit = unit_for(tmp_path, divs)
    assert run(unit, "sequential_divs") is False
    assert any("ascending" in problem for problem in unit.sequence_errors)


def test_gaps_are_reported_per_series(tmp_path):
    """A gap is attributed to the series it appears in."""
    divs = "".join([
        _lyric("strophe", 1), _lyric("antistrophe", 1),
        _lyric("strophe", 5), _lyric("antistrophe", 2),
    ])
    unit = unit_for(tmp_path, divs)
    assert run(unit, "sequential_divs") is True
    assert any("strophe" in gap and "1->5" in gap for gap in unit.sequence_gaps)
