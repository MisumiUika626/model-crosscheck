import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from multicowork.errors import FormatError
from multicowork.protocols import (
    AuditResponse,
    TaskContract,
    WorkerResult,
    parse_audit_response,
    parse_task_contract,
    parse_worker_result,
)


CASES = (
    (parse_audit_response, AuditResponse, {
        "answer": "answer", "reasoning_summary": "reason", "agreements": ["a"],
        "disputes": ["d"], "agree": False, "final_conclusion": "",
    }, "agreements"),
    (parse_task_contract, TaskContract, {
        "goal": "goal", "inputs": ["input"], "constraints": ["constraint"],
        "output_format": "text", "acceptance_criteria": ["check"],
    }, "inputs"),
    (parse_worker_result, WorkerResult, {
        "result": "result", "uncertainties": ["uncertain"],
        "criteria_evidence": ["evidence"],
    }, "uncertainties"),
)


class ProtocolTests(unittest.TestCase):
    def test_valid_objects_preserve_values(self):
        for parse, model, payload, _ in CASES:
            with self.subTest(model=model):
                self.assertEqual(parse(json.dumps(payload)), model(**payload))

    def test_missing_and_extra_fields_rejected(self):
        for parse, _, payload, _ in CASES:
            for changed in ({k: v for k, v in payload.items() if k != next(iter(payload))},
                            {**payload, "unexpected": 1}):
                with self.subTest(parse=parse, changed=changed):
                    with self.assertRaises(FormatError):
                        parse(json.dumps(changed))

    def test_wrong_scalar_and_list_item_types_rejected(self):
        for parse, _, payload, list_key in CASES:
            for changed in ({**payload, next(iter(payload)): 42},
                            {**payload, list_key: "not a list"},
                            {**payload, list_key: ["ok", 42]}):
                with self.subTest(parse=parse, changed=changed):
                    with self.assertRaises(FormatError):
                        parse(json.dumps(changed))
        audit = CASES[0][2]
        with self.assertRaises(FormatError):
            parse_audit_response(json.dumps({**audit, "agree": 1}))

    def test_empty_and_non_object_response_rejected(self):
        for parse, _, _, _ in CASES:
            for raw in ("", "  ", "[]", "null", "42", "not JSON"):
                with self.subTest(parse=parse, raw=raw):
                    with self.assertRaises(FormatError):
                        parse(raw)

    def test_fenced_or_prose_wrapped_object_and_braces_in_string(self):
        for parse, model, payload, _ in CASES:
            payload = {**payload, next(iter(payload)): "value with {braces} and escaped \"quote\""}
            encoded = json.dumps(payload)
            for raw in (f"```json\n{encoded}\n```", f"Explanation:\n{encoded}\nEnd."):
                with self.subTest(parse=parse, raw=raw):
                    self.assertEqual(parse(raw), model(**payload))

    def test_multiple_objects_and_ambiguous_braces_rejected(self):
        for parse, _, payload, _ in CASES:
            encoded = json.dumps(payload)
            for raw in (encoded + "\n" + encoded, "note {} then " + encoded,
                        "note {broken} then " + encoded, encoded + " trailing {brace}"):
                with self.subTest(parse=parse, raw=raw):
                    with self.assertRaises(FormatError):
                        parse(raw)

    def test_duplicate_json_field_rejected(self):
        for parse, _, payload, _ in CASES:
            key = next(iter(payload))
            encoded = json.dumps(payload)
            duplicate = encoded[:-1] + f', "{key}": "overridden"' + "}"
            with self.subTest(parse=parse):
                with self.assertRaises(FormatError):
                    parse(duplicate)


if __name__ == "__main__":
    unittest.main()
