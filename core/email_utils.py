from django.core.mail import send_mail
from django.conf import settings


def send_invite_email(inviter, email, group, token):
    invite_url = f"{getattr(settings, 'APP_URL', 'http://localhost:8000')}/register/?invite={token}"
    subject = f"{inviter.first_name} invited you to join "{group.name}" on Memboard"
    body = (
        f"Hi!\n\n"
        f"{inviter.first_name} {inviter.last_name} has invited you to join the memory board "
        f""{group.name}" on Memboard.\n\n"
        f"Click the link below to create your free account and join:\n{invite_url}\n\n"
        f"This link will add you directly to the board when you register.\n\n"
        f"— The Memboard team"
    )
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
    lines = [f"Here's what happened on your boards this week:\n"]
    for m in memories[:10]:
        lines.append(f"• {m.group.name}: {m.title or m.content[:60]}")
    lines.append(f"\n\nVisit Memboard to see more: {getattr(settings, 'APP_URL', 'http://localhost:8000')}")
    body = "\n".join(lines)
    return send_notification_email(user, "Your Memboard weekly digest 📸", body)


def send_password_reset_email(user, reset_url):
    subject = "Reset your Memboard password"
    body = (
        f"Hi {user.first_name},\n\n"
        f"We received a request to reset your Memboard password.\n\n"
        f"Click the link below to set a new password:\n{reset_url}\n\n"
        f"This link expires in 24 hours. If you didn't request this, you can ignore this email.\n\n"
        f"— The Memboard team"
    )
    return send_notification_email(user, subject, body)
