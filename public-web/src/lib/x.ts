import { z } from "zod";

const usernamePattern = /^[A-Za-z0-9_]{1,15}$/;
const reservedPaths = new Set([
  "home",
  "explore",
  "i",
  "search",
  "messages",
  "notifications",
  "settings",
  "tos",
  "privacy",
  "compose",
]);

export function normalizeXUsername(value: string) {
  let raw = value.trim();
  if (!raw) throw new Error("X account cannot be empty.");
  if (raw.startsWith("@")) raw = raw.slice(1);
  if (/^https?:\/\//i.test(raw)) {
    const url = new URL(raw);
    if (!["x.com", "www.x.com", "twitter.com", "www.twitter.com"].includes(url.hostname.toLowerCase())) {
      throw new Error("Only x.com or twitter.com profile URLs are supported.");
    }
    const parts = url.pathname.split("/").filter(Boolean);
    if (parts.length !== 1) throw new Error("Use a direct X profile URL.");
    raw = parts[0].replace(/^@/, "");
  }
  const username = raw.replace(/^@/, "").replace(/\/$/, "");
  if (reservedPaths.has(username.toLowerCase()) || !usernamePattern.test(username)) {
    throw new Error("Invalid X username.");
  }
  return username.toLowerCase();
}

export function profileUrlForUsername(username: string) {
  return `https://x.com/${normalizeXUsername(username)}`;
}

export const submitAccountSchema = z.object({
  account: z.string().trim().min(1).max(200),
});
