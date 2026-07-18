# GCP Document Routing Agent — Complete Beginner Guide

> **Written for beginners.** Follow every step in order. You can copy and paste
> every command exactly as shown.

---

## What this agent does

1. Reads files from your **SharePoint** document library.
2. Reads files from your **Google Drive** folder.
3. Shows you a numbered list of all files and asks which one to send.
4. Asks you for the **recipient email address**.
5. Sends the file as an email attachment through **Microsoft Graph**.
6. *(Optional)* Checks **Purview sensitivity labels** and blocks sending restricted files to external addresses.
7. *(Optional)* Runs **Purview DLP middleware enforcement** (Agent Framework pattern) before every send.

---

## SDKs used in this repository

| SDK | Package | Purpose |
|-----|---------|---------|
| Entra ID SDK | `azure-identity` | App authentication to Microsoft 365 |
| Purview catalog SDK | `azure-purview-catalog` | Sensitivity label lookup |
| Purview policy middleware | `agent-framework-purview` | DLP enforcement before email send |
| Agent Framework core | `agent-framework` | Middleware pipeline |
| Agent Framework Foundry | `agent-framework-foundry` | Chat client for `purview_test.py` |
| SharePoint SDK | `office365-rest-python-client` | File inventory + download |
| Agent 365 observability | `microsoft-agents-a365-observability-core` | Telemetry |
| Google Drive SDK | `google-api-python-client` | Google Drive inventory + download |

---

## Files in this repository

