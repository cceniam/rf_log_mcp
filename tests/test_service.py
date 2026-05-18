from __future__ import annotations

from rf_log_mcp.domain.models import MessageRecord, NodeRecord, NormalizedRun, RunMetadata
from rf_log_mcp.server.app import RfLogService
from rf_log_mcp.views import build_failure_path
from tests.helpers import fixture_path


def _parse(service: RfLogService, fixture_name: str) -> dict[str, object]:
    return service.parse_result(str(fixture_path(fixture_name)))


def test_parse_result_is_cached(service: RfLogService) -> None:
    first = _parse(service, "single_failure_611.xml")
    second = _parse(service, "single_failure_611.xml")
    assert first["ok"] is True
    assert second["ok"] is True
    assert isinstance(first["run_id"], int)
    assert first["run_id"] == second["run_id"]
    assert first["cached"] is False
    assert second["cached"] is True


def test_parse_result_accepts_robot_602_xml(service: RfLogService) -> None:
    parsed = _parse(service, "single_failure_602.xml")
    assert parsed["ok"] is True
    assert parsed["source_format"] == "xml"
    assert parsed["input_profile"] == "rf-output-xml"
    assert parsed["schemaversion"] == 3
    assert str(parsed["generator"]).startswith("Robot 6.0.2")


def test_parse_result_accepts_robot_74_xml(service: RfLogService) -> None:
    parsed = _parse(service, "single_failure_74.xml")
    assert parsed["ok"] is True
    assert parsed["source_format"] == "xml"
    assert parsed["input_profile"] == "rf-output-xml"
    assert parsed["schemaversion"] == 5
    assert str(parsed["generator"]).startswith("Robot 7.4.2")


def test_parse_result_is_cached_for_json(service: RfLogService) -> None:
    first = _parse(service, "single_failure_72.json")
    second = _parse(service, "single_failure_72.json")
    assert first["ok"] is True
    assert second["ok"] is True
    assert isinstance(first["run_id"], int)
    assert first["run_id"] == second["run_id"]
    assert first["source_format"] == "json"
    assert first["cached"] is False
    assert second["cached"] is True


def test_summary_view_contains_failures_and_errors(service: RfLogService) -> None:
    parsed = _parse(service, "errors_and_long_611.xml")
    summary = service.get_view(parsed["run_id"], view="summary")
    assert summary["ok"] is True
    assert summary["metadata"]["source_name"] == "errors_and_long_611.xml"
    assert len(summary["failed_tests"]) == 2
    assert len(summary["errors"]) == 1
    assert summary["message_truncated"] is True
    assert summary["budget_truncated"] is False


def test_summary_view_contains_failures_and_errors_for_json(service: RfLogService) -> None:
    parsed = _parse(service, "errors_and_long_72.json")
    summary = service.get_view(parsed["run_id"], view="summary")
    assert summary["ok"] is True
    assert summary["input_profile"] == "rf-7.2+-output-json"
    assert summary["metadata"]["source_format"] == "json"
    assert len(summary["failed_tests"]) == 2
    assert len(summary["errors"]) == 1


def test_summary_view_paginates_failed_tests(service: RfLogService) -> None:
    parsed = _parse(service, "errors_and_long_611.xml")
    first_page = service.get_view(parsed["run_id"], view="summary", page_size=1)
    assert first_page["ok"] is True
    assert len(first_page["failed_tests"]) == 1
    assert first_page["next_cursor"] is not None
    assert first_page["page_truncated"] is True

    second_page = service.get_view(
        parsed["run_id"],
        view="summary",
        cursor=first_page["next_cursor"],
        page_size=1,
    )
    assert second_page["ok"] is True
    assert len(second_page["failed_tests"]) == 1
    assert second_page["failed_tests"][0]["test_id"] != first_page["failed_tests"][0]["test_id"]
    assert second_page["next_cursor"] is None
    assert second_page["page_truncated"] is False


def test_failure_path_prefers_short_failed_branch(service: RfLogService) -> None:
    parsed = _parse(service, "nested_failure_611.xml")
    failure_path = service.get_view(parsed["run_id"], view="failure_path")
    assert failure_path["ok"] is True
    assert failure_path["failure_chain"][0]["kind"] == "TEST"
    assert any(item["name"] == "Inner Step" for item in failure_path["failure_chain"])


