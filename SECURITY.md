# Security Policy

## Supported versions

Only the `main` branch is supported. The site and pipeline redeploy from
`main` nightly.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting on this repository
(Security tab, "Report a vulnerability"). If that is unavailable, open an
issue titled "security" without exploit details and a maintainer will follow
up privately.

Please include the affected component: the GitHub Pages site (`docs/`), the
Python pipeline, or the Cloudflare Worker (`worker/` — the Ask tab proxy is
the only component that handles user input server-side).
