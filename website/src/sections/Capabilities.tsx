import { useState } from 'react';
import { Reveal } from '../motion';

const CAPS = [
  { k: 'Runtime Manager', d: 'Detect, connect, and monitor Ollama, LM Studio, llama.cpp, and vLLM from one place.' },
  { k: 'Model Hub', d: 'Browse and download models from Hugging Face and Ollama without a terminal.' },
  { k: 'Projects & Workspaces', d: 'Keep models, datasets, runs, and reports together in local projects.' },
  { k: 'Datasets', d: 'Import, prepare, version, and inspect datasets on your own disk.' },
  { k: 'Prompt Workbench', d: 'Design, test, and compare prompts across models.' },
  { k: 'Benchmark Center', d: 'Run benchmark suites and compare models with recorded results.' },
  { k: 'Evaluation Engine', d: 'Use reproducible evaluations with clear verdicts.' },
  { k: 'Security Testing', d: 'Red-team local models with a library of adversarial attacks.' },
  { k: 'Reports & Analytics', d: 'Turn runs into reports with findings and evidence.' },
  { k: 'Training', d: 'Explore local fine-tuning with LoRA and QLoRA.', exp: true },
  { k: 'Global Task Manager', d: 'Track downloads, benchmarks, and training jobs with progress and logs.' },
  { k: 'Health Engine', d: 'Check Python, CUDA, runtimes, and GPU health.' },
  { k: 'Model Registry', d: 'Register checkpoints and adapters with versioned local metadata.' },
  { k: 'Foundation Models', d: 'Connect runtime tags to Hugging Face repositories for training and export.' },
  { k: 'Plugin Architecture', d: 'Add runtimes, attacks, evaluators, and workflows.' },
];

const GROUPS = [
  { title: 'Get started', note: 'Set up a local workspace', items: CAPS.slice(0, 5) },
  { title: 'Test and improve', note: 'See what works and why', items: CAPS.slice(5, 10) },
  { title: 'Run and extend', note: 'Keep the work moving', items: CAPS.slice(10) },
];

export function Capabilities() {
  const [active, setActive] = useState(0);

  return (
    <section id="capabilities" className="workbench-features">
      <div className="mx-auto max-w-editorial px-6 sm:px-10">
        <Reveal>
          <h2>One place for the whole job.</h2>
          <p className="workbench-features-intro">
            Start with a model. Build a workflow around it. Keep the evidence when you are done.
          </p>
        </Reveal>

        <div className="workbench-features-layout">
          <div className="workbench-features-groups" aria-label="Explore RedForge capabilities">
            {GROUPS.map((group, index) => (
              <button
                key={group.title}
                type="button"
                aria-pressed={active === index}
                onClick={() => setActive(index)}
                className="workbench-features-group focus-ring"
              >
                <span className="workbench-features-group-number">0{index + 1}</span>
                <span>
                  <strong>{group.title}</strong>
                  <small>{group.note}</small>
                </span>
              </button>
            ))}
          </div>
          <div className="workbench-features-detail" aria-live="polite">
            <p>{GROUPS[active].title} in RedForge</p>
            <ul>
              {GROUPS[active].items.map((item, index) => (
                <li key={item.k}>
                  <span className="workbench-features-item-number">0{index + 1}</span>
                  <div>
                    <h3>
                      {item.k}
                      {'exp' in item && item.exp && <span>Experimental</span>}
                    </h3>
                    <p>{item.d}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}
