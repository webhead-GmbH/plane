/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { Editor } from "@tiptap/core";
import { v4 as uuidv4 } from "uuid";
import { Plugin, PluginKey } from "@tiptap/pm/state";
// constants
import { ACCEPTED_ATTACHMENT_MIME_TYPES, ACCEPTED_IMAGE_MIME_TYPES } from "@/constants/config";
import { CORE_EXTENSIONS } from "@/constants/extension";
// types
import type { TEditorCommands, TExtensions } from "@/types";

type Props = {
  disabledExtensions?: TExtensions[];
  flaggedExtensions?: TExtensions[];
  editor: Editor;
  onUnsupportedFiles?: (files: File[]) => void;
  uploadAttachment?: TUploadAttachment;
};

type TUploadAttachment = (file: File) => Promise<{ name: string; url: string }>;

const IMAGE_MIME_TYPES = new Set(ACCEPTED_IMAGE_MIME_TYPES);
const ATTACHMENT_MIME_TYPES = new Set(ACCEPTED_ATTACHMENT_MIME_TYPES);

// Only images can be added to the text; anything else would vanish without a word
const reportUnsupportedFiles = (
  files: File[],
  disabledExtensions: TExtensions[] | undefined,
  onUnsupportedFiles: ((files: File[]) => void) | undefined,
  uploadAttachment?: TUploadAttachment
) => {
  // A host that keeps any file takes them all; nothing is turned away.
  if (uploadAttachment) return;
  const imagesDisabled = !!disabledExtensions?.includes("image");
  const unsupported = files.filter((file) => imagesDisabled || !IMAGE_MIME_TYPES.has(file.type));
  if (unsupported.length) onUnsupportedFiles?.(unsupported);
};

export const DropHandlerPlugin = (props: Props): Plugin => {
  const { disabledExtensions, flaggedExtensions, editor, onUnsupportedFiles, uploadAttachment } = props;
  const isAccepted = (file: File) =>
    !!uploadAttachment || IMAGE_MIME_TYPES.has(file.type) || ATTACHMENT_MIME_TYPES.has(file.type);

  return new Plugin({
    key: new PluginKey("drop-handler-plugin"),
    props: {
      handlePaste: (view, event) => {
        if (
          editor.isEditable &&
          event.clipboardData &&
          event.clipboardData.files &&
          event.clipboardData.files.length > 0
        ) {
          event.preventDefault();
          const files = Array.from(event.clipboardData.files);
          const acceptedFiles = files.filter(isAccepted);
          reportUnsupportedFiles(files, disabledExtensions, onUnsupportedFiles, uploadAttachment);

          if (acceptedFiles.length) {
            const pos = view.state.selection.from;
            insertFilesSafely({
              disabledExtensions,
              flaggedExtensions,
              editor,
              files: acceptedFiles,
              initialPos: pos,
              event: "drop",
              uploadAttachment,
            });
          }
          return true;
        }
        return false;
      },
      handleDrop: (view, event, _slice, moved) => {
        if (
          editor.isEditable &&
          !moved &&
          event.dataTransfer &&
          event.dataTransfer.files &&
          event.dataTransfer.files.length > 0
        ) {
          event.preventDefault();
          const files = Array.from(event.dataTransfer.files);
          const acceptedFiles = files.filter(isAccepted);
          reportUnsupportedFiles(files, disabledExtensions, onUnsupportedFiles, uploadAttachment);

          if (acceptedFiles.length) {
            const coordinates = view.posAtCoords({
              left: event.clientX,
              top: event.clientY,
            });

            if (coordinates) {
              const pos = coordinates.pos;
              insertFilesSafely({
                disabledExtensions,
                flaggedExtensions,
                editor,
                files: acceptedFiles,
                initialPos: pos,
                event: "drop",
                uploadAttachment,
              });
            }
            return true;
          }
        }
        return false;
      },
    },
  });
};

