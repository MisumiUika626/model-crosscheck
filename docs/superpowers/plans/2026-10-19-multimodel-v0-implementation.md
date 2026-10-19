# Multi-model Audit and Delegation V0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete local Python V0 CLI for offline delegation, cross-audit, evidence retention, user continuation/decisions, replay, and explicitly gated live model adapters.

**Architecture:** Keep workflow policy in `AuditWorkflow` and `DelegateWorkflow`, strict JSON boundary validation in `protocols.py`, and all filesystem layout/atomic state updates behind `RunStore`. Model adapters share one small call interface; offline mocks establish the whole behavior before live Codex CLI and DeepSeek transports are added.

**Tech Stack:** Python 3.10+ standard library, `unittest`, `argparse`, `dataclasses`, `json`, `pathlib`, `subprocess`, `urllib.request`.

**Spec:** `docs/superpowers/specs/2026-10-19-multimodel-v0-design.md`

## Global Constraints

- Use Python 3.10+ and the standard library only.
- Default to offline mock behavior; no live Codex or DeepSeek call without the matching explicit CLI flag.
- Require both `DEEPSEEK_API_KEY` and `--allow-paid-api` before constructing a live DeepSeek request.
- Never execute generated code or write generated output into user-selected target files.
- Persist raw model output before parsing; never overwrite round evidence.
- Keep `runs/`, environment files, credentials, and authorization headers out of Git and logs.
- Consensus requires both `agree is True` and identical, non-empty, stripped `final_conclusion` values.

## Review Focus

- A JSON object surrounded by prose or braces inside a JSON string must be extracted safely or rejected without choosing the wrong brace pair; pin in Task 1.
- An existing run ID or round directory must never be overwritten; pin in Task 2.
- A failed second-side audit call must retain the first raw response and leave a non-completed state; pin in Task 4.
- `continue` and `decide` must reject runs outside `awaiting_user`; pin in Task 5.
- Live DeepSeek mode with a missing key or missing paid flag must fail before any transport call; pin in Task 6.

---

### Task 1: Package foundation, protocols, and consensus

**Files:**
- Create: `pyproject.toml`
- Create: `src/multicowork/__init__.py`
- Create: `src/multicowork/errors.py`
- Create: `src/multicowork/protocols.py`
- Create: `src/multicowork/consensus.py`
- Test: `tests/test_protocols.py`
- Test: `tests/test_consensus.py`

**Interfaces:**
- Consumes: raw model response strings.
- Produces: `AuditResponse`, `TaskContract`, `WorkerResult`; `parse_audit_response(raw)`, `parse_task_contract(raw)`, `parse_worker_result(raw)`; `consensus_conclusion(left, right) -> str | None`; typed `FormatError`.

- [ ] **Step 1: Write failing protocol tests** for exact valid payloads, missing/extra fields, wrong scalar/list item types, empty response, fenced/prose-wrapped JSON, and braces embedded inside JSON strings.
- [ ] **Step 2: Run `python -m unittest tests.test_protocols -v`** and verify it fails because the package does not exist.
- [ ] **Step 3: Implement package metadata, protocol dataclasses, one-object extraction with `json.JSONDecoder.raw_decode`, and strict field/type validation.**
- [ ] **Step 4: Run `python -m unittest tests.test_protocols -v`** and verify all protocol tests pass.
- [ ] **Step 5: Write failing consensus tests** covering both flags, whitespace trimming, empty conclusions, unequal conclusions, and no semantic similarity fallback.
- [ ] **Step 6: Implement `consensus_conclusion(left: AuditResponse, right: AuditResponse) -> str | None`.**
- [ ] **Step 7: Run `python -m unittest tests.test_consensus -v`** and verify all consensus tests pass.
- [ ] **Step 8: Commit explicit Task 1 paths with `feat: add strict model protocols`.**

### Task 2: Append-only run storage

**Files:**
- Create: `src/multicowork/storage/__init__.py`
- Create: `src/multicowork/storage/run_store.py`
- Test: `tests/test_run_store.py`

**Interfaces:**
- Consumes: a runs root `Path`, run kind/request mappings, round numbers, raw text, parsed mappings, event mappings, and state mappings.
- Produces: `RunStore.create_run`, `load_request`, `load_state`, `update_state`, `append_event`, `create_round`, `save_raw_response`, `save_parsed_response`, `save_prompt_versions`, and `list_raw_responses`; `RunConflictError`/`RunNotFoundError`.

