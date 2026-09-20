import { ArrowDownRight, ArrowUpRight } from 'lucide-react';
import { ForgeMark } from '../components/marks';
import { WorkbenchPreview } from './WorkbenchPreview';
import { ForgeMesh } from './ForgeMesh';

export function Hero({ started }: { started: boolean }) {
  return (
    <section id="top" className="forge-hero">
      <div className="forge-hero-paper">
        <div className="forge-hero-content">
          <ForgeMesh active={started} />
          <div className="forge-hero-copy" data-mesh-quiet>
            <h1 className={started ? 'forge-hero-entered' : ''}>
              Build locally.
              <br />
              <span>Know what works.</span>
            </h1>
            <p className="forge-hero-intro">
              Find models, compare runs, test prompts, and check security in one desktop workspace.
              Use a local runtime to keep the work on your machine.
            </p>
            <div className="forge-hero-actions">
              <a href="#download" className="forge-hero-primary focus-ring">
                Download RedForge <ArrowUpRight size={17} aria-hidden="true" />
              </a>
              <a href="#capabilities" className="forge-hero-secondary focus-ring">
                Explore the workspace <ArrowDownRight size={17} aria-hidden="true" />
              </a>
            </div>
            <p className="forge-hero-meta">Open source <span aria-hidden="true">/</span> Windows, macOS, Linux</p>
          </div>

          <div className="forge-hero-artifact" aria-hidden="true" data-mesh-quiet>
            <div className="forge-hero-artifact-shadow" />
            <div className="forge-hero-artifact-back" />
            <div className="forge-hero-artifact-face">
              <ForgeMark size={90} />
            </div>
          </div>
        </div>

        <div className="forge-hero-preview-wrap">
          <WorkbenchPreview />
        </div>
      </div>
    </section>
  );
}
