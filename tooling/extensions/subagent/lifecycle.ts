import type { ChildProcess } from "node:child_process";

export class ProcessTracker {
 private processes = new Set<ChildProcess>();

 get size(): number {
 return this.processes.size;
 }

 add(proc: ChildProcess): void {
 this.processes.add(proc);
 }

 remove(proc: ChildProcess): void {
 this.processes.delete(proc);
 }

 killAll(): void {
 for (const proc of this.processes) {
 if (!proc.killed) {
 proc.kill("SIGTERM");
 }
 }
 }
}
