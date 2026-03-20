import { createHmac, timingSafeEqual } from "crypto";

export const TOKEN_COOKIE = "dashboard_token";
export const TOKEN_MAX_AGE = 30 * 24 * 60 * 60; // 30 days in seconds

export function hashToken(token: string): string {
  return createHmac("sha256", token).update(token).digest("hex");
}

export function validateToken(provided: string): boolean {
  const expected = process.env.DASHBOARD_TOKEN;
  if (!expected || !provided) return false;
  const a = Buffer.from(hashToken(provided));
  const b = Buffer.from(hashToken(expected));
  return a.length === b.length && timingSafeEqual(a, b);
}

export function validateCookie(cookieValue: string): boolean {
  const expected = process.env.DASHBOARD_TOKEN;
  if (!expected || !cookieValue) return false;
  const a = Buffer.from(cookieValue);
  const b = Buffer.from(hashToken(expected));
  return a.length === b.length && timingSafeEqual(a, b);
}
