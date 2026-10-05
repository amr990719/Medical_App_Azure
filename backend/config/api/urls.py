"""`/api/v1/` routes, one include per app."""

from django.urls import include, path

from config.api import schema  # noqa: F401 — registers OpenAPI extensions

urlpatterns = [
    path("", include("apps.accounts.api.urls")),
    path("", include("apps.reference.api.urls")),
    path("", include("apps.doctors.api.urls")),
    path("", include("apps.applications.api.urls")),
    path("", include("apps.beneficiaries.api.urls")),
    path("", include("apps.documents.api.urls")),
    path("", include("apps.ocr.api.urls")),
    path("admin/", include("apps.applications.api.admin_urls")),
]
