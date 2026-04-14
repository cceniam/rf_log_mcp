"""Robot Framework XML parsing entrypoint."""

from __future__ import annotations

from rf_log_mcp.domain.models import NormalizedRun
from rf_log_mcp.parsers.gating import ProbedInput
from rf_log_mcp.parsers.result_adapter import parse_output_result


def parse_output_xml(probed: ProbedInput) -> NormalizedRun:
    return parse_output_result(probed)
