from django.urls import path

from .views import ContestAdminAPI, ProblemAdminAPI, ReviewAdminAPI
from .package_views import PackageConfirmAPI, PackageExportAPI, PackageImportAPI

urlpatterns = [
    path("problems", ProblemAdminAPI.as_view()), path("contest", ContestAdminAPI.as_view()),
    path("packages", PackageImportAPI.as_view()), path("packages/confirm", PackageConfirmAPI.as_view()),
    path("packages/export", PackageExportAPI.as_view()), path("reviews", ReviewAdminAPI.as_view()),
]
