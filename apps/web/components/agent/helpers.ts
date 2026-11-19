/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/**
 * The address the server says to send the person on to after they have decided, if it is safe to follow.
 *
 * Only http(s). The server only ever sends back an address the app registered, but this is the line
 * between a page that sends people somewhere and a page that can run script (`javascript:`) or open
 * a file or data URL, so it does not rely on that.
 */
export function safeRedirectUrl(value: unknown): string | null {
  if (typeof value !== "string" || value === "" || value.length > 4096) return null;
  // Control characters (a tab or newline in the scheme is how a check like this gets sidestepped)
  // and whitespace have no place in an address the server built.
  // oxlint-disable-next-line no-control-regex
  if (/[\u0000- \u007f]/.test(value)) return null;
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return null;
  }
  if (url.protocol !== "https:" && url.protocol !== "http:") return null;
  if (!url.hostname || url.username || url.password) return null;
  return url.toString();
}

/**
 * The part of a translation key that stands for a scope.
 *
 * A scope id such as `time:read` cannot be a key segment as it is: `:` separates the namespace from
 * the key. Anything that is not a letter or digit becomes `_`, which also means an id the server
 * invents later can never address a key it should not.
 */
export function scopeKey(scopeId: string): string {
  return scopeId.toLowerCase().replace(/[^a-z0-9]+/g, "_");
}

/** A service name as it is shown: the app sends `telegram`, the person reads `Telegram`. */
export function providerLabel(provider: string): string {
  const trimmed = provider.trim();
  if (!trimmed) return "";
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
}

/** A username as it is written on the service itself: with the `@` in front, once. */
export function handleLabel(username: string): string {
  const trimmed = username.trim().replace(/^@+/, "");
  return trimmed ? `@${trimmed}` : "";
}
