# Returning changes

Return a small archive containing only changed source files, new assets, lockfile changes, a change log, test/build results, and desktop plus narrow-width screenshots.

Do not return dependencies, builds, `.env*`, `.runtime`, caches, databases, logs, audio, models, training data, repository history or unrelated formatting changes.

The owner should review the return archive outside the canonical checkout, diff it against this package, copy only approved files, and rerun the focused SLO backend/frontend tests and production builds.
