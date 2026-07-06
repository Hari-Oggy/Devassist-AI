import { Command } from "commander";
import { computeDiff } from "../git";
import * as fs from "fs";

export const prepCommand = new Command("prep")
  .description("Compute diff and prepare for review")
  .option("--base <ref>", "Base branch")
  .option("--compare <ref>", "Compare branch")
  .action(async (options) => {
    try {
      const diff = await computeDiff({ base: options.base, compare: options.compare });
      fs.writeFileSync("devassist-diff.txt", diff);
      console.log(process.cwd() + "/devassist-diff.txt");
    } catch (err) {
      console.error(err);
      process.exit(1);
    }
  });
