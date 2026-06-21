#!/usr/bin/env node
/**
 * DEPRECATED: Use load-kb-to-memory.py instead (bge-large, 1024-dim).
 *
 * This .mjs version uses 384-dim (all-MiniLM-L6-v2) which is incompatible
 * with the 1024-dim bge-large embeddings used by Central KB and the
 * knowledgebase pipeline. Kept for reference only.
 *
 * Load all knowledgebase OKF markdown files into AgentDB with vector embeddings.
 * Supports both OKF (.md) and legacy (.yaml) formats.
 *
 * Uses @claude-flow/memory (marketplace build) + Xenova transformers (from npx cache).
 */
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const KB = '/project/knowledgebase';

// Inject the npx cache node_modules path so @xenova/transformers is resolvable
const NPX_MODULES = '/home/tool/.npm/_npx/85fb20e3e7e3a233/node_modules';
const MEMORY_MODULES = '/home/tool/.claude/plugins/marketplaces/ruflo/v3/node_modules';

// Load transformers from npx cache
const { pipeline } = await import(join(NPX_MODULES, '@xenova/transformers/src/transformers.js'));

// Load @claude-flow/memory from marketplace build
const memoryModule = await import(join(MEMORY_MODULES, '@claude-flow/memory/dist/index.js'));
const { UnifiedMemoryService } = memoryModule;

console.log('[1/4] Loading embedding model (Xenova/all-MiniLM-L6-v2)...');
const embedder = await pipeline('feature-extraction', 'Xenova/all-MiniLM-L6-v2');

const embeddingGenerator = async (text) => {
  const result = await embedder(text.slice(0, 512), { pooling: 'mean', normalize: true });
  return Array.from(result.data);
};

console.log('[2/4] Initializing memory service...');
const memory = new UnifiedMemoryService({
  dimensions: 384,
  embeddingGenerator,
  autoEmbed: true,
  cacheEnabled: true,
  persistenceEnabled: true,
  persistencePath: '/project/.swarm/memory.db',
});

await memory.initialize();
console.log('  Memory service ready');

const NAMESPACES = {
  decisions: 'decisions',
  patterns: 'patterns',
  sessions: 'sessions',
  metrics: 'metrics',
  tables: 'tables',
  concepts: 'concepts',
};

/**
 * Parse OKF markdown (YAML frontmatter + body).
 */
