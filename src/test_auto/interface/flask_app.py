"""Flask app factory for the dashboard MVP."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request

from test_auto.interface import run_service
from test_auto.interface.dashboard_helpers import (
    list_recent_runs,
    load_run_summary,
)
from test_auto.planning.llm_planner import get_planner_llm_config


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def create_app(testing: bool = False) -> Flask:
    """Create the dashboard Flask application."""

    root = _project_root()
    app = Flask(
        __name__,
        template_folder=str(root / "templates"),
        static_folder=str(root / "static"),
    )
    app.config["TESTING"] = testing

    @app.get("/")
    def index():
        llm_config = get_planner_llm_config()
        return render_template(
            "index.html",
            recent_runs=list_recent_runs(limit=5),
            llm_config=llm_config,
            defaults={
                "repo_url": run_service.DEFAULT_REPO_URL,
                "target_url": run_service.DEFAULT_TARGET_URL,
                "focus": run_service.DEFAULT_FOCUS,
                "rag_top_k": 8,
            },
        )

    @app.post("/run")
    def run():
        result = run_service.run_and_summarize(request.form)
        if result.get("status") == "error":
            return (
                render_template(
                    "error.html",
                    error=result.get("error", "Workflow failed."),
                    errors=result.get("errors", []),
                ),
                500,
            )
        return render_template(
            "run_result.html",
            summary=result.get("summary", {}),
            report_html=result.get("report_html", ""),
        )

    @app.get("/runs")
    def runs():
        return render_template("recent_runs.html", recent_runs=list_recent_runs(limit=20))

    @app.get("/runs/<run_id>")
    def view_run(run_id: str):
        summary = load_run_summary(run_id)
        if not summary:
            abort(404)
        report_html = run_service.load_report_html_for_display(summary.get("report_html_path"))
        return render_template(
            "run_result.html",
            summary=summary,
            report_html=report_html,
        )

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    return app
