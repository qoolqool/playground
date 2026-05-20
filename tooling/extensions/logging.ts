/**
 * File-based logger for subagent extension.
 *
 * Default singleton writes to ~/.pi/logs/tooling-subagent.log.
 * Info/warn/error always write. Debug writes only when PI_SUBAGENT_DEBUG=1.
 * One-deep rotation when file exceeds 5 MB.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

export interface LoggerOptions {
 verbose?: boolean;
 maxSizeBytes?: number;
 rotationCheckInterval?: number;
}

export interface Logger {
 info(message: string): void;
 warn(message: string): void;
 error(message: string, err?: unknown): void;
 debug(message: string): void;
}

const DEFAULT_MAX_SIZE = 5 * 1024 * 1024;
const DEFAULT_ROTATION_CHECK_INTERVAL = 60 * 60 * 1000;
export const MAX_MESSAGE_LENGTH = 10 * 1024;
const TRUNCATED_MARKER = "...(truncated)";

function formatError(err: unknown): string {
 if (err instanceof Error) {
 return err.stack ?? `${err.name}: ${err.message}`;
 }
 return String(err);
}

function timestamp(): string {
 return new Date().toISOString().replace(/\.\d{3}Z$/, "");
}

function truncateMessage(message: string): string {
 if (message.length <= MAX_MESSAGE_LENGTH) return message;
 return message.slice(0, MAX_MESSAGE_LENGTH - TRUNCATED_MARKER.length) + TRUNCATED_MARKER;
}

export function createLogger(logPath: string, options?: LoggerOptions): Logger {
 const verbose = options?.verbose ?? false;
 const maxSizeBytes = options?.maxSizeBytes ?? DEFAULT_MAX_SIZE;
 const rotationCheckInterval = options?.rotationCheckInterval ?? DEFAULT_ROTATION_CHECK_INTERVAL;
 let lastRotationCheck = -Infinity;
 let stderrFallbackFired = false;

 function ensureDir(): void {
 const dir = path.dirname(logPath);
 if (!fs.existsSync(dir)) {
 fs.mkdirSync(dir, { recursive: true });
 }
 }

 function stderrFallback(context: string, err: unknown): void {
 if (stderrFallbackFired) return;
 stderrFallbackFired = true;
 const detail = err instanceof Error ? err.message : String(err);
 process.stderr.write(
 `[subagent] Logger ${context} failed: ${detail}. Further log errors will be silenced.\n`,
 );
 }

 function rotateIfNeeded(): void {
 const now = Date.now();
 if (now - lastRotationCheck < rotationCheckInterval) return;
 lastRotationCheck = now;
 try {
 const stat = fs.statSync(logPath);
 if (stat.size > maxSizeBytes) {
 fs.renameSync(logPath, `${logPath}.1`);
 }
 } catch (err) {
 if ((err as NodeJS.ErrnoException).code !== "ENOENT") {
 stderrFallback("rotation", err);
 }
 }
 }

 function write(level: string, message: string): void {
 try {
 ensureDir();
 rotateIfNeeded();
 const line = `${timestamp()} [${level}] ${truncateMessage(message)}\n`;
 fs.appendFileSync(logPath, line, "utf-8");
 } catch (err) {
 stderrFallback("write", err);
 }
 }

 return {
 info(message: string): void { write("INFO", message); },
 warn(message: string): void { write("WARN", message); },
 error(message: string, err?: unknown): void {
 const suffix = err ? ` — ${formatError(err)}` : "";
 write("ERROR", message + suffix);
 },
 debug(message: string): void {
 if (!verbose) return;
 write("DEBUG", message);
 },
 };
}

const LOG_PATH = path.join(os.homedir(), ".pi", "logs", "tooling-subagent.log");

export const log: Logger = createLogger(LOG_PATH, {
 verbose: process.env.PI_SUBAGENT_DEBUG === "1",
});
