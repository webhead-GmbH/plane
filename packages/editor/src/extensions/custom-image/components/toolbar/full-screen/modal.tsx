/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { AddOutline, CloseOutline, DownloadOutline, MinusOutline, NewTabOutline } from "@makeplane/propel/icons";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactDOM from "react-dom";
// plane imports
import { cn } from "@plane/utils";

const MIN_ZOOM = 0.5;
const MAX_ZOOM = 2;
const ZOOM_SPEED = 0.05;
const ZOOM_STEPS = [0.5, 1, 1.5, 2];
// an arrow key moves the image as far as dragging it this many pixels does
const PAN_STEP = 50;
const PAN_KEY_DIRECTIONS: Partial<Record<string, { x: number; y: number }>> = {
  ArrowUp: { x: 0, y: -1 },
  ArrowDown: { x: 0, y: 1 },
  ArrowLeft: { x: -1, y: 0 },
  ArrowRight: { x: 1, y: 0 },
};

// the image can only be moved around while its zoomed size overflows the viewport
const canPanImage = (imageFrame: HTMLElement, magnification: number) => {
  const imgWidth = imageFrame.offsetWidth * magnification;
  const imgHeight = imageFrame.offsetHeight * magnification;
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;

  return imgWidth > viewportWidth || imgHeight > viewportHeight;
};

type Props = {
  aspectRatio: number;
  downloadSrc: string;
  isFullScreenEnabled: boolean;
  isTouchDevice: boolean;
  src: string;
  toggleFullScreenMode: (val: boolean) => void;
  width: string;
};

