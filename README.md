# Telegram MCP Server

Remote-only Telegram MCP server for Claude Desktop, backed by Telethon and protected by a built-in single-user OAuth flow.

## Breaking Change

This repo is now a hard cutover to a remote MCP deployment:

- `stdio` is gone.
- `claude_desktop_config.json` is gone.
- Claude Desktop should connect through `Settings > Connectors` using your deployed `/mcp` URL.

The Telegram tools exposed by the server are still the same. Only transport and authentication changed.

## Architecture

One process serves everything:

- `/mcp`: Streamable HTTP MCP endpoint
- `/.well-known/oauth-protected-resource`: MCP resource metadata for OAuth discovery
- `/authorize`, `/token`, `/register`: OAuth server endpoints
- `/login`: simple sign-in page for the one account you allow

This is meant for a personal deployment where only you should be able to connect Claude to your Telegram account.

## Required Environment

```env
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=0123456789abcdef0123456789abcdef
TELEGRAM_SESSION_NAME=telegram_session
TELEGRAM_SESSION_STRING=your_string_session

MCP_BIND_HOST=0.0.0.0
MCP_BIND_PORT=8000
MCP_PUBLIC_BASE_URL=https://telegram-mcp.example.com

MCP_AUTH_USERNAME=me
MCP_AUTH_PASSWORD=replace-this-now
MCP_AUTH_SCOPE=user

# Optional, colon-separated
MCP_ALLOWED_ROOTS=/srv/telegram-mcp:/tmp/telegram-mcp
```

Notes:

- `MCP_PUBLIC_BASE_URL` must be the public HTTPS origin of the deployment.
- Do not include a path in `MCP_PUBLIC_BASE_URL`.
- `MCP_AUTH_PASSWORD` must be changed from the placeholder value.
- Use either `TELEGRAM_SESSION_STRING` or a persistent `TELEGRAM_SESSION_NAME`.
- On Railway, the app will also honor Railway's injected `PORT` automatically.

## Telegram Session Setup

Create a session string once:

```bash
uv run session_string_generator.py
```

Then place the generated value in `TELEGRAM_SESSION_STRING`.

## Local Run

Install dependencies:

```bash
uv sync
```

Start the server:

```bash
uv run python main.py
```

The MCP endpoint will be:

```text
http://localhost:8000/mcp
```

For local testing, `http://localhost` is allowed. Public deployments should use HTTPS.

## Docker

Build:

```bash
docker build -t telegram-mcp .
```

Run:

```bash
docker run --rm -p 8000:8000 --env-file .env telegram-mcp
```

Or with Compose:

```bash
docker compose up --build
```

## Deployment

Use a dedicated subdomain and terminate TLS in front of the container.

Recommended shape:

1. Deploy the container on a small VM or container host.
2. Put HTTPS in front of it with your reverse proxy or platform ingress.
3. Set `MCP_PUBLIC_BASE_URL` to the public origin, for example `https://telegram-mcp.example.com`.
4. Keep the server private except for the HTTPS endpoint Claude needs.

The app assumes it is served at the domain root. Do not mount it under a path prefix.

## Claude Desktop Connector Setup

Add the server as a custom connector in Claude Desktop:

1. Open `Settings > Connectors`.
2. Add a custom connector.
3. Enter your remote MCP URL: `https://telegram-mcp.example.com/mcp`
4. Finish the OAuth flow in the browser.
5. Log in with `MCP_AUTH_USERNAME` and `MCP_AUTH_PASSWORD`.

If Claude asks for OAuth client credentials, allow dynamic registration first. This server exposes `/register` for that flow.

## File Tool Roots

File-based tools stay disabled unless roots are configured.

You can allow roots in two ways:

- `MCP_ALLOWED_ROOTS` as a colon-separated list
- positional CLI arguments to `main.py`

Examples:

```bash
MCP_ALLOWED_ROOTS=/srv/telegram-mcp:/tmp/telegram-mcp uv run python main.py
```

```bash
uv run python main.py /srv/telegram-mcp /tmp/telegram-mcp
```

## Health Check

```text
GET /healthz
```

Returns:

```json
{"ok":true,"telegram_connected":true}
```

## Security Model

This is intentionally minimal:

- one username
- one password
- one MCP scope
- dynamic OAuth client registration enabled

It is good enough for a private personal deployment, not a multi-user product.

## Troubleshooting

`MCP_AUTH_PASSWORD` still set to `change-me`

- The server refuses to boot until you set a real password.

`TELEGRAM_API_ID` or `TELEGRAM_API_HASH` missing

- The server refuses to boot until Telegram credentials are configured.

Telegram session database is locked

- Another process is already using the same file-based Telegram session.

Claude cannot connect

- Check that `MCP_PUBLIC_BASE_URL` matches the public HTTPS origin exactly.
- Check that Claude is pointed at `/mcp`, not the site root.
- Check that your reverse proxy forwards requests to port `8000`.
