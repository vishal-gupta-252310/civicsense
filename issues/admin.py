from django.contrib import admin

from .models import Category, Issue, StatusUpdate, Upvote, UserProfile


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


class StatusUpdateInline(admin.TabularInline):
    model = StatusUpdate
    extra = 0
    readonly_fields = ("old_status", "new_status", "note", "staff", "timestamp")


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "category",
        "ai_priority",
        "status",
        "reporter",
        "created_at",
        "duplicate_of",
    )
    list_filter = ("status", "ai_priority", "category")
    search_fields = ("description", "ai_summary")
    readonly_fields = ("created_at", "ai_priority", "ai_summary")
    inlines = (StatusUpdateInline,)


@admin.register(StatusUpdate)
class StatusUpdateAdmin(admin.ModelAdmin):
    list_display = ("issue", "old_status", "new_status", "staff", "timestamp")
    readonly_fields = ("old_status", "new_status", "note", "staff", "timestamp")


@admin.register(Upvote)
class UpvoteAdmin(admin.ModelAdmin):
    list_display = ("issue", "user", "created_at")
    search_fields = ("issue__description",)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role")
    list_filter = ("role",)