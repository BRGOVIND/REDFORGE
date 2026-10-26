import { ArrowUpRight } from 'lucide-react';
import { Reveal } from '../motion';
import { REPO } from '../config/downloads';

const NEXT = [
  { title: 'Follow a call from end to end.', text: 'Local trace exploration and SDK capture, with separate controls for inputs, outputs, metadata and errors.' },
  { title: 'Give every prompt a history.', text: 'Draft, publish and compare immutable prompt versions. Select an older version without erasing the record.' },
  { title: 'Turn failures into better tests.', text: 'Local anomaly alerts and reviewed, sanitized regression cases derived from selected traces.' },
  { title: 'Make decisions with evidence.', text: 'Model comparisons, estimated cost budgets and reviewed security gates. Gate decisions do not deploy anything.' },
];

export function Future() {
  return (
    <section id="future" className="next-release">
      <div className="workspace-inner">
        <Reveal><div className="next-release-heading"><div><h2>More context.<br /><span>Better decisions.</span></h2></div><p className="release-status"><span>In testing</span>2.1.0 is an internal test candidate.<br />Public release validation is still in progress.</p></div></Reveal>
        <div className="next-release-grid">{NEXT.map((item, index) => <Reveal key={item.title} delay={index * 70}><article><span className="release-number">0{index + 1}</span><h3>{item.title}</h3><p>{item.text}</p></article></Reveal>)}</div>
        <div className="next-release-footer"><p>Capture is conservative by default. Review privacy settings before enabling prompt or response bodies.</p><a className="focus-ring" href={`${REPO}/blob/main/docs/release-readiness-audit.md`} target="_blank" rel="noopener noreferrer">Follow development <ArrowUpRight size={16} aria-hidden="true" /></a></div>
      </div>
    </section>
  );
}
