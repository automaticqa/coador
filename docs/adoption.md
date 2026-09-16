# Feedback and privacy

Coador has no telemetry, analytics SDK, installation identifier or reporting
endpoint. CLI and MCP operations do not send repository names, source, generated
profiles, evidence, local paths, prompts or transcripts to the maintainers.

Default scanning is local. Package installation may download dependencies, an MCP
client follows its provider's data policy, and explicit Gradle probing may access
the network. These are separate from Coador's feedback mechanism.

## Optional feedback

Use the public issue forms for bugs, detector gaps, documentation problems or
usage feedback. Participation is voluntary. A repository name, source code,
generated profile, logs, local paths and MCP transcripts are not required.

Use a minimal synthetic reproduction or an explicitly public source when reporting
a problem. Remove credentials, personal information and private-project details.
Never make private material public merely to demonstrate a failure.

For suspected vulnerabilities, follow [SECURITY.md](../SECURITY.md) instead of
posting sensitive information in a public issue.
