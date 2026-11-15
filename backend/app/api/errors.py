"""One place that turns the services' errors into HTTP answers.

A service raises; the request's session is rolled back so nothing half-done stays behind
(including a proposal that couldn't be approved); the client gets the user-facing message.
"""

from collections.abc import Callable

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.services.ask import AskNotAllowed, AskNotFound
from app.services.errors import ApprovalError, NotAllowed, NotFound
from app.services.huddle import HuddleError, HuddleNotAllowed, HuddleNotFound
from app.services.inbound import UnknownPerson

# The most specific class wins: FastAPI looks handlers up along the error's own MRO.
STATUS_FOR: dict[type[Exception], int] = {
    NotFound: status.HTTP_404_NOT_FOUND,
    NotAllowed: status.HTTP_403_FORBIDDEN,
    ApprovalError: status.HTTP_409_CONFLICT,
    AskNotFound: status.HTTP_404_NOT_FOUND,
    AskNotAllowed: status.HTTP_403_FORBIDDEN,
    HuddleNotFound: status.HTTP_404_NOT_FOUND,
    HuddleNotAllowed: status.HTTP_403_FORBIDDEN,
    HuddleError: status.HTTP_409_CONFLICT,
    UnknownPerson: status.HTTP_404_NOT_FOUND,
}


def register_error_handlers(app: FastAPI) -> None:
    for error_type, code in STATUS_FOR.items():
        app.add_exception_handler(error_type, _handler(code))


def _handler(code: int) -> Callable[[Request, Exception], JSONResponse]:
    def handle(request: Request, error: Exception) -> JSONResponse:
        session = getattr(request.state, "session", None)
        if session is not None:
            session.rollback()
        return JSONResponse({"detail": str(error)}, status_code=code)

    return handle
