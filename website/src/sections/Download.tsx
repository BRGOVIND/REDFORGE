import { ArrowUpRight, BookOpen, Github, Map } from 'lucide-react';
import { Reveal } from '../motion';
import { SectionLabel } from '../components/marks';

const LINKS = [
  { icon: Github, k: 'GitHub', v: 'Clone the source, star the repo, open a pull request.', href: 'https://github.com/BRGOVIND/REDFORGE' },
  { icon: BookOpen, k: 'Documentation', v: 'Architecture, the API, and the benchmark, in depth.', href: 'https://github.com/BRGOVIND/REDFORGE#readme' },
  { icon: Map, k: 'Roadmap', v: 'Where RedForge is going — and how to shape it.', href: 'https://github.com/BRGOVIND/REDFORGE' },
];

export function Download() {
  return (
    <section id="download" className="relative border-t border-steel-800 py-32 sm:py-44">
      <div className="mx-auto max-w-editorial px-6 sm:px-10">
        <div className="grid grid-cols-1 gap-16 lg:grid-cols-12">
          <div className="lg:col-span-5">
            <Reveal>
              <SectionLabel index="10">Download</SectionLabel>
            </Reveal>
            <Reveal delay={120}>
              <h2 className="display mt-8 text-6xl text-bone sm:text-7xl">
                Forge it<br />yourself.
              </h2>
            </Reveal>
            <Reveal delay={240}>
              <div className="mt-8 max-w-sm rounded-lg border border-steel-700 bg-char/60 p-4 font-mono text-[13px] leading-relaxed text-steel-300">
                <span className="text-steel-500">$ </span>git clone redforge
                <br />
                <span className="text-steel-500">$ </span>uvicorn app.main:app
                <br />
                <span className="text-forge">→ </span>open localhost:5173
              </div>
            </Reveal>
          </div>

          <div className="lg:col-span-7">
            {LINKS.map((l, i) => {
              const Icon = l.icon;
              return (
                <Reveal key={l.k} delay={i * 110}>
                  <a
                    href={l.href}
                    target="_blank"
                    rel="noreferrer"
                    className="focus-ring group flex items-center gap-6 border-t border-steel-800 py-8 transition-all duration-500 ease-forge last:border-b hover:pl-4"
                  >
                    <Icon size={22} className="shrink-0 text-steel-400 transition-colors group-hover:text-forge" />
                    <div className="flex-1">
                      <h3 className="display text-2xl text-bone sm:text-3xl">{l.k}</h3>
                      <p className="mt-1 text-[14px] text-steel-400">{l.v}</p>
                    </div>
                    <ArrowUpRight
                      size={22}
                      className="shrink-0 text-steel-500 transition-all duration-500 ease-forge group-hover:-translate-y-1 group-hover:translate-x-1 group-hover:text-forge"
                    />
                  </a>
                </Reveal>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
