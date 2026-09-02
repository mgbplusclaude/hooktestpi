# -*- coding: utf-8 -*-
#
# This file is derived from HookTest (https://github.com/Capitains/HookTest),
# Copyright (c) Thibault Clerice, Matt Munson, and contributors.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""The test runner: find files, test them in parallel, report."""

from __future__ import annotations

import glob
import json
import os
import statistics
import sys
import time
import traceback
from collections import OrderedDict, defaultdict
from multiprocessing.pool import Pool
from operator import attrgetter

import hooktestpi.capitains.cts
from hooktestpi.console import Table, magenta, white, yellow
from hooktestpi.projects import get_profile

__all__ = ["Test", "UnitLog", "DefaultFinder", "FilterFinder", "cmd"]


class DefaultFinder(object):
    """Finds the files a run should test."""

    def __init__(self, **options):
        pass

    def find(self, directory):
        """Return ``(text files, __cts__.xml files)`` under ``directory/data``."""
        data = glob.glob(os.path.join(directory, "data/*/*/*.xml")) + glob.glob(
            os.path.join(directory, "data/*/*.xml")
        )
        files = [f for f in data if "__cts__.xml" not in f]
        cts = [f for f in data if "__cts__.xml" in f]
        cts.sort()
        files.sort()
        return files, cts


class FilterFinder(DefaultFinder):
    """Restrict a run to one textgroup, work or version.

    :param include: the URN tail, cut at any level
        (``phi1294``, ``phi1294.phi002``, ``phi1294.phi002.perseus-lat2``)
    """

    def __init__(self, include, **options):
        self.include = include.split(".")

    def find(self, directory):
        textgroup, work, version = self.include[0], "*", "*"
        if len(self.include) > 1:
            work = self.include[1]
        if len(self.include) > 2:
            version = ".".join(self.include)

        cts = glob.glob(
            os.path.join(directory, "data/{0}/__cts__.xml".format(textgroup))
        ) + glob.glob(
            os.path.join(directory, "data/{0}/{1}/__cts__.xml".format(textgroup, work))
        )
        files = [
            found
            for found in glob.glob(
                os.path.join(
                    directory, "data/{0}/{1}/{2}.xml".format(textgroup, work, version)
                )
            )
            # With no version given the glob is "*.xml", which also matches the
            # work's own __cts__.xml; testing that as a text always fails.
            if "__cts__.xml" not in found
        ]
        cts.sort()
        files.sort()
        return files, cts


