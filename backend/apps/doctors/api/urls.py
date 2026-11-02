from django.urls import path

from .views import NotificationPreferenceView, ProfileView

urlpatterns = [
    path("profile/", ProfileView.as_view(), name="profile"),
    path(
        "profile/notifications/",
        NotificationPreferenceView.as_view(),
        name="profile-notifications",
    ),
]
