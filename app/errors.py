class NotFound(Exception):
    """A user, session or question does not exist (404)."""


class BadRequest(Exception):
    """The request is not valid in the current state (400)."""


class Unauthorized(Exception):
    """Missing or invalid login (401)."""


class Forbidden(Exception):
    """Logged in, but not allowed (403)."""


class BudgetExceeded(Exception):
    """The Guardian agent stopped the run: budget used up, kill switch on, or account suspended (429)."""

    def __init__(self, message: str, code: str = "budget"):
        super().__init__(message)
        self.code = code
