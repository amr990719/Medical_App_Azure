from django.contrib.auth.base_user import BaseUserManager


def normalize_email_address(email: str) -> str:
    """Lowercase the whole address: identity lookups are case-insensitive."""
    return (email or "").strip().lower()


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        if not email:
            raise ValueError("email is required")
        user = self.model(email=normalize_email_address(email), **extra_fields)
        if password:
            user.set_password(password)
        else:
            # Sign-in is Entra External ID only; local passwords are never usable.
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_admin(self, email: str, **extra_fields):
        from .models import Role

        extra_fields["role"] = Role.ADMIN
        return self.create_user(email, **extra_fields)
