import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from multicowork.storage.run_store import RunStore
from multicowork.errors import RunConflictError, RunNotFoundError


class RunStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.runs_root = Path(self.temp_dir.name) / "runs"
        self.store = RunStore(self.runs_root)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_run_uses_uuid_and_documented_layout(self):
        request = {"question": "哪个结论可靠？"}

        run_id = self.store.create_run("audit", request)

        self.assertEqual(str(uuid.UUID(run_id)), run_id)
        run_dir = self.runs_root / run_id
        self.assertEqual(self.store.load_request(run_id), request)
        state = self.store.load_state(run_id)
        self.assertEqual(state["run_id"], run_id)
        self.assertEqual(state["kind"], "audit")
        self.assertEqual(state["status"], "created")
        self.assertTrue(state["created_at"].endswith("Z"))
        self.assertEqual(state["created_at"], state["updated_at"])
        self.assertTrue((run_dir / "events.jsonl").is_file())
        self.assertEqual((run_dir / "events.jsonl").read_text(encoding="utf-8"), "")
        self.assertTrue((run_dir / "prompts").is_dir())
        self.assertTrue((run_dir / "rounds").is_dir())

    def test_update_state_atomically_replaces_complete_json(self):
        run_id = self.store.create_run("delegate", {"goal": "draft"})
        state_path = self.runs_root / run_id / "state.json"
        original_inode = state_path.stat().st_ino

        self.store.update_state(run_id, {"status": "running", "note": "处理中"})

        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "running")
        self.assertEqual(state["note"], "处理中")
        self.assertNotEqual(state_path.stat().st_ino, original_inode)
        self.assertEqual(list(state_path.parent.glob(".state.json.*.tmp")), [])

    def test_failed_state_replace_preserves_previous_state_and_cleans_temp(self):
        run_id = self.store.create_run("audit", {"question": "q"})
        before = self.store.load_state(run_id)

        with patch("multicowork.storage.run_store.os.replace", side_effect=OSError("stop")):
            with self.assertRaises(OSError):
                self.store.update_state(run_id, {"status": "running"})

        self.assertEqual(self.store.load_state(run_id), before)
        run_dir = self.runs_root / run_id
        self.assertEqual(list(run_dir.glob(".state.json.*.tmp")), [])

    def test_events_are_utf8_json_lines_appended_in_order(self):
        run_id = self.store.create_run("audit", {"question": "q"})

        self.store.append_event(run_id, {"type": "started", "detail": "开始"})
        self.store.append_event(run_id, {"type": "paused", "detail": "等待"})

        lines = (self.runs_root / run_id / "events.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        self.assertEqual([json.loads(line)["detail"] for line in lines], ["开始", "等待"])
        self.assertTrue(all(json.loads(line)["timestamp"].endswith("Z") for line in lines))

    def test_round_response_and_prompt_files_follow_layout(self):
        run_id = self.store.create_run("audit", {"question": "q"})

        round_dir = self.store.create_round(run_id, 1, {"version": 1})
        raw_path = self.store.save_raw_response(run_id, 1, "gpt", "原始回答")
        parsed_path = self.store.save_parsed_response(
            run_id, 1, "gpt", {"answer": "解析结果"}
        )
        versions_path = self.store.save_prompt_versions(
            run_id, {"audit": "audit-v1"}
        )

        self.assertEqual(round_dir, self.runs_root / run_id / "rounds" / "0001")
        self.assertEqual(
            json.loads((round_dir / "snapshot.json").read_text(encoding="utf-8")),
            {"version": 1},
        )
        self.assertEqual(raw_path.read_text(encoding="utf-8"), "原始回答")
        self.assertEqual(
            json.loads(parsed_path.read_text(encoding="utf-8")),
            {"answer": "解析结果"},
        )
        self.assertEqual(
            json.loads(versions_path.read_text(encoding="utf-8")),
            {"audit": "audit-v1"},
        )

    def test_evidence_files_and_rounds_cannot_be_overwritten(self):
        run_id = self.store.create_run("audit", {"question": "q"})
        self.store.create_round(run_id, 1, {"version": 1})
        self.store.save_raw_response(run_id, 1, "gpt", "first")
        self.store.save_parsed_response(run_id, 1, "gpt", {"answer": "first"})
        self.store.save_prompt_versions(run_id, {"audit": "audit-v1"})

        operations = (
            lambda: self.store.create_round(run_id, 1, {"version": 2}),
            lambda: self.store.save_raw_response(run_id, 1, "gpt", "second"),
            lambda: self.store.save_parsed_response(
                run_id, 1, "gpt", {"answer": "second"}
            ),
            lambda: self.store.save_prompt_versions(run_id, {"audit": "audit-v2"}),
        )
        for operation in operations:
            with self.subTest(operation=operation):
                with self.assertRaises(RunConflictError):
                    operation()

    def test_duplicate_run_id_is_rejected_without_touching_existing_run(self):
        fixed_uuid = uuid.UUID("11111111-1111-4111-8111-111111111111")
        with patch("multicowork.storage.run_store.uuid.uuid4", return_value=fixed_uuid):
            run_id = self.store.create_run("audit", {"question": "first"})
            with self.assertRaises(RunConflictError):
                self.store.create_run("audit", {"question": "second"})

        self.assertEqual(self.store.load_request(run_id), {"question": "first"})

    def test_fresh_store_reloads_state_request_and_sorted_raw_responses(self):
        run_id = self.store.create_run("audit", {"question": "恢复"})
        for round_number in (2, 1):
            self.store.create_round(run_id, round_number, {"round": round_number})
            self.store.save_raw_response(
                run_id, round_number, "deepseek", f"回答 {round_number}"
            )
        self.store.update_state(run_id, {"status": "awaiting_user"})

        reloaded = RunStore(self.runs_root)

        self.assertEqual(reloaded.load_request(run_id), {"question": "恢复"})
        self.assertEqual(reloaded.load_state(run_id)["status"], "awaiting_user")
        self.assertEqual(
            [path.relative_to(self.runs_root / run_id).as_posix()
             for path in reloaded.list_raw_responses(run_id)],
            ["rounds/0001/deepseek.raw.txt", "rounds/0002/deepseek.raw.txt"],
        )

    def test_missing_runs_and_invalid_round_numbers_are_rejected(self):
        missing = "00000000-0000-4000-8000-000000000000"
        with self.assertRaises(RunNotFoundError):
            self.store.load_state(missing)

        run_id = self.store.create_run("audit", {"question": "q"})
        for round_number in (0, -1):
            with self.subTest(round_number=round_number):
                with self.assertRaises(ValueError):
                    self.store.create_round(run_id, round_number, {})


if __name__ == "__main__":
    unittest.main()
