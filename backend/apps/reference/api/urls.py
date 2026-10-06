from django.urls import path

from .views import ReferenceDataView

urlpatterns = [path("reference-data/", ReferenceDataView.as_view(), name="reference-data")]
