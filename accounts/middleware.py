from django.shortcuts import redirect
from django.urls import reverse


class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        allowed_urls = [
            reverse("login"),
            reverse("logout"),
            "/admin/login/",
            "/admin/logout/",
        ]

        # Allow admin static
        if request.path.startswith("/static/"):
            return self.get_response(request)

        if request.path.startswith("/media/"):
            return self.get_response(request)

        if request.path.startswith("/admin/"):
            return self.get_response(request)

        if not request.user.is_authenticated and request.path not in allowed_urls:
            return redirect("login")

        return self.get_response(request)