function parseOkfMarkdown(content) {
  const result = { frontmatter: {}, body: '' };

  // Match YAML frontmatter between --- markers
  const fmMatch = content.match(/^---\s*\n([\s\S]*?)\n---\s*\n?([\s\S]*)/);
  if (fmMatch) {
    const fmRaw = fmMatch[1];
    result.body = fmMatch[2].trim();

    // Simple YAML key: value extraction
    const lines = fmRaw.split('\n');
    let key = null;
    let value = [];
    let inBlock = false;

    for (const line of lines) {
      if (inBlock) {
        if (line.startsWith('  ') || line.trim() === '' || line.startsWith('    ') || line.match(/^\s{2}\w/)) {
          value.push(line.replace(/^  /, ''));
          continue;
        } else {
          result.frontmatter[key] = value.join('\n');
          value = [];
          inBlock = false;
        }
      }

      const m = line.match(/^(\w[\w]*):\s?(.*)/);
      if (m) {
        key = m[1];
        const val = m[2]?.trim();
        if (val === '>' || val === '|') {
          inBlock = true;
          value = [];
        } else if (val && val.startsWith('[') && val.endsWith(']')) {
          // Parse inline array: [tag1, tag2]
          result.frontmatter[key] = val.slice(1, -1).split(',').map(t => t.trim().replace(/^['"]|['"]$/g, ''));
        } else if (val) {
          result.frontmatter[key] = val;
        } else {
          result.frontmatter[key] = '';
        }
      }
    }
    if (inBlock && key) result.frontmatter[key] = value.join('\n');
  } else {
    // No frontmatter — treat entire content as body
    result.body = content.trim();
  }

  return result;
}

/**
 * Parse legacy YAML knowledgebase entry.
 */
function parseYamlFrontmatter(content) {
  const lines = content.split('\n');
  const result = {};
  let key = null;
  let value = [];
  let inBlock = false;

  for (const line of lines) {
    if (inBlock) {
      if (line.startsWith('  ') || line.trim() === '' || line.startsWith('    ') || line.match(/^\s{2}\w/)) {
        value.push(line.replace(/^  /, ''));
        continue;
      } else {
        result[key] = value.join('\n');
        value = [];
        inBlock = false;
      }
    }

    const m = line.match(/^(\w[\w]*):\s?(.*)/);
    if (m) {
      key = m[1];
      const val = m[2]?.trim();
      if (val === '>' || val === '|') {
        inBlock = true;
        value = [];
      } else if (val) {
        result[key] = val;
      } else {
        result[key] = '';
      }
    }
  }
  if (inBlock && key) result[key] = value.join('\n');
  return result;
}

function slug(text) {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

console.log('[3/4] Loading knowledgebase files...');
let stored = 0;
let errors = 0;

for (const [folder, namespace] of Object.entries(NAMESPACES)) {
  const dirPath = join(KB, folder);
  if (!existsSync(dirPath)) continue;

  // Collect both .md (OKF) and .yaml (legacy) files
  const files = [];
  try {
    const allFiles = readdirSync(dirPath);
    for (const f of allFiles) {
      if (f.endsWith('.md') && f !== 'index.md' && f !== 'log.md') {
        files.push({ name: f, type: 'okf' });
      } else if (f.endsWith('.yaml')) {
        files.push({ name: f, type: 'legacy' });
      }
    }
  } catch (e) {
    continue;
  }

  console.log(`  ${folder}/: ${files.length} files`);

  for (const { name: file, type } of files) {
    try {
      const content = readFileSync(join(dirPath, file), 'utf8');
      let parsed, title, desc, tags, extraMeta;

      if (type === 'okf') {
        parsed = parseOkfMarkdown(content);
        const fm = parsed.frontmatter;
        title = fm.title || fm.name || file.replace('.md', '');
        desc = fm.description || fm.summary || parsed.body.slice(0, 200);
        tags = fm.tags || [folder];
        if (typeof tags === 'string') tags = [tags];
        extraMeta = {
          type: fm.type || 'Concept',
          file,
          source: `knowledgebase/${folder}/${file}`,
          ...Object.fromEntries(
            Object.entries(fm).filter(([k]) =>
              !['type', 'title', 'description', 'resource', 'tags', 'timestamp'].includes(k)
            )
          ),
        };
      } else {
        parsed = parseYamlFrontmatter(content);
        title = parsed.title || parsed.name || parsed.id || file.replace('.yaml', '');
        desc = parsed.description || parsed.summary || parsed.decision || content.slice(0, 200);
        tags = parsed.topics || [folder];
        if (typeof tags === 'string') tags = [tags];
        extraMeta = {
          title,
          type: folder,
          file,
          source: `knowledgebase/${folder}/${file}`,
          ...Object.fromEntries(
            Object.entries(parsed).filter(([k]) =>
              ['status', 'date', 'category', 'context', 'consequences', 'implementation'].includes(k)
            )
          ),
        };
      }

      const entryId = file.replace(/\.(md|yaml)$/, '');

      await memory.store({
        key: entryId,
        namespace,
        content: desc,
        metadata: extraMeta,
        tags: Array.isArray(tags) ? tags : [folder],
      });
      stored++;
      if (stored % 20 === 0) console.log(`    ... ${stored} entries stored`);
    } catch (e) {
      console.error(`    ERROR ${file}: ${e.message}`);
      errors++;
    }
  }
}

console.log(`[4/4] Done: ${stored} stored, ${errors} errors`);

const stats = await memory.getStats();
console.log('  Stats:', JSON.stringify(stats, null, 0));

await memory.shutdown();
process.exit(errors > 0 ? 1 : 0);