def test_failure_path_prefers_shorter_branch_over_first_failed_child() -> None:
    run = NormalizedRun(
        run_id=1,
        content_hash="hash",
        metadata=RunMetadata(
            source_path="synthetic.xml",
            source_name="synthetic.xml",
            source_format="xml",
            generator="Robot 7.4.2",
            generated=None,
            generation_time=None,
            rpa=None,
            schemaversion=5,
            input_profile="rf-output-xml",
        ),
        statistics={},
        nodes=[
            NodeRecord(
                id="t1",
                parent_id=None,
                owner_test_id="t1",
                kind="TEST",
                name="Synthetic",
                longname="Synthetic",
                status="FAIL",
                message=None,
                keyword_type=None,
                libname=None,
                start_time=None,
                end_time=None,
                elapsed_ms=None,
                sequence=1,
                ref_uri="rf://runs/1/nodes/t1",
            ),
            NodeRecord(
                id="deep-1",
                parent_id="t1",
                owner_test_id="t1",
                kind="KEYWORD",
                name="Deep First",
                longname=None,
                status="FAIL",
                message=None,
                keyword_type=None,
                libname=None,
                start_time=None,
                end_time=None,
                elapsed_ms=None,
                sequence=2,
                ref_uri="rf://runs/1/nodes/deep-1",
            ),
            NodeRecord(
                id="deep-2",
                parent_id="deep-1",
                owner_test_id="t1",
                kind="KEYWORD",
                name="Deep Leaf",
                longname=None,
                status="FAIL",
                message="deep failure",
                keyword_type=None,
                libname=None,
                start_time=None,
                end_time=None,
                elapsed_ms=None,
                sequence=3,
                ref_uri="rf://runs/1/nodes/deep-2",
            ),
            NodeRecord(
                id="short",
                parent_id="t1",
                owner_test_id="t1",
                kind="KEYWORD",
                name="Short Later",
                longname=None,
                status="FAIL",
                message="short failure",
                keyword_type=None,
                libname=None,
                start_time=None,
                end_time=None,
                elapsed_ms=None,
                sequence=4,
                ref_uri="rf://runs/1/nodes/short",
            ),
        ],
        messages=[
            MessageRecord(
                id="m1",
                parent_id="short",
                owner_test_id="t1",
                level="FAIL",
                message="short failure",
                timestamp=None,
                html=False,
                sequence=5,
                ref_uri="rf://runs/1/nodes/m1",
            )
        ],
        errors=[],
    )
    failure_path = build_failure_path(run, selector="t1")
    assert [item["node_id"] for item in failure_path.failure_chain] == ["t1", "short"]


def test_failure_path_prefers_higher_severity_when_branch_lengths_match() -> None:
    run = NormalizedRun(
        run_id=1,
        content_hash="hash",
        metadata=RunMetadata(
            source_path="synthetic.xml",
            source_name="synthetic.xml",
            source_format="xml",
            generator="Robot 7.4.2",
            generated=None,
            generation_time=None,
            rpa=None,
            schemaversion=5,
            input_profile="rf-output-xml",
        ),
        statistics={},
        nodes=[
            NodeRecord(
                id="t1",
                parent_id=None,
                owner_test_id="t1",
                kind="TEST",
                name="Synthetic",
                longname="Synthetic",
                status="FAIL",
                message=None,
                keyword_type=None,
                libname=None,
                start_time=None,
                end_time=None,
                elapsed_ms=None,
                sequence=1,
                ref_uri="rf://runs/1/nodes/t1",
            ),
            NodeRecord(
                id="warn-branch",
                parent_id="t1",
                owner_test_id="t1",
                kind="KEYWORD",
                name="Warn Branch",
                longname=None,
                status="FAIL",
                message=None,
                keyword_type=None,
                libname=None,
                start_time=None,
                end_time=None,
                elapsed_ms=None,
                sequence=2,
                ref_uri="rf://runs/1/nodes/warn-branch",
            ),
            NodeRecord(
                id="error-branch",
                parent_id="t1",
                owner_test_id="t1",
                kind="KEYWORD",
                name="Error Branch",
                longname=None,
                status="FAIL",
                message=None,
                keyword_type=None,
                libname=None,
                start_time=None,
                end_time=None,
                elapsed_ms=None,
                sequence=3,
                ref_uri="rf://runs/1/nodes/error-branch",
            ),
        ],
        messages=[
            MessageRecord(
                id="m1",
                parent_id="warn-branch",
                owner_test_id="t1",
                level="WARN",
                message="warning detail",
                timestamp=None,
                html=False,
                sequence=4,
                ref_uri="rf://runs/1/nodes/m1",
            ),
            MessageRecord(
                id="m2",
                parent_id="error-branch",
                owner_test_id="t1",
                level="ERROR",
                message="error detail",
                timestamp=None,
                html=False,
                sequence=5,
                ref_uri="rf://runs/1/nodes/m2",
            ),
        ],
        errors=[],
    )
    failure_path = build_failure_path(run, selector="t1")
    assert [item["node_id"] for item in failure_path.failure_chain] == ["t1", "error-branch"]


def test_failure_path_works_for_json(service: RfLogService) -> None:
    parsed = _parse(service, "single_failure_72.json")
    failure_path = service.get_view(parsed["run_id"], view="failure_path", selector="s1-t2")
    assert failure_path["ok"] is True
    assert failure_path["input_profile"] == "rf-7.2+-output-json"
    assert failure_path["failure_chain"][0]["kind"] == "TEST"
    assert any(item["name"] == "Fail" for item in failure_path["failure_chain"])


