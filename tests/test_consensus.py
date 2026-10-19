import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from multicowork.consensus import consensus_conclusion
from multicowork.protocols import AuditResponse


def response(agree=True, conclusion="The result is 42."):
    return AuditResponse("answer", "reason", [], [], agree, conclusion)


class ConsensusTests(unittest.TestCase):
    def test_both_true_and_exact_conclusions_return_trimmed_conclusion(self):
        self.assertEqual(
            consensus_conclusion(response(conclusion="  The result is 42.\n"),
                                 response(conclusion="The result is 42.  ")),
            "The result is 42.",
        )

    def test_any_false_flag_prevents_consensus(self):
        for left, right in ((False, True), (True, False), (False, False)):
            with self.subTest(left=left, right=right):
                self.assertIsNone(consensus_conclusion(response(left), response(right)))

    def test_empty_or_whitespace_conclusion_prevents_consensus(self):
        for left, right in (("", ""), (" \n", " \t"), ("valid", "")):
            with self.subTest(left=left, right=right):
                self.assertIsNone(consensus_conclusion(response(conclusion=left),
                                                       response(conclusion=right)))

    def test_different_text_never_uses_similarity_or_semantics(self):
        for left, right in (("The result is 42.", "The result is 42!"),
                            ("42", "forty-two"), ("Same", "same")):
            with self.subTest(left=left, right=right):
                self.assertIsNone(consensus_conclusion(response(conclusion=left),
                                                       response(conclusion=right)))


if __name__ == "__main__":
    unittest.main()
