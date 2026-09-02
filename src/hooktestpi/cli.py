# -*- coding: utf-8 -*-
#
# This file is derived from HookTest (https://github.com/Capitains/HookTest),
# Copyright (c) Thibault Clerice, Matt Munson, and contributors.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Command line entry points."""

from __future__ import annotations

import argparse
import os
import sys

import hooktestpi.build
import hooktestpi.testing
from hooktestpi.projects import PROFILES, describe_profiles
from hooktestpi.rng.schemas import NAMED_SCHEMAS, PSEUDO_SCHEMES, describe_schemes

__all__ = ["parse_args", "cmd", "parse_args_build", "cmd_build"]


def check_schema(schema):
    """Accept a named scheme or a path to a local RelaxNG file."""
    if schema in NAMED_SCHEMAS or schema in PSEUDO_SCHEMES:
        return schema
    if os.path.isfile(schema):
        return ["local_file", schema]
    raise argparse.ArgumentTypeError(
        "--scheme must point at an existing RelaxNG file or name one of:\n"
        + describe_schemes()
    )


def parse_args(args):
    """Parse ``hooktestpi`` arguments.

    :param args: list of command line arguments
    :return: parsed namespace
    """
    parser = argparse.ArgumentParser(
        prog="hooktestpi",
        description="Validate a CapiTainS/CTS corpus of TEI digital editions.",
        epilog=(
            "Project profiles (--cts-project):\n"
            + describe_profiles()
            + "\n\nSchemes (--scheme):\n"
            + describe_schemes()
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "path",
        help=(
            "Corpus to test: a local directory (the repository root or its "
            "data/ directory) or a git remote"
        ),
    )
    parser.add_argument(
        "--cts-project", dest="cts_project", default="generic",
        choices=sorted(PROFILES),
        help="Project conventions to enforce (default: generic)",
    )
    parser.add_argument("--ref", default=None,
                        help="Branch, tag or commit to use when the path is a git remote")
    parser.add_argument("-w", "--workers", type=int, default=1,
                        help="Number of worker processes (default: 1)")
    parser.add_argument(
        "-s", "--scheme", default=None, type=check_schema,
        help="RelaxNG scheme to validate against (default: the project profile's)",
    )
    parser.add_argument(
        "--rng-backend", dest="rng_backend", default="auto",
        choices=("auto", "jing", "rust"),
        help=(
            "RelaxNG engine. 'auto' (default) uses Jing (the reference "
            "implementation, shipped with the package; needs Java) and "
            "falls back to 'rust' — the relaxng-rust 'rng' binary "
            "(reference-grade verdicts, no Java; found via HOOKTESTPI_RNG "
            "or PATH)"
        ),
    )
    parser.add_argument(
        "-v", "--verbose", default=0, type=int, nargs="?", choices=(0, 5, 7, 10),
        help="Verbosity: 0 essentials, 5 duplicate/forbidden detail, 7 failing units, 10 all",
    )
    parser.add_argument("-j", "--json", default=None,
                        help="Write the full report to this JSON file")
    parser.add_argument(
        "-f", "--filter", dest="finder", default=None,
        help="Restrict the run to a URN fragment (tlg0001, tlg0001.tlg001, ...)",
    )
    parser.add_argument("--countwords", action="store_true", default=False,
                        help="Count words in texts that pass")
    parser.add_argument("--quiet", dest="console", action="store_false",
                        default=True,
                        help="Do not print results to the console "
                             "(console output is on by default)")
    parser.add_argument("--no-manifest", dest="build_manifest",
                        action="store_false", default=True,
                        help="Do not write manifest.txt "
                             "(the manifest is written by default)")
    parser.add_argument(
        "--require-contiguous-divs", dest="require_contiguous_divs",
        action="store_true", default=False,
        help="Treat gaps in <div> numbering as failures. Off by default: a "
             "commentary on selected verses skips numbers legitimately",
    )
    parser.add_argument("--allowfailure", action="store_true", default=False,
                        help="Succeed as long as at least one text passes")
    parser.add_argument("--timeout", type=int, default=30,
                        help="Seconds allowed for one RelaxNG validation (default: 30)")
    parser.add_argument(
        "--schema-dir", dest="schema_dir", default=None,
        help="Directory holding schemas locally (tei-epidoc.rng, tei-pta.rng). "
             "Searched before the cache and before any download, so a corpus "
             "that ships its schemas validates with no network at all",
    )
    parser.add_argument("--cache-dir", dest="cache_dir", default=None,
                        help="Directory for downloaded schemas")
    parser.add_argument(
        "--schema-date", dest="schema_date", default=None, metavar="YYYY-MM-DD",
        help="Validate against the project schema as it stood on this date "
             "(UTC), resolved from the schema's source git repository. "
             "Corpora pin no schema version, so older releases may need the "
             "schema they were written against. Applies to named project "
             "schemas (pta, perseus)",
    )
    parser.add_argument("--guidelines", default=None, choices=("2.tei", "2.epidoc"),
                        help="CapiTainS guideline flavour (default: the profile's)")
    parser.add_argument(
        "--tei-p4", dest="tei_p4", action="store_true", default=False,
        help="Legacy-edition mode: validate against the generic TEI-all "
             "schema instead of the project's, and read the CTS URN from "
             "<text>/<body> (the old '2.tei' guidelines), as pre-EpiDoc "
             "conversions encode it. Combine with --schema-date for the "
             "schema of a given era",
    )

    args = parser.parse_args(args)

    if args.finder:
        args.finderoptions = {"include": args.finder}
        args.finder = hooktestpi.testing.FilterFinder
    if args.tei_p4:
        args.scheme = args.scheme or "tei"
        args.guidelines = args.guidelines or "2.tei"
    del args.tei_p4
    if args.verbose is None:
        args.verbose = 10
    return args


def cmd():
    """``hooktestpi`` entry point."""
    args = parse_args(sys.argv[1:])
    options = vars(args)
    target = options.pop("path")
    ref = options.pop("ref", None)

    from hooktestpi.sources import resolve_source

    try:
        source = resolve_source(target, ref=ref)
    except Exception as exc:  # noqa: BLE001
        print("Could not read the corpus: {0}".format(exc), file=sys.stderr)
        sys.exit(2)

    try:
        status = hooktestpi.testing.cmd(path=str(source.path), **options)
    finally:
        source.cleanup()

    sys.exit(0 if status == hooktestpi.testing.Test.SUCCESS else 1)


def parse_args_build(args):
    """Parse ``hooktestpi-build`` arguments."""
    parser = argparse.ArgumentParser(
        prog="hooktestpi-build",
        description="Build a release containing only the files that passed.",
    )
    parser.add_argument("path", help="Repository root", default="./")
    parser.add_argument("-d", "--dest", default="./",
                        help="Where to write the cleaned corpus")
    parser.add_argument("--ci", "--travis", dest="travis", action="store_true",
                        default=False, help="Run in a CI environment (removes in place)")
    parser.add_argument("--tar", action="store_true", default=False,
                        help="Also produce release.tar.gz")
    parser.add_argument("--txt", action="store_true", default=False,
                        help="Extract plain text from the XML files")
    parser.add_argument("--cites", action="store_true", default=False,
                        help="Include the citation of each passage in the plain text")
    parser.add_argument("--workers", type=int, default=3,
                        help="Processes to use when extracting plain text")
    return parser.parse_args(args)


def cmd_build():
    """``hooktestpi-build`` entry point."""
    status, message = hooktestpi.build.cmd(**vars(parse_args_build(sys.argv[1:])))
    print(message)
    sys.exit(0 if status is True else 1)


if __name__ == "__main__":
    cmd()
