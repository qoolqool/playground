/**
 * distill-and-index: handoff resume + compaction indexing + auto KB search
 *
 * BEFORE_AGENT_START:
 *   - Injects pending handoff (open questions, next steps, blockers)
 *   - Injects cached KB gotcha hints from previous agent_end scan
 *
 * AGENT_END:
 *   - Scans the turn for errors or troubleshooting patterns
 *   - If found, searches KB gotchas for matching entries
 *   - Caches results for injection on next before_agent_start
 *
 * SESSION_BEFORE_COMPACT: indexes any hand-written knowledgebase files
 * into the vector DB so they're searchable post-compaction.
 *
 * Install: .pi/settings.json -> "extensions": [".pi/extensions/resume-handoff.ts"]
 */

import { execSync } from "node:child_process";
import { existsSync } from "node:fs";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const HANDOFF_PATH = "/project/knowledgebase/handoffs/handoff.yaml";
const RESUME_SCRIPT = "/project/.pi/skills/distill-and-index/resume-handoff.sh";
const LOAD_SCRIPT = "/project/.pi/skills/distill-and-index/load-kb-to-memory.py";
const SEARCH_SCRIPT = "/project/tooling/scripts/search-kb-memory.py";

// --- Cross-turn cache: agent_end stores, before_agent_start injects ---
let pendingKbHints: string | null = null;

const TROUBLE_KEYWORDS = [
    "error", "fail", "failed", "failure", "bug", "broken",
    "not working", "doesn't work", "doesnt work", "issue",
    "problem", "traceback", "exception", "unexpected",
    "why", "wrong", "incorrect", "crash", "crashing",
];

function extractText(content: unknown): string {
    if (typeof content === "string") return content;
    if (Array.isArray(content)) {
        return content
            .map((b: unknown) => {
                if (typeof b === "object" && b !== null && "text" in b)
                    return (b as { text: string }).text;
                return "";
            })
            .filter(Boolean)
            .join("\n");
    }
    return "";
}

function isTroubleshooting(text: string): boolean {
    const lower = text.toLowerCase();
    return TROUBLE_KEYWORDS.some((kw) => lower.includes(kw));
}

function searchKbGotchas(query: string): string | null {
    try {
        // Strip newlines, backticks, $(), ${}, and other shell-dangerous chars
        const sanitized = query
            .replace(/"/g, '\\"')
            .replace(/[\n\r`$(){}\[\]|&;<>]/g, ' ')
            .replace(/\s+/g, ' ')
            .trim()
            .slice(0, 400);
        if (!sanitized) return null;
        const output = execSync(
            `python3 "${SEARCH_SCRIPT}" "${sanitized}" -n gotchas -l 3`,
            { encoding: "utf-8", timeout: 5000 }
        );
        const trimmed = output.trim();
        if (!trimmed || trimmed.includes("No results")) return null;
        return trimmed;
    } catch {
        return null; // search-kb-memory.py not available or query failed
    }
}

function readHandoff(): string | null {
    if (!existsSync(HANDOFF_PATH)) return null;
    try {
        const output = execSync(`bash "${RESUME_SCRIPT}"`, {
            encoding: "utf-8",
            timeout: 3000,
        });
        return output.trim() || null;
    } catch {
        return null;
    }
}

function indexKnowledgebase(): void {
    try {
        execSync(`python3 "${LOAD_SCRIPT}"`, {
            encoding: "utf-8",
            timeout: 15000,
            stdio: "pipe",
        });
    } catch {
        // Non-critical — indexing failure shouldn't block compaction
    }
}

export default function (pi: ExtensionAPI) {
    // --- Handoff resume: inject on every agent start so it survives compaction ---
    // --- Also injects cached KB hints from previous agent_end scan ---
    pi.on("before_agent_start", async (event, _ctx) => {
        const parts: string[] = [];

        // 1. Handoff injection
        const handoff = readHandoff();
        if (handoff) {
            parts.push(`## Pending Handoff from Previous Session\n\n${handoff}`);
        }

        // 2. KB hint injection (cached from agent_end)
        if (pendingKbHints) {
            parts.push(pendingKbHints);
            pendingKbHints = null; // consumed
        }

        if (parts.length === 0) return;

        return {
            systemPrompt:
                parts.join("\n\n---\n\n") + "\n\n---\n\n" + event.systemPrompt,
        };
    });

    // --- Post-turn KB scan: detect troubleshooting, search gotchas ---
    pi.on("agent_end", async (event, _ctx) => {
        // Skip if we already have pending hints from a prior scan
        if (pendingKbHints) return;

        const errorTexts: string[] = [];
        let userQuery = "";

        for (const msg of event.messages) {
            const text = extractText(msg.content);

            if (msg.role === "user") {
                userQuery = text;
            }

            // Tool results with errors — these are the strongest signal
            if (msg.role === "tool") {
                if ((msg as Record<string, unknown>).isError) {
                    errorTexts.push(text.slice(0, 300));
                } else if (isTroubleshooting(text)) {
                    errorTexts.push(text.slice(0, 200));
                }
            }

            // Assistant messages that contain error-like language in tool results
            if (msg.role === "assistant" && text.toLowerCase().includes("error")) {
                errorTexts.push(text.slice(0, 200));
            }
        }

        // Build a combined search query
        const searchParts: string[] = [];
        if (errorTexts.length > 0) {
            searchParts.push(...errorTexts);
        } else if (isTroubleshooting(userQuery)) {
            searchParts.push(userQuery.slice(0, 200));
        } else {
            return; // Nothing looks like troubleshooting — skip search
        }

        const query = searchParts.join(" ").slice(0, 400);
        if (!query.trim()) return;

        const results = searchKbGotchas(query);
        if (!results) return;

        pendingKbHints =
            `## KB Gotchas Matching This Issue\n\n` +
            `The following gotchas from the knowledgebase may be relevant ` +
            `to the problem being investigated:\n\n${results}\n\n` +
            `(Auto-detected — run \`search-kb\` for a full search.)`;
    });

    // --- Compaction: re-index knowledgebase so vector DB stays current ---
    pi.on("session_before_compact", async (_event, _ctx) => {
        indexKnowledgebase();
    });
}
