"""Django REST framework wiring shared by the Django services.

Identity comes from gateway headers, errors share one shape, lists share one page format:
    {"error": {"code": "OUT_OF_STOCK", "message": "...", "details": {...}}}
    {"items": [...], "total": 42, "page": 1, "page_size": 20}
"""

from typing import TYPE_CHECKING, Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.authentication import BaseAuthentication
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response

from contracts.enums import UserRole
from py_common.auth import AuthError, CurrentUser, parse_user_headers

if TYPE_CHECKING:
    # Imported for annotations only: rest_framework.views loads the authentication
    # classes from settings, and this module is one of them.
    from rest_framework.views import APIView


class ApiError(exceptions.APIException):
    """A business error with a stable machine readable code.

    raise ApiError("OUT_OF_STOCK", "Not enough stock", status=409, details={...})
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail=message, code=code)
        self.status_code = status
        self.error_code = code
        self.details = details or {}


class GatewayAuthentication(BaseAuthentication):
    """Trust the identity headers Traefik set after the auth service verified the token."""

    def authenticate(self, request: Request) -> tuple[CurrentUser, None] | None:
        try:
            user = parse_user_headers(request.headers)
        except AuthError as exc:
            raise exceptions.AuthenticationFailed(str(exc)) from exc
        if user is None:
            return None
        return user, None

    def authenticate_header(self, request: Request) -> str:
        # A value here turns anonymous access into 401 instead of 403.
        return "Bearer"


def current_user(request: Request) -> CurrentUser | None:
    user = getattr(request, "user", None)
    return user if isinstance(user, CurrentUser) else None


class IsAuthenticatedUser(BasePermission):
    message = "Authentication required."

    def has_permission(self, request: Request, view: "APIView") -> bool:
        return current_user(request) is not None


class _RolePermission(BasePermission):
    role: UserRole

    def has_permission(self, request: Request, view: "APIView") -> bool:
        user = current_user(request)
        return user is not None and user.role is self.role


class IsSeller(_RolePermission):
    role = UserRole.SELLER
    message = "Seller account required."


class IsAdmin(_RolePermission):
    role = UserRole.ADMIN
    message = "Admin account required."


class PagePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data: Any) -> Response:
        assert self.page is not None and self.request is not None
        return Response(
            {
                "items": data,
                "total": self.page.paginator.count,
                "page": self.page.number,
                "page_size": self.get_page_size(self.request) or self.page_size,
            }
        )

    def get_paginated_response_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["items", "total", "page", "page_size"],
            "properties": {
                "items": schema,
                "total": {"type": "integer"},
                "page": {"type": "integer"},
                "page_size": {"type": "integer"},
            },
        }


_STATUS_CODES = {
    status.HTTP_400_BAD_REQUEST: "VALIDATION_ERROR",
    status.HTTP_401_UNAUTHORIZED: "NOT_AUTHENTICATED",
    status.HTTP_403_FORBIDDEN: "PERMISSION_DENIED",
    status.HTTP_404_NOT_FOUND: "NOT_FOUND",
    status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
    status.HTTP_409_CONFLICT: "CONFLICT",
    status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMITED",
}


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """REST_FRAMEWORK["EXCEPTION_HANDLER"]: every error leaves in the shared shape."""
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    if isinstance(exc, ApiError):
        response = Response(
            error_body(exc.error_code, str(exc.detail), exc.details), status=exc.status_code
        )
    elif isinstance(exc, exceptions.ValidationError):
        details = exc.detail if isinstance(exc.detail, dict) else {"non_field_errors": exc.detail}
        response = Response(
            error_body("VALIDATION_ERROR", "Invalid input.", dict(details)),
            status=exc.status_code,
        )
    elif isinstance(exc, exceptions.APIException):
        code = _STATUS_CODES.get(exc.status_code, "ERROR")
        response = Response(error_body(code, str(exc.detail)), status=exc.status_code)
        wait = getattr(exc, "wait", None)
        if isinstance(exc, exceptions.Throttled) and wait is not None:
            response["Retry-After"] = str(int(wait))
    else:
        return None  # unexpected: let Django log it and return 500

    auth_header = getattr(exc, "auth_header", None)
    if auth_header:
        response["WWW-Authenticate"] = auth_header
    return response
