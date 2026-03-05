/**
 * Runs `tsc --noEmit` to catch compile errors across the entire app.
 * Prevents deploying broken imports, missing modules, or type errors.
 */
import { execSync } from "child_process";
import path from "path";

const ROOT = path.resolve(__dirname, "..");

test("TypeScript compiles without errors", () => {
  try {
    execSync("npx tsc --noEmit", { cwd: ROOT, encoding: "utf-8", timeout: 60_000 });
  } catch (err: any) {
    const output = (err.stdout || "") + (err.stderr || "");
    throw new Error(`TypeScript compilation failed:\n${output}`);
  }
});
