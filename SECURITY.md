# Security Policy

## Reporting a Vulnerability

**Please do not open a public GitHub issue for a security vulnerability.** That publishes the details before a fix exists.

Instead, use GitHub's private reporting: go to the [Security tab](https://github.com/xDarkzx/Reaper-MCP/security) → **Report a vulnerability**. This opens a private conversation only you and the maintainer can see, and lets you attach details/reproduction steps without exposing them publicly.

## What to Expect

This is a solo-maintained project, so response times aren't guaranteed on a fixed SLA, but a genuine security report will be prioritized ahead of regular feature work. You'll get an acknowledgement, and a fix (or an explanation if it turns out not to be exploitable) once it's been looked into.

## Scope

Reaper-MCP runs locally and talks to REAPER over a file-based IPC bridge on your own machine — there's no server, no cloud component, and no network exposure by design. Relevant reports include things like:

- A way for a malicious project file, MIDI data, or MCP tool call to trigger unintended file access, code execution, or data exfiltration
- Path traversal or injection through any tool parameter
- Anything that lets an MCP client do more than the documented tools allow

Reports about the underlying REAPER application itself belong with Cockos, REAPER's developer, not here.

## Supported Versions

Only the latest published version is supported. Please update (`pip install --upgrade xdarkzx-reaper-mcp`) before reporting, in case it's already fixed.
