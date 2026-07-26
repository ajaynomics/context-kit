import http from "node:http";

let websocketUpgrades = 0;
let slowRequests = 0;

const server = http.createServer((request, response) => {
  const url = new URL(request.url, "http://mock-search.test");
  if (url.pathname === "/search") {
    response.writeHead(200, { "Content-Type": "application/json" });
    response.end(JSON.stringify({
      results: [{
        title: "Deterministic Search Result",
        url: "https://example.test/result",
        content: `fixture result for ${url.searchParams.get("q")}`
      }]
    }));
    return;
  }
  if (url.pathname === "/dynamic") {
    response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    response.end(`<!doctype html><html><head><title>Dynamic Fixture</title></head>
      <body><main id="content">initial content</main>
      <script>document.getElementById("content").textContent = "BROWSER_RENDERED_MARKER";</script>
      </body></html>`);
    return;
  }
  if (url.pathname === "/slow") {
    slowRequests += 1;
    let closed = false;
    response.once("close", () => {
      if (closed) return;
      closed = true;
      slowRequests -= 1;
    });
    response.writeHead(200, { "Content-Type": "text/plain" });
    response.write("pending");
    return;
  }
  if (url.pathname === "/slow-count") {
    response.writeHead(200, { "Content-Type": "text/plain" });
    response.end(String(slowRequests));
    return;
  }
  if (url.pathname === "/redirect-private") {
    response.writeHead(302, { Location: "http://127.0.0.1:8765/private" });
    response.end();
    return;
  }
  if (url.pathname === "/websocket-attempt") {
    response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    response.end(`<!doctype html><html><body><main id="content">starting</main>
      <script>
        const socket = new WebSocket("ws://mock-search.test:8080/socket");
        socket.onerror = () => { document.getElementById("content").textContent = "WEBSOCKET_BLOCKED"; };
      </script></body></html>`);
    return;
  }
  if (url.pathname === "/ws-count") {
    response.writeHead(200, { "Content-Type": "text/plain" });
    response.end(String(websocketUpgrades));
    return;
  }
  response.writeHead(404).end();
});

server.listen(8080, "0.0.0.0");
server.on("upgrade", (_request, socket) => {
  websocketUpgrades += 1;
  socket.destroy();
});
