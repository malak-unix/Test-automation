"""Shared JSON schemas used as the communication contract between agents."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


AGENT_OUTPUT_STATUSES = {"success", "partial", "error"}
TEST_RESULT_STATUSES = {"passed", "failed", "skipped", "error"}
EXECUTION_MODES = {"sequential", "parallel"}
CHUNK_TYPES = {"doc", "api", "test", "ui", "config", "generic"}
ASSERTION_TYPES = {
    "status_code",
    "response_contains",
    "response_schema",
    "ui_visible",
    "performance_threshold",
    "security_expectation",
    "custom",
}
API_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "UNKNOWN"}
API_EXECUTION_STATUSES = {
    "passed",
    "failed",
    "skipped",
    "error",
    "environment_error",
    "test_data_error",
    "assertion_error",
}
UI_EXECUTION_STATUSES = {
    "passed",
    "failed",
    "skipped",
    "error",
    "environment_error",
    "selector_error",
    "timeout_error",
    "test_data_error",
    "assertion_error",
}
PERFORMANCE_METHODS = {"GET", "HEAD"}
PERFORMANCE_EXECUTION_STATUSES = {
    "passed",
    "failed",
    "skipped",
    "error",
    "environment_error",
    "performance_threshold_failed",
    "configuration_error",
}
BUG_SEVERITIES = {"high", "medium", "low", "info"}
BUG_CLASSIFICATIONS = {
    "application_bug",
    "security_risk",
    "environment_error",
    "test_data_error",
    "assertion_error",
    "test_script_error",
    "performance_anomaly",
    "skipped_or_not_executable",
    "unknown",
}
REPORT_SECTION_STATUSES = {"success", "partial", "error", "missing", "skipped"}
TEST_PRIORITIES = {"high", "medium", "low"}
TEST_CATEGORIES = {
    "functional",
    "security",
    "regression",
    "smoke",
    "negative",
    "boundary",
}
ALLOWED_AGENT_NAMES = {
    "repository_analyzer",
    "rag",
    "test_planner",
    "api",
    "ui",
    "performance",
    "bug",
    "report",
}


class AgentSummary(BaseModel):
    """Compact summary shared by every agent result."""

    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    pass_rate: float = 0.0


class AgentTestResult(BaseModel):
    """One structured test or validation result emitted by an agent."""

    name: str
    status: str
    duration_ms: float | None = None
    details: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        """Ensure test result status is part of the shared contract."""

        if value not in TEST_RESULT_STATUSES:
            allowed = ", ".join(sorted(TEST_RESULT_STATUSES))
            raise ValueError(f"status must be one of: {allowed}")
        return value


class AgentOutput(BaseModel):
    """Standard JSON output envelope used by all agents."""

    agent: str
    timestamp: str
    status: str
    duration_seconds: float
    summary: AgentSummary
    tests: list[AgentTestResult] = Field(default_factory=list)
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        """Ensure agent status is part of the shared contract."""

        if value not in AGENT_OUTPUT_STATUSES:
            allowed = ", ".join(sorted(AGENT_OUTPUT_STATUSES))
            raise ValueError(f"status must be one of: {allowed}")
        return value


class OrchestratorDecision(BaseModel):
    """Rule-based routing decision produced by the Orchestrator Agent."""

    run_id: str
    selected_agents: list[str]
    execution_mode: str
    reasoning_summary: str
    risks: list[str] = Field(default_factory=list)
    next_node: str

    @field_validator("selected_agents")
    @classmethod
    def validate_selected_agents(cls, value: list[str]) -> list[str]:
        """Reject unknown agent names before they enter the workflow."""

        invalid = [agent for agent in value if agent not in ALLOWED_AGENT_NAMES]
        if invalid:
            allowed = ", ".join(sorted(ALLOWED_AGENT_NAMES))
            raise ValueError(
                f"selected_agents contains invalid values {invalid}; allowed: {allowed}"
            )
        return value

    @field_validator("execution_mode")
    @classmethod
    def validate_execution_mode(cls, value: str) -> str:
        """Ensure execution mode is deterministic and supported."""

        if value not in EXECUTION_MODES:
            allowed = ", ".join(sorted(EXECUTION_MODES))
            raise ValueError(f"execution_mode must be one of: {allowed}")
        return value


class RepositoryEndpoint(BaseModel):
    """One endpoint discovered through deterministic repository heuristics."""

    name: str | None = None
    method: str | None = None
    path: str
    source_file: str
    line_number: int | None = None
    confidence: float = 0.5

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        """Keep heuristic confidence scores bounded."""

        if not 0 <= value <= 1:
            raise ValueError("confidence must be between 0 and 1")
        return value


class RepositoryUIFlow(BaseModel):
    """One UI flow discovered from repository file names and paths."""

    name: str
    source_file: str
    flow_type: str
    confidence: float = 0.5

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        """Keep heuristic confidence scores bounded."""

        if not 0 <= value <= 1:
            raise ValueError("confidence must be between 0 and 1")
        return value


class ProjectInfo(BaseModel):
    """Compact repository metadata shared with later agents."""

    language: str
    framework: str
    test_framework: str | None = None
    has_api: bool = False
    has_ui: bool = False
    auth_type: str | None = None
    package_manager: str | None = None
    source_dirs: list[str] = Field(default_factory=list)
    test_dirs: list[str] = Field(default_factory=list)
    candidate_docs: list[str] = Field(default_factory=list)
    candidate_api_files: list[str] = Field(default_factory=list)
    candidate_ui_files: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class RepositoryAnalyzerOutput(BaseModel):
    """Structured JSON report emitted by the Repository Analyzer Agent."""

    agent: str = "repo_analyzer"
    timestamp: str
    status: str
    duration_seconds: float
    project_info: ProjectInfo
    discovered_endpoints: list[RepositoryEndpoint] = Field(default_factory=list)
    discovered_ui_flows: list[RepositoryUIFlow] = Field(default_factory=list)
    indexed_documents: list[dict[str, Any]] = Field(default_factory=list)
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        """Ensure analyzer status matches the shared agent contract."""

        if value not in AGENT_OUTPUT_STATUSES:
            allowed = ", ".join(sorted(AGENT_OUTPUT_STATUSES))
            raise ValueError(f"status must be one of: {allowed}")
        return value


class DocumentChunk(BaseModel):
    """A small source-backed text chunk for local RAG indexing."""

    chunk_id: str
    source_path: str
    chunk_type: str
    content: str
    start_line: int | None = None
    end_line: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        """Reject empty chunks before indexing."""

        if not value.strip():
            raise ValueError("content must not be empty")
        return value

    @field_validator("chunk_type")
    @classmethod
    def validate_chunk_type(cls, value: str) -> str:
        """Keep chunk types aligned with the shared contract."""

        if value not in CHUNK_TYPES:
            allowed = ", ".join(sorted(CHUNK_TYPES))
            raise ValueError(f"chunk_type must be one of: {allowed}")
        return value


class RetrievedContext(BaseModel):
    """One retrieved chunk with relevance score and reason."""

    chunk_id: str
    source_path: str
    content: str
    score: float
    reason: str
    chunk_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("score")
    @classmethod
    def validate_score(cls, value: float) -> float:
        """Keep similarity scores in the normalized range."""

        if not 0 <= value <= 1:
            raise ValueError("score must be between 0 and 1")
        return value


class RAGIndexManifest(BaseModel):
    """Manifest describing a local deterministic vector index."""

    run_id: str
    repo_path: str
    index_path: str
    total_files: int
    total_chunks: int
    embedding_backend: str
    created_at: str
    indexed_sources: list[str] = Field(default_factory=list)


class RAGAgentOutput(BaseModel):
    """Structured JSON report emitted by the RAG Knowledge Agent."""

    agent: str = "rag"
    timestamp: str
    status: str
    duration_seconds: float
    query: str
    index_path: str | None = None
    chunk_count: int = 0
    retrieved_context: list[RetrievedContext] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        """Ensure RAG status matches the shared agent contract."""

        if value not in AGENT_OUTPUT_STATUSES:
            allowed = ", ".join(sorted(AGENT_OUTPUT_STATUSES))
            raise ValueError(f"status must be one of: {allowed}")
        return value


class TestPlanAssertion(BaseModel):
    """One expected condition in a future executable test."""

    type: str
    expected: str
    target: str | None = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        """Keep assertion types inside the planning contract."""

        if value not in ASSERTION_TYPES:
            allowed = ", ".join(sorted(ASSERTION_TYPES))
            raise ValueError(f"type must be one of: {allowed}")
        return value


class APITestCasePlan(BaseModel):
    """Structured plan for one future API test case."""

    id: str
    name: str
    method: str
    endpoint: str
    objective: str
    priority: str = "medium"
    category: str = "functional"
    auth_required: bool = False
    request_body: dict[str, Any] | None = None
    expected_status: int | None = None
    assertions: list[TestPlanAssertion] = Field(default_factory=list)
    evidence_sources: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)

    @field_validator("method")
    @classmethod
    def validate_method(cls, value: str) -> str:
        """Normalize and validate HTTP methods."""

        normalized = value.upper()
        if normalized not in API_METHODS:
            allowed = ", ".join(sorted(API_METHODS))
            raise ValueError(f"method must be one of: {allowed}")
        return normalized

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value: str) -> str:
        """Validate planning priority."""

        if value not in TEST_PRIORITIES:
            allowed = ", ".join(sorted(TEST_PRIORITIES))
            raise ValueError(f"priority must be one of: {allowed}")
        return value

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        """Validate planning category."""

        if value not in TEST_CATEGORIES:
            allowed = ", ".join(sorted(TEST_CATEGORIES))
            raise ValueError(f"category must be one of: {allowed}")
        return value


class UITestCasePlan(BaseModel):
    """Structured plan for one future UI test case."""

    id: str
    name: str
    flow: str
    objective: str
    priority: str = "medium"
    steps: list[str]
    expected_result: str
    evidence_sources: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value: str) -> str:
        """Validate planning priority."""

        if value not in TEST_PRIORITIES:
            allowed = ", ".join(sorted(TEST_PRIORITIES))
            raise ValueError(f"priority must be one of: {allowed}")
        return value


class PerformanceTestCasePlan(BaseModel):
    """Structured plan for one future performance test case."""

    id: str
    name: str
    endpoint: str
    objective: str
    users: int = 5
    duration_seconds: int = 30
    max_avg_response_ms: int = 2000
    evidence_sources: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class TestPlan(BaseModel):
    """Grounded test plan produced before any executable tests exist."""

    scope: str
    assumptions: list[str] = Field(default_factory=list)
    api_tests: list[APITestCasePlan] = Field(default_factory=list)
    ui_tests: list[UITestCasePlan] = Field(default_factory=list)
    performance_tests: list[PerformanceTestCasePlan] = Field(default_factory=list)
    excluded_tests: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    reasoning_summary: str

    @field_validator("reasoning_summary")
    @classmethod
    def validate_reasoning_summary(cls, value: str) -> str:
        """Require a concise explanation without chain-of-thought."""

        if not value.strip():
            raise ValueError("reasoning_summary must not be empty")
        return value

    @model_validator(mode="after")
    def validate_has_tests_or_missing_information(self) -> "TestPlan":
        """Require either planned tests or an explicit evidence gap."""

        has_tests = bool(self.api_tests or self.ui_tests or self.performance_tests)
        if not has_tests and not self.missing_information:
            raise ValueError(
                "At least one test is required unless missing_information explains the gap."
            )
        return self


class TestPlannerOutput(BaseModel):
    """Structured JSON report emitted by the Test Planner Agent."""

    agent: str = "test_planner"
    timestamp: str
    status: str
    duration_seconds: float
    test_plan: TestPlan
    model_info: dict[str, Any]
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        """Ensure planner status matches the shared agent contract."""

        if value not in AGENT_OUTPUT_STATUSES:
            allowed = ", ".join(sorted(AGENT_OUTPUT_STATUSES))
            raise ValueError(f"status must be one of: {allowed}")
        return value


class APIRequestEvidence(BaseModel):
    """Compact request/response evidence saved by the API Testing Agent."""

    url: str
    method: str
    request_body: dict[str, Any] | None = None
    response_preview: str | None = None
    response_json_preview: dict[str, Any] | list[Any] | None = None

    @field_validator("method")
    @classmethod
    def validate_method(cls, value: str) -> str:
        """Normalize and validate HTTP methods in saved evidence."""

        normalized = value.upper()
        if normalized not in API_METHODS:
            allowed = ", ".join(sorted(API_METHODS))
            raise ValueError(f"method must be one of: {allowed}")
        return normalized


class APITestExecutionResult(BaseModel):
    """One executed API test case result."""

    id: str
    name: str
    method: str
    endpoint: str
    status: str
    expected_status: int | None = None
    actual_status: int | None = None
    duration_ms: float | None = None
    details: str | None = None
    evidence: APIRequestEvidence | dict[str, Any] = Field(default_factory=dict)
    assertions: list[dict[str, Any]] = Field(default_factory=list)
    error_type: str | None = None

    @field_validator("method")
    @classmethod
    def validate_method(cls, value: str) -> str:
        """Normalize and validate planned API methods."""

        normalized = value.upper()
        if normalized not in API_METHODS:
            allowed = ", ".join(sorted(API_METHODS))
            raise ValueError(f"method must be one of: {allowed}")
        return normalized

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        """Keep API execution status inside the shared contract."""

        if value not in API_EXECUTION_STATUSES:
            allowed = ", ".join(sorted(API_EXECUTION_STATUSES))
            raise ValueError(f"status must be one of: {allowed}")
        return value


class APITestSummary(BaseModel):
    """Compact aggregate summary for API test execution."""

    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    pass_rate: float = 0.0


class APITestingOutput(BaseModel):
    """Structured JSON report emitted by the API Testing Agent."""

    agent: str = "api_testing"
    timestamp: str
    status: str
    duration_seconds: float
    summary: APITestSummary
    tests: list[APITestExecutionResult] = Field(default_factory=list)
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        """Ensure API agent status matches the shared agent contract."""

        if value not in AGENT_OUTPUT_STATUSES:
            allowed = ", ".join(sorted(AGENT_OUTPUT_STATUSES))
            raise ValueError(f"status must be one of: {allowed}")
        return value


class UIScreenshotEvidence(BaseModel):
    """Screenshot metadata saved by the UI Testing Agent."""

    path: str
    reason: str
    created: bool = False


class UITestExecutionResult(BaseModel):
    """One executed UI test case result."""

    id: str
    name: str
    flow: str | None = None
    status: str
    target_path: str | None = None
    target_url: str | None = None
    duration_ms: float | None = None
    details: str | None = None
    screenshot: UIScreenshotEvidence | dict[str, Any] | None = None
    assertions: list[dict[str, Any]] = Field(default_factory=list)
    error_type: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        """Keep UI execution status inside the shared contract."""

        if value not in UI_EXECUTION_STATUSES:
            allowed = ", ".join(sorted(UI_EXECUTION_STATUSES))
            raise ValueError(f"status must be one of: {allowed}")
        return value


class UISummary(BaseModel):
    """Compact aggregate summary for UI test execution."""

    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    pass_rate: float = 0.0


class UITestingOutput(BaseModel):
    """Structured JSON report emitted by the UI Testing Agent."""

    agent: str = "ui_testing"
    timestamp: str
    status: str
    duration_seconds: float
    summary: UISummary
    tests: list[UITestExecutionResult] = Field(default_factory=list)
    screenshots: list[dict[str, Any]] = Field(default_factory=list)
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        """Ensure UI agent status matches the shared agent contract."""

        if value not in AGENT_OUTPUT_STATUSES:
            allowed = ", ".join(sorted(AGENT_OUTPUT_STATUSES))
            raise ValueError(f"status must be one of: {allowed}")
        return value


class PerformanceMetric(BaseModel):
    """One compact performance metric value."""

    name: str
    value: float | int | str | None = None
    unit: str | None = None


class PerformanceTestExecutionResult(BaseModel):
    """One executed performance test case result."""

    id: str
    name: str
    endpoint: str
    method: str = "GET"
    status: str
    users: int
    spawn_rate: float
    duration_seconds: int
    total_requests: int = 0
    failures: int = 0
    failure_rate: float = 0.0
    average_response_time_ms: float | None = None
    min_response_time_ms: float | None = None
    max_response_time_ms: float | None = None
    p50_response_time_ms: float | None = None
    p95_response_time_ms: float | None = None
    requests_per_second: float | None = None
    threshold_results: list[dict[str, Any]] = Field(default_factory=list)
    details: str | None = None
    error_type: str | None = None
    artifact_paths: list[str] = Field(default_factory=list)

    @field_validator("method")
    @classmethod
    def validate_method(cls, value: str) -> str:
        """Keep performance tests limited to safe read-only HTTP methods."""

        normalized = value.upper()
        if normalized not in PERFORMANCE_METHODS:
            allowed = ", ".join(sorted(PERFORMANCE_METHODS))
            raise ValueError(f"method must be one of: {allowed}")
        return normalized

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        """Keep performance execution status inside the shared contract."""

        if value not in PERFORMANCE_EXECUTION_STATUSES:
            allowed = ", ".join(sorted(PERFORMANCE_EXECUTION_STATUSES))
            raise ValueError(f"status must be one of: {allowed}")
        return value


class PerformanceSummary(BaseModel):
    """Compact aggregate summary for performance test execution."""

    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    average_response_time_ms: float | None = None
    p95_response_time_ms: float | None = None
    overall_failure_rate: float = 0.0


class PerformanceTestingOutput(BaseModel):
    """Structured JSON report emitted by the Performance Testing Agent."""

    agent: str = "performance_testing"
    timestamp: str
    status: str
    duration_seconds: float
    summary: PerformanceSummary
    tests: list[PerformanceTestExecutionResult] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        """Ensure Performance agent status matches the shared agent contract."""

        if value not in AGENT_OUTPUT_STATUSES:
            allowed = ", ".join(sorted(AGENT_OUTPUT_STATUSES))
            raise ValueError(f"status must be one of: {allowed}")
        return value


class BugEvidence(BaseModel):
    """Compact evidence used to classify one anomaly."""

    source_agent: str
    test_id: str | None = None
    test_name: str | None = None
    method: str | None = None
    endpoint: str | None = None
    flow: str | None = None
    target_path: str | None = None
    target_url: str | None = None
    expected_status: int | None = None
    actual_status: int | None = None
    status: str | None = None
    details: str | None = None
    duration_ms: float | None = None
    screenshot_path: str | None = None
    evidence_path: str | None = None
    users: int | None = None
    duration_seconds: int | None = None
    total_requests: int | None = None
    failures: int | None = None
    failure_rate: float | None = None
    average_response_time_ms: float | None = None
    p95_response_time_ms: float | None = None


class BugAnomaly(BaseModel):
    """One classified bug, risk, or execution anomaly."""

    id: str
    type: str
    severity: str
    source_agent: str
    classification: str
    title: str
    evidence: BugEvidence | dict[str, Any]
    recommendation: str
    confidence: float = 0.7

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, value: str) -> str:
        """Keep bug severity inside the shared contract."""

        if value not in BUG_SEVERITIES:
            allowed = ", ".join(sorted(BUG_SEVERITIES))
            raise ValueError(f"severity must be one of: {allowed}")
        return value

    @field_validator("classification")
    @classmethod
    def validate_classification(cls, value: str) -> str:
        """Keep bug classification inside the shared contract."""

        if value not in BUG_CLASSIFICATIONS:
            allowed = ", ".join(sorted(BUG_CLASSIFICATIONS))
            raise ValueError(f"classification must be one of: {allowed}")
        return value

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        """Keep deterministic confidence scores bounded."""

        if not 0 <= value <= 1:
            raise ValueError("confidence must be between 0 and 1")
        return value


class BugSummary(BaseModel):
    """Compact aggregate summary for bug analysis."""

    total_anomalies: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0
    by_classification: dict[str, int] = Field(default_factory=dict)


class BugAnalysisOutput(BaseModel):
    """Structured JSON report emitted by the Bug Analysis Agent."""

    agent: str = "bug_analysis"
    timestamp: str
    status: str
    duration_seconds: float
    summary: BugSummary
    anomalies: list[BugAnomaly] = Field(default_factory=list)
    recommendations: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        """Ensure bug analysis status matches the shared agent contract."""

        if value not in AGENT_OUTPUT_STATUSES:
            allowed = ", ".join(sorted(AGENT_OUTPUT_STATUSES))
            raise ValueError(f"status must be one of: {allowed}")
        return value


class ReportKPIs(BaseModel):
    """Global metrics shown in the final report."""

    total_api_tests: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    pass_rate: float = 0.0
    total_ui_tests: int = 0
    ui_passed: int = 0
    ui_failed: int = 0
    ui_skipped: int = 0
    ui_errors: int = 0
    ui_pass_rate: float = 0.0
    screenshot_count: int = 0
    total_performance_tests: int = 0
    performance_passed: int = 0
    performance_failed: int = 0
    performance_skipped: int = 0
    performance_errors: int = 0
    average_response_time_ms: float | None = None
    p95_response_time_ms: float | None = None
    overall_failure_rate: float = 0.0
    total_anomalies: int = 0
    high_anomalies: int = 0
    medium_anomalies: int = 0
    low_anomalies: int = 0
    info_anomalies: int = 0
    recommendation_count: int = 0
    global_score: float = 0.0


class ReportArtifactPaths(BaseModel):
    """Known artifact paths used to build and save the report."""

    workflow_state_path: str | None = None
    project_info_path: str | None = None
    test_plan_path: str | None = None
    api_result_path: str | None = None
    ui_result_path: str | None = None
    performance_result_path: str | None = None
    bug_result_path: str | None = None
    final_results_path: str | None = None
    report_result_path: str | None = None
    report_html_path: str | None = None


class ReportSection(BaseModel):
    """One readable section in final_results and the HTML report."""

    title: str
    status: str
    summary: dict[str, Any] = Field(default_factory=dict)
    items: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        """Keep report section status inside the shared contract."""

        if value not in REPORT_SECTION_STATUSES:
            allowed = ", ".join(sorted(REPORT_SECTION_STATUSES))
            raise ValueError(f"status must be one of: {allowed}")
        return value


class FinalResults(BaseModel):
    """Aggregated final report data before HTML rendering."""

    run_id: str
    generated_at: str
    project_info: dict[str, Any] = Field(default_factory=dict)
    target_url: str | None = None
    user_preferences: dict[str, Any] = Field(default_factory=dict)
    kpis: ReportKPIs
    test_plan_summary: dict[str, Any] = Field(default_factory=dict)
    api_summary: dict[str, Any] = Field(default_factory=dict)
    ui_summary: dict[str, Any] = Field(default_factory=dict)
    performance_summary: dict[str, Any] = Field(default_factory=dict)
    performance_artifacts: list[dict[str, Any]] = Field(default_factory=list)
    bug_summary: dict[str, Any] = Field(default_factory=dict)
    screenshots: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[dict[str, Any]] = Field(default_factory=list)
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    sections: list[ReportSection] = Field(default_factory=list)
    artifact_paths: ReportArtifactPaths
    limitations: list[str] = Field(default_factory=list)


class ReportAgentOutput(BaseModel):
    """Structured JSON report emitted by the Report Agent."""

    agent: str = "report"
    timestamp: str
    status: str
    duration_seconds: float
    final_results: FinalResults
    report_html_path: str | None = None
    dashboard_payload: dict[str, Any] = Field(default_factory=dict)
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        """Ensure Report Agent status matches the shared agent contract."""

        if value not in AGENT_OUTPUT_STATUSES:
            allowed = ", ".join(sorted(AGENT_OUTPUT_STATUSES))
            raise ValueError(f"status must be one of: {allowed}")
        return value
