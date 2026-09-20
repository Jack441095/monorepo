# Local Data Policy

GitHub contains reviewed source and documentation only.

The following remain local-only unless they pass an explicit privacy,
licensing, and reproducibility review:

- `.env` files and credentials
- databases, logs, chats, runtime state, and generated indexes
- model weights and large binary artifacts
- unreviewed training notes, transcripts, scraped sources, and licensed PDFs
- local AI/editor agent metadata such as `.claude`, `.cursor`, and `.codex`
- build directories, dependency caches, and test workspaces

Reviewed SLO integration code, product source, tests, and durable
documentation belong in Git. If a local corpus is needed by a collaborator,
publish a reviewed manifest and a reproducible acquisition/build procedure
rather than copying private or unlicensed material into the repository.
