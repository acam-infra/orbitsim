import { defineConfig } from "vite";
import { viteStaticCopy } from "vite-plugin-static-copy";

/** Cesium loads its workers, widgets CSS and assets at runtime from this base url. */
const CESIUM = "node_modules/cesium/Build/Cesium";

export default defineConfig({
  base: "./",
  define: { CESIUM_BASE_URL: JSON.stringify("./cesium") },
  server: { port: Number(process.env.PORT ?? 5288) },
  build: {
    chunkSizeWarningLimit: 6000,
    // two pages: the geometry viewer and the satsim co-simulation playback
    rollupOptions: { input: { main: "index.html", play: "play.html" } },
  },
  plugins: [
    viteStaticCopy({
      targets: ["Workers", "ThirdParty", "Assets", "Widgets"].map((dir) => ({ src: `${CESIUM}/${dir}`, dest: "cesium", rename: { stripBase: 4 } })),
    }),
  ],
});
