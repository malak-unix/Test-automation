"""Base helpers shared by current and future agents."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from test_auto.shared.schemas import AgentOutput, AgentSummary
from test_auto.shared.utils import current_timestamp, ensure_directory, write_json_file


def create_error_output(
    agent_name: str,
    error: Exception,
    metadata: dict[str, Any] | None = None,
) -> AgentOutput:
    """Create a standard error envelope for an agent exception."""

    return AgentOutput(
        agent=agent_name,
        timestamp=current_timestamp(),
        status="error",
        duration_seconds=0.0,
        summary=AgentSummary(),
        tests=[],
        anomalies=[
            {
                "type": "exception",
                "message": str(error),
                "exception_class": error.__class__.__name__,
            }
        ],
        metadata=metadata or {},
    )


def save_agent_output(
    output: AgentOutput,
    run_id: str,
    results_dir: str = "results",
) -> str:
    """Persist one agent output under results/runs/<run_id>/."""

    run_dir = ensure_directory(Path(results_dir) / "runs" / run_id)
    agent_name = output.agent.lower().replace(" ", "_")
    result_path = run_dir / f"{agent_name}_result.json"
    write_json_file(result_path, output.model_dump(mode="json"))
    return str(result_path)
