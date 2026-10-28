# Landing-page launch check, 26 October 2026

## Decision

**Local landing-page checks passed; public launch is pending owner review and deployment verification.** This checks `website/`, not a new desktop release. RedForge 2.1.0 remains an internal test candidate under `docs/release-readiness-audit.md`. No commit, push, deployment, tag or publication was performed.

## Verified results

| Check | Status | Evidence |
| --- | --- | --- |
| TypeScript and production build | PASS | `npm run build` completed with Vite 7.3.7. |
| Production static serving | PASS | `npm run preview -- --host 127.0.0.1 --port 4174 --strictPort`; HTML, compiled JS/CSS, icons, manifest, social image and screenshots returned 200 with correct content types. |
| Internal navigation | PASS | All mounted fragment links resolve; no duplicate element IDs. |
| Public documentation links | PASS | GitHub raw main versions of RELEASE_NOTES.md, installation.md, quickstart.md, faq.md and release-readiness-audit.md returned 200. |
| Published download metadata | PASS | GitHub latest-release API returned non-draft, non-prerelease v2.0.3. All six configured installer/portable names and SHA256SUMS.txt exist in that release. Installers were not downloaded or executed. |
| Legal/static routes | PASS | privacy.html, terms.html, license.html, open-source-notice.html, robots.txt and sitemap.xml returned 200 locally. This verifies availability, not legal approval. |
| Gallery and modal | PASS | Vertical document scrolling drives all five screens inside a sticky scene. At progress 0, .25, .5, .75 and 1, the desktop panel stays at top 100 px; after the endpoint it releases. Reverse scrolling and keyboard arrows work. An actual 850 px browser scroll advanced to Observe while staying pinned. Pixel transitions, modal blur, zoom/pan, Escape and focus restoration passed. |
| Navigation and workflow | PASS | Desktop 390 x 58 compass/ruler expands to 1040 x 72 on hover or activation. Keyboard Enter opens and focuses Inside; Escape closes and returns focus to the visible compass. Mobile menu remains available. Enlarged workflow fits without document overflow. |
| Intro and feature previews | PASS | Root entry animates the logo into the visible navbar slot. Clicking the home logo replays it. Hovered workflow rows retain their matching screenshot; clicking opens the blurred-backdrop dialog. Inline screenshot buttons provide access below 1024 px. |
| Responsive layout | PASS | Checked 320 x 740, 390 x 844, 900 x 900 and 1440 x 1000. No horizontal document overflow. |
| Reduced motion | PASS | Screenshot canvases are hidden, clear images remain, navigation still works. Reduced motion and desktop viewports shorter than 520 px and mobile viewports shorter than 700 px use an unpinned horizontal gallery without a tall scene spacer. |
| Automated accessibility | PASS with manual review pending | Latest production scan: 44 rules passed, zero violations, one incomplete color-contrast rule covering 41 nodes. Manual contrast review remains required. |
| Browser errors | PASS | Error log empty during the production interaction checks. |
| Mobile download classification | PASS | Windows, macOS, Linux, Android, iPhone and iPad desktop-mode cases checked against compiled `detectOS`. Mobile devices now show platform choice instead of an inappropriate Linux/macOS primary download. |
| Production dependencies | PASS | `npm audit --omit=dev --json`: zero known findings. This is not proof of absence of vulnerabilities. |
| Complete dependency audit | PASS for current registry response; historical finding needs review | Latest `npm audit --include=dev --json` returned zero findings. Earlier scan reported three moderate development findings. No dependency remediation occurred; see below. |
| Diff whitespace | PASS | `git diff --check`; line-ending conversion warnings only. |
| Hosted CI for these edits | NOT TESTED | Changes remain local and uncommitted. |
| Firefox, Safari and physical touch-device verification | NOT TESTED | Browser checks used Chromium viewport emulation. |
| Hosted CDN, TLS, redirects, caching and security headers | NOT TESTED | Local Vite preview does not validate the production host. |
| Real-device performance | NOT TESTED | No Lighthouse/Core Web Vitals or low-end-device frame-rate certification claimed. |
| Qualified legal/security approval | BLOCKED | Requires owner/reviewer action; prior application release blockers remain open. |

## Dependency finding

