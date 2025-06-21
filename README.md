# Prompt Deployment Pipeline with Amazon Bedrock & S3 Static Website Hosting

> **Purpose:** Automate the generation of rich HTML content using Amazon Bedrock (Claude 3) and publish it to version‑controlled **beta** and **prod** S3 static website buckets through a GitHub‑based CI/CD pipeline.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Project Structure](#project-structure)
3. [AWS Resource Setup](#aws-resource-setup)

   * 3.1 [Create S3 Buckets for Static Website Hosting](#31-create-s3-buckets-for-static-website-hosting)
   * 3.2 [Grant Bedrock Access](#32-grant-bedrock-access)
   * 3.3 [Create IAM Roles / Policies](#33-create-iam-roles--policies)
4. [Local Development Setup](#local-development-setup)
5. [GitHub Repository & Secrets](#github-repository--secrets)
6. [Creating Templates & Variable Configs](#creating-templates--variable-configs)
7. [Running Locally](#running-locally)
8. [CI/CD Workflow](#cicd-workflow)

   * 8.1 [Workflow Triggers](#81-workflow-triggers)
   * 8.2 [Workflow File Overview](#82-workflow-file-overview)
9. [Viewing Published Output](#viewing-published-output)
10. [Cleanup](#cleanup)
11. [Troubleshooting & FAQ](#troubleshooting--faq)

---

## Prerequisites

* **AWS Account** with Bedrock enabled in your chosen region (e.g., `us-east-1`).
* **GitHub Account** with repository created.
* **Python 3.10+** (local use or GitHub Actions runner).
* **AWS CLI v2** configured **or** GitHub OIDC role set up for Actions.
* IAM permissions:

  * `s3:PutObject`, `s3:GetObject`, `s3:ListBucket` on deployment buckets.
  * `bedrock:InvokeModel` on the required Bedrock model.

---

## Project Structure

```
prompt-deployment-pipeline/
├─ .github/workflows/deploy.yml      # CI/CD pipeline
├─ generate_and_upload.py           # Core automation script
├─ prompts/                         # JSON variable files
│   └─ welcome_prompt.json
├─ prompt_templates/                # Jinja2 templates (*.txt)
│   └─ welcome.txt
├─ outputs/                         # Locally rendered files (git‑ignored)
└─ README.md
```

---

## AWS Resource Setup

### 3.1 Create S3 Buckets for Static Website Hosting

1. **Bucket names** (globally unique):

   * `my‑company‑beta‑site`
   * `my‑company‑prod‑site`
2. Enable **Static website hosting** (Objects > Properties > Static website).
3. Set **index document** to `index.html`.
4. **Bucket policy** (public read):

```json
{
  "Version":"2012-10-17",
  "Statement":[{
    "Effect":"Allow",
    "Principal":"*",
    "Action":["s3:GetObject"],
    "Resource":["arn:aws:s3:::my-company-beta-site/*"]
  }]
}
```

> 🔒 *For production, consider CloudFront + OAI instead of public buckets.*

### 3.2 Grant Bedrock Access

Bedrock is region‑locked; request service access:

1. Sign in to the **AWS Console > Bedrock**.
2. Opt‑in to model access (e.g., *Anthropic Claude 3 Sonnet*).
3. Attach the following policy to your GitHub OIDC role or IAM user:

```json
{
  "Version":"2012-10-17",
  "Statement":[{
    "Effect":"Allow",
    "Action":"bedrock:InvokeModel",
    "Resource":"*"   // narrow to specific model ARN in production
  }]
}
```

### 3.3 Create IAM Roles / Policies

| Use‑case           | Method                                                                                                                                                                                                                        |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Local testing**  | Create an **IAM User** with programmatic keys & attach the S3 + Bedrock policy. Configure via `aws configure`.                                                                                                                |
| **GitHub Actions** | Create an **OIDC role** that trusts `token.actions.githubusercontent.com`. Add the S3 + Bedrock policy. Reference this role in your workflow using [AWS OIDC docs](https://github.com/aws-actions/configure-aws-credentials). |

---

## Local Development Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # boto3, jinja2, python‑dotenv (optional)
export AWS_REGION=us-east-1
export S3_BUCKET_BETA=my-company-beta-site
export S3_BUCKET_PROD=my-company-prod-site
export DEPLOY_ENV=beta
python generate_and_upload.py     # renders & uploads
```

---

## GitHub Repository & Secrets

1. **Secrets > Actions** → `New repository secret`.
2. Add:

   | Name             | Example Value                                   |
   | ---------------- | ----------------------------------------------- |
   | `AWS_ROLE_ARN`   | `arn:aws:iam::123456789012:role/GitHubOIDCRole` |
   | `AWS_REGION`     | `us-east-1`                                     |
   | `S3_BUCKET_BETA` | `my-company-beta-site`                          |
   | `S3_BUCKET_PROD` | `my-company-prod-site`                          |
3. If using access keys instead of OIDC (not recommended), add `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`.

---

## Creating Templates & Variable Configs

### ✏️ Prompt Template (`prompt_templates/welcome.txt`)

```txt
Hello {{ name }},
Welcome to **{{ company }}**! We’re thrilled to have you.
```

### 🔧 Variable Config (`prompts/welcome_prompt.json`)

```json
{
  "output_file": "welcome_{{ name | lower }}.html",
  "variables": {
    "name": "Jordan",
    "company": "Aurora Digital"
  },
  "make_index": true
}
```

**Rules:**

* Filename convention: `<topic>_prompt.json`.
* Must contain `output_file`, `variables`, and **optional** `make_index` flag.

---

## Running Locally

```bash
# Beta
DEPLOY_ENV=beta python generate_and_upload.py
# Production
DEPLOY_ENV=prod python generate_and_upload.py
```

Logs show uploaded keys. Confirm via:

```bash
aws s3 ls s3://$S3_BUCKET_BETA --recursive | head
```

---

## CI/CD Workflow

### 8.1 Workflow Triggers

* **Pull Request to `main`** → Lints & dry‑runs script.
* **Merge to `main`** → Runs script against **prod** bucket.
* **Merge to any other branch** → Runs script against **beta** bucket.

### 8.2 Workflow File Overview (`.github/workflows/deploy.yml`)

```yaml
name: Deploy Prompt Output
on:
  pull_request:
  push:
    branches: [ main ]

jobs:
  build-deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write   # OIDC
      contents: read
    steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: "3.11"
    - uses: aws-actions/configure-aws-credentials@v4
      with:
        role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
        aws-region: ${{ secrets.AWS_REGION }}
    - name: Install deps
      run: pip install boto3 jinja2
    - name: Determine environment
      id: env
      run: |
        if [[ "${{ github.ref }}" == "refs/heads/main" ]]; then
          echo "DEPLOY_ENV=prod" >> $GITHUB_ENV
        else
          echo "DEPLOY_ENV=beta" >> $GITHUB_ENV
        fi
    - name: Run script
      env:
        S3_BUCKET_BETA: ${{ secrets.S3_BUCKET_BETA }}
        S3_BUCKET_PROD: ${{ secrets.S3_BUCKET_PROD }}
      run: python generate_and_upload.py
```

---

## Viewing Published Output

1. **Find website endpoint** under *S3 > Properties > Static website hosting*.

   * Beta: `http://my-company-beta-site.s3-website-us-east-1.amazonaws.com`
   * Prod: `http://my-company-prod-site.s3-website-us-east-1.amazonaws.com`
2. Browse to `/index.html` or any generated file path printed in the script logs.
3. For CDN‑backed prod, use the CloudFront domain if configured.

---

## Cleanup

```bash
aws s3 rb s3://my-company-beta-site --force
aws s3 rb s3://my-company-prod-site --force
# Delete IAM user/role or detach policies when finished.
```

---

## Troubleshooting & FAQ

| Symptom                                          | Possible Cause                             | Fix                                                 |
| ------------------------------------------------ | ------------------------------------------ | --------------------------------------------------- |
| **403 Forbidden** when opening HTML              | Bucket policy or object ACL mis‑configured | Re‑apply public read policy or use CloudFront OAI.  |
| `AccessDeniedException` from Bedrock             | IAM policy missing `bedrock:InvokeModel`   | Attach Bedrock policy to role.                      |
| GitHub Actions fails `configure-aws-credentials` | OIDC trust not set                         | Add GitHub issuer to role trust policy.             |
| Empty HTML                                       | Template rendered blank                    | Check `variables` keys match template placeholders. |

---

© 2025 Adolphas Gwena 
