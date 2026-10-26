#!/usr/bin/env node
// Keeps each reviewer agent's brief identical in two places: the agent file Claude Code loads
// (.claude/agents/<name>.md, below its --- frontmatter) and its mirror in docs/KICKOFF-PROMPT.md
// (between <!-- agent-body: <name> --> and <!-- /agent-body -->), which a Claude app chat is given by paste.
//   node scripts/agent-sync.mjs           check: exit 1 and say which differ or are missing
//   node scripts/agent-sync.mjs --write   copy each agent file's body into KICKOFF-PROMPT.md (the agent file is the source)
// An agent file not yet in .claude/agents/ is looked for in docs/agents/ (a Claude app chat can't write .claude/).
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

export function agentBody(text) {
  const m = text.match(/^---\n[\s\S]*?\n---\n([\s\S]*)$/);
  if (!m) throw new Error("no --- frontmatter");
  return m[1].trim();
}
const BLOCK = /<!-- agent-body: ([\w-]+) -->\n([\s\S]*?)\n<!-- \/agent-body -->/g;
export function mirrors(kickoff) {
  return [...kickoff.matchAll(BLOCK)].map((m) => ({ name: m[1], body: m[2].trim() }));
}
export function replaceMirror(kickoff, name, body) {
  let found = false;
  const out = kickoff.replace(BLOCK, (all, n) => {
    if (n !== name) return all;
    found = true;
    return `<!-- agent-body: ${n} -->\n${body}\n<!-- /agent-body -->`;
  });
  if (!found) throw new Error(`no mirror block for ${name}`);
  return out;
}
export function findAgent(root, name) {
  for (const dir of [".claude/agents", "docs/agents"]) {
    const p = join(root, dir, `${name}.md`);
    if (existsSync(p)) return p;
  }
  return null;
}
export function check(root) {
  const kickoff = readFileSync(join(root, "docs/KICKOFF-PROMPT.md"), "utf8");
  const problems = [];
  const blocks = mirrors(kickoff);
  if (blocks.length === 0) problems.push("KICKOFF-PROMPT.md has no agent-body blocks");
  for (const { name, body } of blocks) {
    const p = findAgent(root, name);
    if (!p) { problems.push(`${name}: no .claude/agents/${name}.md (nor docs/agents/)`); continue; }
    if (agentBody(readFileSync(p, "utf8")) !== body) problems.push(`${name}: KICKOFF-PROMPT.md differs from ${p.slice(root.length + 1)}`);
    else if (p.includes("docs/agents")) problems.push(`${name}: in sync, but still in docs/agents/ — move it: git mv docs/agents/${name}.md .claude/agents/`);
  }
  return problems;
}
export function write(root) {
  const kp = join(root, "docs/KICKOFF-PROMPT.md");
  let kickoff = readFileSync(kp, "utf8");
  for (const { name } of mirrors(kickoff)) {
    const p = findAgent(root, name);
    if (p) kickoff = replaceMirror(kickoff, name, agentBody(readFileSync(p, "utf8")));
  }
  writeFileSync(kp, kickoff);
}
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const root = join(dirname(fileURLToPath(import.meta.url)), "..");
  if (process.argv.includes("--write")) write(root);
  const problems = check(root);
  for (const p of problems) console.log(p);
  console.log(problems.length ? `${problems.length} problem(s)` : "agent briefs in sync");
  process.exit(problems.some((p) => !p.includes("still in docs/agents")) ? 1 : 0);
}
