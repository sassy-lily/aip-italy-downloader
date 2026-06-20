"""ENAV authentication — pure httpx replay of the Oracle IDCS / OAM SAML login.

Login is a server-driven chain of form/JSON POSTs (no browser, no MFA): each
step's tokens come from the previous response (see docs/RECON.md section 1). We
run it on one httpx client, then persist the resulting cookie jar so the rest of
the app reuses the session. A saved session is reused if present; delete it
(CLI --login) to force re-auth.
"""

from __future__ import annotations

import json
from http.cookiejar import Cookie

import httpx
from bs4 import BeautifulSoup

from .config import Settings
from .logging_setup import get_logger
from .models import SessionContext
from .version import LANDING_URL

logger = get_logger(__name__)

# IDCS rejects unusual clients, so present as a normal desktop browser.
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/148.0.0.0 Safari/537.36"
)
_SECURE_LOGIN_PATH = "/ui/v1/api/user/secure/login"
# A minimal device fingerprint; IDCS records it for risk analysis but accepts it.
_DEVICE = json.dumps({"screenWidth": 1280, "screenHeight": 720})


class AuthError(RuntimeError):
    """Login could not be completed (e.g. an MFA / adaptive challenge)."""


def _form_action_and_fields(html: str) -> tuple[str, dict[str, str]]:
    """Extract the first form's action URL and its named input values."""
    form = BeautifulSoup(html, "lxml").find("form")
    if form is None or not form.get("action"):
        raise AuthError("expected an auto-submit form but none was found")
    fields = {
        inp.get("name"): inp.get("value", "")
        for inp in form.find_all("input")
        if inp.get("name")
    }
    return form["action"], fields


def _serialize_cookies(client: httpx.AsyncClient) -> str:
    cookies: list[Cookie] = list(client.cookies.jar)
    return json.dumps(
        {
            "cookies": [
                {
                    "name": c.name,
                    "value": c.value or "",
                    "domain": c.domain,
                    "path": c.path,
                }
                for c in cookies
            ]
        },
        indent=2,
    )


class EnavAuth:
    """Establishes a session by replaying the IDCS/OAM SAML login over httpx."""

    async def get_session(self, settings: Settings) -> SessionContext:
        state_path = settings.session_path
        if state_path.exists():
            logger.info("reusing saved session: %s", state_path)
            return SessionContext(storage_state_path=str(state_path))

        settings.require_credentials()
        logger.info("no saved session; logging in via httpx (IDCS/OAM SAML)")

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=30.0,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            await self._login(client, settings)
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(_serialize_cookies(client), encoding="utf-8")

        logger.info("login succeeded; session saved to %s", state_path)
        return SessionContext(storage_state_path=str(state_path))

    async def _login(self, client: httpx.AsyncClient, settings: Settings) -> None:
        # 1-2. Landing redirects to the IDCS user/login auto-submit form, which
        # we replay to /ui/v1/signin.
        landing = await client.get(LANDING_URL)
        signin_action, signin_fields = _form_action_and_fields(landing.text)
        signin_url = httpx.URL(signin_action)
        idcs_base = f"{signin_url.scheme}://{signin_url.host}"
        await client.post(signin_action, data=signin_fields)

        # 3. Credential submit (JSON XHR). The response tells us the next POST.
        resp = await client.post(
            f"{idcs_base}{_SECURE_LOGIN_PATH}",
            json={
                "op": "cred_submit",
                "credentials": {
                    "username": settings.user,
                    "password": settings.password,
                    "device": _DEVICE,
                },
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        data = resp.json()
        if not data.get("success") or data.get("nextOp") != "postRedirect":
            # Don't log the body — it may echo credentials/PII.
            raise AuthError(
                "credential submit did not complete a standard login; the account "
                "may require interactive auth (MFA / adaptive challenge)."
            )

        # 4. Hand OCIS_REQ back to IDCS, which returns the SAML auto-submit form.
        saml_page = await client.post(data["redirectUrl"], data=data["postParams"])
        saml_action, saml_fields = _form_action_and_fields(saml_page.text)

        # 5. POST the SAML assertion to OAM; redirects re-establish the portal session.
        await client.post(saml_action, data=saml_fields)
