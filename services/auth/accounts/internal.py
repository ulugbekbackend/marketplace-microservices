"""Service-to-service API (notification). Traefik routes only ``/api/auth``, so
``/internal/auth`` is reachable on the internal network only.

    GET /internal/auth/users/{id}/contact/ -> {phone, full_name, email, telegram_chat_id}

Sellers are users (``seller_id == user_id``), so the same lookup serves both roles.
"""

from uuid import UUID

from django.urls import path
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from py_common.web.drf import ApiError


class UserContactView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(exclude=True)
    def get(self, request: Request, user_id: UUID) -> Response:
        user = User.objects.filter(pk=user_id, is_active=True).first()
        if user is None:
            raise ApiError("NOT_FOUND", "User not found.", status=404)
        return Response(
            {
                "phone": user.phone,
                "full_name": user.full_name,
                "email": user.email,
                "telegram_chat_id": user.telegram_chat_id,
            }
        )


urlpatterns = [
    path("users/<uuid:user_id>/contact/", UserContactView.as_view(), name="internal-user-contact"),
]
