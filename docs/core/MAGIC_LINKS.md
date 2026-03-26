# Magic Links — Internal Documentation

## What
Single-use, time-limited URLs that bypass the password gate on thinkers pages. One click = authenticated.

## How It Works
1. Generate a 64-char hex token via API
2. Token stored in Redis with 7-day TTL
3. Recipient clicks `base-layer.ai/thinkers/{slug}?t={token}`
4. Server validates token, sets auth cookie (30 days), deletes token (single-use)
5. Redirects to clean URL `/thinkers/{slug}`
6. If token expired/invalid, falls through to password gate

## Generating Magic Links

### Via API (programmatic)
```bash
curl -X POST https://base-layer.ai/api/magic-link/generate \
  -H "Content-Type: application/json" \
  -H "x-admin-secret: $INDUSTRY_ADMIN_SECRET" \
  -d '{"slugs": ["dan-shipper", "kevin-kelly"]}'
```

Response:
```json
{
  "links": [
    {"slug": "dan-shipper", "url": "https://base-layer.ai/thinkers/dan-shipper?t=abc123...", "token": "abc123...", "expiresAt": "2026-04-01T..."},
    {"slug": "kevin-kelly", "url": "https://base-layer.ai/thinkers/kevin-kelly?t=def456...", "token": "def456...", "expiresAt": "2026-04-01T..."}
  ]
}
```

### Via Gmail Drafts (outreach workflow)
```bash
# Set admin secret
export INDUSTRY_ADMIN_SECRET=your_secret_here

# Generate drafts with magic links injected
python push_gmail_drafts.py --wave 2 --magic-links --dry-run  # Preview
python push_gmail_drafts.py --wave 2 --magic-links             # Create drafts
```

The `--magic-links` flag:
1. Extracts slug from each email's thinker URL
2. Calls `/api/magic-link/generate` for each slug
3. Inserts "Direct link (one-click, expires in 7 days)" above the existing password link
4. Password remains as fallback

## Rate Limits
- 20 tokens per hour (global)
- 5 tokens per slug per hour
- If rate-limited, magic link skipped for that email (password-only fallback)

## Security Model
- Tokens are 32 bytes (64 hex chars) — cryptographically random
- Single-use: consumed on first click, deleted from Redis
- 7-day expiry: tokens auto-expire even if unused
- No PII in the token itself
- Auth cookie: httpOnly, secure, sameSite=strict, 30-day expiry, path-scoped to `/thinkers/{slug}`

## Troubleshooting
- **"Rate limit exceeded"**: Wait 1 hour. Global limit is 20/hour.
- **"Token expired"**: Generate a new one. Tokens last 7 days.
- **Magic link not working**: Check if slug exists in Redis. Token may have been consumed already (single-use).
- **INDUSTRY_ADMIN_SECRET not set**: The API returns 503. Set it in your environment.
- **Password still shown after magic link click**: Expected behavior — magic link sets cookie, password is fallback for future visits after cookie expires.

## Files
- `lib/magic-link.ts` — Token generation + consumption logic
- `app/api/magic-link/generate/route.ts` — API endpoint
- `app/thinkers/[slug]/page.tsx` — Token consumption on page load
- `push_gmail_drafts.py` — Gmail integration (--magic-links flag)
