/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { RefObject } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Clock, Square } from "lucide-react";
import { Button } from "@makeplane/propel/components/button";
import { Icon } from "@makeplane/propel/components/icon";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import { useTranslation } from "@plane/i18n";
import type { TIssueWorkLog } from "@plane/types";
import { cn, renderFormattedDate, renderFormattedTime } from "@plane/utils";
// components
import { AppSidebarItem } from "@/components/sidebar/sidebar-item";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// local imports
import { formatElapsed } from "./utils";

const ACTIVE_TIMER_REFRESH_MS = 30_000;

/**
 * A timer can also start or stop outside this tab — in another tab, or in the CRM, which mirrors its
 * timers into Plane — so the running timer is re-read on coming back to the tab and at an interval
 * while the tab is in view.
 */
function useActiveTimerRefresh(slug: string | undefined, refresh: (workspaceSlug: string) => Promise<void>) {
  useEffect(() => {
    if (!slug) return;
    const refreshWhileVisible = () => {
      if (document.visibilityState === "visible") refresh(slug).catch(() => {});
    };
    const intervalId = window.setInterval(refreshWhileVisible, ACTIVE_TIMER_REFRESH_MS);
    document.addEventListener("visibilitychange", refreshWhileVisible);
    window.addEventListener("focus", refreshWhileVisible);
    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", refreshWhileVisible);
      window.removeEventListener("focus", refreshWhileVisible);
    };
  }, [slug, refresh]);
}

/** The time since `startedAt`, ticking every second; empty while nothing runs. */
function useElapsed(startedAt: string | null) {
  const [elapsed, setElapsed] = useState("");
  useEffect(() => {
    if (!startedAt) {
      setElapsed("");
      return;
    }
    const tick = () => setElapsed(formatElapsed(startedAt));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [startedAt]);
  return elapsed;
}

/** Close the popover on a click outside it, listening only while it is open. */
function useCloseOnOutsideClick(ref: RefObject<HTMLDivElement | null>, isOpen: boolean, close: () => void) {
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) close();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [ref, isOpen, close]);
}

type TRunningTimerWorkItemProps = {
  name: string | null | undefined;
  label: string | null;
  href: string | undefined;
  startedAt: string;
  onNavigate: () => void;
};

/** The work item the running timer is on, with its identifier and when the timer started. */
function RunningTimerWorkItem(props: TRunningTimerWorkItemProps) {
  const { name, label, href, startedAt, onNavigate } = props;
  const { t } = useTranslation();

  return (
    <div className="flex items-start gap-2">
      <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-success-subtle">
        <Clock className="size-3.5 text-success-primary" />
      </span>
      <div className="min-w-0 flex-1">
        {href ? (
          <Link
            href={href}
            onClick={onNavigate}
            className="text-sm block truncate font-medium text-primary hover:underline"
          >
            {name}
          </Link>
        ) : (
          <span className="text-sm block truncate font-medium text-primary">{name}</span>
        )}
        {label && <span className="mt-0.5 block text-11 text-tertiary">{label}</span>}
        {startedAt && (
          <span className="mt-0.5 block text-11 text-tertiary">
            {t("common.worklog_started_at", { datetime: startedAt })}
          </span>
        )}
      </div>
    </div>
  );
}

type TRunningTimerPanelProps = {
  timer: TIssueWorkLog;
  slug: string | undefined;
  elapsed: string;
  isStopping: boolean;
  onStop: () => void;
  onNavigate: () => void;
};

