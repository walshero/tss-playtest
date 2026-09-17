# BUILD — 2026-09-17 — covenant floor lift, five assessment surfaces

Branch cut from `3bf3077`.

## The finding

`V49-DESIGN-DOCKET-2026-09-16.md` scoped V49 as surgical work on
`confluence-hub/`: 60 font-size declarations under the 18px floor, smallest
11px. Those numbers are correct — for `confluence-hub/` in the
`TIGHT-SPIRAL-STUDIOS` repo.

**This lane has no `confluence-hub/`.** Its assessment surfaces are standalone
files, and they are worse:

| file | sub-floor before | after | smallest before |
|---|---|---|---|
| `islo-hub.html` | 36 | 0 | 9px |
| `scorer-norming.html` | 36 | 0 | 10px |
| `score-the-room.html` | 37 | 0 | 10px |
| `rubric-forge.html` | 33 | 0 | 9.5px |
| `review-bench.html` | 20 | 0 | 10.5px |
| **total** | **162** | **0** | **9px** |

162, not 149. A px-only census cannot see two other forms that also render
below the floor: sub-1rem font sizes (`.74`/`.76`/`.8`/`.82rem`, and in
`review-bench` even `1.02`/`1.06`/`1.08rem` against a 16px root), and `clamp()`
minimums (16px, 17px). `tools/floor-gate.py` catches all three.

## The mechanism, not a new scale

`confluence-TRUNK.html` does not hold the floor declaration-by-declaration. It
holds it once, at the root:

    html{font-size:18px}  + 446 rem declarations, 391 of them exactly 1rem

Hierarchy rides on weight, colour and spacing — not on shrinking text below the
floor. `tools/lift-to-covenant-floor.py` ports that mechanism. Sizes at or above
the floor keep their rendered size exactly. Sizes below rise to it. Nothing
shrinks.

## Reproducibility

The lifted bytes are a pure function of the script and the source commit:

    python3 tools/lift-to-covenant-floor.py <src>.html <out>.html

Run against the five files at `3bf3077`, the committed script reproduces these
exact md5s:

    64faa234831541bbf5eea4f050d4a2cd  islo-hub.html
    ee02b1f9895e34c815daa66c4f5c8407  scorer-norming.html
    4ee135e7f59daf31bd1bb1218e8cc926  score-the-room.html
    15ef588e5bb3ab23f93b4d41b324d5da  rubric-forge.html
    43238e32c3c2f3f9033343e26884e356  review-bench.html

Verified this session: the script fetched back from this branch, run on the
pristine originals, regenerates all five byte-for-byte.

## Gates

    tools/floor-gate.py   PASS on all five lifted files, exit 0
    tools/floor-gate.py   PASS on confluence-TRUNK.html (canon)
    preship-contrast      SHIP, exit 0, worst text pair 5.57
    emoji / dingbats      0 / 0
    collateral diff       only font-size declarations and the root differ

The gate passing canon matters: it is calibrated against the artifact that
already holds the covenant, not against an assumption.

## A bug worth recording

The first run set the root to 18px FIRST. The px pass then matched that very
declaration and rewrote it to `font-size:1rem` — a self-referential root that
falls back to 16px and puts every size on the page BELOW the floor. The output
looked correct and was wrong.

The first verification passed it, because that check assumed the root was 18px
instead of resolving it. `floor-gate.py` now resolves the root from the document
and HALTs if it is missing, self-referential, or a percentage.

A gate that assumes its own premise is a wish.

## Still open

- **The five lifted `.html` files are not in this branch yet.** They were
  delivered as files in session. They were deliberately not re-typed into API
  calls — transcribing 265 KB of markup by hand is how transcription-drift
  entered the ledger. Push them with git, or regenerate them with the command
  above and verify against the md5s.
- `review-bench.html` couples 52 layout declarations (padding, gap, width,
  border-radius) to rem. Moving its root 16px -> 18px scales that layout by
  1.125. Proportional, not breakage, but it is visible and wants real eyes.
- Night-stop walkthrough on Matt's own screen — the one gate arithmetic cannot
  close.
