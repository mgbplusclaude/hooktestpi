"""Shared fixtures: a minimal CapiTainS repository generated on the fly.

``section`` and ``build_text`` produce a single EpiDoc-flavoured TEI file;
the ``repository`` fixture lays out the full ``data/<textgroup>/<work>/``
tree (textgroup and work ``__cts__.xml`` plus one edition) that the
end-to-end tests run against.
"""

import pytest

URN_GROUP = "urn:cts:latinLit:phi9999"
URN_WORK = URN_GROUP + ".phi001"
URN_EDITION = URN_WORK + ".perseus-lat1"


def section(n, extra=""):
    """One citation div: ``<div type="textpart" subtype="section" n="...">``."""
    return (
        '<div type="textpart" subtype="section" n="{0}"{1}>'
        "<p>Text of section {0}</p>"
        "</div>"
    ).format(n, extra)


TEXT_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader>
    <fileDesc>
      <titleStmt>
        <title>Fixture Work</title>
      </titleStmt>
      <publicationStmt>
        <p>hooktestpi test fixture</p>
      </publicationStmt>
      <sourceDesc>
        <p>Born digital</p>
      </sourceDesc>
    </fileDesc>
    <encodingDesc>
      <refsDecl n="CTS">
        <cRefPattern n="section" matchPattern="(\\w+)"
          replacementPattern="#xpath(/tei:TEI/tei:text/tei:body/tei:div/tei:div[@n='$1'])">
          <p>This pointer pattern extracts section</p>
        </cRefPattern>
      </refsDecl>
    </encodingDesc>
  </teiHeader>
  <text>
    <body>
      <div type="edition" n="{urn}" xml:lang="lat">
{divs}
      </div>
    </body>
  </text>
</TEI>
"""

TEXTGROUP_METADATA = """<?xml version="1.0" encoding="UTF-8"?>
<ti:textgroup xmlns:ti="http://chs.harvard.edu/xmlns/cts" urn="{group}">
  <ti:groupname xml:lang="eng">Fixture Author</ti:groupname>
</ti:textgroup>
""".format(group=URN_GROUP)

WORK_METADATA = """<?xml version="1.0" encoding="UTF-8"?>
<ti:work xmlns:ti="http://chs.harvard.edu/xmlns/cts"
    xml:lang="lat" urn="{work}" groupUrn="{group}">
  <ti:title xml:lang="eng">Fixture Work</ti:title>
  <ti:edition urn="{edition}" workUrn="{work}">
    <ti:label xml:lang="eng">Fixture Edition</ti:label>
    <ti:description xml:lang="eng">A generated edition for the test suite</ti:description>
  </ti:edition>
</ti:work>
""".format(group=URN_GROUP, work=URN_WORK, edition=URN_EDITION)


def build_text(divs, urn=URN_EDITION):
    """A complete TEI file wrapping *divs* in an edition div."""
    return TEXT_TEMPLATE.format(urn=urn, divs=divs)


@pytest.fixture
def repository(tmp_path):
    """Factory building a clean CapiTainS repository; ``divs=`` overrides
    the edition's citation divs (default: sections 1, 2, 3)."""

    def build(divs=None):
        if divs is None:
            divs = "\n".join(section(i) for i in (1, 2, 3))
        root = tmp_path / "repo"
        work_dir = root / "data" / "phi9999" / "phi001"
        work_dir.mkdir(parents=True, exist_ok=True)
        (root / "data" / "phi9999" / "__cts__.xml").write_text(
            TEXTGROUP_METADATA, encoding="utf-8"
        )
        (work_dir / "__cts__.xml").write_text(WORK_METADATA, encoding="utf-8")
        (work_dir / "phi9999.phi001.perseus-lat1.xml").write_text(
            build_text(divs), encoding="utf-8"
        )
        return root

    return build
