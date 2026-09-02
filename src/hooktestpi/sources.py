"""Where a corpus is read from: a directory, a git repository, or a URL.

Validation itself never needs the network: a local checkout is read in
place, and no schema is downloaded when a bundled or cached one already
answers. Remote sources are materialised into a temporary directory first
so that every later stage — finders, test units, the manifest — works on
ordinary files.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

__all__ = ["ResolvedSource", "resolve_source", "looks_remote"]

_GIT_URL = re.compile(r"^(git@|ssh://|git://)|\.git/?$")
_GITHUB_TREE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)"
    r"(?:/(?:tree|blob)/(?P<ref>[^/]+)(?P<path>/.*)?)?/?$"
)


@dataclass
class ResolvedSource:
    """A corpus made available on the local filesystem.

    :param path: repository root — the directory *containing* ``data/``
    :param origin: what the user asked for
    :param temporary: directory to delete when finished, if any
    """

    path: Path
    origin: str
    temporary: Path | None = None

    def cleanup(self) -> None:
        if self.temporary and self.temporary.exists():
            shutil.rmtree(self.temporary, ignore_errors=True)

    def __enter__(self) -> "ResolvedSource":
        return self

    def __exit__(self, *exc) -> None:
        self.cleanup()


def looks_remote(target: str) -> bool:
    """True when *target* names something that must be fetched."""
    if _GIT_URL.search(target):
        return True
    scheme = urlparse(target).scheme
    return scheme in ("http", "https", "git", "ssh")


def resolve_source(target, ref: str | None = None, timeout: int = 120) -> ResolvedSource:
    """Make *target* available locally and return its repository root.

    Accepts a local path or a git remote (cloned shallowly).
    """
    target = str(target)

    if not looks_remote(target):
        path = Path(target).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"No such directory: {path}")
        return ResolvedSource(path=_repository_root(path), origin=target)

    if _GIT_URL.search(target) or _is_github_repo_root(target):
        return _clone(target, ref=ref, timeout=timeout)

    raise ValueError(
        f"Cannot read {target}: pass a local directory or a git remote"
    )


def _repository_root(path: Path) -> Path:
    """Accept either the repo root or the ``data`` directory itself."""
    if path.name == "data" and path.is_dir():
        return path.parent
    return path


def _is_github_repo_root(target: str) -> bool:
    match = _GITHUB_TREE.match(target)
    return bool(match) and not (match.group("path") or "").strip("/")


def _clone(url: str, ref: str | None, timeout: int) -> ResolvedSource:
    if shutil.which("git") is None:
        raise RuntimeError("git is not installed, cannot clone " + url)

    match = _GITHUB_TREE.match(url)
    if match:
        ref = ref or match.group("ref")
        url = "https://github.com/{owner}/{repo}.git".format(
            owner=match.group("owner"), repo=match.group("repo")
        )

    temporary = Path(tempfile.mkdtemp(prefix="hooktestpi-"))
    command = ["git", "clone", "--depth", "1"]
    if ref:
        command += ["--branch", ref]
    command += [url, str(temporary / "repo")]
    result = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
    if result.returncode != 0:
        shutil.rmtree(temporary, ignore_errors=True)
        raise RuntimeError(
            "git clone failed: " + result.stderr.decode("utf-8", "replace").strip()
        )
    return ResolvedSource(
        path=_repository_root(temporary / "repo"), origin=url, temporary=temporary
    )


