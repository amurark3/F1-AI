#!/usr/bin/env node
/**
 * Reads an ESLint JSON report on stdin and splits the findings into two gates:
 *
 *   - sonar gate — the `sonarjs/*` rules plus the complexity/size budgets that
 *     mirror them (see `frontend/eslint.config.mjs`, "Code smells" sections).
 *   - lint gate  — every other rule (correctness, type hygiene, imports, style).
 *
 * Both gates read the same ESLint run, so there is exactly one lint pass per
 * commit; the split only changes how failures are reported and attributed.
 *
 * Exit code: 0 when no errors, 1 when either gate has at least one error.
 * Warnings are printed but never block, matching `npm run lint` in CI.
 */

/** Rules attributed to the sonar gate. Everything else is the lint gate. */
const SONAR_RULES = new Set([
  "complexity",
  "max-depth",
  "max-lines",
  "max-lines-per-function",
  "max-params",
  "no-nested-ternary",
]);

const SONAR_RULE_PREFIX = "sonarjs/";

const isSonarRule = (ruleId) =>
  ruleId != null && (ruleId.startsWith(SONAR_RULE_PREFIX) || SONAR_RULES.has(ruleId));

const SEVERITY_ERROR = 2;

const color = process.stderr.isTTY
  ? {
      red: (s) => `[31m${s}[0m`,
      yellow: (s) => `[33m${s}[0m`,
      dim: (s) => `[2m${s}[0m`,
      bold: (s) => `[1m${s}[0m`,
    }
  : { red: (s) => s, yellow: (s) => s, dim: (s) => s, bold: (s) => s };

const readStdin = async () => {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return Buffer.concat(chunks).toString("utf8").trim();
};

/** Flattens the ESLint report into `{ filePath, ...message }` records. */
const flatten = (results) =>
  results.flatMap((result) =>
    (result.messages ?? []).map((message) => ({ filePath: result.filePath, ...message })),
  );

const printGate = (label, findings, projectDir) => {
  const errors = findings.filter((f) => f.severity === SEVERITY_ERROR);
  const warnings = findings.filter((f) => f.severity !== SEVERITY_ERROR);

  if (errors.length === 0 && warnings.length === 0) {
    process.stderr.write(`  ${label}: no findings\n`);
    return 0;
  }

  const counts = [
    errors.length > 0 ? color.red(`${errors.length} error(s)`) : null,
    warnings.length > 0 ? color.yellow(`${warnings.length} warning(s)`) : null,
  ]
    .filter(Boolean)
    .join(", ");
  process.stderr.write(`  ${color.bold(label)}: ${counts}\n`);

  // Only errors are itemised — warnings do not block, so their detail belongs in
  // a full `npm run lint`, not in the commit-blocking output.
  const byFile = new Map();
  for (const error of errors) {
    const relative = error.filePath.startsWith(projectDir)
      ? error.filePath.slice(projectDir.length + 1)
      : error.filePath;
    byFile.set(relative, [...(byFile.get(relative) ?? []), error]);
  }

  for (const [file, fileErrors] of byFile) {
    process.stderr.write(`    ${file}\n`);
    for (const error of fileErrors) {
      const location = color.dim(`${error.line}:${error.column}`);
      const rule = color.dim(error.ruleId ?? "(no rule)");
      process.stderr.write(`      ${location}  ${error.message}  ${rule}\n`);
    }
  }

  return errors.length;
};

const main = async () => {
  const projectDir = process.argv[2] ?? process.cwd();
  const raw = await readStdin();

  if (raw === "") {
    process.stderr.write(`${color.red("ESLint produced no output — treating as a gate failure.")}\n`);
    return 1;
  }

  let results;
  try {
    results = JSON.parse(raw);
  } catch {
    process.stderr.write(`${color.red("Could not parse the ESLint report:")}\n${raw}\n`);
    return 1;
  }

  const findings = flatten(results);
  const lintErrors = printGate(
    "lint gate ",
    findings.filter((f) => !isSonarRule(f.ruleId)),
    projectDir,
  );
  const sonarErrors = printGate(
    "sonar gate",
    findings.filter((f) => isSonarRule(f.ruleId)),
    projectDir,
  );

  return lintErrors + sonarErrors > 0 ? 1 : 0;
};

main().then(
  (code) => process.exit(code),
  (error) => {
    process.stderr.write(`${color.red("eslint-gate-report crashed:")} ${String(error)}\n`);
    process.exit(1);
  },
);
