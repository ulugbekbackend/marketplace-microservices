"""Request and response shapes. Every endpoint documents both for the generated client."""

from typing import Any, ClassVar

from rest_framework import serializers

from accounts.models import ApplicationStatus, SellerApplication, User


class UserSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = ("id", "phone", "full_name", "role", "date_joined")
        read_only_fields = fields


class UserUpdateSerializer(serializers.ModelSerializer[User]):
    full_name = serializers.CharField(max_length=150, allow_blank=False, trim_whitespace=True)

    class Meta:
        model = User
        fields = ("full_name",)


class OtpSendSerializer(serializers.Serializer[Any]):
    phone = serializers.CharField(max_length=32)


class OtpVerifySerializer(serializers.Serializer[Any]):
    phone = serializers.CharField(max_length=32)
    code = serializers.RegexField(r"^\d{6}$", max_length=6)


class RefreshSerializer(serializers.Serializer[Any]):
    refresh = serializers.CharField()


class TokenPairSerializer(serializers.Serializer[Any]):
    access = serializers.CharField()
    refresh = serializers.CharField()


class LoginSerializer(TokenPairSerializer):
    user = UserSerializer()


class SellerApplySerializer(serializers.ModelSerializer[SellerApplication]):
    class Meta:
        model = SellerApplication
        fields = ("shop_name", "inn", "description")
        extra_kwargs: ClassVar[dict[str, dict[str, Any]]] = {"description": {"required": False}}


class SellerApplicationSerializer(serializers.ModelSerializer[SellerApplication]):
    class Meta:
        model = SellerApplication
        fields = ("id", "shop_name", "inn", "description", "status", "reviewed_at", "created_at")
        read_only_fields = fields


class ApplicantSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = ("id", "phone", "full_name")
        read_only_fields = fields


class AdminSellerApplicationSerializer(serializers.ModelSerializer[SellerApplication]):
    user = ApplicantSerializer(read_only=True)
    reviewed_by = serializers.UUIDField(source="reviewed_by_id", read_only=True, allow_null=True)

    class Meta:
        model = SellerApplication
        fields = (
            "id",
            "user",
            "shop_name",
            "inn",
            "description",
            "status",
            "reviewed_by",
            "reviewed_at",
            "created_at",
        )
        read_only_fields = fields


class ApplicationFilterSerializer(serializers.Serializer[Any]):
    status = serializers.ChoiceField(choices=ApplicationStatus.choices, required=False)


class JwkSerializer(serializers.Serializer[Any]):
    kty = serializers.CharField()
    use = serializers.CharField()
    alg = serializers.CharField()
    kid = serializers.CharField()
    n = serializers.CharField()
    e = serializers.CharField()


class JwksSerializer(serializers.Serializer[Any]):
    keys = JwkSerializer(many=True)


class ErrorDetailSerializer(serializers.Serializer[Any]):
    code = serializers.CharField()
    message = serializers.CharField()
    details = serializers.DictField()


class ErrorSerializer(serializers.Serializer[Any]):
    """The shared error shape: {"error": {"code", "message", "details"}}."""

    error = ErrorDetailSerializer()
