import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";

const roots = ["app", "components"];
const checks = [
  ["double hyphen", / -- /g],
  ["placeholder", /lorem ipsum|TODO customer copy/gi],
  ["generic marketing", /revolutionary|cutting-edge|game-changing|supercharge|unlock|unleash|seamless|next-generation/gi],
];

async function files(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const nested = await Promise.all(entries.map((entry) => {
    const path = join(dir, entry.name);
    return entry.isDirectory() ? files(path) : (entry.name.endsWith(".tsx") || entry.name.endsWith(".ts") ? [path] : []);
  }));
  return nested.flat();
}

const sourceFiles = (await Promise.all(roots.map(files))).flat();
const findings = [];
for (const file of sourceFiles) {
  const source = await readFile(file, "utf8");
  for (const [label, pattern] of checks) {
    const count = [...source.matchAll(pattern)].length;
    if (count) findings.push(`${file}: ${label} × ${count}`);
  }
}

console.log(`Checked ${sourceFiles.length} customer-facing source files.`);
if (findings.length) console.log(findings.join("\n"));
