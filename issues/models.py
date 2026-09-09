"""Issue models (Listing 3.1)."""

from django.conf import settings
from django.db import models

ROLE_CHOICES = [
    ("citizen", "Citizen"),
    ("admin", "Administrator"),
]


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="citizen")
    llm_platform = models.CharField(max_length=30, blank=True, default="")
    llm_api_key = models.CharField(max_length=500, blank=True, default="")
    llm_model = models.CharField(max_length=200, blank=True, default="")

    def __str__(self):
        return f"{self.user} ({self.get_role_display()})"


class Category(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class Issue(models.Model):
    STATUS = [
        ("open", "Open"),
        ("progress", "In Progress"),
        ("resolved", "Resolved"),
    ]
    PRIORITY = [
        ("High", "High"),
        ("Medium", "Medium"),
        ("Low", "Low"),
    ]

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="issues",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="issues",
    )
    description = models.TextField()
    address = models.CharField(max_length=255, blank=True)
    photo = models.ImageField(upload_to="issues/", blank=True, null=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    ai_priority = models.CharField(max_length=10, choices=PRIORITY, default="Medium")
    ai_summary = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="open")
    duplicate_of = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="duplicates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_status_display()} {self.category} #{self.pk}"


class StatusUpdate(models.Model):
    issue = models.ForeignKey(
        Issue,
        on_delete=models.CASCADE,
        related_name="status_updates",
    )
    old_status = models.CharField(max_length=10, blank=True)
    new_status = models.CharField(max_length=10)
    note = models.TextField(blank=True)
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="status_updates",
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timestamp"]

    def __str__(self):
        return f"{self.issue_id}: {self.old_status} -> {self.new_status}"


class Upvote(models.Model):
    issue = models.ForeignKey(
        Issue,
        on_delete=models.CASCADE,
        related_name="upvotes",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="upvotes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["issue", "user"], name="unique_issue_user_upvote"
            ),
        ]

    def __str__(self):
        return f"{self.user_id} @ issue {self.issue_id}"