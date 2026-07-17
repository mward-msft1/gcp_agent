# GCP Document Routing Agent (Beginner Step-by-Step Guide)

This guide is written for beginners. Follow it exactly, one step at a time.

## What this agent does

1. Reads files from your SharePoint folder.
2. Reads files from your Google Drive folder.
3. Shows all found files and asks which one to send.
4. Asks where to send the file.
5. Sends the selected file as an email attachment through Microsoft Graph.
6. Optionally checks Purview labels and blocks external send based on policy.

## SDKs used in this repository

1. Entra ID SDK: `azure-identity`
2. Purview SDK: `azure-purview-catalog`
3. Microsoft 365 / SharePoint SDK: `office365-rest-python-client`
4. Agent 365 SDK: `microsoft-agents-a365-observability-core`
5. Google Drive SDK: `google-api-python-client`

## Before you start

You need:

1. A Microsoft 365 tenant where you are admin (or can get admin help).
2. A Google Cloud project where you can create service accounts.
3. A local computer (Windows, macOS, or Linux) with Python 3.11+.

---

## Part A - Local computer setup

### Step A1: Install required tools

Install:

1. Python 3.11 or newer
2. Git
3. (Optional now, required for cloud deploy later) Google Cloud SDK (`gcloud`)

Check installs:

```bash
python3 --version
git --version
gcloud --version
```

### Step A2: Download the repository

```bash
git clone https://github.com/mward-msft1/gcp_agent.git
cd gcp_agent
```

### Step A3: Create Python environment and install packages

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## Part B - Microsoft 365 setup (your tenant)

### Step B1: Create Entra app registration

1. Open Entra admin center.
2. Go to **App registrations** -> **New registration**.
3. Name it (example: `gcp-document-routing-agent`).
4. Click **Register**.

### Step B2: Create client secret

1. Open your new app.
2. Go to **Certificates & secrets**.
3. Create **New client secret**.
4. Copy the secret value immediately and save it safely.

### Step B3: Add Microsoft Graph permissions

Add **Application** permissions:

1. `Mail.Send`
2. `Sites.Read.All`
3. `Files.Read.All`
4. `User.Read.All`

Then click **Grant admin consent**.

### Step B4: Save these values

You need these for `.env`:

1. Tenant ID
2. Client ID
3. Client Secret

### Step B5: SharePoint and mailbox details

Get:

1. `SHAREPOINT_SITE_URL` (example: `https://contoso.sharepoint.com/sites/YourSite`)
2. `SHAREPOINT_FOLDER_SERVER_RELATIVE` (example: `/sites/YourSite/Shared Documents`)
3. `GRAPH_SENDER_UPN` (mailbox to send from, example: `automation@contoso.com`)

Optional:

1. `PURVIEW_ENDPOINT` if using Purview.

---

## Part C - Google setup

### Step C1: Create service account

1. Open Google Cloud Console.
2. Create/select a project.
3. Go to **IAM & Admin** -> **Service Accounts**.
4. Create a service account.

### Step C2: Enable Drive API

1. Go to **APIs & Services**.
2. Enable **Google Drive API**.

### Step C3: Create key file

1. Open your service account.
2. Create a JSON key.
3. Download the JSON key file to your local machine.
4. Save its full path.

### Step C4: Share Drive folder

1. Open Google Drive.
2. Share the target folder with the service account email.
3. Copy the folder ID from the URL.

---

## Part D - Configure the agent

### Step D1: Create `.env`

```bash
cp .env.example .env
```

### Step D2: Fill in `.env`

Open `.env` and set all values:

1. `ENTRA_TENANT_ID`
2. `ENTRA_CLIENT_ID`
3. `ENTRA_CLIENT_SECRET`
4. `SHAREPOINT_SITE_URL`
5. `SHAREPOINT_FOLDER_SERVER_RELATIVE`
6. `GRAPH_SENDER_UPN`
7. `GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE`
8. `GOOGLE_DRIVE_FOLDER_ID`
9. `PURVIEW_ENDPOINT` (optional)
10. `ALLOWED_RECIPIENT_DOMAINS`
11. `BLOCKED_PURVIEW_LABELS`
12. `ENABLE_A365_OBSERVABILITY`
13. `OBSERVABILITY_SERVICE_NAME`
14. `OBSERVABILITY_SERVICE_NAMESPACE`

---

## Part E - Run locally

1. Activate virtual environment.
2. Run:

```bash
python main.py
```

3. Follow prompts:
   1. choose file number
   2. enter recipient email
   3. enter subject (or leave blank)

---

## Part F - Use this as a true third-party Google-hosted agent

This means your code runs in Google Cloud, but it connects to Microsoft 365 in your tenant.

### Step F1: Prepare Google Cloud project

Enable these APIs:

1. Cloud Run Admin API
2. Cloud Build API
3. Artifact Registry API
4. Secret Manager API
5. IAM API

### Step F2: Store secrets safely

Put secrets in Secret Manager:

1. Entra client secret
2. Google service account JSON
3. Any other sensitive values

### Step F3: Deploy to Cloud Run

```bash
gcloud run deploy document-routing-agent \
  --source . \
  --region us-central1 \
  --platform managed
```

### Step F4: Add environment variables in Cloud Run

Set the same `.env` values in Cloud Run service configuration.

### Step F5: Confirm network access

Your Cloud Run service must reach:

1. `graph.microsoft.com`
2. your SharePoint tenant endpoints
3. Purview endpoint (if used)
4. Google Drive API

---

## Part G - Build on Google AI Platform / ADK

Current code is CLI-interactive. To turn this into a conversational Google AI agent:

1. Keep this repo as your integration layer.
2. Wrap inventory/send logic as ADK tools or HTTP actions.
3. In your Google AI agent flow:
   1. call inventory tool
   2. show file choices to user
   3. call send tool with selected file + recipient
4. Host that orchestrator in GCP and keep secrets in Secret Manager.

---

## Quick test checklist

1. Agent starts without errors.
2. SharePoint files are listed.
3. Google Drive files are listed.
4. File selection prompt appears.
5. Email sends with attachment.
6. Purview label appears when configured.
7. External send block works for restricted labels.

---

## Important safety notes

1. Never commit your `.env` file.
2. Never commit your Google service account JSON key.
3. Rotate secrets regularly.
4. Use least-privilege permissions in both Microsoft and Google.

---

## Main project files

1. `main.py` - starts the agent
2. `src/gcp_agent/agent.py` - workflow logic
3. `src/gcp_agent/auth.py` - Entra auth
4. `src/gcp_agent/sharepoint_client.py` - SharePoint access
5. `src/gcp_agent/google_drive_client.py` - Drive access
6. `src/gcp_agent/purview_client.py` - Purview lookup
7. `src/gcp_agent/email_client.py` - Graph email sending
8. `.env.example` - all environment variables
