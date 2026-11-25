/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { setToast } from "@plane/blocks/toast";

const dateTime = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

/** A moment as the administrator's own computer shows it, or a dash for none. */
export const formatMoment = (value: string | null | undefined) => {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : dateTime.format(date);
};

/** What Plane's answer said went wrong, in its own words, so the administrator can act on it. */
export const errorMessage = (error: unknown, fallback = "Something went wrong. Please try again.") => {
  if (error && typeof error === "object" && "error" in error && typeof error.error === "string" && error.error) {
    return error.error;
  }
  return fallback;
};

export const showError = (title: string, error: unknown) =>
  setToast({ type: "error", title, message: errorMessage(error) });

/** What a secret dialog shows: one or more values to copy, and what to say about them. */
export type TRevealed = {
  title: string;
  intro: string;
  /** The value cannot be read again once this dialog is closed. */
  once: boolean;
  fields: { label: string; value: string; description: string }[];
};

/** Addresses as typed, one per line, without blanks or repeats. */
export const parseLines = (text: string) =>
  [...new Set(text.split(/\r?\n/).map((line) => line.trim()))].filter(Boolean);
