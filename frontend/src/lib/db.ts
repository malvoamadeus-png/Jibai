import "server-only";

import Database from "better-sqlite3";
import { existsSync } from "node:fs";
import path from "node:path";

let dbInstance: Database.Database | null | undefined;
let dbInstancePath: string | null = null;

export function getDbPath() {
  if (process.env.INSIGHT_DB_PATH) {
    return path.resolve(process.env.INSIGHT_DB_PATH);
  }

  const candidates = [
    path.resolve(process.cwd(), "data", "runtime", "insight.db"),
    path.resolve(process.cwd(), "..", "data", "runtime", "insight.db"),
  ];

  return candidates.find((candidate) => existsSync(candidate)) ?? candidates[1];
}

export function getDb() {
  const dbPath = getDbPath();
  if (dbInstance !== undefined && dbInstancePath === dbPath) return dbInstance;
  if (!existsSync(dbPath)) {
    return null;
  }
  const db = new Database(dbPath, {
    readonly: true,
    fileMustExist: true,
  });
  db.pragma("journal_mode = WAL");
  dbInstance = db;
  dbInstancePath = dbPath;
  return dbInstance;
}

export function withDb<T>(run: (db: Database.Database) => T, fallback: T) {
  const db = getDb();
  if (!db) return fallback;
  try {
    return run(db);
  } catch {
    return fallback;
  }
}
