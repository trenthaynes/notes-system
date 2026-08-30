# Deployment

This directory contains the Docker Compose configuration for running PiperVault and the notes-mcp server on your home server. Both services sit behind your existing Traefik reverse proxy and are reachable from any machine on your network or over Tailscale.

## Prerequisites

Before you start:

- Server is running and you have shell access (SSH or the Unraid terminal).
- Docker and Docker Compose are available (standard on Unraid).
- Traefik is already deployed as a container and is listening on ports 80 and 443. You know which entrypoint name handles HTTPS — typically `websecure`.
- Traefik has a certificate resolver configured (Let's Encrypt or similar). You know its name — check your Traefik static config (`traefik.yml` or the equivalent command-line flags on your existing Traefik container).
- A Docker network named `proxy` (or whatever name connects your containers to Traefik) already exists. If not, create it:
  ```sh
  docker network create proxy
  ```
- Both services will need DNS records. Create A records (or CNAME records pointing to your server's IP) for both subdomains you choose before deploying. Traefik will not obtain a TLS certificate for a domain that doesn't resolve.
- Tailscale (or another VPN) is configured if you want to reach the services from outside your home network.

## Understanding the Traefik labels

Each container has a block of `labels:` in the Compose file. These tell Traefik how to route HTTPS traffic to that container.

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.pipervault.rule=Host(`vault.example.com`)"
  - "traefik.http.routers.pipervault.entrypoints=websecure"
  - "traefik.http.routers.pipervault.tls=true"
  - "traefik.http.routers.pipervault.tls.certresolver=letsencrypt"
  - "traefik.http.services.pipervault.loadbalancer.server.port=8080"
```

- `traefik.enable=true` — Traefik only picks up containers that opt in.
- `rule=Host(...)` — the domain that routes to this container.
- `entrypoints=websecure` — the HTTPS entrypoint. Your Traefik setup may call this something different; check your existing Traefik containers or config.
- `tls.certresolver=letsencrypt` — the name of the certificate resolver in your Traefik static config. If your existing containers use `le` or `cloudflare` or another name, use that same value.
- `loadbalancer.server.port` — the port the container listens on internally. PiperVault uses 8080; notes-mcp uses 8000. Do not change these unless you also change the container configuration.

The Compose file uses environment variables (e.g. `${PIPERVAULT_DOMAIN}`) so you set the values once in `.env` and they propagate to both the container environment and the Traefik labels.

## Step 1: Copy the files to Server

Copy the `deployment/` directory to your server. A reasonable location is `/mnt/user/appdata/notes-system/`:

```sh
scp -r deployment/ root@your-server-ip:/mnt/user/appdata/notes-system/
```

Or copy via UI file manager, or clone the whole repo onto the server and work from there.

## Step 2: Create your `.env` file

In the directory where `docker-compose.yml` lives, create a file named `.env` by copying the example:

```sh
cp .env.example .env
```

Then edit `.env` and fill in every value. Here is what each variable does:

---

**`PIPERVAULT_DOMAIN`**

The subdomain where PiperVault's web UI and API will be reachable.

```
PIPERVAULT_DOMAIN=vault.yourdomain.com
```

This must match the DNS record you created. Traefik uses it to route HTTPS requests and to request a TLS certificate. Do not include `https://` — just the bare domain.

---

**`JWT_SECRET`**

A random string used to sign authentication tokens. Anyone who knows this value can forge tokens, so generate a strong one:

```sh
openssl rand -hex 32
```

The output (a 64-character hex string) goes here:

```
JWT_SECRET=a8f3c2...
```

Keep this secret. If you ever need to rotate it, all existing sessions will be invalidated and users will need to log in again.

---

**`ASK_SAGE_TOKEN`**

Your AskSage API token. PiperVault uses this only for its RAG chat feature — when you ask a question in the chat interface, it sends the query and retrieved note excerpts to the LLM to generate a response. PiperVault has a built-in AskSage adapter alongside Anthropic, OpenAI, and Ollama.

```
ASK_SAGE_TOKEN=your-asksage-token-here
```

Search and semantic similarity run entirely locally using the bundled ONNX model. If you leave this blank, PiperVault will still work for note storage and search; only the RAG chat feature will fail.

After deploying and logging in for the first time, go to **Settings → LLM Configuration** and select **Ask Sage** as the provider. The token you set here is what PiperVault will use for API calls — you do not need to re-enter it in the UI.

---

**`TRAEFIK_CERT_RESOLVER`**

The name of the certificate resolver defined in your Traefik static configuration.

```
TRAEFIK_CERT_RESOLVER=letsencrypt
```

To find the right value, look at how your existing Traefik-managed containers are labelled. For example, if another container has `traefik.http.routers.something.tls.certresolver=le`, then your value is `le`. Common values are `letsencrypt`, `le`, and `cloudflare`. If you use Cloudflare DNS challenge, you would use whatever name you gave that resolver in Traefik's `certificatesResolvers` block.

---

**`PIPERVAULT_API_TOKEN`**

An API token that the notes-mcp server uses to authenticate with PiperVault. You cannot set this until PiperVault is running and you have logged in for the first time (see Step 5 below). Leave it blank for now:

```
PIPERVAULT_API_TOKEN=
```

---

**`NOTES_MCP_DOMAIN`**

The subdomain for the notes-mcp server. This is separate from the PiperVault domain so Claude Code can reach the MCP endpoint at its own URL.

```
NOTES_MCP_DOMAIN=mcp.yourdomain.com
```

Same rules as `PIPERVAULT_DOMAIN` — must have a DNS record, no `https://`.

## Step 3: Deploy PiperVault

From the directory containing `docker-compose.yml` and your `.env` file:

```sh
docker compose up -d pipervault
```

Starting only the `pipervault` service here because `notes-mcp` depends on a PiperVault API token you do not have yet.

Watch the logs to confirm startup completes (PiperVault starts PostgreSQL internally, which takes 15–30 seconds):

```sh
docker compose logs -f pipervault
```

You are looking for log lines indicating the API server is ready. When you see the server listening on port 8080, proceed.

## Step 4: Verify PiperVault is reachable

From your work machine, check the health endpoint:

```sh
curl https://vault.yourdomain.com/api/v1/health
```

You should get a JSON response. If you get a TLS error, Traefik may still be obtaining the certificate — wait a minute and try again. If the connection is refused, check that the `proxy` Docker network is connected to your Traefik container and that DNS resolves correctly.

Try loading `https://vault.yourdomain.com` in a browser. You should see the PiperVault web UI login page.

## Step 5: First-time PiperVault setup

PiperVault requires a brief setup the first time you open it.

1. Open `https://vault.yourdomain.com` in your browser.
2. Register an account. Because `AUTH_ENABLED=true`, authentication is required.
3. After logging in, open **Settings → LLM Configuration** and select **Ask Sage** as the provider. Confirm the token field reflects the value you set in `.env` — PiperVault receives it as an environment variable, but you may need to confirm or re-enter it in the UI depending on how PiperVault surfaces provider configuration.
4. Open **Settings → API Keys** and create a new API key. Give it a descriptive name like `notes-cli`. Copy the token value — you will not be able to see it again.

## Step 6: Add the API token and deploy notes-mcp

Add the token you just copied to your `.env` file:

```
PIPERVAULT_API_TOKEN=pv_live_abc123...
```

Now deploy the notes-mcp service. It will build its Docker image from the repo:

```sh
docker compose up -d --build notes-mcp
```

The build step compiles the Python package and installs dependencies. It takes a minute or two on first run.

Verify it is healthy:

```sh
curl https://mcp.yourdomain.com/health
```

You should get a 200 response. If the `pipervault` container's health check is not yet passing, `notes-mcp` will wait (it depends on `pipervault` being healthy).

## Step 7: Add notes-mcp to Claude Code

On your work machine, edit `~/.claude/settings.json` and add the MCP server:

```json
{
  "mcpServers": {
    "notes": {
      "type": "url",
      "url": "https://mcp.yourdomain.com/mcp"
    }
  }
}
```

The key `"notes"` is the name Claude Code will use to identify this server — you can choose any name. After saving, restart Claude Code. In a new session, Claude should have access to the `search_notes`, `get_note`, `get_daily_note`, and `create_note` tools.

## Updating PiperVault

PiperVault does not publish versioned releases — `latest` is the only tag. Before pulling a new image, back up the `pgdata` volume:

```sh
# On Unraid, use the CA Backup plugin or manually:
docker run --rm \
  -v pipervault_pgdata:/data \
  -v /mnt/user/backups/notes:/backup \
  alpine tar czf /backup/pgdata-$(date +%Y%m%d).tar.gz -C /data .
```

Then update:

```sh
docker compose pull pipervault
docker compose up -d pipervault
```

## Troubleshooting

**Traefik is not routing to PiperVault**

Check that the `proxy` network is attached to your Traefik container. Traefik discovers services on shared networks — if PiperVault is not on the same network as Traefik, the labels are invisible to it.

```sh
docker network inspect proxy
```

Look for both your Traefik container and the `pipervault` container in the `Containers` list.

**Certificate is not being issued**

Verify that your DNS record resolves to your server's public IP (or Tailscale IP, if that is how you have Traefik configured). Let's Encrypt performs an HTTP challenge by default — port 80 must be open and reachable for this to work. If you use a DNS challenge instead, ensure your Traefik resolver is correctly configured with API credentials for your DNS provider.

**notes-mcp returns 401 errors**

The API token in your `.env` may be wrong or the token may have been deleted in PiperVault. Go to **Settings → API Keys** in PiperVault, create a new token, update `PIPERVAULT_API_TOKEN` in `.env`, and restart notes-mcp:

```sh
docker compose up -d notes-mcp
```

**PiperVault takes a long time to start**

PiperVault starts an embedded PostgreSQL instance. On first run it initialises the database and runs migrations, which can take 60–90 seconds. The health check in the Compose file gives it 60 seconds before starting to check — give it up to two minutes before investigating logs.
