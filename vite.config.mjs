import { defineConfig } from "vite";
import path from "node:path";

export default defineConfig({
  root: path.resolve(process.cwd(), "frontend"),
  build: {
    outDir: path.resolve(process.cwd(), "app/static/dist"),
    emptyOutDir: true,
    cssCodeSplit: false,
    assetsDir: "assets",
    rollupOptions: {
      input: path.resolve(process.cwd(), "frontend/main.js"),
      output: {
        entryFileNames: "main.js",
        assetFileNames: "assets/[name][extname]",
        chunkFileNames: "chunks/[name].js",
      },
    },
  },
});

