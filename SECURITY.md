# Security Policy

We take the security of `airflow-pytest-plugin` seriously. This document covers
how to report vulnerabilities, which versions receive fixes, and the timelines
you can expect.

## Supported versions

Security fixes are released only for the **current minor version**. The project
is pre-1.0; upgrade to the latest release to receive security fixes.

| Version | Status |
|---------|--------|
| 0.1.x   | ✅ Supported |
| < 0.1   | ❌ Not supported — please upgrade |

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues,
discussions, or pull requests.**

Use **GitHub's Private Vulnerability Reporting** instead. From the
[Security tab of this repository](https://github.com/IKrysanov/airflow-pytest-plugin/security)
click **"Report a vulnerability"**. This opens a private advisory visible only
to you and the maintainer.

If you cannot use Private Vulnerability Reporting, open a regular GitHub issue
containing **only** the words *"please contact me about a security matter"* and a
contact method — no technical details — and the maintainer will reach out
privately.

### What to include

- A short summary of the issue and its impact.
- Affected version(s) of `airflow-pytest-plugin`, Airflow, and Python.
- Steps to reproduce, or a minimal proof of concept.
- Any suggested mitigation, if you have one.

## What to expect after reporting

- **Acknowledgement: within 72 hours.**
- **Initial assessment: within 7 days** (confirmation, preliminary severity,
  rough remediation timeline).
- **Coordinated disclosure: 90 days** from initial report, extendable by mutual
  agreement.
- **Credit:** reporters are credited in the advisory and `CHANGELOG.md` unless
  they prefer to remain anonymous.

These timelines reflect a single-maintainer project. If a report sits
unacknowledged past 72 hours, re-ping via the same channel.

## Out of scope

- Behaviour of pytest, test code, or third-party plugins invoked by the
  operator — running pytest is the operator's purpose; the trust boundary is who
  can write DAGs and place tests on a worker.
- Misconfiguration of the surrounding Airflow deployment (permissive
  Connections, weak worker isolation, an over-shared reports volume).
- Issues that require write access to the DAGs folder, the reports root, or the
  worker filesystem — those imply an already-compromised environment.

## Hardening recommendations for users

- **Parse untrusted JUnit reports with the hardened XML extra.** The reader uses
  the operator's `JUnitResultParser`, which routes through `defusedxml` when
  present:
  ```bash
  pip install "airflow-pytest-plugin[secure-xml]"
  ```
  This closes the standard XML attack classes (entity expansion, external
  entities, recursive expansion).
- **Treat the reports root as a trust boundary.** The reader renders whatever it
  finds under `AIRFLOW_PYTEST_REPORTS_ROOT`. Point it at a directory only your
  workers write to, not a world-writable share.
- **Restrict who can write DAGs and tests** to the same trust level as who can
  deploy production code.

## Acknowledgements

Reporters who responsibly disclose security issues will be listed here. None to
date.
