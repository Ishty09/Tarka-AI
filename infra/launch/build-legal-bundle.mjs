#!/usr/bin/env node
/**
 * Concatenate all six legal-document English drafts into a single
 * `legal-bundle.md` for lawyer review.
 *
 * Usage:
 *   node infra/launch/build-legal-bundle.mjs > legal-bundle.md
 *
 * Reads each module under apps/web/lib/legal/content/, extracts the
 * `en.markdown` payload, prefixes each section with a heading + the
 * §16 placeholder notes from the privacy module's leading comment so
 * the lawyer knows which fields are intentional placeholders pending
 * incorporation.
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(HERE, "..", "..");

const DOCS = [
  { slug: "privacy", title: "Privacy Policy" },
  { slug: "terms", title: "Terms of Service" },
  { slug: "ai-disclosure", title: "AI Disclosure (EU AI Act Article 50)" },
  { slug: "acceptable-use", title: "Acceptable Use Policy" },
  { slug: "cookies", title: "Cookie Policy" },
  { slug: "dpa", title: "Data Processing Agreement" },
];

function extractMarkdown(slug) {
  const path = resolve(REPO_ROOT, "apps/web/lib/legal/content", `${slug}.ts`);
  const src = readFileSync(path, "utf-8");
  // The TS modules wrap the markdown in `const en = \`...\`;`. Pull the
  // template-literal body. We escape backticks inside via \` so the
  // unescape is straightforward.
  const m = src.match(/const en = `([\s\S]*?)`;\s*\n\s*export const/);
  if (!m) {
    throw new Error(`could not extract markdown from ${slug}.ts`);
  }
  return m[1].replace(/\\`/g, "`");
}

const now = new Date().toISOString().slice(0, 10);

const out = [];
out.push(`# Quarrel AI — Legal review bundle`);
out.push("");
out.push(`Generated: ${now}`);
out.push("");
out.push(
  `Six documents in publication order. Each is the English source; non-English locales fall back to English with a "translation pending" banner until lawyer-grade translations land. Placeholder fields (Bangladesh street address, EU representative, DPO name) are intentional and will be filled in at incorporation.`,
);
out.push("");
out.push("---");
out.push("");

for (const doc of DOCS) {
  out.push(`# ${doc.title}`);
  out.push("");
  out.push(extractMarkdown(doc.slug));
  out.push("");
  out.push("---");
  out.push("");
}

process.stdout.write(out.join("\n"));
