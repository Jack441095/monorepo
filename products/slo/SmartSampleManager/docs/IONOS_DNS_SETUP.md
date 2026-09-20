# IONOS DNS Setup

Phase 5.6, Section 13. `nitedsp.co.uk` is registered at IONOS. This document explains WHICH
records will need configuring once Railway provides target hostnames -- it does not invent
target values (an IP address or CNAME target) ahead of Railway actually supplying them, per
Section 13's explicit instruction.

## What you'll need from Railway first

For each Railway service you attach a custom domain to (website and backend, separately),
Railway's dashboard (Settings → Networking → Custom Domain) generates a target CNAME value
specific to that service -- something like `<service-id>.up.railway.app`. That exact value does
not exist yet because no Railway project exists yet (`docs/RAILWAY_DEPLOYMENT.md`).

## Records to configure at IONOS, once Railway supplies the targets

| Record | Type | Name | Target | Purpose |
|---|---|---|---|---|
| Root/apex | CNAME* or A | `nitedsp.co.uk` (`@`) | Railway's provided target for the website service | Main site |
| www | CNAME | `www` | Railway's provided target for the website service | `www.nitedsp.co.uk` redirect/alias |
| API | CNAME | `api` | Railway's provided target for the backend service | `api.nitedsp.co.uk` |

*Root/apex CNAME note: standard DNS forbids a CNAME at the zone apex. IONOS supports "CNAME
flattening" / ALIAS-style records for this exact case (check IONOS's current UI for the option --
it may be labeled differently); if unavailable, Railway's dashboard will indicate whether an A
record (pointing at a Railway-provided IP) is the supported alternative for apex domains. Confirm
directly against Railway's current custom-domain instructions at the time of setup, since this
detail changes between platforms/versions and should not be assumed here.

## TLS expectations

Railway provisions and renews TLS certificates automatically for custom domains once DNS
validation succeeds (standard Railway behavior) -- no separate certificate purchase or IONOS-side
TLS configuration is expected. `docs/RAILWAY_DEPLOYMENT.md`'s note about `_validate_production_config`
already assumes HTTPS URLs throughout (`https://nitedsp.co.uk`, `https://api.nitedsp.co.uk`).

## Verification records

None anticipated beyond the CNAME/A records above for a straightforward Railway custom-domain
setup. If Railway's dashboard requests a TXT verification record at setup time, add exactly what
it displays -- not invented here since it doesn't exist yet.

## Order of operations

1. Create the Railway project and both services (`docs/RAILWAY_DEPLOYMENT.md`).
2. Add custom domains in Railway's dashboard for each service; note the exact target values
   Railway displays.
3. Add the corresponding records at IONOS using this document's table, substituting Railway's
   real target values.
4. Wait for DNS propagation and Railway's automatic TLS provisioning.
5. Verify `https://nitedsp.co.uk` and `https://api.nitedsp.co.uk/health` both resolve and serve
   correctly before pointing any real traffic at them.