class Test(object):
    """Run the CapiTainS tests over a repository.

    :param path: repository root (the directory containing ``data/``)
    :param workers: number of worker processes
    :param scheme: RelaxNG scheme name, ``auto``, ``ignore``, or a file path
    :param cts_project: project profile name (``generic``/``perseus``/``pta``)
    :param rng_backend: ``auto``, ``jing`` or ``rust``
    """

    #: Tells pytest this is not a test class to collect.
    __test__ = False

    FAILURE = "failed"
    ERROR = "error"
    SUCCESS = "success"
    SCHEMES = ("tei", "epidoc", "ignore", "auto")

    def __init__(
        self,
        path,
        workers=1,
        scheme="auto",
        verbose=0,
        console=False,
        build_manifest=False,
        finder=DefaultFinder,
        finderoptions=None,
        countwords=False,
        allowfailure=False,
        timeout=30,
        guidelines=None,
        cts_project=None,
        rng_backend="auto",
        cache_dir=None,
        schema_dir=None,
        schema_date=None,
        require_contiguous_divs=False,
        **kwargs,
    ):
        self.console = console
        self.build_manifest = build_manifest
        self.path = path
        self.workers = workers
        self.profile = get_profile(cts_project)
        self.rng_backend = rng_backend
        self.cache_dir = cache_dir
        self.schema_dir = schema_dir
        self.schema_date = schema_date
        self.require_contiguous_divs = require_contiguous_divs

        if scheme in (None, "profile"):
            scheme = self.profile.scheme

        self.scheme = scheme
        self.rng = None
        if isinstance(scheme, list):
            self.scheme = scheme[0]
            self.rng = scheme[1]
        self.verbose = verbose
        self.countwords = countwords
        self.allowfailure = allowfailure
        self.timeout = timeout
        self.guidelines = guidelines or self.profile.guidelines

        if (
            not isinstance(scheme, list)
            and scheme not in Test.SCHEMES
            and scheme not in ("perseus", "pta", "local_file")
            and not os.path.isfile(str(scheme))
        ):
            raise ValueError(
                "Scheme {0} unknown, please use one of the following : {1}".format(
                    scheme, ", ".join(Test.SCHEMES + ("perseus", "pta"))
                )
            )

        self.results = OrderedDict()
        self.passing = defaultdict(bool)
        self.inventory = []
        self.text_files = []
        self.cts_files = []
        self.progress = None
        self.schema_map = {}
        self.m_files = self.m_passing = 0

        self.finder = finder or DefaultFinder
        if finderoptions:
            self.finder = self.finder(**finderoptions)
        else:
            self.finder = self.finder()

    # ------------------------------------------------------------------
    # Reporting helpers
    # ------------------------------------------------------------------

    @property
    def successes(self):
        return len([True for status in self.passing.values() if status is True])

    @property
    def json(self):
        return Test.dump(self.report)

    @property
    def report(self):
        coverage = 0
        if len(self.results) > 0:
            coverage = statistics.mean([test.coverage for test in self.results.values()])
        return {
            "status": self.status,
            "units": [unitlog.dict for unitlog in self.results.values()],
            "coverage": coverage,
            "project": self.profile.name,
            "schemas": {key: str(value) for key, value in self.schema_map.items()},
            "manifest": self.create_manifest(),
        }

    @property
    def directory(self):
        return self.path

    @property
    def status(self):
        if self.count_files == 0 or len(self.passing) != self.count_files:
            return Test.ERROR
        elif self.allowfailure is True and self.count_files > 0 and self.successes > 0:
            return Test.SUCCESS
        elif self.count_files > 0 and self.successes == len(self.passing):
            return Test.SUCCESS
        return Test.FAILURE

    @property
    def files(self):
        return self.text_files, self.cts_files

    @property
    def count_files(self):
        return len(self.text_files) + len(self.cts_files)

    # ------------------------------------------------------------------
    # Schema preparation
    # ------------------------------------------------------------------

    def prepare_schemas(self):
        """Resolve and compile every schema *before* the workers start.

        Compiling in the parent means a schema that libxml2 cannot handle
        is detected — and repaired — exactly once, instead of every worker
        discovering the same stall independently.
        """
        from hooktestpi.rng import resolve_scheme
        from hooktestpi.rng.backends import (
            BackendUnavailable,
            SchemaCompilationError,
            get_validator,
        )
        if self.scheme == "ignore":
            return

        def prepare(key, rng_path):
            try:
                validator = get_validator(
                    rng_path,
                    backend=self.rng_backend,
                    run_timeout=self.timeout,
                    log=self.note,
                )
            except (SchemaCompilationError, BackendUnavailable) as exc:
                self.note(str(exc))
                return
            self.schema_map[key] = getattr(validator, "rng_path", rng_path)

        if self.scheme in ("auto", "auto_rng"):
            for uri in sorted(self.declared_schemas()):
                try:
                    prepare(uri, self.resolve_declared(uri))
                except Exception as exc:  # noqa: BLE001
                    self.note("Could not prepare {0}: {1}".format(uri, exc))
            return

        key = self.scheme if self.scheme in ("tei", "epidoc") else "local_file"
        target = self.rng if self.rng else self.scheme
        try:
            resolved = resolve_scheme(
                target, cache=self.cache_dir, schema_dir=self.schema_dir,
                at=self.schema_date,
            )
        except Exception as exc:  # noqa: BLE001
            self.note(str(exc))
            return
        if resolved is not None:
            prepare(key, resolved)

    def declared_schemas(self):
        """Collect every xml-model href declared across the corpus."""
        from lxml import etree

        found = set()
        for path in self.text_files:
            try:
                tree = etree.parse(path)
            except Exception:  # noqa: BLE001
                continue
            for instruction in tree.xpath("/processing-instruction('xml-model')"):
                href = instruction.attrib.get("href")
                if href:
                    found.add(href)
        return found

    def resolve_declared(self, uri):
        """Turn one xml-model href into a local schema file."""
        from urllib.parse import urlparse

        from pathlib import Path

        from hooktestpi.rng.schemas import NAMED_SCHEMAS, _schema_dirs, download

        if urlparse(uri).scheme in ("http", "https"):
            for spec in NAMED_SCHEMAS.values():
                if spec.url == uri:
                    return spec.local_path(cache=self.cache_dir, schema_dir=self.schema_dir)
            for directory in _schema_dirs(self.schema_dir):
                candidate = Path(directory) / Path(uri).name
                if candidate.is_file():
                    return candidate
            return download(uri, cache=self.cache_dir)
        candidate = os.path.abspath(os.path.join(self.path, uri))
        if os.path.isfile(candidate):
            return candidate
        raise FileNotFoundError("No RNG was found at " + candidate)

    def note(self, message):
        """Record a run-level message and echo it in console mode."""
        self.schema_notes.append(str(message))
        if self.console:
            print(yellow(">>> " + str(message)), flush=True)

    # ------------------------------------------------------------------
    # Running
    # ------------------------------------------------------------------

    def unit(self, filepath):
        """Test one file and return its :class:`UnitLog`."""
        logs = []
        results = {}
        if filepath.endswith("__cts__.xml"):
            unit = hooktestpi.capitains.cts.CTSMetadata_TestUnit(
                filepath, profile=self.profile
            )
            texttype = "CTSMetadata"
            logs.append(">>>> Testing " + filepath)
            for name, status, unitlogs in unit.test():
                logs.append(">>>>> " + name + (" passed" if status else " failed"))
                if self.verbose > 0 and len(unitlogs) > 0:
                    logs += [log for log in unitlogs if log]
                results[name] = status
            additional = unit.urns
        else:
            unit = hooktestpi.capitains.cts.CTSText_TestUnit(
                filepath,
                countwords=self.countwords,
                timeout=self.timeout,
                profile=self.profile,
                schema_map=self.schema_map,
                backend=self.rng_backend,
                require_contiguous_divs=self.require_contiguous_divs,
            )
            texttype = "CTSText"
            logs.append(">>>> Testing " + filepath.split("data")[-1])
            for name, status, unitlogs in unit.test(
                self.scheme_for_tests(), self.guidelines, self.rng, self.inventory
            ):
                logs.append(">>>>> " + name + (" passed" if status else " failed"))
                if self.verbose > 0 and len(unitlogs) > 0:
                    logs += [log for log in unitlogs if log]
                results[name] = status


            additional = {
                "citations": unit.citation,
                "duplicates": unit.duplicates,
                "forbiddens": unit.forbiddens,
                "dtd_errors": unit.dtd_errors,
                "language": unit.lang,
                "empties": unit.empties,
                "capitains_errors": unit.capitains_errors,
                "sequence_errors": unit.sequence_errors,
                "sequence_gaps": unit.sequence_gaps,
                "id_errors": unit.id_errors,
                "convention_errors": unit.convention_errors,
            }
            if self.countwords:
                additional["words"] = unit.count
        return (
            self.cover(filepath, results, testtype=texttype, logs=logs, additional=additional),
            filepath,
            additional,
        )

    def scheme_for_tests(self):
        """Map a scheme name onto the test method that implements it."""
        if self.scheme in ("auto", "auto_rng"):
            return "auto_rng"
        if self.scheme in ("tei", "epidoc"):
            return self.scheme
        if self.scheme == "ignore":
            return "ignore"
        return "local_file"

    def run(self):
        """Run every test, returning the overall status string."""
        self.text_files, self.cts_files = self.find()
        self.start()
        self.prepare_schemas()

        with Pool(processes=self.workers) as executor:
            for future in executor.imap_unordered(self.unit, self.cts_files):
                result, filepath, additional = future
                self.results[filepath] = result
                self.passing[filepath] = result.status
                self.inventory += additional
                self.log(self.results[filepath])
            executor.close()
            executor.join()
            self.middle()

        with Pool(processes=self.workers) as executor:
            for future in executor.imap_unordered(self.unit, self.text_files):
                result, filepath, additional = future
                self.results[filepath] = result
                self.passing[filepath] = result.status
                self.log(self.results[filepath])
            executor.close()
            executor.join()
        self.end()
        return self.status

    def log(self, log):
        if self.console and isinstance(log, UnitLog):
            sys.stdout.write("." if log.status is True else "X")
            sys.stdout.flush()

    def start(self):
        if self.console:
            print(">>> Starting tests !", flush=True)
            print(">>> Project profile : " + self.profile.name, flush=True)
            print(">>> Files to test : " + str(self.count_files), flush=True)

    def middle(self):
        """Print the metadata results between the two phases."""
        self.m_files = self.m_passing = len(self.results.values())

        if self.console and self.verbose > 0:
            print("", flush=True)
            if False not in [unit.status for unit in self.results.values()]:
                print("All Metadata Files Passed", flush=True)
            else:
                display_table = Table(["Filename", "Failed Tests"])
                for unit in sorted(self.report["units"], key=lambda x: x["name"]):
                    if unit["status"] is not True:
                        self.m_passing -= 1
                        display_table.add_row([
                            unit["name"],
                            "\n".join(
                                "{test} failed".format(test=x)
                                for x in unit["units"]
                                if unit["units"][x] is False
                            ),
                        ])
                print(display_table, flush=True)

    def end(self):
        """Print (or send) the final report."""
        total_units = 0
        total_words = 0
        language_words = defaultdict(int)
        show = list(hooktestpi.capitains.cts.CTSText_TestUnit.readable.values())
        if self.verbose == 0:
            show.remove("Duplicate passages")
            show.remove("Forbidden characters")

        if not self.console:
            return

        extra_sections = defaultdict(str)
        num_texts = 0
        num_failed = 0
        print("", flush=True)

        headers = ["Identifier", "Words", "Nodes", "Failed Tests"] if self.countwords \
            else ["Identifier", "Nodes", "Failed Tests"]
        display_table = Table(headers)

        for unit in sorted(self.results.values(), key=attrgetter("name")):
            if unit.name.endswith("__cts__.xml"):
                continue
            num_texts += 1
            if unit.units.get("Passage level parsing") is False:
                for name in ("Duplicate passages", "Forbidden characters"):
                    if name in show:
                        show.remove(name)
            text_color = white if unit.coverage == 100.0 else magenta
            if unit.coverage != 100.0:
                num_failed += 1

            failed_tests = "All" if unit.coverage == 0.0 else "\n".join(
                x for x in unit.units if unit.units[x] is False and x in show
            )

            for key, label in (
                ("duplicates", "Duplicate nodes found"),
                ("forbiddens", "Forbidden characters found"),
                ("empties", "Empty references found"),
                ("sequence_errors", "Out-of-sequence div numbering found"),
                ("sequence_gaps", "Gaps in div numbering (not an error)"),
                ("id_errors", "Duplicate xml:id values found"),
                ("convention_errors", "Project convention problems found"),
                ("capitains_errors", "CapiTainS parsing errors found"),
            ):
                if unit.additional.get(key):
                    extra_sections[label] += "\t{name}\t{nodes}\n".format(
                        name=magenta(os.path.basename(unit.name)),
                        nodes=", ".join(str(x) for x in unit.additional[key]),
                    )
            if unit.additional.get("dtd_errors") and self.verbose >= 6:
                extra_sections["DTD errors found"] += "\t{name}\t{nodes}\n".format(
                    name=magenta(os.path.basename(unit.name)),
                    nodes=", ".join(unit.additional["dtd_errors"]),
                )

            if self.verbose >= 7 or unit.status is False:
                nodes = ";".join(str(x[1]) for x in unit.additional.get("citations", []))
                row = [text_color(os.path.basename(unit.name))]
                if self.countwords:
                    row.append("{:,}".format(unit.additional.get("words", 0)))
                row += [nodes, failed_tests]
                display_table.add_row(row)

            for citation in unit.additional.get("citations", []):
                total_units += citation[1]
            if self.countwords:
                total_words += unit.additional.get("words", 0)
                if unit.additional.get("words", 0) > 0:
                    language_words[unit.additional.get("language", "UNK")] += \
                        unit.additional["words"]

        print(display_table, flush=True)
        print("", flush=True)

        rendered = ""
        for label, body in extra_sections.items():
            structural = label in (
                "Out-of-sequence div numbering found",
                "Duplicate xml:id values found",
                "Project convention problems found",
                "CapiTainS parsing errors found",
            )
            if structural or self.verbose >= 5:
                rendered += magenta(label + ":\n") + body + "\n"
        print("{0}>>> End of the test !\n".format(rendered))

        t_pass = num_texts - num_failed
        cov_results = [test.coverage for test in self.results.values()]
        cov = round(statistics.mean(cov_results), ndigits=2) if cov_results else 0.00

        results_table = Table(["HookTestResults", ""])
        results_table.add_row(["Project", self.profile.name])
        results_table.add_row(["Total Texts", num_texts])
        results_table.add_row(["Passing Texts", t_pass])
        results_table.add_row(["Metadata Files", self.m_files])
        results_table.add_row(["Passing Metadata", self.m_passing])
        results_table.add_row(["Coverage", cov])
        results_table.add_row(["Total Citation Units", "{:,}".format(total_units)])
        if self.countwords:
            results_table.add_row(["Total Words", "{:,}".format(total_words)])
            for language, words in language_words.items():
                results_table.add_row(
                    ["Words in {}".format(language.upper()), "{:,}".format(words)]
                )
        print(results_table, flush=True)



        if self.build_manifest:
            passing = self.create_manifest()
            with open("{}/manifest.txt".format(self.path), mode="w") as f:
                f.write("\n".join(passing))

    def create_manifest(self):
        """List the passing files, keeping each text with its metadata.

        A text only earns a place if both its work-level and textgroup-level
        ``__cts__.xml`` passed too: a text whose metadata is broken cannot be
        served, so shipping it would produce a release that does not resolve.
        """
        passing_temp = [x.name for x in self.results.values() if x.coverage == 100.0]
        passing = []
        for name in passing_temp:
            if name.endswith("__cts__.xml"):
                continue
            work_meta = "{}/__cts__.xml".format(os.path.dirname(name))
            group_meta = "{}/__cts__.xml".format("/".join(name.split("/")[:-2]))
            if work_meta in passing_temp and group_meta in passing_temp:
                passing += [name, work_meta, group_meta]
        return sorted(set(passing))

    def find(self):
        return self.finder.find(self.directory)

    def cover(self, name, test, testtype=None, logs=None, additional=None):
        """Turn a dict of test results into a :class:`UnitLog`."""
        results = list(test.values())
        if logs is None:
            logs = list()

        if len(results) > 0:
            return UnitLog(
                directory=self.directory,
                name=name,
                units=test,
                coverage=len([v for v in results if v is True]) / len(results) * 100,
                status=False not in results,
                logs=logs,
                additional=additional,
                testtype=testtype,
            )
        return UnitLog(
            directory=self.directory,
            name=name,
            units=list(),
            coverage=0.0,
            status=False,
            logs=logs,
            testtype=testtype,
        )

    @staticmethod
    def dump(obj):
        return json.dumps(obj, separators=(",", ":"), sort_keys=True, default=str)


