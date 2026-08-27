# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Settings for this module, kept here rather than in the shared settings file.

Everything is read through ``getattr(settings, ...)`` with the value below as the
fallback, so an installation can override any of it without this module needing an
entry in a file that is merged from upstream.
"""

# The zone every day and month boundary is resolved in. Not the server's zone and
# not the viewer's browser: one declared answer, the same from a web request and
# from a background job.
DEFAULT_HR_TIMEZONE = "Europe/Vienna"

# A timer left running past this is closed by the sweeper and marked for the owner
# to correct. Ten hours is the daily ceiling, so anything beyond it is a forgotten
# timer rather than a long day.
DEFAULT_MAX_TIMER_MINUTES = 600

# How far back the rebuild reaches. The current month plus the one before it covers
# the window in which figures can still change.
DEFAULT_REBUILD_MONTHS = 2