| File | What it does |
|------|--------------|
| `main.py` | Starts the agent |
| `purview_test.py` | Standalone Purview DLP validation test |
| `src/gcp_agent/agent.py` | Workflow logic — inventory, select, enforce, send |
| `src/gcp_agent/auth.py` | Entra ID authentication |
| `src/gcp_agent/sharepoint_client.py` | SharePoint file listing + download |
| `src/gcp_agent/google_drive_client.py` | Google Drive listing + download |
| `src/gcp_agent/purview_client.py` | Purview sensitivity label lookup |
| `src/gcp_agent/purview_policy_enforcer.py` | Purview DLP middleware enforcement |
| `src/gcp_agent/email_client.py` | Graph `sendMail` with attachment |
| `src/gcp_agent/a365.py` | Agent 365 observability bootstrap |
| `.env.example` | Template — copy to `.env` and fill in |
| `scripts/Create-DlpPolicyForCustomAIApps.ps1` | PowerShell script to create Purview DLP policy (from [microsoft/purview-api-samples](https://github.com/microsoft/purview-api-samples/tree/main/DLPforCustomAIApps)) |

---

## Before you start — what you need

1. A **Windows, macOS, or Linux** computer.
2. A **Microsoft 365 tenant** where you are (or can ask) an admin.
3. A **Google Cloud project** where you can create service accounts.
4. **Python 3.11 or newer** installed (not 3.9 or 3.10 — some packages need 3.11).
5. **Git** installed.

---

## Quick start (copy/paste — fastest path)

### macOS or Linux

Open Terminal and paste this line by line:

```bash
git clone https://github.com/mward-msft1/gcp_agent.git
cd gcp_agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Then open the `.env` file you just created, fill in your values (see Part D), and run:

```bash
python main.py
```

### Windows PowerShell

Open PowerShell and paste this line by line:

```powershell
git clone https://github.com/mward-msft1/gcp_agent.git
cd gcp_agent
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
```

Then open `.env`, fill in your values (see Part D), and run:

```powershell
python main.py
```

---

## Part A — Install tools on your local PC

### Step A1 — Install Python 3.11+

1. Go to https://www.python.org/downloads/
2. Download **Python 3.11** or newer.
3. Run the installer.  
   **Windows:** check ✅ "Add Python to PATH" during install.
4. Confirm install:

```bash
python3 --version
```

You should see `Python 3.11.x` or higher.

### Step A2 — Install Git

1. Go to https://git-scm.com/downloads
2. Download and install Git.
3. Confirm:

```bash
git --version
```

### Step A3 — (Optional, needed for cloud deploy) Install Google Cloud SDK

1. Go to https://cloud.google.com/sdk/docs/install
2. Follow the install steps for your OS.
3. Confirm:

```bash
gcloud --version
```

---

## Part B — Microsoft 365 setup

> You need to do this once in your Microsoft 365 tenant. If you are not the admin,
> ask your admin to do Steps B1–B4 for you.

### Step B1 — Register an Entra application

1. Open https://entra.microsoft.com
2. Click **App registrations** (in the left sidebar under "Applications").
3. Click **+ New registration**.
4. Fill in:
   - **Name:** `gcp-document-routing-agent`  *(you can use any name)*
   - **Supported account types:** Accounts in this organizational directory only
5. Click **Register**.

> You are now on the app overview page. Leave this page open.

### Step B2 — Copy your app's IDs

On the app overview page, copy:

1. **Application (client) ID** → this is your `ENTRA_CLIENT_ID`
2. **Directory (tenant) ID** → this is your `ENTRA_TENANT_ID`

Save both values in a text file. You will need them in Part D.

### Step B3 — Create a client secret

1. On the same app page, click **Certificates & secrets** (left sidebar).
2. Click **+ New client secret**.
3. Give it a description (example: `gcp-agent-secret`).
4. Choose an expiry (example: 12 months).
5. Click **Add**.
6. **Copy the secret value immediately** — it will only be shown once.

Save this as your `ENTRA_CLIENT_SECRET`.

### Step B4 — Add Microsoft Graph permissions

1. Click **API permissions** (left sidebar).
2. Click **+ Add a permission**.
3. Choose **Microsoft Graph** → **Application permissions**.
4. Search for and add each of these:

   | Permission | Why it is needed |
   |------------|-----------------|
   | `Mail.Send` | Send email |
   | `Sites.Read.All` | Read SharePoint files |
   | `Files.Read.All` | Read file contents |
   | `User.Read.All` | Look up user info |

5. Click **Add permissions**.
6. Click **Grant admin consent for [your tenant]**.
7. Click **Yes** to confirm.

All permissions should now show a green ✅ checkmark.

### Step B5 — (If using Purview DLP) Add Purview permissions

Skip this step if you are not using `ENABLE_PURVIEW_POLICY_ENFORCEMENT=true`.

1. In the same **API permissions** page, click **+ Add a permission**.
2. Choose **Microsoft Graph** → **Application permissions**.
3. Search for and add:

   | Permission | Why it is needed |
   |------------|-----------------|
   | `ProtectionScopes.Compute.All` | Compute Purview protection scopes |
   | `Content.Process.All` | DLP content evaluation |
   | `ContentActivity.Write` | DLP audit logging |

4. Click **Grant admin consent** again.

> **Note:** These permissions may not appear in your tenant if you do not have a
> Microsoft 365 E5 or equivalent Purview license. See Step B7 for alternatives.

### Step B6 — Get your SharePoint details

You need these for `.env`:

1. **`SHAREPOINT_SITE_URL`** — the URL of your SharePoint site.  
   Example: `https://contoso.sharepoint.com/sites/YourSite`  
   *(Get it by opening the site in your browser and copying the URL up to the site name.)*

2. **`SHAREPOINT_FOLDER_SERVER_RELATIVE`** — the server-relative path to the folder.  
   Example: `/sites/YourSite/Shared Documents`  
   *(In SharePoint, hover over the folder → Copy link → the path is visible in the URL.)*

3. **`GRAPH_SENDER_UPN`** — the email address of the mailbox the agent will send from.  
   Example: `automation@contoso.com`  
   *(This must be a licensed mailbox in your tenant.)*

### Step B7 — (If using Purview DLP) Set up a Purview DLP policy

This step lets you see the `BLOCKED` outcome when running `purview_test.py`.
If you skip it, the test still runs but every message will show `ALLOWED`.

**What to do:**

1. Open https://compliance.microsoft.com
2. Click **Data loss prevention** → **Policies**.
3. Click **+ Create policy**.
4. Choose **Custom policy** → **Custom** → **Next**.
5. Name it `Block Credit Card in AI Apps` → **Next**.
6. On "Assign admin units" → **Next** (leave default).
7. On "Choose locations" — enable **Microsoft 365 Copilot and AI apps** → **Next**.
8. On "Define policy settings" → choose **Create or customize advanced DLP rules** → **Next**.
9. Click **+ Create rule**.
10. Name it `Block credit card`.
11. Under **Conditions** → **+ Add condition** → **Content contains** → **Sensitive info types** → search and add **Credit Card Number**.
12. Under **Actions** → **+ Add action** → **Restrict access** → **Block everyone**.
13. Click **Save** → **Next** → **Next**.
14. On "Policy mode" → choose **Turn it on right away** → **Next**.
15. Click **Submit**.

> Policy activation can take up to 24 hours. Run `purview_test.py` the next day to
> see the `BLOCKED` result for the credit card scenario.

### Step B8 — Create the DLP policy with PowerShell (recommended — fastest, most precise)

> **Source:** [microsoft/purview-api-samples — DLPforCustomAIApps](https://github.com/microsoft/purview-api-samples/tree/main/DLPforCustomAIApps)  
> The script is included in this repo at `scripts/Create-DlpPolicyForCustomAIApps.ps1`.

This PowerShell script does everything Step B7 does — and more — in under 2 minutes.
It creates a DLP policy scoped **directly to your Entra app registration** (not just
"all Copilot apps"), sets up block rules for 6 sensitive info types, and wires up
alerts and incident reports.

> **You need:**
> - PowerShell 7+ (not Windows PowerShell 5)
> - A Microsoft 365 account with **Compliance Administrator** or **Compliance Data Administrator** role
> - Your Entra **Application (client) ID** (from Step B2)

#### Quick start (copy/paste)

**Step 1 — Install PowerShell 7** (skip if already installed):

```powershell
winget install --id Microsoft.PowerShell --source winget
```

Or download from https://aka.ms/PSWindows

**Step 2 — Install the Exchange Online Management module:**

```powershell
Install-Module ExchangeOnlineManagement -Scope CurrentUser
```

**Step 3 — Open `scripts/Create-DlpPolicyForCustomAIApps.ps1` in any text editor and edit these 3 lines:**

```powershell
# Line to find:             What to change it to:
$DlpPolicyName = "Contoso Custom AI Apps - Block Sensitive Data"  # change "Contoso" to your org name
$Applications = @(
    @{
        AppId   = "11111111-1111-1111-1111-111111111111"   # <-- REPLACE with your ENTRA_CLIENT_ID
        AppName = "GCP Document Routing Agent"              # <-- optional: change display name
    }
)
```

Your `ENTRA_CLIENT_ID` is the same GUID you saved in Step B2.

**Step 4 — Run the script:**

```powershell
cd path\to\gcp_agent
.\scripts\Create-DlpPolicyForCustomAIApps.ps1
```

A browser window opens — sign in with your **Compliance Administrator** account.

**Step 5 — Confirm it worked:**

The script prints the created policy at the end. You should see:

```
Verification:
Name              : Contoso Custom AI Apps - Block Sensitive Data
Mode              : Enable
EnforcementPlanes : {Application}
...
Name          : Block sensitive info in custom AI apps
Policy        : Contoso Custom AI Apps - Block Sensitive Data
RestrictAccess: {UploadText=Block, DownloadText=Block}
```

Also confirm in the Microsoft Purview portal:  
https://compliance.microsoft.com → **Data Loss Prevention** → **Policies**

#### What the script creates

| Setting | Value |
|---------|-------|
| Policy scope | Your Entra app only (not all M365 apps) |
| Action | **Block** (UploadText + DownloadText) |
| Sensitive info types | Credit Card, SSN, Bank Account, ITIN, Passport, IBAN |
| Alerts | Sent to `SiteAdmin` (configurable) |
| Incident report | Severity High, sent to `SiteAdmin` |
| Mode | Enable (active immediately) |

#### Customising the script

Open the `# Configuration` section at the top of the script and edit these variables:

| Variable | What to change |
|----------|---------------|
| `$DlpPolicyName` | Friendly name in the Purview portal |
| `$DlpRuleName` | Friendly name for the rule |
| `$PolicyMode` | `Enable` (active), `TestWithNotifications`, `TestWithoutNotifications`, `Disable` |
| `$RestrictAction` | `Block` to deny, `Audit` to log only |
| `$Applications` | Add more `@{AppId=...; AppName=...}` entries for additional apps |
| `$AlertRecipients` | `@("SiteAdmin")` or `@("admin@contoso.com")` |
| `$SensitiveTypes` | Add or remove sensitive info type names |

#### Test the block after the policy is active

After the policy is active (allow up to 1 hour), run `purview_test.py` (Part F).
The "expected block" scenario sends a message containing `4111 1111 1111 1111` — a
test credit card number. If the policy is active, you will see `BLOCKED`.

#### Remove the policy (cleanup)

```powershell
# Uncomment these two lines at the bottom of the script, or run directly:
Remove-DlpComplianceRule   -Identity "Block sensitive info in custom AI apps" -Confirm:$false
Remove-DlpCompliancePolicy -Identity "Contoso Custom AI Apps - Block Sensitive Data" -Confirm:$false
```

---

## Part C — Google setup

### Step C1 — Create a Google Cloud project

1. Open https://console.cloud.google.com
2. Click the project selector (top left) → **New Project**.
3. Name it (example: `document-routing-agent`).
4. Click **Create**.

### Step C2 — Enable the Google Drive API

1. In Google Cloud Console, go to **APIs & Services** → **Library**.
2. Search for **Google Drive API**.
3. Click it → **Enable**.

### Step C3 — Create a service account

1. Go to **IAM & Admin** → **Service Accounts**.
2. Click **+ Create Service Account**.
3. Name it (example: `drive-reader`).
4. Click **Create and Continue** → **Done**.

### Step C4 — Download the key file

1. Click on the service account you just created.
2. Go to **Keys** tab → **Add Key** → **Create new key**.
3. Choose **JSON** → **Create**.
4. A JSON file downloads to your computer. Save its **full absolute path**.

This path is your `GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE`.

### Step C5 — Share your Drive folder with the service account

1. Open **Google Drive** in your browser.
2. Right-click the folder you want the agent to read.
3. Click **Share**.
4. Paste the service account email (found in Google Cloud Console, it looks like `name@project.iam.gserviceaccount.com`).
5. Set role to **Viewer**.
6. Click **Send**.

### Step C6 — Get the folder ID

1. Open the Google Drive folder in your browser.
2. The URL looks like: `https://drive.google.com/drive/folders/1A2B3C4D5E6F...`
3. Copy the long string after `/folders/`.

This is your `GOOGLE_DRIVE_FOLDER_ID`.

---

## Part D — Configure your `.env` file

### Step D1 — Copy the template

**macOS/Linux:**
```bash
cp .env.example .env
```

**Windows:**
```powershell
copy .env.example .env
```

### Step D2 — Open `.env` and fill in your values

Open the file in any text editor (Notepad, VS Code, etc.) and replace every placeholder.

Here is the full template you can paste in — replace everything after `=`:

```env
# ── Required ────────────────────────────────────────────────
ENTRA_TENANT_ID=paste-your-directory-tenant-id-here
ENTRA_CLIENT_ID=paste-your-application-client-id-here
ENTRA_CLIENT_SECRET=paste-your-client-secret-value-here

SHAREPOINT_SITE_URL=https://contoso.sharepoint.com/sites/YourSite
SHAREPOINT_FOLDER_SERVER_RELATIVE=/sites/YourSite/Shared Documents

GRAPH_SENDER_UPN=automation@contoso.com

GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE=/full/path/to/service-account.json
GOOGLE_DRIVE_FOLDER_ID=paste-your-google-drive-folder-id-here

# ── Optional – Purview catalog label lookup ─────────────────
PURVIEW_ENDPOINT=

# ── Optional – Outbound policy (label-based blocking) ───────
ALLOWED_RECIPIENT_DOMAINS=contoso.com
BLOCKED_PURVIEW_LABELS=confidential,secret,restricted

# ── Optional – Purview DLP middleware enforcement ───────────
ENABLE_PURVIEW_POLICY_ENFORCEMENT=false
PURVIEW_DEFAULT_USER_ID=
PURVIEW_APP_NAME=DocumentRoutingAgent
PURVIEW_IGNORE_EXCEPTIONS=false
PURVIEW_IGNORE_PAYMENT_REQUIRED=false

# Entra app used for Purview auth (can be same as ENTRA_CLIENT_ID)
PURVIEW_CLIENT_APP_ID=paste-your-application-client-id-here

# Set to true for certificate auth (headless/production)
PURVIEW_USE_CERT_AUTH=false
PURVIEW_TENANT_ID=
PURVIEW_CERT_PATH=
PURVIEW_CERT_PASSWORD=

# ── Optional – Azure AI Foundry (for purview_test.py) ───────
FOUNDRY_PROJECT_ENDPOINT=
FOUNDRY_MODEL=gpt-4o-mini

# ── Optional – Agent 365 observability ─────────────────────
ENABLE_A365_OBSERVABILITY=true
OBSERVABILITY_SERVICE_NAME=DocumentRoutingAgent
OBSERVABILITY_SERVICE_NAMESPACE=GCPAgent
```

### Step D3 — Enable Purview DLP enforcement (recommended before sharing with customers)

Once you have completed Steps B5 and B7, turn on the middleware:

```env
ENABLE_PURVIEW_POLICY_ENFORCEMENT=true
PURVIEW_DEFAULT_USER_ID=paste-an-entra-user-object-id-guid-here
PURVIEW_CLIENT_APP_ID=paste-your-application-client-id-here
```

> **How to find a user object ID:**  
> Go to https://entra.microsoft.com → Users → click a user → copy "Object ID".

---

## Part E — Run the agent locally

### Step E1 — Activate your virtual environment

**macOS/Linux:**
```bash
source .venv/bin/activate
```

**Windows:**
```powershell
.venv\Scripts\Activate.ps1
```

### Step E2 — Start the agent

```bash
python main.py
```

### Step E3 — Follow the prompts

The agent will:

1. List files from SharePoint (numbered).
2. List files from Google Drive (numbered, continuing from SharePoint count).
3. Ask: `Enter the number of the file to send:`
4. Ask: `Enter recipient email address:`
5. Ask: `Enter email subject (press Enter for default):`
6. Send the email and confirm.

---

## Part F — Validate your Purview DLP policies with `purview_test.py`

This standalone test script mirrors the official Microsoft Agent Framework sample:  
https://github.com/microsoft/agent-framework/tree/main/python/samples/05-end-to-end/purview_agent

### What it tests

It sends three messages through a Purview-enabled agent pipeline:

| Message | Expected outcome |
|---------|-----------------|
| Harmless joke | `ALLOWED` |
| Contains a test credit card number | `BLOCKED` (only if you set up Step B7) |
| Another harmless joke | `ALLOWED` |

### Step F1 — Set the required env var

In your `.env`:
```env
PURVIEW_CLIENT_APP_ID=paste-your-application-client-id-here
```

### Step F2 — (Optional) Set Foundry endpoint for full scenarios

If you have an Azure AI Foundry resource, add:
```env
FOUNDRY_PROJECT_ENDPOINT=https://your-foundry-resource.openai.azure.com/
FOUNDRY_MODEL=gpt-4o-mini
```

Without this, the Foundry-based scenarios will show `SKIPPED` — that is normal.

### Step F3 — Run the test

**macOS/Linux:**
```bash
source .venv/bin/activate
python purview_test.py
```

**Windows:**
```powershell
.venv\Scripts\Activate.ps1
python purview_test.py
```

A **browser window will open** (first time only) so you can sign in with your Microsoft 365 account. This is normal — it is using interactive browser authentication.

### Step F4 — Read the results

```
── Scenario 3: Custom Cache Provider ────────────────────────
  [Cache] MISS ...
  [custom cache] good (cold cache): ALLOWED
  [custom cache] expected block: BLOCKED
  [custom cache] good (warm cache): ALLOWED
```

- `ALLOWED` = content passed Purview evaluation.
- `BLOCKED` = a DLP policy in your tenant blocked the content.
- If "expected block" shows `ALLOWED`, your DLP policy may not be active yet (wait up to 24 hours after Step B7).

---

## Part G — Use this as a true third-party Google-hosted agent

This is how a **Google-hosted agent** can access your **Microsoft 365 tenant** —
the two clouds are completely separate.

### Step G1 — Enable required Google Cloud APIs

In Google Cloud Console → **APIs & Services** → **Library**, enable:

1. Cloud Run Admin API
2. Cloud Build API
3. Artifact Registry API
4. Secret Manager API
5. IAM API

### Step G2 — Store secrets in Secret Manager

Never put secrets in your source code or Cloud Run environment variables directly.
Use Secret Manager instead:

```bash
# Entra client secret
echo -n "your-client-secret" | \
  gcloud secrets create entra-client-secret --data-file=-

# Google service account key file
gcloud secrets create google-sa-key \
  --data-file=/path/to/service-account.json
```

### Step G3 — Deploy to Cloud Run

```bash
gcloud run deploy document-routing-agent \
  --source . \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated
```

### Step G4 — Add environment variables in Cloud Run

In Cloud Run → your service → **Edit & Deploy New Revision** → **Variables & Secrets**,
add each env var from your `.env` file (point to Secret Manager secrets where applicable).

### Step G5 — Confirm network access

Your Cloud Run service needs outbound HTTPS to:

- `graph.microsoft.com` — Microsoft Graph (email + SharePoint)
- `login.microsoftonline.com` — Entra authentication
- `*.sharepoint.com` — SharePoint files
- `purview.microsoft.com` — Purview DLP (if enabled)
- `www.googleapis.com` — Google Drive API
- your Azure AI Foundry endpoint (if using `purview_test.py`)

---

## Part H — Integrate with Google AI Platform (ADK / Vertex AI Agent Builder)

Current code is CLI-interactive. To turn it into a conversational Google AI agent:

### Architecture

```
User in Google AI Agent
        ↓
  ADK tool call → this Python code (Cloud Run)
        ↓
SharePoint inventory + Google Drive inventory
        ↓
Return document list to Google AI
        ↓
User picks file + recipient
        ↓
  ADK tool call → send_email endpoint
        ↓
Purview DLP check → Graph sendMail
        ↓
Email delivered to recipient
```

### Steps

1. Wrap `agent.list_documents()` as an ADK `Tool` returning a list of dicts.
2. Wrap `agent.send_document(file_number, recipient, subject)` as an ADK `Tool`.
3. Deploy both tools as a Cloud Run HTTP service.
4. Register the Cloud Run URL as an OpenAPI extension in Vertex AI Agent Builder or Google ADK.
5. Secrets stay in Google Secret Manager — no credentials leave GCP.

---

## Quick validation checklist

Run through this before handing off to a customer:

- [ ] `python main.py` starts without errors.
- [ ] SharePoint files appear in the list.
- [ ] Google Drive files appear in the list.
- [ ] Selecting a file and entering an email sends the attachment.
- [ ] (If Purview enabled) Files with blocked labels are rejected before send.
- [ ] `scripts/Create-DlpPolicyForCustomAIApps.ps1` runs and creates the policy in Purview.
- [ ] `python purview_test.py` runs all 4 scenarios without crashing.
- [ ] `purview_test.py` shows `BLOCKED` for credit card message (after Step B7 policy activates).
- [ ] `.env` is NOT committed to the repo (run `git status` — it must not appear).

---

## Safety rules — do not skip these

1. **Never commit your `.env` file.** It contains your secrets.
2. **Never commit your Google service account JSON key.** Keep it local.
3. **Rotate your Entra client secret** before it expires (you set an expiry in Step B3).
4. **Use the minimum required permissions** — only add permissions you actually use.
5. **In production**, store all secrets in Google Secret Manager or Azure Key Vault — never as plain text.

