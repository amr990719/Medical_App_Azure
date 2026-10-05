from django.urls import path

from .views import BeneficiaryViewSet

collection = BeneficiaryViewSet.as_view({"get": "list", "post": "create"})
item = BeneficiaryViewSet.as_view({"patch": "partial_update", "delete": "destroy"})

urlpatterns = [
    path(
        "applications/<uuid:application_id>/beneficiaries/",
        collection,
        name="beneficiary-list",
    ),
    path(
        "applications/<uuid:application_id>/beneficiaries/<uuid:pk>/",
        item,
        name="beneficiary-detail",
    ),
]
