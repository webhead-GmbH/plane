/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useLayoutEffect, useState } from "react";
import type { DropzoneState } from "react-dropzone";
// plane imports
import { UserOutline } from "@makeplane/propel/icons";
import { getFileURL } from "@plane/utils";

type TImagePreview = {
  file: File;
  url: string;
};

type Props = {
  dropzone: DropzoneState;
  image: File | null;
  previewAlt: string;
  value: string | null;
};

// Owns the object URL of the picked file: it is created after render, revoked when the file changes or
// the dropzone unmounts, and set in a layout effect so the preview is in place before the browser paints.
const useImagePreviewUrl = (image: File | null): string | undefined => {
  const [preview, setPreview] = useState<TImagePreview | null>(null);

  useLayoutEffect(() => {
    if (!image) return;
    const url = URL.createObjectURL(image);
    setPreview({ file: image, url });
    return () => URL.revokeObjectURL(url);
  }, [image]);

  return image && preview?.file === image ? preview.url : undefined;
};

export function ImageUploadDropzone(props: Props) {
  const { dropzone, image, previewAlt, value } = props;
  const { getRootProps, getInputProps, isDragActive, fileRejections } = dropzone;
  // derived values
  const imagePreviewUrl = useImagePreviewUrl(image);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-center gap-3">
        <div
          {...getRootProps()}
          className={`relative grid h-80 w-80 cursor-pointer place-items-center rounded-lg p-12 text-center focus:ring-2 focus:ring-accent-strong focus:ring-offset-2 focus:outline-none ${
            (image === null && isDragActive) || !value ? "border-2 border-dashed border-subtle hover:bg-surface-2" : ""
          }`}
        >
          {image !== null || (value && value !== "") ? (
            <>
              <button
                type="button"
                className="absolute top-0 right-0 z-40 translate-x-1/2 -translate-y-1/2 rounded-sm bg-surface-2 px-2 py-0.5 text-11 font-medium text-secondary"
              >
                Edit
              </button>
              <img
                src={image ? imagePreviewUrl : value ? getFileURL(value) : ""}
                alt={previewAlt}
                className="absolute top-0 left-0 h-full w-full rounded-md object-cover"
              />
            </>
          ) : (
            <div>
              <UserOutline className="mx-auto h-16 w-16 text-secondary" />
              <span className="mt-2 block text-13 font-medium text-secondary">
                {isDragActive ? "Drop image here to upload" : "Drag & drop image here"}
              </span>
            </div>
          )}

          <input {...getInputProps()} />
        </div>
      </div>
      {fileRejections.length > 0 && (
        <p className="text-13 text-danger-primary">
          {fileRejections[0].errors[0].code === "file-too-large"
            ? "The image size cannot exceed 5 MB."
            : "Please upload a file in a valid format."}
        </p>
      )}
    </div>
  );
}
