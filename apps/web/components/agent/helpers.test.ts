/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { handleLabel, providerLabel, safeRedirectUrl, scopeKey } from "./helpers";

describe("safeRedirectUrl", () => {
  it("follows an https address with its query, which is where the code travels", () => {
    expect(safeRedirectUrl("https://bot.example.com/plane/callback?code=abc&state=s1")).toBe(
      "https://bot.example.com/plane/callback?code=abc&state=s1"
    );
  });

  it("follows plain http, which the server only registers for localhost", () => {
    expect(safeRedirectUrl("http://localhost:9001/plane/callback?code=abc")).toBe(
      "http://localhost:9001/plane/callback?code=abc"
    );
  });

  it.each([
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "file:///etc/passwd",
    "ftp://example.com/",
    "tg://resolve?domain=bot",
    "//evil.example.com/callback",
    "/relative/path",
    "evil.example.com",
    "",
  ])("refuses %j", (value) => {
    expect(safeRedirectUrl(value)).toBeNull();
  });

  it("refuses an address with whitespace or control characters in it", () => {
    expect(safeRedirectUrl("java\tscript:alert(1)")).toBeNull();
    expect(safeRedirectUrl("https://example.com/\nSet-Cookie: a=b")).toBeNull();
    expect(safeRedirectUrl(" https://example.com/")).toBeNull();
  });

  it("refuses credentials in the address, which is how a link is made to look like another site", () => {
    expect(safeRedirectUrl("https://plane.example.com@evil.example.com/")).toBeNull();
    expect(safeRedirectUrl("https://user:pass@example.com/")).toBeNull();
  });

  it("refuses anything that is not a string", () => {
    expect(safeRedirectUrl(undefined)).toBeNull();
    expect(safeRedirectUrl(null)).toBeNull();
    expect(safeRedirectUrl({ href: "https://example.com/" })).toBeNull();
  });

  it("refuses an address too long to be one the server built", () => {
    expect(safeRedirectUrl(`https://example.com/${"a".repeat(5000)}`)).toBeNull();
  });
});

describe("scopeKey", () => {
  it("turns the namespace separator into something a key can hold", () => {
    expect(scopeKey("time:read")).toBe("time_read");
    expect(scopeKey("work_items:read")).toBe("work_items_read");
    expect(scopeKey("profile")).toBe("profile");
  });

  it("cannot be made to address another part of the translations", () => {
    expect(scopeKey("a.b:c")).toBe("a_b_c");
    expect(scopeKey("../../common")).toBe("_common");
  });
});

describe("providerLabel", () => {
  it("capitalises the name the app sent", () => {
    expect(providerLabel("telegram")).toBe("Telegram");
    expect(providerLabel(" slack ")).toBe("Slack");
  });

  it("is empty for nothing", () => {
    expect(providerLabel("")).toBe("");
    expect(providerLabel("   ")).toBe("");
  });
});

describe("handleLabel", () => {
  it("puts one @ in front", () => {
    expect(handleLabel("mallory")).toBe("@mallory");
    expect(handleLabel("@mallory")).toBe("@mallory");
    expect(handleLabel("@@mallory")).toBe("@mallory");
  });

  it("is empty when there is no username", () => {
    expect(handleLabel("")).toBe("");
    expect(handleLabel("@")).toBe("");
  });
});
