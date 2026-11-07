import { defineConfig } from "vite";

export default defineConfig({
  preview: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: { "/api": "http://127.0.0.1:8000" },
    watch: {
      ignored: [
        "**/data/**",
        "**/.venv/**",
        "**/backend/**",
        "**/docs/**",
        "**/tests/**",
        "**/.env",
        "**/.env.*",
      ],
    },
    fs: {
      deny: [
        ".env",
        ".env.*",
        "*.{crt,pem}",
        "**/.git/**",
        "**/data/**",
        "**/backend/**",
        "**/scripts/**",
        "**/deploy/**",
      ],
    },
  },
  build: {
    target: "es2022",
    chunkSizeWarningLimit: 1100,
    rollupOptions: {
      input: {
        dashboard: "index.html",
        investigations: "advanced.html",
        monitoring: "monitoring.html",
      },
    },
  },
});
