# RedForge 2.1.0 clean Windows rehearsal

**Operator worksheet. Not yet executed.** Run only in a disposable Windows 11
VM with a local console and a snapshot. Never use the developer's installed
RedForge 1.2.0 or existing data. The VM needs administrator access for packet
capture and firewall tests, enough free space for multi-file packet logs, and a
preloaded, trusted local model. Copy installers and test tools through controlled
media. Keep the VM disconnected from production accounts and data.

## Identify the exact candidate

Copy these three files plus `scripts/verify_windows_candidate.ps1` to
`C:\RedForge-test` inside the VM. The checksums identify the current candidate,
which supersedes earlier Windows builds:

| File | SHA-256 |
| --- | --- |
| `RedForge-v2.1.0-Setup.exe` | `6AC524632BE437375022BB620E638ABCE4418025E26AEA3347F6CBEBFCCDD27B` |
| `RedForge-v2.1.0-Portable.zip` | `DFA6129BD5B7BF321EC01441D776B7544B60BBBE21052AF223FC7A7A9D37792B` |
| `redforge-2.1.0.zip` | `B43A96D02A4AE6FE8AC1877721A4931192E0921C3BDAA9F6DF67E2E7F7043E39` |

In the VM's PowerShell console, before executing the installer:

```powershell
Set-Location C:\RedForge-test
& .\verify_windows_candidate.ps1 `
  -SetupPath .\RedForge-v2.1.0-Setup.exe `
  -SetupSha256 6AC524632BE437375022BB620E638ABCE4418025E26AEA3347F6CBEBFCCDD27B `
  -PortableZipPath .\RedForge-v2.1.0-Portable.zip `
  -PortableSha256 DFA6129BD5B7BF321EC01441D776B7544B60BBBE21052AF223FC7A7A9D37792B `
  -SourceZipPath .\redforge-2.1.0.zip `
  -SourceSha256 B43A96D02A4AE6FE8AC1877721A4931192E0921C3BDAA9F6DF67E2E7F7043E39
Get-AuthenticodeSignature -LiteralPath .\RedForge-v2.1.0-Setup.exe
```

Stop if any hash differs. `NotSigned` is expected for this internal candidate;
record the Windows trust prompts instead of treating them as a pass.

## Capture before installation

In an elevated VM PowerShell console, run the commands below before setup.
They use Microsoft's in-box Packet Monitor and capture all components without
destination filters. Full packets can contain sensitive content; use synthetic
data and restrict access to the evidence. Multi-file mode prevents overwriting
older packets but can fill the VM disk. Check free space during the test.

```powershell
Set-Location C:\RedForge-test
pktmon filter remove
Get-DnsClientCache | Export-Csv .\dns-before.csv -NoTypeInformation
Get-NetFirewallProfile | Select-Object Name,Enabled,DefaultOutboundAction |
  Export-Csv .\firewall-before.csv -NoTypeInformation
pktmon start --capture --trace --provider Microsoft-Windows-TCPIP `
  --pkt-size 0 --file-name C:\RedForge-test\redforge.etl `
  --file-size 1024 --log-mode multi-file
pktmon status
```

Record VM clock, OS build, interface names, snapshot ID, `pktmon` version,
capture start time, and available disk. Keep capture running through setup,
first launch, at least five minutes idle, local inference, blocked operations,
normal shutdown, and uninstall. Take process and socket snapshots at each phase:

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.Name -match 'RedForge|redforge-backend|Ollama' } |
  Select-Object ProcessId,ParentProcessId,Name,ExecutablePath,CreationDate |
  Export-Csv C:\RedForge-test\processes-PHASE.csv -NoTypeInformation
Get-NetTCPConnection |
  Select-Object LocalAddress,LocalPort,RemoteAddress,RemotePort,State,OwningProcess |
  Export-Csv C:\RedForge-test\tcp-PHASE.csv -NoTypeInformation
Get-NetUDPEndpoint |
  Select-Object LocalAddress,LocalPort,OwningProcess |
  Export-Csv C:\RedForge-test\udp-PHASE.csv -NoTypeInformation
