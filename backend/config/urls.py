"""Root URL configuration: `/api/v1/` (REST), `/api/health/` + `/api/ready/` (probes),
`/api/schema/` + `/api/docs/` (OpenAPI, only when API_DOCS_ENABLED)."""

from django.conf import settings
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config import health

urlpatterns = [
    path("api/health/", health.health, name="health"),
    path("api/ready/", health.ready, name="ready"),
    path("api/v1/", include("config.api.urls")),
]

if settings.API_DOCS_ENABLED:
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="api-docs"),
    ]

handler404 = "config.api.views.not_found"
handler500 = "config.api.views.server_error"
handler403 = "config.api.views.permission_denied"
handler400 = "config.api.views.bad_request"
