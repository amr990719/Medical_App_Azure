from rest_framework import serializers

from apps.accounts.models import Role, User
from apps.accounts.services import display_name


class CurrentUserSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    has_profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "role", "display_name", "has_profile"]
        read_only_fields = fields

    def get_display_name(self, user) -> str:
        return display_name(user)

    def get_has_profile(self, user) -> bool:
        return hasattr(user, "doctor")


class MeSerializer(serializers.Serializer):
    user = CurrentUserSerializer()
    csrf_token = serializers.CharField()


class LogoutSerializer(serializers.Serializer):
    entra_logout_url = serializers.CharField(allow_null=True)


class DevUserSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "role", "display_name"]
        read_only_fields = fields

    def get_display_name(self, user) -> str:
        return display_name(user)


class DevLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    # Development/end-to-end only: create a fresh DOCTOR when the e-mail is unknown, so every
    # Playwright run starts without an application. Existing users keep their role.
    create = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs: dict) -> dict:
        email = attrs["email"].strip().lower()
        user = User.objects.filter(email=email).first()
        if user is None and attrs["create"]:
            user = User.objects.create_user(email, display_name="", role=Role.DOCTOR)
        if user is None or not user.is_active:
            raise serializers.ValidationError({"email": ["لا يوجد مستخدم تجريبي بهذا البريد"]})
        attrs["email"] = user
        return attrs


__all__ = ["Role"]
