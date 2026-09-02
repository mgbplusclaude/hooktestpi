# -*- coding: utf-8 -*-
#
# This file is derived from HookTest (https://github.com/Capitains/HookTest),
# Copyright (c) Thibault Clerice, Matt Munson, and contributors.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Test units for CTS metadata files and CTS text files."""

from __future__ import annotations

import re
import warnings
from collections import OrderedDict, defaultdict
from os import environ

# MyCapytain 3.0.2's regex literals raise SyntaxWarning on first compile.
# A module= filter cannot catch warnings raised by the import machinery,
# so suppress by category, narrowly, for the duration of the import.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", SyntaxWarning)

    import MyCapytain.common  # noqa: E402
    from MyCapytain.common.constants import Mimetypes  # noqa: E402
    from MyCapytain.errors import (  # noqa: E402
        DuplicateReference,
        EmptyReference,
        MissingRefsDecl,
    )
    from MyCapytain.resources.collections.cts import (  # noqa: E402
        XmlCtsTextgroupMetadata,
        XmlCtsWorkMetadata,
    )
    from MyCapytain.resources.texts.local.capitains.cts import (  # noqa: E402
        CapitainsCtsText,
    )

from hooktestpi.projects import ProjectProfile, get_profile  # noqa: E402
from hooktestpi.units import TESTUnit  # noqa: E402

__all__ = ["CTSMetadata_TestUnit", "CTSText_TestUnit"]

XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
TEI_DIV = "{http://www.tei-c.org/ns/1.0}div"


