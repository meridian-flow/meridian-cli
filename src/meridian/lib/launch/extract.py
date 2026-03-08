"""Post-execution extraction pipeline used during run finalization.

Also includes shared artifact read helpers (formerly ``extract/_io.py``).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from meridian.lib.domain import TokenUsage
from meridian.lib.launch.files_touched import extract_files_touched
from meridian.lib.launch.report import ExtractedReport, extract_or_fallback_report
from meridian.lib.harness.adapter import HarnessAdapter
from meridian.lib.safety.redaction import SecretSpec, redact_secrets
from meridian.lib.state.artifact_store import ArtifactStore
from meridian.lib.types import ArtifactKey, SpawnId


# ---------------------------------------------------------------------------
# Artifact I/O helpers (absorbed from extract/_io.py)
# ---------------------------------------------------------------------------


def read_artifact_text(artifacts: ArtifactStore, spawn_id: SpawnId, name: str) -> str:
    key = ArtifactKey(f"{spawn_id}/{name}")
    if not artifacts.exists(key):
        return ""
    return artifacts.get(key).decode("utf-8", errors="ignore")


# ---------------------------------------------------------------------------
# Finalization pipeline
# ---------------------------------------------------------------------------

_REPORT_FILENAME = "report.md"
_OUTPUT_FILENAME = "output.jsonl"
_STDERR_FILENAME = "stderr.log"
_TOKENS_FILENAME = "tokens.json"


class FinalizeExtraction(BaseModel):
    model_config = ConfigDict(frozen=True)

    usage: TokenUsage
    harness_session_id: str | None
    files_touched: tuple[str, ...]
    report_path: Path | None
    report: ExtractedReport
    output_is_empty: bool


def reset_finalize_attempt_artifacts(
    *,
    artifacts: ArtifactStore,
    spawn_id: SpawnId,
    log_dir: Path,
) -> None:
    """Clear attempt-scoped artifacts so retries never reuse stale extraction state."""

    for name in (_OUTPUT_FILENAME, _STDERR_FILENAME, _TOKENS_FILENAME, _REPORT_FILENAME):
        artifacts.delete(ArtifactKey(f"{spawn_id}/{name}"))

    report_path = log_dir / _REPORT_FILENAME
    if report_path.exists():
        report_path.unlink()


def _persist_report(
    *,
    artifacts: ArtifactStore,
    spawn_id: SpawnId,
    log_dir: Path,
    extracted: ExtractedReport,
    secrets: tuple[SecretSpec, ...],
) -> Path | None:
    if extracted.content is None:
        return None

    redacted_content = redact_secrets(extracted.content, secrets)
    target = log_dir / _REPORT_FILENAME
    report_key = ArtifactKey(f"{spawn_id}/{_REPORT_FILENAME}")
    if extracted.source == "assistant_message":
        wrapped = f"# Auto-extracted Report\n\n{redacted_content.strip()}\n"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(wrapped, encoding="utf-8")
        artifacts.put(report_key, wrapped.encode("utf-8"))
        return target

    # The harness may have written report.md directly. Ensure both filesystem and artifact
    # views are populated so downstream readers can consume a single source.
    text = redacted_content
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    artifacts.put(report_key, text.encode("utf-8"))
    return target


def _is_empty_output(
    *,
    artifacts: ArtifactStore,
    spawn_id: SpawnId,
    extracted_report: ExtractedReport,
) -> bool:
    if extracted_report.content and extracted_report.content.strip():
        return False
    output_text = read_artifact_text(artifacts, spawn_id, _OUTPUT_FILENAME)
    return not output_text.strip()


def enrich_finalize(
    *,
    artifacts: ArtifactStore,
    adapter: HarnessAdapter,
    spawn_id: SpawnId,
    log_dir: Path,
    secrets: tuple[SecretSpec, ...] = (),
) -> FinalizeExtraction:
    """Spawn all extraction steps and return one enriched finalization payload."""

    usage = adapter.extract_usage(artifacts, spawn_id)
    harness_session_id = adapter.extract_session_id(artifacts, spawn_id)
    files_touched = extract_files_touched(artifacts, spawn_id)
    report = extract_or_fallback_report(artifacts, spawn_id, adapter=adapter)
    report_path = _persist_report(
        artifacts=artifacts,
        spawn_id=spawn_id,
        log_dir=log_dir,
        extracted=report,
        secrets=secrets,
    )

    return FinalizeExtraction(
        usage=usage,
        harness_session_id=harness_session_id,
        files_touched=files_touched,
        report_path=report_path,
        report=report,
        output_is_empty=_is_empty_output(
            artifacts=artifacts,
            spawn_id=spawn_id,
            extracted_report=report,
        ),
    )
