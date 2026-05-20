# Final Project Checklist

## Environment

- [ ] Project virtual environment exists at `.venv/`.
- [ ] Dependencies are installed with `pip install -r requirements.txt`.
- [ ] Package is installed with `pip install -e .`.
- [ ] `pytest` passes.

## Notebook Kernel

- [ ] `python scripts/setup_notebook_kernel.py` was run.
- [ ] VS Code notebook kernel is `Python (sma-test-auto)`.
- [ ] `python scripts/validate_notebook_env.py` passes.

## GitHub Repo Validation

- [ ] Public demo URL is valid.
- [ ] `python scripts/validate_github_input.py --repo-url "https://github.com/Vitaee/DjangoRestAPI"` runs safely.
- [ ] No GitHub token is entered in the dashboard.

## LLM Config

- [ ] `python scripts/validate_llm_config.py` runs safely.
- [ ] No Groq or Mistral key is printed.
- [ ] LLM smoke test passes when `--use-llm` is intentionally passed.

## MCP

- [ ] `python mcp_servers/testing_tools_server.py --self-test` passes.

## Dashboard

- [ ] Dashboard starts with `python app.py`.
- [ ] Dashboard opens at `http://127.0.0.1:5000`.
- [ ] GitHub Repository URL field is clear.
- [ ] API, UI, and Performance test type controls are visible.
- [ ] Generated HTML report is visible inside the dashboard.

## Full Workflow

- [ ] Full workflow runs with API, UI, and Performance selected.
- [ ] `workflow_state.json` is created.
- [ ] `project_info.json` is created.
- [ ] `retrieved_context.json` is created.
- [ ] `test_plan.json` is created.
- [ ] `api_result.json` is created.
- [ ] `ui_result.json` is created when UI inputs exist.
- [ ] `performance_result.json` is created when Performance is selected.
- [ ] `bug_result.json` is created.
- [ ] `final_results.json` is created.
- [ ] HTML report is generated.

## Security

- [ ] `.env` is not committed.
- [ ] `python scripts/check_no_secrets.py` passes.
- [ ] No credentials, cookies, tokens, passwords, or Authorization headers are shown.

## Presentation Ready

- [ ] `docs/demo_script.md` is ready.
- [ ] `docs/final_architecture.md` is ready.
- [ ] `docs/presentation_outline.md` is ready.
- [ ] `notebooks/README.md` lists trace notebooks.
