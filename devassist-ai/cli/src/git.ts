import { exec } from "child_process";
import { promisify } from "util";

const execAsync = promisify(exec);

export interface PrepOpts {
  base?: string;
  compare?: string;
}

export async function computeDiff(opts: PrepOpts): Promise<string> {
  const base = opts.base ?? "main";
  const compare = opts.compare ?? "HEAD";
  
  try {
    const { stdout } = await execAsync(`git diff --unified=3 ${base}...${compare}`);
    return stdout;
  } catch (err) {
    // If it fails, fallback to simple diff
    const { stdout } = await execAsync(`git diff HEAD`);
    return stdout;
  }
}
