# Landing refresh, 26 October 2026

Scope: marketing website only. The hero, entry animation, logo, red/cream palette, mesh and "Your model. Your machine. Your data." remain. No desktop application or database changes. This revision supersedes the previous three-tab walkthrough.

## Presentation

- Five real screenshots form a horizontal, center-snapping gallery: Evaluate, Observe, Compare, Report and Inspect. Captions explain evaluation setup, resource estimates, live progress, comparisons, report exports and findings.
- Vertical scrolling pins the screenshot section and drives the gallery sideways, then releases the section after the final screen. Reverse scrolling reverses the sequence. The centered screenshot resolves from pixels; the outgoing screenshot becomes pixelated. Arrow buttons and Left/Right/Home/End move to the corresponding document position. Reduced motion and desktop viewports shorter than 520 px and mobile viewports shorter than 700 px use a native horizontal gallery with swipe and arrow controls instead.
- Clicking a screenshot opens a native dialog with a blurred backdrop, zoom, scroll-to-pan, previous/next controls, Escape dismissal and focus return. Screenshots are previews, not functional app controls.
- Desktop feature previews appear as their rows enter view and respond to hover. Hover takes priority over scroll selection. Clicking opens the dialog; below 1024 px, inline screenshot buttons provide the same access.
- Desktop glass navigation starts as a 390 x 58 compass/ruler and expands on hover or button activation. The compass rotates and links fade into place. Enter opens the navigation and focuses its first link; Escape closes it and restores focus to the compass. Small screens retain the menu.
- The original logo entrance docks into a visible navbar logo slot. Clicking the home logo clears the page fragment, returns to the top and replays the entrance. Reduced-motion preferences still skip the flight.
- Workflow nodes are enlarged to 58 px on sufficiently tall desktop screens, with larger labels and icons. Stage visibility prevents overlapping titles during transitions.
- Removed the "Next chapter / 2.1" label, download version pill/red dot and repeated horizontal dividers. Subtle cream surfaces group content instead.
- Upcoming 2.1 content remains explicitly an internal test candidate. Download targets and release readiness are unchanged. The future CLI section remains after downloads and installation guidance.

## Screenshot provenance

Supplied PNGs are copied unchanged. Presentational crops are defined in `src/components/ProductScreen.tsx`; no scores or app content were fabricated. Screens show version 2.0.3 and are labelled accordingly. Example results are not universal model ratings. Architectural benchmark previews are identified.

| Public asset | Supplied file | Bytes |
| --- | --- | ---: |
| screens/benchmarks.png | Screenshot 2026-10-25 145628.png | 185992 |
| screens/live.png | Screenshot 2026-10-25 150012.png | 158586 |
| screens/report.png | Screenshot 2026-10-25 145855.png | 191264 |
| screens/models.png | Screenshot 2026-10-25 145509.png | 141732 |
| screens/evaluation.png | Screenshot 2026-10-25 145809.png | 200817 |
| screens/findings.png | Screenshot 2026-10-25 145901.png | 337619 |

Total: 1,216,010 bytes. Five assets appear in the gallery; models remains a feature preview. Images load lazily. CSS and canvas use the same crop.

## Motion and performance

No dependencies added. Gallery pixel transitions use quantized canvas resolutions over 560 ms. Feature-image reveal uses ten redraw steps over 760 ms. Animation frames cancel when offscreen, hidden or unmounted; there is no permanent screenshot animation loop. Scroll measurements and pointer updates are coalesced through requestAnimationFrame. Reduced-motion mode shows clear static screenshots and removes motion transitions while retaining navigation and preview access.

## Local validation

- `npm run build` in `website`: TypeScript and Vite production build passed.
- Output: JS 258.38 kB (81.34 kB gzip), CSS 59.44 kB (13.29 kB gzip), HTML 3.91 kB (1.42 kB gzip). PNGs are additional, separately requested assets.
- `git diff --check`: passed with repository line-ending conversion warnings only.
- Checked desktop 1440 x 1000 and mobile 390 x 844; additional width checks at 320 x 740 and 900 x 900 found no horizontal document overflow.
- Verified gallery centering, incoming/outgoing pixel states, endpoint button disabling, reduced-motion clear images, and keyboard Home/End navigation.
- Verified dialog opening, zoom/pan dimensions, blurred backdrop, Escape dismissal, body-scroll restoration and focus return. Fixed a StrictMode queued-close issue.
- Verified hover/keyboard expansion of desktop navigation, mobile menu opening and Escape dismissal.
- Verified scroll-activated clickable feature preview and larger workflow without overlapping stage titles.
- Browser error log was empty during interaction checks.
- Final production-preview accessibility scan in `agent-browser --session redforge-launch-check`: 44 rules passed, zero violations, one incomplete contrast rule covering 41 nodes. This automated scan is not a full accessibility certification; contrast over moving/gradient content still needs manual judgment.

See LAUNCH-READINESS.md for the production-build checks, dependency findings and owner actions. No commit, publication, deployment, release approval or cross-browser performance certification is included.


## Cursor and scrollbar follow-up (27 October 2026)

The illuminated pointer now stays active over page text, controls, disabled controls and screenshot dialogs. A manual popover keeps this decorative, pointer-transparent element above modal backdrops. Text selection and copying retain their native behavior. Updates are coalesced into one animation frame with no idle loop or new dependency. Touch, forced-color mode and browsers without the Popover API retain the native pointer. Browser chrome and OS-owned menus remain outside the website's control.

The scrollbar track now uses the page base color, #f2efe8, with a red thumb. Native arrows remain browser-controlled. Scrolling and dragging use the browser's own behavior.

Production-preview checks passed for text hover, the cursor above screenshot dialogs and Escape dismissal. A real mouse drag selected gallery description text while the custom cursor stayed visible; Ctrl+C emitted an unprevented copy event with that selection. No clipboard contents were read. Build and diff checks passed. Modal evidence: %TEMP%/rf-cursor-modal.png. Physical touch and cross-browser testing remain pending. The earlier accessibility scan predates this pointer follow-up.

## Zoomed desktop gallery follow-up (27 October 2026)

The sticky gallery remains active down to a 520 px desktop CSS viewport height. Its compact layout fits the smaller scene; below that height it uses native horizontal scrolling. Production preview checked at 960 x 600, 800 x 520 and 640 x 520: vertical scrolling advanced screenshots, reached the last screen and then released to the next section. Browser errors were empty. This checks viewport behavior, not every browser's native zoom implementation.


