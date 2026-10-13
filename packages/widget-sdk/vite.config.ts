import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const here = (path: string) => fileURLToPath(new URL(path, import.meta.url));

// Builds a single self-contained script that the chat web app serves at /sdk/v1/chat-widget.js
export default defineConfig({
  build: {
    lib: {
      entry: here("./src/index.ts"),
      name: "EnterpriseChat",
      formats: ["iife"],
      fileName: () => "chat-widget.js",
    },
    outDir: here("../../apps/web/public/sdk/v1"),
    emptyOutDir: true,
    sourcemap: true,
  },
  test: {
    environment: "jsdom",
  },
});
