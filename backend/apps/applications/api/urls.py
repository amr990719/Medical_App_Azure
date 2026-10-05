from rest_framework.routers import SimpleRouter

from .views import ApplicationViewSet

router = SimpleRouter()
router.register("applications", ApplicationViewSet, basename="application")

urlpatterns = router.urls
