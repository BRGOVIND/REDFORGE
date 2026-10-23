# RedForge engineering release audit, 2026-10-23

**Status: release blocked; internal testing only.** This audit distinguishes
local verification from a consumer release. It does not authorize publication, deployment, or migration
of a user database. The owner chose to preserve the V3 constitution's no-egress
direction. The 2.1.0 candidate now defaults to an application-level strict
profile that blocks RedForge-managed hosted inference, remote trace ingestion,
downloads, update checks, and non-loopback CLI binding. Network-enabled code
is preserved behind an explicit connected profile. This is not an OS firewall;
see [network profiles](network-profile.md). No public no-egress claim is approved.

| Phase | Repository state | Remaining release limit |
| --- | --- | --- |
| 1: observability | SDK wrappers, project ingestion tokens, trace explorer, trace migration, tests and privacy hooks are present. | Strict mode accepts only loopback trace peers/endpoints. It is not a secure enterprise ingestion service. |
| 2: prompts and privacy | Draft/publish/activation registry and privacy controls are present; isolated browser refresh, capture tests, and synthetic upgrade have passed. | Multi-user RBAC is not part of the desktop product. Local operator access is not enterprise tenant isolation. |
| 3: comparison, routing, cost budgets | Immutable Workbench-backed comparisons, explicit versioned routing, operator prices, cost reports and soft/hard budget behavior are implemented. See [Phase 3 design](phase3-comparison-routing-cost.md). | Hosted routing may need deferral for no-egress. Cost limits are planning estimates, not provider invoice caps; they cannot preempt external SDK calls. |
| 4: anomaly and feedback | Local anomaly rules, trace feedback, reviewed regression cases, tests and UI are present. | No email/webhook channel exists; alerts stay local. |
| 5: security and release gates | Reviewed trace-derived security cases and versioned evidence-only gates are implemented. See [Phase 5 design](phase5-security-release-gates.md). | Gate decisions do not deploy. Prompt rollback is a validated recommendation, not an executed rollback. |

## Local verification

