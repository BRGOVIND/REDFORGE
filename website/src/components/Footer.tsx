import { Wordmark } from './marks';

const REPO = 'https://github.com/BRGOVIND/REDFORGE';
const BLOB = `${REPO}/blob/main`;

interface Link {
  label: string;
  href: string;
  external?: boolean;
}

interface Column {
  title: string;
  links: Link[];
}

const COLUMNS: Column[] = [
  {
    title: 'Product',
    links: [
      { label: 'Download', href: '#download' },
      { label: 'Documentation', href: `${REPO}#readme`, external: true },
      { label: 'GitHub', href: REPO, external: true },
      { label: 'Changelog', href: `${BLOB}/CHANGELOG.md`, external: true },
    ],
  },
  {
    title: 'Resources',
    links: [
      { label: 'Installation Guide', href: `${BLOB}/docs/installation.md`, external: true },
      { label: 'Getting Started', href: `${BLOB}/docs/quickstart.md`, external: true },
      { label: 'FAQ', href: `${BLOB}/docs/faq.md`, external: true },
    ],
  },
  {
    title: 'Legal',
    links: [
      { label: 'Privacy Policy', href: '/privacy.html' },
      { label: 'Terms of Service', href: '/terms.html' },
      { label: 'License', href: '/license.html' },
    ],
  },
  {
    title: 'Community',
    links: [
      { label: 'GitHub', href: REPO, external: true },
      { label: 'Issues', href: `${REPO}/issues`, external: true },
      { label: 'Discussions', href: `${REPO}/discussions`, external: true },
    ],
  },
  {
    title: 'Company',
    links: [
      { label: 'About', href: '#about' },
      { label: 'Contact', href: 'mailto:brgovind2005@gmail.com' },
    ],
  },
];

export function Footer() {
  return (
    <footer className="border-t border-steel-800 bg-char/40">
      <div className="mx-auto max-w-editorial px-6 py-16 sm:px-10">
        <div className="grid grid-cols-2 gap-x-8 gap-y-10 sm:grid-cols-3 lg:grid-cols-6">
          <div className="col-span-2">
            <Wordmark />
            <p className="mt-3 max-w-xs text-[13px] leading-relaxed text-steel-500">
              Break your model before attackers do. Local AI security, forged in the open.
            </p>
          </div>

          {COLUMNS.map((col) => (
            <nav key={col.title} aria-label={col.title}>
              <p className="label mb-4 text-steel-500">{col.title}</p>
              <ul className="space-y-2.5">
                {col.links.map((l) => (
                  <li key={l.label}>
                    <a
                      href={l.href}
                      {...(l.external ? { target: '_blank', rel: 'noreferrer' } : {})}
                      className="focus-ring rounded text-[13px] text-steel-300 transition-colors hover:text-bone"
                    >
                      {l.label}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>

        <div className="mt-14 flex flex-col items-start justify-between gap-3 border-t border-steel-800 pt-8 sm:flex-row sm:items-center">
          <span className="text-[13px] text-steel-500">© 2026 RedForge</span>
          <span className="label text-steel-600">Built for local AI security research</span>
        </div>
      </div>
    </footer>
  );
}