- [ ] **Step 1: Write failing storage tests** for the documented file layout, UUID run IDs, atomic state replacement, append-only events, immutable response files, duplicate run/round rejection, UTF-8, and reload from a fresh store instance.
- [ ] **Step 2: Run `python -m unittest tests.test_run_store -v`** and verify it fails because `RunStore` does not exist.
- [ ] **Step 3: Implement `RunStore`** using exclusive file creation for evidence, temporary sibling plus `os.replace` for `state.json`, and UTC ISO timestamps.
- [ ] **Step 4: Run `python -m unittest tests.test_run_store -v`** and verify all storage tests pass.
- [ ] **Step 5: Commit explicit Task 2 paths with `feat: add append-only run storage`.**

### Task 3: Adapter contract, deterministic mocks, and delegate workflow

**Files:**
- Create: `src/multicowork/adapters/__init__.py`
- Create: `src/multicowork/adapters/base.py`
- Create: `src/multicowork/adapters/mock.py`
- Create: `src/multicowork/prompts.py`
- Create: `src/multicowork/workflows/__init__.py`
- Create: `src/multicowork/workflows/delegate.py`
- Test: `tests/test_delegate_workflow.py`

**Interfaces:**
- Consumes: `ModelAdapter.call(role: str, prompt: str, protocol: str) -> ModelCallResult`, user goal/background, and `RunStore`.
- Produces: `ModelCallResult(raw_text: str, metadata: dict[str, object])`; `MockAdapter` with queued fixed responses and call capture; `DelegateWorkflow.run(...) -> str` returning the run ID.

- [ ] **Step 1: Write failing delegate tests** for prompt version recording, contract-before-worker ordering, raw-before-parsed evidence, saved metadata without secrets, invalid contract stopping before worker, and exact worker result persistence.
- [ ] **Step 2: Run `python -m unittest tests.test_delegate_workflow -v`** and verify it fails because workflow modules do not exist.
- [ ] **Step 3: Implement the adapter protocol, queue-based mock, versioned prompt builders, and `DelegateWorkflow`.**
- [ ] **Step 4: Run `python -m unittest tests.test_delegate_workflow -v`** and verify all delegate tests pass.
- [ ] **Step 5: Commit explicit Task 3 paths with `feat: add offline delegation workflow`.**

### Task 4: Three-round audit workflow and unbiased snapshots

**Files:**
- Create: `src/multicowork/workflows/audit.py`
- Test: `tests/test_audit_workflow.py`

**Interfaces:**
- Consumes: two `ModelAdapter` instances, `RunStore`, question/background/candidate text, and `max_rounds: int = 3`.
- Produces: `AuditWorkflow.run(...) -> str`; states `running`, `completed_by_consensus`, `awaiting_user`, or `failed`; round snapshots visible identically to both adapters.

- [ ] **Step 1: Write failing audit tests** for initial independent answers, a shared pre-round snapshot, early exact consensus, whitespace normalization, three-round disagreement, monotonically increasing versions, and one-side failure retaining the other side's raw evidence without completing.
- [ ] **Step 2: Run `python -m unittest tests.test_audit_workflow -v`** and verify it fails because `AuditWorkflow` does not exist.
- [ ] **Step 3: Implement `AuditWorkflow`** so each round persists its snapshot before either call and derives both prompts solely from that immutable snapshot.
- [ ] **Step 4: Run `python -m unittest tests.test_audit_workflow -v`** and verify all audit tests pass.
- [ ] **Step 5: Commit explicit Task 4 paths with `feat: add bounded cross-audit workflow`.**

### Task 5: Offline CLI, inspection, continuation, decisions, and replay

**Files:**
- Create: `src/multicowork/cli.py`
- Create: `src/multicowork/__main__.py`
- Modify: `src/multicowork/workflows/audit.py`
- Modify: `src/multicowork/storage/run_store.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_recovery.py`

**Interfaces:**
- Consumes: `delegate`, `audit`, `continue`, `decide`, `show`, and `replay` CLI arguments; stored run IDs; `--text` xor UTF-8 `--file`; optional `--runs-dir`.
- Produces: `main(argv: list[str] | None = None) -> int`; readable stdout/stderr; persisted user decisions/supplements; replay reports that never call an adapter or overwrite evidence.

