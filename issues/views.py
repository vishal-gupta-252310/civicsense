"""CivicSense views: auth, reporting, tracking, map, upvotes, analytics."""

import json

from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import EmailLoginForm, RegisterForm, ReportIssueForm, StatusUpdateForm
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
        form = EmailLoginForm(request.POST)
        if form.is_valid():
            login(request, form.cleaned_data["user"])
            return redirect("home")
    else:
        form = EmailLoginForm()
    return render(request, "issues/login.html", {"form": form})


def logout_view(request):
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
            ai = classify_issue(issue.description)
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
            "form": form,
            "upvote_count": issue.upvotes.count(),
            "has_upvoted": has_upvoted,
        },
    )


@login_required
def map_view(request):
    issues = Issue.objects.select_related("category").all()
    data = [
        {
            "id": i.pk,
            "description": i.description,
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
    data = classify_issue(hint or "a civic issue in my neighbourhood")
    text = (data.get("description") or data.get("summary") or "").strip()
    if not text:
        text = hint or "a civic issue in my neighbourhood"
    return JsonResponse({"description": text})


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