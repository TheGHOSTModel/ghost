# Self-Deployment Guide

This guide covers deploying the GHOST Live Simulation and Threat Radar to your own AWS account. The stack is fully defined in `cloudlaunch/` and deployed with a single script.

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| AWS account | Any region supported; stack defaults to `eu-central-1` |
| AWS CLI | Configured with credentials that have CloudFormation, Lambda, S3, DynamoDB, CloudFront, API Gateway, IAM permissions |
| AWS SAM CLI | `pip install aws-sam-cli` |
| Python 3.13 | Required by SAM's runtime validator — [python.org/downloads](https://www.python.org/downloads/) |
| An LLM API key | Any OpenAI-compatible endpoint (see [Bring Your Own LLM](#bring-your-own-llm) below) |

---

## Quick Start

```bash
git clone https://github.com/TheGHOSTModel/ghost.git
cd ghost/cloudlaunch

export GHOST_AI_KEY="your-api-key-here"
bash deploy.sh
```

That's it. The script builds, deploys, uploads the frontend, and prints the URL.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GHOST_AI_KEY` | Yes | API key for your chosen LLM endpoint |
| `GHOST_DOMAIN` | No | Custom domain e.g. `example.com` — leave unset to use the CloudFront default `*.cloudfront.net` URL |
| `GHOST_ACM_ARN` | If domain set | ACM certificate ARN — **must be in `us-east-1`** regardless of stack region |
| `GHOST_HOSTED_ZONE` | If domain set | Route53 Hosted Zone ID for the domain |
| `AWS_DEFAULT_REGION` | No | Defaults to `eu-central-1` |

### Without a custom domain

```bash
export GHOST_AI_KEY="your-api-key-here"
bash deploy.sh
# → App is live at https://<random>.cloudfront.net
```

### With a custom domain

```bash
export GHOST_AI_KEY="your-api-key-here"
export GHOST_DOMAIN="example.com"
export GHOST_ACM_ARN="arn:aws:acm:us-east-1:123456789012:certificate/..."
export GHOST_HOSTED_ZONE="Z1234567890ABC"
bash deploy.sh
# → App is live at https://example.com
```

---

## Bring Your Own LLM

The GHOST AI harm-detection component uses an **OpenAI-compatible chat completions API**. No code changes are needed — you configure it via SAM parameters or environment variables.

### Parameters

| Parameter | Environment variable | Default | Description |
|-----------|---------------------|---------|-------------|
| `GHOST_AI_API_KEY` | `GHOST_AI_KEY` | *(required)* | Bearer token for your LLM endpoint |
| `GHOST_AI_PROVIDER` | set in `template.yaml` | `cerebras` | Label only — does not affect routing |
| `GHOST_AI_MODEL` | set in `template.yaml` | `gpt-oss-120b` | Model name sent in the API request |
| `GHOST_AI_BASE_URL` | set in `template.yaml` | `https://api.cerebras.ai/v1` | Base URL of the chat completions endpoint |

To use a different provider, update the three `GHOST_AI_*` environment variables in `cloudlaunch/template.yaml` under `ApiFunction → Environment → Variables` before deploying:

```yaml
GHOST_AI_BASE_URL: "https://api.openai.com/v1"
GHOST_AI_MODEL:    "gpt-4o-mini"
```

Then pass your key at deploy time as usual via `GHOST_AI_KEY`.

### Compatible providers

Any provider that implements `POST /v1/chat/completions` with OpenAI request/response format works out of the box:

| Provider | Base URL | Example model |
|----------|----------|---------------|
| **Cerebras** *(default)* | `https://api.cerebras.ai/v1` | `gpt-oss-120b` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| Groq | `https://api.groq.com/openai/v1` | `llama-3.1-8b-instant` |
| Ollama (local) | `http://localhost:11434/v1` | `llama3.1` |
| AWS Bedrock (via proxy) | Your proxy URL | Any supported model |
| Azure OpenAI | `https://<resource>.openai.azure.com/openai/deployments/<deployment>` | `gpt-4o` |

### Running without any LLM

GHOST AI only activates when a **minor player flag** is set on a session participant. If no API key is provided, the harm-detection step is silently skipped and everything else (game, telemetry, threat radar) works normally.

---

## What Gets Deployed

```
Route53 (optional, if GHOST_DOMAIN set)
    └── A-alias → CloudFront

CloudFront Distribution
    └── Private S3 bucket (static frontend)
    └── API Gateway → Lambda

Lambda (Python 3.13)
    ├── Game: session management, GHOST rule evaluation, AI harm detection
    └── Threats: feed aggregation, classification, geo-location

DynamoDB Table
    └── Game sessions with automatic TTL expiry

S3 Buckets
    ├── Frontend (private, CloudFront OAC only)
    └── Threat data (threats.json refreshed every 4 hours)
```

Full architecture detail: [architecture.md](./architecture.md)

---

## Updating After Deploy

Re-run `deploy.sh` at any time — it is fully idempotent. CloudFormation updates only changed resources; the frontend is re-synced and the CloudFront cache is invalidated automatically.

---

## Tearing Down

```bash
aws cloudformation delete-stack --stack-name ghost-framework --region eu-central-1

# Empty the S3 buckets first (CloudFormation cannot delete non-empty buckets)
aws s3 rm s3://<frontend-bucket> --recursive
aws s3 rm s3://<threat-bucket> --recursive
aws cloudformation delete-stack --stack-name ghost-framework --region eu-central-1
```

---

## Cost Estimate

For a demo or low-traffic deployment all resources fall within or close to the AWS free tier:

| Resource | Free tier | Typical demo usage |
|----------|-----------|-------------------|
| Lambda | 1M requests / month | < 10k |
| DynamoDB | 25 GB + 200M requests / month | Negligible |
| S3 | 5 GB + 20k GET / month | Negligible |
| CloudFront | 1 TB transfer + 10M requests / month | < 1k |
| API Gateway | 1M HTTP API calls / month | < 10k |

LLM API costs depend on your chosen provider and usage volume. At 256 max tokens per analysis call, costs are minimal for demo use.
