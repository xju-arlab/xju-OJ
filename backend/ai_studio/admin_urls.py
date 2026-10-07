from django.urls import path

from .views import ContestAdminAPI, ProblemAdminAPI

urlpatterns = [path("problems", ProblemAdminAPI.as_view()), path("contest", ContestAdminAPI.as_view())]
