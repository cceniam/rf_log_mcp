"""Application errors with stable codes."""

from __future__ import annotations


class RfLogMcpError(Exception):
    """Base error with a stable code for MCP responses."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class InvalidFileTypeError(RfLogMcpError):
    def __init__(self, message: str = "Only .xml files are supported.") -> None:
        super().__init__("INVALID_FILE_TYPE", message)


class InvalidXmlError(RfLogMcpError):
    def __init__(
        self,
        message: str = "Input file is not a valid Robot Framework XML result.",
    ) -> None:
        super().__init__("INVALID_XML", message)


class InvalidJsonError(RfLogMcpError):
    def __init__(
        self,
        message: str = "Input file is not a valid Robot Framework JSON result.",
    ) -> None:
        super().__init__("INVALID_JSON", message)


class UnsupportedInputVersionError(RfLogMcpError):
    def __init__(self, message: str) -> None:
        super().__init__("UNSUPPORTED_INPUT_VERSION", message)


class RunNotFoundError(RfLogMcpError):
    def __init__(self, run_id: str) -> None:
        super().__init__("RUN_NOT_FOUND", f"Run '{run_id}' does not exist.")


class InvalidViewError(RfLogMcpError):
    def __init__(self, view: str) -> None:
        super().__init__("INVALID_VIEW", f"View '{view}' is not supported.")


class InvalidCursorError(RfLogMcpError):
    def __init__(self, message: str = "Cursor is invalid.") -> None:
        super().__init__("INVALID_CURSOR", message)


class TestNotFoundError(RfLogMcpError):
    def __init__(self, test_id: str) -> None:
        super().__init__("TEST_NOT_FOUND", f"Test '{test_id}' does not exist.")


class InvalidQueryError(RfLogMcpError):
    def __init__(self, message: str = "Query must not be empty.") -> None:
        super().__init__("INVALID_QUERY", message)
