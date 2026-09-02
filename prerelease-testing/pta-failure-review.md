# Review: the 7 PTA validation failures (pta0001.pta001)

Reference-grade validation (jing and patched relaxng-rust agree exactly)
of the 19 texts of Severian of Gabala, *De fide et lege naturae*, against
the current `tei-pta.rng` (TEI P5 4.11.0 build, 2026-02-18; byte-identical
to the user-supplied fresh download modulo NBSP normalization). 12 pass;
the 7 failures fall into four classes, none of them tool artifacts:

## 1. `add/@place` correction-method tokens — MsAb (2×), MsVa (1×)

`<add place="overstrike">`, `<add place="erase">`, `<add place="overwrite">`
in the witness transcriptions. The schema constrains `add/@place` to
`above | below | inline | margin`. These three tokens describe *how* a
correction was made, not *where* — TEI-canonically they belong on
`<del rend="…">`/`<subst>`. No schema revision in the past year allowed
them, so these encodings have never validated against the published
schema. **File-side fix.**

## 2. `msIdentifier` missing `@corresp` — MsCatJm, MsCatOx, MsCatPa, MsCatVat

The PTA schema requires `msIdentifier/@corresp`, linking the catalog
entry to the PTA manuscript registry (`corresp="PTAMS00571"` in the
*passing* MsCatCo shows the intended pattern). Four catalog files lack
the link. **File-side fix (add the registry IDs).**

## 3. `witDetail` inside `app` — grcBibex (4×)

`<witDetail wit="#Pa" target="#lac-Pa">Blattausfall.</witDetail>` inside
apparatus entries. The schema allowed `witDetail` until 2025-06-06
(Schema@59cf913) and removed it on 2025-06-13 (Schema@ae7062b, "remove
witDetail"): the encoding was valid when written and the **schema moved
under it**. Either the schema should re-admit `witDetail` (it is standard
TEI critical-apparatus vocabulary) or the files should migrate to
`<note>` — a PTA-team decision.

## 4. `seg/@type="fq"` — grcBibex (3×)

Allowed `seg/@type` values are `allusion | insertion | psq | similar |
source | textpart`; `fq` (Folgezitat?) appears in no recent schema
revision. Either an undocumented convention that should be added to the
ODD, or a file-side fix.

## Why PTA's own release validation passed these files

Their `manifest.txt` lists all 21 files as passing. Two contributing
mechanisms, both verified:

- The files pin no schema version — every file's `xml-model` points at
  the un-pinned `master` URL, so validity is a moving target; class 3 is
  a direct consequence.
- libxml2 cannot compile `tei-pta.rng` at all (current libxml2 2.14.6
  included), so any lxml/libxml2-based pipeline had no working RelaxNG
  enforcement of this schema; classes 1, 2 and 4 have been invalid all
  year yet shipped, consistent with RNG validation being silently absent
  or advisory at release time.

hooktestpi with the relaxng-rust backend closes exactly this gap:
reference verdicts, no Java, no relaxation.
