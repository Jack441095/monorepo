# Contributing to KENN

## Branch workflow

1. Pull `develop` before starting.
2. Create a short-lived branch such as `feature/slo-library-filters`.
3. Keep one concern per commit and use plain descriptive commit messages.
4. Run the relevant backend and frontend checks.
5. Open a pull request into `develop` and describe any local assets the reviewer must generate.

## Canonical locations

- Backend: `apps/backend/src/kenn/`
- Frontend: `apps/frontend/`
- Desktop: `apps/desktop/`
- Plug-ins: `plugins/kenn-vst3-au/`
- Ableton integrations: `integrations/`
- Product packages: `packages/`
- Build and evaluation tools: `tooling/`

Do not create another frontend or backend mirror. Extend `kenn.paths` when backend code needs a new workspace path.

## Local-only data

Never commit `.env` files, credentials, chat databases, audio, model weights, generated indexes, build output, or newly harvested training material. Environment examples and reviewed fixtures are safe to commit. See `docs/handover/LOCAL_DATA_AND_SECURITY.md`.

## Verification

```bash
make backend-test
make frontend-install
make frontend-test
make frontend-build
```

The focused commands above cover the SLO integration. Run the broader subsystem tests when changing shared backend behavior.
