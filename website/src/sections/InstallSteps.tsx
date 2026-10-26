import { Reveal } from '../motion';

const STEPS = [
  { title: 'Get the desktop app.', text: 'Choose the installer for your platform from the published release.', note: 'Windows / macOS / Linux' },
  { title: 'Install and launch.', text: 'The backend comes bundled. No separate Python or Node.js setup.', note: 'One desktop workspace' },
  { title: 'Check your machine.', text: 'Review detected hardware and connect a supported local runtime.', note: 'CPU, GPU and runtime checks' },
  { title: 'Choose a local model.', text: 'Start with a model installed in Ollama, LM Studio, llama.cpp or vLLM.', note: 'Bring your installed models' },
  { title: 'Run a first evaluation.', text: 'Choose a small test, follow its progress and inspect the responses.', note: 'Start small. Learn the workflow.' },
  { title: 'Keep the findings.', text: 'Read the report, compare results and export the evidence you need.', note: 'JSON / Markdown / PDF' },
];

export function InstallSteps() {
  return <section id="install" className="install-guide">
    <div className="workspace-inner">
      <Reveal><div className="install-heading"><h2>From download<br />to first report<span>.</span></h2><p>Bring a local runtime and a model.<br />RedForge brings the workspace.</p></div></Reveal>
      <ol className="install-grid">{STEPS.map((step, index) => <Reveal as="li" key={step.title} delay={index * 55}>
        <span className="install-number">0{index + 1}</span><h3>{step.title}</h3><p>{step.text}</p><small>{step.note}</small>
      </Reveal>)}</ol>
    </div>
  </section>;
}
