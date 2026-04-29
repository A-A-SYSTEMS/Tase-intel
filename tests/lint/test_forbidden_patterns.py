"""
Forbidden pattern lint tests — scan the real repo.

Each test calls the corresponding detector against the actual codebase
and asserts zero violations.
"""
import pytest

from src.lint.forbidden_patterns import (
    detect_pattern_1_embargo,
    detect_pattern_2_same_day_close,
    detect_pattern_3_bitemporal_bypass,
)


def _format_violations(violations):
    return "\n".join(
        f"  {v.file}:{v.line_number}: {v.line_text.strip()}"
        for v in violations
    )


def test_no_calendar_day_embargo(repo_root):
    """
    IMPLEMENTATION_GUARDRAILS §2.4, §4.3:
    timedelta(days=N) used for embargo arithmetic is forbidden.
    Trading-day math goes through tase_trading_calendar.
    """
    violations = detect_pattern_1_embargo(repo_root)
    if violations:
        pytest.fail(
            "Calendar-day embargo detected:\n" + _format_violations(violations)
        )


def test_no_same_day_close(repo_root):
    """
    IMPLEMENTATION_GUARDRAILS §2.5, §4.6:
    business_date = DATE(event_observable_at) is forbidden.
    Use subtract_trading_days() for pre-event pricing.
    """
    violations = detect_pattern_2_same_day_close(repo_root)
    if violations:
        pytest.fail(
            "Same-day close reference detected:\n" + _format_violations(violations)
        )


def test_no_bitemporal_bypass(repo_root):
    """
    IMPLEMENTATION_GUARDRAILS §2.4, §4.8:
    Direct FROM on bitemporal tables is forbidden in application code.
    Use the corresponding *_as_of() function instead.
    """
    violations = detect_pattern_3_bitemporal_bypass(repo_root)
    if violations:
        pytest.fail(
            "Bitemporal bypass detected:\n" + _format_violations(violations)
        )
