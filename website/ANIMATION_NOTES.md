# RedForge animation implementation

## Scope

All changes are in `website/`. No dependencies were added. No commits or deployment were made.

## Intro

The intro animates the navbar's real `Wordmark`, preserving the same DOM element throughout. Its existing SVG angles flatten into a red horizontal line, contract, then unfold while the ember resolves into the flame. The wordmark reveals beside the mark. The complete logo travels into its measured navbar slot.

The sequence lasts 2,420 ms. Logo construction occupies approximately the first 1,320 ms; the wordmark appears between 1,040 and 1,480 ms; docking occupies approximately the final 750 ms. Completion reveals the navigation and hero and starts the mesh. Hero text uses brief staggered opacity and transform transitions without animated blur.

The destination is measured from the rendered navbar. Resizing or a font-driven logo width change rebases the flight from its current position. Skip, Escape, Tab, scrolling, and interacting with a link or button finish the intro immediately. Deep links and restored scroll positions bypass it. The intro does not lock scrolling or remove the scrollbar.

## Forge Mesh

`ForgeMesh.tsx` mounts a decorative Canvas 2D element. `motion/forgeMesh.ts` owns its mutable state and lifecycle, independently of React rendering.

- Desktop uses 50–72 nodes; narrow or coarse-pointer layouts use 24–32.
- Nodes have seeded, asymmetric placement, slow ambient drift, damped spring displacement, and localized red highlights.
- A pointer press sends one temporary scan through nearby nodes. It replaces the previous scan instead of accumulating particles.
- Only a few nodes have labels: model, runtime, and guard.
- Text, button rows, and the scroll hint have quiet zones that suppress mesh contrast. Labels turn inward near the right edge.
- The existing blueprint grid stays in CSS. The obsolete silhouette component was removed and remains recoverable from Git.

## Performance

- One requestAnimationFrame loop; pointer handlers only update mutable coordinates.
- Drawing targets 60 Hz, with deadline-based pacing for high-refresh displays. Idle mobile drawing targets 30 Hz.
- DPR is capped at 1.5 on desktop and 1.25 on mobile/coarse-pointer layouts.
- A cached glow sprite replaces per-frame gradient creation.
- Reused typed-array spatial buckets restrict connection searches to nearby cells, with at most three links per node.
- The frame loop performs no DOM measurements. Geometry is measured on layout changes, font readiness, and completion of the hero's transform transitions.
- IntersectionObserver and document visibility stop the loop when the hero is offscreen or the tab is hidden. Cleanup cancels frames, timers, observers, and listeners.

## Accessibility

Reduced motion bypasses the intro and renders a static mesh. Changes to that preference are handled live. The canvas is hidden from assistive technology and never receives pointer events. Text remains HTML; existing links remain functional. Keyboard input finishes the intro, and the navbar retains its visible focus ring.

## Files

- `src/App.tsx`: stable completion callback and shared logo ref.
- `src/components/Entry.tsx`: forging, docking, interruption, and cleanup.
- `src/components/Nav.tsx`: persistent logo slot and navigation reveal.
- `src/components/marks.tsx`: animation hooks on the existing SVG and wordmark.
- `src/sections/Hero.tsx`: mesh integration, quiet zones, faster reveal, and responsive spacing.
- `src/sections/ForgeMesh.tsx`: canvas mount and lifecycle bridge.
- `src/motion/forgeMesh.ts`: simulation, rendering, and visibility handling.
- `src/index.css`: intro layering, compositing, reduced motion, and short-screen spacing.
- `src/sections/HeroSilhouette.tsx`: removed.
- `qa/animation.html` and `qa/animation.js`: development-only browser checks.
- `ANIMATION_NOTES.md`: this implementation and review guide.

## Verification and reproduction

From `website/`:

```sh
npm run typecheck
npm run build
node --check qa/animation.js
npm run dev -- --host 127.0.0.1
```

TypeScript and the production build pass. The package defines no lint or automated test script. `git diff --check` passes.

Open `http://127.0.0.1:5174/qa/animation.html` and click **Run animation checks**. The harness loads the actual app in an iframe and checks:

1. 1920×1080 desktop.
2. 1366×768 laptop.
3. 390×844 coarse-pointer layout.
4. 390×844 reduced-motion layout.
5. Resizing from laptop to mobile during the intro.
6. Skipping the intro.

Checks cover logo identity and docking, horizontal overflow, DPR, decorative canvas behavior, real pointer-induced spring displacement, offscreen pause/resume, live motion preferences, and visibility pause/resume. Media preferences and the hidden-tab event path are simulated inside the test iframe. Real keyboard navigation was also checked in the browser: Tab finishes the intro and focuses RedForge home.

All six cases passed in the final run. The 1920×1080 case used 72 nodes and reached 60 draws per second, with 0.2 ms median and 0.4 ms 95th-percentile JavaScript frame work. The 1366×768 case used 50 nodes and reached 60 draws per second, with 0.6 ms median and 1.3 ms 95th-percentile work. Mobile used 24 nodes and reached 30 idle draws per second. Reduced motion recorded zero animation-frame draws.

These numbers measure drawing submissions, not GPU presentation or a guarantee for every device. The QA instrumentation itself adds overhead, and timings vary with system load.

## Review before publishing

Inspect the transition and hover intensity in your regular browser, and test a physical phone. Native OS reduced-motion preferences, Safari, and CPU-throttled GPU presentation were not independently profiled. The deterministic browser checks complement those visual checks. The QA files are outside the production build entry and are not included in `dist/`.
