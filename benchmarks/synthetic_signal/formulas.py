"""Build the catalog of formulas a run measures, where both benches read it.

The Rust bench and the mstlo-python one each carried their own hardcoded copy of
the paper's sweep.  Building it here instead makes it configurable in one place,
keeps the two benches measuring the same specs by construction, and leaves what
was measured sitting next to the measurements.

The file is tab-separated rather than comma-separated because a spec contains
commas (`G[0,1000] ...`) but never a tab:

    formula_id<TAB>spec

A formula ID names a family, not a row: every bound of the globally family
shares ID 6.  That is what the analysis stage keys off -- IDs 5, 6 and 7 are the
until, globally and eventually families it fits and plots -- so custom formulas
are numbered from 100 upwards, out of the way.  They are measured and land in
the result CSVs, but no figure will show them.
"""

import argparse
import sys
from pathlib import Path

# The paper's four fixed formulas.  IDs 1-4, one row each.
FIXED = (
    (1, "(x < 0.5) and (x > -0.5)"),
    (2, "G[0,1000] (x > 0.5 -> F[0,100] (x < 0.0))"),
    (3, "(x < 0.5) U[0,1000] (x < 0.0)"),
    (4, "(G[0,100] (x < 0.5)) or (G[100,150] (x > 0.0))"),
)

# The three families, each swept over the bounds.  Their shape is fixed: it is
# the bound that varies, because the sweep exists to show how cost scales with
# it.  Anything else belongs in --custom.
FAMILIES = (
    (5, "(x < 0.0) U[0,{bound}] (x > 0.0)"),
    (6, "G[0,{bound}] (x > 0.0)"),
    (7, "F[0,{bound}] (x > 0.0)"),
)

CUSTOM_ID_START = 100

HEADER = ("formula_id", "spec")


def format_bound(bound: float) -> str:
    """A bound as an STL parser wants to see it, without a pointless `.0`."""
    if bound == int(bound):
        return str(int(bound))
    return f"{bound:.6f}".rstrip("0")


def sweep(low: float, high: float, step: float, first: float) -> list[float]:
    """The bounds the families are swept over: low, low + step, ... up to high.

    A bound of zero makes the family degenerate -- `G[0,0] (x > 0.0)` is just
    `x > 0.0`, with none of the temporal depth the sweep is measuring -- so a
    sweep that starts at zero starts at *first* instead.  That is the paper's
    `b[0] += 1`, made explicit.
    """
    if step <= 0:
        raise SystemExit(f"--bound-step must be > 0, got {step}")
    if high < low:
        raise SystemExit(f"--bound-high ({high}) is below --bound-low ({low})")

    count = int((high - low) / step + 1e-9) + 1
    # Accumulating the step would drift; multiplying and rounding does not.
    bounds = [round(low + index * step, 9) for index in range(count)]

    if bounds[0] == 0:
        bounds[0] = first
        if len(bounds) > 1 and not bounds[0] < bounds[1]:
            raise SystemExit(
                f"--first-bound ({format_bound(first)}) replaces the zero bound but is not "
                f"below the next one ({format_bound(bounds[1])})"
            )

    return bounds


def parse_ids(raw: str) -> set[int] | None:
    """The `FORMULA_IDS` selection: commas, whitespace or newlines, or nothing."""
    tokens = raw.replace(",", " ").split()
    if not tokens:
        return None

    ids = set()
    for token in tokens:
        try:
            ids.add(int(token))
        except ValueError:
            raise SystemExit(f"--formula-ids takes whole numbers, got '{token}'") from None
    return ids


def parse_custom(raw: str) -> list[str]:
    """The extra formulas, one per line, blank lines ignored."""
    return [line.strip() for line in raw.splitlines() if line.strip()]


def build(
    bounds: list[float],
    selected: set[int] | None,
    custom: list[str],
    custom_id_start: int = CUSTOM_ID_START,
) -> list[tuple[int, str]]:
    """The catalog: the built-ins the selection asks for, then the custom ones.

    The selection applies to the built-ins only.  A custom formula was written
    out by hand in the config, so asking for it twice would be strange.
    """
    catalog = [
        (formula_id, spec)
        for formula_id, spec in FIXED
        if selected is None or formula_id in selected
    ]

    for formula_id, template in FAMILIES:
        if selected is not None and formula_id not in selected:
            continue
        catalog += [(formula_id, template.format(bound=format_bound(bound))) for bound in bounds]

    catalog += [(custom_id_start + index, spec) for index, spec in enumerate(custom)]

    if not catalog:
        raise SystemExit("nothing to measure: --formula-ids selected none of 1-7 and there are no custom formulas")

    for _, spec in catalog:
        if "\t" in spec:
            raise SystemExit(f"a formula cannot contain a tab: '{spec}'")

    return catalog


def check_parses(catalog: list[tuple[int, str]]) -> None:
    """Reject a malformed spec now rather than hours into the sweep.

    Both benches parse a formula only when they reach it, so a typo in a custom
    formula -- numbered last, and therefore measured last -- would otherwise
    surface at the very end of a run.  The bindings are what the benches use, so
    they are what says whether a spec is good; outside the image they are not
    installed, and the check is skipped.
    """
    try:
        import mstlo_python
    except ImportError:
        return

    for formula_id, spec in catalog:
        try:
            mstlo_python.parse_formula(spec)
        except Exception as error:
            raise SystemExit(f"formula {formula_id} does not parse: '{spec}': {error}") from None


def write(path: Path, catalog: list[tuple[int, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        f.write("\t".join(HEADER) + "\n")
        for formula_id, spec in catalog:
            f.write(f"{formula_id}\t{spec}\n")


def read(path: Path) -> list[tuple[int, str]]:
    """The other side of write(), for the tests and for anything reporting."""
    lines = path.read_text().splitlines()
    if not lines or tuple(lines[0].split("\t")) != HEADER:
        raise SystemExit(f"{path} does not start with a '{HEADER[0]}\\t{HEADER[1]}' header")

    catalog = []
    for line in lines[1:]:
        if not line:
            continue
        formula_id, spec = line.split("\t", 1)
        catalog.append((int(formula_id), spec))
    return catalog


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", required=True, help="output TSV path")
    parser.add_argument("--bound-low", type=float, default=0.0, help="first bound of the family sweep")
    parser.add_argument("--bound-high", type=float, default=5000.0, help="last bound of the family sweep")
    parser.add_argument("--bound-step", type=float, default=100.0, help="distance between bounds")
    parser.add_argument(
        "--first-bound",
        type=float,
        default=1.0,
        help="what a zero first bound becomes, since G[0,0] has no temporal depth",
    )
    parser.add_argument(
        "--formula-ids",
        default="",
        help="which of the built-in 1-7 to measure; empty is all of them",
    )
    parser.add_argument(
        "--custom",
        default="",
        help="extra formulas, one per line, numbered from 100",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    catalog = build(
        bounds=sweep(args.bound_low, args.bound_high, args.bound_step, args.first_bound),
        selected=parse_ids(args.formula_ids),
        custom=parse_custom(args.custom),
    )
    check_parses(catalog)
    write(Path(args.output), catalog)

    families = sorted({formula_id for formula_id, _ in catalog})
    print(
        f"{len(catalog)} formulas over {len(families)} IDs ({', '.join(map(str, families))})"
        f" -> {args.output}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
