# Security policy

## Supported versions

Only the latest release receives security fixes. Before the first release, fixes go to `main`.

## Reporting a vulnerability

Report vulnerabilities privately through GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
("Report a vulnerability" on the repository's _Security_ tab). Do not open a public issue.

Please include the version, the steps to reproduce and, if possible, a file that triggers the
problem. We aim to confirm a report within seven days and to publish a fix or a mitigation
within 90 days.

## Scope

Relevant are, among others:

- Parsing of scan and project files (STL, OBJ, PLY, `.m2c`): crashes, excessive memory use,
  path traversal inside project archives.
- The Electron hardening: sandbox, context isolation, content security policy, IPC sender checks,
  navigation and permission handling.
- The geometry process: methods that can be reached from the user interface and must not touch
  files the user did not choose.

Mesh-to-CAD makes no network requests at runtime and collects no telemetry. Behaviour that
contradicts this is a security issue.
