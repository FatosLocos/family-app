from django.db.models.signals import post_save
from django.dispatch import receiver

from households.models import Membership, ChildProfile


@receiver(post_save, sender=Membership)
def auto_create_child_profile(sender, instance, created, **kwargs):
    if created and instance.role == Membership.Role.CHILD:
        ChildProfile.objects.get_or_create(
            household=instance.household,
            user=instance.user,
            defaults={"color": "#3B82F6"}
        )
