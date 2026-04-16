from enum import IntEnum


class ErrorCode(IntEnum):
    # Connection errors (1000s)
    CONNECTION_FAILED = 1000
    CONNECTION_REFUSED = 1001
    CONNECTION_TIMEOUT = 1002
    CONNECTION_LOST = 1003
    SEND_FAILED = 1004
    RECV_FAILED = 1005

    # Command errors (2000s)
    COMMAND_FAILED = 2000
    COMMAND_NOT_FOUND = 2001
    COMMAND_TIMEOUT = 2002
    COMMAND_REJECTED = 2003

    # Validation errors (3000s)
    VALIDATION_FAILED = 3000
    INVALID_PARAMETER = 3001
    MISSING_PARAMETER = 3002
    INVALID_PATH = 3003
    INVALID_FORMAT = 3004
    INJECTION_DETECTED = 3005
    VALUE_OUT_OF_RANGE = 3006


class ReaperMCPError(Exception):
    def __init__(self, code: ErrorCode, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code.name} ({code.value})] {message}")
