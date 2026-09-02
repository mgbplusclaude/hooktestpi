"""Project profiles for ``--cts-project``.

A CapiTainS repository is only half-described by the CTS guidelines: each
project layers its own conventions on top. PTA texts do not validate
against the Perseus schema, and Perseus texts do not validate against
PTA's. A profile bundles the schema, the guideline flavour and the
structural conventions that belong together, so that one flag selects a
coherent set instead of the caller wiring them up by hand.

Profiles deliberately constrain only what the corpora demonstrably agree
on. A survey of Perseus, PTA and nine further CapiTainS repositories
showed ``textpart/@subtype`` vocabularies ranging over ``verse``,
``poem``, ``strophe``, ``antistrophe``, ``anapests``, ``scene`` and many
more, so subtype is never allow-listed — doing so would fail valid texts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = ["ProjectProfile", "PROFILES", "get_profile"]


@dataclass(frozen=True)
class ProjectProfile:
    """Conventions that belong to one CapiTainS project.

    :param scheme: default ``--scheme`` when the caller does not pass one
    :param guidelines: default CapiTainS guideline flavour
    :param div_types: values allowed on ``<div type="...">`` directly under
        ``<body>``; None disables the check
    :param version_pattern: expected shape of the version component of a
        text URN (``perseus-lat2``, ``pta-MsL``); None disables the check
    """

    name: str
    description: str
    scheme: str = "auto"
    guidelines: str = "2.epidoc"
    div_types: frozenset[str] | None = None
    version_pattern: str | None = None
    urn_namespaces: frozenset[str] | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    def check_div_type(self, value: str | None) -> str | None:
        """Return an error message when *value* is not an allowed div type."""
        if self.div_types is None or value is None:
            return None
        if value in self.div_types:
            return None
        return (
            f"<div type=\"{value}\"> is not used by the {self.name} project "
            f"(expected one of: {', '.join(sorted(self.div_types))})"
        )

    def check_version(self, version: str | None) -> str | None:
        """Return an error message when the URN version part looks wrong."""
        if self.version_pattern is None or not version:
            return None
        if re.fullmatch(self.version_pattern, version):
            return None
        return (
            f"version identifier '{version}' does not match the {self.name} "
            f"convention /{self.version_pattern}/"
        )

    def check_namespace(self, namespace: str | None) -> str | None:
        if self.urn_namespaces is None or not namespace:
            return None
        if namespace in self.urn_namespaces:
            return None
        return (
            f"CTS namespace '{namespace}' is not one the {self.name} project uses "
            f"({', '.join(sorted(self.urn_namespaces))})"
        )


GENERIC = ProjectProfile(
    name="generic",
    description="Any CapiTainS repository; CTS guidelines only, no project conventions",
    scheme="auto",
    guidelines="2.epidoc",
)

PERSEUS = ProjectProfile(
    name="perseus",
    description="Perseus Digital Library canonical-* repositories (EpiDoc schema)",
    scheme="perseus",
    guidelines="2.epidoc",
    div_types=frozenset({"edition", "translation", "commentary", "textpart"}),
    # perseus-lat2, perseus-grc2, perseus-eng3 ...
    version_pattern=r"[A-Za-z0-9]+-[a-z]{3}\d+",
    notes=(
        "Perseus texts declare https://epidoc.stoa.org/schema/latest/tei-epidoc.rng "
        "in their xml-model processing instruction.",
    ),
)

PTA = ProjectProfile(
    name="pta",
    description="Patristic Text Archive (PTA TEI schema, critical editions and witness transcriptions)",
    scheme="pta",
    guidelines="2.epidoc",
    div_types=frozenset(
        {"edition", "translation", "commentary", "praefatio", "textpart"}
    ),
    # pta-grc1, pta-deu1, pta-eng1 for editions/translations; pta-MsL,
    # pta-MsPb ... for witness transcriptions.
    version_pattern=r"pta-(?:[a-z]{3}[A-Za-z0-9]*|Ms[A-Za-z0-9]+)",
    notes=(
        "PTA texts declare the PatristicTextArchive/Schema tei-pta.rng schema.",
        "Witness transcriptions use a pta-Ms<siglum> version identifier and "
        "carry an xml:id on <msIdentifier> that the critical edition references.",
    ),
)

PROFILES: dict[str, ProjectProfile] = {
    profile.name: profile for profile in (GENERIC, PERSEUS, PTA)
}


def get_profile(name: str | None) -> ProjectProfile:
    """Look up a profile by name, defaulting to ``generic``."""
    if not name:
        return GENERIC
    try:
        return PROFILES[name]
    except KeyError:
        raise ValueError(
            f"Unknown --cts-project '{name}'. Available: {', '.join(sorted(PROFILES))}"
        ) from None


def describe_profiles() -> str:
    lines = []
    for name in sorted(PROFILES):
        profile = PROFILES[name]
        lines.append(f"  {name:<10} {profile.description}")
    return "\n".join(lines)
