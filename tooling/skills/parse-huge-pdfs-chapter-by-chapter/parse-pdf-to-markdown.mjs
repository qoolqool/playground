#!/usr/bin/env node
// Parse a very large PDF into de-duplicated, chapter-split Markdown using
// LiteParse (the engine bundled with pi-docparser).
//
// Why this exists:
//   - pi-docparser's `document_parse` tool only exposes `text` and `json`
//     output, not Markdown.
//   - A single parse call cannot exceed 1000 pages (MAX_PAGES).
//   - Big documents are often heavily duplicated page-for-page (HTML-to-PDF
//     exports in particular), which would otherwise bloat the Markdown with
//     repeats.
//
// Usage:
//   node parse-pdf-to-markdown.mjs <pdf> <out-dir> [options]
//
// Options:
//   --label=NAME       Output label; defaults to a slug of the PDF file name.
//   --map=FILE         Chapter map file, one boundary per line: "PAGE|TITLE".
//                      If omitted, boundaries are auto-detected (approximate)
//                      and printed so you can save and refine them.
//   --dump-map=FILE    Write the effective chapter map to FILE (useful with
//                      auto-detection to capture it for later refinement).
//   --no-dedup         Keep duplicate pages (default is to drop them).
//   --keep-headers     Keep running headers/footers (default: stripped).
//
// Output (in <out-dir>):
//   00-<slug>.md, 01-<slug>.md, ...   one file per chapter
//   INDEX.md                          chapter / page / unique-page table
//   <label>.full.md                   all chapters concatenated
//
// Environment:
//   LITEPARSE_MODULE   Explicit path to @llamaindex/liteparse dist/lib.js
//                      (auto-resolved from the pi agent directory otherwise).

import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { basename, join } from 'node:path';
import { pathToFileURL } from 'node:url';

const CHUNK = 1000; // hard max pages per LiteParse call
const PAGE_COUNT_PROBE_LIMIT = 100_000;

// ---------------------------------------------------------------------------
// Resolve the LiteParse engine
// ---------------------------------------------------------------------------
async function loadLiteParse() {
  // pi installs extension packages under the agent directory's npm tree, which
  // is not on this script's module resolution path, so name it explicitly. The
  // agent directory follows PI_CODING_AGENT_DIR when set, ~/.pi/agent otherwise.
  const agentDir = process.env.PI_CODING_AGENT_DIR || join(homedir(), '.pi', 'agent');
  const candidates = [
    process.env.LITEPARSE_MODULE,
    '@llamaindex/liteparse',
    join(agentDir, 'npm', 'node_modules', '@llamaindex', 'liteparse', 'dist', 'lib.js'),
  ].filter(Boolean);
  for (const candidate of candidates) {
    try {
      // Bare specifiers go through normal resolution; filesystem paths need a
      // file URL to survive spaces and Windows drive letters.
      const isPath = candidate.startsWith('.') || candidate.startsWith('/') || /^[A-Za-z]:[\\/]/.test(candidate);
      const target = isPath ? pathToFileURL(candidate).href : candidate;
      const mod = await import(target);
      if (mod.LiteParse) return mod.LiteParse;
    } catch {
      /* try next */
    }
  }
  throw new Error(
    'Cannot load @llamaindex/liteparse. Install pi-docparser or set LITEPARSE_MODULE to its dist/lib.js path.',
  );
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------
function parseArgs(argv) {
  const positional = [];
  const flags = {};
  for (const arg of argv) {
    const m = /^--([^=]+)(?:=(.*))?$/.exec(arg);
    if (m) flags[m[1]] = m[2] === undefined ? true : m[2];
    else positional.push(arg);
  }
  return { positional, flags };
}

const { positional, flags } = parseArgs(process.argv.slice(2));
if (positional.length < 2) {
  console.error('Usage: node parse-pdf-to-markdown.mjs <pdf> <out-dir> [--map=FILE] [--label=NAME]');
  process.exit(2);
}
const [pdfPath, outDir] = positional;
const dedup = flags['no-dedup'] !== true;
const keepHeaders = flags['keep-headers'] === true;

const slugify = (s) =>
  String(s)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60);

const label = flags.label || slugify(basename(pdfPath).replace(/\.pdf$/i, '')) || 'document';
const sourceName = basename(pdfPath);

const LiteParse = await loadLiteParse();

// ---------------------------------------------------------------------------
// Page count (cheap: single-page probes + binary search)
// ---------------------------------------------------------------------------
async function hasPage(n) {
  try {
    const p = new LiteParse({
      outputFormat: 'text',
      ocrEnabled: false,
      targetPages: String(n),
      maxPages: 1,
      quiet: true,
    });
    const r = await p.parse(pdfPath);
    return r.pages.some((pg) => pg.pageNum === n);
  } catch {
    return false;
  }
}

