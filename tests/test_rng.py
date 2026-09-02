"""Schema resolution and the validation backends."""

from pathlib import Path

import pytest

from hooktestpi.rng import backends, schemas

SIMPLE = """<grammar xmlns="http://relaxng.org/ns/structure/1.0"
  datatypeLibrary="http://www.w3.org/2001/XMLSchema-datatypes">
  <start>
    <element name="root"><zeroOrMore><element name="child"><text/></element></zeroOrMore></element>
  </start>
</grammar>
"""


@pytest.fixture
def simple_rng(tmp_path):
    path = tmp_path / "simple.rng"
    path.write_text(SIMPLE, encoding="utf-8")
    return path


# ---------------------------------------------------------------- resolution


def test_pseudo_schemes_resolve_to_nothing():
    assert schemas.resolve_scheme("auto") is None
    assert schemas.resolve_scheme("ignore") is None


def test_a_local_file_is_accepted_as_a_scheme(simple_rng):
    assert schemas.resolve_scheme(str(simple_rng)) == simple_rng


def test_unknown_scheme_is_rejected():
    with pytest.raises(ValueError):
        schemas.resolve_scheme("no-such-scheme")


def test_every_named_schema_has_a_canonical_source():
    for name, spec in schemas.NAMED_SCHEMAS.items():
        assert spec.url, name


def test_schema_dir_is_preferred_over_downloading(tmp_path):
    """A corpus that ships its schemas must validate with no network."""
    local = tmp_path / "schemas"
    local.mkdir()
    (local / "tei-pta.rng").write_text(SIMPLE, encoding="utf-8")
    found = schemas.NAMED_SCHEMAS["pta"].local_path(schema_dir=local)
    assert found == local / "tei-pta.rng"


def test_cached_path_keeps_hooktest_naming():
    url = "https://example.org/tei.rng"
    assert schemas.cached_path_for_url(url).name.endswith(".rng")
    assert len(schemas.cached_path_for_url(url).stem) == 32


# ---------------------------------------------------------------------- jing


def test_jvm_option_banners_are_not_read_as_errors():
    """The JVM narrates its options environment variables on stderr.

    Jing reports a valid file by saying nothing, so any line left on the
    stream becomes a validation error. A banner that survives the filter
    fails every file in the corpus instead of none.
    """
    for variable in ("_JAVA_OPTIONS", "JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS"):
        banner = "Picked up {0}: -Dhttps.proxyPort=8080\n".format(variable)
        assert backends.strip_jvm_banner(banner.encode()).strip() == ""


def test_real_jing_output_survives_the_banner_filter():
    noisy = (
        b"Picked up JAVA_TOOL_OPTIONS: -Dfile.encoding=UTF-8\n"
        b"/corpus/text.xml:12:8: error: element \"foo\" not allowed here\n"
    )
    cleaned = backends.strip_jvm_banner(noisy)
    assert "Picked up" not in cleaned
    assert 'element "foo" not allowed here' in cleaned


def test_the_jar_is_found_without_importing_jingtrang(tmp_path, monkeypatch):
    """jingtrang's __init__ imports pkg_resources, which modern virtualenvs
    no longer ship, so the jar must be located without executing the package.
    """
    package = tmp_path / "jingtrang"
    package.mkdir()
    (package / "jing.jar").write_bytes(b"not really a jar")

    class Spec:
        submodule_search_locations = [str(package)]

    def explode(name):
        raise ModuleNotFoundError("No module named 'pkg_resources'")

    monkeypatch.setattr(backends.metadata, "files", explode)
    monkeypatch.setattr(backends.util, "find_spec", lambda name: Spec())
    assert backends.JingBackend.find_jar() == str(package / "jing.jar")


def test_a_missing_jingtrang_is_not_an_error(monkeypatch):
    monkeypatch.setattr(backends.util, "find_spec", lambda name: None)
    monkeypatch.setattr(
        backends.metadata, "files", lambda name: (_ for _ in ()).throw(Exception())
    )
    assert backends.JingBackend.find_jar() is None


# ---------------------------------------------------------------------- rust

RUST_DIAGNOSTIC = """Validating "some/file.xml"
error: attribute not expected here
    --> some/file.xml:1482:47
     |
1482 |         <add place="overstrike">x</add>
     |                                               ^^^ Not allowed
help: Remove this
error: element-end not expected here
  --> some/file.xml:35:44
   |
35 |                <msIdentifier xml:id="CatJm">
"""


def test_rust_diagnostics_collapse_to_one_line_each():
    errors = backends.RustBackend.parse_errors(RUST_DIAGNOSTIC)
    assert errors == [
        "(L1482 C47) attribute not expected here",
        "(L35 C44) element-end not expected here",
    ]


def test_rust_diagnostics_strip_ansi_colour():
    assert backends.RustBackend.parse_errors(
        "\x1b[1m" + RUST_DIAGNOSTIC + "\x1b[0m"
    ) == backends.RustBackend.parse_errors(RUST_DIAGNOSTIC)


def _stub_rng(tmp_path, exit_code, stderr=""):
    stub = tmp_path / "rng"
    stub.write_text(
        "#!/bin/sh\nprintf '%b' {stderr} >&2\nexit {code}\n".format(
            stderr=repr(stderr), code=exit_code
        )
    )
    stub.chmod(0o755)
    return stub


def test_rust_backend_finds_binary_through_the_environment(tmp_path, monkeypatch):
    stub = _stub_rng(tmp_path, 0)
    monkeypatch.setenv("HOOKTESTPI_RNG", str(stub))
    assert backends.RustBackend.find_binary() == str(stub)
    assert backends.available_backends()["rust"] is True


