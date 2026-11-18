/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Extension } from "@tiptap/core";
import type { Node as ProseMirrorNode } from "@tiptap/pm/model";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
// constants
import { CORE_EXTENSIONS } from "@/constants/extension";

export type TTextDirection = "ltr" | "rtl";

const LETTER = /\p{L}/u;
const RTL_LETTER = /[\p{Script=Arabic}\p{Script=Hebrew}\p{Script=Syriac}\p{Script=Thaana}]/u;

/**
 * Which way a piece of text reads, or undefined when it holds no words (empty, digits, emoji).
 *
 * Counted in words, by each word's first letter, and not taken from the first letter of the text as
 * `dir="auto"` does: a Persian sentence that opens with an English or German word ("Deploy کردن پروژه
 * انجام شد") would then be laid out left to right and read out of order. A long English identifier
 * does not outvote the Persian around it either, as it would counting letters.
 *
 * Right to left wins a tie: the people who need this are the ones writing in right-to-left scripts, and
 * a two-word phrase of one Persian and one English word is theirs.
 */
export const detectTextDirection = (text: string): TTextDirection | undefined => {
  let rtl = 0;
  let ltr = 0;
  for (const word of text.split(/\s+/)) {
    const letter = LETTER.exec(word)?.[0];
    if (!letter) continue;
    if (RTL_LETTER.test(letter)) rtl++;
    else ltr++;
  }
  if (rtl === 0 && ltr === 0) return undefined;
  return rtl >= ltr ? "rtl" : "ltr";
};

// Lists, quotes and callouts take one direction as a whole: the side their bullets, indent and bar are
// on is theirs, not each line's, and a nested list would otherwise indent the other way.
const CONTAINERS = new Set<string>([
  CORE_EXTENSIONS.BLOCKQUOTE,
  CORE_EXTENSIONS.BULLET_LIST,
  CORE_EXTENSIONS.ORDERED_LIST,
  CORE_EXTENSIONS.TASK_LIST,
  CORE_EXTENSIONS.CALLOUT,
]);

// Nodes are immutable and shared between document versions, so a block that did not change keeps its answer.
const known = new WeakMap<ProseMirrorNode, TTextDirection | null>();

const directionOf = (node: ProseMirrorNode): TTextDirection | undefined => {
  let direction = known.get(node);
  if (direction === undefined) {
    direction = detectTextDirection(node.textBetween(0, node.content.size, " ", " ")) ?? null;
    known.set(node, direction);
  }
  return direction ?? undefined;
};

/** The direction to give each block of a document, as node decorations. */
export const textDirectionDecorations = (doc: ProseMirrorNode): Decoration[] => {
  const decorations: Decoration[] = [];

  const visit = (parent: ProseMirrorNode, start: number) => {
    // A block with no words of its own (an empty line, a number) goes the way the one before it did, so the
    // caret does not jump to the other side when somebody presses Enter in the middle of Persian text.
    let previous: TTextDirection | undefined;
    parent.forEach((node, offset) => {
      // Images, embeds and rules are not text, and code reads left to right whatever it says.
      if (!node.isBlock || node.isAtom || node.type.name === CORE_EXTENSIONS.CODE_BLOCK) return;
      const position = start + offset;

      if (node.isTextblock || CONTAINERS.has(node.type.name)) {
        const direction = directionOf(node) ?? previous;
        if (direction) {
          decorations.push(Decoration.node(position, position + node.nodeSize, { dir: direction }));
          previous = direction;
        }
        return;
      }

      // Tables and their cells keep their layout; the blocks inside each cell choose for themselves.
      visit(node, position + 1);
    });
  };

  visit(doc, 0);
  return decorations;
};

/**
 * Lays each block out in the direction its text reads, so Persian, Arabic and Hebrew are right to left
 * and English or German stay left to right, in the same document and while somebody is typing. Only the
 * view is decorated: nothing is stored, so text written before this existed is laid out the same way.
 */
export const TextDirectionExtension = Extension.create({
  name: CORE_EXTENSIONS.TEXT_DIRECTION,

  addProseMirrorPlugins() {
    let current: { doc: ProseMirrorNode; decorations: DecorationSet } | undefined;

    return [
      new Plugin({
        key: new PluginKey(CORE_EXTENSIONS.TEXT_DIRECTION),
        props: {
          // Asked for on every selection change too; the document is what the answer depends on.
          decorations: ({ doc }) => {
            if (current?.doc !== doc) {
              current = { doc, decorations: DecorationSet.create(doc, textDirectionDecorations(doc)) };
            }
            return current.decorations;
          },
        },
      }),
    ];
  },
});
