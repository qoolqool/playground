export const DEFAULT_SUBAGENT_CONCURRENCY = 6;

export function getSubagentConcurrency(): number {
 const envVal = process.env.PI_SUBAGENT_CONCURRENCY;
 if (envVal) {
 const parsed = Number.parseInt(envVal, 10);
 if (Number.isFinite(parsed)) return Math.max(1, parsed);
 }
 return DEFAULT_SUBAGENT_CONCURRENCY;
}

export class Semaphore {
 private _active = 0;
 private _queue: Array<() => void> = [];

 constructor(private _limit: number) {}

 get limit(): number {
 return this._limit;
 }

 get active(): number {
 return this._active;
 }
 get waiting(): number {
 return this._queue.length;
 }

 async acquire(): Promise<() => void> {
 if (this._active < this._limit) {
 this._active++;
 return this._createRelease();
 }
 return new Promise<() => void>((resolve) => {
 this._queue.push(() => {
 this._active++;
 resolve(this._createRelease());
 });
 });
 }

 private _createRelease(): () => void {
 let released = false;
 return () => {
 if (released) return;
 released = true;
 this._active--;
 const next = this._queue.shift();
 if (next) next();
 };
 }
}
