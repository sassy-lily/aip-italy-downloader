"""ENAV authentication. RECON-BLOCKED: body filled in after Phase 1.

Confirmed: the AIP landing page redirects to Oracle Access Manager
(auth.enav.it/oam/...) via a SAML flow. Login is password-only (no MFA), so the
target is a headless Playwright login that persists a storage_state.json; the
manual-login-then-persist path is the contingency if scripting the OAM form
proves unreliable. Recon decides which, and whether httpx can reuse the cookies.
"""

from __future__ import annotations

from .config import Settings
from .models import SessionContext

_NOT_YET = (
    "EnavAuth.get_session is recon-blocked: the OAM/SAML login flow is "
    "determined in Phase 1 (see docs/BUILD_PROMPT.md)."
)


class EnavAuth:
    """Establishes an authenticated session against the ENAV portal."""

    async def get_session(self, settings: Settings) -> SessionContext:
        raise NotImplementedError(_NOT_YET)
