from django.conf import settings
from django.utils import translation


class ProfileLanguageMiddleware:
    """Overrides whatever LocaleMiddleware just activated (from the
    language cookie or the browser's Accept-Language header) with the
    signed-in user's saved profile.language, so it's remembered on every
    device they log into — mirrors how theme/note_font already work. Must
    sit AFTER LocaleMiddleware (this overrides its decision) and after
    AuthenticationMiddleware (needs request.user).

    This Django version's language detection is cookie-based only — it
    doesn't check the session — so the override is also written back as the
    language cookie, keeping the next request (and any pre-login page)
    consistent with it too.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        lang = None
        user = getattr(request, 'user', None)
        if user is not None and getattr(user, 'is_authenticated', False):
            profile = getattr(user, 'profile', None)
            if profile is not None:
                lang = profile.language
                if lang != translation.get_language():
                    translation.activate(lang)
                    request.LANGUAGE_CODE = lang

        response = self.get_response(request)

        if lang:
            response.set_cookie(settings.LANGUAGE_COOKIE_NAME, lang)
        return response
