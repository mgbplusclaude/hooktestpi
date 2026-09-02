"""RelaxNG validation backends.

Validation is reference-grade only: Jing (the reference implementation,
needs Java) or the relaxng-rust ``rng`` binary (no JVM). libxml2 is not
used — it cannot compile every TEI-scale grammar and diverges from the
reference implementation on the ones it can.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from importlib import metadata, util
from pathlib import Path

__all__ = [
    "BackendUnavailable", "SchemaCompilationError", "JingBackend",
    "RustBackend", "get_validator", "available_backends", "strip_jvm_banner",
]


class BackendUnavailable(RuntimeError):
    """Raised when a requested backend cannot run on this machine."""


class SchemaCompilationError(RuntimeError):
    """Raised when a schema is not a usable RelaxNG grammar."""


def strip_jvm_banner(raw: bytes) -> str:
    """Drop the JVM's "Picked up VAR: ..." lines from Jing's output.

    The JVM announces every options environment variable it honours on
    stderr — ``_JAVA_OPTIONS``, ``JAVA_TOOL_OPTIONS`` and
    ``JDK_JAVA_OPTIONS`` alike — and CI images and proxied environments set
    these routinely. Whatever Jing leaves on the streams is read as a
    validation error, so a banner that slips through fails every file in the
    corpus rather than none.
    """
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    return "\n".join(
        line for line in text.split("\n") if not line.startswith("Picked up ")
    )


class JingBackend:
    """Validate with Jing. Matches HookTest 1.3.1 exactly, but needs Java."""

    name = "jing"

    def __init__(self, rng_path, timeout: int = 30, jar: str | None = None):
        self.rng_path = str(rng_path)
        self.timeout = timeout
        self.jar = jar or self.find_jar()
        if self.jar is None:
            raise BackendUnavailable("jing.jar not found (pip install jingtrang)")
        if shutil.which("java") is None:
            raise BackendUnavailable("java not found on PATH")

    @staticmethod
    def find_jar() -> str | None:
        """Locate jing.jar without importing jingtrang.

        jingtrang's ``__init__`` imports ``pkg_resources``, which modern
        virtualenvs no longer provide by default and which is gone for good
        on newer Pythons. Importing the package to reach a data file next to
        it therefore fails on exactly the interpreters this tool targets,
        and the Jing fallback would report itself unavailable with the jar
        sitting in site-packages. Both routes below read the installation
        rather than executing it.
        """
        try:
            for entry in metadata.files("jingtrang") or ():
                if entry.name == "jing.jar":
                    located = Path(str(entry.locate()))
                    if located.is_file():
                        return str(located)
        except Exception:  # noqa: BLE001 - fall through to the spec lookup
            pass

        try:
            spec = util.find_spec("jingtrang")
        except Exception:  # noqa: BLE001 - a broken package is not a jar
            spec = None
        for location in getattr(spec, "submodule_search_locations", None) or ():
            candidate = Path(location) / "jing.jar"
            if candidate.is_file():
                return str(candidate)
        return None

    def validate(self, xml_path) -> list[str]:
        try:
            process = subprocess.run(
                [
                    "java", "-Duser.country=US", "-Duser.language=en",
                    "-jar", self.jar, self.rng_path, str(xml_path),
                ],
                capture_output=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ["Timeout on RelaxNG validation"]

        from hooktestpi.units import TESTUnit

        combined = (
            strip_jvm_banner(process.stdout) + "\n" + strip_jvm_banner(process.stderr)
        ).strip()
        if not combined:
            return []
        return list(TESTUnit.rng_logs(combined))


class RustBackend:
    """Validate with the relaxng-rust ``rng`` tool. No JVM, reference-grade.

    Verdicts match Jing's on real TEI corpora, with no Java needed. The
    binary is found through ``HOOKTESTPI_RNG`` or as ``rng`` on PATH; until
    the upstream fixes (dholroyd/relaxng-rust) are released it is built
    from the patched source — see the README.
    """

    name = "rust"

    #: One diagnostic looks like ``error: <msg>`` followed by
    #: ``--> <file>:<line>:<col>`` on the next line.
    _ANSI = __import__("re").compile(r"\x1b\[[0-9;]*m")
    _LOCATION = __import__("re").compile(r"^\s*-->\s.*:(\d+):(\d+)\s*$")

    def __init__(self, rng_path, timeout: int = 30, binary: str | None = None):
        self.rng_path = str(rng_path)
        self.timeout = timeout
        self.binary = binary or self.find_binary()
        if self.binary is None:
            raise BackendUnavailable(
                "relaxng-rust 'rng' binary not found (set HOOKTESTPI_RNG or put "
                "'rng' on PATH; see README for building it)"
            )

    @staticmethod
    def find_binary() -> str | None:
        candidate = os.environ.get("HOOKTESTPI_RNG")
        if candidate and Path(candidate).is_file():
            return candidate
        return shutil.which("rng")

    @classmethod
    def parse_errors(cls, raw) -> list[str]:
        """Collapse the tool's multi-line diagnostics to one line per error."""
        text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        text = cls._ANSI.sub("", text)
        errors = []
        pending = None
        for line in text.split("\n"):
            if line.startswith("error:"):
                if pending:
                    errors.append(pending)
                pending = line[len("error:"):].strip()
                continue
            if pending:
                location = cls._LOCATION.match(line)
                if location:
                    errors.append(
                        "(L{0} C{1}) {2}".format(
                            location.group(1), location.group(2), pending
                        )
                    )
                    pending = None
        if pending:
            errors.append(pending)
        return errors

    def validate(self, xml_path) -> list[str]:
        try:
            process = subprocess.run(
                [self.binary, "validate", self.rng_path, str(xml_path)],
                capture_output=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ["Timeout on RelaxNG validation"]
        if process.returncode == 0:
            return []
        errors = self.parse_errors(process.stderr) + self.parse_errors(process.stdout)
        return errors or [
            "relaxng-rust exited with status {0}".format(process.returncode)
        ]


def available_backends() -> dict[str, bool]:
    """Report which backends can run here."""
    return {
        "rust": RustBackend.find_binary() is not None,
        "jing": JingBackend.find_jar() is not None and shutil.which("java") is not None,
    }


_CACHE: dict[tuple[str, str], object] = {}


def get_validator(rng_path, backend: str = "auto", run_timeout: int = 30, log=None):
    """Build (and cache) a validator for *rng_path*.

    :param backend: ``jing``, ``rust`` or ``auto`` (Jing, then rust)
    :param log: optional callable receiving progress messages
    """
    key = (backend, str(rng_path))
    if key in _CACHE:
        return _CACHE[key]

    if backend == "jing":
        validator = JingBackend(rng_path, timeout=run_timeout)
    elif backend == "rust":
        validator = RustBackend(rng_path, timeout=run_timeout)
    else:
        try:
            validator = JingBackend(rng_path, timeout=run_timeout)
        except BackendUnavailable:
            try:
                validator = RustBackend(rng_path, timeout=run_timeout)
                if log is not None:
                    log("Jing not available; using the relaxng-rust backend")
            except BackendUnavailable as exc:
                raise BackendUnavailable(
                    "No RelaxNG backend is available: Jing needs Java on "
                    "PATH, and the relaxng-rust 'rng' binary was not found "
                    f"(set HOOKTESTPI_RNG or put 'rng' on PATH) ({exc})."
                ) from exc
    _CACHE[key] = validator
    return validator

