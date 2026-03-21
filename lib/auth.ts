/**
 * lib/auth.ts — Token-based authentication utilities for the dashboard.
 *
 * Provides HMAC-SHA256 hashing and timing-safe comparison for the
 * DASHBOARD_TOKEN authentication flow. Used by middleware.ts to validate
 * query param tokens, header tokens, and cookie-stored hashes.
 *
 * Security model: the raw token is never stored. It is hashed on first
 * use and the hash is persisted in an httpOnly cookie. Subsequent requests
 * compare the cookie hash against a freshly computed hash of DASHBOARD_TOKEN.
 */

import { createHmac, timingSafeEqual } from "crypto";

/** Cookie name used to persist the hashed dashboard token. */
export const TOKEN_COOKIE = "dashboard_token";

/** Cookie max-age in seconds (30 days). */
export const TOKEN_MAX_AGE = 30 * 24 * 60 * 60;

/**
 * Computes an HMAC-SHA256 hash of a token string.
 *
 * @param token Raw token string to hash
 * @returns Hex-encoded HMAC-SHA256 digest
 */
export function hashToken(token: string): string {
  return createHmac("sha256", token).update(token).digest("hex");
}

/**
 * Validates a provided token against DASHBOARD_TOKEN using timing-safe comparison.
 *
 * @param provided Raw token string from the request (query param or header)
 * @returns True if the provided token matches DASHBOARD_TOKEN
 * @throws Never — returns false on any mismatch or missing values
 */
export function validateToken(provided: string): boolean {
  const expected = process.env.DASHBOARD_TOKEN;
  if (!expected || !provided) return false;
  const a = Buffer.from(hashToken(provided));
  const b = Buffer.from(hashToken(expected));
  return a.length === b.length && timingSafeEqual(a, b);
}

/**
 * Validates a cookie-stored hash against the expected hash of DASHBOARD_TOKEN.
 *
 * @param cookieValue Pre-hashed token value from the dashboard_token cookie
 * @returns True if the cookie hash matches the expected hash
 * @throws Never — returns false on any mismatch or missing values
 */
export function validateCookie(cookieValue: string): boolean {
  const expected = process.env.DASHBOARD_TOKEN;
  if (!expected || !cookieValue) return false;
  const a = Buffer.from(cookieValue);
  const b = Buffer.from(hashToken(expected));
  return a.length === b.length && timingSafeEqual(a, b);
}