function ImageFullScreenModalWithoutPortal(props: Props) {
  const { aspectRatio, isFullScreenEnabled, isTouchDevice, downloadSrc, src, toggleFullScreenMode, width } = props;
  // refs
  const dragStart = useRef({ x: 0, y: 0 });
  const dragOffset = useRef({ x: 0, y: 0 });

  const [magnification, setMagnification] = useState<number>(1);
  const [initialMagnification, setInitialMagnification] = useState(1);
  const [isDragging, setIsDragging] = useState(false);
  const modalRef = useRef<HTMLDivElement>(null);
  // the button that holds the image: it is what gets zoomed and moved around
  const imageFrameRef = useRef<HTMLButtonElement | null>(null);
  // latest requested zoom, so zoom actions fired before the next render build on each other
  const magnificationRef = useRef(1);

  const widthInNumber = useMemo(() => {
    if (!width) return 0;
    return Number(width.replace("px", ""));
  }, [width]);

  const updateMagnification = useCallback((value: number) => {
    magnificationRef.current = value;
    setMagnification(value);
  }, []);

  const setImageFrameRef = useCallback(
    (node: HTMLButtonElement | null) => {
      if (!node || !isFullScreenEnabled) return;

      imageFrameRef.current = node;

      const viewportWidth = window.innerWidth * 0.9;
      const viewportHeight = window.innerHeight * 0.75;
      const imageWidth = widthInNumber;
      const imageHeight = imageWidth / aspectRatio;

      const widthRatio = viewportWidth / imageWidth;
      const heightRatio = viewportHeight / imageHeight;

      setInitialMagnification(Math.min(widthRatio, heightRatio));
      updateMagnification(1);

      // Reset image position
      node.style.left = "0px";
      node.style.top = "0px";
    },
    [isFullScreenEnabled, widthInNumber, aspectRatio, updateMagnification]
  );

  const handleClose = useCallback(() => {
    if (isDragging) return;
    toggleFullScreenMode(false);
    updateMagnification(1);
    setInitialMagnification(1);
  }, [isDragging, toggleFullScreenMode, updateMagnification]);

  const handleMagnification = useCallback(
    (direction: "increase" | "decrease") => {
      const prev = magnificationRef.current;
      // Find the appropriate target zoom level based on current magnification
      let targetZoom: number;
      if (direction === "increase") {
        targetZoom = ZOOM_STEPS.find((step) => step > prev) ?? MAX_ZOOM;
      } else {
        // Reverse the array to find the next lower step
        targetZoom = [...ZOOM_STEPS].reverse().find((step) => step < prev) ?? MIN_ZOOM;
      }

      // Reset position when zoom matches initial magnification
      if (targetZoom === 1 && imageFrameRef.current) {
        imageFrameRef.current.style.left = "0px";
        imageFrameRef.current.style.top = "0px";
      }

      updateMagnification(targetZoom);
    },
    [updateMagnification]
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape" || e.key === "+" || e.key === "=" || e.key === "-") {
        e.preventDefault();
        e.stopPropagation();

        if (e.key === "Escape") handleClose();
        if (e.key === "+" || e.key === "=") handleMagnification("increase");
        if (e.key === "-") handleMagnification("decrease");
      }
    },
    [handleClose, handleMagnification]
  );

  const handleMouseDown = (e: React.MouseEvent) => {
    if (!imageFrameRef.current) return;

    if (canPanImage(imageFrameRef.current, magnification)) {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(true);
      dragStart.current = { x: e.clientX, y: e.clientY };
      dragOffset.current = {
        x: parseInt(imageFrameRef.current.style.left || "0"),
        y: parseInt(imageFrameRef.current.style.top || "0"),
      };
    }
  };

  // arrow keys move the image the way dragging it does
  const handlePanKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>) => {
    const direction = PAN_KEY_DIRECTIONS[e.key];
    const imageFrame = e.currentTarget;
    if (!direction || e.altKey || e.ctrlKey || e.metaKey || !canPanImage(imageFrame, magnification)) return;

    e.preventDefault();
    e.stopPropagation();
    // Apply the scale factor to the movement, as dragging does
    imageFrame.style.left = `${parseFloat(imageFrame.style.left || "0") + (direction.x * PAN_STEP) / magnification}px`;
    imageFrame.style.top = `${parseFloat(imageFrame.style.top || "0") + (direction.y * PAN_STEP) / magnification}px`;
  };

  const handleMouseMove = useCallback(
    (e: MouseEvent) => {
      if (!isDragging || !imageFrameRef.current) return;

      const dx = e.clientX - dragStart.current.x;
      const dy = e.clientY - dragStart.current.y;

      // Apply the scale factor to the drag movement
      const scaledDx = dx / magnification;
      const scaledDy = dy / magnification;

      imageFrameRef.current.style.left = `${dragOffset.current.x + scaledDx}px`;
      imageFrameRef.current.style.top = `${dragOffset.current.y + scaledDy}px`;
    },
    [isDragging, magnification]
  );

  const handleMouseUp = useCallback(() => {
    if (!isDragging || !imageFrameRef.current) return;
    setIsDragging(false);
  }, [isDragging]);

  const handleWheel = useCallback(
    (e: WheelEvent) => {
      if (!imageFrameRef.current || !isFullScreenEnabled) return;

      e.preventDefault();

      // Handle pinch-to-zoom
      if (e.ctrlKey || e.metaKey) {
        const delta = e.deltaY;
        const newZoom = magnificationRef.current * (1 - delta * ZOOM_SPEED);
        const clampedZoom = Math.min(Math.max(newZoom, MIN_ZOOM), MAX_ZOOM);

        // Reset position when zoom matches initial magnification
        if (clampedZoom === 1 && imageFrameRef.current) {
          imageFrameRef.current.style.left = "0px";
          imageFrameRef.current.style.top = "0px";
        }

        updateMagnification(clampedZoom);
        return;
      }
    },
    [isFullScreenEnabled, updateMagnification]
  );

  // Event listeners
  useEffect(() => {
    if (!isFullScreenEnabled) return;

    document.addEventListener("keydown", handleKeyDown);
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    window.addEventListener("wheel", handleWheel, { passive: false });

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
      window.removeEventListener("wheel", handleWheel);
    };
  }, [isFullScreenEnabled, handleKeyDown, handleMouseMove, handleMouseUp, handleWheel]);

  if (!isFullScreenEnabled) return null;

  return (
    <div
      className={cn("pointer-events-none fixed inset-0 z-50 size-full bg-black/90 opacity-0 transition-opacity", {
        "editor-image-full-screen-modal pointer-events-auto opacity-100": isFullScreenEnabled,
        "cursor-default": !isDragging,
        "cursor-grabbing": isDragging,
      })}
      role="dialog"
      aria-modal="true"
      aria-label="Fullscreen image viewer"
    >
      <div
        ref={modalRef}
        onMouseDown={(e) => e.target === modalRef.current && handleClose()}
        className="relative grid size-full place-items-center overflow-hidden"
      >
        <button
          type="button"
          onClick={handleClose}
          className="absolute top-10 right-10 grid size-8 place-items-center"
          aria-label="Close image viewer"
        >
          <CloseOutline className="size-8 text-white/60 transition-colors hover:text-white" />
        </button>
        <button
          ref={setImageFrameRef}
          type="button"
          onMouseDown={handleMouseDown}
          onKeyDown={handlePanKeyDown}
          className="cursor-[inherit] rounded-lg"
          style={{
            position: "relative",
            transform: `scale(${magnification})`,
            transformOrigin: "center",
            transition: "transform 0.2s ease",
          }}
          aria-label="Pan image"
          aria-keyshortcuts="ArrowUp ArrowDown ArrowLeft ArrowRight"
        >
          <img
            src={src}
            alt=""
            className="read-only-image block rounded-lg"
            style={{
              width: `${widthInNumber * initialMagnification}px`,
              maxWidth: "none",
              maxHeight: "none",
              aspectRatio,
              transition: "width 0.2s ease",
            }}
          />
        </button>
        <div className="fixed bottom-10 left-1/2 flex -translate-x-1/2 items-center justify-center gap-1 divide-x divide-subtle-1 rounded-md border border-subtle-1 bg-black py-2">
          <div className="flex items-center">
            <button
              type="button"
              onClick={(e) => {
                if (isTouchDevice) {
                  e.preventDefault();
                  e.stopPropagation();
                }
                handleMagnification("decrease");
              }}
              className="grid size-6 place-items-center text-white/60 transition-colors duration-200 hover:text-white disabled:text-white/30"
              disabled={magnification <= MIN_ZOOM}
              aria-label="Zoom out"
            >
              <MinusOutline className="size-4" />
            </button>
            <span className="w-12 text-center text-13 text-white">{Math.round(100 * magnification)}%</span>
            <button
              type="button"
              onClick={(e) => {
                if (isTouchDevice) {
                  e.preventDefault();
                  e.stopPropagation();
                }
                handleMagnification("increase");
              }}
              className="grid size-6 place-items-center text-white/60 transition-colors duration-200 hover:text-white disabled:text-white/30"
              disabled={magnification >= MAX_ZOOM}
              aria-label="Zoom in"
            >
              <AddOutline className="size-4" />
            </button>
          </div>
          {!isTouchDevice && (
            <button
              type="button"
              onClick={() => window.open(downloadSrc, "_blank")}
              className="grid size-8 flex-shrink-0 place-items-center text-white/60 transition-colors duration-200 hover:text-white"
              aria-label="Download image"
            >
              <DownloadOutline className="size-4" />
            </button>
          )}
          {!isTouchDevice && (
            <button
              type="button"
              onClick={() => window.open(src, "_blank")}
              className="grid size-8 flex-shrink-0 place-items-center text-white/60 transition-colors duration-200 hover:text-white"
              aria-label="Open image in new tab"
            >
              <NewTabOutline className="size-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export function ImageFullScreenModal(props: Props) {
  let modal = <ImageFullScreenModalWithoutPortal {...props} />;
  const portal = document.querySelector("#editor-portal");
  if (portal) {
    modal = ReactDOM.createPortal(modal, portal);
  } else {
    console.warn("Portal element #editor-portal not found. Rendering in document.body");
    if (typeof document !== "undefined" && document.body) {
      modal = ReactDOM.createPortal(modal, document.body);
    }
  }
  return modal;
}
