from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


RESULT_NOT_TESTED = "Not tested"
RESULT_OK = "OK"
RESULT_FAIL = "FAIL"
RESULT_NA = "N/A"
RESULT_OPTIONS = (RESULT_NOT_TESTED, RESULT_OK, RESULT_FAIL, RESULT_NA)

RESULT_FILTER_ALL = "All"
RESULT_FILTER_PENDING = "Pending"
RESULT_FILTER_WITH_STATUS = "With status"
RESULT_FILTER_OK = RESULT_OK
RESULT_FILTER_FAIL = RESULT_FAIL
RESULT_FILTER_NA = RESULT_NA
RESULT_FILTER_MIXED = "Mixed"
RESULT_FILTER_OPTIONS = (
    RESULT_FILTER_ALL,
    RESULT_FILTER_PENDING,
    RESULT_FILTER_WITH_STATUS,
    RESULT_FILTER_OK,
    RESULT_FILTER_FAIL,
    RESULT_FILTER_NA,
    RESULT_FILTER_MIXED,
)


@dataclass(frozen=True)
class PanelResult:
    target: str
    result: str = RESULT_NOT_TESTED
    comment: str = ""
    updated_at: str = ""


def make_panel_result(
    target: str,
    result: str,
    comment: str,
    updated_at: str | None = None,
) -> PanelResult:
    normalized_result = result if result in RESULT_OPTIONS else RESULT_NOT_TESTED
    return PanelResult(
        target=target,
        result=normalized_result,
        comment=comment.strip(),
        updated_at=updated_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def should_keep_result(panel_result: PanelResult) -> bool:
    return panel_result.result != RESULT_NOT_TESTED or bool(panel_result.comment)


def summarize_family_result(
    family_name: str,
    variant_names: list[str],
    results: dict[str, PanelResult],
) -> str:
    family_result = results.get(family_name)
    if family_result and should_keep_result(family_result):
        return family_result.result

    variant_results = [
        results[variant_name].result
        for variant_name in variant_names
        if variant_name in results and should_keep_result(results[variant_name])
    ]
    if not variant_results:
        return RESULT_NOT_TESTED

    unique_results = set(variant_results)
    suffix = f" ({len(variant_results)}/{len(variant_names)})" if len(variant_names) > 1 else ""
    if len(unique_results) == 1:
        return f"{variant_results[0]}{suffix}"
    return f"Mixed{suffix}"


def result_matches_filter(result_summary: str, result_filter: str) -> bool:
    if result_filter == RESULT_FILTER_ALL:
        return True
    if result_filter == RESULT_FILTER_PENDING:
        return result_summary == RESULT_NOT_TESTED
    if result_filter == RESULT_FILTER_WITH_STATUS:
        return result_summary != RESULT_NOT_TESTED
    if result_filter == RESULT_FILTER_MIXED:
        return result_summary.startswith(RESULT_FILTER_MIXED)
    if result_filter in {RESULT_OK, RESULT_FAIL, RESULT_NA}:
        return result_summary == result_filter or result_summary.startswith(f"{result_filter} ")
    return True
