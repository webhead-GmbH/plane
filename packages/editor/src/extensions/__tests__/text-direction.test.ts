/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { Extensions, JSONContent } from "@tiptap/core";
import { Editor } from "@tiptap/core";
import { StarterKit } from "@tiptap/starter-kit";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Table, TableCell, TableHeader, TableRow } from "../table";
import { TextDirectionExtension, detectTextDirection } from "../text-direction";

describe("detectTextDirection", () => {
  it.each([
    ["Persian", "این یک متن فارسی است", "rtl"],
    ["Arabic", "هذا نص عربي", "rtl"],
    ["Hebrew", "זה טקסט בעברית", "rtl"],
    ["English", "This is an English sentence", "ltr"],
    ["German", "Das ist ein deutscher Satz mit Umlauten über Straße", "ltr"],
  ] as const)("reads %s the way it is written", (_name, text, expected) => {
    expect(detectTextDirection(text)).toBe(expected);
  });

  it("keeps a Persian sentence right to left when it opens with an English or German word", () => {
    expect(detectTextDirection("Deploy کردن پروژه به سرور انجام شد")).toBe("rtl");
    expect(detectTextDirection("Straße ها را بررسی کردم")).toBe("rtl");
  });

  it("keeps an English sentence left to right when it holds a Persian word", () => {
    expect(detectTextDirection("Please fix the کاربر issue before Friday")).toBe("ltr");
  });

  it("does not let one long English identifier outvote the Persian around it", () => {
    expect(detectTextDirection("این docker-compose.production.override.yml فایل است")).toBe("rtl");
  });

  it("gives a tie to right to left", () => {
    expect(detectTextDirection("Docker سرور")).toBe("rtl");
  });

  it("has no answer for text without words", () => {
    expect(detectTextDirection("")).toBeUndefined();
    expect(detectTextDirection("   ")).toBeUndefined();
    expect(detectTextDirection("12 ۱۲۳ 🙂 - ()")).toBeUndefined();
  });
});

let editor: Editor | undefined;
const createEditor = (content: JSONContent, extraExtensions: Extensions = []) => {
  editor = new Editor({
    element: document.createElement("div"),
    content,
    extensions: [StarterKit, TextDirectionExtension, ...extraExtensions],
  });
  return editor;
};
const view = () => editor!.view.dom;
const text = (value: string): JSONContent => ({ type: "text", text: value });
const paragraph = (value?: string): JSONContent => ({ type: "paragraph", content: value ? [text(value)] : [] });
const directions = (selector: string) =>
  [...view().querySelectorAll(selector)].map((element) => element.getAttribute("dir"));

afterEach(() => {
  editor?.destroy();
  editor = undefined;
});

describe("TextDirectionExtension", () => {
  it("gives each paragraph the direction of its own text", () => {
    createEditor({
      type: "doc",
      content: [paragraph("سلام، حال شما چطور است"), paragraph("Hello there"), paragraph("Deploy کردن پروژه انجام شد")],
    });
    expect(directions("p")).toEqual(["rtl", "ltr", "rtl"]);
  });

  it("lets an empty line follow the one before it, and a first empty line stay as it is", () => {
    createEditor({
      type: "doc",
      content: [paragraph(), paragraph("سلام"), paragraph(), paragraph("Hello"), paragraph()],
    });
    expect(directions("p")).toEqual([null, "rtl", "rtl", "ltr", "ltr"]);
  });

  it("follows the text as it is typed", () => {
    createEditor({ type: "doc", content: [paragraph("Hello")] });
    expect(directions("p")).toEqual(["ltr"]);
    editor!.commands.insertContentAt(6, " سلام دوست من و همه شما");
    expect(directions("p")).toEqual(["rtl"]);
  });

  it("lays a whole list out one way, and leaves its items to inherit", () => {
    createEditor({
      type: "doc",
      content: [
        {
          type: "bulletList",
          content: [
            { type: "listItem", content: [paragraph("اولین مورد")] },
            { type: "listItem", content: [paragraph("Docker")] },
            { type: "listItem", content: [paragraph("سومین مورد از فهرست")] },
          ],
        },
      ],
    });
    expect(directions("ul")).toEqual(["rtl"]);
    expect(directions("li, li p")).toEqual([null, null, null, null, null, null]);
  });

  it("lays a quote out as a whole too", () => {
    createEditor({ type: "doc", content: [{ type: "blockquote", content: [paragraph("نقل قول فارسی")] }] });
    expect(directions("blockquote")).toEqual(["rtl"]);
    expect(directions("blockquote p")).toEqual([null]);
  });

  it("leaves code left to right", () => {
    createEditor({
      type: "doc",
      content: [{ type: "codeBlock", content: [text("const سلام = 1")] }, paragraph("سلام")],
    });
    expect(directions("pre")).toEqual([null]);
    expect(directions("p")).toEqual(["rtl"]);
  });

  it("lets each table cell choose for itself and leaves the table as it is", () => {
    // The table's insert handlers poll on a timer that reaches for the view after the editor is gone.
    vi.useFakeTimers();
    createEditor(
      {
        type: "doc",
        content: [
          {
            type: "table",
            content: [
              {
                type: "tableRow",
                content: [
                  { type: "tableCell", content: [paragraph("نام")] },
                  { type: "tableCell", content: [paragraph("Name")] },
                ],
              },
            ],
          },
        ],
      },
      [Table, TableHeader, TableCell, TableRow]
    );
    vi.useRealTimers();
    expect(directions("table, tr, td")).toEqual([null, null, null, null]);
    expect(directions("td p")).toEqual(["rtl", "ltr"]);
  });

  it("stores nothing: the document comes out as it went in", () => {
    createEditor({ type: "doc", content: [paragraph("سلام")] });
    expect(editor!.getHTML()).not.toContain("dir=");
  });
});
