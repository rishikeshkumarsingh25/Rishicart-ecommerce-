import logging
from django.core.mail import send_mail
from django.conf import settings
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages

logger = logging.getLogger(__name__)


def admin_required(view_func):
    """
    Decorator to restrict access ONLY to staff and superusers.
    Regular logged-in users are redirected to the storefront home page with an alert.
    Unauthenticated users are redirected to the login page.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.info(request, "Please log in with your administrator account.")
            return redirect(f"/login/?next={request.path}")
        if not (request.user.is_staff or request.user.is_superuser):
            messages.error(request, "Access Denied: The dashboard is restricted to administrators only. You are logged in as a store customer.")
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def mask_email(email):
    """
    Mask an email for privacy display.
    Example: rishikesh@gmail.com -> r***h@gmail.com
    """
    if not email or '@' not in email:
        return email
    username, domain = email.split('@', 1)
    if len(username) <= 2:
        masked_user = username[0] + '*'
    else:
        masked_user = username[0] + ('*' * (len(username) - 2)) + username[-1]
    return f"{masked_user}@{domain}"


def send_otp_email(email, otp, purpose='login'):
    """
    Sends an OTP verification email to the user.
    Supports both HTML and plain-text formats.
    """
    action_text = "log in to your RishiCart account" if purpose == 'login' else "verify your email and complete your registration"
    subject = f"Your RishiCart Verification Code: {otp}"

    html_message = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>{subject}</title>
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f1f3f6; margin: 0; padding: 24px; }}
        .container {{ max-width: 540px; margin: 0 auto; background: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 16px rgba(0,0,0,0.1); border: 1px solid #e2e8f0; }}
        .header {{ background: #2874f0; padding: 28px 24px; text-align: center; color: #ffffff; }}
        .header h1 {{ margin: 0; font-size: 26px; font-weight: 800; letter-spacing: 0.5px; }}
        .header p {{ margin: 6px 0 0; font-size: 14px; opacity: 0.9; }}
        .content {{ padding: 32px 28px; color: #212121; }}
        .welcome {{ font-size: 16px; margin-bottom: 12px; }}
        .desc {{ font-size: 14px; color: #555555; line-height: 1.6; margin-bottom: 24px; }}
        .otp-box {{ background: #f0f6ff; border: 2px dashed #2874f0; border-radius: 8px; text-align: center; padding: 20px; margin: 24px 0; }}
        .otp-code {{ font-size: 38px; font-weight: 800; color: #2874f0; letter-spacing: 10px; font-family: monospace; display: inline-block; }}
        .validity {{ font-size: 13px; color: #e65100; font-weight: 600; margin-top: 10px; }}
        .security {{ background: #fff8e1; border-left: 4px solid #ffa000; padding: 12px 16px; border-radius: 4px; font-size: 12px; color: #6d4c41; line-height: 1.5; margin: 20px 0; }}
        .footer {{ background: #fafafa; border-top: 1px solid #eeeeee; padding: 18px 24px; text-align: center; font-size: 12px; color: #878787; }}
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <h1>RishiCart</h1>
          <p>Online Shopping Portal</p>
        </div>
        <div class="content">
          <div class="welcome">Hello,</div>
          <p class="desc">Please use the verification code below to {action_text}:</p>
          <div class="otp-box">
            <div class="otp-code">{otp}</div>
            <div class="validity">⏳ Valid for 10 minutes only</div>
          </div>
          <div class="security">
            <strong>Security Warning:</strong> Never share this OTP with anyone, including RishiCart support or executives. If you did not request this code, please ignore this email.
          </div>
        </div>
        <div class="footer">
          &copy; RishiCart India. All rights reserved.<br>
          This is an automated notification. Please do not reply directly to this email.
        </div>
      </div>
    </body>
    </html>
    """

    plain_message = f"""
RishiCart Verification Code
============================
Hello,

Your verification code to {action_text} is:

    {otp}

This code is valid for 10 minutes.
Security Notice: Never share this OTP with anyone.

Thank you,
Team RishiCart
"""

    # Always log OTP in terminal/console so development and testing is seamless
    print(f"\n=======================================================")
    print(f" [RishiCart OTP] To: {email} | Code: {otp} | Purpose: {purpose}")
    print(f"=======================================================\n")

    smtp_user = getattr(settings, 'EMAIL_HOST_USER', '').strip()
    smtp_pass = getattr(settings, 'EMAIL_HOST_PASSWORD', '').strip()
    is_real_smtp = bool(smtp_user and smtp_pass)

    try:
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'RishiCart <noreply@rishicart.com>'
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=[email],
            html_message=html_message,
            fail_silently=False
        )
        if not is_real_smtp:
            return False, "SMTP (EMAIL_HOST_USER) not configured in .env; printed to console instead"
        logger.info(f"OTP successfully sent to {email}")
        return True, None
    except Exception as e:
        logger.error(f"Failed to send email to {email}: {e}")
        return False, str(e)
