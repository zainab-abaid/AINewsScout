import { describe, expect, it } from "vitest";

import { findHitIndex, normalizeForMatch, parseBlocks } from "../src/excerpt";

describe("parseBlocks", () => {
  it("splits headings, lists, rules and paragraphs", () => {
    const blocks = parseBlocks(
      "# Title\n\nFirst para.\n\n## Section\n\n- one\n- two\n\n---\n\nLast para.",
    );
    expect(blocks.map((b) => b.kind)).toEqual(["h", "p", "h", "ul", "hr", "p"]);
    const ul = blocks[3];
    if (ul.kind !== "ul") throw new Error("expected a list");
    expect(ul.items).toEqual(["one", "two"]);
  });

  it("keeps a body with no blank lines as one block", () => {
    // This is what a plain-text email import looks like, and why it read as a
    // single blob before bodies were converted from HTML.
    const blob = ["line one", "line two", "line three"].join("\n");
    expect(parseBlocks(blob)).toHaveLength(1);
  });
});

describe("normalizeForMatch", () => {
  it("collapses both link styles to the same words", () => {
    const newsletter = "vLLM [ https://substack.com/redirect/535088ca?j=eyJ1 ] shipped sharding";
    const markdown = "**[vLLM](https://substack.com/redirect/535088ca?j=eyJ1)** shipped sharding";
    expect(normalizeForMatch(newsletter)).toBe("vllm shipped sharding");
    expect(normalizeForMatch(markdown)).toBe("vllm shipped sharding");
  });

  it("ignores punctuation and curly quotes", () => {
    expect(normalizeForMatch("Agent Arena’s “new” cost-per-task filters.")).toBe(
      "agent arena s new cost per task filters",
    );
  });
});

describe("findHitIndex", () => {
  const body = [
    "# [AINews] Issue",
    "",
    "- **From:** AINews <swyx+ainews@substack.com>",
    "",
    "---",
    "",
    "## Twitter recap",
    "",
    "- **Small VLMs and local multimodal are getting serious**: Cohere launched **[North Micro Vision](https://substack.com/redirect/601d390a)**, a 7B vision model aimed at on-device document work.",
    "",
    "- **Other infra releases reinforced the same trend**: [turbopuffer](https://substack.com/redirect/7f0a) shipped sharding in beta for indexing up to a billion vectors.",
    "",
    "## Reddit recap",
    "",
    "DSPy 3.3.0 shipped:",
    "",
    "- dspy.Flex for optimizing code + prompts",
    "- ReActV2 with native/parallel tool calling",
  ].join("\n");
  const blocks = parseBlocks(body);

  it("finds the passage when the excerpt kept the newsletter's link style", () => {
    // The excerpt was captured from the plain-text import, the body is now
    // converted from HTML, so only the words are common to both.
    const excerpt =
      "Cohere launched North Micro Vision [ https://substack.com/redirect/601d390a?j=eyJ1IjoiM2 ], a 7B vision model aimed at on-device document work.";
    const hit = findHitIndex(blocks, excerpt);
    expect(blocks[hit].raw).toContain("North Micro Vision");
  });

  it("looks past a lead-in the model wrote itself", () => {
    const excerpt =
      "Vector databases are consolidating around sharding: Other infra releases reinforced the same trend: turbopuffer shipped sharding in beta for indexing up to a billion vectors.";
    const hit = findHitIndex(blocks, excerpt);
    expect(blocks[hit].raw).toContain("turbopuffer");
  });

  it("handles an excerpt that spans a line and the list under it", () => {
    const excerpt =
      "DSPy 3.3.0 shipped:\ndspy.Flex for optimizing code + prompts\nReActV2 with native/parallel tool calling";
    const hit = findHitIndex(blocks, excerpt);
    expect(hit).toBeGreaterThanOrEqual(0);
    expect(blocks[hit].raw).toContain("dspy.Flex");
  });

  it("prefers the block with the most overlap", () => {
    const excerpt =
      "Cohere launched North Micro Vision, a 7B vision model aimed at on-device document work.";
    const scores = blocks.map((b) => b.raw);
    const hit = findHitIndex(blocks, excerpt);
    expect(scores[hit]).toContain("North Micro Vision");
    expect(scores[hit]).not.toContain("turbopuffer");
  });

  it("reports no target rather than guessing", () => {
    expect(findHitIndex(blocks, "")).toBe(-1);
    expect(findHitIndex(blocks, "short")).toBe(-1);
    expect(findHitIndex(blocks, "entirely unrelated words about knitting patterns")).toBe(-1);
  });
});
