import { Command } from "commander";
import * as fs from "fs";
import * as path from "path";
import express from "express";

export const showCommand = new Command("show")
  .description("Show the review in the browser")
  .argument("<json-or-stdin>", "JSON payload containing chapters and prologue")
  .action(async (jsonArg) => {
    console.log(`Validating review payload from ${jsonArg}...`);
    try {
      const payloadStr = fs.readFileSync(jsonArg, "utf8");
      const payload = JSON.parse(payloadStr);

      const API_URL = process.env.DEVASSIST_API_URL || "http://localhost:8000";
      console.log(`Posting payload to ${API_URL}/api/v3/local-review...`);
      
      const fetch = (await import("node-fetch")).default;
      const res = await fetch(`${API_URL}/api/v3/local-review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      
      if (!res.ok) {
        throw new Error(`Failed to create local review: ${res.statusText}`);
      }
      const data = await res.json() as any;
      const run_id = data.run_id || 1; // Fallback if backend doesn't return run_id

      console.log(`Starting loopback server...`);
      const app = express();
      
      // Serve frontend static export
      const frontendPath = path.resolve(__dirname, "../../../frontend/out");
      if (fs.existsSync(frontendPath)) {
        app.use(express.static(frontendPath));
      } else {
        console.warn("Warning: frontend/out not found. Please build the frontend.");
      }

      const port = 8000;
      app.listen(port, () => {
        console.log(`Opening browser to http://127.0.0.1:${port}/reviews/${run_id} ...`);
        import("open").then((open) => {
          open.default(`http://127.0.0.1:${port}/reviews/${run_id}`);
        });
      });
    } catch (err) {
      console.error("Error running show command:", err);
      process.exit(1);
    }
  });
