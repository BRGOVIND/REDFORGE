import { Fragment, type ReactNode } from 'react';

/**
 * Minimal, dependency-free, XSS-safe Markdown renderer.
 *
 * Builds React nodes directly (never uses dangerouslySetInnerHTML), so untrusted
 * input can't inject HTML. Supports the subset the Assistant emits: headings,
 * bold, italic, inline code, fenced code blocks, unordered/ordered lists, links,
 * and paragraphs. Unsupported syntax degrades to plain text.
 */
export function Markdown({ children, className }: { children: string; className?: string }) {
  return <div className={className}>{renderBlocks(children)}</div>;
}

function renderBlocks(src: string): ReactNode[] {
  const lines = src.replace(/\r\n/g, '\n').split('\n');
  const out: ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Fenced code block
    if (line.trim().startsWith('```')) {
      const buf: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        buf.push(lines[i]);
        i++;
      }
      i++; // closing fence
      out.push(
        <pre key={key++} className="my-1.5 overflow-x-auto rounded-md border border-border bg-base p-2.5 font-mono text-[11px] text-content">
          <code>{buf.join('\n')}</code>
        </pre>
      );
      continue;
    }

    // Heading
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      const size = level <= 1 ? 'text-sm font-semibold' : 'text-[13px] font-semibold';
      out.push(
        <p key={key++} className={`${size} mb-1 mt-2 text-content first:mt-0`}>
          {renderInline(heading[2])}
        </p>
      );
      i++;
      continue;
    }

    // List (unordered or ordered) — consecutive item lines
    if (/^\s*([-*]|\d+\.)\s+/.test(line)) {
      const items: ReactNode[] = [];
      const ordered = /^\s*\d+\.\s+/.test(line);
      while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) {
        const text = lines[i].replace(/^\s*([-*]|\d+\.)\s+/, '');
        items.push(<li key={items.length}>{renderInline(text)}</li>);
        i++;
      }
      out.push(
        ordered ? (
          <ol key={key++} className="my-1 list-decimal space-y-0.5 pl-4">{items}</ol>
        ) : (
          <ul key={key++} className="my-1 list-disc space-y-0.5 pl-4">{items}</ul>
        )
      );
      continue;
    }

    // Blank line
    if (line.trim() === '') {
      i++;
      continue;
    }

    // Paragraph — gather until blank/heading/list/fence
    const para: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !/^(#{1,4})\s+/.test(lines[i]) &&
      !/^\s*([-*]|\d+\.)\s+/.test(lines[i]) &&
      !lines[i].trim().startsWith('```')
    ) {
      para.push(lines[i]);
      i++;
    }
    out.push(
      <p key={key++} className="my-1 leading-relaxed first:mt-0">
        {renderInline(para.join(' '))}
      </p>
    );
  }

  return out;
}

// Inline: **bold**, *italic*, `code`, [text](url). Order matters (code first).
function renderInline(text: string): ReactNode[] {
  const tokens: ReactNode[] = [];
  let rest = text;
  let key = 0;

  const patterns: { re: RegExp; render: (m: RegExpExecArray) => ReactNode }[] = [
    { re: /`([^`]+)`/, render: (m) => <code key={key++} className="rounded bg-overlay px-1 py-0.5 font-mono text-[11px]">{m[1]}</code> },
    { re: /\*\*([^*]+)\*\*/, render: (m) => <strong key={key++} className="font-semibold text-content">{m[1]}</strong> },
    { re: /(?<!\*)\*([^*]+)\*(?!\*)/, render: (m) => <em key={key++}>{m[1]}</em> },
    {
      re: /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/,
      render: (m) => (
        <a key={key++} href={m[2]} target="_blank" rel="noreferrer" className="text-red-400 underline hover:text-red-500">
          {m[1]}
        </a>
      ),
    },
  ];

  // Greedily consume the earliest match of any pattern.
  while (rest) {
    let best: { index: number; length: number; node: ReactNode } | null = null;
    for (const p of patterns) {
      const m = p.re.exec(rest);
      if (m && (best === null || m.index < best.index)) {
        best = { index: m.index, length: m[0].length, node: p.render(m) };
      }
    }
    if (best === null) {
      tokens.push(<Fragment key={key++}>{rest}</Fragment>);
      break;
    }
    if (best.index > 0) tokens.push(<Fragment key={key++}>{rest.slice(0, best.index)}</Fragment>);
    tokens.push(best.node);
    rest = rest.slice(best.index + best.length);
  }
  return tokens;
}
