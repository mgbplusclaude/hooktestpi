# hooktestpi

Validation for [CapiTainS](http://capitains.org/)/CTS corpora of TEI digital
editions. A port of [HookTest](https://pypi.org/project/HookTest/) for
**Python 3.14**.

Checks the `data/<textgroup>/<work>/` layout, every `__cts__.xml`, URN/filename
agreement, citation passages, RelaxNG validation, `<div>` ordering and `xml:id`
uniqueness — then writes a `manifest.txt` of everything that passed.

## Install

```bash
python3.14 -m venv .venv
.venv/bin/pip install hooktestpi
```

## Validation

Validation is reference-grade only. The default backend is Jing (the
reference implementation, shipped with the package; Java required).
Without Java, the [relaxng-rust](https://github.com/dholroyd/relaxng-rust)
`rng` binary is the fallback — same verdicts, no JVM — found through
`HOOKTESTPI_RNG` or `PATH`. Until the upstream datatype fixes are released,
build it from the patched source:

```bash
git clone https://github.com/mgbplusclaude/relaxng-rust -b fix-xml-datatype-library-resolution
cargo build --release -p relaxng-tool --manifest-path relaxng-rust/Cargo.toml
export HOOKTESTPI_RNG=$PWD/relaxng-rust/target/release/rng
```

Schemas are pulled from their canonical sources and cached — the current
EpiDoc schema for Perseus, `tei-pta.rng` for the Patristic Text Archive,
TEI-all from tei-c.org. Nothing is bundled, so validation always reflects
the published standard. Keep copies in `--schema-dir DIR` to run offline.

## Use

```bash
# Patristic Text Archive (console output and manifest.txt are defaults)
hooktestpi ./pta_data --cts-project pta -v 7

# Perseus, with word counts and a JSON report
hooktestpi ./canonical-greekLit --cts-project perseus -v 7 --countwords -j report.json

# One textgroup, work or version; or straight from a git remote
hooktestpi ./corpus -f tlg0012.tlg001
hooktestpi https://github.com/PerseusDL/canonical-greekLit --cts-project perseus

# Older editions: the schema as it stood when they were released
hooktestpi ./corpus --cts-project pta --schema-date 2025-06-01

# Legacy pre-EpiDoc conversions: generic TEI-all, URN on <text>/<body>
hooktestpi ./corpus --tei-p4

# CI: no console chatter, no manifest
hooktestpi ./corpus --quiet --no-manifest
```

Build a release containing only the passing files:

```bash
hooktestpi-build ./corpus --ci --txt --cites --tar
```

Exit `0` if everything passed, `1` if anything failed, `2` if the corpus
could not be read.

MIT (`LICENSE`); files derived from HookTest remain MPL-2.0 (`LICENSE.MPL-2.0`).
