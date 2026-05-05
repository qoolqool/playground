#!/usr/bin/env node
/**
 * Load all knowledgebase YAML files into AgentDB with vector embeddings.
 * Uses @claude-flow/memory (marketplace build) + Xenova transformers (from npx cache).
 */
import { readFileSync, readdirSync } from 'node:fs';
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
};

function parseYamlFrontmatter(content) {
  // Simple YAML key: value extraction (no library needed)
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
  if (!readdirSync) continue;

  const files = readdirSync(dirPath).filter(f => f.endsWith('.yaml'));
  console.log(`  ${folder}/: ${files.length} files`);

  for (const file of files) {
    try {
      const content = readFileSync(join(dirPath, file), 'utf8');
      const parsed = parseYamlFrontmatter(content);
      const entryId = file.replace('.yaml', '');
      const title = parsed.title || parsed.name || parsed.id || entryId;
      const desc = parsed.description || parsed.summary || parsed.decision || content.slice(0, 200);

      await memory.store({
        key: entryId,
        namespace,
        content: desc,
        metadata: {
          title,
          type: folder,
          file,
          source: `knowledgebase/${folder}/${file}`,
          ...Object.fromEntries(
            Object.entries(parsed).filter(([k]) =>
              ['status', 'date', 'category', 'context', 'consequences', 'implementation'].includes(k)
            )
          ),
        },
        tags: parsed.topics || [folder],
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
