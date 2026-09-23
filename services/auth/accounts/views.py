"""HTTP endpoints of the auth service, all under /api/auth/."""

from typing import Any
from uuid import UUID

from django.db.models import QuerySet
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import otp, sellers, tokens
from accounts.models import SellerApplication, User
from accounts.serializers import (
    AdminSellerApplicationSerializer,
    ApplicationFilterSerializer,
    ErrorSerializer,
    JwksSerializer,
    LoginSerializer,
    OtpSendSerializer,
    OtpVerifySerializer,
    RefreshSerializer,
    SellerApplicationSerializer,
    SellerApplySerializer,
    TokenPairSerializer,
    UserSerializer,
    UserUpdateSerializer,
)
from contracts.headers import X_SELLER_ID, X_USER_ID, X_USER_ROLE
from py_common.auth import CurrentUser
from py_common.web.drf import ApiError, IsAdmin, current_user

ERRORS: dict[int, Any] = {
    code: OpenApiResponse(ErrorSerializer, description=description)
    for code, description in (
        (400, "Invalid input"),
        (401, "Not authenticated"),
        (403, "Not allowed"),
        (404, "Not found"),
        (409, "Conflict"),
        (429, "Rate limited"),
    )
}


def errors(*codes: int) -> dict[int, Any]:
    return {code: ERRORS[code] for code in codes}


def _caller(request: Request) -> CurrentUser:
    user = current_user(request)
    assert user is not None  # guaranteed by the permission classes
    return user


def _token_error(exc: tokens.InvalidTokenError) -> ApiError:
    return ApiError(
        "TOKEN_INVALID", "Token is invalid or expired.", status=401, details={"reason": str(exc)}
    )


class PublicView(APIView):
    """No gateway identity needed: the caller proves itself with a code or a token."""

    authentication_classes = ()
    permission_classes = (AllowAny,)


class OtpSendView(PublicView):
    @extend_schema(
        request=OtpSendSerializer,
        responses={204: None, **errors(400, 429)},
        summary="Send a sign in code by SMS",
    )
    def post(self, request: Request) -> Response:
        serializer = OtpSendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        otp.send_code(serializer.validated_data["phone"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class OtpVerifyView(PublicView):
    @extend_schema(
        request=OtpVerifySerializer,
        responses={200: LoginSerializer, **errors(400, 403, 429)},
        summary="Sign in with the code; creates the account on first sign in",
    )
    def post(self, request: Request) -> Response:
        serializer = OtpVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, pair = otp.verify_code(
            serializer.validated_data["phone"], serializer.validated_data["code"]
        )
        body = {"access": pair.access, "refresh": pair.refresh, "user": UserSerializer(user).data}
        return Response(LoginSerializer(body).data)


class TokenRefreshView(PublicView):
    @extend_schema(
        request=RefreshSerializer,
        responses={200: TokenPairSerializer, **errors(400, 401)},
        summary="Exchange a refresh token for a new pair; the old refresh is revoked",
    )
    def post(self, request: Request) -> Response:
        serializer = RefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            pair = tokens.rotate_refresh(serializer.validated_data["refresh"])
        except tokens.InvalidTokenError as exc:
            raise _token_error(exc) from exc
        return Response(TokenPairSerializer(pair).data)


class LogoutView(PublicView):
    @extend_schema(
        request=RefreshSerializer,
        responses={204: None, **errors(400, 401)},
        summary="Revoke a refresh token",
    )
    def post(self, request: Request) -> Response:
        serializer = RefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            tokens.revoke_refresh(serializer.validated_data["refresh"])
        except tokens.InvalidTokenError as exc:
            raise _token_error(exc) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)


def _identity_header(name: str, description: str) -> OpenApiParameter:
    return OpenApiParameter(
        name, OpenApiTypes.STR, OpenApiParameter.HEADER, description=description, response=[200]
    )


class VerifyView(PublicView):
    """Traefik ForwardAuth target.

    The signature and expiry are checked locally with the public key; then one primary key
    lookup confirms the account is still active and reads its current role, so a blocked user
    or a revoked role stops working at once rather than when the access token expires.
    """

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "optional",
                OpenApiTypes.INT,
                OpenApiParameter.QUERY,
                description="1: a request without a token passes as a guest (no headers).",
                enum=[0, 1],
            ),
            _identity_header(X_USER_ID, "Verified user id."),
            _identity_header(X_USER_ROLE, "Verified role."),
            _identity_header(X_SELLER_ID, "Seller id (the user id); sellers only."),
        ],
        responses={200: None, **errors(401)},
        summary="Gateway token check (ForwardAuth)",
    )
    def get(self, request: Request) -> Response:
        header = request.headers.get("Authorization", "")
        if not header:
            if request.query_params.get("optional") == "1":
                return Response(status=status.HTTP_200_OK)
            raise ApiError("NOT_AUTHENTICATED", "Authentication required.", status=401)

        scheme, _, raw = header.partition(" ")
        if scheme.lower() != "bearer" or not raw.strip():
            raise ApiError("TOKEN_INVALID", "Expected a Bearer token.", status=401)
        try:
            identity = tokens.verify_access(raw.strip())
        except tokens.InvalidTokenError as exc:
            raise _token_error(exc) from exc

        response = Response(status=status.HTTP_200_OK)
        response[X_USER_ID] = str(identity.user_id)
        response[X_USER_ROLE] = identity.role.value
        if identity.seller_id is not None:
            response[X_SELLER_ID] = str(identity.seller_id)
        return response


