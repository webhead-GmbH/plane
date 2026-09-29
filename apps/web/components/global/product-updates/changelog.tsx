/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState, useEffect, useRef } from "react";
import { observer } from "mobx-react";
// plane imports
import { Loader } from "@plane/blocks/skeleton";
import { useTranslation } from "@plane/i18n";
// hooks
import { ProductUpdatesFallback } from "@/components/global/product-updates/fallback";
import { useInstance } from "@/hooks/store/use-instance";

export const ProductUpdatesChangelog = observer(function ProductUpdatesChangelog() {
  // plane hooks
  const { t } = useTranslation();
  // refs
  const isLoadingRef = useRef(true);
  // states
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  // store hooks
  const { config } = useInstance();
  // derived values
  const changeLogUrl = config?.instance_changelog_url;
  const shouldShowFallback = !changeLogUrl || changeLogUrl === "" || hasError;

  // timeout fallback - if iframe doesn't load within 15 seconds, show error
  useEffect(() => {
    if (!changeLogUrl || changeLogUrl === "") {
      setIsLoading(false);
      isLoadingRef.current = false;
      return;
    }

    setIsLoading(true);
    setHasError(false);
    isLoadingRef.current = true;

    const timeoutId = setTimeout(() => {
      if (isLoadingRef.current) {
        setHasError(true);
        setIsLoading(false);
        isLoadingRef.current = false;
      }
    }, 15000); // 15 second timeout

    return () => {
      clearTimeout(timeoutId);
    };
  }, [changeLogUrl]);

  const handleIframeLoad = () => {
    setTimeout(() => {
      isLoadingRef.current = false;
      setIsLoading(false);
    }, 1000);
  };

  const handleIframeError = () => {
    isLoadingRef.current = false;
    setHasError(true);
    setIsLoading(false);
  };

  // Show fallback if URL is missing, empty, or iframe failed to load
  if (shouldShowFallback) {
    return (
      <ProductUpdatesFallback
        description="We're having trouble fetching the updates. Please visit our changelog to view the latest updates."
        variant={config?.is_self_managed ? "self-managed" : "cloud"}
      />
    );
  }

  return (
    <div className="relative flex h-[550px] flex-col overflow-hidden">
      {isLoading && (
        <Loader className="absolute inset-0 flex h-full w-full flex-col items-center justify-center gap-3">
          <Loader.Item height="95%" width="95%" />
        </Loader>
      )}
      {/* The changelog is a page on another site (the images point INSTANCE_CHANGELOG_URL at
          sites.plane.so) that renders itself in the browser, so it needs its scripts and its own
          origin for storage and its own requests. Scripts plus same-origin only lets a page lift its
          sandbox when it shares this page's origin; this one does not, so what remains holds: it
          cannot navigate the app, submit forms or open dialogs, and its links open in new tabs. */}
      <iframe
        src={changeLogUrl}
        sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox"
        className={`h-full w-full ${isLoading ? "opacity-0" : "opacity-100"} transition-opacity duration-200`}
        title={t("whats_new")}
        onLoad={handleIframeLoad}
        onError={handleIframeError}
      />
    </div>
  );
});