class CTSMetadata_TestUnit(TESTUnit):
    """Tests for a ``__cts__.xml`` metadata file.

    :param path: path to the file
    :param profile: project profile supplying naming conventions
    """

    tests = ["parsable", "capitain", "metadata", "check_urns", "filename"]
    readable = {
        "parsable": "File parsing",
        "capitain": "MyCapytain parsing",
        "metadata": "Metadata availability",
        "check_urns": "URNs testing",
        "filename": "Naming Convention",
    }

    def __init__(self, path, profile: ProjectProfile | None = None, *args, **kwargs):
        super(CTSMetadata_TestUnit, self).__init__(path, *args, **kwargs)
        self.urns = []
        self.type = None
        self.profile = profile or get_profile(None)

    def capitain(self):
        """Load the file through MyCapytain."""
        Trait = None
        if self.xml:
            textgroup = "textgroup" in self.xml.getroot().tag
            work = not textgroup and "work" in self.xml.getroot().tag
            if textgroup:
                self.type = "textgroup"
                self.log("TextGroup detected")
                Trait = XmlCtsTextgroupMetadata
            elif work:
                self.type = "work"
                self.log("Work detected")
                Trait = XmlCtsWorkMetadata
            else:
                self.log("No metadata type detected (neither work nor textgroup)")
                self.log("Inventory can't be read through Capitains standards")
                yield False

        if self.type in ["textgroup", "work"] and Trait is not None:
            try:
                self.Text = Trait.parse(self.xml.getroot())
            except AttributeError as E:
                self.log("Missing URN attribute")
                self.error(E)
            except Exception as E:
                self.error(E)

        yield self.Text is not False

    def metadata(self):
        """Check that the required CTS metadata is present."""
        status = False
        if self.xml is not None and self.Text is not False:

            if self.type == "textgroup":
                groups = len(self.Text.get_cts_property("groupname"))
                self.log("{0} groupname found".format(str(groups)))
                status = groups > 0

            elif self.type == "work":
                status = True

                workLang = self.xml.xpath("//ti:work/@xml:lang", namespaces=TESTUnit.NS)
                if len(workLang) != 1:
                    status = False
                    self.log("Work node is missing its lang attribute")

                langs = self.xml.xpath("//ti:translation/@xml:lang", namespaces=TESTUnit.NS)
                if len(langs) != len(self.xml.xpath("//ti:translation", namespaces=TESTUnit.NS)):
                    status = False
                    self.log("Translation(s) are missing lang attribute")

                com_langs = self.xml.xpath("//ti:commentary/@xml:lang", namespaces=TESTUnit.NS)
                if len(com_langs) != len(self.xml.xpath("//ti:commentary", namespaces=TESTUnit.NS)):
                    status = False
                    self.log("Some Commentaries are missing lang attribute")

                titles = len(self.Text.get_cts_property("title"))
                self.log("{0} titles found".format(titles))
                status = status and titles > 0

                texts = len(self.Text.texts)
                labels = len([
                    text for text in self.Text.texts.values()
                    if len(text.get_cts_property("label")) > 0
                ])

                self.log("{0}/{1} file(s) with labels".format(labels, texts))
                status = status and labels == texts

                descs = len([
                    text for text in self.Text.texts.values()
                    if len(text.get_cts_property("description")) > 0
                ])
                self.log("{0}/{1} file(s) with descs".format(descs, texts))
                status = status and labels == descs

        yield status

    def check_urns(self):
        """Check the validity and presence of URNs, populating ``self.urns``."""
        status = False
        if self.xml:
            if self.type == "textgroup":
                urns = [
                    urn
                    for urn in self.xml.xpath("//ti:textgroup/@urn", namespaces=TESTUnit.NS)
                    if urn and len(MyCapytain.common.reference.URN(urn)) == 3
                ]
                self.log("Group urn :" + "".join(
                    self.xml.xpath("//ti:textgroup/@urn", namespaces=TESTUnit.NS)))
                status = len(urns) == 1
                if status:
                    self.urn = urns[0]
            elif self.type == "work":
                matches = True
                onlyOneWork = True
                allMembers = True
                worksUrns = [
                    urn
                    for urn in self.xml.xpath("//ti:work/@urn", namespaces=TESTUnit.NS)
                    if urn and len(MyCapytain.common.reference.URN(urn)) == 4
                ]
                groupUrns = [
                    urn
                    for urn in self.xml.xpath("//ti:work/@groupUrn", namespaces=TESTUnit.NS)
                    if urn and len(MyCapytain.common.reference.URN(urn)) == 3
                ]
                self.urn = None
                urn = None
                if len(worksUrns) == 1:
                    self.urn = worksUrns[0]
                    urn = MyCapytain.common.reference.URN(self.urn)
                    if len(groupUrns) == len(worksUrns):
                        missing = [
                            key for key in ["namespace", "work", "textgroup"]
                            if getattr(urn, key) is None or len(getattr(urn, key)) == 0
                        ]
                        if missing:
                            self.log("Work URN is missing: {}".format(", ".join(missing)))
                            allMembers = False
                        elif groupUrns[0] != urn.upTo(MyCapytain.common.reference.URN.TEXTGROUP):
                            matches = False
                            self.log("The Work URN is not a child of the Textgroup URN")
                elif len(worksUrns) == 0:
                    self.log("The Work URN on the <ti:work> element is incorrectly formatted or missing.")
                self.log("Group urn : " + "".join(groupUrns))
                self.log("Work urn : " + "".join(worksUrns))

                texts = self.xml.xpath(
                    "//ti:edition|//ti:translation|//ti:commentary", namespaces=TESTUnit.NS)

                for text in texts:
                    t_urn = text.get("urn")
                    if t_urn and t_urn.startswith("urn:cts:"):
                        t_urn = MyCapytain.common.reference.URN(t_urn)
                        missing = [
                            key for key in ["namespace", "work", "version", "textgroup"]
                            if getattr(t_urn, key) is None or len(getattr(t_urn, key)) == 0
                        ]
                        if missing:
                            self.log("Text {} URN is missing: {}".format(str(t_urn), ", ".join(missing)))
                            allMembers = False
                        elif t_urn.upTo(MyCapytain.common.reference.URN.WORK) != str(urn):
                            matches = False
                            self.log("Text {} does not match parent URN".format(str(t_urn)))
                    self.urns.append(t_urn)
                    worksUrns.append(text.get("workUrn"))

                if len(set(worksUrns)) > 1:
                    onlyOneWork = False
                    self.log("There is different workUrns in the metadata")

                self.urns = [str(urn) for urn in self.urns if urn and len(urn) == 5]

                self.log("Edition, translation, and commentary urns : " + " ".join(self.urns))

                status = (
                    allMembers and matches and onlyOneWork and self.urn
                    and len(groupUrns) == 1
                    and (len(texts) * 2 + 1) == len(self.urns + worksUrns)
                )

        yield bool(status)

    def filename(self):
        """Check that the file's location on disk matches its URN."""
        status = False
        if self.urn:
            urn = MyCapytain.common.reference.URN(self.urn)
            if self.type == "textgroup":
                status = self.path.endswith(
                    "data/{textgroup}/__cts__.xml".format(textgroup=urn.textgroup))
            elif self.type == "work":
                self.log(str(urn))
                status = self.path.endswith("data/{textgroup}/{work}/__cts__.xml".format(
                    textgroup=urn.textgroup, work=urn.work
                ))
            namespace_issue = self.profile.check_namespace(urn.namespace)
            if namespace_issue:
                self.log(namespace_issue)
                status = False

        if not status:
            self.log("URN and path does not match")
        yield status

    def test(self):
        """Run every metadata test, yielding ``(name, status, logs)``."""
        self.urns = []

        for test in CTSMetadata_TestUnit.tests:
            for status in getattr(self, test)():
                yield (CTSMetadata_TestUnit.readable[test], status, self.logs)
                self.flush()