class JwksView(PublicView):
    @extend_schema(responses={200: JwksSerializer}, summary="Public signing keys (JWKS)")
    def get(self, request: Request) -> Response:
        response = Response(JwksSerializer(tokens.jwks()).data)
        response["Cache-Control"] = "public, max-age=300"
        return response


class MeView(APIView):
    def _user(self, request: Request) -> User:
        user = User.objects.filter(pk=_caller(request).user_id, is_active=True).first()
        if user is None:
            raise ApiError("USER_NOT_FOUND", "User not found.", status=404)
        return user

    @extend_schema(responses={200: UserSerializer, **errors(401, 404)}, summary="Current user")
    def get(self, request: Request) -> Response:
        return Response(UserSerializer(self._user(request)).data)

    @extend_schema(
        request=UserUpdateSerializer,
        responses={200: UserSerializer, **errors(400, 401, 404)},
        summary="Update the current user's profile",
    )
    def patch(self, request: Request) -> Response:
        user = self._user(request)
        serializer = UserUpdateSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(user).data)


class SellerApplyView(APIView):
    @extend_schema(
        request=SellerApplySerializer,
        responses={201: SellerApplicationSerializer, **errors(400, 401, 404, 409)},
        summary="Apply to become a seller",
    )
    def post(self, request: Request) -> Response:
        serializer = SellerApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = sellers.apply(
            _caller(request).user_id,
            shop_name=serializer.validated_data["shop_name"],
            inn=serializer.validated_data["inn"],
            description=serializer.validated_data.get("description", ""),
        )
        return Response(
            SellerApplicationSerializer(application).data, status=status.HTTP_201_CREATED
        )


class SellerApplicationView(APIView):
    @extend_schema(
        responses={200: SellerApplicationSerializer, **errors(401, 404)},
        summary="The caller's latest seller application",
    )
    def get(self, request: Request) -> Response:
        application = sellers.latest_application(_caller(request).user_id)
        if application is None:
            raise ApiError("NOT_FOUND", "No application yet.", status=404)
        return Response(SellerApplicationSerializer(application).data)


class AdminApplicationListView(ListAPIView[SellerApplication]):
    permission_classes = (IsAdmin,)
    serializer_class = AdminSellerApplicationSerializer

    @extend_schema(
        parameters=[ApplicationFilterSerializer],
        responses={200: AdminSellerApplicationSerializer(many=True), **errors(400, 401, 403)},
        summary="Seller applications for review",
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().get(request, *args, **kwargs)

    def get_queryset(self) -> QuerySet[SellerApplication]:
        filters = ApplicationFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        queryset = SellerApplication.objects.select_related("user").order_by("created_at", "id")
        wanted = filters.validated_data.get("status")
        if wanted:
            queryset = queryset.filter(status=wanted)
        return queryset


_REVIEW_RESPONSES: dict[int, Any] = {
    200: AdminSellerApplicationSerializer,
    **errors(401, 403, 404, 409),
}


class AdminApproveView(APIView):
    permission_classes = (IsAdmin,)

    @extend_schema(
        request=None,
        responses=_REVIEW_RESPONSES,
        summary="Approve an application: the user becomes a seller",
    )
    def post(self, request: Request, application_id: UUID) -> Response:
        application = sellers.approve(application_id, reviewer_id=_caller(request).user_id)
        return Response(AdminSellerApplicationSerializer(application).data)


class AdminRejectView(APIView):
    permission_classes = (IsAdmin,)

    @extend_schema(request=None, responses=_REVIEW_RESPONSES, summary="Reject an application")
    def post(self, request: Request, application_id: UUID) -> Response:
        application = sellers.reject(application_id, reviewer_id=_caller(request).user_id)
        return Response(AdminSellerApplicationSerializer(application).data)
