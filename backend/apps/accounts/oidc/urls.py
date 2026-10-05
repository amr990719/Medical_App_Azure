from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="auth-login"),
    path("callback/", views.CallbackView.as_view(), name="auth-callback"),
]