def cmd(console=False, **kwargs):
    """Build a :class:`Test`, run it, and write any requested JSON report."""
    json_path = kwargs.pop("json", None)
    test = Test(console=console, **kwargs)
    test.console = console

    status = Test.ERROR
    try:
        status = test.run()
    except Exception:  # noqa: BLE001
        type_, value_, traceback_ = sys.exc_info()
        tb = "".join(traceback.format_exception(type_, value_, traceback_))
        if console:
            print(tb, flush=True)

    if json_path:
        with open(json_path, "w") as json_file:
            json.dump(test.report, json_file, indent=2, default=str)

    return status


class UnitLog(object):
    """The result of testing one file."""

    def __init__(self, directory, name, units, coverage, status, testtype=None,
                 logs=None, additional=None):
        self.directory = directory
        self.units = units
        self.coverage = coverage
        self.status = status
        self.__logs = list()
        self.time = time.strftime("%Y-%m-%d %H:%M:%S")

        self.name = self.directory_replacer(name)
        self.logs = logs
        self.additional = {}
        self.testtype = testtype
        if isinstance(additional, dict):
            self.additional = additional

    @property
    def logs(self):
        return self.__logs

    @logs.setter
    def logs(self, logs):
        if isinstance(logs, list):
            self.__logs = [self.directory_replacer(data) for data in logs]

    def directory_replacer(self, data):
        if self.directory != ".":
            return data.replace(str(self.directory), "").lstrip("/")
        return data

    @property
    def dict(self):
        x = {
            "name": self.name,
            "units": self.units,
            "coverage": self.coverage,
            "status": self.status,
            "logs": self.logs,
            "at": self.time,
        }
        x.update(self.additional)
        return x

    def __str__(self):
        return "\n".join(self.logs)
