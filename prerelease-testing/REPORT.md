# hooktestpi 1.0.0 — pre-release test report

Date: 2026-08-31. Tested from the uploaded release artifacts
(`hooktestpi-1.0.0.tar.gz`, `hooktestpi-1.0.0-py3-none-any.whl`) on
**Python 3.14.7** (uv-managed), targeting a 3.14-only release.

## Package installation

- Wheel installs cleanly on 3.14.7 with `MyCapytain 3.0.2`, `lxml 6.1.2`,
  `requests 2.34.2`. Both entry points (`hooktestpi`, `hooktestpi-build`)
  work; `import hooktestpi` reports version 1.0.0.
- sdist and wheel package sources are byte-identical.
- Note: MyCapytain 3.0.2 pulls in the obsolete PyPI `typing` backport
  (harmless at runtime on 3.14, stdlib wins on sys.path, but worth a
  pin/exclusion note in the README at some point).

## Unit test suite

- **Blocker found in the sdist**: `tests/conftest.py` is missing from the
  tarball, so `tests/test_run.py` and `tests/test_structure.py` (33 of 69
  tests) fail at collection. The fixtures were reconstructed from the
  tests' expectations and package internals — see `tests/conftest.py` in
  this branch; the sdist build config needs to include it (and the release
  sdist rebuilt).
- With the reconstructed conftest: **71/71 tests pass on Python 3.14.7**
  (and on 3.13 as a cross-check).

## Real-corpus runs (console + manifest in this directory)

| Corpus | Command profile | Result |
|---|---|---|
| Homer, Iliad (`tlg0012.tlg001`, PerseusDL/canonical-greekLit) | `--cts-project perseus --schema-dir ./schemas -v 7 --countwords --manifest` | exit 0, 3/3 texts + 2/2 metadata, coverage 100.0, 16,374 citation units, 444,141 words |
| Homer, Odyssey (`tlg0012.tlg002`) | same | exit 0, 3/3 texts + 2/2 metadata, coverage 100.0, 12,734 citation units, 339,800 words |
| Severian of Gabala, *De fide et lege naturae* (`pta0001.pta001`, PatristicTextArchive/pta_data) | `--cts-project pta -v 7 --countwords --manifest` | exit 0, 19/19 texts + 2/2 metadata, coverage 100.0, 57 citation units, 62,823 words |

Both runs read the full CTS URN tree — textgroup- and work-level
`__cts__.xml` — and the manifests list texts together with both metadata
files, matching classic HookTest output.

Notes from the runs:

- The Perseus texts at current HEAD use TEI `<citeStructure>`, which the
  bundled 2017 EpiDoc schema rejects; the current EpiDoc schema (what
  `--cts-project perseus` downloads from epidoc.stoa.org) validates them.
  In this sandbox epidoc.stoa.org was blocked by the egress proxy, so the
  schema was fetched from its GitHub Pages source
  (EpiDoc/Source@gh-pages) and supplied via `--schema-dir` — the tool's
  documented offline path worked as designed.
- On the PTA run, libxml2 stalled compiling the PTA schema (>120s); the
  schema-repair path kicked in automatically, validation completed against
  the relaxed grammar, and the console clearly marks those RelaxNG results
  as advisory with a pointer to `--rng-backend jing`. This is the designed
  no-Java degradation and it behaved correctly.
- When a named schema cannot be downloaded at all, texts fail RNG
  validation with the log line `Error reading file 'None'` — correct
  outcome, unhelpful message. Cosmetic; could say "schema unavailable".
- `manifest.txt` is written without a trailing newline (same as upstream).

## Status

Superseded by the 1.0.0 release: validation is reference-grade only
(Jing default, relaxng-rust fallback), the libxml2 backend and the
relaxation machinery described below were removed, and schemas are
pulled live from their canonical sources. The findings below are kept
as the record of the testing that led there.

## Addendum: reference-grade RelaxNG (jing) comparison on the PTA run

Java happened to be available in the test sandbox, so the Severian run was
repeated with `--rng-backend jing` (`severian-jing-console.txt`):
**12/19 texts pass, coverage 97.92** — seven genuine schema violations that
the relaxed-libxml2 run had (correctly, per its advisory contract) not
asserted: invalid `place` tokens (`overstrike`, `erase`, `overwrite`) in
witness transcriptions, `msIdentifier` missing required `corresp` in four
catalog files, and misplaced `witDetail` in `pta-grcBibex`. These are
corpus-vs-schema drift in pta_data HEAD, not tool artifacts.

Survey of non-Java engines against this exact schema (tei-pta.rng,
TEI P5 4.11.0 ODD build):

- **libxml2 2.14.6** (current): compile does not finish (>60s; upstream
  pathology in attribute analysis triggered by `rend`), and after repair it
  reports element-content errors jing does not — not reference-grade.
- **relaxng-rust (dholroyd)**: fails to load the schema — its XML-syntax
  reader treats `<data type="token">` + `<param name="pattern">` as the
  parameter-less RELAX NG built-in library even when
  `datatypeLibrary="...XMLSchema-datatypes"` is declared (minimal repro
  confirmed). Promising engine, not usable on TEI schemas today.
- **rnv (C)**: compact syntax only; converting .rng→.rnc needs trang
  (Java) — circular.

Conclusion: no existing non-Java engine validates TEI-scale RelaxNG at
reference grade today. jing remains the only reference-quality option;
a GraalVM native-image build of jing (self-contained binary, no JVM at
runtime) is the most credible path to "reference-grade without installing
Java".