async function detectPageCount() {
  let hi = 1;
  while (await hasPage(hi)) {
    hi *= 2;
    if (hi > PAGE_COUNT_PROBE_LIMIT) throw new Error('Page count probe exceeded limit.');
  }
  let lo = Math.floor(hi / 2);
  while (hi - lo > 1) {
    const mid = Math.floor((lo + hi) / 2);
    if (await hasPage(mid)) lo = mid;
    else hi = mid;
  }
  return lo;
}

// ---------------------------------------------------------------------------
// Parse (markdown, chunked) + de-duplicate
// ---------------------------------------------------------------------------
async function parseAll(total) {
  const pages = [];
  for (let start = 1; start <= total; start += CHUNK) {
    const end = Math.min(total, start + CHUNK - 1);
    const parser = new LiteParse({
      outputFormat: 'markdown',
      ocrEnabled: false,
      keepHeadersFooters: keepHeaders,
      targetPages: `${start}-${end}`,
      maxPages: CHUNK,
      quiet: true,
    });
    const result = await parser.parse(pdfPath);
    for (const pg of result.pages) pages.push(pg);
    console.error(`parsed pages ${start}-${end} (${result.pages.length})`);
  }
  pages.sort((a, b) => a.pageNum - b.pageNum);
  return pages;
}

function dedupe(pages) {
  const seen = new Set();
  const unique = [];
  for (const pg of pages) {
    const hash = createHash('sha1')
      .update((pg.text || '').replace(/\s+/g, ' ').trim())
      .digest('hex');
    if (seen.has(hash)) continue;
    seen.add(hash);
    unique.push(pg);
  }
  return unique;
}

// ---------------------------------------------------------------------------
// Chapter map handling
// ---------------------------------------------------------------------------
function readMapFile(file) {
  return readFileSync(file, 'utf8')
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
    .map((line) => {
      const [page, ...rest] = line.split('|');
      return { page: parseInt(page, 10), title: rest.join('|').trim() };
    });
}

const KEYWORD =
  /(Specification|Overview|Guide|Views|Framework|Catalogue|Constitution|Architecture|Management|Portal|Decision Record|Process Group|ServiceNow|Learning Management|Developer Portal|Functional|Technical)/i;

function withFrontMatter(points) {
  if (points.length === 0 || points[0].page !== 1) points.unshift({ page: 1, title: 'Front matter' });
  const out = [];
  for (const p of points) {
    if (out.length === 0 || out[out.length - 1].page !== p.page) out.push(p);
  }
  return out;
}

// Strategy 1 (preferred when the PDF carries real font sizes): a chapter starts on
// pages whose first text item uses the recurring, largest heading font size.
function detectMapFromFonts(uniquePages) {
  const candidates = [];
  for (const pg of uniquePages) {
    const items = (pg.textItems || [])
      .filter((i) => i.text.trim())
      .sort((a, b) => a.y - b.y);
    if (items.length === 0) continue;
    const first = items[0];
    const size = first.fontSize || 0;
    if (size >= 1.5) {
      candidates.push({
        page: pg.pageNum,
        size: Number(size.toFixed(1)),
        title: first.text.trim().slice(0, 90),
      });
    }
  }
  if (candidates.length < 3) return null;
  const freq = {};
  for (const c of candidates) freq[c.size] = (freq[c.size] || 0) + 1;
  const recurring = Object.keys(freq)
    .map(Number)
    .filter((s) => freq[s] >= 2);
  if (recurring.length === 0) return null;
  const chapterSize = Math.max(...recurring);
  const points = candidates
    .filter((c) => c.size === chapterSize)
    .map((c) => ({ page: c.page, title: c.title }));
  return points.length >= 3 ? points : null;
}

