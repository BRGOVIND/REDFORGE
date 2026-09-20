import { useState } from 'react';
import { ForgeMark } from '../components/marks';

const VIEWS = [
  {
    name: 'Discover',
    title: 'Find a model that fits your machine.',
    description: 'Start in Model Hub, connect a runtime, and keep the model inside your workspace.',
    steps: ['Browse models', 'Connect Ollama or LM Studio', 'Save to a project'],
    footer: 'Model Hub',
  },
  {
    name: 'Evaluate',
    title: 'See what changed between runs.',
    description: 'Test prompts and benchmarks side by side, then keep the result with your project.',
    steps: ['Choose a benchmark', 'Compare model runs', 'Export a report'],
    footer: 'Evaluation workbench',
  },
  {
    name: 'Secure',
    title: 'Test before you trust the output.',
    description: 'Run local security checks and inspect the evidence behind each verdict.',
    steps: ['Choose an attack category', 'Run tests locally', 'Review findings'],
    footer: 'Security testing',
  },
] as const;

export function WorkbenchPreview() {
  const [active, setActive] = useState(0);
  const view = VIEWS[active];

  return (
    <div className="workbench-preview" aria-label="Interactive RedForge workflow preview">
      <div className="workbench-preview-topbar">
        <div className="flex items-center gap-2.5">
          <ForgeMark size={20} />
          <span className="font-semibold tracking-tight">RedForge</span>
          <span className="workbench-preview-divider" />
          <span className="text-stone-500">Workspace preview</span>
        </div>
        <span className="hidden text-xs text-stone-500 sm:inline">Runs on your machine</span>
      </div>

      <div className="workbench-preview-body">
        <div className="workbench-preview-nav" aria-label="Preview workflows">
          <p className="workbench-preview-nav-title">What you can do</p>
          {VIEWS.map((item, index) => (
            <button
              key={item.name}
              type="button"
              aria-pressed={active === index}
              onClick={() => setActive(index)}
              className="workbench-preview-tab focus-ring"
            >
              <span className="workbench-preview-tab-number">0{index + 1}</span>
              <span>{item.name}</span>
            </button>
          ))}
        </div>

        <div className="workbench-preview-panel" aria-live="polite">
          <div className="flex items-center justify-between gap-4 text-xs text-stone-500">
            <span>Workflow / 0{active + 1}</span>
            <span className="workbench-preview-local"><span /> Local-first</span>
          </div>
          <h2>{view.title}</h2>
          <p className="workbench-preview-description">{view.description}</p>
          <ol className="workbench-preview-steps">
            {view.steps.map((step, index) => (
              <li key={step}>
                <span>0{index + 1}</span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
          <div className="workbench-preview-foot">
            <span>Inside RedForge</span>
            <strong>{view.footer}</strong>
          </div>
        </div>
      </div>
    </div>
  );
}
