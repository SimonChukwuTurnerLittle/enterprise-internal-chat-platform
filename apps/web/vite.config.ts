import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // Same-origin API in development, as in production (Caddy proxies /api).
    proxy: {
      "/api": { target: process.env.API_URL ?? "http://localhost:8000" },
    },
  },
  test: {
    environment: "jsdom",
  },
});
