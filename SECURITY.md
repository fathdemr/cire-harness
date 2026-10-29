# Security

cire-harness runs shell commands, edits files and talks to model providers and MCP servers on your behalf, so security reports matter.

## Reporting a vulnerability

Please do not open a public issue for security problems. Use GitHub's private vulnerability reporting on this repository ("Security" tab, "Report a vulnerability"). If that is not available to you, open an issue that says only "security report, please contact me" without details and the maintainer will reach out.

You should get a first reply within a week. Please give a reasonable time to fix before disclosing publicly.

## Scope

In scope: anything that lets a model, a tool result or an MCP server do something the user did not approve, leak credentials, read or write outside the working directory, or bypass the confirmation prompts.

Out of scope: the behaviour of third-party MCP servers or model providers themselves, and issues that require the user to put secrets into the config file against the documented rules.

## Design notes relevant to reviewers

- Provider keys and MCP secrets come from environment variables only; the config rejects values that look like `NAME=value`.
- MCP subprocesses start with a minimal environment plus the variables named per server.
- File and grep tools refuse paths outside the working directory.
- Shell commands, file writes and every MCP tool ask for confirmation unless the server was marked trusted.
- The Bedrock region is validated against the AWS region format before a hostname is built from it.