/** The popover's body while a timer runs: the work item, the elapsed time and the Stop control. */
function RunningTimerPanel(props: TRunningTimerPanelProps) {
  const { timer, slug, elapsed, isStopping, onStop, onNavigate } = props;
  const { t } = useTranslation();

  const detail = timer.issue_detail;
  const workItemLabel =
    detail?.project_identifier && detail?.sequence_id != null
      ? `${detail.project_identifier}-${detail.sequence_id}`
      : null;
  const workItemHref = slug && workItemLabel ? `/${slug}/browse/${workItemLabel}/` : undefined;
  const startedAt = timer.started_at
    ? `${renderFormattedDate(timer.started_at) ?? ""} ${renderFormattedTime(timer.started_at)}`.trim()
    : "";

  return (
    <div className="space-y-3">
      <RunningTimerWorkItem
        name={detail?.name ?? workItemLabel}
        label={workItemLabel}
        href={workItemHref}
        startedAt={startedAt}
        onNavigate={onNavigate}
      />

      {/* live elapsed time */}
      <div className="rounded-md bg-surface-2 px-3 py-2 text-center">
        <div className="font-mono text-lg leading-6 text-success-primary">{elapsed}</div>
        <div className="text-11 tracking-wide text-tertiary uppercase">{t("common.worklog_elapsed")}</div>
      </div>

      <Button
        variant="danger"
        size="md"
        stretch="full"
        label={t("common.stop_timer")}
        icon={<Icon icon={<Square className="fill-current" />} />}
        onClick={onStop}
        loading={isStopping}
      />

      {workItemHref && (
        <Link
          href={workItemHref}
          onClick={onNavigate}
          className="block text-center text-11 text-tertiary hover:text-secondary"
        >
          {t("common.worklog_view_work_item")}
        </Link>
      )}
    </div>
  );
}

/**
 * Header widget mirroring the CRM's running-timer indicator: a clock in the top nav that
 * turns active when the user has a timer running anywhere in the workspace, and opens a
 * popover naming the work item, its elapsed time, and a Stop control.
 */
export const HeaderTimerIndicator = observer(function HeaderTimerIndicator() {
  const { workspaceSlug } = useParams();
  const { t } = useTranslation();
  const { worklog } = useIssueDetail();

  const [isOpen, setIsOpen] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const slug = workspaceSlug?.toString();
  const activeTimer = worklog.userActiveTimer;
  // duration === null marks a still-running timer; a completed worklog never lingers here.
  const runningTimer = activeTimer?.duration === null && activeTimer.started_at ? activeTimer : null;
  const isRunning = runningTimer !== null;
  const elapsed = useElapsed(runningTimer?.started_at ?? null);

  // Load the user's running timer once when the header mounts (deduped in the store).
  useEffect(() => {
    if (!slug) return;
    worklog.fetchUserActiveTimer(slug).catch(() => {});
  }, [slug, worklog]);

  useActiveTimerRefresh(slug, worklog.refreshUserActiveTimer);

  const closePopover = useCallback(() => setIsOpen(false), []);
  useCloseOnOutsideClick(containerRef, isOpen, closePopover);

  const handleStop = async () => {
    if (!slug || !activeTimer) return;
    // Prefer the embedded work-item ids; fall back to the raw ids the worklog always carries.
    const projectId = activeTimer.issue_detail?.project_id ?? activeTimer.project;
    const issueId = activeTimer.issue_detail?.id ?? activeTimer.issue;
    setIsStopping(true);
    try {
      await worklog.stopTimer(slug, projectId, issueId, {});
      setIsOpen(false);
    } finally {
      setIsStopping(false);
    }
  };

  return (
    <div ref={containerRef} className="relative">
      <Tooltip
        label={isRunning ? t("common.worklog_running") : t("common.worklog_timer_indicator_tooltip")}
        side="bottom"
      >
        <div>
          <AppSidebarItem
            variant="button"
            item={{
              icon: (
                <div className="relative">
                  <Clock className={cn("size-5", { "text-success-primary": isRunning })} />
                  {isRunning && (
                    <span className="ring-canvas absolute -top-0.5 -right-0.5 size-2 rounded-full bg-success-primary ring-2" />
                  )}
                </div>
              ),
              isActive: isOpen || isRunning,
              onClick: () => setIsOpen((v) => !v),
            }}
          />
        </div>
      </Tooltip>

      {isOpen && (
        <div className="absolute top-full right-0 z-30 mt-1 w-72 rounded-lg border border-subtle bg-surface-1 p-3 shadow-raised-200">
          {runningTimer ? (
            <RunningTimerPanel
              timer={runningTimer}
              slug={slug}
              elapsed={elapsed}
              isStopping={isStopping}
              onStop={handleStop}
              onNavigate={closePopover}
            />
          ) : (
            /* empty state — no running timer */
            <div className="flex flex-col items-center gap-1 py-4 text-center">
              <span className="flex size-9 items-center justify-center rounded-full bg-surface-2">
                <Clock className="size-5 text-tertiary" />
              </span>
              <span className="text-sm mt-1 font-medium text-primary">{t("common.worklog_no_active_timer")}</span>
              <span className="px-2 text-11 text-tertiary">{t("common.worklog_no_active_timer_description")}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
});
