"""`/api/v1/admin/...` — role ADMIN only."""

from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.doctors.api.admin_views import AdminDoctorViewSet
from apps.fees.api.admin_views import AdminFeeScheduleViewSet

from .admin_views import AdminApplicationViewSet, AdminStatsView

router = SimpleRouter()
router.register("applications", AdminApplicationViewSet, basename="admin-application")
router.register("doctors", AdminDoctorViewSet, basename="admin-doctor")
router.register("fee-schedules", AdminFeeScheduleViewSet, basename="admin-fee-schedule")

urlpatterns = [path("stats/", AdminStatsView.as_view(), name="admin-stats"), *router.urls]
