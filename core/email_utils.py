from django.core.mail import send_mail
from django.conf import settings


def send_invite_email(inviter, email, group, token):
    invite_url = "{}/register/?invite={}".format(
        getattr(settings, 'APP_URL', 'http://localhost:8000'), token)
    subject = "{} invited you to join \"{}\" on Memboard".format(
        inviter.first_name, group.name)
    body = (
        "Hi!\n\n"
        "{} {} has invited you to join the memory board "
        "\"{}\" on Memboard.\n\n"
        "Click the link below to create your free account and join:\n{}\n\n"
        "This link will add you directly to the board when you register.\n\n"
        "-- The Memboard team"
    ).format(inviter.first_name, inviter.last_name, group.name, invite_url)
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [email])
        return True
    except Exception:
        return False


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
    lines.append("\n\nVisit Memboard to see more: {}".format(app_url))
    body = "\n".join(lines)
    return send_notification_email(user, "Your Memboard weekly digest", body)


def send_password_reset_email(user, reset_url):
    subject = "Reset your Memboard password"
    body = (
        "Hi {},\n\n"
        "We received a request to reset your Memboard password.\n\n"
        "Click the link below to set a new password:\n{}\n\n"
        "This link expires in 24 hours. If you did not request this, you can ignore this email.\n\n"
        "-- The Memboard team"
    ).format(user.first_name, reset_url)
    return send_notification_email(user, subject, body)
