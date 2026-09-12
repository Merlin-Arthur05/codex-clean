/**
 * codex-clean — Pi extension.
 *
 * Exposes the codex-clean CLI as native Pi tools plus a `/clean-agents`
 * command, so the same scan -> confirm -> clean flow available in Codex and
 * Claude Code also works inside Pi.
 *
 * Design notes
 * ------------
 * - Thin wrapper. This extension never deletes anything itself; every safety
 *   rule (whitelist, per-item confirmation, protected list) lives in the
 *   Python script, which stays the single source of truth.
 * - Scanning is read-only and always safe. Cleaning asks for explicit user
 *   confirmation via ctx.ui.confirm before invoking the script with --clean.
 * - Portability: the script may live on read-only media (mounted image, live
 *   CD, CI checkout). Nothing here writes into the repository directory.
 *   The interpreter is probed in a fixed order and the first one that can
 *   actually run the script wins, so PATH-python, venv-python and py-launcher
 *   systems all work without configuration.
 * - No background processes, sockets, watchers or timers are started, so the
 *   factory is safe to run in invocations that never start a session.
 */
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { spawn } from "node:child_process";
import { access, constants } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
/** Repository layout: <repo>/pi-extension/index.ts -> <repo>/scripts/codex_clean.py */
const SCRIPT = resolve(HERE, "..", "scripts", "codex_clean.py");

const TARGETS = ["codex", "claude-code", "pi", "all"] as const;

type RunResult = { code: number; stdout: string; stderr: string };

/**
 * Candidate interpreters, in preference order.
 *
 * Each entry is the argv prefix that must be prepended to the script path.
 * The order is a hint, not a guarantee: some Windows installs expose `python`
 * as an App Execution Alias that exists but cannot run a script, so every
 * candidate is verified by actually executing it (see resolvePython).
 */
function pythonCandidates(): string[][] {
  if (process.env.CODEX_CLEAN_PYTHON) {
    return [process.env.CODEX_CLEAN_PYTHON.split(" ").filter(Boolean)];
  }
  return process.platform === "win32"
    ? [["py", "-3"], ["python"], ["python3"], ["py"]]
    : [["python3"], ["python"]];
}

/** Spawn one command and collect its output. */
function spawnOnce(
  cmd: string,
  argv: string[],
  cwd: string,
  signal?: AbortSignal,
): Promise<RunResult> {
  return new Promise((done) => {
    let child;
    try {
      child = spawn(cmd, argv, { cwd, signal, windowsHide: true });
    } catch (err) {
      done({ code: -1, stdout: "", stderr: String(err) });
      return;
    }
    let stdout = "";
    let stderr = "";
    child.stdout?.on("data", (d) => (stdout += d.toString()));
    child.stderr?.on("data", (d) => (stderr += d.toString()));
    child.on("error", (err) => done({ code: -1, stdout, stderr: stderr + String(err) }));
    child.on("close", (code) => done({ code: code ?? -1, stdout, stderr }));
  });
}

let cachedPython: string[] | null = null;

/**
 * Find an interpreter that can actually run the script.
 *
 * A candidate is rejected unless it reports a Python version, which excludes
 * Windows store aliases and unrelated `python`-named executables. The probe
 * runs `<cand> -c "import sys;print(sys.version_info[0])"`, so no script is
 * executed and nothing is written anywhere.
 */
async function resolvePython(cwd: string, signal?: AbortSignal): Promise<string[] | null> {
  if (cachedPython) return cachedPython;
  for (const cand of pythonCandidates()) {
    const [cmd, ...pre] = cand;
    const probe = await spawnOnce(
      cmd,
      [...pre, "-c", "import sys;print(sys.version_info[0])"],
      cwd,
      signal,
    );
    if (probe.code === 0 && /^3\s*$/.test(probe.stdout.trim())) {
      cachedPython = cand;
      return cand;
    }
  }
  return null;
}

/**
 * Run the cleaner script with the resolved interpreter.
 *
 * Scanning never writes to disk, so it is safe on read-only media. A genuine
 * non-zero exit from the script itself (2 = bad args, 3 = --check threshold)
 * is returned as-is rather than being retried.
 */
