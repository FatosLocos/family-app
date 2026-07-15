from django.conf import settings
from django.db import models

from households.code_utils import generate_invite_code, hash_invite_code


class Household(models.Model):
    name = models.CharField(max_length=160)
    invite_only = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class Membership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Eigenaar"
        PARENT = "parent", "Ouder"
        CHILD = "child", "Kind"

    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.CHILD)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("household", "user"), name="unique_household_member")]

    @property
    def can_manage(self) -> bool:
        return self.role in {self.Role.OWNER, self.Role.PARENT}


class ChildProfile(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="child_profiles")
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="child_profile")
    date_of_birth = models.DateField(null=True, blank=True)
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)
    color = models.CharField(max_length=7, default="#3B82F6")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("household", "user"), name="unique_child_in_household")]

    def __str__(self) -> str:
        return f"{self.user.display_name or self.user.get_full_name()} ({self.household.name})"

    @property
    def age(self) -> int | None:
        if not self.date_of_birth:
            return None
        from datetime import date
        today = date.today()
        return today.year - self.date_of_birth.year - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))


class HouseholdInvite(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="invites")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=16, choices=Membership.Role.choices, default=Membership.Role.CHILD)
    label = models.CharField(max_length=120, blank=True)
    code_hash = models.CharField(max_length=64, unique=True, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="accepted_invites")
    created_at = models.DateTimeField(auto_now_add=True)

    _plain_code = None  # Temporary storage for the plain code before hashing

    def save(self, *args, **kwargs):
        if not self.code_hash:
            code = generate_invite_code()
            self.code_hash = hash_invite_code(code)
            self._plain_code = code  # Store for later retrieval
        super().save(*args, **kwargs)

    @classmethod
    def create_with_code(cls, household, created_by, role, label="", expires_at=None):
        """Create invite and return both the invite and plain code."""
        code = generate_invite_code()
        invite = cls(
            household=household,
            created_by=created_by,
            role=role,
            label=label,
            expires_at=expires_at,
            code_hash=hash_invite_code(code),
        )
        invite.save()
        invite._plain_code = code
        return invite, code
