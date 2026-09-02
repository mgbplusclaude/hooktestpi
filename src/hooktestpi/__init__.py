"""hooktestpi — CapiTainS/CTS validation for TEI digital editions.

A port of HookTest (https://pypi.org/project/HookTest/) to Python 3.14 with
reference-grade RelaxNG validation, selectable project conventions, and
structural checks that CTS corpora depend on in practice.
"""

from __future__ import annotations

from importlib import metadata

# Single source of truth is pyproject.toml, read from the installed
# distribution so the two can never disagree.
try:
    __version__ = metadata.version("hooktestpi")
except metadata.PackageNotFoundError:  # running from a bare checkout
    __version__ = "0.0.0+uninstalled"

__all__ = ["__version__"]
