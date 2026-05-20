# Final Demo Script

## 1. Project Objective

Present the system as a LangGraph-based multi-agent testing assistant. It takes
a GitHub repository URL or local path, analyzes the code, retrieves grounded
context, plans tests, executes API/UI/performance checks, classifies anomalies,
and generates a final report.

## 2. Demo Prerequisites

```powershell
cd sma_test_automation
.venv\Scripts\activate
pytest
python scripts/validate_notebook_env.py
python scripts/validate_github_input.py --repo-url "https://github.com/Vitaee/DjangoRestAPI"
python scripts/validate_llm_config.py
python scripts/final_smoke_test.py
python scripts/check_no_secrets.py
python mcp_servers/testing_tools_server.py --self-test
```

## 3. Dashboard Demo

Start the dashboard:

```powershell
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

Use:

- GitHub Repository URL: `https://github.com/Vitaee/DjangoRestAPI`
- Target URL: `http://localhost:8000`
- Test types: API, UI, Performance
- Planner mode: LLM planner
- External performance target: unchecked

## 4. CLI Demo

```powershell
python -m test_auto.main --repo-url "https://github.com/Vitaee/DjangoRestAPI" --target-url "http://localhost:8000" --test-types api ui performance --execution-mode sequential --focus "JWT authentication todo CRUD API tests"
```

## 5. GitHub Repo Input

Public GitHub repositories do not require a token. The system uses normal Git
clone and read-only file inspection. Private repositories may require
`GITHUB_TOKEN` in `.env`, but tokens must never be entered in the dashboard or
printed in logs.

## 6. LLM Validation

Groq/Mistral planner mode is the default. Validate non-secret configuration
only:

```powershell
python scripts/validate_llm_config.py
```

The LLM smoke test does nothing unless explicitly enabled, so run it only when
you want to verify one real provider call:

```powershell
python scripts/llm_planner_smoke_test.py
```

## 7. MCP Self-Test

```powershell
python mcp_servers/testing_tools_server.py --self-test
```

## 8. Expected Artifacts

```text
results/runs/<run_id>/workflow_state.json
results/runs/<run_id>/project_info.json
results/runs/<run_id>/retrieved_context.json
results/runs/<run_id>/test_plan.json
results/runs/<run_id>/api_result.json
results/runs/<run_id>/ui_result.json
results/runs/<run_id>/performance_result.json
results/runs/<run_id>/bug_result.json
results/runs/<run_id>/final_results.json
results/runs/<run_id>/report_result.json
reports/generated/report_<run_id>.html
```

## 9. If Target App Is Not Running

API, UI, and performance execution may record `environment_error`. This is
expected and safe: the workflow still produces artifacts and a final report.

## 10. Jury Explanation Of Each Agent

- Orchestrator validates the request and chooses agents.
- Repository Analyzer inspects code safely without executing it.
- RAG Knowledge Agent retrieves grounded repository context.
- Test Planner creates grounded test plans.
- API Testing Agent executes planned HTTP checks.
- UI Testing Agent executes planned Selenium checks.
- Performance Testing Agent runs small safe Locust checks.
- Bug Analysis Agent classifies API/UI/performance anomalies.
- Report Agent aggregates artifacts into final JSON and HTML.

## 11. Notebooks To Show

- `notebooks/00_environment_validation.ipynb`
- `notebooks/18_ui_integration_trace.ipynb`
- `notebooks/19_performance_testing_agent_trace.ipynb`
- `notebooks/20_performance_integration_trace.ipynb`