type InsertFilesSafelyArgs = {
  disabledExtensions?: TExtensions[];
  flaggedExtensions?: TExtensions[];
  editor: Editor;
  event: "insert" | "drop";
  files: File[];
  initialPos: number;
  type?: Extract<TEditorCommands, "attachment" | "image">;
  uploadAttachment?: TUploadAttachment;
};

export const insertFilesSafely = async (args: InsertFilesSafelyArgs) => {
  const { disabledExtensions, editor, event, files, initialPos, type, uploadAttachment } = args;
  let pos = initialPos;
  const imagesAllowed = !disabledExtensions?.includes("image");

  for (const file of files) {
    // safe insertion
    const docSize = editor.state.doc.content.size;
    pos = Math.min(pos, docSize);

    let fileType: "image" | "attachment" | null = null;

    try {
      if (type) {
        if (["image", "attachment"].includes(type)) fileType = type;
        else throw new Error("Wrong file type passed");
      } else {
        if (imagesAllowed && IMAGE_MIME_TYPES.has(file.type)) fileType = "image";
        else if (uploadAttachment || ATTACHMENT_MIME_TYPES.has(file.type)) fileType = "attachment";
      }
      // insert file depending on the type at the current position
      if (fileType === "image" && imagesAllowed) {
        editor.commands.insertImageComponent({
          file,
          pos,
          event,
        });
      } else if (fileType === "attachment" && uploadAttachment) {
        void insertAttachmentLink(editor, file, pos, uploadAttachment);
      }
    } catch (error) {
      console.error(`Error while ${event}ing file:`, error);
    }

    // Move to the next position
    pos += 1;
  }
};

// A link to a file still on its way carries this in its address until it arrives.
const UPLOADING_LINK = "#uploading-";

/** Where the link carrying this placeholder address is now, however the text has moved since. */
const findPlaceholder = (editor: Editor, href: string) => {
  const linkType = editor.schema.marks[CORE_EXTENSIONS.CUSTOM_LINK];
  let found: { from: number; to: number } | null = null;
  editor.state.doc.descendants((node, nodePos) => {
    if (found) return false;
    if (node.isText && node.marks.some((mark) => mark.type === linkType && mark.attrs.href === href)) {
      found = { from: nodePos, to: nodePos + node.nodeSize };
      return false;
    }
    return true;
  });
  return found as { from: number; to: number } | null;
};

/**
 * Put a link to the file where it was dropped: at once, under the file's name and
 * going nowhere, and pointing at the file itself once the host has it. Plain names,
 * no emoji: the emoji extension would turn one into a node of its own, outside the
 * link, and leave it behind when the link is swapped. If the upload fails, the
 * placeholder goes and the host says why.
 */
export const insertAttachmentLink = async (
  editor: Editor,
  file: File,
  pos: number,
  uploadAttachment: TUploadAttachment
) => {
  const linkType = editor.schema.marks[CORE_EXTENSIONS.CUSTOM_LINK];
  if (!linkType) return;
  const placeholder = `${UPLOADING_LINK}${uuidv4()}`;
  editor
    .chain()
    .insertContentAt(pos, [
      { type: "text", text: file.name, marks: [{ type: linkType.name, attrs: { href: placeholder } }] },
      { type: "text", text: " " },
    ])
    .run();

  let uploaded: { name: string; url: string } | null = null;
  try {
    uploaded = await uploadAttachment(file);
  } catch {
    uploaded = null;
  }
  if (editor.isDestroyed) return;
  const where = findPlaceholder(editor, placeholder);
  if (!where) return;
  const transaction = editor.state.tr;
  if (uploaded) {
    transaction.replaceWith(
      where.from,
      where.to,
      editor.schema.text(uploaded.name, [
        linkType.create({ href: uploaded.url, target: "_blank", rel: "noopener noreferrer nofollow" }),
      ])
    );
  } else {
    transaction.delete(where.from, where.to);
  }
  editor.view.dispatch(transaction);
};
