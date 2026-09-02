"""End-to-end runs against a generated repository."""

import json

from hooktestpi.cli import parse_args, parse_args_build
from hooktestpi.testing import DefaultFinder, FilterFinder, Test
from tests.conftest import section


def run(path, **kwargs):
    options = dict(scheme="ignore", console=False, workers=1, verbose=0)
    options.update(kwargs)
    test = Test(str(path), **options)
    status = test.run()
    return test, status


def test_a_clean_repository_passes(repository):
    test, status = run(repository())
    assert status == Test.SUCCESS
    assert test.count_files == 3
    assert test.successes == 3


def test_manifest_lists_texts_with_their_metadata(repository):
    test, _ = run(repository())
    manifest = test.create_manifest()
    assert len(manifest) == 3
    assert any(name.endswith("perseus-lat1.xml") for name in manifest)
    assert sum(name.endswith("__cts__.xml") for name in manifest) == 2


def test_out_of_order_divs_fail_the_run(repository):
    divs = "".join(section(i) for i in (1, 3, 2))
    test, status = run(repository(divs=divs))
    assert status == Test.FAILURE
    failing = [u for u in test.results.values() if not u.status]
    assert any(
        u.units.get("Sequential div numbering") is False for u in failing
    )


def test_duplicate_xml_ids_fail_the_run(repository):
    divs = section(1, extra=' xml:id="d"') + section(2, extra=' xml:id="d"')
    test, status = run(repository(divs=divs))
    assert status == Test.FAILURE
    text = [u for u in test.results.values() if not u.name.endswith("__cts__.xml")][0]
    assert text.units["Unique xml:id values"] is False
    # the rest of the file was still tested rather than abandoned at parse time
    assert text.units["File parsing"] is True
    assert text.units["Passage level parsing"] is True


def test_gaps_alone_do_not_fail_the_run(repository):
    divs = "".join(section(i) for i in (1, 2, 7))
    test, status = run(repository(divs=divs))
    assert status == Test.SUCCESS


def test_pta_conventions_reject_a_perseus_version(repository):
    test, status = run(repository(), cts_project="pta")
    assert status == Test.FAILURE
    text = [u for u in test.results.values() if not u.name.endswith("__cts__.xml")][0]
    assert text.units["Project conventions"] is False


def test_report_is_json_serialisable(repository, tmp_path):
    test, _ = run(repository())
    payload = json.loads(Test.dump(test.report))
    assert payload["status"] == "success"
    assert payload["project"] == "generic"
    assert len(payload["units"]) == 3
    assert payload["manifest"]


def test_filter_finder_narrows_the_run(repository):
    root = repository()
    all_texts, all_meta = DefaultFinder().find(str(root))
    assert len(all_texts) == 1

    narrowed = FilterFinder(include="phi9999.phi001")
    texts, meta = narrowed.find(str(root))
    assert len(texts) == 1
    assert len(meta) == 2

    missing = FilterFinder(include="phi0000")
    assert missing.find(str(root)) == ([], [])


def test_allowfailure_passes_when_one_text_survives(repository):
    divs = "".join(section(i) for i in (1, 3, 2))
    test, status = run(repository(divs=divs), allowfailure=True)
    assert status == Test.SUCCESS


def test_unknown_scheme_is_rejected():
    try:
        Test("/tmp", scheme="nonsense")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


# ------------------------------------------------------------------- CLI


def test_cli_defaults():
    args = parse_args(["/some/path"])
    assert args.cts_project == "generic"
    assert args.rng_backend == "auto"
    assert args.require_contiguous_divs is False
    assert args.workers == 1
    assert args.console is True
    assert args.build_manifest is True
    assert args.schema_date is None


def test_cli_filter_selects_the_finder():
    args = parse_args(["/p", "-f", "tlg0001.tlg001"])
    assert args.finder is FilterFinder
    assert args.finderoptions == {"include": "tlg0001.tlg001"}


def test_cli_quiet_and_no_manifest_turn_the_defaults_off():
    args = parse_args(["/p", "--quiet", "--no-manifest"])
    assert args.console is False
    assert args.build_manifest is False


def test_cli_verbose_without_a_value_means_everything():
    assert parse_args(["/p", "-v"]).verbose == 10


def test_build_cli_defaults():
    args = parse_args_build(["/p"])
    assert args.dest == "./"
    assert args.travis is False
    assert args.workers == 3



def test_cli_tei_p4_selects_legacy_conventions():
    args = parse_args(["/p", "--tei-p4"])
    assert args.scheme == "tei"
    assert args.guidelines == "2.tei"
    assert not hasattr(args, "tei_p4")