An earlier `npm audit --json` reported moderate findings in `postcss-selector-parser`, `postcss-nested` and `tailwindcss`, reflecting one transitive selector-parser advisory: [GHSA-rj75-hqrm-r3gf](https://github.com/advisories/GHSA-rj75-hqrm-r3gf). The final `npm audit --include=dev --json` returned zero findings, but the lockfile was not changed and still includes selector-parser 6.1.5. The difference in registry responses is not evidence of remediation. Preserve this historical finding for security review rather than claiming it was fixed.

This website emits static assets. Tailwind/PostCSS run during builds; the site does not accept CSS uploads or run these parsers for visitors. That limits runtime exposure, but does not clear build pipelines processing untrusted changes. The audit suggests Tailwind 4.3.3, a major migration. No forced update, override, suppression or accepted-risk sign-off was applied. Owner/security reviewer should approve a scoped migration or a documented, time-bounded build-tool risk decision. Review untrusted contributions before running builds with secrets.

## Current local build

- HTML: 3.91 kB, gzip 1.42 kB.
- JS: 258.38 kB, gzip 81.34 kB.
- CSS: 59.44 kB, gzip 13.29 kB.
- Six original screenshot assets: 1,216,010 bytes total; five in the gallery and one in the feature previews. Lazy loaded; no new dependencies.

SHA-256, local generated artifacts:

| Artifact | SHA-256 |
| --- | --- |
| dist/index.html | 23879355AA579744953CAE9C677134FAD0A00790096CF841F663907839A4BAF5 |
| dist/assets/index-BhrJXvEp.js | 92168D7635F28366D93CA156B7A36AAC3BF3FC0BE51101F974DB7C63B47FBDC1 |
| dist/assets/index-CACezGg1.css | 4DF60892C7D3AA0A57B2694065B45E6CF80698BFD35997B0B9F55B5509DE415E |

Local evidence: `%TEMP%/rf-website-audit-20261026.json`, `%TEMP%/rf-website-a11y-interactions-20261026.json`, `%TEMP%/rf-pinned-desktop-final.png` and `%TEMP%/rf-pinned-mobile-verified.png`. These temporary files are not committed release evidence and should be copied to the owner's review archive if needed. Checks used the named `agent-browser --session redforge-launch-check` session against the production preview. The latest fragment check found no missing targets or duplicate IDs.

## Owner's next actions

1. Review the local landing page, including screenshots and copy. Resolve the build-tool audit decision and manually review text contrast over gradients/mesh.
2. Authorize committing this website change when satisfied. Run hosted CI on that exact commit. Deployment requires separate authorization.
3. Test a hosted preview in Safari/Firefox and a physical phone. Check actual HTTPS, canonical redirect to the chosen www host, caching, headers, external fonts/GitHub failure behavior and page performance before public deployment.
4. Confirm support/contact ownership and legal/privacy disclosures. The website loads Google Fonts and GitHub release metadata; it must not be advertised as making zero network requests.
5. Keep desktop 2.1.0 internal until its separate clean-machine/network/upgrade/restore, signing, target-platform, CI and legal/security gates pass. Those gates were not rerun in this website task. No normal RedForge database was opened as part of these checks.

## Cursor and scrollbar follow-up (27 October 2026)

The illuminated pointer now stays active over page text, controls, disabled controls and screenshot dialogs. A manual popover keeps this decorative, pointer-transparent element above modal backdrops. Text selection and copying retain their native behavior. Updates are coalesced into one animation frame with no idle loop or new dependency. Touch, forced-color mode and browsers without the Popover API retain the native pointer. Browser chrome and OS-owned menus remain outside the website's control.

The scrollbar track now uses the page base color, #f2efe8, with a red thumb. Native arrows remain browser-controlled. Scrolling and dragging use the browser's own behavior.

Production-preview checks passed for text hover, the cursor above screenshot dialogs and Escape dismissal. A real mouse drag selected gallery description text while the custom cursor stayed visible; Ctrl+C emitted an unprevented copy event with that selection. No clipboard contents were read. Build and diff checks passed. Modal evidence: %TEMP%/rf-cursor-modal.png. Physical touch and cross-browser testing remain pending. The earlier accessibility scan predates this pointer follow-up.

## Zoomed desktop gallery follow-up (27 October 2026)

The sticky gallery remains active down to a 520 px desktop CSS viewport height. Its compact layout fits the smaller scene; below that height it uses native horizontal scrolling. Production preview checked at 960 x 600, 800 x 520 and 640 x 520: vertical scrolling advanced screenshots, reached the last screen and then released to the next section. Browser errors were empty. This checks viewport behavior, not every browser's native zoom implementation.


The expanded desktop navigation was reduced to 1040 x 72 px on 27 October 2026. Hover expansion was checked at 1440 px and 900 px viewport widths; links and Download fit without overlap or document overflow. Production build passed and browser errors were empty.

