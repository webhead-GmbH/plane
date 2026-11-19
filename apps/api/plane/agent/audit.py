# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Writing down what connected apps did, without ever being the reason something failed."""

# Django imports
from django.db import transaction

# Module imports
from plane.agent.models import AgentAuditLog
from plane.agent.network import client_address
from plane.utils.exception_logger import log_exception


def record(event, *, request=None, client=None, grant=None, user=None, status_code=None, **detail):
    """Add one line to the log.

    A failure to write it is logged and swallowed. The log is there to explain what
    happened, so it must not be what stops a person's request from working; and the
    write sits in a savepoint of its own so a failure cannot poison the transaction
    of the caller, which may be in the middle of ending somebody's access.
    """
    try:
        if grant is not None:
            client = client or grant.client
            user = user or grant.user
        with transaction.atomic():
            AgentAuditLog.objects.create(
                event=event,
                client=client,
                grant=grant,
                user=user,
                method=(request.method if request is not None else "")[:8],
                path=(request.path if request is not None else "")[:255],
                status_code=status_code,
                ip_address=client_address(request) if request is not None else None,
                user_agent=(request.META.get("HTTP_USER_AGENT", "") if request is not None else "")[:255],
                detail=detail,
            )
    except Exception as error:  # noqa: BLE001 - see the docstring
        log_exception(error)
