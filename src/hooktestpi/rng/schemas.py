"""Named RelaxNG schemas and the on-disk schema cache.

HookTest 1.3.1 could only use its two bundled schemas (frozen in 2017) or
an ``--scheme`` pointing at a local file. Projects that needed a current
schema had to overwrite the bundled ``epidoc.rng`` in site-packages before
each run. This module makes the schemas that Perseus and the Patristic
Text Archive actually declare first-class names instead.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from hashlib import md5
from pathlib import Path

__all__ = [
    "SchemaSpec", "SchemaUnavailable", "NAMED_SCHEMAS", "PSEUDO_SCHEMES",
    "cache_dir", "resolve_scheme", "schema_as_of", "describe_schemes",
    "cached_path_for_url",
]


class SchemaUnavailable(RuntimeError):
    """Raised when a named schema is neither local nor reachable."""


@dataclass(frozen=True)
class SchemaSpec:
    """A schema that can be named on the command line.

    :param description: help text shown by ``--help``
    :param url: canonical download location
    :param filename: conventional name when kept in a local schema directory
    :param git: ``(repository URL, branch, path)`` of the schema's source of
        truth, enabling ``--schema-date`` to fetch the schema as it stood on
        a past date
    """

    description: str
    url: str | None = None
    filename: str | None = None
    git: tuple[str, str, str] | None = None

    def local_path(self, cache: Path | None = None,
                   schema_dir: str | os.PathLike | None = None) -> Path:
        """Return the local file for this schema.

        Looks in *schema_dir* first, then the download cache, and only then
        goes to the network — so a project that keeps its schemas in the
        repository never needs to be online to validate.
        """
        assert self.url is not None

        for directory in _schema_dirs(schema_dir):
            for name in filter(None, (self.filename, Path(self.url).name)):
                candidate = Path(directory) / name
                if candidate.is_file():
                    return candidate

        cached = cached_path_for_url(self.url, cache)
        if cached.exists():
            return cached

        try:
            return download(self.url, cache=cache)
        except Exception as exc:  # noqa: BLE001
            raise SchemaUnavailable(
                f"Could not obtain the '{self.filename or self.url}' schema.\n"
                f"  Tried: {self.url}\n"
                f"  Reason: {exc}\n"
                f"  Fix: download it once and pass --schema-dir DIR (the file may be "
                f"named {self.filename}), or point --scheme at the .rng file directly."
            ) from exc


def _schema_dirs(explicit=None):
    """Directories searched for locally kept schemas, most specific first."""
    directories = []
    if explicit:
        directories.append(Path(explicit))
    from_env = os.environ.get("HOOKTESTPI_SCHEMA_DIR")
    if from_env:
        directories.append(Path(from_env))
    directories.append(Path.cwd() / "schemas")
    return directories


NAMED_SCHEMAS: dict[str, SchemaSpec] = {
    "perseus": SchemaSpec(
        description=(
            "Current EpiDoc schema from epidoc.stoa.org — the schema every "
            "Perseus canonical text declares in its xml-model PI"
        ),
        url="https://epidoc.stoa.org/schema/latest/tei-epidoc.rng",
        filename="tei-epidoc.rng",
        # epidoc.stoa.org is the GitHub Pages rendering of this branch.
        git=("https://github.com/EpiDoc/Source", "gh-pages",
             "schema/latest/tei-epidoc.rng"),
    ),
    "pta": SchemaSpec(
        description="Patristic Text Archive TEI schema (PatristicTextArchive/Schema)",
        url="https://raw.githubusercontent.com/PatristicTextArchive/Schema/master/tei-pta.rng",
        filename="tei-pta.rng",
        git=("https://github.com/PatristicTextArchive/Schema", "master",
             "tei-pta.rng"),
    ),
    "epidoc": SchemaSpec(
        description="Current EpiDoc schema (alias of 'perseus')",
        url="https://epidoc.stoa.org/schema/latest/tei-epidoc.rng",
        filename="tei-epidoc.rng",
        git=("https://github.com/EpiDoc/Source", "gh-pages",
             "schema/latest/tei-epidoc.rng"),
    ),
    "tei": SchemaSpec(
        description="Current TEI-all schema from tei-c.org",
        url="https://www.tei-c.org/release/xml/tei/custom/schema/relaxng/tei_all.rng",
        filename="tei_all.rng",
    ),
}

#: Scheme names that do not resolve to a single schema file.
PSEUDO_SCHEMES = {
    "auto": "Follow each file's own xml-model processing instruction (downloads and caches)",
    "ignore": "Skip RelaxNG validation entirely",
}


def cache_dir(explicit: str | os.PathLike | None = None) -> Path:
    """Directory holding downloaded schemas.

    Order of preference: explicit argument, ``HOOKTESTPI_CACHE``,
    ``XDG_CACHE_HOME``, then ``~/.cache``.
    """
    if explicit:
        path = Path(explicit)
    elif os.environ.get("HOOKTESTPI_CACHE"):
        path = Path(os.environ["HOOKTESTPI_CACHE"])
    else:
        base = os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")
        path = Path(base) / "hooktestpi" / "schemas"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cached_path_for_url(url: str, cache: Path | None = None) -> Path:
    """Stable on-disk name for a remote schema.

    Keeps HookTest's md5-of-URL naming so caches built by the old tool
    are still recognised.
    """
    cache = cache or cache_dir()
    return cache / (md5(url.encode()).hexdigest() + ".rng")


def download(url: str, cache: Path | None = None, timeout: int = 60) -> Path:
    """Fetch *url* into the cache, returning the local path.

    Concurrent workers coordinate through an ``.indownload`` marker so the
    same schema is not fetched several times at once.
    """
    import time

    import requests

    cache = cache or cache_dir()
    target = cached_path_for_url(url, cache)
    if target.exists():
        return target

    marker = target.with_suffix(".rng-indownload")
    if marker.exists():
        waited = timeout
        while not target.exists():
            time.sleep(1)
            waited -= 1
            if waited < 0:
                raise TimeoutError(f"Timed out waiting for another worker to download {url}")
        return target

    marker.write_text("downloading", encoding="utf-8")
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        marker.write_bytes(response.content)
        marker.replace(target)
    finally:
        if marker.exists():
            marker.unlink()
    return target


def schema_as_of(name: str, date: str, cache: Path | None = None) -> Path:
    """Fetch the named schema as it stood at the end of *date*.

    Corpora pin no schema version — every file's ``xml-model`` points at a
    moving URL — so validating an older release against today's schema can
    fail on rules that did not exist when the release was made. This
    resolves the schema from its source-of-truth git repository at the last
    commit on or before *date* (``YYYY-MM-DD``, evaluated in UTC), caching
    both the clone and the extracted file.
    """
    spec = NAMED_SCHEMAS.get(name)
    if spec is None or spec.git is None:
        raise SchemaUnavailable(
            f"--schema-date needs a schema with a git source of truth; "
            f"'{name}' has none. It applies to: "
            + ", ".join(sorted(n for n, s in NAMED_SCHEMAS.items() if s.git))
        )
    import re as _re
    import subprocess

    if not _re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise SchemaUnavailable(f"--schema-date must be YYYY-MM-DD, got '{date}'")

    url, branch, path = spec.git
    cache = cache or cache_dir()
    clone = cache / "git" / _re.sub(r"[^A-Za-z0-9._-]+", "-", url.split("://")[-1])

    def run(*argv, **kwargs):
        return subprocess.run(
            argv, capture_output=True, text=True, timeout=300, **kwargs
        )

    try:
        if not (clone / "HEAD").exists() and not (clone / ".git").exists():
            clone.parent.mkdir(parents=True, exist_ok=True)
            done = run("git", "clone", "--filter=blob:none", "--bare",
                       "--single-branch", "--branch", branch, url, str(clone))
            if done.returncode != 0:
                raise SchemaUnavailable(
                    f"Could not clone {url} for --schema-date: {done.stderr.strip()}"
                )
        else:
            run("git", "-C", str(clone), "fetch", "-q", "origin", branch)

        found = run("git", "-C", str(clone), "rev-list", "-1",
                    "--before", f"{date}T23:59:59Z", branch, "--", path)
        sha = found.stdout.strip()
        if not sha:
            raise SchemaUnavailable(
                f"{url} has no commit touching {path} on or before {date}"
            )
        target = cache / f"{name}-{date}-{sha[:12]}.rng"
        if not target.exists():
            content = run("git", "-C", str(clone), "show", f"{sha}:{path}")
            if content.returncode != 0:
                raise SchemaUnavailable(
                    f"Could not read {path} at {sha[:12]} from {url}: "
                    f"{content.stderr.strip()}"
                )
            target.write_text(content.stdout, encoding="utf-8")
        return target
    except subprocess.TimeoutExpired as exc:
        raise SchemaUnavailable(f"git timed out resolving --schema-date: {exc}") from exc


def resolve_scheme(scheme, cache: Path | None = None,
                   schema_dir: str | os.PathLike | None = None,
                   at: str | None = None) -> Path | None:
    """Resolve a ``--scheme`` value to a schema file.

    :param scheme: a name from :data:`NAMED_SCHEMAS`, ``"auto"``,
        ``"ignore"``, or a path to a local ``.rng`` file
    :param at: optional ``YYYY-MM-DD`` — resolve a named schema as it stood
        on that date (see :func:`schema_as_of`)
    :returns: the schema path, or None for ``auto``/``ignore``
    """
    if isinstance(scheme, (list, tuple)):  # legacy ["local_file", path] form
        scheme = scheme[1]
    if scheme in PSEUDO_SCHEMES:
        if at:
            raise SchemaUnavailable(
                f"--schema-date cannot apply to the '{scheme}' scheme; name a "
                "project schema (e.g. --cts-project pta, or -s pta)"
            )
        return None
    if scheme in NAMED_SCHEMAS:
        if at:
            return schema_as_of(scheme, at, cache=cache)
        return NAMED_SCHEMAS[scheme].local_path(cache=cache, schema_dir=schema_dir)
    path = Path(scheme)
    if path.is_file():
        if at:
            raise SchemaUnavailable(
                "--schema-date applies to named schemas with a git source of "
                "truth, not to a local .rng file"
            )
        return path
    raise ValueError(f"Unknown scheme and not an existing file: {scheme}")


def describe_schemes() -> str:
    """Human readable listing of every accepted ``--scheme`` value."""
    lines = []
    for name, spec in NAMED_SCHEMAS.items():
        lines.append(f"  {name:<10} {spec.description}")
    for name, description in PSEUDO_SCHEMES.items():
        lines.append(f"  {name:<10} {description}")
    lines.append(f"  {'<path>':<10} Any local RelaxNG (.rng) file")
    return "\n".join(lines)
