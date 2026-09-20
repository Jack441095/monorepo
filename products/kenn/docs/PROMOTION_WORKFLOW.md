# KENN promotion workflow

## Source of truth

The platform monorepo is authoritative for whole-product work:

`Nite-DSP/monorepo` → `products/kenn`

`Nite-DSP/colloidal-cyclone` is the focused KENN collaboration/release
surface. It is intentionally not a second full platform checkout.

## Promoting monorepo work into the focused KENN repo

1. Start from a clean monorepo commit and record its SHA.
2. Identify the smallest KENN-only scope; do not copy generated files,
   unrelated products, local corpora, or build workspaces.
3. Port the change into a topic branch in `colloidal-cyclone`.
4. Run the standalone checks relevant to the changed backend, frontend,
   desktop, plugin, integration, and SLO-hook paths.
5. Open a PR into `develop` that records the source SHA, scope, tests, and
   intentional differences.
6. Merge only after a human review confirms that the focused repo still has a
   complete runnable KENN product.

## Promoting focused-repo work back to the platform

If a change belongs in the whole platform, port it back into
`monorepo/products/kenn` through a separate PR. Do not use a force push or a
whole-tree overwrite to make the repositories look identical.

## Release and cleanup rules

- Keep `develop` as the collaboration branch in `colloidal-cyclone`.
- Keep experimental monorepo branches out of `main` until their tests and
  ownership are reviewed.
- Tag verified baselines before large migrations.
- Keep private, licensed, generated, and local agent data out of both repos.
- Delete handoff bundles or duplicate checkouts only after their contents are
  either preserved in Git or explicitly marked disposable.
