/* global process, console, URL */
// Fail on any high or critical npm advisory except a documented, unexpired
// exception in audit-exceptions.json (SECURITY_GUIDELINES.md, "Dependencies").
// npm audit has no ignore option, and a package flagged only through an
// excepted advisory must not fail the gate.
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

const BLOCKING = new Set(["high", "critical"]);
const exceptions = JSON.parse(readFileSync(new URL("../audit-exceptions.json", import.meta.url)));
const today = new Date().toISOString().slice(0, 10);

function fail(message) {
  console.error(`audit failed: ${message}`);
  process.exit(1);
}

// Fail closed: only a complete audit report may pass. npm audit exits 1 when it
// finds anything; any other failure (registry outage, bad lockfile) is an error.
let output;
try {
  output = execFileSync("npm", ["audit", "--json"], { encoding: "utf8" });
} catch (error) {
  if (error.status !== 1 || !error.stdout) fail(`npm audit did not run (status ${error.status})`);
  output = error.stdout;
}
let report;
try {
  report = JSON.parse(output);
} catch {
  fail("npm audit output is not JSON");
}
if (
  report.error ||
  typeof report.vulnerabilities !== "object" ||
  !report.metadata?.vulnerabilities
) {
  fail(
    `npm audit returned no report: ${report.error?.summary || report.error?.code || "missing vulnerabilities"}`,
  );
}
const vulnerabilities = report.vulnerabilities;

const advisories = new Map();
for (const entry of Object.values(vulnerabilities)) {
  for (const via of entry.via) {
    if (typeof via === "object" && BLOCKING.has(via.severity)) {
      advisories.set(via.url.split("/").pop(), via);
    }
  }
}

let failed = false;
for (const [id, advisory] of advisories) {
  const exception = exceptions[id];
  if (exception && exception.expires >= today) {
    console.log(`excepted until ${exception.expires}: ${id} ${advisory.name} ${advisory.title}`);
  } else {
    failed = true;
    const note = exception ? ` (exception expired ${exception.expires})` : "";
    console.error(`${advisory.severity}: ${id} ${advisory.name} ${advisory.title}${note}`);
  }
}
for (const [id, exception] of Object.entries(exceptions)) {
  if (!advisories.has(id)) console.log(`unused exception, remove it: ${id} (${exception.package})`);
}
console.log(failed ? "audit failed" : "audit passed: no unexcepted high or critical advisory");
process.exit(failed ? 1 : 0);
