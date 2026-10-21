# Phase 2 build measurements

Measured on Windows on 2026-10-21 after `npm run build`. Comparison uses the Phase 1 development-build figures in `phase1-measurements.md`. Each file was gzip-compressed separately at level 9. These figures are build artifacts, not transfer-size or runtime-memory guarantees.

| Artifact | Phase 1 | Phase 2 | Change |
| --- | ---: | ---: | ---: |
| Frontend HTML/CSS/JS, raw | 1,110,757 B | 1,117,893 B | +7,136 B |
| Frontend HTML/CSS/JS, gzip | 338,630 B | 341,497 B | +2,867 B |
| Full `frontend/dist`, raw | 1,311,821 B | 1,318,957 B | +7,136 B |
| Full `frontend/dist`, gzip | 537,279 B | 540,317 B | +3,038 B |
| Trace Explorer and detail lazy chunks, raw | 10,222 B | 13,340 B | +3,118 B |
| Trace Explorer and detail lazy chunks, gzip | 3,853 B | 4,828 B | +975 B |

No package manifest or lockfile changed. Phase 2 adds **zero mandatory third-party dependencies**. Prompt history uses the existing Workbench tables; privacy adds two small indexed tables. No new desktop installer was built, so packaged-app size, startup time, and idle memory changes remain unmeasured. The existing 152,834,887 B Windows installer predates these changes and is not a Phase 2 measurement.

The CLI packaging check (`python -m build cli --no-isolation --sdist --wheel`) passed. Its current wheel is 37,512 B and source archive is 32,227 B. No comparable Phase 1 CLI package was retained, so no package delta is claimed.
