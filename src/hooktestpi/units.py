# -*- coding: utf-8 -*-
#
# This file is derived from HookTest (https://github.com/Capitains/HookTest),
# Copyright (c) Thibault Clerice, Matt Munson, and contributors.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Base class shared by every test unit."""

from __future__ import annotations

import re
from collections import defaultdict

from lxml import etree

__all__ = ["TESTUnit"]


class TESTUnit(object):
    """TestUnit metaclass.

    :param path: path of the current file
    """

    RNG_ERROR = re.compile(r"([0-9]+):([0-9]+):(.*);")
    RNG_FAILURE = re.compile(r"([0-9]+):([0-9]+):(\s*fatal.*)")
    SPACE_REPLACER = re.compile(r"(\s{2,})")
    FORBIDDEN_CHAR = re.compile(r"[^\w\d]")
    NS = {
        "tei": "http://www.tei-c.org/ns/1.0",
        "ti": "http://chs.harvard.edu/xmlns/cts",
    }
    # collect_ids=False stops lxml refusing to parse a file that repeats an
    # xml:id. Such a file *is* invalid, but rejecting it at parse time hides
    # every other problem in it; hooktestpi reports duplicate ids as their
    # own failing test instead, so the rest of the file still gets tested.
    PARSER = etree.XMLParser(
        no_network=True, resolve_entities=False, collect_ids=False
    )

    def __init__(self, path):
        self.path = path
        self.xml = None
        self.testable = True
        self.__logs = []
        self.__archives = []
        self.Text = False
        self.urn = None

    @property
    def logs(self):
        return self.__logs

    def log(self, message):
        if isinstance(message, str) and not message.isspace() and len(message) > 0:
            self.__logs.append(
                ">>>>>> " + TESTUnit.SPACE_REPLACER.sub(" ", message.lstrip())
            )

    def error(self, error):
        if isinstance(error, Exception):
            self.log(str(type(error)) + " : " + str(error))

    def flush(self):
        self.__archives = self.__archives + self.__logs
        self.__logs = []

    def parsable(self):
        """Check and parse the XML file.

        :returns: indicator of success and messages
        :rtype: bool
        """
        try:
            # Binary mode: the file carries its own encoding declaration and
            # lxml refuses a decoded string that declares an encoding.
            with open(self.path, "rb") as f:
                xml = etree.parse(f, TESTUnit.PARSER)
                self.xml = xml
                self.testable = True
                self.log("Parsed")
        except Exception as e:
            self.testable = False
            self.error(e)
        finally:
            yield self.testable

    @staticmethod
    def rng(line):
        """Return an rng-free line.

        :param line: line of logs
        :return: LineColumn code, error
        :rtype: (str, str)
        """
        found = TESTUnit.RNG_ERROR.findall(line)
        identifier, code = "", line

        if len(found) == 0:
            found = TESTUnit.RNG_FAILURE.findall(line)

        if len(found) > 0:
            identifier, code = "(L{0} C{1})".format(*found[0]), found[0][-1]

        return code, identifier

    @staticmethod
    def rng_logs(logs):
        """Group raw validator output by message.

        :param logs: sum of logs
        :type logs: str or bytes
        :return: iterator of human readable messages
        """
        if isinstance(logs, bytes):
            logs = logs.decode("utf-8", errors="replace")
        parsed = [TESTUnit.rng(log) for log in logs.split("\n") if bool(log.strip())]
        filtered_logs = defaultdict(list)

        for key, value in parsed:
            filtered_logs[key].append(value)

        for key, value in filtered_logs.items():
            yield "{0} [In {1}]".format(key, "; ".join(value))
