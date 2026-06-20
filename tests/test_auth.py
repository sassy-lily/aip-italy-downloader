"""httpx-only IDCS/OAM login: full chain, session reuse, and challenge handling."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from aip_downloader.auth import AuthError, EnavAuth
from aip_downloader.config import Settings
from aip_downloader.version import LANDING_URL

IDCS = "https://idcs-test.identity.oraclecloud.com"
OAM_SSO = "https://auth.enav.it/oam/server/fed/sp/sso"


def _user_login_form() -> str:
    return f"""<html><body onload="document.forms[0].submit();">
      <form method="POST" action="{IDCS}/ui/v1/signin">
        <input type="hidden" name="signature" value="sig"/>
        <input type="hidden" name="state" value="null"/>
        <input type="hidden" name="loginCtx" value="ctx"/>
      </form></body></html>"""


def _saml_form() -> str:
    return f"""<html><body onload="document.forms[0].submit();">
      <form method="POST" action="{OAM_SSO}">
        <input type="hidden" name="RelayState" value="rs"/>
        <input type="hidden" name="SAMLResponse" value="assertion"/>
      </form></body></html>"""


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        base_url="https://www.enav.it",
        output_dir=tmp_path,
        user="fakeuser",
        password="fakepass",
        session_path=tmp_path / "session.json",
    )


def _mock_full_chain():
    respx.get(LANDING_URL).mock(
        return_value=httpx.Response(200, text=_user_login_form())
    )
    respx.post(f"{IDCS}/ui/v1/signin").mock(return_value=httpx.Response(200, text="ok"))
    secure = respx.post(f"{IDCS}/ui/v1/api/user/secure/login").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "nextOp": "postRedirect",
                "redirectUrl": f"{IDCS}/fed/v1/user/response/login",
                "postParams": {"OCIS_REQ": "token"},
            },
        )
    )
    respx.post(f"{IDCS}/fed/v1/user/response/login").mock(
        return_value=httpx.Response(200, text=_saml_form())
    )
    respx.post(OAM_SSO).mock(
        return_value=httpx.Response(
            200, headers={"set-cookie": "OAMAuthnCookie_test=xyz; Path=/"}
        )
    )
    return secure


@respx.mock
async def test_login_chain_persists_session(tmp_path):
    secure = _mock_full_chain()
    settings = _settings(tmp_path)

    ctx = await EnavAuth().get_session(settings)

    assert ctx.storage_state_path == str(settings.session_path)
    saved = json.loads(settings.session_path.read_text())
    names = {c["name"] for c in saved["cookies"]}
    assert "OAMAuthnCookie_test" in names

    # Credential submit carried the right op + username (no real creds in tests).
    body = json.loads(secure.calls.last.request.content)
    assert body["op"] == "cred_submit"
    assert body["credentials"]["username"] == "fakeuser"


@respx.mock
async def test_existing_session_is_reused_without_network(tmp_path):
    settings = _settings(tmp_path)
    settings.session_path.write_text('{"cookies": []}', encoding="utf-8")

    ctx = await EnavAuth().get_session(settings)

    assert ctx.storage_state_path == str(settings.session_path)
    assert respx.calls.call_count == 0  # short-circuited, no login attempted


@respx.mock
async def test_mfa_or_failed_credentials_raise_clean_error(tmp_path):
    respx.get(LANDING_URL).mock(
        return_value=httpx.Response(200, text=_user_login_form())
    )
    respx.post(f"{IDCS}/ui/v1/signin").mock(return_value=httpx.Response(200, text="ok"))
    respx.post(f"{IDCS}/ui/v1/api/user/secure/login").mock(
        return_value=httpx.Response(200, json={"success": False, "nextOp": "challenge"})
    )

    with pytest.raises(AuthError) as exc:
        await EnavAuth().get_session(_settings(tmp_path))

    # Error is informative but leaks no credentials.
    message = str(exc.value)
    assert "fakepass" not in message and "fakeuser" not in message
    assert not settings_file_written(tmp_path)


def settings_file_written(tmp_path: Path) -> bool:
    return (tmp_path / "session.json").exists()
