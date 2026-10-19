"""Filesystem-backed, append-only storage for model workflow runs."""

from collections.abc import Mapping
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

from multicowork.errors import RunConflictError, RunNotFoundError


_SAFE_LABEL = re.compile(r"^[A-Za-z0-9_-]+$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class RunStore:
    """Store each run in a separate directory without replacing evidence."""

    def __init__(self, runs_root: Path):
        self.runs_root = Path(runs_root)

    def create_run(self, kind: str, request: Mapping[str, object]) -> str:
        run_id = str(uuid.uuid4())
        run_dir = self.runs_root / run_id
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise RunConflictError(f"run already exists: {run_id}") from exc

        (run_dir / "prompts").mkdir()
        (run_dir / "rounds").mkdir()
        self._write_json_exclusive(run_dir / "request.json", request)
        (run_dir / "events.jsonl").touch(exist_ok=False)
        created_at = _utc_now()
        self._replace_json(
            run_dir / "state.json",
            {
                "run_id": run_id,
                "kind": kind,
                "status": "created",
                "created_at": created_at,
                "updated_at": created_at,
            },
        )
        return run_id

    def load_request(self, run_id: str) -> dict[str, object]:
        return self._load_json(self._run_dir(run_id) / "request.json")

    def load_state(self, run_id: str) -> dict[str, object]:
        return self._load_json(self._run_dir(run_id) / "state.json")

    def update_state(
        self, run_id: str, updates: Mapping[str, object]
    ) -> dict[str, object]:
        state_path = self._run_dir(run_id) / "state.json"
        state = self._load_json(state_path)
        state.update(updates)
        state["updated_at"] = _utc_now()
        self._replace_json(state_path, state)
        return state

    def append_event(
        self, run_id: str, event: Mapping[str, object]
    ) -> dict[str, object]:
        stored_event = dict(event)
        stored_event["timestamp"] = _utc_now()
        event_path = self._run_dir(run_id) / "events.jsonl"
        with event_path.open("a", encoding="utf-8", newline="\n") as stream:
            json.dump(stored_event, stream, ensure_ascii=False, separators=(",", ":"))
            stream.write("\n")
        return stored_event

    def create_round(
        self, run_id: str, round_number: int, snapshot: Mapping[str, object]
    ) -> Path:
        round_dir = self._round_dir(run_id, round_number)
        try:
            round_dir.mkdir(exist_ok=False)
        except FileExistsError as exc:
            raise RunConflictError(
                f"round already exists: {run_id}/{round_number:04d}"
            ) from exc
        self._write_json_exclusive(round_dir / "snapshot.json", snapshot)
        return round_dir

    def save_raw_response(
        self, run_id: str, round_number: int, source: str, raw_text: str
    ) -> Path:
        path = self._round_dir(run_id, round_number) / f"{self._label(source)}.raw.txt"
        self._write_text_exclusive(path, raw_text)
        return path

    def save_parsed_response(
        self,
        run_id: str,
        round_number: int,
        source: str,
        parsed: Mapping[str, object],
    ) -> Path:
        path = (
            self._round_dir(run_id, round_number)
            / f"{self._label(source)}.parsed.json"
        )
        self._write_json_exclusive(path, parsed)
        return path

    def save_prompt_versions(
        self, run_id: str, versions: Mapping[str, object]
    ) -> Path:
        path = self._run_dir(run_id) / "prompts" / "versions.json"
        self._write_json_exclusive(path, versions)
        return path

    def list_raw_responses(self, run_id: str) -> list[Path]:
        run_dir = self._run_dir(run_id)
        return sorted((run_dir / "rounds").glob("*/*.raw.txt"))

    def _run_dir(self, run_id: str) -> Path:
        run_dir = self.runs_root / run_id
        if not run_dir.is_dir():
            raise RunNotFoundError(f"run not found: {run_id}")
        return run_dir

    def _round_dir(self, run_id: str, round_number: int) -> Path:
        if type(round_number) is not int or round_number < 1:
            raise ValueError("round_number must be a positive integer")
        return self._run_dir(run_id) / "rounds" / f"{round_number:04d}"

    @staticmethod
    def _label(value: str) -> str:
        if not isinstance(value, str) or _SAFE_LABEL.fullmatch(value) is None:
            raise ValueError("source must contain only letters, digits, '_' or '-'")
        return value

    @staticmethod
    def _load_json(path: Path) -> dict[str, object]:
        with path.open(encoding="utf-8") as stream:
            value = json.load(stream)
        if not isinstance(value, dict):
            raise ValueError(f"expected a JSON object in {path}")
        return value

    @staticmethod
    def _write_text_exclusive(path: Path, text: str) -> None:
        try:
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(text)
        except FileExistsError as exc:
            raise RunConflictError(f"evidence already exists: {path}") from exc

    @classmethod
    def _write_json_exclusive(
        cls, path: Path, value: Mapping[str, object]
    ) -> None:
        try:
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        except FileExistsError as exc:
            raise RunConflictError(f"evidence already exists: {path}") from exc

    @staticmethod
    def _replace_json(path: Path, value: Mapping[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary_path = Path(stream.name)
                json.dump(value, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
