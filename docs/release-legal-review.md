# Release legal and privacy review, 2026-10-22

This is an engineering issue-spotting checklist, not legal advice or a finding
of compliance. A qualified reviewer and the project owner must approve public
claims, applicable-jurisdiction duties, and distribution terms before release.

## Verified product facts

- The desktop management API is designed for one local operator and has no
  account-level authentication or multi-user RBAC. Do not publish it on an
  untrusted network or describe it as an enterprise access-control boundary.
- Workspace and optional trace records use a local SQLite database. Trace
  bodies are off by default; operators can enable input/output capture and
  choose retention settings. A local project token authenticates SDK ingestion,
  but local UI management routes do not require a login.
- The strict 2.1.0 candidate blocks RedForge-managed hosted requests, model
  downloads, and update checks. A separately configured connected deployment
  retains those network features. A local runtime may have its own network
  behavior outside RedForge's controls.
  The marketing site loads Google Fonts and fetches release metadata from
  GitHub. Its source contains no analytics or tracking-cookie integration.
- Redaction is heuristic and fail-closed on filtering errors, but it cannot
  guarantee removal of every personal or confidential value. Prompts, exported
  traces, datasets, and reports may contain sensitive information.
- RedForge's own source license is MIT. `website/public/open-source-notice.html`
  identifies selected direct dependencies, not a complete installer SBOM or
  legal clearance for every bundled/transitive component, model weight, dataset,
  or provider. Those each have their own terms.

## Before public release

1. Confirm who operates the website and receives support/privacy requests, and
   whether the stated contact mailbox is monitored. Review the privacy policy's
   controller/operator identity, request handling, retention, incident response,
   and disclosures for each target jurisdiction. Local-only storage does not by
   itself resolve every data-protection obligation.
2. Decide whether external Google Fonts should remain. If retained, keep the
   website disclosure; if self-hosted later, update the disclosure and retain
   font license notices. Confirm any CDN and hosting logs separately.
3. Review third-party notices and license texts for the actual packaged
   dependencies on Windows, macOS, and Linux, plus model and dataset licenses.
   Preserve MIT notices in source and binary distributions as required.
4. Test the final signing and notarization posture. An unsigned Windows/macOS
   build should be labeled honestly; a green local build is not proof of user
   trust prompts or platform distribution approval.
5. Have a security reviewer approve trace capture, local API exposure,
   sanitization/export controls, and the wording of any privacy or security
   claims. Never market estimated budget enforcement as a guaranteed provider
   billing cap or evidence-only gates as automatic deployment approval.
6. Review the strict application-level boundary in
   [network profiles](network-profile.md) against the V3 constitution. The
   owner chose to **defer conflicting network features**, not amend that
   document. Hosted adapters and remote trace paths remain behind explicit
   connected configuration. This is not OS-level network isolation. Before a
   no-egress public claim, verify the actual installer and deployed runtime
   under network observation, and resolve any architectural wording conflict.

## Dependency and notice evidence, 2026-10-23

This is an engineering inventory, not license clearance. The current Windows
portable ZIP has 389 entries and was checked against the exact SHA-256 in the
[release audit](release-readiness-audit.md). Its top level includes RedForge's
`LICENSE.txt` and Electron's `LICENSE.electron.txt`. The extracted `app.asar`
contains 16 production Node modules and license files for 15 of them;
`lazy-val` has package metadata but no separate license file in the archive.
The frozen backend's visible files include license texts for Click,
OpenTelemetry API, and two vendored setuptools packages, but the archive does
not contain a complete license-text collection for its Python dependency set.
These observations do not establish which notices are legally required.

Lockfile metadata inventory (counts are scoped to each project and can overlap):

| Scope | Production package records | Metadata licenses requiring specific review |
| --- | ---: | --- |
| Frontend | 122 | `victory-vendor` uses `MIT AND ISC`; remaining records are MIT, ISC, BSD-3-Clause, Apache-2.0, or 0BSD. |
| Desktop Node | 16 | `argparse` declares Python-2.0; `sax` declares BlueOak-1.0.0. |
| Website | 8 | MIT or ISC. |
| Backend Python | 31 pinned runtime packages | `certifi` declares MPL-2.0; `greenlet` declares `MIT AND PSF-2.0`. `aiosqlite`, `annotated-types`, and `colorama` omit a machine-readable license field but ship license files and MIT/MIT/BSD classifiers respectively. |

The Python count comes from `backend/requirements.lock` matched against the
isolated build environment's installed distribution metadata. That
environment also has build tools; they are not counted as runtime dependencies
in the table. PyInstaller itself declares GPLv2-or-later with a special
distribution exception in its metadata. Qualified review should confirm the
exception and the frozen bootloader's notices. The lockfile inventory alone
does not prove an exhaustive binary SBOM, especially for bundled native
libraries, Electron/Chromium, fonts, models, or datasets.

The website's selected-dependency notice had grouped Starlette with FastAPI
as MIT. Installed Starlette 1.6.0 declares BSD-3-Clause; FastAPI declares MIT.
`website/public/open-source-notice.html` now distinguishes them, adds certifi's
MPL-2.0 declaration, and states that the list is incomplete. The website build
passed and the built notice matches the source byte-for-byte. This source edit
has not been deployed or reviewed as complete legal notice text.

Before distribution, produce a file-level SBOM from each final platform
artifact; compare it with its lockfiles; collect full applicable license and
notice texts; and verify the installer/source packages include required copies.
Review MPL, Python-2.0, BlueOak, multi-license expressions, Electron/Chromium,
font, model, and dataset terms with qualified counsel. Recheck after any
dependency or artifact rebuild. Do not interpret this inventory as a legal
approval.

## Reference material for human review

- [India's Digital Personal Data Protection Rules, 2025](https://www.meity.gov.in/static/uploads/2025/11/53450e6e5dc0bfa85ebd78686cadad39.pdf): commencement is staggered, so counsel should check which provisions apply at launch.
- [European Commission GDPR data-protection principles](https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/principles-gdpr_en): relevant if EU personal data is processed; applicability depends on actual activities and users.
- [FTC Start with Security](https://www.ftc.gov/business-guidance/resources/start-security-guide-business): US security-practice guidance, not a certification.
