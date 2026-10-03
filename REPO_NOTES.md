# Repo Notes — Nite-DSP Monorepo

## Structure

```
Nite-DSP/monorepo          ← source of truth (GitHub org)
Jack441095/monorepo        ← personal mirror (Vercel auto-deploy)
```

## Vercel Deploy

**Project:** nite-dsp/website  
**URL:** https://nitedsp.co.uk  
**Connected repo:** Jack441095/monorepo (personal mirror, Hobby plan compatible)  
**Root directory:** platform/website  
**Auto-deploy:** on push to main via GitHub Actions mirror

### Manual deploy (fallback)
```bash
cd platform/website
vercel build --prod
vercel deploy --prebuilt --prod
```

## GitHub Mirror Action

File: `.github/workflows/mirror-to-personal.yml`  
Secret: `PERSONAL_MIRROR_TOKEN` set on Nite-DSP/monorepo  
Triggers: every push to `main` → mirrors to `Jack441095/monorepo`

## GitHub Org Structure

**Nite-DSP org**
- `monorepo` — main codebase (this repo)
- `client-websites` — client work

**Teams**
- `Nite-DSP` — internal products
- `Client-Work` — client projects

## Stripe commerce

Stripe is the only active provider. Checkout settings, webhook events, and migration instructions are in [docs/STRIPE_COMMERCE.md](docs/STRIPE_COMMERCE.md). Public SLO and Submit payment links use Stripe; the authenticated checkout endpoint is `/commerce/checkout`.

## Submodule URLs

All updated to `github.com/Nite-DSP/...` after org transfer (Sept 2026).

## Rates

Standard: £38/hr  
Friend/referral: £25/hr  
Active client: Crystal Carpentry (£25/hr)
