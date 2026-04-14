from __future__ import annotations

from rf_log_mcp.server.app import RfLogService
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


def test_summary_view_contains_failures_and_errors_for_json(service: RfLogService) -> None:
    parsed = _parse(service, "errors_and_long_72.json")
    summary = service.get_view(parsed["run_id"], view="summary")
    assert summary["ok"] is True
    assert summary["input_profile"] == "rf-7.2+-output-json"
    assert summary["metadata"]["source_format"] == "json"
    assert len(summary["failed_tests"]) == 2
    assert len(summary["errors"]) == 1


def test_failure_path_prefers_short_failed_branch(service: RfLogService) -> None:
    parsed = _parse(service, "nested_failure_611.xml")
    failure_path = service.get_view(parsed["run_id"], view="failure_path")
    assert failure_path["ok"] is True
    assert failure_path["failure_chain"][0]["kind"] == "TEST"
    assert any(item["name"] == "Inner Step" for item in failure_path["failure_chain"])


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


def test_search_messages_returns_next_cursor_for_json(service: RfLogService) -> None:
    parsed = _parse(service, "errors_and_long_72.json")
    results = service.search_messages(parsed["run_id"], query="collected line", limit=1)
    assert results["ok"] is True
    assert results["input_profile"] == "rf-7.2+-output-json"
    assert len(results["results"]) == 1
    assert results["next_cursor"] is not None


def test_get_view_can_resolve_run_from_file_path(service: RfLogService) -> None:
    fixture = fixture_path("single_failure_611.xml")
    parsed = service.parse_result(str(fixture))
    summary = service.get_view(str(fixture), view="summary")
    assert summary["ok"] is True
    assert summary["run_id"] == parsed["run_id"]
