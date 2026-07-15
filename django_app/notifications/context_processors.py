from django.conf import settings


def webpush_context(request):
    return {"webpush_vapid_key": settings.WEBPUSH_VAPID_PUBLIC_KEY}
