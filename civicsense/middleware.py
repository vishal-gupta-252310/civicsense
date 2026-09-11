"""Security response headers middleware (Content-Security-Policy).

Inline scripts/styles are allowed because the templates rely on them;
everything else is locked down to same-origin plus the external origins the
templates actually use (Bootstrap, Leaflet, Chart.js, cloudinary, CARTO map
tiles, reverse-geocoding and IP-lookup endpoints).
"""

_CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com",
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com",
        "img-src 'self' data: blob: https://res.cloudinary.com https://unpkg.com https://*.basemaps.cartocdn.com",
        "font-src 'self' data: https://cdn.jsdelivr.net",
        "connect-src 'self' https://nominatim.openstreetmap.org https://ipwho.is",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
        "object-src 'none'",
        "upgrade-insecure-requests",
    ]
)


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["Content-Security-Policy"] = _CSP
        return response