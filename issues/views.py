"""CivicSense views: auth, reporting, tracking, map, upvotes, analytics."""

import json

import requests

from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import (
    HttpResponseBadRequest,
    HttpResponseForbidden,
    HttpResponseNotAllowed,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import EmailLoginForm, RegisterForm, ReportIssueForm, StatusUpdateForm
from .llm import PLATFORMS, full_model_id, fetch_models
from .models import Category, Issue, StatusUpdate, Upvote, UserProfile
from .services import classify_issue, find_duplicate


def register_view(request):
    if request.user.is_authenticated:
        return redirect("home")
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            form.save()
            login(request, form.instance)
            return redirect("home")
    else:
        form = RegisterForm()
    return render(request, "issues/register.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")
    if request.method == "POST":
        form = EmailLoginForm(request.POST, request=request)
        if form.is_valid():
            login(request, form.cleaned_data["user"])
            return redirect("home")
    else:
        form = EmailLoginForm()
    response = render(request, "issues/login.html", {"form": form})
    # Expose the rate-limit as a real status code so the lockout is observable
    # (e.g. by clients/auditors) instead of looking like a normal failed login.
    if getattr(form, "lockout", False):
        response.status_code = 429
    return response


def logout_view(request):
    # GET logout is a CSRF-prone pattern (and shares the URL with any naive
    # <a> link or prefetcher); require a POST with the CSRF token.
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    logout(request)
    return redirect("home")


@login_required
def home_view(request):
    issues = Issue.objects.select_related("category", "reporter").all()
    total = issues.count()
    open_count = issues.filter(status="open").count()
    resolved_count = issues.filter(status="resolved").count()
    return render(
        request,
        "issues/home.html",
        {
            "issues": issues,
            "total_issues": total,
            "open_count": open_count,
            "resolved_count": resolved_count,
        },
    )


@login_required
def report_view(request):
    if request.method == "POST":
        form = ReportIssueForm(request.POST, request.FILES)
        if form.is_valid():
            issue = form.save(commit=False)
            issue.reporter = request.user
            profile = getattr(request.user, "profile", None)
            ai = classify_issue(
                issue.description,
                platform=profile.llm_platform if profile else "",
                api_key=profile.llm_api_key if profile else "",
                model=profile.llm_model if profile else "",
                photo=issue.photo,
            )
            category, _ = Category.objects.get_or_create(name=ai["category"])
            issue.category = category
            issue.ai_priority = ai["priority"]
            issue.ai_summary = ai["summary"]
            issue.duplicate_of = find_duplicate(
                issue.description, issue.latitude, issue.longitude
            )
            issue.save()
            return redirect("issue_detail", pk=issue.pk)
    else:
        form = ReportIssueForm()
    return render(request, "issues/report.html", {"form": form, "AI_SERVICE_URL": ""})


@login_required
def issue_detail_view(request, pk):
    issue = get_object_or_404(
        Issue.objects.select_related("category", "reporter", "duplicate_of"), pk=pk
    )
    is_staff = request.user.profile.role == "admin"
    if request.method == "POST" and is_staff:
        form = StatusUpdateForm(request.POST)
        if form.is_valid():
            new_status = form.cleaned_data["new_status"]
            StatusUpdate.objects.create(
                issue=issue,
                old_status=issue.status,
                new_status=new_status,
                note=form.cleaned_data["note"],
                staff=request.user,
            )
            if new_status == "resolved":
                issue.resolved_at = timezone.now()
            issue.status = new_status
            issue.save()
            return redirect("issue_detail", pk=issue.pk)
    else:
        form = StatusUpdateForm()
    has_upvoted = Upvote.objects.filter(issue=issue, user=request.user).exists()
    return render(
        request,
        "issues/issue_detail.html",
        {
            "issue": issue,
            "is_staff": is_staff,
            "is_owner": issue.reporter == request.user,
            "form": form,
            "upvote_count": issue.upvotes.count(),
            "has_upvoted": has_upvoted,
        },
    )


@login_required
def withdraw_view(request, pk):
    issue = get_object_or_404(Issue, pk=pk)
    if issue.reporter != request.user:
        return HttpResponseForbidden("You can only withdraw your own reports.")
    if request.method == "POST":
        issue.delete()
        return redirect("home")
    return render(request, "issues/withdraw_confirm.html", {"issue": issue})


@login_required
def map_view(request):
    issues = Issue.objects.select_related("category").all()
    data = [
        {
            "id": i.pk,
            "description": i.description,
            "address": i.address,
            "category": i.category.name if i.category else "Other",
            "priority": i.ai_priority,
            "status": i.status,
            "lat": i.latitude,
            "lng": i.longitude,
        }
        for i in issues
    ]
    return render(request, "issues/map.html", {"issues_json": json.dumps(data)})


@login_required
def suggest_description_view(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required.")
    try:
        hint = json.loads(request.body).get("hint", "")
    except (ValueError, AttributeError):
        hint = ""
    profile = getattr(request.user, "profile", None)
    data = classify_issue(
        hint or "a civic issue in my neighbourhood",
        platform=profile.llm_platform if profile else "",
        api_key=profile.llm_api_key if profile else "",
        model=profile.llm_model if profile else "",
    )
    if data.get("source") == "fallback":
        return JsonResponse(
            {
                "error": (
                    "The AI service fell back to a plain echo — no model responded. "
                    "Check your API key/model on the AI Settings page, or try again later."
                )
            },
            status=502,
        )
    text = (data.get("description") or data.get("summary") or "").strip()
    if not text:
        text = hint or "a civic issue in my neighbourhood"
    return JsonResponse({"description": text})


@login_required
def llm_settings_view(request):
    profile = request.user.profile
    if request.method == "POST":
        platform = (request.POST.get("platform") or "").strip()
        api_key = (request.POST.get("api_key") or "").strip()
        model_id = (request.POST.get("model") or "").strip()
        if platform and platform not in PLATFORMS:
            return render(
                request,
                "issues/llm_settings.html",
                {
                    "error": "Unknown platform.",
                    "platforms": PLATFORMS,
                },
                status=400,
            )
        profile.llm_platform = platform
        # Write-only key: a blank field means "keep the saved key".
        if api_key:
            profile.llm_api_key = api_key
        # Strip any provider prefix the dropdown may have included so
        # full_model_id() doesn't double-prefix (e.g. "groq/groq/...").
        _STRIP_PREFIXES = ("groq/", "gemini/", "openrouter/", "openai/", "anthropic/", "mistral/", "deepseek/", "together_ai/")
        for _pfx in _STRIP_PREFIXES:
            if model_id.startswith(_pfx):
                model_id = model_id[len(_pfx):]
                break
        profile.llm_model = full_model_id(platform, model_id) if platform and model_id else ""
        profile.save(update_fields=["llm_platform", "llm_api_key", "llm_model"])
        return redirect("llm_settings")
    return render(
        request,
        "issues/llm_settings.html",
        {
            "platforms": PLATFORMS,
            "saved_platform": profile.llm_platform,
            "saved_model": profile.llm_model,
            # Never send the stored key back to the page (CIV-09).
            "saved_key_configured": bool(profile.llm_api_key),
        },
    )


@login_required
def llm_models_api(request):
    if request.method == "POST":
        platform = (request.POST.get("platform") or "").strip()
        api_key = (request.POST.get("api_key") or "").strip()
    else:
        platform = (request.GET.get("platform") or "").strip()
        api_key = (request.GET.get("api_key") or "").strip()
    if not api_key:
        api_key = request.user.profile.llm_api_key
    try:
        ids = fetch_models(platform, api_key)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except requests.RequestException:
        return JsonResponse({"error": "Could not fetch models for this platform."}, status=502)
    return JsonResponse(
        {
            "platform": platform,
            "models": [{"id": mid, "model": full_model_id(platform, mid)} for mid in ids],
        }
    )


@login_required
def upvote_view(request, pk):
    issue = get_object_or_404(Issue, pk=pk)
    if request.method == "POST":
        upvote, created = Upvote.objects.get_or_create(issue=issue, user=request.user)
        if not created:
            upvote.delete()
            return JsonResponse({"count": issue.upvotes.count(), "voted": False})
        return JsonResponse({"count": issue.upvotes.count(), "voted": True})
    return HttpResponseBadRequest("Upvote requires POST.")


@login_required
def analytics_view(request):
    if request.user.profile.role != "admin":
        return redirect("home")

    issues = Issue.objects.select_related("category")
    by_status = {}
    for status, label in Issue.STATUS:
        by_status[label] = issues.filter(status=status).count()

    by_category = {}
    for cat in Category.objects.all():
        count = issues.filter(category=cat).count()
        if count:
            by_category[cat.name] = count

    by_priority = {}
    for priority, label in Issue.PRIORITY:
        by_priority[label] = issues.filter(ai_priority=priority).count()

    return render(
        request,
        "issues/analytics.html",
        {
            "total_issues": issues.count(),
            "open_count": issues.filter(status="open").count(),
            "resolved_count": issues.filter(status="resolved").count(),
            "total_upvotes": Upvote.objects.count(),
            "by_status": json.dumps(by_status),
            "by_category": json.dumps(by_category),
            "by_priority": json.dumps(by_priority),
        },
    )


def page_not_found(request, exception=None):
    return render(request, "issues/404.html", status=404)


def permission_denied(request, exception=None):
    return render(request, "issues/403.html", status=403)


def server_error(request):
    return render(request, "issues/500.html", status=500)