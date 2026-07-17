# GCP Document Routing Agent

This project provides a Python agent scaffold you can run on Google Agent Platform workloads to:

1. Connect to **Microsoft SharePoint** (via Microsoft 365 SDK).
2. Connect to **Google Drive**.
3. Optionally enrich file metadata from **Microsoft Purview SDK**.
4. Prompt for which discovered document to attach and where to send it.
5. Send an email with that attachment via **Microsoft Graph**.

## Architecture

- `SharePointClient`: inventories and downloads files from SharePoint using the Microsoft 365 SDK (`office365-rest-python-client`).
- `GoogleDriveClient`: inventories and downloads files from Google Drive.
- `PurviewClient`: optional metadata enrichment via `azure-purview-catalog` SDK.
- `GraphEmailClient`: sends email with attachment through Graph.
- `a365.configure_a365_observability`: enables Agent365 observability SDK wiring.
- `DocumentRoutingAgent`: orchestrates user prompt -> file selection -> send workflow.

## Security and protection controls

- **Entra ID SDK** (`azure-identity`) handles confidential-client auth/token flows.
- **Purview SDK** (`azure-purview-catalog`) attaches sensitivity metadata to inventory results.
- **Agent365 SDK** (`microsoft-agents-a365-observability-core`) enables runtime observability hooks.
- **Policy enforcement** blocks sending Purview-labeled sensitive files to external domains.

## Entra ID app registration

Create a single Entra app registration and configure:

1. **Authentication**
   - App type: confidential client (server-side).
   - Create a client secret.
2. **API permissions** (application permissions where supported)
   - Microsoft Graph: `Mail.Send`, `Sites.Read.All`, `Files.Read.All`, `User.Read.All`
   - SharePoint: delegated through Graph/SharePoint depending on tenant policy
3. **Admin consent**
   - Grant admin consent for the tenant.
4. **Credentials**
   - Save tenant ID, client ID, and client secret.

## Google configuration

1. Create a Google Cloud service account with Drive access.
2. Enable Drive API.
3. Download service account JSON key file.
4. Share the target Google Drive folders/files with the service account.

## Purview configuration (optional)

If you have a Purview endpoint, set `PURVIEW_ENDPOINT` to enable metadata enrichment during inventory.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Populate `.env` values, then run:

```bash
python main.py
```

## Environment variables

See `.env.example` for all required values.
