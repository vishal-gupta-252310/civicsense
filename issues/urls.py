from django.urls import path

from . import views

urlpatterns = [
    path("", views.home_view, name="home"),
    path("report/", views.report_view, name="report"),
    path("issue/<int:pk>/", views.issue_detail_view, name="issue_detail"),
    path("map/", views.map_view, name="map"),
    path("issue/<int:pk>/upvote/", views.upvote_view, name="upvote"),
    path("api/suggest-description/", views.suggest_description_view, name="suggest_description"),
    path("analytics/", views.analytics_view, name="analytics"),
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
]