import { spawnSync } from "node:child_process";
import { rmSync, writeFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const depcruise = () =>
  spawnSync(
    process.execPath,
    ["node_modules/dependency-cruiser/bin/dependency-cruiser.mjs", "src"],
    { encoding: "utf8" },
  );

describe("architecture", () => {
  it("[S0-R05] dependency-cruiser rejects import outside web/", () => {
    const clean = depcruise();
    expect(clean.status, clean.stdout + clean.stderr).toBe(0);

    const tmp = "src/__violation.ts";
    writeFileSync(tmp, 'import "../../engine/x";\nexport {};\n');
    try {
      const bad = depcruise();
      expect(bad.status).not.toBe(0);
      expect(bad.stdout + bad.stderr).toContain("no-import-outside-web");
    } finally {
      rmSync(tmp, { force: true });
    }
  });
});
