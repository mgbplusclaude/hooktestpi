# -*- coding: utf-8 -*-
#
# This file is derived from HookTest (https://github.com/Capitains/HookTest),
# Copyright (c) Thibault Clerice, Matt Munson, and contributors.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Produce a release containing only the files that passed the tests."""

from __future__ import annotations

import os
import shutil
import sys
import tarfile
import warnings
from glob import glob
from multiprocessing.pool import Pool

warnings.filterwarnings("ignore", category=SyntaxWarning, module="MyCapytain.*")

from lxml import etree  # noqa: E402
from MyCapytain.common.constants import Mimetypes  # noqa: E402
from MyCapytain.resources.texts.local.capitains.cts import CapitainsCtsText  # noqa: E402

__all__ = ["Build", "CI", "cmd"]


class Build(object):
    """Copy the passing part of a corpus into a release directory.

    :param path: directory containing the corpus ``data`` directory
    :param dest: where the cleaned corpus is written
    :param tar: also produce a ``release.tar.gz``
    :param txt: extract plain text for every passing XML file
    :param cites: prefix each passage in the plain text with its citation
    :param workers: processes used for the plain-text extraction
    """

    def __init__(self, path, dest, tar=False, txt=False, cites=False, workers=3):
        self.path = path if path.endswith("/") else path + "/"
        self.dest = dest if dest.endswith("/") else dest + "/"
        self.tar = tar
        self.txt = txt
        self.cites = cites
        self.workers = workers

    def repo_file_list(self):
        """Every XML file in the source repository."""
        files = glob("{}data/*/*/*.xml".format(self.path))
        files += glob("{}data/*/*.xml".format(self.path))
        return files

    def remove_failing(self, files, passing):
        """Keep only *passing* files, in place or by copying to ``dest``."""
        if self.path == self.dest:
            for file in files:
                if file.replace(self.path, "") not in passing:
                    os.remove(file)
            dirs = [x for x in glob("{}data/*/*".format(self.dest)) if os.path.isdir(x)]
            for directory in dirs:
                try:
                    os.removedirs(directory)
                except OSError:
                    continue
        else:
            shutil.rmtree("{}data".format(self.dest), ignore_errors=True)
            for file in files:
                if file.replace(self.path, "") in passing:
                    target = file.replace(self.path, self.dest)
                    try:
                        shutil.copy2(file, target)
                    except FileNotFoundError:
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        shutil.copy2(file, target)

    def plain_text(self):
        """Write one ``.txt`` per passing text into ``dest/text``."""
        os.makedirs("{}text".format(self.dest), exist_ok=True)
        passing_texts = [
            x for x in glob("{}data/*/*/*.xml".format(self.dest)) if "__cts__" not in x
        ]
        sys.stdout.write("Extracting Text.\n")
        sys.stdout.flush()
        with Pool(processes=self.workers) as executor:
            for _ in executor.imap_unordered(self.build_texts, passing_texts):
                sys.stdout.write(".")
                sys.stdout.flush()
            executor.close()
            executor.join()
        sys.stdout.write("\n")

    def build_texts(self, text):
        interactive_text = CapitainsCtsText(resource=etree.parse(text).getroot())
        reffs = interactive_text.getReffs(level=len(interactive_text.citation))
        passages = [interactive_text.getTextualNode(passage) for passage in reffs]
        plaintext = [
            r.export(Mimetypes.PLAINTEXT, exclude=["tei:note"]).strip() for r in passages
        ]
        if self.cites is True:
            for i, t in enumerate(plaintext):
                plaintext[i] = "#" + str(reffs[i]) + "#\n" + t
        name = text.split("/")[-1].replace(".xml", "")
        with open("{}text/{}.txt".format(self.dest, name), mode="w") as f:
            f.write("\n\n".join(plaintext))

    def run(self):
        raise NotImplementedError("run is not implemented on the base class")


class CI(Build):
    """Build in a CI checkout, deleting failing files in place."""

    def run(self):
        try:
            with open("{}manifest.txt".format(self.path)) as f:
                passing = f.read().split("\n")
        except FileNotFoundError:
            return False, "There is no manifest.txt file to load.\nStopping build."
        passing = [x for x in passing if x.strip() != ""]
        if len(passing) == 0:
            return False, "The manifest file is empty.\nStopping build."
        self.remove_failing(self.repo_file_list(), passing)
        if self.txt is True:
            self.plain_text()
        if self.tar is True:
            to_zip = glob("{}*".format(self.dest))
            with tarfile.open("{}release.tar.gz".format(self.dest), mode="w:gz") as f:
                for file in sorted(to_zip):
                    f.add(file)
        return True, "Build successful."


#: Kept so that code written against HookTest 1.3.1 keeps importing.
Travis = CI


def cmd(**kwargs):
    """Entry point used by ``hooktestpi-build``."""
    if kwargs.get("travis") is True:
        status, message = CI(
            path=kwargs["path"], dest=kwargs["dest"], tar=kwargs["tar"],
            txt=kwargs["txt"], cites=kwargs["cites"], workers=int(kwargs["workers"]),
        ).run()
        return status, message
    return False, "You cannot run build on the base class; pass --ci"