async function runScript(
  argv: string[],
  cwd: string,
  signal?: AbortSignal,
): Promise<RunResult> {
  await access(SCRIPT, constants.R_OK); // read-only is enough; never write here
  const python = await resolvePython(cwd, signal);
  if (!python) {
    return {
      code: -1,
      stdout: "",
      stderr:
        "No working Python 3 interpreter found. Install Python 3, or set " +
        "CODEX_CLEAN_PYTHON to its full path.",
    };
  }
  const [cmd, ...pre] = python;
  return spawnOnce(cmd, [...pre, SCRIPT, ...argv], cwd, signal);
}

/** Format a scan/clean run for the model, keeping exit-code meaning visible. */
function asText(r: RunResult): string {
  const body = (r.stdout || "").trim();
  if (r.code === 0) return body || "(no output)";
  if (r.code === 3) {
    return `${body}\n\n(exit 3: reclaimable space reached the --check threshold)`;
  }
  const err = (r.stderr || "").trim();
  return [body, err].filter(Boolean).join("\n\n") || `(exit ${r.code})`;
}

export default function (pi: ExtensionAPI) {
  /**
   * Tool: scan agent caches read-only. Always safe, never mutates anything.
   */
  pi.registerTool({
    name: "agent_cache_scan",
    label: "Scan agent caches",
    description:
      "Read-only scan of AI coding agent caches/logs/WAL (Codex, Claude Code, Pi). " +
      "Lists regenerable items and their sizes without changing anything.",
    promptSnippet: "Read-only scan of Codex/Claude Code/Pi caches, logs and WAL files",
    promptGuidelines: [
      "Use agent_cache_scan when the user asks how much disk space an AI coding agent uses, or asks to check Codex/Claude Code/Pi caches and logs.",
      "Prefer agent_cache_scan before agent_cache_clean so the user sees the reclaimable items first.",
    ],
    parameters: Type.Object({
      target: Type.Optional(
        Type.Union(
          [
            Type.Literal("codex"),
            Type.Literal("claude-code"),
            Type.Literal("pi"),
            Type.Literal("all"),
          ],
          { description: "Which agent to inspect. Defaults to codex." },
        ),
      ),
      age: Type.Optional(
        Type.Number({ description: "Only count files older than N days (0 = no filter)." }),
      ),
    }),
    async execute(_id, params, signal, _onUpdate, ctx: ExtensionContext) {
      const argv = ["--scan", "--json", "--lang", "en"];
      if (params.target) argv.push("--target", params.target);
      if (params.age && params.age > 0) argv.push("--age", String(params.age));
      const r = await runScript(argv, ctx.cwd, signal);
      if (r.code !== 0 && r.code !== 3) {
        return {
          content: [{ type: "text", text: `[error] ${asText(r)}` }],
          details: { exitCode: r.code, failed: true },
        };
      }
      let items: unknown = null;
      try {
        items = JSON.parse(r.stdout);
      } catch {
        /* keep raw stdout below */
      }
      return {
        content: [{ type: "text", text: r.stdout.trim() || "(no output)" }],
        details: { exitCode: r.code, items },
      };
    },
  });

  /**
   * Tool: clean agent caches. Confirms with the user first unless `yes` is
   * set, which the model should only do after the user already agreed.
   */
  pi.registerTool({
    name: "agent_cache_clean",
    label: "Clean agent caches",
    description:
      "Clean regenerable caches/logs of AI coding agents (Codex, Claude Code, Pi). " +
      "Deletes only whitelisted regenerable items; optionally VACUUMs SQLite databases. " +
      "Never touches conversations, configs or project files.",
    promptSnippet: "Clean Codex/Claude Code/Pi regenerable caches and logs",
    promptGuidelines: [
      "Use agent_cache_clean when the user explicitly asks to free space or clean an AI coding agent's cache or logs.",
      "Ask the user which agent to clean if it is ambiguous; agent_cache_clean defaults to codex.",
    ],
    parameters: Type.Object({
      target: Type.Optional(
        Type.Union(
          [
            Type.Literal("codex"),
            Type.Literal("claude-code"),
            Type.Literal("pi"),
            Type.Literal("all"),
          ],
          { description: "Which agent to clean. Defaults to codex." },
        ),
      ),
      vacuum: Type.Optional(
        Type.Boolean({ description: "Also VACUUM SQLite databases (keeps data, reclaims space)." }),
      ),
      age: Type.Optional(
        Type.Number({ description: "Only delete files older than N days (0 = no filter)." }),
      ),
      yes: Type.Optional(
        Type.Boolean({
          description:
            "Skip the interactive confirmation. Only set this when the user has already explicitly approved the cleanup.",
        }),
      ),
    }),
    async execute(_id, params, signal, _onUpdate, ctx: ExtensionContext) {
      const agent = params.target ?? "codex";
      const scope =
        params.age && params.age > 0
          ? `files older than ${params.age} days`
          : "all regenerable items";
      if (!params.yes) {
        const ok = await ctx.ui.confirm(
          "Clean agent caches",
          `Clean ${scope} for ${agent}${params.vacuum ? " (including database VACUUM)" : ""}?\n` +
            "Conversations, configs and project files are never touched.",
        );
        if (!ok) {
          return {
            content: [{ type: "text", text: "Cancelled by user." }],
            details: { cancelled: true },
          };
        }
      }
      const argv = ["--clean", "--yes", "--json", "--lang", "en", "--target", agent];
      if (params.vacuum) argv.push("--vacuum");
      if (params.age && params.age > 0) argv.push("--age", String(params.age));
      const r = await runScript(argv, ctx.cwd, signal);
      if (r.code !== 0) {
        return {
          content: [{ type: "text", text: `[error] ${asText(r)}` }],
          details: { exitCode: r.code, failed: true },
        };
      }
      let report: unknown = null;
      try {
        report = JSON.parse(r.stdout);
      } catch {
        /* keep raw stdout below */
      }
      return {
        content: [{ type: "text", text: r.stdout.trim() || "(no output)" }],
        details: { exitCode: r.code, report },
      };
    },
  });

  /**
   * Tool: show which agents are supported and what they expose.
   */
  pi.registerTool({
    name: "agent_cache_targets",
    label: "List agent clean targets",
    description:
      "List the AI coding agents codex-clean supports, their data directories, " +
      "cleanable items and per-agent capabilities.",
    promptSnippet: "List agents supported by codex-clean and their capabilities",
    parameters: Type.Object({}),
    async execute(_id, _params, signal, _onUpdate, ctx: ExtensionContext) {
      const r = await runScript(["--list-targets", "--json"], ctx.cwd, signal);
      return {
        content: [{ type: "text", text: r.code === 0 ? asText(r) : `[error] ${asText(r)}` }],
        details: { exitCode: r.code, failed: r.code !== 0 },
      };
    },
  });

  /**
   * Command: /clean-agents — scan, confirm in the TUI, then clean.
   */
  pi.registerCommand("clean-agents", {
    description: "Scan AI coding agent caches and clean them after confirmation",
    handler: async (args, ctx) => {
      const raw = (args || "").trim();
      const agent = (TARGETS as readonly string[]).includes(raw) ? raw : "codex";
      const scanned = await runScript(["--scan", "--lang", "en", "--target", agent], ctx.cwd);
      if (scanned.code !== 0) {
        ctx.ui.notify(
          `Scan failed:\n${scanned.stderr.trim() || scanned.stdout.trim()}`,
          "error",
        );
        return;
      }
      const ok = await ctx.ui.confirm(
        `Clean agent caches (${agent})`,
        `${scanned.stdout.trim()}\n\nProceed with the cleanup?`,
      );
      if (!ok) {
        ctx.ui.notify("Cleanup cancelled.", "info");
        return;
      }
      const cleaned = await runScript(
        ["--clean", "--yes", "--vacuum", "--lang", "en", "--target", agent],
        ctx.cwd,
      );
      if (cleaned.code !== 0) {
        ctx.ui.notify(`Cleanup failed:\n${cleaned.stderr.trim()}`, "error");
        return;
      }
      ctx.ui.notify(cleaned.stdout.trim() || "Cleanup finished.", "info");
    },
  });
}
