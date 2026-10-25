# Security policy

## Reporting a vulnerability

Please do **not** open a public issue for security problems.

Use GitHub's private vulnerability reporting (repository **Security** tab →
*Report a vulnerability*) or contact the maintainer through the repository
profile. Include:

- affected version/commit
- a description of the issue and impact
- reproduction steps or a proof of concept
- any suggested mitigation

You will receive an acknowledgement as soon as possible. Please allow a
reasonable window for a fix before disclosing publicly.

## Secrets

This repository never needs provider keys to be committed. Keep them in `.env`
(git-ignored) or your deployment platform's secret manager:

- `GEMINI_API_KEY` / `GEMINI_API_KEYS`
- `PINECONE_API_KEY`
- `APIFY_API_KEY`
- `GROQ_API_KEY` / `OPENAI_API_KEY`
- `CRAG_API_KEY` (local administration API access key)
- `CRAG_PUBLIC_TOKEN_USERS` (public access token digests mapped to user IDs)
- Instagram `cookies.txt`

Remember that every `VITE_*` value is bundled into the public frontend; it can
never be a real secret.

`VITE_API_KEY` is supported only for the local administration frontend. Public
builds use `VITE_APP_MODE=query` and accept an individual access key at runtime.
The public API verifies the token and derives user identity on the server;
`X-User-Id` is not public authentication. Keep the administration API on loopback.
See [deployment boundaries and remaining production checks](docs/deployment.md).

If a key is ever committed or pushed, rotate it immediately and remove it from
history (for example with `git filter-repo`). Enabling GitHub secret scanning
and push protection is strongly recommended.
