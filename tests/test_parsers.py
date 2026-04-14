from __future__ import annotations

import warnings

import pytest

from rf_log_mcp.errors import (
    InvalidFileTypeError,
    InvalidJsonError,
    InvalidXmlError,
    UnsupportedInputVersionError,
)
from rf_log_mcp.parsers.gating import probe_json_input, probe_xml_input
from rf_log_mcp.parsers.json_adapter import parse_output_json
from rf_log_mcp.parsers.xml_adapter import parse_output_xml
from tests.helpers import fixture_path


def test_probe_accepts_robot_611_xml() -> None:
    probed = probe_xml_input(fixture_path("output-20260413-151651.xml"))
    assert probed.schemaversion == 4
    assert probed.generator.startswith("Robot 6.1.1")


def test_probe_accepts_robot_602_xml() -> None:
    probed = probe_xml_input(fixture_path("single_failure_602.xml"))
    assert probed.schemaversion == 3
    assert probed.generator.startswith("Robot 6.0.2")


def test_probe_accepts_robot_74_xml() -> None:
    probed = probe_xml_input(fixture_path("single_failure_74.xml"))
    assert probed.schemaversion == 5
    assert probed.generator.startswith("Robot 7.4.2")


def test_probe_rejects_non_xml_file() -> None:
    with pytest.raises(InvalidFileTypeError):
        probe_xml_input(fixture_path("invalid.txt"))


def test_probe_rejects_broken_xml() -> None:
    with pytest.raises(InvalidXmlError):
        probe_xml_input(fixture_path("broken.xml"))


def test_probe_accepts_robot_72_json() -> None:
    probed = probe_json_input(fixture_path("single_failure_72.json"))
    assert probed.source_format == "json"
    assert probed.schemaversion is None
    assert probed.generator.startswith("Rebot 7.4.2")


def test_probe_rejects_broken_json() -> None:
    with pytest.raises(InvalidJsonError):
        probe_json_input(fixture_path("broken.json"))


def test_probe_rejects_pre_72_json() -> None:
    with pytest.raises(UnsupportedInputVersionError):
        probe_json_input(fixture_path("single_failure_71.json"))


def test_parse_output_xml_collects_failures_and_errors() -> None:
    run = parse_output_xml(probe_xml_input(fixture_path("errors_and_long_611.xml")))
    assert run.metadata.input_profile == "rf-output-xml"
    assert len(run.failed_tests) == 2
    assert run.errors
    assert any(message.owner_test_id for message in run.messages)


def test_parse_output_xml_supports_robot_602_schema3() -> None:
    run = parse_output_xml(probe_xml_input(fixture_path("single_failure_602.xml")))
    assert run.metadata.input_profile == "rf-output-xml"
    assert run.metadata.schemaversion == 3
    assert run.metadata.generator.startswith("Robot 6.0.2")
    assert len(run.failed_tests) == 1


def test_parse_output_xml_supports_robot_74_schema5() -> None:
    run = parse_output_xml(probe_xml_input(fixture_path("single_failure_74.xml")))
    assert run.metadata.input_profile == "rf-output-xml"
    assert run.metadata.schemaversion == 5
    assert run.metadata.generator.startswith("Robot 7.4.2")
    assert len(run.failed_tests) == 1


def test_parse_output_json_collects_failures_and_errors() -> None:
    run = parse_output_json(probe_json_input(fixture_path("errors_and_long_72.json")))
    assert run.metadata.input_profile == "rf-7.2+-output-json"
    assert run.metadata.source_format == "json"
    assert len(run.failed_tests) == 2
    assert run.errors
    assert any(message.owner_test_id for message in run.messages)


def test_parse_output_xml_avoids_robot_result_deprecation_warnings() -> None:
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        run = parse_output_xml(probe_xml_input(fixture_path("output-20260413-151651.xml")))

    assert run.run_id is None
    assert run.content_hash
    messages = [str(item.message) for item in captured]
    assert not any("robot.result." in message and "deprecated" in message for message in messages)
