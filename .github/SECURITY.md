# Security Policy

## Reporting a Vulnerability

Found a security issue in this project? Please report it — we take every report seriously.

**Open a GitHub issue for security vulnerabilities.**

For sensitive reports you'd rather not make public (e.g. anything exposing live credentials or user data), email: **amarjeet.vicky.pasrija+ai_analyst@gmail.com**

A good report includes:
- What the vulnerability is
- How to reproduce it
- What an attacker could do with it
- A suggested fix, if you have one

We aim to respond within 48 hours and will work with you to understand and resolve the issue.

## Scope

In scope:
- The AI Analyst plugin code (skills, agents, helpers, MCP servers)
- Configuration files and templates
- Build and setup scripts
- Data handling, PII redaction, and connection logic

Out of scope:
- Claude / Claude Code / Cowork themselves (report to [Anthropic](https://www.anthropic.com/security))
- AWS Athena, Superset, or other connected services (report to their vendors)
- Third-party dependencies (report to their maintainers)

## Best Practices for Users

- Never commit `.mcp.json` or config files containing real tokens or passwords
- Keep AWS credentials in your local AWS profile — never hardcode them in the repo
- Never commit `knowledge-repo/superset_config.json` or data exports containing PII (the build script blocks these from the plugin zip)
- Review `.gitignore` and run `./build-plugin-zip.sh` (which includes a secret scan) before sharing the plugin
