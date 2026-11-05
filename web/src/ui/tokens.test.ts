import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(join(here, "tokens.css"), "utf8");

function colorNames(block: string): string[] {
  return [...block.matchAll(/(--color-[\w-]+)\s*:/g)].map((m) => m[1] as string);
}

function blockAfter(marker: string): string {
  const start = css.indexOf(marker);
  expect(start, marker).toBeGreaterThanOrEqual(0);
  return css.slice(start, css.indexOf("}", start));
}

describe("tokens", () => {
  it("[B1-R12] every token has a dark value", () => {
    const light = colorNames(blockAfter(":root {"));
    expect(light.length).toBeGreaterThan(10);
    for (const marker of [':root:not([data-theme="light"])', ':root[data-theme="dark"]']) {
      const dark = colorNames(blockAfter(marker));
      for (const name of light) expect(dark, `${name} in ${marker}`).toContain(name);
    }
  });
});

// Lints source text as if it were a component module; stdin keeps the repo free of bad fixtures.
function lint(source: string): { status: number | null; out: string } {
  const bin = join(here, "../../node_modules/stylelint/bin/stylelint.mjs");
  const r = spawnSync(
    process.execPath,
    [bin, "--stdin", "--stdin-filename", join(here, "x.module.css")],
    { input: source, encoding: "utf8", cwd: join(here, "../..") },
  );
  return { status: r.status, out: r.stdout + r.stderr };
}

describe("token lint", () => {
  it("[B1-R12] lint rejects literal colour", () => {
    const bad = lint(".a { color: #fff; }\n");
    expect(bad.status).not.toBe(0);
    expect(bad.out).toContain("color-no-hex");
  });

  it("[B1-R12] lint rejects literal font family, size and spacing", () => {
    for (const decl of ["font-family: Arial", "font-size: 14px", "padding: 8px", "gap: 12px"]) {
      expect(lint(`.a { ${decl}; }\n`).status, decl).not.toBe(0);
    }
  });

  it("[B1-R12] lint rejects literal font shorthand and radius", () => {
    for (const decl of ["font: 14px Arial", "border-radius: 4px", "border-top-left-radius: 3px"]) {
      expect(
        lint(`.a { ${decl}; }
`).status,
        decl,
      ).not.toBe(0);
    }
  });

  it("[B1-R12] lint allows token arithmetic but not literal lengths in calc", () => {
    const ok = ".a { padding: calc(var(--space-1) * 2); margin: calc(-1 * var(--space-2)); }\n";
    expect(lint(ok).status).toBe(0);
    for (const v of ["calc(var(--space-1) + 4px)", "calc(2px * 2)"]) {
      expect(
        lint(`.a { padding: ${v}; }
`).status,
        v,
      ).not.toBe(0);
    }
  });

  it("[B1-R12] lint accepts token-only styles", () => {
    const ok = lint(
      ".a { color: var(--color-fg); font: inherit; font-family: var(--font-body);" +
        " font-size: var(--text-md); padding: 0 var(--space-2); gap: var(--space-1);" +
        " border-radius: 50%; border-bottom-left-radius: var(--radius-pill); }\n",
    );
    expect(ok.out).toBe("");
    expect(ok.status).toBe(0);
  });
});
