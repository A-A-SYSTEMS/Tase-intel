"""
Forbidden pattern scanner for tase-intel.

Sole authority: IMPLEMENTATION_GUARDRAILS_V1.0.1.md §2 and §4.

This module ONLY detects the three patterns enumerated below. Adding a fourth
pattern requires a spec amendment first.
"""
from dataclasses import dataclass
from pathlib import Path
import re

# Bitemporal tables — exact list from IMPLEMENTATION_GUARDRAILS §2.4.
# Sole source: do not duplicate elsewhere.
BITEMPORAL_TABLES = (
    "prices_daily",
    "events",
    "companies",
    "features_at_event",
    "macro_daily",
    "corporate_actions",
    "intraday_quotes_summary",
)

# Directories that are scanned for source code.
SCAN_ROOTS = ("src", "scripts")

# Subdirectories that are skipped even within SCAN_ROOTS.
EXCLUDED_SUBDIRS = ("migrations/versions",)

# File extensions scanned.
SCANNED_EXTENSIONS_PYTHON = (".py",)
SCANNED_EXTENSIONS_SQL = (".sql",)


@dataclass(frozen=True)
class Violation:
    rule: str
    file: Path
    line_number: int
    line_text: str
    rationale: str


# ---------------------------------------------------------------------------
# File enumeration
# ---------------------------------------------------------------------------

def _is_excluded(path: Path, repo_root: Path) -> bool:
    """Return True if *path* falls under an excluded subdirectory."""
    rel = path.relative_to(repo_root)
    parts = rel.as_posix()
    for exc in EXCLUDED_SUBDIRS:
        if f"/{exc}/" in f"/{parts}/" or parts.startswith(f"{exc}/"):
            return True
    return False


def iter_target_files(
    repo_root: Path, extensions: tuple[str, ...]
) -> list[Path]:
    """Return files under SCAN_ROOTS with the given extensions,
    excluding EXCLUDED_SUBDIRS."""
    results: list[Path] = []
    for root_name in SCAN_ROOTS:
        root_dir = repo_root / root_name
        if not root_dir.is_dir():
            continue
        for ext in extensions:
            for f in root_dir.rglob(f"*{ext}"):
                if not _is_excluded(f, repo_root):
                    results.append(f)
    return sorted(results)


# ---------------------------------------------------------------------------
# Pattern 1 — Calendar-day emb.argo arithmetic
# IMPLEMENTATION_GUARDRAILS §2.4, §4.3
# ---------------------------------------------------------------------------

_RE_TIMEDELTA_DAYS = re.compile(r"timedelta\s*\(\s*days\s*=", re.IGNORECASE)
_RE_EMBARGO = re.compile(r"embargo", re.IGNORECASE)
_EMBARGO_WINDOW = 5  # lines above and below


def detect_pattern_1_embargo(repo_root: Path) -> list[Violation]:
    """P1: calendar-day arithmetic near emb-argo keyword."""
    violations: list[Violation] = []
    for fpath in iter_target_files(repo_root, SCANNED_EXTENSIONS_PYTHON):
        lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
        for idx, line in enumerate(lines):
            if not _RE_TIMEDELTA_DAYS.search(line):
                continue
            # Check inline comment on same line
            if _RE_EMBARGO.search(line):
                violations.append(Violation(
                    rule="P1_calendar_day_embargo",
                    file=fpath,
                    line_number=idx + 1,
                    line_text=line,
                    rationale="IMPLEMENTATION_GUARDRAILS §2.4, §4.3",
                ))
                continue
            # Check ±5 line window
            window_start = max(0, idx - _EMBARGO_WINDOW)
            window_end = min(len(lines), idx + _EMBARGO_WINDOW + 1)
            window_text = "\n".join(lines[window_start:window_end])
            if _RE_EMBARGO.search(window_text):
                violations.append(Violation(
                    rule="P1_calendar_day_embargo",
                    file=fpath,
                    line_number=idx + 1,
                    line_text=line,
                    rationale="IMPLEMENTATION_GUARDRAILS §2.4, §4.3",
                ))
    return violations


# ---------------------------------------------------------------------------
# Pattern 2 — Same-day close reference
# IMPLEMENTATION_GUARDRAILS §2.5, §4.6
# ---------------------------------------------------------------------------

_RE_SAME_DAY_CLOSE = re.compile(
    r"business_date\s*=\s*DATE\s*\(\s*(?:\w+\.)?\s*event_observable_at\s*\)",
    re.IGNORECASE | re.MULTILINE,
)


def detect_pattern_2_same_day_close(repo_root: Path) -> list[Violation]:
    """P2: same-day close join pattern."""
    violations: list[Violation] = []
    extensions = SCANNED_EXTENSIONS_PYTHON + SCANNED_EXTENSIONS_SQL
    for fpath in iter_target_files(repo_root, extensions):
        lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
        for idx, line in enumerate(lines):
            if _RE_SAME_DAY_CLOSE.search(line):
                violations.append(Violation(
                    rule="P2_same_day_close",
                    file=fpath,
                    line_number=idx + 1,
                    line_text=line,
                    rationale="IMPLEMENTATION_GUARDRAILS §2.5, §4.6",
                ))
    return violations


# ---------------------------------------------------------------------------
# Pattern 3 — Bitemporal table direct query (no _as_of wrapper)
# IMPLEMENTATION_GUARDRAILS §2.4, §4.8
# ---------------------------------------------------------------------------

_BITEMPORAL_REGEXES = {
    table: re.compile(
        rf"\bFROM\s+{table}\b(?!\s*_as_of)",
        re.IGNORECASE,
    )
    for table in BITEMPORAL_TABLES
}


def detect_pattern_3_bitemporal_bypass(repo_root: Path) -> list[Violation]:
    """FROM <bitemporal_table> without _as_of suffix."""
    violations: list[Violation] = []
    extensions = SCANNED_EXTENSIONS_PYTHON + SCANNED_EXTENSIONS_SQL
    for fpath in iter_target_files(repo_root, extensions):
        lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
        for idx, line in enumerate(lines):
            for table, pattern in _BITEMPORAL_REGEXES.items():
                if pattern.search(line):
                    violations.append(Violation(
                        rule="P3_bitemporal_bypass",
                        file=fpath,
                        line_number=idx + 1,
                        line_text=line,
                        rationale=(
                            f"IMPLEMENTATION_GUARDRAILS §2.4, §4.8 — "
                            f"use {table}_as_of() instead of direct FROM {table}"
                        ),
                    ))
    return violations


# ---------------------------------------------------------------------------
# Convenience aggregator
# ---------------------------------------------------------------------------

def scan_all(repo_root: Path) -> list[Violation]:
    return (
        detect_pattern_1_embargo(repo_root)
        + detect_pattern_2_same_day_close(repo_root)
        + detect_pattern_3_bitemporal_bypass(repo_root)
    )
