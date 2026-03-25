import * as esbuild from "esbuild";
import { readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(__dirname, "..");
const tsDir = path.join(root, "src", "ts");

const files = await readdir(tsDir);
const targets = files.filter(
  (f) => f.endsWith(".ts") && f !== "globals.d.ts"
);

for (const f of targets) {
  const base = f.replace(/\.ts$/, "");
  const entry = path.join(tsDir, f);
  if (base === "sw") {
    await esbuild.build({
      entryPoints: [entry],
      outfile: path.join(root, "static", "sw.js"),
      target: "es2020",
      logLevel: "warning",
    });
    continue;
  }
  await esbuild.build({
    entryPoints: [entry],
    outfile: path.join(root, "static", "js", `${base}.js`),
    target: "es2020",
    logLevel: "warning",
  });
}

console.log("built", targets.length, "targets");