- [ ] **Step 1: Write failing CLI tests** for `delegate --mock`, `audit --mock`, `show`, mutually exclusive input sources, missing run IDs, non-zero failures, and default `runs/` behavior.
- [ ] **Step 2: Run `python -m unittest tests.test_cli -v`** and verify it fails because the CLI does not exist.
- [ ] **Step 3: Implement argparse commands and readable summaries**, keeping all workflow logic outside `cli.py`.
- [ ] **Step 4: Run `python -m unittest tests.test_cli -v`** and verify the first runnable slice passes.
- [ ] **Step 5: Write failing recovery tests** for continuing only `awaiting_user`, appending three more rounds and optional supplement, deciding via GPT/DeepSeek/custom conclusion, rejecting invalid state transitions, replaying every stored raw response offline, and preserving original parsed files.
- [ ] **Step 6: Implement continuation/decision methods and replay reporting.**
- [ ] **Step 7: Run `python -m unittest tests.test_recovery -v`** and verify all recovery tests pass.
- [ ] **Step 8: Run `python -m unittest discover -s tests -v`** and verify the complete offline suite passes.
- [ ] **Step 9: Commit explicit Task 5 paths with `feat: complete offline V0 commands`.**

### Task 6: Live Codex CLI and DeepSeek adapters with hard gates

**Files:**
- Create: `src/multicowork/adapters/codex_cli.py`
- Create: `src/multicowork/adapters/deepseek.py`
- Modify: `src/multicowork/cli.py`
- Modify: `src/multicowork/errors.py`
- Test: `tests/test_live_adapters.py`

**Interfaces:**
- Consumes: injected subprocess/HTTP transports for tests; Codex command/timeout/model; DeepSeek model/timeout/base URL; environment mapping; `--live-codex`; `--allow-paid-api`.
- Produces: `CodexCLIAdapter` and `DeepSeekAdapter` implementing `ModelAdapter`; classified timeout/rate-limit/network/server/configuration errors; at most two interface retries and one format-repair request at workflow boundary.

- [ ] **Step 1: Write failing adapter tests** for Codex read-only/non-interactive arguments, timeout and exit-code mapping, DeepSeek official endpoint payload parsing, redacted metadata, retry limits, and missing-key/missing-paid-flag rejection before injected transport invocation.
- [ ] **Step 2: Run `python -m unittest tests.test_live_adapters -v`** and verify it fails because live adapters do not exist.
- [ ] **Step 3: Implement `CodexCLIAdapter`** with `subprocess.run`, captured output, timeout, read-only sandbox arguments, and no shell.
- [ ] **Step 4: Implement `DeepSeekAdapter`** with `urllib.request`, authorization only in the request object, sanitized metadata, and classified HTTP/URL errors.
- [ ] **Step 5: Wire explicit live flags and bounded retries into the CLI/workflow boundary** while retaining mock defaults.
- [ ] **Step 6: Run `python -m unittest tests.test_live_adapters -v`** and verify all adapter tests pass without network access.
- [ ] **Step 7: Run `python -m unittest discover -s tests -v`** and verify the entire suite passes offline.
- [ ] **Step 8: Commit explicit Task 6 paths with `feat: add explicitly gated live adapters`.**

### Task 7: User documentation and final verification

**Files:**
- Modify: `README.md`
- Modify: `PROJECT.md` only if implementation exposes a documented boundary change.
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: the shipped CLI behavior and safety gates from Tasks 1-6.
- Produces: install/run examples for every command, mock-first quick start, local-record privacy warning, live-mode prerequisites, and accurate project status.

- [ ] **Step 1: Add a CLI help smoke assertion** ensuring all six subcommands remain discoverable.
- [ ] **Step 2: Update README** with editable install, mock examples, run layout/privacy, continuation/decision/replay, and explicit live-call warnings.
- [ ] **Step 3: Run `python -m unittest discover -s tests -v`** and verify all tests pass.
- [ ] **Step 4: Run `python -m multicowork --help` and one temporary-directory mock delegate/audit/show sequence** and verify no network access and inspectable run output.
- [ ] **Step 5: Run `git diff --check` and inspect `git status --short`** for caches, runs, secrets, or unrelated changes.
- [ ] **Step 6: Commit explicit documentation/test paths with `docs: document V0 CLI usage`.**
