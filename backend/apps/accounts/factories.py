import factory

from .models import Role, User


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("email",)

    email = factory.Sequence(lambda n: f"doctor{n}@example.test")
    role = Role.DOCTOR

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        return model_class.objects.create_user(*args, **kwargs)


class AdminUserFactory(UserFactory):
    email = factory.Sequence(lambda n: f"admin{n}@example.test")
    role = Role.ADMIN
