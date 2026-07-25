import { Reveal } from '../motion';

const LOCAL = ['Ollama', 'LM Studio', 'llama.cpp', 'GGUF', 'Hugging Face', 'vLLM'];
const CLOUD = ['OpenAI', 'Anthropic', 'Gemini', 'Groq', 'OpenRouter'];

/** Supported technologies — RedForge as the orchestration layer connecting them all. */
export function Stack() {
  return (
    <section id="stack" className="relative border-t border-steel-800 py-24 sm:py-32">
      <div className="mx-auto max-w-editorial px-6 sm:px-10">
        <Reveal>
          <p className="label mb-5">Supported technologies</p>
          <h2 className="display max-w-2xl text-4xl leading-[1.05] text-bone sm:text-5xl">
            The orchestration layer for local &amp; hosted AI.
          </h2>
          <p className="mt-6 max-w-2xl text-[15px] leading-relaxed text-steel-300">
            RedForge connects the runtimes and providers you already use — with local, offline-first
            execution at its core and hosted providers available when you want them.
          </p>
        </Reveal>

        <div className="mt-12 grid grid-cols-1 gap-10 lg:grid-cols-2">
          <Reveal>
            <p className="label mb-4 text-forge">Local runtimes</p>
            <div className="flex flex-wrap gap-2.5">
              {LOCAL.map((t) => (
                <span key={t} className="rounded-lg border border-steel-700 bg-char/50 px-3.5 py-2 text-[13px] text-bone">
                  {t}
                </span>
              ))}
            </div>
          </Reveal>
          <Reveal delay={120}>
            <p className="label mb-4">Hosted providers</p>
            <div className="flex flex-wrap gap-2.5">
              {CLOUD.map((t) => (
                <span key={t} className="rounded-lg border border-steel-800 bg-ink px-3.5 py-2 text-[13px] text-steel-200">
                  {t}
                </span>
              ))}
              <span className="rounded-lg border border-dashed border-steel-700 px-3.5 py-2 text-[13px] text-steel-400">
                + future providers
              </span>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
