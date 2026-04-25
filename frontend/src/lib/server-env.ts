import "server-only";

import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

import { getLocalProjectPaths } from "@/lib/local-paths";

let cachedRootEnv: Record<string, string> | null = null;

function stripWrappingQuotes(value: string) {
  if (value.length >= 2) {
    const first = value[0];
    const last = value[value.length - 1];
    if ((first === `"` && last === `"`) || (first === `'` && last === `'`)) {
      return value.slice(1, -1);
    }
  }
  return value;
}

function loadRootEnv() {
  if (cachedRootEnv) {
    return cachedRootEnv;
  }

  const { rootDir } = getLocalProjectPaths();
  const envPath = path.join(rootDir, ".env");
  const values: Record<string, string> = {};

  if (!existsSync(envPath)) {
    cachedRootEnv = values;
    return values;
  }

  for (const rawLine of readFileSync(envPath, "utf8").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) {
      continue;
    }

    const separator = line.indexOf("=");
    const key = line.slice(0, separator).trim();
    const value = stripWrappingQuotes(line.slice(separator + 1).trim());

    if (key) {
      values[key] = value;
    }
  }

  cachedRootEnv = values;
  return values;
}

export function getServerEnv(name: string) {
  const runtimeValue = process.env[name];
  if (runtimeValue && runtimeValue.trim()) {
    return runtimeValue.trim();
  }

  const rootValue = loadRootEnv()[name];
  return rootValue && rootValue.trim() ? rootValue.trim() : null;
}
