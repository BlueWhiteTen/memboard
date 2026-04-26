from django.core.mail import send_mail
from django.conf import settings


def send_invite_email(invited_by, email, group, token):
    """
    Send a Memboard group invitation email to someone who isn't registered yet.
    """
    inviter   = invited_by.username
    group_name = group.name
    signup_url = f"http://127.0.0.1:8000/register/?invite={token}"

    subject = f"{inviter} invited you to join Memboard"

    message = f"""Hi there!

{inviter} has invited you to join their board "{group_name}" on Memboard — a place to save shared memories with friends.

Click the link below to create your free account and join the board:

{signup_url}

Once you sign up with this email address ({email}), you'll be automatically added to "{group_name}".

See you there!
— The Memboard team
"""

    html_message = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: 'DM Sans', Arial, sans-serif; background: #F7F3EC; margin: 0; padding: 40px 20px; }}
    .card {{ background: #FDFAF5; border-radius: 16px; max-width: 480px; margin: 0 auto; padding: 40px; border: 1px solid rgba(44,36,23,0.12); }}
    .logo {{ font-size: 22px; font-weight: 600; color: #2C2417; margin-bottom: 28px; }}
    .logo span {{ color: #C97B2A; }}
    h1 {{ font-size: 20px; color: #2C2417; margin: 0 0 12px; font-weight: 600; }}
    p {{ color: #6B5E4A; font-size: 15px; line-height: 1.6; margin: 0 0 16px; }}
    .board-chip {{ display: inline-block; background: #F5E8D0; color: #C97B2A; border-radius: 8px; padding: 6px 14px; font-size: 14px; font-weight: 500; margin: 4px 0 20px; }}
    .btn {{ display: block; background: #2C2417; color: #FDFAF5 !important; text-decoration: none; padding: 14px 28px; border-radius: 10px; font-size: 15px; font-weight: 500; text-align: center; margin: 24px 0; }}
    .footer {{ font-size: 12px; color: #9D8E7A; margin-top: 28px; padding-top: 20px; border-top: 1px solid rgba(44,36,23,0.1); }}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">Mem<span>board</span></div>
    <h1>{inviter} invited you to join a board</h1>
    <p>You've been invited to <strong>"{group_name}"</strong> — a shared memory board on Memboard.</p>
    <div class="board-chip">📌 {group_name}</div>
    <p>Create your free account and you'll be added to the board automatically.</p>
    <a href="{signup_url}" class="btn">Accept invitation &amp; sign up</a>
    <p style="font-size:13px;">Or copy this link into your browser:<br>
      <span style="color:#C97B2A;">{signup_url}</span>
    </p>
    <div class="footer">
      This invite was sent to {email} by {inviter}.<br>
      If you didn't expect this, you can ignore it.
    </div>
  </div>
</body>
</html>
"""

    try:
        send_mail(
            subject        = subject,
            message        = message,
            from_email     = settings.DEFAULT_FROM_EMAIL,
            recipient_list = [email],
            html_message   = html_message,
            fail_silently  = False,
        )
        return True
    except Exception as e:
        print(f"[Memboard] Email send failed: {e}")
        return False
