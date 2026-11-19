/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import path from "node:path";
import { defineConfig } from "vitest/config";

// A config of its own, so vitest does not load vite.config.ts and with it the React Router plugin,
// which wants a whole app around it. Tests here are for the pure logic that sits beside components.
export default defineConfig({
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, ".") },
  },
  test: {
    environment: "node",
    include: ["**/*.test.ts"],
    exclude: ["node_modules/**", "build/**", ".react-router/**"],
  },
});
