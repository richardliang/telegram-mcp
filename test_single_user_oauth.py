import pytest
from starlette.exceptions import HTTPException

from single_user_oauth import LocalTokenVerifier, SingleUserOAuthConfig, SingleUserOAuthProvider


class _Client:
    def __init__(self, client_id: str):
        self.client_id = client_id


@pytest.mark.asyncio
async def test_finish_login_creates_authorization_code():
    provider = SingleUserOAuthProvider(
        config=SingleUserOAuthConfig(username="owner", password="secret"),
        login_url="http://localhost:8000/login",
    )
    provider.pending_states["state-1"] = {
        "redirect_uri": "http://localhost/callback",
        "redirect_uri_provided_explicitly": True,
        "code_challenge": "challenge",
        "client_id": "client-123",
        "resource": "http://localhost:8000/mcp",
    }

    redirect_uri = await provider.finish_login("owner", "secret", "state-1")

    assert "code=" in redirect_uri
    assert "state=state-1" in redirect_uri
    assert len(provider.auth_codes) == 1


@pytest.mark.asyncio
async def test_finish_login_rejects_invalid_credentials():
    provider = SingleUserOAuthProvider(
        config=SingleUserOAuthConfig(username="owner", password="secret"),
        login_url="http://localhost:8000/login",
    )
    provider.pending_states["state-1"] = {
        "redirect_uri": "http://localhost/callback",
        "redirect_uri_provided_explicitly": True,
        "code_challenge": "challenge",
        "client_id": "client-123",
        "resource": "http://localhost:8000/mcp",
    }

    with pytest.raises(HTTPException) as error:
        await provider.finish_login("owner", "wrong", "state-1")

    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_local_token_verifier_accepts_bound_token():
    provider = SingleUserOAuthProvider(
        config=SingleUserOAuthConfig(username="owner", password="secret"),
        login_url="http://localhost:8000/login",
    )
    provider.pending_states["state-1"] = {
        "redirect_uri": "http://localhost/callback",
        "redirect_uri_provided_explicitly": True,
        "code_challenge": "challenge",
        "client_id": "client-123",
        "resource": "http://localhost:8000/mcp",
    }

    await provider.finish_login("owner", "secret", "state-1")
    auth_code = next(iter(provider.auth_codes.values()))
    token = await provider.exchange_authorization_code(_Client("client-123"), auth_code)

    verifier = LocalTokenVerifier(
        provider=provider,
        server_url="http://localhost:8000/mcp",
        validate_resource_binding=True,
    )

    verified = await verifier.verify_token(token.access_token)
    assert verified is not None
    assert verified.token == token.access_token
