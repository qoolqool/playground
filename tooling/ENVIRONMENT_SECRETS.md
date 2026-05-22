# Environment-Specific Secrets and Configuration

This directory contains files that are **environment-specific** and should **NOT be committed** to the public repository.

## Files to Keep Local

The following files are gitignored and must be provided locally:

| File | Purpose | How to Generate |
|------|---------|-----------------|
| `cloudflare-gateway.crt` | Cloudflare Gateway CA certificate for TLS interception | Download from Cloudflare dashboard or export from browser |
| `cloudflare.pem` | Alternative PEM format | Convert from `.crt` if needed |
| `.env` | Environment variables | Create from `.env.example` |

## Adding Cloudflare Gateway Certificate

If you need TLS interception behind Cloudflare WARP:

1. **Download the certificate:**
   - Go to Cloudflare Zero Trust Dashboard
   - Navigate to Settings → Certificates
   - Download the CA certificate

2. **Place in tooling directory:**
   ```bash
   cp ~/Downloads/cloudflare-gateway.crt /project/tooling/
   ```

3. **Build the image:**
   ```bash
   docker build -t my-image tooling/
   ```

The Dockerfile will automatically detect and include the certificate if present.

## Dockerfile Pattern for Optional Files

When adding environment-specific files to the Dockerfile, use this pattern:

```dockerfile
# Optional: Environment-specific CA certificate
# Copy if exists, skip if not (build won't fail)
COPY --chown=tool:tool cloudflare-gateway.crt /tmp/cloudflare-gateway.crt 2>/dev/null || true
RUN if [ -f /tmp/cloudflare-gateway.crt ]; then \
      cp /tmp/cloudflare-gateway.crt /usr/local/share/ca-certificates/ && \
      update-ca-certificates --fresh; \
    else \
      echo "⚠ No cloudflare-gateway.crt found - skipping custom CA"; \
    fi
```

## Security Best Practices

1. **Never commit secrets:**
   - CA certificates specific to your environment
   - API keys, tokens, passwords
   - Private keys
   - `.env` files with real credentials

2. **Use `.gitignore`:**
   - All secret files are already gitignored
   - Check `git status` before committing

3. **Provide examples:**
   - Create `.env.example` with placeholder values
   - Document required environment variables in README

4. **Use Docker secrets or build args for CI:**
   ```dockerfile
   ARG CLOUDFLARE_CERT
   RUN if [ -n "$CLOUDFLARE_CERT" ]; then echo "$CLOUDFLARE_CERT" > /usr/local/share/ca-certificates/cloudflare-gateway.crt; fi
   ```

## Verification

Before committing, verify no secrets are included:

```bash
# Check what will be committed
git status
git diff --cached

# Verify .gitignore is working
git check-ignore -v tooling/cloudflare-gateway.crt
```

Expected output: `tooling/.gitignore:cloudflare-gateway.crt tooling/cloudflare-gateway.crt`
