import {
  Server, Package, Boxes, Database, FlaskConical, Gauge, ShieldCheck, ScrollText,
  Dumbbell, Activity, HeartPulse, Layers, Brain, Plug, Command,
} from 'lucide-react';
import { Reveal } from '../motion';

/** The platform capabilities — RedForge as a complete Local AI Engineering Platform,
 *  with security repositioned as one capability among many. */
const CAPS: { k: string; d: string; icon: typeof Server; exp?: boolean }[] = [
  { k: 'Runtime Manager', icon: Server, d: 'Detect, connect, and monitor local runtimes — Ollama, LM Studio, llama.cpp, vLLM — from one place.' },
  { k: 'Model Hub', icon: Package, d: 'Browse and one-click download models from Hugging Face and Ollama. No terminal, no manual setup.' },
  { k: 'Projects & Workspaces', icon: Boxes, d: 'Organize models, datasets, runs, and reports into projects with full local lineage.' },
  { k: 'Datasets', icon: Database, d: 'Import, preprocess, version, and inspect datasets for training and evaluation — all on disk.' },
  { k: 'Prompt Workbench', icon: FlaskConical, d: 'Design, test, and regression-check prompts across models with side-by-side results.' },
  { k: 'Benchmark Center', icon: Gauge, d: 'Score and compare models across suites; track results over time with real metrics.' },
  { k: 'Evaluation Engine', icon: ScrollText, d: 'Deterministic, reproducible evaluation with heuristics or LLM-as-judge, and clear verdicts.' },
  { k: 'Security Testing', icon: ShieldCheck, d: 'Red-team any local model with a library of adversarial attacks — one capability, not the whole product.' },
  { k: 'Reports & Analytics', icon: Activity, d: 'Turn runs into structured reports: executive summaries, findings, evidence, and recommendations.' },
  { k: 'Training', icon: Dumbbell, exp: true, d: 'Fine-tune local models with LoRA / QLoRA. Actively evolving — clearly marked Experimental.' },
  { k: 'Global Task Manager', icon: Command, d: 'Every long-running job — downloads, benchmarks, training — with progress, ETA, logs, and background execution.' },
  { k: 'Health Engine', icon: HeartPulse, d: 'Continuous checks on Python, CUDA, runtimes, and GPU, with clear, actionable guidance.' },
  { k: 'Model Registry', icon: Layers, d: 'Register runnable checkpoints and adapters with versioned, local metadata.' },
  { k: 'Foundation Models', icon: Brain, d: 'Resolve runtime tags to real Hugging Face repositories, ready for training and export.' },
  { k: 'Plugin Architecture', icon: Plug, d: 'Extensible by design — add runtimes, attacks, evaluators, and workflows.' },
];

export function Capabilities() {
  return (
    <section id="capabilities" className="relative border-t border-steel-800 py-24 sm:py-32 lg:py-40">
      <div className="mx-auto max-w-editorial px-6 sm:px-10">
        <Reveal>
          <p className="label mb-5">The platform</p>
          <h2 className="display max-w-3xl text-4xl leading-[1.04] text-bone sm:text-5xl lg:text-6xl">
            One application for the entire <span className="text-ember-gradient">local AI</span> workflow.
          </h2>
          <p className="mt-6 max-w-2xl text-[15px] leading-relaxed text-steel-300">
            Discover models, manage runtimes, engineer prompts, benchmark, evaluate, secure, and
            fine-tune — think VS Code, Docker Desktop, MLflow, and LM Studio for local AI, in one
            cohesive, offline-first platform.
          </p>
        </Reveal>

        <div className="mt-14 grid grid-cols-1 gap-px overflow-hidden rounded-2xl border border-steel-800 bg-steel-800 sm:grid-cols-2 lg:grid-cols-3">
          {CAPS.map((c, i) => {
            const Icon = c.icon;
            return (
              <Reveal key={c.k} delay={(i % 3) * 80}>
                <div className="group relative h-full bg-ink p-6 transition-colors duration-300 hover:bg-char/60">
                  <div className="flex items-center gap-3">
                    <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-steel-700 bg-char text-steel-300 transition-colors duration-300 group-hover:border-forge group-hover:text-forge">
                      <Icon size={16} />
                    </span>
                    <h3 className="display text-lg text-bone">{c.k}</h3>
                    {c.exp && (
                      <span className="rounded bg-forge/15 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-forge">
                        Experimental
                      </span>
                    )}
                  </div>
                  <p className="mt-3 text-[13px] leading-relaxed text-steel-400">{c.d}</p>
                </div>
              </Reveal>
            );
          })}
        </div>
      </div>
    </section>
  );
}
