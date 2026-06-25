import fs from "node:fs";

// Context Kit patch for @zhafron/mcp-web-search 1.3.0.
// Upstream hard-codes the fetch_url schema limit to 25 MiB even though the
// runtime extractor already uses MAX_BYTES. Keep this narrow and fail the build
// if upstream changes the compiled source shape.
const serverPath = "/usr/local/lib/node_modules/@zhafron/mcp-web-search/dist/src/server.js";
let source = fs.readFileSync(serverPath, "utf8");

const replacements = [
  [
    'import { MAX_RESULTS } from "./constants.js";',
    'import { MAX_BYTES, MAX_RESULTS } from "./constants.js";'
  ],
  [
    "max_download_bytes: z.number().int().min(1).max(26214400).optional()",
    "max_download_bytes: z.number().int().min(1).max(MAX_BYTES).optional()"
  ]
];

for (const [before, after] of replacements) {
  if (!source.includes(before)) {
    throw new Error(`mcp-web-search patch target not found: ${before}`);
  }
  source = source.replace(before, after);
}

fs.writeFileSync(serverPath, source);
