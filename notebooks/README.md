# Notebook Trace Index

Use the `Python (sma-test-auto)` kernel or `.venv\Scripts\python.exe` in VS
Code.

| Notebook | Purpose | Internet | Browser | Target App | LLM Key |
| --- | --- | --- | --- | --- | --- |
| `00_environment_validation.ipynb` | Validates kernel and imports. | No | No | No | No |
| `01_orchestrator_agent_trace.ipynb` | Shows standalone Orchestrator. | No | No | No | No |
| `02_repository_analyzer_agent_trace.ipynb` | Shows repository analysis. | Optional | No | No | No |
| `03_orchestrator_repo_analyzer_integration_trace.ipynb` | Shows Orchestrator to Analyzer integration. | Optional | No | No | No |
| `04_rag_knowledge_agent_trace.ipynb` | Shows local RAG indexing and retrieval. | Optional | No | No | No |
| `05_orchestrator_repo_rag_integration_trace.ipynb` | Shows RAG integration. | Optional | No | No | No |
| `06_test_planner_agent_trace.ipynb` | Shows deterministic test planning. | No | No | No | No |
| `07_orchestrator_repo_rag_planner_integration_trace.ipynb` | Shows planner integration. | Optional | No | No | No |
| `08_api_testing_agent_trace.ipynb` | Shows API Testing Agent. | No | No | Optional | No |
| `09_api_integration_trace.ipynb` | Shows API integration. | Optional | No | Optional | No |
| `10_bug_analysis_agent_trace.ipynb` | Shows Bug Analysis Agent. | No | No | No | No |
| `11_bug_analysis_integration_trace.ipynb` | Shows Bug Analysis integration. | Optional | No | Optional | No |
| `12_report_agent_trace.ipynb` | Shows Report Agent. | No | No | No | No |
| `13_report_integration_trace.ipynb` | Shows Report integration. | Optional | No | Optional | No |
| `14_dashboard_interface_trace.ipynb` | Shows dashboard/interface milestone. | No | No | No | No |
| `15_mcp_testing_tools_server_trace.ipynb` | Shows MCP server milestone. | No | No | No | No |
| `16_mcp_agent_integration_trace.ipynb` | Shows optional MCP integration. | Optional | No | Optional | No |
| `17_ui_testing_agent_trace.ipynb` | Shows standalone UI Testing Agent with mocked Selenium by default. | No | Optional | Optional | No |
| `18_ui_integration_trace.ipynb` | Shows UI integration with mocked execution by default. | Optional | Optional | Optional | No |
| `19_performance_testing_agent_trace.ipynb` | Shows standalone Performance Agent with mocked Locust by default. | No | No | Optional | No |
| `20_performance_integration_trace.ipynb` | Shows Performance integration with mocked execution by default. | Optional | No | Optional | No |

Cells that require a real target app or browser are marked optional in the
notebook text. Do not put credentials or tokens in notebooks.
