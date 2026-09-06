"""Django forms for registration and issue reporting."""

from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Issue

ROLE_CHOICES = [
    ("citizen", "Citizen"),
    ("admin", "Administrator"),
]


class EmailLoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "you@example.com",
                "required": True,
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
            }
        )
    )

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("email", "").strip().lower()
        password = cleaned.get("password")
        user = None
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise forms.ValidationError("No account found for that email address.")
        auth_user = authenticate(username=user.username, password=password)
        if auth_user is None:
            raise forms.ValidationError("Incorrect password.")
        cleaned["user"] = auth_user
        return cleaned


class RegisterForm(UserCreationForm):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "you@example.com",
                "required": True,
            }
        )
    )
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        initial="citizen",
        widget=forms.Select(attrs={"class": "form-select", "required": True}),
    )
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Choose a username",
                "required": True,
                "maxlength": 150,
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
            }
        ),
    )

    class Meta:
        model = User
        fields = ["username", "email", "role", "password1", "password2"]

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            from .models import UserProfile
            UserProfile.objects.create(user=user, role=self.cleaned_data["role"])
            if self.cleaned_data["role"] == "admin":
                user.is_staff = True
                user.save()
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
        widget=forms.Select(attrs={"required": True}),
    )
    note = forms.CharField(
        required=False,
        max_length=1000,
        widget=forms.Textarea(
            attrs={"rows": 2, "placeholder": "Optional note", "maxlength": 1000}
        ),
    )