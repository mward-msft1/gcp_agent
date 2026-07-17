# GCP Document Routing Agent

This project is a Python agent scaffold that can inventory documents from **SharePoint** and **Google Drive**, ask which file to send, and send that file by email through **Microsoft Graph**. It also supports **Purview classification lookup** and **Agent365 observability**.

## What this agent does

1. Lists documents from SharePoint and Google Drive.
2. Optionally enriches each file with Purview metadata.
3. Prompts for:
   - which file to attach
   - destination email address
   - subject
4. Applies outbound policy checks (for example: blocked labels to external domains).
5. Sends email with attachment via Graph.

## SDKs included

- **Entra ID SDK**: `azure-identity`
- **Purview SDK**: `azure-purview-catalog`
- **Microsoft 365/SharePoint SDK**: `office365-rest-python-client`
- **Agent 365 SDK**: `microsoft-agents-a365-observability-core`
- **Google Drive SDK**: `google-api-python-client`

## Architecture

- `SharePointClient`: SharePoint inventory + file download
- `GoogleDriveClient`: Drive inventory + file download
- `PurviewClient`: Purview discovery query for metadata labels
- `GraphEmailClient`: Graph `sendMail` with attachment
- `DocumentRoutingAgent`: end-to-end orchestration and policy enforcement
- `configure_a365_observability`: Agent365 tracing bootstrap

## Environments supported

- **Environment A (Local PC)**: run the agent interactively from your machine.
- **Environment B (Google Cloud / third-party hosting)**: run the same workload in GCP while using your own Microsoft 365 tenant as the external system-under-test.

> Current implementation is interactive CLI (`input()` prompts).  
> For fully managed Google AI conversations (chat endpoints), keep this business logic and place it behind a Google ADK/Agent runtime HTTP wrapper.

## 1) Local PC prerequisites

Install these tools:

1. Python 3.11+ (`python3 --version`)
2. Git (`git --version`)
3. pip + virtualenv support
4. Optional for cloud deployment: Google Cloud SDK (`gcloud --version`)

Install Python dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 2) Microsoft 365 tenant setup (your own tenant)

Create one Entra app registration for this agent:

1. Entra admin center -> **App registrations** -> **New registration**
2. Create a **client secret**
3. Add **Application permissions** in Microsoft Graph:
   - `Mail.Send`
   - `Sites.Read.All`
   - `Files.Read.All`
   - `User.Read.All`
4. Click **Grant admin consent**
5. Record:
   - Tenant ID
   - Client ID
   - Client secret

Required data-plane setup:

1. SharePoint: identify site URL and folder server-relative path.
2. Exchange Online: create/choose sender mailbox (`GRAPH_SENDER_UPN`) with permission to send.
3. Purview (optional): ensure your app identity can query Purview catalog endpoint.

## 3) Google Drive setup

1. In Google Cloud, create a service account.
2. Enable **Google Drive API**.
3. Create/download service account key JSON.
4. Share target Drive folder/files with that service account.
5. Save the folder ID for `GOOGLE_DRIVE_FOLDER_ID`.

## 4) Configure environment variables

Copy the template:

```bash
cp .env.example .env
```

Set all required values in `.env`:

- Entra credentials (`ENTRA_*`)
- SharePoint details (`SHAREPOINT_*`)
- Graph sender (`GRAPH_SENDER_UPN`)
- Google service account file and folder ID
- Optional Purview endpoint
- Policy controls:
  - `ALLOWED_RECIPIENT_DOMAINS`
  - `BLOCKED_PURVIEW_LABELS`
- Agent365 observability flags

## 5) Run locally

```bash
source .venv/bin/activate
python main.py
```

You should see document inventory, then prompts for file selection and recipient.

## 6) Third-party Google Cloud deployment (for tenant testing)

Use this when you want the agent hosted outside Microsoft (GCP) and connected to your Microsoft 365 tenant as a third-party system.

1. Create/select a GCP project.
2. Enable APIs:
   - Cloud Run Admin API
   - Cloud Build API
   - Artifact Registry API
   - Secret Manager API
   - IAM API
3. Store secrets in Secret Manager:
   - Entra client secret
   - Google service account JSON (or mount as a secure file)
4. Deploy runtime (example with source deploy):
   ```bash
   gcloud run deploy document-routing-agent \
     --source . \
     --region us-central1 \
     --platform managed
   ```
5. Inject environment variables/secrets into Cloud Run service.
6. Verify outbound access from Cloud Run to:
   - `graph.microsoft.com`
   - SharePoint tenant endpoints
   - Purview endpoint (if used)
   - Google Drive APIs

## 7) Building this into Google AI Platform agent workflows

To make this a true Google AI Platform agent (instead of local CLI prompts):

1. Keep this repository as the **integration/action layer** (SharePoint, Purview, Graph, Drive).
2. Wrap `DocumentRoutingAgent` logic in ADK-compatible tool handlers (or HTTP endpoints).
3. Use Google AI/ADK orchestrator to:
   - call an inventory tool
   - present choices to the user
   - call a send tool with selected document + recipient
4. Host that orchestrator in GCP (Cloud Run or your chosen runtime) and keep secrets in Secret Manager.
5. Run test scenarios against your own Microsoft 365 tenant for third-party validation.

## 8) Validation checklist for your tenant test

1. Inventory returns SharePoint + Drive files.
2. Purview labels appear for files when endpoint is configured.
3. External recipient block works for restricted labels.
4. Allowed recipient receives email + correct attachment.
5. Graph sent-items log confirms send operation.

## Environment variable reference

See `.env.example` for the canonical list and names.
