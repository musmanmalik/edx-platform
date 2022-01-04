"""
Decorators that can be used to interact with third_party_auth.
"""


from functools import wraps

from django.conf import settings
from django.shortcuts import redirect
from django.utils.decorators import available_attrs
from six.moves.urllib.parse import urlencode, urlparse, urlunparse

from third_party_auth.models import LTIProviderConfig, SAMLProviderData
from third_party_auth.provider import Registry
from edx_solutions_organizations.models import WhitelistedUrls


def allow_frame_from_whitelisted_url(view_func):  # pylint: disable=invalid-name
    """
    Modifies a view function so that it can be rendered in a frame or iframe
    if parent url is whitelisted and request HTTP referrer is matches one of SAML providers's sso url.
    """

    def wrapped_view(request, *args, **kwargs):
        """ Modify the response with the correct X-Frame-Options and . """
        resp = view_func(request, *args, **kwargs)
        x_frame_option = 'DENY'
        content_security_policy = "frame-ancestors 'none'"

        if settings.FEATURES['ENABLE_THIRD_PARTY_AUTH']:
            referer = request.META.get('HTTP_REFERER')
            if referer is not None:
                parsed_url = urlparse(referer)
                # reconstruct a referer url without querystring and trailing slash
                referer_url = urlunparse(
                    (parsed_url.scheme, parsed_url.netloc, parsed_url.path.rstrip('/'), '', '', '')
                )
                sso_urls = SAMLProviderData.objects.values_list('sso_url', flat=True)
                sso_urls = [url.rstrip('/') for url in sso_urls]
                if referer_url in sso_urls:
                    internal_allowed_urls = [url.url for url in WhitelistedUrls.objects.all()]
                    allowed_urls = ' '.join(settings.THIRD_PARTY_AUTH_FRAME_ALLOWED_FROM_URL + internal_allowed_urls)
                    x_frame_option = 'ALLOW-FROM {}'.format(allowed_urls)
                    content_security_policy = "frame-ancestors {}".format(allowed_urls)
        resp['X-Frame-Options'] = x_frame_option
        resp['Content-Security-Policy'] = content_security_policy
        return resp
    return wraps(view_func, assigned=available_attrs(view_func))(wrapped_view)


def xframe_allow_whitelisted(view_func):
    """
    Modifies a view function so that its response has the X-Frame-Options HTTP header
    set to 'DENY' if the request HTTP referrer is not from a whitelisted hostname.
    """

    def wrapped_view(request, *args, **kwargs):
        """ Modify the response with the correct X-Frame-Options. """
        resp = view_func(request, *args, **kwargs)
        x_frame_option = 'DENY'
        if settings.FEATURES['ENABLE_THIRD_PARTY_AUTH']:
            referer = request.META.get('HTTP_REFERER')
            if referer is not None:
                parsed_url = urlparse(referer)
                hostname = parsed_url.hostname
                if LTIProviderConfig.objects.current_set().filter(lti_hostname=hostname, enabled=True).exists():
                    x_frame_option = 'ALLOW'
        resp['X-Frame-Options'] = x_frame_option
        return resp
    return wraps(view_func, assigned=available_attrs(view_func))(wrapped_view)
