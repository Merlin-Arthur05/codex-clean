/**
 * Load test for the Pi extension (pi-extension/index.ts).
 *
 * Verifies that Pi's own extension loader can load the extension and that it
 * registers the expected tools and command. This is the only test that needs
 * Node and Pi; it skips cleanly when Pi is not installed so the Python suite
 * stays runnable everywhere.
 *
 * Usage:  node tests/test_pi_extension.mjs
 *   Requires @earendil-works/pi-coding-agent to be resolvable. Set
 *   PI_CODING_AGENT_DIR / HOME to a throwaway dir to avoid touching real data.
 *
 * Exit: 0 = passed (or skipped), 1 = failed.
 */
import { createRequire } from "node:module";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "..");
const EXT = resolve(REPO, "pi-extension", "index.ts");

const results = [];
const check = (name, ok, detail = "") => {
  results.push([name, !!ok]);
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${name}${!ok && detail ? "   " + detail : ""}`);
};

/**
 * Import Pi's public entry point.
 *
 * Pi's package.json `exports` declares only an "import" condition for ".".
 * `require.resolve()` therefore fails with ERR_PACKAGE_PATH_NOT_EXPORTED, and
 * deep paths such as /dist/core/extensions/loader.js are not exported at all.
 * A plain dynamic import is the supported way in, and it is also how Pi itself
 * pulls the loader in. `loadExtensions` is re-exported from the root.
 */
async function loadPi() {
  try {
    const m = await import("@earendil-works/pi-coding-agent");
    return m;
  } catch {
    return null;
  }
}

const pi = await loadPi();
if (!pi || typeof pi.discoverAndLoadExtensions !== "function") {
  console.log("SKIP  Pi is not installed (@earendil-works/pi-coding-agent not resolvable).");
  console.log("      Install it to run this test:  npm i @earendil-works/pi-coding-agent");
  process.exit(0);
}

if (!existsSync(EXT)) {
  check("extension file exists", false, EXT);
  process.exit(1);
}

// Load exactly the way Pi does, so virtual modules (typebox, the pi packages)
// resolve from Pi's own tree.
const res = await pi.discoverAndLoadExtensions([EXT], process.cwd());

check("extension loads with no errors", (res.errors?.length ?? 0) === 0,
  JSON.stringify(res.errors ?? []).slice(0, 300));

const ext = (res.extensions ?? [])[0];
check("one extension was loaded", !!ext);
if (!ext) {
  console.log("\n0/" + results.length + " passed");
  process.exit(1);
}

// tools/commands are Maps keyed by name.
const toolNames = [...ext.tools.keys()];
check("registers agent_cache_scan", toolNames.includes("agent_cache_scan"),
  toolNames.join(", "));
check("registers agent_cache_clean", toolNames.includes("agent_cache_clean"));
check("registers agent_cache_targets", toolNames.includes("agent_cache_targets"));
check("registers /clean-agents command", ext.commands.has("clean-agents"));

// ToolDefinition requires these fields; a missing one makes Pi reject the tool.
for (const name of toolNames) {
  const def = ext.tools.get(name).definition;
  const missing = ["name", "label", "description", "parameters", "execute"]
    .filter((k) => !(k in def));
  check(`tool ${name} is well-formed`, missing.length === 0, "missing " + missing.join(","));
  check(`tool ${name} has object parameters`,
    def.parameters?.type === "object", JSON.stringify(def.parameters).slice(0, 80));
}

// The clean tool must gate on confirmation when `yes` is absent.
const clean = ext.tools.get("agent_cache_clean").definition;
let confirmCalls = 0;
const declined = await clean.execute("t1", { target: "pi" }, undefined, undefined, {
  cwd: REPO,
  ui: {
    confirm: async () => {
      confirmCalls += 1;
      return false;
    },
    notify: () => {},
  },
});
check("clean asks for confirmation by default", confirmCalls === 1);
check("declining confirmation cancels the clean", declined.details?.cancelled === true);

// A live read-only scan must succeed and cover registered agents.
const scan = ext.tools.get("agent_cache_scan").definition;
const r = await scan.execute("t2", { target: "all" }, undefined, undefined, { cwd: REPO });
check("live scan exits 0", r.details?.exitCode === 0,
  "exit=" + r.details?.exitCode + " " + JSON.stringify(r.content?.[0]?.text ?? "").slice(0, 160));
check("live scan returns parsed items", Array.isArray(r.details?.items));

const targets = ext.tools.get("agent_cache_targets").definition;
const tr = await targets.execute("t3", {}, undefined, undefined, { cwd: REPO });
let rows = [];
try {
  rows = JSON.parse(tr.content.map((c) => c.text).join(""));
} catch {
  /* leave empty */
}
check("list-targets reports every agent",
  rows.map((x) => x.name).sort().join(",") === "claude-code,codex,pi",
  rows.map((x) => x.name).join(","));
check("pi protected list includes user-installed packages",
  (rows.find((x) => x.name === "pi")?.protected ?? []).includes("npm"));

const bad = results.filter(([, ok]) => !ok).map(([n]) => n);
console.log(`\n${results.length - bad.length}/${results.length} passed`);
if (bad.length) console.log("FAILED:", bad);
process.exit(bad.length ? 1 : 0);
