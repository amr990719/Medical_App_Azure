from django.urls import include, path

from . import views

urlpatterns = [
    path("auth/me/", views.MeView.as_view(), name="auth-me"),
    path("auth/logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("auth/dev/users/", views.DevUsersView.as_view(), name="auth-dev-users"),
    path("auth/dev/login/", views.DevLoginView.as_view(), name="auth-dev-login"),
    path("auth/", include("apps.accounts.oidc.urls")),
]
