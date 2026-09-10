import logging

from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)


def send_invite_email(inviter, email, group, token):
    """
    Returns (ok, error_message). error_message is the real reason the send
    failed (e.g. an SMTP auth error), so callers can show something more
    useful than a generic "failed to send" — it's also logged server-side
    either way.
    """
    invite_url = "{}/register/?invite={}".format(
        getattr(settings, 'APP_URL', 'http://localhost:8000'), token)
    subject = "{} invited you to join \"{}\" on WorthKeeping".format(
        inviter.first_name, group.name)
    body = (
        "Hi!\n\n"
        "{} {} has invited you to join the memory board "
        "\"{}\" on WorthKeeping.\n\n"
        "Click the link below to create your free account and join:\n{}\n\n"
        "This link will add you directly to the board when you register.\n\n"
        "-- The WorthKeeping team"
    ).format(inviter.first_name, inviter.last_name, group.name, invite_url)
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [email])
        return True, None
    except Exception as e:
        logger.exception("Failed to send invite email to %s for group %s", email, group.pk)
        return False, str(e)


def send_friend_invite_email(inviter, email, token):
    """
    Like send_invite_email, but for a friend invite rather than a board
    invite — the recipient doesn't have a WorthKeeping account yet, so we email
    them a registration link. They become friends with `inviter`
    automatically once they sign up with this email address.
    Returns (ok, error_message).
    """
    invite_url = "{}/register/?invite={}".format(
        getattr(settings, 'APP_URL', 'http://localhost:8000'), token)
    subject = "{} wants to add you as a friend on WorthKeeping".format(inviter.first_name)
    body = (
        "Hi!\n\n"
        "{} {} uses WorthKeeping to keep shared memories with friends, and wants "
        "to add you as a friend there.\n\n"
        "Click the link below to create your free account — you'll be "
        "connected as friends automatically as soon as you sign up:\n{}\n\n"
        "-- The WorthKeeping team"
    ).format(inviter.first_name, inviter.last_name, invite_url)
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [email])
        return True, None
    except Exception as e:
        logger.exception("Failed to send friend invite email to %s from user %s", email, inviter.pk)
        return False, str(e)


def send_notification_email(user, subject, body):
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email])
        return True
    except Exception:
        return False


def send_weekly_digest_email(user, memories):
    if not memories:
        return False
    app_url = getattr(settings, 'APP_URL', 'http://localhost:8000')
    lines = ["Here's what happened on your boards this week:\n"]
    for m in memories[:10]:
        lines.append("* {}: {}".format(m.group.name, m.title or m.content[:60]))
    lines.append("\n\nVisit WorthKeeping to see more: {}".format(app_url))
    body = "\n".join(lines)
    return send_notification_email(user, "Your WorthKeeping weekly digest", body)


def send_problem_report_email(user, message):
    """Sends a user's 'Report a problem' message to the site's support
    inbox (settings.REPORT_PROBLEM_EMAIL), not to the user themselves.
    Returns (ok, error_message).
    """
    to_email = getattr(settings, 'REPORT_PROBLEM_EMAIL', None)
    if not to_email:
        return False, "No report recipient configured."
    subject = "WorthKeeping problem report from {} {}".format(user.first_name, user.last_name)
    body = (
        "{} {} ({}) reported a problem on WorthKeeping:\n\n"
        "{}\n"
    ).format(user.first_name, user.last_name, user.email, message)
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to_email])
        return True, None
    except Exception as e:
        logger.exception("Failed to send problem report email from user %s", user.pk)
        return False, str(e)


def send_password_reset_email(user, reset_url):
    subject = "Reset your WorthKeeping password"
    body = (
        "Hi {},\n\n"
        "We received a request to reset your WorthKeeping password.\n\n"
        "Click the link below to set a new password:\n{}\n\n"
        "This link expires in 24 hours. If you did not request this, you can ignore this email.\n\n"
        "-- The WorthKeeping team"
    ).format(user.first_name, reset_url)
    return send_notification_email(user, subject, body)
