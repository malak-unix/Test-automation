"""Render final report data to static HTML."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from test_auto.reporting.artifact_loader import mask_sensitive_report_data


def get_template_environment(template_dir: str | Path | None = None) -> Environment:
    """Create a Jinja2 environment for report templates."""

    directory = Path(template_dir) if template_dir else Path("reports") / "templates"
    if not directory.exists() and template_dir is None:
        directory = Path(__file__).resolve().parents[3] / "reports" / "templates"
    return Environment(
        loader=FileSystemLoader(str(directory)),
        autoescape=select_autoescape(("html", "xml", "j2")),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_report_html(
    final_results: dict[str, Any],
    template_name: str = "report.html.j2",
) -> str:
    """Render final_results to an HTML string."""

    environment = get_template_environment()
    template = environment.get_template(template_name)
    return template.render(final_results=mask_sensitive_report_data(final_results))


def save_report_html(
    run_id: str,
    html: str,
    output_dir: str | Path = "reports/generated",
) -> str:
    """Save reports/generated/report_<run_id>.html and return its path."""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"report_{run_id}.html"
    path.write_text(html, encoding="utf-8")
    return str(path)


def render_and_save_report(final_results: dict[str, Any]) -> str:
    """Render final_results and save the resulting HTML report."""

    html = render_report_html(final_results)
    return save_report_html(str(final_results["run_id"]), html)