The latest backend suites passed **677 tests on Python 3.11 and 677 on Python
3.12** after the final network and packaging-harness regressions. The first
Python 3.12 full run had one Windows-only test-server abort: the new fixture
answered a POST without reading its body. That fixture was corrected, and both
complete suites passed on rerun. Final sequential verification passed 677 tests
on Python 3.11 in 71.76 seconds (one Starlette/httpx deprecation warning) and
677 on Python 3.12 in 385.70 seconds with no warnings. The Python 3.12 JUnit
report is saved at
`C:\Users\LOQ\AppData\Local\Temp\redforge-final-py312-20261023.xml`.
An earlier concurrent full-suite run emitted an `aiosqlite` worker/event-loop
teardown warning; the named training test and final sequential suite passed.
Its origin is unconfirmed. Run these suites sequentially because the test
configuration uses a shared temporary database filename.
The preceding proxy-fix baseline passed 667 tests on each interpreter.
The preceding strict-profile run passed 665 tests on each interpreter. Ruff,
version guard, desktop configuration guard,
frontend asset graph, frontend and website builds, and 20 desktop tests passed.
The preceding CLI wheel and sdist built successfully (38,911 and 33,606 bytes);
those measurements predate the CLI proxy fix and are not current release artifacts.
`pip-audit` found no known vulnerabilities in the new Python lock;
website and desktop production npm audits found none. Frontend production audit
still reports two moderate React Router findings in `react-router` and
`react-router-dom`: GHSA-wrjc-x8rr-h8h6 and GHSA-337j-9hxr-rhxg. The reported
fix is React Router 7.18.4, a major-version migration requiring compatibility
review. No advisory was suppressed or dependency changed in this validation.
The 2026-10-23 repeat audit still reports exactly those two production
findings; desktop and website production audits report zero. The upstream
maintainers list 7.18.0 as the first patched React Router version for both
([redirect advisory](https://github.com/remix-run/react-router/security/advisories/GHSA-wrjc-x8rr-h8h6),
[SSR advisory](https://github.com/advisories/GHSA-337j-9hxr-rhxg)); `npm audit`
suggests 7.18.4. This frontend uses `<BrowserRouter>` declarative routing,
not manual SSR/hydration, so the stated SSR advisory precondition is absent in
the inspected code. The redirect advisory still warrants review of paths
derived from user or API data. No 6.x patched version exists for these ranges.
The owner/security reviewer must approve a scoped 7.x migration with route and
navigation regression tests or record an explicit, time-bounded risk decision;
the current candidate is not dependency-cleared.
Including development tools, npm audit
reports 12 findings in frontend (6 high), 7 in website (5 high), and 8 moderate
in desktop; these are not included in production runtime packages, but CI and
build-tool exposure still need a reviewed update plan. A source-served and an isolated frozen
backend smoke test loaded all referenced JavaScript chunks and CSS with correct
MIME/cache headers. A fresh isolated migration reached head
`c6b7a81d402e`. A synthetic older database upgraded from Phase 1 while
preserving a prompt and version. Those migration tests used isolated data. A
later packaging smoke had an incomplete DB override, described below. In an
isolated browser session, a newly created Workbench collection appeared without
reload, the strict Model Hub showed disabled download buttons, and the browser
reported no page errors. Earlier browser smoke covered
Release and Model decisions, including policy activation and budget saving,
without browser errors or confirmed automated WCAG 2A/2AA violations. The
marketing site and four legal pages also had no automated WCAG 2A/2AA
violations after contrast and wrapping repairs; visual inspection and manual
accessibility review are still needed. The Model decisions page at a 390-pixel
viewport is squeezed by the existing desktop sidebar; desktop remains the
release target.

A resumed targeted run passed 17 Python network/routing tests and 11 desktop
network/supervisor tests before the proxy fix. Afterward, the full Python suites
passed 667 tests on each interpreter, all 20 desktop tests passed, and Ruff
passed on the changed code. GitHub CI for committed HEAD `e1e88b7` failed on
2026-10-21: `tests/test_traces.py::test_sdk_sync_wrappers_stream_privacy_and_noop`
received a coroutine instead of a synchronous stream. That older committed
revision is not the current working tree. Current uncommitted code passed the
corresponding local tests, but **no hosted CI has run on this candidate**.

The superseded, pre-proxy-fix Windows rehearsal produced a **132,676,995-byte unsigned setup
executable** and **177,123,112-byte portable ZIP** from a clean pinned Python
3.11 backend environment. The frozen backend is 46,080,512 bytes. Its live
smoke test booted in 11.0 seconds on this development machine and loaded all 55
referenced JavaScript chunks plus CSS with correct MIME/cache behavior. The
portable ZIP's 379 entries passed CRC integrity checks and include
`RedForge.exe`, `resources/app.asar`, the frozen backend,
`resources/backend/VERSION`, and `LICENSE.txt`. The Windows update feed's
installer filename, size, and SHA-512 digest match the built setup executable.
Both the setup executable and extracted portable `RedForge.exe` report
`NotSigned` through Windows Authenticode. A ZIP file itself is not an
Authenticode-signed executable.
That portable ZIP was extracted to an isolated temporary directory, and its
`RedForge.exe` served `/healthz`, `/api/providers` with `network_profile=strict`,
and the frontend root. A later local rehearsal used that same extracted binary
with an isolated temporary workspace and an already installed Ollama model,
`mistral:latest`. `/api/playground/chat` returned HTTP 200 with a local model
response and reported 4,734 ms latency. Model Hub download, onboarding pull,
training-runtime install, and a hosted OpenAI Playground request each returned
HTTP 403 with `network_policy_blocked` before their managed network action.
This demonstrates tested application paths, not absence of all network traffic;
no packet capture ran during this rehearsal. The test processes were stopped.
The installer was **not installed** on a clean machine:
RedForge 1.2.0 is already installed on this PC, so running setup here could
replace the user's installation. An earlier Windows
rehearsal produced a 134,031,083-byte setup and 178,478,316-byte portable ZIP,
but those builds are not directly comparable because environment and source
changed. A source-archive rehearsal initially produced a 40,280,353-byte
ZIP that unintentionally included local training outputs and generated cache.
The preceding isolated source ZIP is **1,290,663 bytes** and tar.gz is **1,091,564 bytes**;
both archives contain 495 entries, ZIP integrity and SHA-256 checksums passed,
and no generated database, cache, training output, or credential-like filename
was found. The source ZIP was extracted and its `install.cmd` installed pinned
Python 3.11 dependencies in a fresh virtual environment from a local wheelhouse
with `--no-index`; `start` then served health, strict provider profile, and
frontend from the extracted files. That historical smoke used a
pre-documentation-fix archive; its immediate rebuild changed only installation
instructions. The current archive described below additionally contains the
proxy fix. The source archive still requires Python and an offline
wheelhouse or preinstalled dependencies. The packaging fix leaves original
local data untouched and excludes generated backend-root state. The initial
oversized copy and its staging directory were moved out of `releases` to
`%TEMP%/redforge-unsafe-archive-quarantine-3a9e3cf1b71f4750a517ec273bba6dd2`;
**do not publish or share that quarantined copy**. It can be recovered for
inspection, then securely removed by the owner. The corrected source archive is not
a standalone desktop installer. macOS and Linux packages, an actual Windows
installation, signing, notarization, cross-platform update behavior, and a
representative user-data restore have not been validated locally.

This host is Windows 11 Home Single Language, x64, build 26200, with a
medium-integrity (non-elevated) session. `WindowsSandbox.exe`, Hyper-V `Get-VM`,
VirtualBox, and VMware CLI were unavailable; WSL listed only `docker-desktop`,
not a clean Windows environment. The existing `C:\Program Files\RedForge`
registration reports version 1.2.0. No disposable clean Windows VM was
available, and the final 2.1.0 setup was not run on this host. No installation,
upgrade, backup/restore, or uninstall claim follows from the portable smoke.
The VM availability check was repeated on 2026-10-23 with the same result.
The local Docker Linux daemon was also unavailable, so it supplied no
substitute Linux test environment.
The exact candidate hashes, packet-capture commands, firewall commands, proxy
matrix, upgrade sequence, and evidence checklist are in the
[clean Windows rehearsal worksheet](release-vm-rehearsal.md). That worksheet is
prepared, not executed.

The first packaged Electron strict-mode smoke exposed two external HTTPS
connections from Chromium's network utility process. Startup background-network
switches, an external web-request guard, and strict external-link handling were
added. The pre-proxy-fix guarded app booted with `network_profile=strict`; a
55-second TCP sample observed **zero external endpoints across 50 process samples**. The
frozen backend smoke separately observed zero external endpoints across 11
samples. Sampling can miss short-lived traffic and does not establish OS-level
isolation. Neither the unguarded archive nor the guarded pre-proxy-fix binary
is a current release candidate.

A further strict-mode review found an application-level proxy bypass: with
`HTTP_PROXY` set and `NO_PROXY` empty, Python's default HTTP clients attempted
to send loopback requests through that proxy. A local `127.0.0.1:11434` Ollama
probe timed out through a deliberately unreachable proxy, while an identical
request with `trust_env=False` succeeded. Strict provider clients now ignore
proxy environment variables; CLI and trace SDK loopback calls also disable
proxy use and external redirects. Regression tests use a local test server and
poisoned proxy variables. Connected profile behavior remains explicit. This is
defense in depth, not an OS-level no-egress guarantee.

The **now-superseded proxy-guard** Windows candidate was rebuilt in a separate temporary copy of
the working tree, preserving older artifacts and the installed 1.2.0 copy. It
uses Python 3.11.16, PyInstaller 6.21.0, hooks 2026.9, and electron-builder
26.15.3. The staged frozen backend passed its live smoke: healthy in 3.7 seconds
on this host, all 55 referenced JS chunks and CSS served with correct headers.
The rebuilt portable ZIP has 379 entries, passes CRC checks, adds or removes no
files relative to the preceding ZIP, and differs in its frozen backend binary.
No generated database, environment file, checkpoint, output, or compiled-cache
filename appeared in the ZIP. The update feed's setup filename, size, and
SHA-512 digest match the rebuilt setup. Both setup and extracted portable
`RedForge.exe` remain `NotSigned` by Authenticode.

That portable ZIP was extracted into a fresh temporary directory.
`/healthz` was online, `/api/providers` reported `strict`, a real preloaded
Ollama `mistral:latest` Playground call returned HTTP 200, and four prohibited
actions (Model Hub download, onboarding pull, training-runtime install, hosted
OpenAI call) each returned HTTP 403 `network_policy_blocked`. Test processes
were stopped. This was not a clean install, upgrade, or sustained packet capture.
That binary was not live-tested with poisoned proxy variables; source
regression tests exercise that condition. No final-candidate outbound packet
capture has been completed.

Independent verification found a release-blocking mismatch in that candidate:
its packaged `backend/app/static/index.html` referenced `index-pNV5cNTT.js`,
while the current frontend build and source ZIP referenced
`index-Cd9qoj1A.js`. Asset-graph checks passed because the older UI was
internally consistent, but it did not match current source. A release-stage
guard now rejects `--skip-frontend --require-frozen`, the combination that
allowed this stale copy. The old candidate must not be released.

The **replacement current Windows candidate** was built from a new isolated
copy with a fresh frontend build and frozen backend. Staging compared frontend
`dist`, backend static files, and PyInstaller-collected static files. Its
frozen-backend smoke served all 60 JavaScript chunks and CSS. The 389-entry
portable ZIP passed CRC checks, and its extracted static `index.html` exactly
matches the fresh frontend build. The extracted portable's bundled backend
also passed a poisoned-proxy smoke (`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`
set to unreachable loopback, `NO_PROXY` empty): `/healthz`, strict profile,
all UI assets, and a real preloaded Ollama `mistral:latest` call returned
HTTP 200. The response body was nonempty. That smoke launched the **bundled
backend**, not the Electron `RedForge.exe`; the full new desktop shell still
needs clean-VM observation. The no-proxy smoke harness was fixed after an
initial false failure caused by its own urllib proxy use. No sustained packet
capture was taken. Setup and extracted `RedForge.exe` are `NotSigned`.

The smoke harness also exposed a data-isolation fault: it set temporary
`REDFORGE_HOME` but not `REDFORGE_DATABASE_URL`; the backend's default SQLite
path is under `%LOCALAPPDATA%\RedForge`. The existing
`C:\Users\LOQ\AppData\Local\RedForge\redforge.db` had a 2026-10-23 00:25:45
local last-write time after smoke activity. `PRAGMA quick_check` returned `ok`,
but no pre-smoke snapshot exists, so unchanged records cannot be proven.
The harness now sets an explicit SQLite URL inside its temporary directory;
a subsequent source-archive smoke succeeded and the default DB's last-write
time did not advance. Do not restore or delete the user's DB without a
reviewed backup and owner direction.

Current unsigned Windows artifacts, **replacing the prior hashes**:

- Setup: `C:\Users\LOQ\AppData\Local\Temp\redforge-current-ui-build-1792694794463\desktop\release-build\RedForge-v2.1.0-Setup.exe`, **134,523,678 bytes**, SHA-256 `6AC524632BE437375022BB620E638ABCE4418025E26AEA3347F6CBEBFCCDD27B`.
- Portable ZIP: `C:\Users\LOQ\AppData\Local\Temp\redforge-current-ui-build-1792694794463\desktop\release-build\RedForge-v2.1.0-Portable.zip`, **178,973,497 bytes**, SHA-256 `DFA6129BD5B7BF321EC01441D776B7544B60BBBE21052AF223FC7A7A9D37792B`.

Current source archives are at
`C:\Users\LOQ\AppData\Local\Temp\redforge-source-current-ui-1792695718186\`.
The ZIP is **1,292,763 bytes**, SHA-256
`B43A96D02A4AE6FE8AC1877721A4931192E0921C3BDAA9F6DF67E2E7F7043E39`;
the tar.gz is **1,093,392 bytes**, SHA-256
`1560823462B777F572F29820CB1EDF253DC2806547BB8816DCE67D5573F2741C`.
Both contain 496 entries; ZIP integrity passed, and the new CLI proxy helper is
present. `.env.example` is a template, not a credential. This replacement
source archive includes the current network-profile documentation and fresh UI;
its ZIP passed CRC and its tar.gz enumerated all 496 members. The ZIP was
extracted and `install.cmd` installed all pinned dependencies using Python
3.11.16 in a fresh virtual environment with `REDFORGE_WHEELHOUSE` and
`--no-index`. Its extracted backend then served health, all 60 UI chunks,
strict profile, and real local inference with poisoned proxies using an
isolated temporary SQLite database. No artifact was published. Installed
footprint, idle memory, and representative latency were not measured on final
binaries; the replacement backend smoke's 3.8-second staging and 1.8-second
extracted startup observations are not cold-start benchmarks.

The SHA-512 in `latest.yml` matches the replacement setup byte-for-byte.
Version is 2.1.0 in the setup metadata, extracted desktop PE, `app.asar`
package metadata, bundled backend `VERSION`, source archive, and repo `VERSION`.
The read-only candidate preflight passed under both PowerShell 7 and Windows
PowerShell 5.1, warning correctly that the installer is unsigned.
The packaged license matches the repository license. No generated database,
checkpoint, cache, test fixture, `.env`, private key, or development Node
dependency appeared in inspected package paths. The bundled `certifi/cacert.pem`
is a public CA trust bundle, not a private key. This is a path/content-pattern
screen, **not** a complete secret or license audit. Build provenance remains
a dirty working tree based on `e1e88b7`, not a reviewable immutable commit.
No dependency manifests or lockfiles changed during this verification pass.
The 2026-10-23 license inventory found 122 frontend production package records,
16 desktop Node records, eight website records, and 31 pinned backend Python
runtime packages. The current portable ZIP has RedForge and Electron root
licenses, 15 of the 16 `app.asar` Node modules carry license files, and the
frozen backend exposes only selected Python license texts. This is not a
complete bundled notice set or legal clearance. Exact metadata and reviewer
actions are in the [legal issue list](release-legal-review.md). The website
notice incorrectly described Starlette as MIT; source now says BSD-3-Clause,
labels the dependency list partial, and adds certifi MPL-2.0. The rebuilt
website includes that exact notice. It has not been deployed or legally signed
off. No Windows package source changed during this pass.
Against the rejected stale-UI candidate, replacement setup grew **45,962
bytes**, portable ZIP **49,324 bytes**, source ZIP **142 bytes**, and source
tar.gz **289 bytes**. These are compressed artifact sizes, not installed
footprint or runtime-memory measurements.

Commands executed for the current source and candidate (from the repository
unless noted) included:

```powershell
C:\Users\LOQ\AppData\Local\Temp\redforge-build-venv-1792672599678\Scripts\python.exe -m pytest backend/tests -q
C:\Users\LOQ\AppData\Local\Programs\Python\Python312\python.exe -m pytest backend/tests -q
node --test desktop/test/*.test.js
ruff check backend/app/runtime/providers/base.py backend/app/runtime/providers/ollama.py backend/tests/test_network_policy.py cli/redforge
# In isolated temporary build copy:
C:\Users\LOQ\AppData\Local\Temp\redforge-build-venv-1792672599678\Scripts\python.exe desktop/scripts/stage-backend.py --require-frozen
C:\Users\LOQ\AppData\Local\Temp\redforge-build-venv-1792672599678\Scripts\python.exe scripts/smoke_packaged_app.py desktop/resources/backend
Push-Location desktop
.\node_modules\.bin\electron-builder.cmd --win --publish never
Pop-Location
# From the repository, against the extracted replacement portable ZIP:
$env:REDFORGE_NETWORK_PROFILE='strict'
$env:HTTP_PROXY='http://127.0.0.1:1'; $env:HTTPS_PROXY='http://127.0.0.1:1'
$env:ALL_PROXY='http://127.0.0.1:1'; $env:NO_PROXY=''
python scripts/smoke_packaged_app.py <extracted-resources-backend> --local-model mistral:latest
python scripts/build_release.py --output-dir <new-isolated-temp-directory>
& .\scripts\verify_windows_candidate.ps1 -SetupPath <setup> -SetupSha256 <expected> `
  -PortableZipPath <zip> -PortableSha256 <expected> -SourceZipPath <source-zip> `
  -SourceSha256 <expected>
```

The proxy reproduction used `HTTP_PROXY`, `HTTPS_PROXY`, and `ALL_PROXY` set
to an unreachable `http://127.0.0.1:59999`, with `NO_PROXY` empty. Against an
already running local Ollama, default `httpx.get` raised `ConnectTimeout`,
whereas `httpx.get(..., trust_env=False)` returned HTTP 200. Regression tests
then used `127.0.0.1:1` as the unreachable proxy and a temporary loopback test
server. The preceding source-archive startup log is at
`C:\Users\LOQ\AppData\Local\Temp\redforge-source-guard-smoke-1792691488962\redforge-2.1.0\.redforge\redforge.log`.
No network packet-capture log exists for the current candidate.

## Product risk register

| Risk | Impact | Current control | Owner action |
| --- | --- | --- | --- |
| App-level strict policy is mistaken for an air gap | Sensitive data could leave through external runtimes, browsers, or third-party code | Explicit profile, backend guards, offline library flags, and qualified documentation | Observe final binaries on each supported OS and use OS network isolation for a no-egress guarantee. |
| Local management API is exposed outside the machine | Workspace and captured trace data lack a multi-user authentication boundary | Strict CLI rejects non-loopback binding; management UI is intended for one local operator | Test packaged binding and reverse-proxy scenarios; do not market as a shared service. |
| Model and training dependencies are unavailable in strict mode | First-run tasks may fail without a preloaded model or offline wheels | Disabled download controls, actionable install guidance, and successful Windows source install from a local wheelhouse | Exercise end-to-end inference with a preloaded local model on a fresh machine. |
| Consumer upgrade loses or strands local data | Evaluation and audit history could become inaccessible | Fresh and synthetic legacy migrations pass; destructive downgrade is refused | Rehearse backup, upgrade, restore, and interrupted migration on consented representative data. |
| Earlier smoke may have opened default user DB | Possible unreviewed migration/write during test | Harness now forces a temporary SQLite URL; default DB `quick_check` passed and its mtime stayed fixed after the fix | Owner should back up and review current DB before any upgrade; no before snapshot exists to prove unchanged records. |
| License/privacy or package claims are wrong | Distribution or user-trust risk | Draft notices, privacy review, dependency audits, and an issue list | Obtain qualified legal/security review of final platform artifacts and actual hosting behavior. |

## Release gate matrix

| Gate | Status | Evidence or required next action |
| --- | --- | --- |
| Python 3.11 full tests | PASS | Repeated the CI command from `backend/` with strict profile: 677 passed in 125.37 seconds; one Starlette/httpx deprecation warning. Full Ruff and `git diff --check` passed. |
| Python 3.12 full tests | PASS | Final sequential run passed 677 tests in 385.70 seconds with no warnings; JUnit report saved. An earlier concurrent run's teardown warning did not recur. |
| Frontend and website production builds | PASS | Both `npm run build` commands completed again with TypeScript checks; frontend graph has 60 JS chunks plus CSS and its `index.html` hash matches the extracted current portable. Website was rebuilt after the notice correction. |
| Full desktop tests, lint, and version guards | PASS | Repeated 20 Node tests, full Ruff, version consistency, desktop config guard, and `git diff --check` passed. |
| Phase 2 server behavior | PASS | Registry, immutable versions, linked traces/evaluations, capture/redaction, and retention tests passed. |
| Workbench collection refresh | PASS | Isolated browser create/list flow completed without reload or page error. |
| Fresh and synthetic legacy migration | PASS | Both reached Alembic head; synthetic legacy prompt/version remained intact. |
| Strict no-egress application controls | PASS | Source route/provider/CLI tests passed. Superseded binary returned 403 for four prohibited actions; replacement bundled backend returned a strict profile and real local inference. Full replacement Electron/blocked-route rehearsal remains untested. This is not a complete egress guarantee. |
| Proxy-environment regression | PASS | Source tests cover HTTP/HTTPS/ALL_PROXY, empty and nonempty NO_PROXY, external DNS/direct IP rejection, alternate provider/CLI paths, redirects, and connected-mode behavior. |
| CI strict boundary subset | PASS | Repeated the strict-profile CI command from `backend/`: 60 tests passed in 11.41 seconds. |
| Packaged proxy-environment rehearsal | PASS | Extracted replacement ZIP's bundled backend served UI and real local `mistral:latest` inference with poisoned proxies and empty NO_PROXY. Electron process itself was not launched under these variables. |
| Current candidate sustained network observation | NOT TESTED | Earlier pre-proxy-fix guarded binary had zero external endpoints across 50 TCP samples in 55 seconds; current binary has no packet capture. |
| OS-level no-egress isolation | NOT TESTED | Use firewall/air gap and sustained packet capture before any no-egress guarantee. |
| Windows artifact build and integrity | PASS | Replacement unsigned setup and portable ZIP built; 389 ZIP entries passed CRC, feed SHA-512, package/PE/backend versions, license, and current UI match passed. Old stale-UI candidate is rejected. |
| Extracted portable bundled-backend smoke | PASS | Freshly extracted replacement ZIP's bundled backend served health, strict profile, current UI, all chunks, and real local Ollama inference under poisoned proxies. Not a clean VM install. |
| Replacement Electron shell and blocked routes | NOT TESTED | Full replacement `RedForge.exe` was not live-tested. Recheck four blocked routes and capture Electron startup on disposable VM. |
| Source archive integrity and offline instructions | PASS | Replacement ZIP CRC and tar.gz member checks passed. `install.cmd`/`install.sh` use `--no-index` and optional `REDFORGE_WHEELHOUSE` in strict mode, matching installation docs. |
| Replacement source archive offline install | PASS | Current ZIP's `install.cmd` installed pinned dependencies in a fresh Python 3.11.16 virtual environment from local wheelhouse using `--no-index`. |
| Replacement source archive startup | PASS | Extracted ZIP launched under its fresh virtual environment with isolated SQLite. Health, strict profile, all UI chunks, and real local Ollama inference passed under poisoned proxies. |
| Smoke-test DB isolation | PASS | Harness now sets temporary `REDFORGE_DATABASE_URL`; source-archive smoke passed and default DB mtime stayed unchanged. Earlier smoke may have written that DB; integrity check passed, content-diff unavailable. |
| Windows signing and consumer trust | BLOCKED | Setup and portable executable are `NotSigned`; owner must decide and validate signing/trust posture. |
| Disposable Windows VM availability | BLOCKED | No Windows Sandbox, Hyper-V VM, VirtualBox, VMware, or clean Windows test machine available on this host. Prepared [VM rehearsal worksheet](release-vm-rehearsal.md); operator must run it on a disposable VM. |
| Windows clean install and upgrade | NOT TESTED | Test signed or honestly labeled unsigned setup on a disposable clean VM. |
| Representative backup and restore | NOT TESTED | Use a copied, consented dataset; verify restoration after upgrade failure. |
| Windows uninstall behavior | NOT TESTED | Check application removal and documented workspace retention on disposable VM. |
| Current macOS/Linux packages | NOT TESTED | Build, install, and smoke-test on each supported OS. |
| Final installed footprint, idle memory, operation latency | NOT TESTED | Compressed artifact sizes were measured; these runtime measurements were not. |
| macOS notarization and cross-platform update behavior | NOT TESTED | Validate platform signing/notarization, update feeds, upgrade, and rollback on their target OSes. |
| Latest hosted GitHub CI on committed HEAD | FAIL | [Run 39648341799](https://github.com/BRGOVIND/REDFORGE/actions/runs/39648341799) failed trace SDK sync-stream test on old HEAD `e1e88b7`; current uncommitted candidate has no hosted run. |
| Hosted CI on current candidate | BLOCKED | Requires an authorized reviewed commit/branch; no commit or push performed. |
| Frontend production dependency advisories | BLOCKED | 2026-10-23 `npm audit --omit=dev --json` still reports two moderate React Router advisories. Upstream patched in 7.18.0; npm proposes 7.18.4, a major migration. Current declarative UI lacks the SSR precondition for one finding, but redirect paths still need review and reviewer-approved remediation/risk decision. Desktop and website production audits report zero. |
| Third-party licenses and notices | BLOCKED | Lockfile metadata inventoried and current ZIP/asar notice files inspected. Python notices are incomplete in the frozen package; see [legal issue list](release-legal-review.md). File-level SBOM, notice assembly, model/dataset terms, and qualified review remain. |
| Privacy claims and security sign-off | BLOCKED | Owner and qualified reviewers must assess actual artifacts, hosting, trace handling, local API exposure, and claims. |
| Accidental oversized local archive | PASS | Unsafe generated copy was quarantined outside `releases`; original backend data untouched. |

## Clean Windows operator checklist

The [VM rehearsal worksheet](release-vm-rehearsal.md) gives exact PowerShell
preflight, packet-capture, proxy, firewall, evidence-hash, and recovery steps.
It has not been executed. The summary below remains the acceptance checklist.

Use a disposable Windows 11 VM with an isolated network that allows capture,
not this development host. Record OS build, VM image, installed prior version,
clock time, candidate path, SHA-256, signature status, and capture-tool version.
Take a VM snapshot before installation. Copy the replacement candidate artifacts
and `scripts/verify_windows_candidate.ps1` into the VM. Run its read-only
preflight before executing anything (it checks exact hashes, ZIP layout,
version, and signature status):

```powershell
& C:\RedForge-test\verify_windows_candidate.ps1 `
  -SetupPath C:\RedForge-test\RedForge-v2.1.0-Setup.exe `
  -SetupSha256 6AC524632BE437375022BB620E638ABCE4418025E26AEA3347F6CBEBFCCDD27B `
  -PortableZipPath C:\RedForge-test\RedForge-v2.1.0-Portable.zip `
  -PortableSha256 DFA6129BD5B7BF321EC01441D776B7544B60BBBE21052AF223FC7A7A9D37792B
```

Start a full packet capture **before** setup, and retain it through first
launch, at least five minutes of idle time, local-provider discovery, local
inference, blocked strict-mode actions, and uninstall. Capture DNS, UDP, TCP,
IPv4, and IPv6, not just sampled established TCP connections. An elevated
`pktmon` capture or Wireshark capture is suitable; record the exact command,
interface, start/stop times, process tree, and any external destination. Export
DNS query/response records and DNS cache snapshots as well as flows. Repeat
with OS firewall outbound denial to test operation without successful egress.
Attribute traffic to RedForge, its bundled backend, Electron children, the
local runtime, or unrelated OS processes; do not infer attribution from a bare
destination alone.

1. Start packet capture before setup. Install interactively and record trust
   prompts, installer log, result, installed files, first-launch time, workspace
   path, API bind address, and process tree from startup. Use only synthetic VM
   data. Verify first-run and a second launch after normal shutdown.
2. Leave capture running through at least five minutes idle, local provider
   discovery, and one inference from a preloaded model. Run once with normal
   environment, then restart with `HTTP_PROXY`, `HTTPS_PROXY`, and `ALL_PROXY`
   set to a VM-local unreachable proxy and `NO_PROXY` empty; repeat with
   `NO_PROXY=127.0.0.1,localhost`. Confirm local inference still works.
3. In strict mode, try hosted provider selection and generation, Model Hub and
   Ollama pulls, onboarding pull, training-runtime dependency install, update
   check/download, remote trace ingestion, and opening an external link. Test
   a loopback service returning an external HTTP redirect. Record each response,
   user-facing error, and whether any DNS query or connection occurred. Check
   Electron/Chromium children, updater, Python CLI/SDK, and subprocess paths
   separately; a blocked UI control alone is insufficient.
4. Repeat core local workflows with OS outbound denial. Attribute every packet
   to RedForge, bundled backend, local model runtime, OS, or other software.
   A trusted local runtime may have its own network behavior; record it
   separately. Any unexplained application-origin external DNS, UDP, TCP,
   IPv4, or IPv6 traffic fails the no-egress gate.
5. Restore the VM snapshot. Install a supported earlier version with synthetic
   project, prompt, trace, and evaluation records. Back up workspace and DB,
   verify backup checksum and SQLite integrity, install 2.1.0, compare record
   counts and representative data, and restart. Interrupt an isolated copy of
   the migration, then restore and verify its checksum/integrity and records.
   Never trial a destructive downgrade on live data.
6. Uninstall inside the disposable VM. Verify application removal and that
   workspace retention matches documentation. Record remaining files, registry
   entries, processes, and network traffic. Restart VM and confirm no orphaned
   process/update task or unintended data loss.
7. Archive redacted packet capture, DNS evidence, installer/backend logs,
   hashes, screenshots, exact commands, durations, process attribution, and
   reviewer sign-off. A quiet capture is limited evidence, not proof of an air
   gap; enforce a true no-egress deployment at OS or network level.

## macOS and Linux target-platform gate

The release workflow declares native `macos-latest` and `ubuntu-latest` builds
alongside Windows. The desktop config targets macOS x64 and arm64 DMG plus ZIP,
and Linux x64 AppImage plus deb. Windows checks cannot validate those targets.
On each target OS, from a clean checkout of the *reviewed candidate commit*,
install Python 3.11 and Node 22, install pinned backend dependencies and
PyInstaller 6.21.0/hooks 2026.9, then run:

```bash
python scripts/version.py --check --release
ruff check .
python -m pytest backend/tests -q
python desktop/scripts/stage-backend.py --require-frozen
python scripts/smoke_packaged_app.py desktop/resources/backend
cd desktop
npm ci --no-audit --no-fund
npm test
npx electron-builder --publish never
```

Inspect all produced package names, hashes, signatures, bundled version,
licenses, asset graph, and update feed. Install and run each architecture on
its target OS with an isolated temporary SQLite database; test current UI,
preloaded local inference, strict blocked operations, offline behavior,
upgrade/restore/uninstall, and sustained OS-level network capture. On macOS,
validate Developer ID signing, hardened runtime/entitlements, notarization,
Gatekeeper, and both architectures. On Linux, validate AppImage and deb on a
supported distribution, package dependencies, executable permissions, desktop
integration, data retention, and update behavior. Record exact OS version,
commands, artifacts, logs, capture limits, and reviewer decision. These are
NOT TESTED gates until target-platform evidence exists.

## Before tagging or publishing a release

1. Inspect the final desktop binary under network observation. Reconcile the
   constitution's structural no-egress language with the application-level
   policy and the retained connected profile. Do not silently amend it.
2. Push to a review branch only when authorized, then rerun actual GitHub CI.
   Local Python 3.11 success does not prove hosted CI or cross-platform success.
3. Back up and rehearse migration plus restore on representative user data. Do
   not test a destructive downgrade: audit-bearing migrations intentionally
   refuse it.
4. Keep the current Windows hashes only if reviewed source remains unchanged;
   rebuild after any further code change. Build and smoke-test macOS and Linux
   packages on their target OSes. Verify bundled license notices, update feeds,
   checksums, signing, and notarization where applicable.
5. Obtain owner and qualified legal/security review of website privacy claims,
   third-party licenses, sensitive-data handling, local API exposure, pricing
   estimates, and evidence-only release gates. See [legal issue list](release-legal-review.md).

No commit, push, deployment, or release was performed by this audit.
