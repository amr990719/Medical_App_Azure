from django.urls import path

from .views import ExtractView

urlpatterns = [
    path("documents/<uuid:pk>/extract/", ExtractView.as_view(), name="document-extract"),
]
