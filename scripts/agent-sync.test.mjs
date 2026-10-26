import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { agentBody, mirrors, replaceMirror, check, write } from "./agent-sync.mjs";

const agent = (body) => `---\nname: x\ndescription: y\n---\n\n${body}\n`;
const kick = (name, body) => `# K\n\n## Section\n\n<!-- agent-body: ${name} -->\n${body}\n<!-- /agent-body -->\n\nafter\n`;
function repo({ claude = {}, docs = {}, kickoff }) {
  const r = mkdtempSync(join(tmpdir(), "agent-sync-"));
  mkdirSync(join(r, ".claude/agents"), { recursive: true });
  mkdirSync(join(r, "docs/agents"), { recursive: true });
  for (const [n, b] of Object.entries(claude)) writeFileSync(join(r, ".claude/agents", `${n}.md`), agent(b));
  for (const [n, b] of Object.entries(docs)) writeFileSync(join(r, "docs/agents", `${n}.md`), agent(b));
  writeFileSync(join(r, "docs/KICKOFF-PROMPT.md"), kickoff);
  return r;
}
test("agentBody strips the frontmatter and trims", () => {
  assert.equal(agentBody(agent("You are a reviewer.\n\n## How")), "You are a reviewer.\n\n## How");
  assert.throws(() => agentBody("no frontmatter"));
});
test("mirrors finds every block by name", () => {
  const k = kick("a", "A body") + kick("b", "B body");
  assert.deepEqual(mirrors(k).map((m) => m.name), ["a", "b"]);
  assert.equal(mirrors(k)[1].body, "B body");
});
test("in sync passes", () => {
  assert.deepEqual(check(repo({ claude: { ux: "Same.\nLines." }, kickoff: kick("ux", "Same.\nLines.") })), []);
});
test("a changed agent file is caught", () => {
  const p = check(repo({ claude: { ux: "New text." }, kickoff: kick("ux", "Old text.") }));
  assert.equal(p.length, 1); assert.match(p[0], /ux: KICKOFF-PROMPT.md differs/);
});
test("a missing agent file is caught", () => {
  assert.match(check(repo({ kickoff: kick("ghost", "x") }))[0], /no .claude\/agents\/ghost.md/);
});
test("an agent still in docs/agents is found, and the move is asked for", () => {
  const p = check(repo({ docs: { id: "Brief." }, kickoff: kick("id", "Brief.") }));
  assert.equal(p.length, 1); assert.match(p[0], /still in docs\/agents/);
});
test("--write copies the agent file into its block and nothing else", () => {
  const r = repo({ claude: { ux: "Fresh." }, kickoff: kick("ux", "Stale.") });
  write(r);
  assert.equal(readFileSync(join(r, "docs/KICKOFF-PROMPT.md"), "utf8"), kick("ux", "Fresh."));
  assert.deepEqual(check(r), []);
});
test("replaceMirror refuses an unknown name", () => {
  assert.throws(() => replaceMirror(kick("a", "x"), "b", "y"));
});
