from django.urls import path

from . import views

urlpatterns = [
    path(
        "applications/<uuid:application_id>/dues-requests/<uuid:dues_id>/receipts/",
        views.DuesReceiptUploadView.as_view(),
        name="dues-receipt-upload",
    ),
]

admin_urlpatterns = [
    path(
        "applications/<uuid:application_id>/dues-requests/",
        views.AdminDuesRequestCreateView.as_view(),
        name="admin-dues-request-create",
    ),
    path(
        "applications/<uuid:application_id>/dues-requests/<uuid:dues_id>/review/",
        views.AdminDuesReviewView.as_view(),
        name="admin-dues-request-review",
    ),
    path(
        "applications/<uuid:application_id>/dues-requests/<uuid:dues_id>/cancel/",
        views.AdminDuesCancelView.as_view(),
        name="admin-dues-request-cancel",
    ),
]
