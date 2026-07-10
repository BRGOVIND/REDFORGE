import { Reveal } from '../motion';
import { SectionLabel } from '../components/marks';

const NODES = [
  { id: 'pi', x: 90, y: 78, label: 'Prompt Injection', delay: '0s' },
  { id: 'jb', x: 510, y: 78, label: 'Jailbreak', delay: '0.55s' },
  { id: 'hl', x: 90, y: 322, label: 'Hallucination', delay: '1.1s' },
  { id: 'dl', x: 510, y: 322, label: 'Data Leakage', delay: '1.65s' },
];
const CX = 300;
const CY = 200;

function pathFor(x: number, y: number): string {
  // gentle curve from the node toward the core
  const mx = (x + CX) / 2 + (x < CX ? 30 : -30);
  const my = (y + CY) / 2 + (y < CY ? 30 : -30);
  return `M ${x} ${y} Q ${mx} ${my} ${CX} ${CY}`;
}

export function AttackViz() {
  return (
    <section className="relative border-t border-steel-800 py-24 sm:py-32 lg:py-40">
      <div className="mx-auto max-w-editorial px-6 sm:px-10">
        <Reveal>
          <SectionLabel>Under Attack</SectionLabel>
        </Reveal>
        <div className="mt-8 grid grid-cols-1 items-center gap-12 lg:grid-cols-12 lg:gap-16">
          <div className="lg:col-span-4">
            <Reveal delay={120}>
              <h2 className="display text-5xl text-bone sm:text-6xl">
                Watch it<br />
                <span className="text-ember-gradient">get hit.</span>
              </h2>
            </Reveal>
            <Reveal delay={240}>
              <p className="mt-6 max-w-sm text-[15px] leading-relaxed text-steel-300">
                Every category fires waves of adversarial prompts at the core. When one lands, the
                model lights up — and RedForge records exactly what broke and why.
              </p>
            </Reveal>
          </div>

          <div className="lg:col-span-8">
            <Reveal delay={200}>
              <svg viewBox="-72 0 744 400" className="w-full overflow-visible" role="img" aria-label="Attacks travelling into a model core">
                <defs>
                  <radialGradient id="core" cx="50%" cy="50%">
                    <stop offset="0%" stopColor="#FFD9A0" />
                    <stop offset="45%" stopColor="#FF7A45" />
                    <stop offset="100%" stopColor="#B0242A" />
                  </radialGradient>
                </defs>

                {/* connectors + travelling attacks */}
                {NODES.map((n) => {
                  const d = pathFor(n.x, n.y);
                  return (
                    <g key={n.id}>
                      <path d={d} fill="none" stroke="#2A2A31" strokeWidth="1" />
                      <circle r="3.5" fill="#FF7A45">
                        <animateMotion dur="2.4s" begin={n.delay} repeatCount="indefinite" path={d} />
                        <animate attributeName="opacity" values="0;1;1;0" dur="2.4s" begin={n.delay} repeatCount="indefinite" />
                      </circle>
                    </g>
                  );
                })}

                {/* category nodes */}
                {NODES.map((n) => (
                  <g key={`node-${n.id}`}>
                    <circle cx={n.x} cy={n.y} r="7" fill="#0B0B0D" stroke="#3A3A42" strokeWidth="1.5" />
                    <circle cx={n.x} cy={n.y} r="2.5" fill="#E5484D" />
                    <text
                      x={n.x < CX ? n.x - 14 : n.x + 14}
                      y={n.y + 4}
                      textAnchor={n.x < CX ? 'end' : 'start'}
                      className="fill-steel-300"
                      style={{ font: "500 12px 'JetBrains Mono', monospace" }}
                    >
                      {n.label}
                    </text>
                    {/* vuln bar lighting up */}
                    <rect x={n.x < CX ? n.x - 14 - 60 : n.x + 14} y={n.y + 12} width="0" height="3" rx="1.5" fill="#E5484D" opacity="0.7">
                      <animate attributeName="width" values="0;60;60;0" dur="4.8s" begin={n.delay} repeatCount="indefinite" />
                    </rect>
                  </g>
                ))}

                {/* core */}
                <circle cx={CX} cy={CY} r="34" fill="url(#core)" opacity="0.9" />
                <circle cx={CX} cy={CY} r="34" fill="none" stroke="#FF7A45" strokeWidth="1.5" opacity="0.5">
                  <animate attributeName="r" values="34;52;34" dur="2.4s" repeatCount="indefinite" />
                  <animate attributeName="opacity" values="0.5;0;0.5" dur="2.4s" repeatCount="indefinite" />
                </circle>
                <text x={CX} y={CY + 4} textAnchor="middle" className="fill-black" style={{ font: "600 12px 'Space Grotesk', sans-serif" }}>
                  MODEL
                </text>
              </svg>
            </Reveal>
          </div>
        </div>
      </div>
    </section>
  );
}
