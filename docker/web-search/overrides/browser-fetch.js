import { HTTP_TIMEOUT, MAX_BYTES } from "../constants.js";
import { browserPool } from "../utils/browser-pool.js";
import { assertSafeUrl } from "./security.js";
import { fetchViaVettedAddress } from "./http.js";

const MAX_BROWSER_REQUESTS = 100;
const MAX_BROWSER_TOTAL_BYTES = Math.min(MAX_BYTES, 20 * 1024 * 1024);

function responseHeaders(headers) {
  const record = {};
  headers.forEach((value, key) => { record[key] = value; });
  return record;
}

export async function fetchBrowserResource(url, timeoutMs = HTTP_TIMEOUT, signal) {
  signal?.throwIfAborted();
  await assertSafeUrl(url);
  return browserPool.withBrowser(async browser => {
    const page = await browser.newPage();
    const pendingRequests = new Set();
    const abort = () => void page.close().catch(() => undefined);
    signal?.addEventListener("abort", abort, { once: true });
    try {
      signal?.throwIfAborted();
      const devtools = await page.target().createCDPSession();
      await devtools.send("Network.enable");
      await devtools.send("Network.setBlockedURLs", {
        urls: ["ws://*", "wss://*", "file://*", "ftp://*"]
      });
      await page.evaluateOnNewDocument(() => {
        const blockedTransport = name => class {
          constructor() {
            throw new DOMException(`${name} is disabled by the safe browser fetcher`, "SecurityError");
          }
        };
        for (const name of ["WebSocket", "WebTransport", "RTCPeerConnection", "webkitRTCPeerConnection"]) {
          if (name in globalThis) {
            Object.defineProperty(globalThis, name, {
              configurable: false,
              writable: false,
              value: blockedTransport(name)
            });
          }
        }
      });
      await page.setBypassServiceWorker(true);
      let requests = 0;
      let totalBytes = 0;
      let blockedError;
      await page.setRequestInterception(true);
      page.on("request", request => {
        const pending = (async () => {
          try {
            const requestUrl = new URL(request.url());
            if (!["http:", "https:"].includes(requestUrl.protocol)) throw new Error("unsupported browser request scheme");
            if (request.method() !== "GET") throw new Error("browser fetch blocks non-GET requests");
            requests += 1;
            if (requests > MAX_BROWSER_REQUESTS) throw new Error("browser request limit exceeded");
            await assertSafeUrl(requestUrl);
            const upstream = await fetchViaVettedAddress(requestUrl, timeoutMs, signal);
            const body = Buffer.from(await upstream.arrayBuffer());
            totalBytes += body.byteLength;
            if (totalBytes > MAX_BROWSER_TOTAL_BYTES) throw new Error("browser byte limit exceeded");
            await request.respond({
              status: upstream.status,
              headers: responseHeaders(upstream.headers),
              body
            });
          } catch (error) {
            blockedError ||= error;
            await request.abort("blockedbyclient").catch(() => undefined);
          }
        })();
        pendingRequests.add(pending);
        void pending.finally(() => pendingRequests.delete(pending));
      });
      signal?.throwIfAborted();
      const navigation = await page.goto(url.toString(), {
        waitUntil: "networkidle2",
        timeout: timeoutMs
      });
      if (blockedError && !navigation) throw blockedError;
      const finalUrl = new URL(page.url());
      await assertSafeUrl(finalUrl);
      const html = await page.content();
      const buffer = Buffer.from(html);
      if (buffer.byteLength > MAX_BYTES) throw new Error("rendered content too large");
      const headers = new Headers({ "content-type": "text/html; charset=utf-8" });
      const status = navigation?.status() || 200;
      const response = new Response(new Uint8Array(buffer), { status, headers });
      Object.defineProperty(response, "url", { value: finalUrl.toString() });
      return {
        response,
        finalUrl: finalUrl.toString(),
        contentType: headers.get("content-type"),
        buffer,
        byteLength: buffer.byteLength
      };
    } catch (error) {
      signal?.throwIfAborted();
      throw error;
    } finally {
      signal?.removeEventListener("abort", abort);
      if (!page.isClosed()) await page.close();
      await Promise.allSettled(pendingRequests);
    }
  });
}
