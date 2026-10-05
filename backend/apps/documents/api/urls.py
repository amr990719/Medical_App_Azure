from django.urls import path

from . import views

urlpatterns = [
    path(
        "applications/<uuid:application_id>/documents/",
        views.DocumentUploadView.as_view(),
        name="document-upload",
    ),
    path("documents/<uuid:pk>/", views.DocumentDetailView.as_view(), name="document-detail"),
    path(
        "documents/<uuid:pk>/content/", views.DocumentContentView.as_view(), name="document-content"
    ),
]
