import assert from "node:assert/strict";

import { boundFetchCollections } from "../docker/web-search/overrides/bounds.mjs";
import {
  attemptProvider,
  classifyProviderError
} from "../docker/web-search/overrides/diagnostics.mjs";

assert.deepEqual(classifyProviderError(new Error("HTTP 429 rate limit")), {
  category: "rate_limited",
  message: "HTTP 429 rate limit"
});
assert.equal(classifyProviderError(new Error("captcha challenge")).category, "blocked");

const unavailable = await attemptProvider({ name: "brave", configured: false }, "q", 3, "en");
assert.equal(unavailable.diagnostic.status, "unavailable");
assert.equal(unavailable.diagnostic.result_count, 0);

const empty = await attemptProvider({
  name: "empty",
  async search() { return []; }
}, "q", 3, "en");
assert.equal(empty.diagnostic.status, "empty");

const failed = await attemptProvider({
  name: "failed",
  async search() { throw new Error("network socket failed"); }
}, "q", 3, "en");
assert.equal(failed.diagnostic.status, "error");
assert.equal(failed.diagnostic.error.category, "network");

let underlyingAborted = false;
let underlyingCleanupFinished = false;
const timedOut = await attemptProvider({
  name: "slow",
  async search(_query, _limit, _lang, signal) {
    await new Promise((resolve, reject) => {
      signal.addEventListener("abort", () => {
        underlyingAborted = true;
        setTimeout(() => {
          underlyingCleanupFinished = true;
          reject(signal.reason);
        }, 25);
      }, { once: true });
    });
  }
}, "q", 3, "en", { timeoutMs: 20 });
assert.equal(timedOut.diagnostic.error.category, "timeout");
assert.equal(underlyingAborted, true);
assert.equal(underlyingCleanupFinished, true);

const cancellation = new AbortController();
const cancellationReason = new Error("search request cancelled");
let cancellationCleanupFinished = false;
const cancelled = attemptProvider({
  name: "cancelled",
  async search(_query, _limit, _lang, signal) {
    await new Promise((resolve, reject) => {
      signal.addEventListener("abort", () => {
        setTimeout(() => {
          cancellationCleanupFinished = true;
          reject(signal.reason);
        }, 10);
      }, { once: true });
    });
  }
}, "q", 3, "en", { timeoutMs: 1000, signal: cancellation.signal });
cancellation.abort(cancellationReason);
await assert.rejects(cancelled, error => error === cancellationReason);
assert.equal(cancellationCleanupFinished, true);

const result = boundFetchCollections({
  links: Array.from({ length: 550 }, (_, index) => ({ url: `https://example.test/${index}` })),
  media: {
    images: Array.from({ length: 250 }, (_, index) => ({ url: `https://example.test/${index}.png` })),
    videos: [],
    audio: []
  },
  warnings: []
});
assert.equal(result.links.length, 500);
assert.equal(result.media.images.length, 200);
assert(result.warnings.some(warning => warning.includes("links truncated")));
assert(result.warnings.some(warning => warning.includes("images truncated")));

console.log("pass web-search diagnostics and collection bounds tests");
