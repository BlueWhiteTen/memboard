"""
Custom Django email backend that sends via the Resend HTTP API
(https://resend.com) instead of SMTP.

Why: our droplet's hosting provider blocks outbound SMTP (port 587), so
Django's built-in SMTP backend just hangs trying to connect to Gmail until
gunicorn's worker timeout kills the whole request. Resend's API is a plain
HTTPS POST (port 443), which isn't blocked, so this sidesteps the problem
entirely — and since Django routes *all* mail (our own invite emails, and
the built-in password-reset flow) through whatever EMAIL_BACKEND is
configured, switching it here fixes both without touching the call sites.
"""
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

RESEND_API_URL = 'https://api.resend.com/emails'


class ResendEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        api_key = getattr(settings, 'RESEND_API_KEY', '')
        if not api_key:
            if not self.fail_silently:
                raise ValueError(
                    "RESEND_API_KEY is not set — add it to your .env to send email.")
            return 0

        default_from = getattr(settings, 'RESEND_FROM_EMAIL', 'onboarding@resend.dev')
        sent_count = 0

        for message in email_messages:
            payload = {
                'from':    message.from_email or default_from,
                'to':      list(message.to),
                'subject': message.subject,
                'text':    message.body,
            }
            if message.cc:
                payload['cc'] = list(message.cc)
            if message.bcc:
                payload['bcc'] = list(message.bcc)
            if message.reply_to:
                payload['reply_to'] = list(message.reply_to)

            try:
                data = json.dumps(payload).encode('utf-8')
                req = urllib.request.Request(
                    RESEND_API_URL, data=data, method='POST',
                    headers={
                        'Authorization': f'Bearer {api_key}',
                        'Content-Type':  'application/json',
                        'Accept':        'application/json',
                        # Resend's API sits behind Cloudflare, which blocks
                        # urllib's default "Python-urllib/x.y" User-Agent as
                        # bot traffic (Cloudflare error 1010) — a normal
                        # browser-looking one avoids that.
                        'User-Agent':    'Mozilla/5.0 (compatible; Memboard/1.0)',
                    },
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    resp.read()
                sent_count += 1
            except urllib.error.HTTPError as e:
                body = e.read().decode('utf-8', errors='replace')
                logger.exception("Resend API error %s sending to %s: %s", e.code, message.to, body)
                if not self.fail_silently:
                    raise RuntimeError(f"Resend API error {e.code}: {body}") from e
            except Exception as e:
                logger.exception("Failed to send email via Resend to %s", message.to)
                if not self.fail_silently:
                    raise RuntimeError(f"Failed to reach Resend: {e}") from e

        return sent_count
