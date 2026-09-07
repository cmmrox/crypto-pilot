import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    headers: { "Cache-Control": "no-store" },
    proxy: process.env.VITE_DEV_API_PROXY
      ? {
          "/api": process.env.VITE_DEV_API_PROXY,
          "/health": process.env.VITE_DEV_API_PROXY,
        }
      : undefined,
  },
  build: { outDir: "dist", sourcemap: false },
});
