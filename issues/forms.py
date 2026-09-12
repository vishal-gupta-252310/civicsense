"""Django forms for registration and issue reporting."""

import json
import time

from django import forms
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.forms import (
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)
from django.contrib.auth.models import User
from django.core.cache import cache
from urllib.parse import urlsplit

from .models import Issue

LOGIN_FAILURE_LIMIT = 5
LOGIN_IP_FAILURE_LIMIT = 20
LOGIN_FAILURE_WINDOW = 900  # seconds


class EmailLoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "you@example.com",
                "required": True,
                "autocomplete": "email",
            }
        )
    )
    password = forms.CharField(
        min_length=1,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "••••••••",
                "required": True,
                "minlength": 1,
                "autocomplete": "current-password",
            }
        )
    )

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        # True when this submission is refused due to rate-limiting (the view
        # turns it into an HTTP 429 so the lockout is observable, not just an
        # error message on an otherwise-200 response).
        self.lockout = False

    def _client_ip(self):
        meta = self.request.META if self.request else {}
        return meta.get("REMOTE_ADDR", "") or ""

    @staticmethod
    def _read(key):
        raw = cache.get(key)
        if raw:
            try:
                return json.loads(raw)
            except (TypeError, ValueError):
                return None
        return None

    @staticmethod
    def _write(key, count, start):
        cache.set(key, json.dumps({"count": count, "start": start}),
                  timeout=LOGIN_FAILURE_WINDOW)

    def _record_failure(self, ip, email):
        now = time.time()
        for key in (
            f"civicsense:login:{ip}",
            f"civicsense:login:{ip}:{email}",
        ):
            rec = self._read(key)
            self._write(key, (rec or {}).get("count", 0) + 1, (rec or {}).get("start", now))

    def _clear_failures(self, ip, email):
        cache.delete(f"civicsense:login:{ip}")
        cache.delete(f"civicsense:login:{ip}:{email}")

    def _lockout_minutes(self, ip, email):
        now = time.time()
        for key, limit in (
            (f"civicsense:login:{ip}:{email}", LOGIN_FAILURE_LIMIT),
            # Bare-IP limit sits higher: in production REMOTE_ADDR is the
            # reverse-proxy IP shared by all users, so a low global threshold
            # would let one attacker lock out the whole site.
            (f"civicsense:login:{ip}", LOGIN_IP_FAILURE_LIMIT),
        ):
            rec = self._read(key)
            if rec and rec.get("count", 0) >= limit:
                elapsed = now - rec.get("start", now)
                if elapsed < LOGIN_FAILURE_WINDOW:
                    return max(1, int((LOGIN_FAILURE_WINDOW - elapsed) // 60) + 1)
        return 0

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("email", "").strip().lower()
        password = cleaned.get("password")
        if not email or not password:
            # Field-level errors already render; don't count empty/spam submits
            # as failed authentication attempts.
            return cleaned
        ip = self._client_ip()
        minutes = self._lockout_minutes(ip, email)
        if minutes:
            self.lockout = True
            raise forms.ValidationError(
                "Too many failed sign-in attempts. "
                f"Try again in {minutes} minute{'s' if minutes != 1 else ''}."
            )
        user = None
        try:
            user = User.objects.get(email=email)
        except (User.DoesNotExist, User.MultipleObjectsReturned):
            # Same generic message for both failure modes so the login page never
            # reveals which email addresses are registered.
            self._record_failure(ip, email)
            raise forms.ValidationError("Please enter a correct email and password.")
        auth_user = authenticate(username=user.username, password=password)
        if auth_user is None:
            self._record_failure(ip, email)
            raise forms.ValidationError("Please enter a correct email and password.")
        self._clear_failures(ip, email)
        cleaned["user"] = auth_user
        return cleaned


class CivicPasswordResetForm(PasswordResetForm):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "you@example.com",
                "required": True,
                "autocomplete": "email",
            }
        )
    )

    def save(self, **kwargs):
        request = kwargs.get("request")
        site_url = urlsplit(settings.SITE_URL)
        host = request.get_host() if request else ""
        hostname = urlsplit("//" + host).hostname.lower() if host else ""
        if hostname in ("localhost", "127.0.0.1", "::1"):
            # Local dev: the reset link points back at the local server.
            kwargs["domain_override"] = host
            kwargs["use_https"] = False
        else:
            # Production: always use the public SITE_URL, never an internal host.
            kwargs["domain_override"] = site_url.netloc
            kwargs["use_https"] = site_url.scheme == "https"
        return super().save(**kwargs)


class CivicSetPasswordForm(SetPasswordForm):
    new_password1 = forms.CharField(
        label="New password",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "New password",
                "required": True,
                "autocomplete": "new-password",
            }
        ),
    )
    new_password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Confirm password",
                "required": True,
                "autocomplete": "new-password",
            }
        ),
    )


class RegisterForm(UserCreationForm):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "you@example.com",
                "required": True,
                "autocomplete": "email",
            }
        )
    )
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Choose a username",
                "required": True,
                "maxlength": 150,
                "autocomplete": "username",
            }
        ),
    )
    password1 = forms.CharField(
        label="Password",
        min_length=8,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "••••••••",
                "required": True,
                "minlength": 8,
                "autocomplete": "new-password",
            }
        ),
    )
    password2 = forms.CharField(
        label="Confirm password",
        min_length=8,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "••••••••",
                "required": True,
                "minlength": 8,
                "autocomplete": "new-password",
            }
        ),
    )

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account already exists for that email.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_staff = False
        if commit:
            user.save()
            from .models import UserProfile
            UserProfile.objects.create(user=user, role="citizen")
        return user


class ReportIssueForm(forms.ModelForm):
    MAX_PHOTO_SIZE = 5 * 1024 * 1024  # 5 MB

    class Meta:
        model = Issue
        fields = ["description", "address", "photo", "latitude", "longitude"]
        widgets = {
            "address": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. MG Road, near City Mall",
                    "maxlength": 255,
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Describe the problem, e.g. a pothole near the school gate…",
                    "required": True,
                    "minlength": 10,
                    "maxlength": 2000,
                }
            ),
            "photo": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "latitude": forms.HiddenInput(),
            "longitude": forms.HiddenInput(),
        }

    def clean_description(self):
        desc = self.cleaned_data.get("description", "").strip()
        if len(desc) < 10:
            raise forms.ValidationError("Description must be at least 10 characters.")
        if len(desc) > 2000:
            raise forms.ValidationError("Description must be at most 2000 characters.")
        return desc

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and hasattr(photo, "size"):
            if photo.size > self.MAX_PHOTO_SIZE:
                raise forms.ValidationError("Photo must be under 5 MB.")
        return photo

    def clean(self):
        cleaned = super().clean()
        latitude = cleaned.get("latitude")
        longitude = cleaned.get("longitude")
        if latitude is None or longitude is None:
            raise forms.ValidationError(
                "Location permission is required to report an issue."
            )
        return cleaned


class StatusUpdateForm(forms.Form):
    new_status = forms.ChoiceField(
        choices=Issue.STATUS,
        label="New status",
        widget=forms.Select(
            attrs={"required": True, "class": "form-select"}
        ),
    )
    note = forms.CharField(
        required=False,
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "class": "form-control",
                "placeholder": "Optional note",
                "maxlength": 1000,
            }
        ),
    )