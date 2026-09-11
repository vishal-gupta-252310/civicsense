from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from .forms import CivicPasswordResetForm, CivicSetPasswordForm
from . import views

urlpatterns = [
    path("", views.home_view, name="home"),
    path("report/", views.report_view, name="report"),
    path("issue/<int:pk>/", views.issue_detail_view, name="issue_detail"),
    path("issue/<int:pk>/withdraw/", views.withdraw_view, name="withdraw_issue"),
    path("map/", views.map_view, name="map"),
    path("issue/<int:pk>/upvote/", views.upvote_view, name="upvote"),
    path("api/suggest-description/", views.suggest_description_view, name="suggest_description"),
    path("settings/llm/", views.llm_settings_view, name="llm_settings"),
    path("api/llm/models/", views.llm_models_api, name="llm_models"),
    path("analytics/", views.analytics_view, name="analytics"),
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            form_class=CivicPasswordResetForm,
            template_name="issues/password_reset_form.html",
            subject_template_name="issues/email/password_reset_subject.txt",
            email_template_name="issues/email/password_reset_body.txt",
            html_email_template_name="issues/email/password_reset_body.html",
            extra_email_context={"site_name": "CivicSense"},
            success_url=reverse_lazy("password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="issues/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "password-reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            form_class=CivicSetPasswordForm,
            template_name="issues/password_reset_confirm.html",
            success_url=reverse_lazy("password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "password-reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="issues/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
]