```

Replace `PHASE` with a distinct name each time. These snapshots supplement
packet capture; they can miss brief connections. Use the TCP/IP event trace,
process tree, and packet timestamps for attribution. If process attribution is
unclear, keep the network gate open. Include DNS, UDP, TCP, IPv4, IPv6, and
Electron child processes. Distinguish RedForge, its frozen backend, local model
runtime, OS services, and unrelated processes.

## Functional and policy sequence

1. Install interactively from `C:\RedForge-test\RedForge-v2.1.0-Setup.exe`.
   Record installation path, trust prompts, installer log, process tree, startup
   time, workspace path, bound addresses, and the first and second launches.
2. Confirm `/healthz`, `/api/providers` with `network_profile=strict`, current
   UI, and inference from a preloaded local model. Record request IDs,
   responses, model identity, and latency without logging actual sensitive
   prompts.
3. Close RedForge. In the same VM console set the variables below, then
   relaunch the **installed** executable. Repeat discovery and local inference.
   Repeat with `NO_PROXY=127.0.0.1,localhost`.

   ```powershell
   $env:REDFORGE_NETWORK_PROFILE = 'strict'
   $env:HTTP_PROXY = 'http://127.0.0.1:1'
   $env:HTTPS_PROXY = 'http://127.0.0.1:1'
   $env:ALL_PROXY = 'http://127.0.0.1:1'
   $env:NO_PROXY = ''
   # Launch the installed RedForge.exe from this console, then repeat tests.
   ```

4. Exercise hosted-provider selection and generation, Model Hub and Ollama
   pulls, onboarding pull, training-runtime dependency install, updater
   check/download, remote trace ingestion, and an external-link click. Test
   CLI/SDK and a loopback HTTP endpoint that redirects to an external URL.
   Record HTTP result, UI error, DNS, packets, and process for each attempt.
   A disabled button alone does not pass this gate.
5. In the disposable VM only, save firewall settings, set outbound default to
   `Block`, repeat local discovery and inference, and inspect active allow
   rules. A firewall default block does not override explicit allow rules.
   Restore saved settings in the same session. For a stronger test, disconnect
   the VM's virtual NIC at the hypervisor while keeping loopback available.

   ```powershell
   $vmFirewallBefore = Get-NetFirewallProfile |
     Select-Object Name,DefaultOutboundAction
   Set-NetFirewallProfile -Name Domain,Private,Public -DefaultOutboundAction Block
   Get-NetFirewallProfile |
     Select-Object Name,DefaultOutboundAction
   # Repeat local inference and blocked-operation tests here.
   foreach ($vmProfile in $vmFirewallBefore) {
     Set-NetFirewallProfile -Name $vmProfile.Name `
       -DefaultOutboundAction $vmProfile.DefaultOutboundAction
   }
   ```

6. Keep capture running. Uninstall in the VM and record remaining app files,
   workspace files, registry entries, services, and processes. Restart VM and
   verify no orphaned process or update task. Observe intended data retention.

Stop capture only after those steps:

```powershell
pktmon stop
Get-DnsClientCache | Export-Csv C:\RedForge-test\dns-after.csv -NoTypeInformation
Get-ChildItem -LiteralPath C:\RedForge-test -Filter 'redforge*.etl' |
  ForEach-Object {
    pktmon etl2pcap $_.FullName --out ($_.FullName + '.pcapng')
  }
Get-ChildItem -LiteralPath C:\RedForge-test -File |
  ForEach-Object { Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256 } |
  Export-Csv C:\RedForge-test\evidence-hashes.csv -NoTypeInformation
```

Retain original ETL as well as pcapng: conversion loses component and drop
metadata. Inspect trace with a packet analyzer and Windows event tools. Log
capture start/stop times, file sizes, dropped packets, DNS queries, connection
destinations, process attribution, and gaps. A quiet trace alone does not prove
an air gap.

## Upgrade and recovery on a separate VM snapshot

Restore the clean snapshot. Install a supported previous RedForge version and
create synthetic project, prompt, trace, evaluation, and file records. Identify
the actual workspace and SQLite path in that VM; defaults can differ between
desktop and source installations. Close all RedForge processes before copying
data. Back up the full workspace and SQLite database to separate VM media,
record SHA-256 for every file, and run SQLite `PRAGMA integrity_check` on the
copy using a separate offline test tool. Never point this test at the owner's
normal database.

Repeat the capture setup before installing the previous version and retain a
continuous trace through upgrade, first 2.1.0 launch, restore, and uninstall.
Use distinct filenames from the clean-install trace. Record any capture gap.

Install 2.1.0, inspect migration logs, reopen representative records, compare
counts and stable IDs, then restart. On another snapshot, interrupt migration
on synthetic data; restore the verified backup and confirm integrity plus
records. Do not test destructive downgrade against real data. Run uninstall
against both upgraded and fresh-install snapshots, recording retained data.

## Evidence and gate decision

Archive checksums, exact installer and prior-version identity, VM snapshot ID,
commands, start/stop times, ETL and pcapng, DNS and process snapshots, firewall
settings, logs, redacted screenshots, backup checksums, integrity output,
record comparisons, and reviewer names. Record PASS/FAIL for each scenario.
Any unexplained application-origin external traffic, missing packet interval,
unattributed flow, failed local inference, failed restore, or data loss leaves
the relevant release gate open. Security and owner review remain separate gates.

Packet Monitor command syntax: [Microsoft pktmon start](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/pktmon-start),
[ETL conversion](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/pktmon-etl2pcap).
Firewall syntax: [Microsoft Set-NetFirewallProfile](https://learn.microsoft.com/en-us/powershell/module/netsecurity/set-netfirewallprofile).