class CTSText_TestUnit(TESTUnit):
    """Tests for a CTS text file.

    :param path: path to the file
    :param countwords: count words in passing texts
    :param timeout: seconds allowed for one RelaxNG validation
    :param profile: project profile supplying conventions
    :param schema_map: prepared ``{key: rng path}`` from the parent process
    :param backend: RelaxNG backend name (``auto``/``lxml``/``jing``)
    """

    tests = [
        "parsable",
        "has_urn", "language",
        "inventory", "naming_convention",
        "refsDecl", "passages", "unique_passage",
        "duplicate", "forbidden", "empty",
        "sequential_divs", "unique_xml_ids", "project_conventions",
    ]
    breaks = ["parsable", "refsDecl", "passages"]
    readable = {
        "parsable": "File parsing",
        "refsDecl": "RefsDecl parsing",
        "passages": "Passage level parsing",
        "duplicate": "Duplicate passages",
        "forbidden": "Forbidden characters",
        "epidoc": "Epidoc DTD validation",
        "tei": "TEI DTD Validation",
        "auto_rng": "Automatic RNG validation",
        "local_file": "Custom local RNG validation",
        "has_urn": "URN informations",
        "naming_convention": "Naming conventions",
        "inventory": "Available in inventory",
        "unique_passage": "Unique nodes found by XPath",
        "count_words": "Word Counting",
        "language": "Correct xml:lang attribute",
        "empty": "Empty References",
        "sequential_divs": "Sequential div numbering",
        "unique_xml_ids": "Unique xml:id values",
        "project_conventions": "Project conventions",
    }
    splitter = re.compile(r"\S+", re.MULTILINE)

    def __init__(self, path, countwords=False, timeout=30, profile=None,
                 schema_map=None, backend="auto", require_contiguous_divs=False,
                 *args, **kwargs):
        self.inv = list()
        self.timeout = timeout
        self.scheme = None
        self.guidelines = None
        self.rng = None
        self.Text = None
        self.xml = None
        self.count = 0
        self.countwords = countwords
        self.citation = list()
        self.duplicates = list()
        self.forbiddens = list()
        self.empties = list()
        self.capitains_errors = list()
        self.test_status = defaultdict(bool)
        self.lang = ""
        self.dtd_errors = list()
        self.sequence_errors = list()
        self.sequence_gaps = list()
        self.id_errors = list()
        self.convention_errors = list()
        self.profile = profile or get_profile(None)
        self.schema_map = schema_map or {}
        self.backend = backend
        self.require_contiguous_divs = require_contiguous_divs
        super(CTSText_TestUnit, self).__init__(path, *args, **kwargs)

    def parsable(self):
        """Parse as XML, then ingest through MyCapytain."""
        status = next(super(CTSText_TestUnit, self).parsable())
        if status is True:
            try:
                self.Text = CapitainsCtsText(resource=self.xml.getroot())
            except MissingRefsDecl as E:
                self.Text = None
                self.log(str(E))
                self.capitains_errors.append(str(E))
                yield False
        else:
            self.Text = None
        yield status

    def refsDecl(self):
        """Check that the text declares a CTS citation scheme."""
        if self.Text:
            if self.Text.citation.is_set():
                self.log(str(len(self.Text.citation)) + " citation's level found")
                yield True
            else:
                yield False
        else:
            yield False

    # ------------------------------------------------------------------
    # RelaxNG
    # ------------------------------------------------------------------

    def _validate_with(self, rng_path):
        """Validate ``self.path`` against *rng_path*, logging any errors."""
        from hooktestpi.rng.backends import (
            BackendUnavailable,
            SchemaCompilationError,
            get_validator,
        )

        try:
            validator = get_validator(
                rng_path,
                backend=self.backend,
                run_timeout=self.timeout,
                log=self.log,
            )
        except (SchemaCompilationError, BackendUnavailable) as exc:
            self.log(str(exc))
            self.dtd_errors.append(str(exc))
            return False
        except Exception as exc:  # noqa: BLE001
            self.error(exc)
            return False

        errors = validator.validate(self.path)
        for issue in errors:
            self.log(issue)
            self.dtd_errors.append(issue)
        return not errors

    def _schema_for(self, key):
        """Look up a schema the parent process already prepared."""
        return self.schema_map.get(key)

    def auto_rng(self):
        """Validate against each schema the file itself declares."""
        declared = self.declared_schemas()
        if not declared:
            self.log("No xml-model processing instruction found")
            self.dtd_errors.append("No xml-model processing instruction found")
            yield False
            return
        for uri in declared:
            prepared = self._schema_for(uri)
            if prepared is None:
                self.log("No RNG could be prepared for " + uri)
                self.dtd_errors.append("No RNG was found at " + uri)
                yield False
                continue
            yield self._validate_with(prepared)

    def declared_schemas(self):
        """The xml-model hrefs declared by this file."""
        if self.xml is None:
            from lxml.etree import parse

            try:
                tree = parse(self.path)
            except Exception:  # noqa: BLE001
                return []
        else:
            tree = self.xml
        found = []
        for instruction in tree.xpath("/processing-instruction('xml-model')"):
            href = instruction.attrib.get("href")
            if href:
                found.append(href)
        return found

    def _named_schema(self, name):
        """Resolve a named schema when the parent prepared none."""
        from hooktestpi.rng import resolve_scheme

        try:
            return resolve_scheme(name)
        except Exception as exc:  # noqa: BLE001
            self.log(str(exc))
            self.dtd_errors.append(str(exc))
            return None

    def epidoc(self):
        path = self._schema_for("epidoc") or self._named_schema("epidoc")
        yield False if path is None else self._validate_with(path)

    def tei(self):
        path = self._schema_for("tei") or self._named_schema("tei")
        yield False if path is None else self._validate_with(path)

    def local_file(self):
        yield self._validate_with(self._schema_for("local_file") or self.rng)

    # ------------------------------------------------------------------
    # Citation structure
    # ------------------------------------------------------------------

    def passages(self):
        """Check that passages exist at each citation level."""
        if self.Text and self.Text.citation.refsDecl:
            citations = [c.name for c in self.Text.citation]
            for i in range(0, len(self.Text.citation)):
                try:
                    with warnings.catch_warnings(record=True) as warning_record:
                        warnings.simplefilter("always")
                        passages = self.Text.getValidReff(level=i + 1, _debug=True)
                        ids = [str(ref).split(".", i)[-1] for ref in passages]
                        space_in_passage = TESTUnit.FORBIDDEN_CHAR.search("".join(ids))
                        with_dot = [str(ref) for ref in passages if ref and ref.depth > i + 1]
                        len_passage = len(passages)
                        status = len_passage > 0
                        self.log(str(len_passage) + " found")
                        self.citation.append((i, len_passage, citations[i]))
                        for record in warning_record:
                            if record.category == DuplicateReference:
                                self.duplicates += sorted(str(record.message).split(", "))
                            if record.category == EmptyReference:
                                self.empties += [str(record.message)]
                        if space_in_passage and space_in_passage is not None:
                            self.forbiddens += [
                                "'{}'".format(n)
                                for ref, n in zip(ids, passages)
                                if TESTUnit.FORBIDDEN_CHAR.search(ref)
                            ]
                        if with_dot and with_dot is not None:
                            self.forbiddens += [
                                "'{}'".format(n) for n in with_dot
                                if "'{}'".format(n) not in self.forbiddens
                            ]
                        if status is False:
                            yield status
                            break
                        yield status
                except Exception as E:
                    self.error(E)
                    self.log("Error when searching passages at level {0}".format(i + 1))
                    yield False
                    break
        else:
            yield False

    def duplicate(self):
        if len(self.duplicates) > 0:
            self.log("Duplicate references found : {0}".format(", ".join(self.duplicates)))
            yield False
        elif self.test_status["passages"] is False:
            yield False
        else:
            yield True

    def forbidden(self):
        if len(self.forbiddens) > 0:
            self.log("Reference with forbidden characters found: {0}".format(
                ", ".join(self.forbiddens)))
            yield False
        elif self.test_status["passages"] is False:
            yield False
        else:
            yield True

    def empty(self):
        if len(self.empties) > 0:
            self.log("Empty references found : {0}".format(", ".join(self.empties)))
            yield False
        elif self.test_status["passages"] is False:
            yield False
        else:
            yield True

    def unique_passage(self):
        """Check that citation levels do not resolve to the same node."""
        try:
            xpaths = [
                self.Text.xml.xpath(
                    MyCapytain.common.reference._capitains_cts.REFERENCE_REPLACER.sub(
                        r"\1", citation.refsDecl
                    ),
                    namespaces=TESTUnit.NS,
                )
                for citation in self.Text.citation
            ]
            nodes = [element for xpath in xpaths for element in xpath]
            if len(nodes) != len(set(nodes)):
                self.log("Some node are found twice")
                yield False
            else:
                yield True
        except Exception:  # noqa: BLE001
            yield False

    # ------------------------------------------------------------------
    # Structural conventions
    # ------------------------------------------------------------------

    def sequential_divs(self):
        """Sibling citation divs must be numbered in ascending order.

        Out-of-order or repeated ``@n`` break CTS references. Gaps (1, 2, 5)
        are only reported — commentaries and fragmentary works skip numbers
        legitimately — unless ``--require-contiguous-divs``. Non-numeric
        references (``praefatio``) have no order to check. Siblings are
        grouped by ``@subtype`` first: Greek drama interleaves independent
        series (strophe 1, antistrophe 1, strophe 2) under one parent, and
        comparing them as one list fails all of Perseus' Sophocles.
        """
        if self.xml is None:
            yield False
            return

        problems = []
        gaps = []
        for parent in self.xml.iter():
            if not isinstance(parent.tag, str):
                continue
            siblings = [
                child for child in parent
                if child.tag == TEI_DIV and child.get("n") is not None
                and child.get("type") in (None, "textpart")
            ]
            if len(siblings) < 2:
                continue

            where = parent.get("n") or parent.get("type") or parent.tag.split("}")[-1]

            series = OrderedDict()
            for child in siblings:
                series.setdefault(child.get("subtype"), []).append(child.get("n"))

            for subtype, values in series.items():
                if len(values) < 2:
                    continue
                label = where if subtype is None else "{0}/{1}".format(where, subtype)

                counts = defaultdict(int)
                for value in values:
                    counts[value] += 1
                repeated = sorted(value for value, count in counts.items() if count > 1)
                if repeated:
                    problems.append(
                        "repeated @n {0} among <div> siblings of <{1}>".format(
                            ", ".join(repr(r) for r in repeated), label)
                    )

                if all(re.fullmatch(r"-?\d+", value) for value in values):
                    numbers = [int(value) for value in values]
                    if numbers != sorted(numbers):
                        problems.append(
                            "<div> siblings of <{0}> are not in ascending order: {1}".format(
                                label, ", ".join(values))
                        )
                    else:
                        missing = [
                            "{0}->{1}".format(a, b)
                            for a, b in zip(numbers, numbers[1:]) if b - a > 1
                        ]
                        if missing:
                            gaps.append(
                                "gap under <{0}>: {1}".format(label, ", ".join(missing))
                            )

        self.sequence_errors = problems
        self.sequence_gaps = gaps
        for problem in problems:
            self.log(problem)
        for gap in gaps:
            self.log(gap)
        if self.require_contiguous_divs:
            yield not (problems or gaps)
        else:
            yield not problems

    def unique_xml_ids(self):
        """``xml:id`` values must be unique within a file.

        PTA references witnesses, hands, readings and bibliography by
        ``xml:id``; a repeated value silently sends a reference to the wrong
        target, and repeated ids are invalid XML besides.
        """
        if self.xml is None:
            yield False
            return

        counts: defaultdict[str, int] = defaultdict(int)
        for element in self.xml.iter():
            if not isinstance(element.tag, str):
                continue
            value = element.get(XML_ID)
            if value is not None:
                counts[value] += 1

        repeated = sorted(value for value, count in counts.items() if count > 1)
        self.id_errors = repeated
        if repeated:
            self.log("Duplicate xml:id values found: {0}".format(", ".join(repeated)))
        yield not repeated

    def project_conventions(self):
        """Apply the selected project's own conventions."""
        problems = []
        if self.xml is not None:
            for div in self.xml.xpath("//tei:text/tei:body/tei:div", namespaces=TESTUnit.NS):
                issue = self.profile.check_div_type(div.get("type"))
                if issue:
                    problems.append(issue)
            if self.urn:
                parts = str(self.urn).split(":")[-1].split(".")
                if len(parts) > 2:
                    issue = self.profile.check_version(parts[2])
                    if issue:
                        problems.append(issue)
                namespace = str(self.urn).split(":")
                if len(namespace) > 3:
                    issue = self.profile.check_namespace(namespace[3])
                    if issue:
                        problems.append(issue)

        self.convention_errors = problems
        for problem in problems:
            self.log(problem)
        yield not problems

    # ------------------------------------------------------------------
    # URN and inventory
    # ------------------------------------------------------------------

    def has_urn(self):
        """Check the file carries a CTS URN where the guidelines require it."""
        if self.xml is not None:
            if self.guidelines == "2.tei":
                urns = self.xml.xpath(
                    "//tei:text/tei:body[starts-with(@n, 'urn:cts:')]",
                    namespaces=TESTUnit.NS)
                urns += self.xml.xpath(
                    "//tei:text[starts-with(@xml:base, 'urn:cts:')]",
                    namespaces=TESTUnit.NS)
            else:
                urns = self.xml.xpath(
                    "//tei:body/tei:div[@type='edition' and starts-with(@n, 'urn:cts:')]",
                    namespaces=TESTUnit.NS)
                urns += self.xml.xpath(
                    "//tei:body/tei:div[@type='translation' and starts-with(@n, 'urn:cts:')]",
                    namespaces=TESTUnit.NS)
                urns += self.xml.xpath(
                    "//tei:body/tei:div[@type='commentary' and starts-with(@n, 'urn:cts:')]",
                    namespaces=TESTUnit.NS)
            status = len(urns) > 0
            if status:
                logs = urns[0].get("n")
                if not logs:
                    logs = urns[0].base
                urn = MyCapytain.common.reference.URN(logs)
                missing_members = [
                    key for key in ["namespace", "work", "version", "textgroup"]
                    if getattr(urn, key) is None or len(getattr(urn, key)) == 0
                ]
                if len(urn) < 5:
                    status = False
                    self.log("Incomplete URN")
                elif urn.reference:
                    status = False
                    self.log("Reference not accepted in URN")
                elif len(missing_members) > 0:
                    status = False
                    self.log("Elements of URN are empty: {}".format(
                        ", ".join(sorted(missing_members))))
                self.urn = logs
        else:
            status = False
        yield status

    def naming_convention(self):
        """The filename must contain the version part of the URN."""
        if self.urn:
            yield self.urn.split(":")[-1] in self.path
        else:
            yield False

    def inventory(self):
        """The text's URN must appear in a ``__cts__.xml`` inventory."""
        if self.urn and self.inv:
            yield self.urn in self.inv
        else:
            yield False

    def count_words(self):
        """Count the words of a passing text."""
        status = False
        if self.test_status["passages"]:
            text = self.Text.export(Mimetypes.PLAINTEXT, exclude=["tei:note", "tei:teiHeader"])
            self.count = len(type(self).splitter.findall(text))
            self.log("{} has {} words".format(self.urn, self.count))
            status = self.count > 0
        yield status

    def language(self):
        """The URN-holding node must carry an ``xml:lang``."""
        urns_holding_node = []
        if self.guidelines == "2.epidoc":
            urns_holding_node = self.xml.xpath(
                "//tei:text/tei:body/tei:div"
                "[@type='edition' or @type='translation' or @type='commentary']"
                "[starts-with(@n, 'urn:cts:')]",
                namespaces=TESTUnit.NS,
            )
        elif self.guidelines == "2.tei":
            urns_holding_node = self.xml.xpath(
                "//tei:text/tei:body[starts-with(@n, 'urn:cts:')]",
                namespaces=TESTUnit.NS,
            ) + self.xml.xpath(
                "//tei:text[starts-with(@xml:base, 'urn:cts:')]",
                namespaces=TESTUnit.NS,
            )

        try:
            self.lang = urns_holding_node[0].get(XML_LANG)
        except IndexError:
            self.lang = ""
        if self.lang == "" or self.lang is None:
            self.lang = "UNK"
            yield False
        else:
            yield True

    def test(self, scheme, guidelines, rng=None, inventory=None):
        """Run every text test, yielding ``(name, status, logs)``."""
        if inventory is not None:
            self.inv = inventory
        tests = [] + CTSText_TestUnit.tests
        if self.countwords:
            tests.append("count_words")

        if scheme in ["tei", "epidoc", "auto_rng", "local_file"]:
            tests = [scheme] + tests

        self.scheme = scheme
        self.guidelines = guidelines
        self.rng = rng
        if environ.get("HOOKTEST_DEBUG", False):
            print("Starting %s " % self.path)
        i = 0
        for test in tests:
            if environ.get("HOOKTEST_DEBUG", False):
                print("\t Testing %s " % test)
            status = False not in [status for status in getattr(self, test)()]
            self.test_status[test] = status
            yield (CTSText_TestUnit.readable[test], status, self.logs)
            if test in self.breaks and not status:
                for t in tests[i + 1:]:
                    self.test_status[t] = False
                    yield (CTSText_TestUnit.readable[t], False, [])
                break
            self.flush()
            i += 1
