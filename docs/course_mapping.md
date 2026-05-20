# Course Mapping

This project follows the professor course patterns without copying course text or
building the full MVP in one step.

- LangGraph course: the workflow is organized with State, Nodes, and Edges.
  Milestone 1 uses a minimal `START -> orchestrator -> END` graph.
- Prompt Engineering course: future LLM agents will use clear system prompts,
  user input, and structured JSON output.
- Agent course: each future agent will be designed around Mind, Tools, Memory,
  and Loop, then tested alone before integration.
- MCP course: MCP will be added later as the standardized tool layer for
  external actions such as repository access, browser work, and test execution.
- PFA plan: every agent must work alone first, produce JSON, handle errors, and
  only then be connected into the shared LangGraph workflow.
