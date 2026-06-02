# GHOSTv2 — Production Readiness Checklist

Last updated: 2026-06-02  
Current deployment: CloudLaunch `app-4cfbec7d1a37` (us-east-1)  
Target: Full AWS deployment on custom domain

---

## 🔴 Blockers — must fix before going live

### 1. Move Cerebras API key out of template.yaml
**File:** `cloudlaunch/template.yaml:83`  
The key `REDACTED_API_KEY` is in plaintext and committed to git.  
**Fix:** Store in AWS Secrets Manager. Fetch at Lambda init via `boto3.client('secretsmanager')`.

### 2. Fix hardcoded S3 bucket name in frontend build
**File:** `cloudlaunch/frontend/patch_srcdoc.py:95`  
The fallback radar iframe URL hardcodes the current bucket name (`cloudlaunch-dev-byoa-app-4cfbec7d1a-frontendbucket-s4uyuxjjvvli`). This breaks on any fresh deployment because CloudFormation generates a new bucket name.  
**Fix:** Derive the S3 URL dynamically from `__CLOUDLAUNCH_CONFIG__.frontendUrl` only — remove the hardcoded fallback entirely.

### 3. Remove `verify=False` SSL in backend calls
**Files:** `cloudlaunch/backend/game/handler.py:285`, `cloudlaunch/backend/threats/handler.py:273`  
SSL verification is disabled for Cerebras AI calls and threat feed fetches. This was a corporate proxy workaround — not acceptable in production Lambda.  
**Fix:** Remove `verify=False`. AWS Lambda uses the standard Amazon cert bundle which trusts all major CAs.

---

## 🟡 Should fix before go-live

### 4. Enable DynamoDB TTL on SessionsTable
**File:** `cloudlaunch/template.yaml` (SessionsTable resource)  
The `ttl` field is written to every session item but the DynamoDB table has no TTL configuration. Stale sessions never auto-delete, storage bloats over time.  
**Fix:** Add to SessionsTable in template.yaml:
```yaml
TimeToLiveSpecification:
  AttributeName: ttl
  Enabled: true
```

### 5. Restrict CORS to custom domain
**File:** `cloudlaunch/template.yaml:54`, `cloudlaunch/template.yaml:39`  
Both the HTTP API and S3 bucket CORS use `AllowOrigins: ["*"]`. Fine for dev, not for production.  
**Fix:** Replace `"*"` with `["https://yourdomain.com"]` once domain is confirmed.

### 6. Move S3 frontend to CloudFront OAI (block public access)
**File:** `cloudlaunch/template.yaml:29-46`  
S3 bucket is publicly readable. For production, frontend should be served through CloudFront with an Origin Access Identity — block direct public S3 access.

---

## 🏗 New infrastructure needed for custom domain

### 7. Add CloudFront distribution
- Route `/api/*` → API Gateway (HTTP API)
- Route `/*` → S3 Frontend bucket via OAI
- Set default root object to `index.html`
- Enable HTTP→HTTPS redirect

### 8. ACM Certificate
- Request certificate for `yourdomain.com` and `www.yourdomain.com` in `us-east-1` (required for CloudFront)
- Add DNS validation records to Route53

### 9. Route53 DNS
- A record (alias) → CloudFront distribution
- CNAME `www` → CloudFront distribution

### 10. Add SAM Outputs for domain wiring
Add to `template.yaml` Outputs:
```yaml
FrontendBucketArn:
  Value: !GetAtt FrontendBucket.Arn
CloudFrontDistributionId:
  Value: !Ref CloudFrontDistribution  # once added
```

---

## ✅ Already good — no action needed

- DynamoDB session isolation and server-authoritative game logic
- Input validation on all API endpoints
- Telemetry + GHOST rule evaluation working
- Chat rate limiting (move, chat) per player
- EventBridge 4-hour threat feed refresh
- GHOST AI with Cerebras retry logic and busy error message
- REST polling replacing WebSockets (Lambda-compatible)
- S3 CORS configured for cross-origin radar iframe

---

## Deployment notes

**Current stack name:** `ghost-framework`  
**Region:** `us-east-1`  
**API URL:** `https://trl95o1hhc.execute-api.us-east-1.amazonaws.com`  
**S3 Frontend:** `cloudlaunch-dev-byoa-app-4cfbec7d1a-frontendbucket-s4uyuxjjvvli`  
**Model:** Cerebras `gpt-oss-120b`

**Estimated effort to production:** 1–2 days  
- Fix blockers 1–3: ~2 hours  
- DynamoDB TTL + CORS: 30 min  
- CloudFront + ACM + Route53 stack: ~4 hours  
- Testing on custom domain: ~2 hours