def test_step_window_paginates(service: RfLogService) -> None:
    parsed = _parse(service, "errors_and_long_611.xml")
    first_page = service.get_view(parsed["run_id"], view="step_window", selector="s1-t1")
    assert first_page["ok"] is True
    assert first_page["next_cursor"] is not None
    second_page = service.get_view(
        parsed["run_id"],
        view="step_window",
        selector="s1-t1",
        cursor=first_page["next_cursor"],
    )
    assert second_page["ok"] is True
    assert second_page["items"]


def test_step_window_accepts_node_selector_and_centers_window(service: RfLogService) -> None:
    parsed = _parse(service, "errors_and_long_611.xml")
    window = service.get_view(
        parsed["run_id"],
        view="step_window",
        selector="s1-t1-k13",
        page_size=5,
    )
    assert window["ok"] is True
    assert window["test_id"] == "s1-t1"
    assert window["selected_node_id"] == "s1-t1-k13"
    assert window["selected_node_name"] == "Create Long Failure"
    assert any(item.get("node_id") == "s1-t1-k13" for item in window["items"])


def test_step_window_paginates_for_json(service: RfLogService) -> None:
    parsed = _parse(service, "errors_and_long_72.json")
    first_page = service.get_view(parsed["run_id"], view="step_window", selector="s1-t1")
    assert first_page["ok"] is True
    assert first_page["input_profile"] == "rf-7.2+-output-json"
    assert first_page["next_cursor"] is not None


def test_search_messages_returns_next_cursor(service: RfLogService) -> None:
    parsed = _parse(service, "errors_and_long_611.xml")
    results = service.search_messages(parsed["run_id"], query="collected line", limit=1)
    assert results["ok"] is True
    assert len(results["results"]) == 1
    assert results["next_cursor"] is not None
    assert results["page_truncated"] is True


def test_search_messages_returns_next_cursor_for_json(service: RfLogService) -> None:
    parsed = _parse(service, "errors_and_long_72.json")
    results = service.search_messages(parsed["run_id"], query="collected line", limit=1)
    assert results["ok"] is True
    assert results["input_profile"] == "rf-7.2+-output-json"
    assert len(results["results"]) == 1
    assert results["next_cursor"] is not None


def test_search_messages_escapes_like_wildcards(service: RfLogService) -> None:
    parsed = _parse(service, "errors_and_long_611.xml")
    percent = service.search_messages(parsed["run_id"], query="%", limit=3)
    underscore = service.search_messages(parsed["run_id"], query="_", limit=10)
    backslash = service.search_messages(parsed["run_id"], query="\\", limit=3)

    assert percent["ok"] is True
    assert percent["results"] == []
    assert all("collected line" not in item["message"] for item in underscore["results"])
    assert backslash["results"]
    assert all("\\" in item["message"] for item in backslash["results"])


def test_search_messages_combines_escaped_query_with_level_filter(
    service: RfLogService,
) -> None:
    parsed = _parse(service, "errors_and_long_611.xml")
    error_results = service.search_messages(parsed["run_id"], query="\\", level="ERROR")
    info_results = service.search_messages(parsed["run_id"], query="\\", level="INFO")

    assert error_results["results"]
    assert all(item["level"] == "ERROR" for item in error_results["results"])
    assert info_results["results"] == []


def test_view_budget_flags_are_specific(service: RfLogService) -> None:
    parsed = _parse(service, "errors_and_long_611.xml")
    summary = service.get_view(parsed["run_id"], view="summary", budget=50)
    failure_path = service.get_view(parsed["run_id"], view="failure_path", budget=50)

    assert summary["truncated"] is True
    assert summary["budget_truncated"] is True
    assert summary["message_truncated"] is True
    assert failure_path["truncated"] is True
    assert failure_path["budget_truncated"] is True
    assert failure_path["message_truncated"] is True


def test_summary_budget_shrinks_errors_and_failures(service: RfLogService) -> None:
    parsed = _parse(service, "errors_and_long_611.xml")
    summary = service.get_view(parsed["run_id"], view="summary", budget=300)

    assert summary["budget_truncated"] is True
    assert summary["message_truncated"] is True
    assert summary["errors"]
    assert len(summary["errors"][0]["message"]) < 320
    assert summary["estimated_tokens"] < 364


def test_get_view_can_resolve_run_from_file_path(service: RfLogService) -> None:
    fixture = fixture_path("single_failure_611.xml")
    parsed = service.parse_result(str(fixture))
    summary = service.get_view(str(fixture), view="summary")
    assert summary["ok"] is True
    assert summary["run_id"] == parsed["run_id"]
