from django.conf import settings


class ContentSecurityPolicyMiddleware:
    """Add Content-Security-Policy headers based on Django settings."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        csp_directives = []
        csp_config = {
            'default-src': getattr(settings, 'CSP_DEFAULT_SRC', ("'self'",)),
            'script-src': getattr(settings, 'CSP_SCRIPT_SRC', ("'self'",)),
            'style-src': getattr(settings, 'CSP_STYLE_SRC', ("'self'",)),
            'font-src': getattr(settings, 'CSP_FONT_SRC', ("'self'",)),
            'img-src': getattr(settings, 'CSP_IMG_SRC', ("'self'",)),
            'connect-src': getattr(settings, 'CSP_CONNECT_SRC', ("'self'",)),
            'frame-ancestors': getattr(settings, 'CSP_FRAME_ANCESTORS', ("'none'",)),
            'base-uri': getattr(settings, 'CSP_BASE_URI', ("'self'",)),
            'form-action': getattr(settings, 'CSP_FORM_ACTION', ("'self'",)),
        }

        for directive, sources in csp_config.items():
            if sources:
                csp_directives.append(f"{directive} {' '.join(sources)}")

        if csp_directives:
            response['Content-Security-Policy'] = '; '.join(csp_directives)

        return response
