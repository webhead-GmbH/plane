/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

"use client";

import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Clock, Square } from "lucide-react";
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { Tooltip } from "@plane/propel/tooltip";
import { cn, renderFormattedDate, renderFormattedTime } from "@plane/utils";
// components
import { AppSidebarItem } from "@/components/sidebar/sidebar-item";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// local imports
import { formatElapsed } from "./utils";

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
  const [elapsed, setElapsed] = useState("");
  const [isStopping, setIsStopping] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const slug = workspaceSlug?.toString();
  const activeTimer = worklog.userActiveTimer;
  // duration === null marks a still-running timer; a completed worklog never lingers here.
  const isRunning = !!activeTimer && activeTimer.duration === null && !!activeTimer.started_at;
  const detail = activeTimer?.issue_detail;

  const workItemLabel =
    detail?.project_identifier && detail?.sequence_id != null
      ? `${detail.project_identifier}-${detail.sequence_id}`
      : null;
  const workItemHref = slug && workItemLabel ? `/${slug}/browse/${workItemLabel}/` : undefined;

  // Load the user's running timer once when the header mounts (deduped in the store).
  useEffect(() => {
    if (!slug) return;
    worklog.fetchUserActiveTimer(slug).catch(() => {});
  }, [slug, worklog]);

  // Live elapsed tick while a timer runs.
  useEffect(() => {
    if (!isRunning || !activeTimer?.started_at) {
      setElapsed("");
      return;
    }
    const tick = () => setElapsed(formatElapsed(activeTimer.started_at!));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [isRunning, activeTimer?.started_at]);

  // Close the popover on outside click.
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setIsOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [isOpen]);

  const handleStop = async () => {
    if (!slug || !activeTimer) return;
    // Prefer the embedded work-item ids; fall back to the raw ids the worklog always carries.
    const projectId = detail?.project_id ?? activeTimer.project;
    const issueId = detail?.id ?? activeTimer.issue;
    setIsStopping(true);
    try {
      await worklog.stopTimer(slug, projectId, issueId, {});
      setIsOpen(false);
    } finally {
      setIsStopping(false);
    }
  };

  const startedAt =
    isRunning && activeTimer?.started_at
      ? `${renderFormattedDate(activeTimer.started_at) ?? ""} ${renderFormattedTime(activeTimer.started_at)}`.trim()
      : "";

  return (
    <div ref={containerRef} className="relative">
      <Tooltip
        tooltipContent={isRunning ? t("common.worklog_running") : t("common.worklog_timer_indicator_tooltip")}
        position="bottom"
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
          {isRunning && activeTimer ? (
            <div className="space-y-3">
              {/* work item the timer is running on */}
              <div className="flex items-start gap-2">
                <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-success-subtle">
                  <Clock className="size-3.5 text-success-primary" />
                </span>
                <div className="min-w-0 flex-1">
                  {workItemHref ? (
                    <Link
                      href={workItemHref}
                      onClick={() => setIsOpen(false)}
                      className="text-sm block truncate font-medium text-primary hover:underline"
                    >
                      {detail?.name ?? workItemLabel}
                    </Link>
                  ) : (
                    <span className="text-sm block truncate font-medium text-primary">
                      {detail?.name ?? workItemLabel}
                    </span>
                  )}
                  {workItemLabel && <span className="mt-0.5 block text-11 text-tertiary">{workItemLabel}</span>}
                  {startedAt && (
                    <span className="mt-0.5 block text-11 text-tertiary">
                      {t("common.worklog_started_at", { datetime: startedAt })}
                    </span>
                  )}
                </div>
              </div>

              {/* live elapsed time */}
              <div className="rounded-md bg-surface-2 px-3 py-2 text-center">
                <div className="font-mono text-lg leading-6 text-success-primary">{elapsed}</div>
                <div className="text-11 tracking-wide text-tertiary uppercase">{t("common.worklog_elapsed")}</div>
              </div>

              <Button
                variant="error-fill"
                size="lg"
                className="w-full"
                onClick={handleStop}
                loading={isStopping}
                disabled={isStopping}
              >
                <Square className="size-3.5 shrink-0 fill-current" />
                {t("common.stop_timer")}
              </Button>

              {workItemHref && (
                <Link
                  href={workItemHref}
                  onClick={() => setIsOpen(false)}
                  className="block text-center text-11 text-tertiary hover:text-secondary"
                >
                  {t("common.worklog_view_work_item")}
                </Link>
              )}
            </div>
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
