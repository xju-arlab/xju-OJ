from django.urls import path

from . import views

urlpatterns = [
    path("problems", views.ProblemsAPI.as_view()),
    path("draft", views.DraftAPI.as_view()),
    path("file", views.FileAPI.as_view()),
    path("jobs", views.JobsAPI.as_view()),
    path("completed", views.CompletedAPI.as_view()),
    path("contest", views.AIContestAPI.as_view()),
    path("leaderboard", views.LeaderboardAPI.as_view()),
    path("problem-leaderboard", views.ProblemLeaderboardAPI.as_view()),
    path("health", views.HealthAPI.as_view()),
    path("worker", views.WorkerAPI.as_view()),
]
