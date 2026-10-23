# Network profiles and no-egress boundary

The 2.1.0 candidate defaults to `REDFORGE_NETWORK_PROFILE=strict`. This is an
application-level policy, not a sandbox or firewall. Unknown/misspelled values
also behave as strict. `REDFORGE_NETWORK_PROFILE=connected` explicitly restores
the preserved network integrations for a separately configured deployment; it
is not the no-egress consumer release profile.

| Operation | Strict profile | Connected profile |
| --- | --- | --- |
| Inference | Supported local providers at loopback URLs only | Local and configured hosted providers |
| Model Hub, Ollama pull, onboarding pull | Rejected before download | Explicit user action can download |
| Training-runtime dependency installation | Rejected before package index access | Explicit user action can install |
| Desktop and CLI update checks | No automatic check; manual check/update rejected | Existing update flow |
| Electron Chromium background requests | Background services disabled; external web requests canceled | Existing Chromium behavior |
| Desktop external links | Address can be copied, but RedForge does not open the browser | Links open in the system browser |
| Source `redforge install` | Local files/wheelhouse only, no index | Existing installer behavior |
| SDK trace ingestion | Loopback endpoint only | Configured endpoint |
| API trace ingestion | Loopback peer only, project token still required | Token-authorized remote ingestion allowed |
| Health internet probe | Skipped | Existing optional check |
| Server bind via CLI | Loopback only, even with `--yes` | Non-loopback requires exposure warning |

The active profile is returned by `/api/providers` and `/api/system/checks` and
shown in setup. Strict mode sets the Hugging Face, Transformers, and Datasets
offline environment flags at backend startup. Already installed models,
local-only evaluation, prompt registry, trace exploration, anomaly monitoring,
and feedback workflows remain available, subject to their own dependencies.

## Verified candidate behavior and limits

The first proxy-guarded 2.1.0 Windows candidate was inspected on 2026-10-22,
then superseded because it carried a stale frontend. The replacement candidate
was inspected on 2026-10-23.
Electron calls its Chromium startup switches before `app.whenReady()`, installs
the default-session external-request interceptor before loading either window,
and blocks external navigation and `shell.openExternal` in strict mode. Its
updater returns before creating an updater or checking a feed. Backend provider
selection checks provider names and loopback URLs before constructing or using
HTTP clients; model downloads, training dependency installation, remote trace
ingestion, CLI non-loopback binding, and CLI update checks have separate guards.
Routing uses the same runtime manager, so an explicit routing policy does not
bypass the strict provider check. The connected profile is a separate explicit
configuration, not a fallback after local errors.

Validation also found that Python's HTTP clients followed proxy environment
variables even for a loopback URL when `NO_PROXY` was empty. A hostile or
misconfigured `HTTP_PROXY` could therefore receive local inference or trace
requests. Strict-mode provider clients now set `trust_env=False`; the CLI and
trace SDK use a no-proxy, no-redirect loopback opener. Connected mode retains
the prior proxy behavior. Regression tests use a deliberately unreachable
loopback proxy and a real local test server; both local provider families and
CLI calls still succeed, while a redirect to an external URL is rejected.

The proxy-fix baseline passed 667 backend tests on each interpreter and 20
desktop tests. The superseded frozen backend served all 55 referenced JavaScript
chunks. That earlier extracted portable Windows build returned HTTP
403 with `network_policy_blocked` for Model Hub download, onboarding pull,
training-runtime install, and a hosted OpenAI Playground call. The same build
returned HTTP 200 for a real local Ollama `mistral:latest` Playground call.
The replacement ZIP passed integrity and current-frontend comparison. Its
extracted bundled backend served all 60 JavaScript chunks and completed a real
local Ollama inference with poisoned HTTP/HTTPS/ALL_PROXY variables and empty
NO_PROXY. Its Electron shell and blocked routes were not rerun, and no packet
capture was taken. An earlier, now-superseded build had process-level TCP sampling with zero
external endpoints during 55 seconds and 50 samples after Chromium guards were
added; the replacement candidate has not had sustained packet capture.
These are bounded path checks, not a
complete packet capture or proof that no packet can leave. No clean-machine
installer test or sustained network observation has been completed. A genuine
no-egress deployment must use operating-system or network-level outbound
enforcement, including DNS, UDP, TCP, IPv4, and IPv6, plus a trusted local
runtime and validation on each supported platform.

## Local setup and recovery

Install a local runtime and model independently while you have connectivity, or
transfer trusted model files from another machine. Start RedForge with its
default loopback address. Do not set hosted-provider credentials for strict
mode. If a download or update action reports `network_policy_blocked`, it has
not started a network request; use an already installed local asset. Source
installers need dependencies already installed or an offline wheelhouse set via
`REDFORGE_WHEELHOUSE`. An isolated or air-gapped machine is the appropriate
deployment control when network isolation is required.

## Threat model and residual risks

The protected assets are prompt/response bodies, project traces, provider
credentials, local models, reports, and the SQLite database. Relevant attackers
include a malicious webpage targeting the loopback API, another local process,
a compromised local runtime, a malicious imported model/dataset, and an actor
with access to a connected deployment.

Controls include loopback binding in strict CLI use, provider URL/provider-name
checks at runtime construction and request boundaries, explicit download/update
blocks, Chromium background-network switches and a desktop web-request guard,
offline library flags, project-scoped trace tokens, capture-off defaults,
payload bounds, redaction, and limited CORS origins. These are defense in depth,
not authentication for the desktop management API. A local process can call
that API. CORS is not a general authorization mechanism; local browser/CSRF and
file-import surfaces still warrant dedicated penetration testing. An external
runtime bound to loopback may itself contact the internet or proxy elsewhere.
The site loaded in a separate browser independently requests fonts and release
metadata. Strict desktop mode offers to copy external links instead of opening
them; the user can still paste one into a separate browser outside RedForge's
control. Strict mode does not constrain OS services, user shell commands,
third-party plugins, or model code. Reverse proxies can obscure a remote trace
client as loopback, so do not expose the API through one. Use OS-level network
controls, filesystem permissions, and a trusted local runtime for high-assurance
deployments.

Do not claim regulatory compliance or full offline isolation from this policy.
Deployment location, processed data, jurisdiction, retained traces, and vendor
terms determine additional obligations; obtain qualified security/legal review
before public or enterprise release.