// Strategy 2 (fallback for HTML-to-PDF exports where every font size is 1): use the
// first level-1/2 Markdown heading on a page when it looks like a document/section title.
function detectMapFromMarkdown(uniquePages) {
  const points = [];
  for (const pg of uniquePages) {
    const heading = (pg.markdown || '')
      .split('\n')
      .map((l) => /^(#{1,2})\s+(.*)$/.exec(l))
      .find(Boolean);
    if (!heading) continue;
    const level = heading[1];
    const text = heading[2].trim();
    const isToc = text === 'Table of Contents';
    const isTitle =
      text.length >= 8 && text.length <= 95 && !text.endsWith(':') && KEYWORD.test(text);
    const isNumbered = level === '#' && /^\d+\.\s+\S/.test(text);
    if (isToc || isTitle || isNumbered) points.push({ page: pg.pageNum, title: text });
  }
  return points;
}

function detectMap(uniquePages) {
  const fontPoints = detectMapFromFonts(uniquePages);
  if (fontPoints) return withFrontMatter(fontPoints);
  return withFrontMatter(detectMapFromMarkdown(uniquePages));
}

function buildChapters(map, total) {
  return map.map((m, i) => ({
    start: m.page,
    end: i + 1 < map.length ? map[i + 1].page - 1 : total,
    order: String(i).padStart(2, '0'),
    slug: slugify(m.title) || `chapter-${i}`,
    title: m.title,
  }));
}

// ---------------------------------------------------------------------------
// Markdown normalisation: numbered heading "N.N.N Title" -> level = depth + 1
// ---------------------------------------------------------------------------
function normaliseHeadings(md) {
  return md
    .split('\n')
    .map((line) => {
      const m = /^(#{1,6})\s+(.*)$/.exec(line);
      if (!m) return line;
      const text = m[2].trim();
      const num = /^(\d+(?:\.\d+)*)\.?\s+(\S.*)$/.exec(text);
      if (!num) return line;
      const level = Math.min(6, num[1].split('.').length + 1);
      return `${'#'.repeat(level)} ${text}`;
    })
    .join('\n');
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
const total = await detectPageCount();
console.error(`page count: ${total}`);

const parsed = await parseAll(total);
const uniquePages = dedup ? dedupe(parsed) : parsed;
console.error(
  `pages=${parsed.length} unique=${uniquePages.length} duplicates=${parsed.length - uniquePages.length}`,
);

const map = flags.map ? readMapFile(flags.map) : detectMap(uniquePages);
console.error(`chapters: ${map.length}`);
if (!flags.map) {
  console.error('--- auto-detected chapter map (save with --dump-map=FILE and refine) ---');
  for (const m of map) console.error(`${m.page}|${m.title}`);
  console.error('---');
}
if (flags['dump-map']) {
  writeFileSync(flags['dump-map'], map.map((m) => `${m.page}|${m.title}`).join('\n') + '\n');
  console.error(`wrote map to ${flags['dump-map']}`);
}

const chapters = buildChapters(map, total);
mkdirSync(outDir, { recursive: true });

const used = new Set();
const index = [];
const parts = [];
for (const ch of chapters) {
  const selected = uniquePages.filter(
    (pg) => pg.pageNum >= ch.start && pg.pageNum <= ch.end && !used.has(pg.pageNum),
  );
  for (const pg of selected) used.add(pg.pageNum);
  if (selected.length === 0) {
    console.error(`skip ${ch.slug} (0 unique pages; content de-duplicated into an earlier chapter)`);
    continue;
  }
  const body = normaliseHeadings(
    selected
      .map((pg) => `<!-- source page ${pg.pageNum} -->\n${(pg.markdown || pg.text || '').trim()}`)
      .join('\n\n---\n\n'),
  );
  const header =
    `# ${ch.title}\n\n> Source: ${sourceName}  |  pages ${ch.start}-${ch.end} (original numbering)  |  ` +
    `${selected.length} unique pages\n\n`;
  const fname = `${ch.order}-${ch.slug}.md`;
  const doc = header + body + '\n';
  writeFileSync(join(outDir, fname), doc);
  index.push({ fname, title: ch.title, pages: `${ch.start}-${ch.end}`, unique: selected.length });
  parts.push(doc);
  console.error(`wrote ${fname} (${selected.length} unique pages)`);
}

const leftover = uniquePages.filter((pg) => !used.has(pg.pageNum));
if (leftover.length > 0) {
  const body = normaliseHeadings(
    leftover
      .map((pg) => `<!-- source page ${pg.pageNum} -->\n${(pg.markdown || pg.text || '').trim()}`)
      .join('\n\n---\n\n'),
  );
  writeFileSync(
    join(outDir, '99-uncategorised.md'),
    `# Uncategorised\n\n> ${leftover.length} unique pages not assigned to a chapter\n\n${body}\n`,
  );
  console.error(`wrote 99-uncategorised.md (${leftover.length} unique pages)`);
}

writeFileSync(
  join(outDir, 'INDEX.md'),
  `# ${label} — parsed markdown\n\nSource PDF: \`${sourceName}\` (${total} pages, ${uniquePages.length} unique after de-duplication)\n\n` +
    `| File | Chapter | Source pages | Unique pages |\n|---|---|---|---|\n` +
    index.map((i) => `| ${i.fname} | ${i.title} | ${i.pages} | ${i.unique} |`).join('\n') +
    '\n',
);
writeFileSync(
  join(outDir, `${label}.full.md`),
  `# ${label} — full parsed markdown\n\n> ${uniquePages.length} unique pages (de-duplicated from ${total}) from \`${sourceName}\`\n\n---\n\n` +
    parts.map((p) => p.replace(/^# /, '## ')).join('\n\n---\n\n') +
    '\n',
);
console.error(`wrote INDEX.md and ${label}.full.md`);
