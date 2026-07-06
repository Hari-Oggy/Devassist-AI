#!/usr/bin/env node
import { Command } from "commander";
import { prepCommand } from "./commands/prep";
import { showCommand } from "./commands/show";

const program = new Command();

program
  .name("devassist")
  .description("DevAssist AI local CLI")
  .version("1.0.0");

program.addCommand(prepCommand);
program.addCommand(showCommand);

program.parse();
