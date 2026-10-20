# RedForge animation implementation

## Scope

All changes are in `website/`. No dependencies were added. No commits or deployment were made.

## Intro

The intro animates the navbar's real `Wordmark`, preserving the same DOM element throughout. Its existing SVG angles flatten into a red horizontal line, contract, then unfold while the ember resolves into the flame. The wordmark reveals beside the mark. The complete logo travels into its measured navbar slot.

The sequence lasts 2,420 ms. Logo construction occupies approximately the first 1,320 ms; the wordmark appears between 1,040 and 1,480 ms; docking occupies approximately the final 750 ms. Completion reveals the navigation and hero and starts the mesh. Hero text uses brief staggered opacity and transform transitions without animated blur.

The destination is measured from the rendered navbar. Resizing or a font-driven logo width change rebases the flight from its current position. Skip, Escape, Tab, scrolling, and interacting with a link or button finish the intro immediately. Deep links and restored scroll positions bypass it. The intro does not lock scrolling or remove the scrollbar.

## Forge Mesh

`ForgeMesh.tsx` mounts a decorative Canvas 2D element. `motion/forgeMesh.ts` owns its mutable state and lifecycle, independently of React rendering.

- Desktop uses 72 to 96 nodes; narrow or coarse-pointer layouts use 28 to 38.
- Nodes have seeded, asymmetric placement, slow ambient drift, damped spring displacement, and localized red highlights.
- A pointer press sends one temporary scan through nearby nodes. It replaces the previous scan instead of accumulating particles.
- Nodes have different depth weights. Scrolling shifts their positions slightly, while pointer proximity lights connected signal hops.
- Text and the logo artifact have quiet zones that suppress mesh contrast. The mesh has no text labels.
- The existing blueprint grid stays in CSS. The obsolete silhouette component was removed and remains recoverable from Git.

## Performance

- One requestAnimationFrame loop; pointer handlers only update mutable coordinates.
- Interaction uses requestAnimationFrame. Idle drawing waits 38 ms on desktop and 70 ms on mobile between frame requests.
- DPR is capped at 1.25 on desktop and 1 on mobile/coarse-pointer layouts.
- A cached glow sprite replaces per-frame gradient creation.
- Nearest-anchor connections are computed only during layout measurement, with at most three links per node. There is no per-frame pair search.
- The frame loop performs no DOM measurements. Geometry is measured on layout changes, font readiness, and completion of the hero's transform transitions.
- IntersectionObserver and document visibility stop the loop when the hero is offscreen or the tab is hidden. Cleanup cancels frames, timers, observers, and listeners.

## Accessibility

Reduced motion bypasses the intro and renders a static mesh. Changes to that preference are handled live. The canvas is hidden from assistive technology and never receives pointer events. Text remains HTML; existing links remain functional. Keyboard input finishes the intro, and the navbar retains its visible focus ring.

## Scroll scenes and product examples

`useScrollScene` writes bounded CSS custom properties through a passive, animation-frame-throttled scroll listener. It does not update React state per frame. IntersectionObserver limits work to visible scenes; ResizeObserver refreshes geometry. All listeners and observers are disposed on unmount.

The hero logo has a small scroll-dependent lift and rotation. The workspace preview settles from a shallow perspective tilt into a flat, readable interface as it enters view. Pipeline connectors draw continuously between nodes while the existing stage hook changes the explanatory copy. These effects add no extra scroll distance. Reduced motion removes the new spatial transforms.

The three preview buttons show model details, a prompt comparison, and a security response with its verdict. All examples are explicitly labeled illustrative; they are not connected to the user's runtime or presented as measured results.

## October 17, 2026 verification

Production build and TypeScript pass. Browser checks covered 1440 by 1000 desktop and 390 by 844 mobile layouts, all three preview buttons, partial pipeline connector progress, reduced-motion transforms, mesh animation, and mouse dragging without text selection. No browser errors or horizontal overflow were observed in those checks.

A 1.5-second desktop sample observed 81 nodes, with 0.2 ms median and 0.4 ms 95th-percentile JavaScript drawing work. This measures canvas submission work on this machine, not GPU presentation or a performance guarantee for other devices.

## Files

- `src/App.tsx`: stable completion callback and shared logo ref.
- `src/components/Entry.tsx`: forging, docking, interruption, and cleanup.
- `src/components/Nav.tsx`: persistent logo slot and navigation reveal.
- `src/components/marks.tsx`: animation hooks on the existing SVG and wordmark.
- `src/sections/Hero.tsx`: mesh integration, quiet zones, faster reveal, and responsive spacing.
- `src/sections/ForgeMesh.tsx`: canvas mount and lifecycle bridge.
- `src/motion/forgeMesh.ts`: simulation, rendering, and visibility handling.
- `src/motion/useScrollScene.ts`: scroll progress without per-frame React rendering.
- `src/sections/WorkbenchPreview.tsx`: interactive, clearly labeled product examples.
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

The older six-case harness predates the current mesh renderer. Its exact-radius node instrumentation and event host assumptions need updating before its results can be used for this version. The targeted browser checks above are the checks performed for this change.

These numbers measure drawing submissions, not GPU presentation or a guarantee for every device. The QA instrumentation itself adds overhead, and timings vary with system load.

## Review before publishing

Inspect the transition and hover intensity in your regular browser, and test a physical phone. Native OS reduced-motion preferences, Safari, and CPU-throttled GPU presentation were not independently profiled. The deterministic browser checks complement those visual checks. The QA files are outside the production build entry and are not included in `dist/`.
