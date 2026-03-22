import html
import secrets
import time
from dataclasses import dataclass
from typing import Any

from pydantic import AnyHttpUrl
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenVerifier,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from mcp.shared.auth_utils import check_resource_allowed, resource_url_from_server_url


@dataclass(frozen=True)
class SingleUserOAuthConfig:
    username: str
    password: str
    scope: str = "user"
    authorization_code_ttl_seconds: int = 300
    access_token_ttl_seconds: int = 3600


class SingleUserOAuthProvider(
    OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]
):
    """Minimal OAuth provider for a single protected MCP deployment."""

    def __init__(self, config: SingleUserOAuthConfig, login_url: str):
        self.config = config
        self.login_url = login_url
        self.clients: dict[str, OAuthClientInformationFull] = {}
        self.auth_codes: dict[str, AuthorizationCode] = {}
        self.tokens: dict[str, AccessToken] = {}
        self.pending_states: dict[str, dict[str, Any]] = {}

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self.clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull):
        if not client_info.client_id:
            raise ValueError("Missing client_id")
        self.clients[client_info.client_id] = client_info

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        state = params.state or secrets.token_hex(16)
        self.pending_states[state] = {
            "redirect_uri": str(params.redirect_uri),
            "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
            "code_challenge": params.code_challenge,
            "client_id": client.client_id,
            "resource": params.resource,
        }
        return f"{self.login_url}?state={state}"

    async def get_login_page(self, state: str) -> HTMLResponse:
        if not state:
            raise HTTPException(400, "Missing state parameter")

        username = html.escape(self.config.username)
        html_content = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Telegram MCP Sign In</title>
    <style>
      :root {{
        color-scheme: light;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }}
      body {{
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background: linear-gradient(160deg, #f4f0e8 0%, #dce9f5 100%);
        color: #18212b;
      }}
      main {{
        width: min(420px, calc(100vw - 32px));
        padding: 28px;
        border-radius: 18px;
        background: rgba(255, 255, 255, 0.92);
        box-shadow: 0 22px 70px rgba(24, 33, 43, 0.16);
      }}
      h1 {{
        margin: 0 0 8px;
        font-size: 24px;
      }}
      p {{
        margin: 0 0 16px;
        line-height: 1.5;
      }}
      label {{
        display: block;
        margin: 12px 0 6px;
        font-weight: 600;
      }}
      input {{
        box-sizing: border-box;
        width: 100%;
        padding: 12px 14px;
        border: 1px solid #bcc7d4;
        border-radius: 12px;
        font: inherit;
      }}
      button {{
        width: 100%;
        margin-top: 18px;
        padding: 12px 14px;
        border: 0;
        border-radius: 999px;
        background: #1365d6;
        color: white;
        font: inherit;
        font-weight: 700;
        cursor: pointer;
      }}
      .hint {{
        margin-top: 14px;
        font-size: 13px;
        color: #5a6877;
      }}
      code {{
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      }}
    </style>
  </head>
  <body>
    <main>
      <h1>Telegram MCP Sign In</h1>
      <p>Use the single account credentials configured on this deployment.</p>
      <form method="post" action="/login/callback">
        <input type="hidden" name="state" value="{html.escape(state)}" />
        <label for="username">Username</label>
        <input id="username" name="username" autocomplete="username" value="{username}" required />
        <label for="password">Password</label>
        <input
          id="password"
          name="password"
          type="password"
          autocomplete="current-password"
          required
        />
        <button type="submit">Continue</button>
      </form>
      <p class="hint">Only the configured owner account can finish OAuth for this MCP server.</p>
    </main>
  </body>
</html>"""
        return HTMLResponse(content=html_content)

    async def handle_login_callback(self, request: Request) -> Response:
        form = await request.form()
        username = form.get("username")
        password = form.get("password")
        state = form.get("state")

        if not isinstance(username, str) or not isinstance(password, str) or not isinstance(
            state, str
        ):
            raise HTTPException(400, "Invalid login form payload")

        redirect_uri = await self.finish_login(username, password, state)
        return RedirectResponse(url=redirect_uri, status_code=302)

    async def finish_login(self, username: str, password: str, state: str) -> str:
        state_data = self.pending_states.get(state)
        if not state_data:
            raise HTTPException(400, "Invalid state parameter")

        if username != self.config.username or password != self.config.password:
            raise HTTPException(401, "Invalid credentials")

        redirect_uri = state_data["redirect_uri"]
        code_challenge = state_data["code_challenge"]
        client_id = state_data["client_id"]
        if not redirect_uri or not code_challenge or not client_id:
            raise HTTPException(400, "Incomplete authorization request")

        code = f"mcp_code_{secrets.token_hex(16)}"
        self.auth_codes[code] = AuthorizationCode(
            code=code,
            client_id=client_id,
            redirect_uri=AnyHttpUrl(redirect_uri),
            redirect_uri_provided_explicitly=bool(
                state_data["redirect_uri_provided_explicitly"]
            ),
            expires_at=time.time() + self.config.authorization_code_ttl_seconds,
            scopes=[self.config.scope],
            code_challenge=code_challenge,
            resource=state_data.get("resource"),
        )
        del self.pending_states[state]

        return construct_redirect_uri(redirect_uri, code=code, state=state)

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        return self.auth_codes.get(authorization_code)

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        if authorization_code.code not in self.auth_codes:
            raise ValueError("Invalid authorization code")
        if not client.client_id:
            raise ValueError("Missing client_id")

        token_value = f"mcp_token_{secrets.token_hex(32)}"
        expires_at = None
        if self.config.access_token_ttl_seconds > 0:
            expires_at = int(time.time()) + self.config.access_token_ttl_seconds

        self.tokens[token_value] = AccessToken(
            token=token_value,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=expires_at,
            resource=authorization_code.resource,
        )
        del self.auth_codes[authorization_code.code]

        return OAuthToken(
            access_token=token_value,
            token_type="Bearer",
            expires_in=(
                self.config.access_token_ttl_seconds
                if self.config.access_token_ttl_seconds > 0
                else None
            ),
            scope=" ".join(authorization_code.scopes),
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        access_token = self.tokens.get(token)
        if not access_token:
            return None

        if access_token.expires_at and access_token.expires_at < time.time():
            del self.tokens[token]
            return None

        return access_token

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        return None

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        raise NotImplementedError("Refresh tokens are not supported")

    async def revoke_token(self, token: str, token_type_hint: str | None = None) -> None:
        self.tokens.pop(token, None)


class LocalTokenVerifier(TokenVerifier):
    """Validate bearer tokens directly against the in-process auth provider."""

    def __init__(
        self,
        provider: SingleUserOAuthProvider,
        server_url: str,
        validate_resource_binding: bool = True,
    ):
        self.provider = provider
        self.server_url = server_url
        self.validate_resource_binding = validate_resource_binding
        self.resource_url = resource_url_from_server_url(server_url)

    async def verify_token(self, token: str) -> AccessToken | None:
        access_token = await self.provider.load_access_token(token)
        if not access_token:
            return None

        if self.validate_resource_binding and not self._resource_allowed(access_token.resource):
            return None

        return access_token

    def _resource_allowed(self, resource: str | list[str] | None) -> bool:
        if not self.resource_url:
            return False
        if not resource:
            return False

        if isinstance(resource, list):
            return any(
                check_resource_allowed(
                    requested_resource=self.resource_url, configured_resource=value
                )
                for value in resource
            )

        return check_resource_allowed(
            requested_resource=self.resource_url, configured_resource=resource
        )
