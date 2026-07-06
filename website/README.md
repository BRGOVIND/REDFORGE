# RedForge — Website

A separate, standalone marketing website for RedForge. **This project does not
touch `/frontend`** (the application). It is an editorial, cinematic, scroll-told
experience — a "classified AI security laboratory," not a dashboard or a
template.

```
npm run dev        # http://localhost:5174
npm run build      # production build → dist/
npm run typecheck
```

## Structure

```
src/
├── App.tsx                 # composes the entry + 11 scroll sections
├── index.css               # design tokens, blueprint grid, grain, gradients
├── components/
│   ├── Entry.tsx           # cinematic entry (black → forged line → wordmark → lift)
│   ├── Nav.tsx             # minimal nav + forge scroll-progress line
│   └── marks.tsx           # ForgeMark, Wordmark, SectionLabel
├── motion/                 # in-house motion toolkit (see note below)
│   ├── useInView.ts        # IntersectionObserver reveal
│   ├── useScrollProgress.ts# viewport-pass + pinned-section progress
│   ├── Reveal.tsx          # slow, confident entrance
│   └── Parallax.tsx
└── sections/               # one file per narrative section
    ├── Hero · Problem · Vision · Pipeline · AttackViz
    ├── Benchmark · BuiltFor · Local · Download · Future
```

## The story (scroll = narrative)

1. **Entry** — black screen, a forged red line draws itself, the wordmark rises, the curtain lifts.
2. **Hero** — *Break your model. Before attackers do.*
3. **The Problem** — the four ways LLMs fail, revealed on interaction.
4. **Why RedForge Exists** — local-first vision; no cloud, no keys, no subscriptions.
5. **How It Works** — a pinned, scroll-drawn pipeline: Model → Planner → Attack → Judge → Analysis → Report.
6. **Under Attack** — an animated scene: adversarial prompts travelling into the model core.
7. **Benchmark Engine** — 800 cases, adaptive attacks, autonomous evaluation, research mode.
8. **Built For** — researchers, students, security engineers, companies, contributors.
9. **Everything Local** — pinned statement: *Your model. Your machine. Your data.*
10. **Download** — GitHub, Documentation, Roadmap.
11. **The Horizon** — enterprise, fine-tuning, connectors, research platform + footer.

## Motion — a deliberate substitution

The brief specifies **GSAP + Framer Motion + Lenis**. This project was built in an
environment **with no network access**, so those packages could not be installed
from the registry. Rather than block, the motion is implemented **in-house** with
the same feel:

| Brief | Here | Where |
|-------|------|-------|
| Framer Motion `whileInView` | `Reveal` (IntersectionObserver + eased CSS transitions) | `motion/Reveal.tsx` |
| GSAP ScrollTrigger / pin | `usePinProgress` + `position: sticky` | `motion/useScrollProgress.ts`, `sections/Pipeline.tsx`, `sections/Local.tsx` |
| GSAP scroll-linked tweens | `useScrollProgress` + `Parallax` | `motion/*` |
| Lenis smooth scroll | native smooth scroll + eased reveals (no scroll hijack, so `sticky` pins stay correct) | `index.css` |

**To swap in the real libraries** once a registry is reachable:
`npm i gsap framer-motion lenis`, then replace the four primitives above — the
consuming sections don't need to change, only the toolkit internals.

The `node_modules` here is a junction to `/frontend/node_modules` (offline
toolchain reuse); with network, run a normal `npm install` in this folder to make
it fully independent.
