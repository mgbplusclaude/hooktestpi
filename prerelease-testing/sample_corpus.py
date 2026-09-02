"""Materialize a random sample of a CapiTainS corpus for pre-release testing.

Samples a fraction of the *edition files* (``data/<tg>/<work>/<version>.xml``,
``__cts__.xml`` excluded) with a fixed seed, fetches the needed work
directories into the source checkout (sparse, blob-on-demand), and copies
the sampled editions together with their work- and textgroup-level
``__cts__.xml`` into a standalone corpus directory that hooktestpi can run
on directly. Copying (rather than testing the sparse checkout in place)
keeps unsampled sibling editions out of the run, so the tested set is
exactly the sample.

Usage: python sample_corpus.py <repo> <out_dir> [fraction] [seed]
"""

import random
import shutil
import subprocess
import sys
from pathlib import Path


def main(repo, out_dir, fraction=0.10, seed=20260901):
    repo = Path(repo)
    out = Path(out_dir)

    listing = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", "HEAD", "data/"],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()

    editions = [
        p for p in listing
        if p.count("/") == 3 and p.endswith(".xml") and not p.endswith("__cts__.xml")
    ]
    count = max(1, round(len(editions) * fraction))
    sample = sorted(random.Random(seed).sample(editions, count))
    work_dirs = sorted({str(Path(p).parent) for p in sample})

    print(f"{repo.name}: {len(editions)} editions, sampling {count} "
          f"across {len(work_dirs)} works (seed {seed})")

    # Cone-mode sparse checkout of the sampled work directories also brings
    # in the files sitting directly in ancestor directories, which includes
    # each textgroup's __cts__.xml.
    subprocess.run(
        ["git", "-C", str(repo), "sparse-checkout", "set", "--cone", *work_dirs],
        check=True,
    )

    if out.exists():
        shutil.rmtree(out)
    copied = 0
    for edition in sample:
        source = repo / edition
        if not source.is_file():
            print(f"  missing in checkout, skipped: {edition}")
            continue
        for wanted in (
            source,
            source.parent / "__cts__.xml",
            source.parent.parent / "__cts__.xml",
        ):
            if not wanted.is_file():
                continue
            target = out / wanted.relative_to(repo)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copy2(wanted, target)
                copied += 1
    print(f"materialized {copied} files under {out}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2],
         float(sys.argv[3]) if len(sys.argv) > 3 else 0.10,
         int(sys.argv[4]) if len(sys.argv) > 4 else 20260901)
