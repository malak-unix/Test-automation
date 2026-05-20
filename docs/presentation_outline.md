# Presentation Outline

1. Title
   - LangGraph-Based Multi-Agent System for Automated Software Testing.

2. Problem Statement
   - Testing APIs, UI flows, and performance manually is slow and easy to miss.

3. Why Testing Is Hard
   - Repositories differ, documentation is incomplete, and target environments
     may be unavailable.

4. Proposed Solution
   - A progressive multi-agent workflow that analyzes, plans, executes, and
     reports testing results.

5. Final Architecture
   - Dashboard, LangGraph workflow, agents, local tools, optional MCP, and
     artifact persistence.

6. LangGraph Workflow
   - `START -> orchestrator -> repo_analyzer -> rag -> test_planner -> api_testing -> ui_testing -> performance_testing -> bug_analysis -> report -> END`

7. Agent Roles
   - Explain each agent in one sentence.

8. GitHub Repo Input
   - Public repos use Git clone without a token.
   - Private repos can later use `GITHUB_TOKEN`.

9. RAG Pipeline
   - File selection, chunking, local hash embeddings, JSON index, retrieved
     context.

10. MCP Integration
    - Standalone FastMCP server and optional safe use in selected agents.

11. API/UI/Performance Testing
    - API HTTP checks, Selenium UI checks, small safe Locust checks.

12. Bug Analysis
    - Deterministic anomaly classification and recommendations.

13. Dashboard
    - Cyber QA control center, KPIs, workflow topology, logs, artifacts, and
      report iframe.

14. Results Artifacts
    - `workflow_state.json`, `test_plan.json`, result JSON files, final report.

15. Limitations
    - Heuristic analysis, simple UI assertions, local performance loads,
      synchronous dashboard.

16. Future Work
    - CI/CD integration, GitHub PR creation, authentication, advanced selectors,
      production RAG, async jobs.

17. Conclusion
    - The MVP demonstrates an end-to-end, safe, explainable automated testing
      workflow.
