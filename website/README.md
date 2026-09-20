# RedForge Website

Standalone marketing site in `website/`. The desktop application lives in
`frontend/` and is not part of this site.

The page uses warm paper, charcoal, and RedForge red. A brief black logo intro
leads into a product-focused hero, interactive workspace preview, grouped
capabilities, workflow, security sections, local runtime story, downloads, and
the roadmap. Linked legal pages use the same light palette.

```text
npm run dev        # http://localhost:5174
npm run build      # TypeScript check and production bundle in dist/
npm run typecheck
```

## Structure

- `src/App.tsx` composes the landing page.
- `src/index.css` contains the light theme, section fades, and responsive styles.
- `src/components/Entry.tsx` animates the logo into the navigation bar.
- `src/sections/WorkbenchPreview.tsx` provides the three interactive previews.
- `src/sections/Pipeline.tsx` runs the scroll-linked workflow.
- `src/motion/` contains small, local reveal and scroll utilities.
- `public/` contains icons, legal pages, sitemap, and the social preview image.
- `og-card-source.html` is the source layout for the 1200 x 630 social image.

## Downloads

`src/config/downloads.ts` checks the latest GitHub release for installer assets.
If that request fails, it uses the last verified published release. Keep
`PUBLISHED_FALLBACK_VERSION` current when publishing a new installer release.
The repository `VERSION` can be newer than the published installers.

## Motion

The site uses CSS transitions, IntersectionObserver, and a small scroll progress
hook. Continuous SVG motion pauses when offscreen or when reduced motion is
requested. No animation package is needed to build the site.
