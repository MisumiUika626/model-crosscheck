"""Mechanical agreement check for two validated audit responses."""

from .protocols import AuditResponse


def consensus_conclusion(left: AuditResponse, right: AuditResponse) -> str | None:
    if left.agree is not True or right.agree is not True:
        return None
    conclusion = left.final_conclusion.strip()
    if conclusion and conclusion == right.final_conclusion.strip():
        return conclusion
    return None