def test_rust_backend_unavailable_without_binary(monkeypatch, simple_rng):
    monkeypatch.delenv("HOOKTESTPI_RNG", raising=False)
    monkeypatch.setattr(backends.shutil, "which", lambda name: None)
    with pytest.raises(backends.BackendUnavailable):
        backends.RustBackend(simple_rng)


def test_rust_backend_validates_through_the_binary(tmp_path, monkeypatch, simple_rng):
    ok = _stub_rng(tmp_path, 0, stderr='Validating "x"\n')
    monkeypatch.setenv("HOOKTESTPI_RNG", str(ok))
    assert backends.RustBackend(simple_rng).validate("x.xml") == []

    bad = _stub_rng(
        tmp_path, 2,
        stderr='error: attribute not expected here\n --> x.xml:14:7\n',
    )
    monkeypatch.setenv("HOOKTESTPI_RNG", str(bad))
    assert backends.RustBackend(simple_rng).validate("x.xml") == [
        "(L14 C7) attribute not expected here"
    ]


# ------------------------------------------------------------------- auto


def test_auto_prefers_jing(tmp_path, monkeypatch, simple_rng):
    monkeypatch.setenv("HOOKTESTPI_RNG", str(_stub_rng(tmp_path, 0)))
    monkeypatch.setattr(
        backends.shutil, "which",
        lambda name: "/usr/bin/java" if name == "java" else None,
    )
    monkeypatch.setattr(backends.JingBackend, "find_jar", staticmethod(lambda: "/x/jing.jar"))
    monkeypatch.setattr(backends, "_CACHE", {})
    validator = backends.get_validator(simple_rng, backend="auto")
    assert isinstance(validator, backends.JingBackend)


def test_auto_falls_back_to_rust_without_jing(tmp_path, monkeypatch, simple_rng):
    monkeypatch.setenv("HOOKTESTPI_RNG", str(_stub_rng(tmp_path, 0)))
    monkeypatch.setattr(backends.shutil, "which", lambda name: None)
    monkeypatch.setattr(backends.JingBackend, "find_jar", staticmethod(lambda: None))
    monkeypatch.setattr(backends, "_CACHE", {})
    validator = backends.get_validator(simple_rng, backend="auto")
    assert isinstance(validator, backends.RustBackend)


def test_auto_refuses_when_no_backend_exists(monkeypatch, simple_rng):
    monkeypatch.delenv("HOOKTESTPI_RNG", raising=False)
    monkeypatch.setattr(backends.shutil, "which", lambda name: None)
    monkeypatch.setattr(backends.JingBackend, "find_jar", staticmethod(lambda: None))
    monkeypatch.setattr(backends, "_CACHE", {})
    with pytest.raises(backends.BackendUnavailable):
        backends.get_validator(simple_rng, backend="auto")


def test_explicit_rust_backend_is_returned(tmp_path, monkeypatch, simple_rng):
    monkeypatch.setenv("HOOKTESTPI_RNG", str(_stub_rng(tmp_path, 0)))
    monkeypatch.setattr(backends, "_CACHE", {})
    validator = backends.get_validator(simple_rng, backend="rust")
    assert isinstance(validator, backends.RustBackend)


# ------------------------------------------------------------- schema dates


def _git(repo, *argv, env=None):
    import os as _os
    import subprocess

    merged = {**_os.environ, **(env or {})}
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@example.org",
         "-c", "user.name=t", *argv],
        check=True, capture_output=True, env=merged,
    )


def test_schema_as_of_resolves_the_last_revision_on_or_before_the_date(
    tmp_path, monkeypatch
):
    repo = tmp_path / "schema-repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "s.rng").write_text("v1", encoding="utf-8")
    _git(repo, "add", "s.rng")
    stamp1 = {"GIT_AUTHOR_DATE": "2024-01-01T12:00:00Z",
              "GIT_COMMITTER_DATE": "2024-01-01T12:00:00Z"}
    _git(repo, "commit", "-q", "-m", "v1", env=stamp1)
    (repo / "s.rng").write_text("v2", encoding="utf-8")
    stamp2 = {"GIT_AUTHOR_DATE": "2025-01-01T12:00:00Z",
              "GIT_COMMITTER_DATE": "2025-01-01T12:00:00Z"}
    _git(repo, "commit", "-q", "-am", "v2", env=stamp2)

    spec = schemas.SchemaSpec(description="dated", git=(str(repo), "main", "s.rng"))
    monkeypatch.setitem(schemas.NAMED_SCHEMAS, "dated-test", spec)
    monkeypatch.setenv("HOOKTESTPI_CACHE", str(tmp_path / "cache"))

    old = schemas.schema_as_of("dated-test", "2024-06-01")
    assert old.read_text(encoding="utf-8") == "v1"
    new = schemas.schema_as_of("dated-test", "2025-06-01")
    assert new.read_text(encoding="utf-8") == "v2"


def test_schema_as_of_rejects_dateless_schemes(monkeypatch, tmp_path):
    monkeypatch.setenv("HOOKTESTPI_CACHE", str(tmp_path / "cache"))
    with pytest.raises(schemas.SchemaUnavailable):
        schemas.schema_as_of("tei", "2024-06-01")
    with pytest.raises(schemas.SchemaUnavailable):
        schemas.resolve_scheme("ignore", at="2024-06-01")
