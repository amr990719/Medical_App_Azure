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

    def validate_email(self, value: str) -> User:
        user = User.objects.filter(email=value.strip().lower(), is_active=True).first()
        if user is None:
            raise serializers.ValidationError("لا يوجد مستخدم تجريبي بهذا البريد")
        return user


__all__ = ["Role"]
