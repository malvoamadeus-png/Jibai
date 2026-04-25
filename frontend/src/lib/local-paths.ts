import "server-only";

import { existsSync } from "node:fs";
import path from "node:path";

export type LocalProjectPaths = {
  rootDir: string;
  dataDir: string;
  configDir: string;
  runtimeDir: string;
  stateDir: string;
  aiSettingsPath: string;
  aiSettingsExamplePath: string;
  watchlistPath: string;
  xWatchlistPath: string;
  runtimeSettingsPath: string;
  insightDbPath: string;
  xhsStatePath: string;
  xStatePath: string;
  xhsUserDataDir: string;
};

function looksLikeProjectRoot(candidate: string) {
  return (
    existsSync(path.join(candidate, "backend")) &&
    existsSync(path.join(candidate, "frontend")) &&
    existsSync(path.join(candidate, "data"))
  );
}

export function getLocalProjectPaths(): LocalProjectPaths {
  const candidates = [path.resolve(process.cwd()), path.resolve(process.cwd(), "..")];
  const rootDir = candidates.find(looksLikeProjectRoot) ?? candidates[candidates.length - 1];
  const dataDir = path.join(rootDir, "data");
  const configDir = path.join(dataDir, "config");
  const runtimeDir = path.join(dataDir, "runtime");
  const stateDir = path.join(runtimeDir, "state");

  return {
    rootDir,
    dataDir,
    configDir,
    runtimeDir,
    stateDir,
    aiSettingsPath: path.join(configDir, "ai_settings.local.json"),
    aiSettingsExamplePath: path.join(configDir, "ai_settings.example.json"),
    watchlistPath: path.join(configDir, "watchlist.json"),
    xWatchlistPath: path.join(configDir, "x_watchlist.json"),
    runtimeSettingsPath: path.join(configDir, "runtime_settings.json"),
    insightDbPath: path.join(runtimeDir, "insight.db"),
    xhsStatePath: path.join(stateDir, "xhs_monitor_state.json"),
    xStatePath: path.join(stateDir, "x_monitor_state.json"),
    xhsUserDataDir: path.join(stateDir, "xhs_chrome_user_data"),
  };
}

export function toRelativeProjectPath(rootDir: string, targetPath: string) {
  const relative = path.relative(rootDir, targetPath).replaceAll("\\", "/");
  return relative || ".";
}
