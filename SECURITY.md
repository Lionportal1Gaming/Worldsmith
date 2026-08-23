# Security and secret handling

Do not commit credentials, access tokens, API keys, private keys, certificates, production saves, or personally identifying test data.

Use `.env.example` for documented configuration names; keep actual values in ignored local environment files or the approved secret store. If a secret is committed, revoke or rotate it immediately, open a private security issue, and avoid reproducing the secret in comments or tickets.

Before adding tools, CI, integrations, or assets, verify least-privilege access and record material decisions in GitBook.
