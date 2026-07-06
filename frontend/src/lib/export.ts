import type { SecurityReport } from '../api/types';

export function downloadBlob(filename: string, content: string, mime: string): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function reportToMarkdown(report: SecurityReport, model: string): string {
  const s = report.security_score;
  const lines: string[] = [];
  lines.push(`# RedForge Security Report — ${model}`, '');
  lines.push(`**Overall Security Score:** ${Math.round(s.overall)}/100 (${s.risk_band})`, '');
  lines.push('## Executive Summary', '', report.executive_summary, '');

  lines.push('## Category Scores', '');
  lines.push('| Category | Score | Risk | Failed |');
  lines.push('| --- | --- | --- | --- |');
  for (const c of s.categories) {
    lines.push(`| ${c.category} | ${Math.round(c.score)} | ${c.risk_level} | ${c.failed}/${c.total} |`);
  }
  lines.push('');

  if (report.findings.length) {
    lines.push('## Findings', '');
    for (const f of report.findings) {
      lines.push(`### ${f.title} — ${f.severity}`, '', f.reason, '');
      if (f.evidence.length) {
        lines.push('**Evidence:**');
        for (const e of f.evidence) lines.push(`- \`${e.attack_name}\` → ${e.verdict}`);
        lines.push('');
      }
      lines.push(`**Recommendation:** ${f.recommendation}`, '');
    }
  }

  if (report.recommendations.length) {
    lines.push('## Recommendations', '');
    for (const r of report.recommendations) lines.push(`- ${r}`);
    lines.push('');
  }

  return lines.join('\n');
}
