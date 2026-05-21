// Tiny markdown-to-JSX renderer for legal pages (§22 — no
// dangerouslySetInnerHTML; everything goes through React's escaping).
//
// Supported subset (intentionally small — legal prose only):
//   - `#`, `##`, `###` headings
//   - blank-line-separated paragraphs
//   - `- ` and `* ` bullet lists
//   - `1.` ordered lists
//   - **bold**, *italic*, `code` spans
//   - [text](url) links (http(s)://, mailto:, # anchors only)
//
// No HTML, no tables, no images, no nested lists. If a feature is missing
// from this list, write the document without it.

import Link from "next/link";

type Block =
  | { kind: "h1" | "h2" | "h3" | "p"; text: string }
  | { kind: "ul"; items: string[] }
  | { kind: "ol"; items: string[] };

const SAFE_URL = /^(https?:|mailto:|#|\/)/;

function parseBlocks(source: string): Block[] {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];

  let paragraph: string[] = [];
  let ul: string[] | null = null;
  let ol: string[] | null = null;

  const flushParagraph = (): void => {
    if (paragraph.length === 0) return;
    blocks.push({ kind: "p", text: paragraph.join(" ").trim() });
    paragraph = [];
  };
  const flushUl = (): void => {
    if (ul && ul.length > 0) blocks.push({ kind: "ul", items: ul });
    ul = null;
  };
  const flushOl = (): void => {
    if (ol && ol.length > 0) blocks.push({ kind: "ol", items: ol });
    ol = null;
  };
  const flushAll = (): void => {
    flushParagraph();
    flushUl();
    flushOl();
  };

  for (const rawLine of lines) {
    const line = rawLine.replace(/\s+$/, "");

    if (line.trim() === "") {
      flushAll();
      continue;
    }

    const h3 = /^###\s+(.*)$/.exec(line);
    const h2 = !h3 ? /^##\s+(.*)$/.exec(line) : null;
    const h1 = !h3 && !h2 ? /^#\s+(.*)$/.exec(line) : null;
    if (h1 || h2 || h3) {
      flushAll();
      const match = h1 ?? h2 ?? h3;
      const kind = h1 ? "h1" : h2 ? "h2" : "h3";
      blocks.push({ kind, text: match![1] ?? "" });
      continue;
    }

    const ulMatch = /^[-*]\s+(.*)$/.exec(line);
    if (ulMatch) {
      flushParagraph();
      flushOl();
      ul = ul ?? [];
      ul.push(ulMatch[1] ?? "");
      continue;
    }

    const olMatch = /^\d+\.\s+(.*)$/.exec(line);
    if (olMatch) {
      flushParagraph();
      flushUl();
      ol = ol ?? [];
      ol.push(olMatch[1] ?? "");
      continue;
    }

    flushUl();
    flushOl();
    paragraph.push(line.trim());
  }
  flushAll();
  return blocks;
}

// ----- Inline rendering -----------------------------------------------------

interface InlineToken {
  kind: "text" | "strong" | "em" | "code" | "link";
  text: string;
  href?: string;
}

const INLINE_RE =
  /(\*\*[^*]+\*\*|\*[^*\n]+\*|`[^`\n]+`|\[[^\]]+\]\([^)\s]+\))/g;

function parseInline(text: string): InlineToken[] {
  const tokens: InlineToken[] = [];
  let lastIndex = 0;
  for (const match of text.matchAll(INLINE_RE)) {
    const start = match.index ?? 0;
    if (start > lastIndex) {
      tokens.push({ kind: "text", text: text.slice(lastIndex, start) });
    }
    const raw = match[0];
    if (raw.startsWith("**") && raw.endsWith("**")) {
      tokens.push({ kind: "strong", text: raw.slice(2, -2) });
    } else if (raw.startsWith("*") && raw.endsWith("*")) {
      tokens.push({ kind: "em", text: raw.slice(1, -1) });
    } else if (raw.startsWith("`") && raw.endsWith("`")) {
      tokens.push({ kind: "code", text: raw.slice(1, -1) });
    } else if (raw.startsWith("[")) {
      const link = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(raw);
      if (link) {
        const href = link[2] ?? "";
        if (SAFE_URL.test(href)) {
          tokens.push({ kind: "link", text: link[1] ?? "", href });
        } else {
          tokens.push({ kind: "text", text: link[1] ?? "" });
        }
      } else {
        tokens.push({ kind: "text", text: raw });
      }
    }
    lastIndex = start + raw.length;
  }
  if (lastIndex < text.length) {
    tokens.push({ kind: "text", text: text.slice(lastIndex) });
  }
  return tokens;
}

function renderInline(text: string): React.ReactNode[] {
  return parseInline(text).map((tok, i) => {
    switch (tok.kind) {
      case "strong":
        return <strong key={i}>{tok.text}</strong>;
      case "em":
        return <em key={i}>{tok.text}</em>;
      case "code":
        return (
          <code key={i} className="rounded bg-muted px-1 py-0.5 text-sm">
            {tok.text}
          </code>
        );
      case "link":
        if (tok.href && tok.href.startsWith("/")) {
          return (
            <Link key={i} href={tok.href} className="underline underline-offset-2">
              {tok.text}
            </Link>
          );
        }
        return (
          <a
            key={i}
            href={tok.href}
            className="underline underline-offset-2"
            rel="noreferrer noopener"
            target={tok.href?.startsWith("http") ? "_blank" : undefined}
          >
            {tok.text}
          </a>
        );
      default:
        return <span key={i}>{tok.text}</span>;
    }
  });
}

// ----- Public component -----------------------------------------------------

export function Markdown({ source }: { source: string }) {
  const blocks = parseBlocks(source);
  return (
    <div className="prose prose-neutral max-w-none text-sm leading-relaxed">
      {blocks.map((block, i) => {
        switch (block.kind) {
          case "h1":
            return (
              <h1 key={i} className="mt-8 text-2xl font-semibold tracking-tight">
                {renderInline(block.text)}
              </h1>
            );
          case "h2":
            return (
              <h2 key={i} className="mt-6 text-xl font-semibold tracking-tight">
                {renderInline(block.text)}
              </h2>
            );
          case "h3":
            return (
              <h3 key={i} className="mt-4 text-base font-semibold">
                {renderInline(block.text)}
              </h3>
            );
          case "p":
            return (
              <p key={i} className="mt-3 text-muted-foreground">
                {renderInline(block.text)}
              </p>
            );
          case "ul":
            return (
              <ul key={i} className="mt-3 list-disc space-y-1 pl-5 text-muted-foreground">
                {block.items.map((item, j) => (
                  <li key={j}>{renderInline(item)}</li>
                ))}
              </ul>
            );
          case "ol":
            return (
              <ol key={i} className="mt-3 list-decimal space-y-1 pl-5 text-muted-foreground">
                {block.items.map((item, j) => (
                  <li key={j}>{renderInline(item)}</li>
                ))}
              </ol>
            );
        }
      })}
    </div>
  );
}
