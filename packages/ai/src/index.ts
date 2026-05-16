// @quarrel/ai — the only path apps/web takes to reach an LLM (§1 rule 4).
// Streaming uses Vercel AI SDK in apps/web (§27 step 10), which can adapt
// the chatStream async iterator from `client.ts` directly.

export * from "./models";
export * from "./routing";
export * from "./types";
export * from "./errors";
export * from "./client";
export * from "./caching";
export * from "./trace";
