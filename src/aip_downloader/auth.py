"""ENAV authentication via Playwright, then session reuse over httpx.

Login is Oracle IDCS federated through OAM/SAML, password-only (no MFA). We drive
the headless browser through the sign-in once, persist its storage_state, and let
the rest of the app reuse those cookies in httpx (see docs/RECON.md section 1).
A saved session is reused if present; delete it (CLI --login) to force re-auth.
"""

from __future__ import annotations

from playwright.async_api import async_playwright

from .config import Settings
from .logging_setup import get_logger
from .models import SessionContext
from .version import LANDING_URL

logger = get_logger(__name__)

USERNAME_SEL = "#idcs-signin-basic-signin-form-username"
PASSWORD_SEL = '[id="idcs-signin-basic-signin-form-password|input"]'
PORTAL_GLOB = "**onlineservices.enav.it/**"


class EnavAuth:
    async def get_session(self, settings: Settings) -> SessionContext:
        state_path = settings.session_path
        if state_path.exists():
            logger.info("reusing saved session: %s", state_path)
            return SessionContext(storage_state_path=str(state_path))

        settings.require_credentials()
        logger.info("no saved session; logging in via Playwright (headless)")
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.goto(LANDING_URL, wait_until="networkidle", timeout=60_000)
                await page.fill(USERNAME_SEL, settings.user)
                await page.fill(PASSWORD_SEL, settings.password)
                await page.get_by_role("button", name="Sign In", exact=True).click()
                # The SAML round-trip lands us back on the ENAV portal.
                await page.wait_for_url(PORTAL_GLOB, timeout=60_000)
                await page.wait_for_load_state("networkidle", timeout=60_000)
                state_path.parent.mkdir(parents=True, exist_ok=True)
                await context.storage_state(path=str(state_path))
            finally:
                await browser.close()

        logger.info("login succeeded; session saved to %s", state_path)
        return SessionContext(storage_state_path=str(state_path))
