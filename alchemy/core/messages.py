"""
alchemy.core.messages
======================
Centralized business messages — edit this file to customize any message
shown to users. All keys follow the pattern SECTION_CONTEXT_STATE.

HOW TO CUSTOMIZE:
    Simply change any string value below. Messages support {placeholders}
    using Python .format() — available vars are shown in comments.

    To add a new message:
        1. Add a key here
        2. Use MSG.get("your_key", "fallback") in your route
"""

MSG: dict[str, str] = {

    # ── Authentication ────────────────────────────────────────────────────
    "auth_login_success":
        "Welcome back, {name}! You are now signed in.",

    "auth_login_invalid":
        "Incorrect email or password. Please try again.",

    "auth_login_locked":
        "Your account is temporarily locked after too many failed attempts. "
        "Please try again in 15 minutes or contact support.",

    "auth_login_banned":
        "Your account has been suspended. Please contact support for assistance.",

    "auth_login_pending":
        "Your account is pending email verification. "
        "Please check your inbox for the verification link.",

    "auth_login_rate_limited":
        "Too many sign-in attempts. Please wait {retry_after} seconds before trying again.",

    # ── Signup ────────────────────────────────────────────────────────────
    "auth_signup_success":
        "Welcome to Alchemy, {name}! Your account is ready.",

    "auth_signup_email_taken":
        "An account with this email address already exists. "
        "Please sign in or use a different email.",

    "auth_signup_username_taken":
        "The username '{username}' is already taken. Please choose another.",

    "auth_signup_username_invalid":
        "Username must be 3–32 characters using only letters, numbers, and underscores. "
        "Spaces and special characters are not allowed.",

    "auth_signup_password_weak":
        "Password is too weak. Use at least 12 characters with uppercase, "
        "lowercase, numbers, and a special character (!@#$%^&*).",

    "auth_signup_server_error":
        "We could not create your account at this time. "
        "Please try again in a moment. If the problem persists, contact support.",

    # ── Password ──────────────────────────────────────────────────────────
    "auth_password_changed":
        "Your password has been updated successfully.",

    "auth_password_wrong_current":
        "The current password you entered is incorrect.",

    "auth_password_same_as_old":
        "Your new password cannot be the same as your current password.",

    # ── OTP / 2FA ─────────────────────────────────────────────────────────
    "otp_sent":
        "A 6-digit verification code has been sent to {email}. "
        "It expires in 10 minutes.",

    "otp_sent_dev":
        "SMTP not configured — your OTP code is: {otp} (development mode only)",

    "otp_invalid":
        "The code you entered is incorrect or has expired. "
        "Please request a new code and try again.",

    "otp_verified":
        "Email verified successfully. You can now sign in.",

    "totp_enabled":
        "Two-factor authentication has been enabled on your account. "
        "Keep your authenticator app safe — you will need it to sign in.",

    "totp_disabled":
        "Two-factor authentication has been disabled. "
        "You can re-enable it at any time in Settings.",

    "totp_invalid_code":
        "The authenticator code is incorrect. "
        "Make sure your device time is synced and try again.",

    "totp_setup_expired":
        "The 2FA setup session expired. Please start the setup process again.",

    # ── Exchange / Tokens ─────────────────────────────────────────────────
    "token_saved":
        "{exchange} credentials saved and encrypted successfully.",

    "token_deleted":
        "{exchange} credentials removed from your account.",

    "token_not_found":
        "No credentials found for {exchange}. Please connect this exchange first.",

    "token_test_success_paper":
        "{exchange} connected in paper mode. Live BTC price: ${price:,.2f}",

    "token_test_success_live":
        "{exchange} live connection successful. Account balance: {balance}",

    "token_test_failed_futures":
        "Binance API key lacks Futures permission. "
        "Go to Binance → Profile → API Management → Edit key → Enable Futures.",

    "token_test_failed_auth":
        "Authentication failed for {exchange}. "
        "Please check your API key and secret, then try again.",

    "token_test_failed_network":
        "Could not reach {exchange} servers. Check your internet connection.",

    # ── Risk Management ───────────────────────────────────────────────────
    "risk_emergency_stop_activated":
        "⛔ Emergency Stop activated. All trading has been halted immediately. "
        "No new orders will be placed until you deactivate this.",

    "risk_emergency_stop_deactivated":
        "✅ Emergency Stop deactivated. Trading can now resume.",

    # ── Subscription / Feature Gate ───────────────────────────────────────
    "plan_upgrade_required":
        "This feature is available on the {required_plan} plan and above. "
        "You are currently on the {current_plan} plan. Upgrade to unlock this feature.",

    "plan_limit_reached":
        "You have reached your {limit_name} limit for the {current_plan} plan. "
        "Upgrade to {required_plan} to get {new_limit}.",

    # ── General ───────────────────────────────────────────────────────────
    "server_error":
        "Something went wrong on our end. Our team has been notified. "
        "Please try again in a moment.",

    "rate_limited":
        "You are sending requests too quickly. "
        "Please wait {retry_after} seconds before trying again.",

    "not_found":
        "The requested resource could not be found.",

    "unauthorized":
        "You must be signed in to access this page. Please sign in and try again.",

    "forbidden":
        "You do not have permission to perform this action.",
}


def msg(key: str, **kwargs) -> str:
    """
    Get a message by key with optional format placeholders.

    Usage:
        msg("auth_signup_success", name="Jaikumar")
        msg("otp_sent", email="user@example.com")
        msg("plan_upgrade_required", required_plan="Pro", current_plan="Free")
    """
    template = MSG.get(key, MSG.get("server_error", "An error occurred."))
    try:
        return template.format(**kwargs) if kwargs else template
    except KeyError:
        return template
