import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: `npm run dev` serves on 5173 and sends /api to the Python server on 8765.
// Build: `npm run build` writes dist/, which the Python server serves itself (no Node at run time).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8765" } },
  build: { outDir: "dist", sourcemap: true },
});
