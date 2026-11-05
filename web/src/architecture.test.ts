import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const depcruise = (dir: string) =>
  spawnSync(process.execPath, ["node_modules/dependency-cruiser/bin/dependency-cruiser.mjs", dir], {
    encoding: "utf8",
  });

describe("architecture", () => {
  it("[S0-R05] dependency-cruiser rejects import outside web/", () => {
    const clean = depcruise("src");
    expect(clean.status, clean.stdout + clean.stderr).toBe(0);

    // A unique directory beside src, so concurrent runs never see each other's file.
    const dir = mkdtempSync(join(process.cwd(), "arch-violation-"));
    writeFileSync(join(dir, "v.ts"), 'import "../../engine/x";\nexport {};\n');
    try {
      const bad = depcruise(dir);
      expect(bad.status).not.toBe(0);
      expect(bad.stdout + bad.stderr).toContain("no-import-outside-web");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
