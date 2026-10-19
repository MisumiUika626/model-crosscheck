"""Strict, data-only parsing of model response protocols."""

from dataclasses import dataclass, fields
import json

from .errors import FormatError


@dataclass(frozen=True)
class AuditResponse:
    answer: str
    reasoning_summary: str
    agreements: list[str]
    disputes: list[str]
    agree: bool
    final_conclusion: str


@dataclass(frozen=True)
class TaskContract:
    goal: str
    inputs: list[str]
    constraints: list[str]
    output_format: str
    acceptance_criteria: list[str]


@dataclass(frozen=True)
class WorkerResult:
    result: str
    uncertainties: list[str]
    criteria_evidence: list[str]


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise FormatError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _one_object(raw: str) -> dict[str, object]:
    if not isinstance(raw, str) or not raw.strip():
        raise FormatError("empty or non-text response")

    decoder = json.JSONDecoder(object_pairs_hook=_unique_pairs)
    starts = []
    in_string = False
    escaped = False
    for index, char in enumerate(raw):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "{":
            starts.append(index)

    if len(starts) != 1:
        raise FormatError("response must contain exactly one unambiguous JSON object")
    try:
        value, _ = decoder.raw_decode(raw, starts[0])
    except json.JSONDecodeError as exc:
        raise FormatError("invalid JSON object") from exc
    if not isinstance(value, dict):
        raise FormatError("response must be a JSON object")
    return value


def _parse(raw: str, model: type, string_fields: set[str], list_fields: set[str]):
    value = _one_object(raw)
    expected = {field.name for field in fields(model)}
    if value.keys() != expected:
        raise FormatError(f"expected exactly these fields: {', '.join(sorted(expected))}")
    for name in string_fields:
        if type(value[name]) is not str:
            raise FormatError(f"{name} must be a string")
    for name in list_fields:
        items = value[name]
        if type(items) is not list or any(type(item) is not str for item in items):
            raise FormatError(f"{name} must be a list of strings")
    if model is AuditResponse and type(value["agree"]) is not bool:
        raise FormatError("agree must be a boolean")
    return model(**value)


def parse_audit_response(raw: str) -> AuditResponse:
    return _parse(raw, AuditResponse,
                  {"answer", "reasoning_summary", "final_conclusion"},
                  {"agreements", "disputes"})


def parse_task_contract(raw: str) -> TaskContract:
    return _parse(raw, TaskContract, {"goal", "output_format"},
                  {"inputs", "constraints", "acceptance_criteria"})


def parse_worker_result(raw: str) -> WorkerResult:
    return _parse(raw, WorkerResult, {"result"},
                  {"uncertainties", "criteria_evidence"})
