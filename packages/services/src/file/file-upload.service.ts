/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import axios from "axios";
// api service
import { APIService } from "../api.service";
import { toFileUploadError } from "./upload-error";

/**
 * Service class for handling file upload operations
 * Handles file uploads
 * @extends {APIService}
 */
export class FileUploadService extends APIService {
  private cancelSource: any;

  constructor() {
    super("");
  }

  /**
   * Uploads a file to the specified signed URL
   * @param {string} url - The URL to upload the file to
   * @param {FormData} data - The form data to upload
   * @returns {Promise<void>} Promise resolving to void
   * @throws {FileUploadError} Why storage did not take the file, including a cancelled upload
   */
  async uploadFile(url: string, data: FormData): Promise<void> {
    // oxlint-disable-next-line import/no-named-as-default-member -- CancelToken is accessed via the default export at runtime
    this.cancelSource = axios.CancelToken.source();
    return this.post(url, data, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
      cancelToken: this.cancelSource.token,
      withCredentials: false,
    })
      .then((response) => response?.data)
      .catch((error) => {
        throw toFileUploadError(error, "upload");
      });
  }

  /**
   * Cancels the upload
   */
  cancelUpload() {
    this.cancelSource?.cancel("Upload canceled");
  }
}
