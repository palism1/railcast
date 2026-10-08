# FILE MAP
#   purpose: keep every file's FILE MAP header in sync with its "# == Section ==" markers
#   sections:
#     L14-35  Parsing
#     L38-64  Rewrite
#     L67-90  CLI
# END FILE MAP
"""Regenerate (or --check) FILE MAP line ranges. Run: python scripts/filemap.py [--check]."""

import re
import sys
from pathlib import Path

# == Parsing ==
MARKER = re.compile(r"^\s*# == (.+?) ==\s*$")
START, END = "# FILE MAP", "# END FILE MAP"
GLOBS = [
    "src/**/*.py",
    "tests/**/*.py",
    "scripts/*.py",
    ".github/workflows/*.yml",
    "pyproject.toml",
]


def sections(lines: list[str]) -> list[tuple[str, int, int]]:
    """Return (name, first_line, last_line) per section, 1-indexed, trailing blanks trimmed."""
    marks = [(i, m.group(1)) for i, ln in enumerate(lines) if (m := MARKER.match(ln))]
    out = []
    for n, (i, name) in enumerate(marks):
        end = marks[n + 1][0] - 1 if n + 1 < len(marks) else len(lines) - 1
        while end > i and not lines[end].strip():
            end -= 1
        out.append((name, i + 1, end + 1))
    return out


# == Rewrite ==
def render(text: str) -> str | None:
    lines = text.split("\n")
    try:
        s, e = lines.index(START), lines.index(END)
    except ValueError:
        return None
    purpose = [ln for ln in lines[s:e] if ln.startswith("#   purpose:")]
    # Header length depends on section count, not line numbers, so one pass is stable.
    for _ in range(3):
        body = lines[e + 1 :]
        n_secs = sum(1 for ln in body if MARKER.match(ln))
        header_len = 2 + len(purpose) + (1 + n_secs if n_secs else 0)
        offset = s + header_len
        new = [START, *purpose]
        secs = sections(body)
        if secs:
            new.append("#   sections:")
            new += [f"#     L{a + offset}-{b + offset}  {name}" for name, a, b in secs]
        new.append(END)
        lines = lines[:s] + new + body
        e = s + len(new) - 1
    return "\n".join(lines)


def files(root: Path) -> list[Path]:
    return sorted({p for g in GLOBS for p in root.glob(g) if p.is_file()})


# == CLI ==
def main() -> int:
    root = Path(__file__).resolve().parent.parent
    check = "--check" in sys.argv
    stale, missing = [], []
    for p in files(root):
        text = p.read_text()
        new = render(text)
        if new is None:
            missing.append(p)
            continue
        if new != text:
            stale.append(p)
            if not check:
                p.write_text(new)
    for p in missing:
        print(f"no FILE MAP header: {p.relative_to(root)}")
    for p in stale:
        print(f"{'stale' if check else 'updated'} FILE MAP: {p.relative_to(root)}")
    return 1 if check and (stale or missing) else 0


if __name__ == "__main__":
    sys.exit(main())
