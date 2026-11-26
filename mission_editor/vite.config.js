import { defineConfig } from "vite";

export default defineConfig({
  publicDir: "node_modules/blockly/media",
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
    },
  },
});
