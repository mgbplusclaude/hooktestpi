"""Project profiles."""

import pytest

from hooktestpi.projects import PROFILES, get_profile


def test_default_profile_constrains_nothing():
    profile = get_profile(None)
    assert profile.name == "generic"
    assert profile.check_div_type("anything-at-all") is None
    assert profile.check_version("whatever") is None


def test_unknown_profile_is_rejected():
    with pytest.raises(ValueError):
        get_profile("not-a-project")


@pytest.mark.parametrize("version", ["pta-grc1", "pta-deu1", "pta-MsL", "pta-MsPb"])
def test_pta_accepts_its_own_version_identifiers(version):
    assert get_profile("pta").check_version(version) is None


def test_pta_rejects_a_perseus_version_identifier():
    assert get_profile("pta").check_version("perseus-lat2") is not None


@pytest.mark.parametrize("version", ["perseus-lat2", "perseus-grc2", "1st1K-grc1"])
def test_perseus_accepts_project_version_identifiers(version):
    assert get_profile("perseus").check_version(version) is None


def test_pta_allows_praefatio_but_perseus_does_not():
    assert get_profile("pta").check_div_type("praefatio") is None
    assert get_profile("perseus").check_div_type("praefatio") is not None


def test_every_profile_names_itself():
    for name, profile in PROFILES.items():
        assert profile.name == name
        assert profile.description
