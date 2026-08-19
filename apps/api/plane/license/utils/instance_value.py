# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import os
from email.utils import formataddr, parseaddr

# Django imports
from django.conf import settings

# Module imports
from plane.license.models import InstanceConfiguration
from plane.license.utils.encryption import decrypt_data


# Helper function to return value from the passed key
def get_configuration_value(keys):
    environment_list = []
    if settings.SKIP_ENV_VAR:
        # Get the configurations
        instance_configuration = InstanceConfiguration.objects.values("key", "value", "is_encrypted")

        for key in keys:
            for item in instance_configuration:
                if key.get("key") == item.get("key"):
                    if item.get("is_encrypted", False):
                        environment_list.append(decrypt_data(item.get("value")))
                    else:
                        environment_list.append(item.get("value"))

                    break
            else:
                environment_list.append(key.get("default"))
    else:
        # Get the configuration from os
        for key in keys:
            environment_list.append(os.environ.get(key.get("key"), key.get("default")))

    return tuple(environment_list)


def compose_sender(email_from, from_name):
    """Build the From header from a plain address and a display name.

    A mail always carries the sender's address — that is the protocol — but what
    an inbox *shows* is the display name, so setting one is how the raw address
    stops being what recipients read. The two are configured separately and
    joined here rather than asking an admin to write RFC 5322 syntax by hand.

    formataddr does the quoting and non-ASCII encoding, so a name with a comma or
    umlaut cannot produce a malformed header. An EMAIL_FROM that already carries
    its own display name is left exactly as configured.
    """
    if not email_from:
        return email_from

    name = (from_name or "").strip()
    if not name:
        return email_from

    existing_name, address = parseaddr(email_from)
    if existing_name or not address:
        # Already "Name <addr>", or not parseable — do not second-guess it.
        return email_from

    return formataddr((name, address))


def get_email_configuration():
    (
        email_host,
        email_host_user,
        email_host_password,
        email_port,
        email_use_tls,
        email_use_ssl,
        email_from,
        email_from_name,
    ) = get_configuration_value(
        [
            {"key": "EMAIL_HOST", "default": os.environ.get("EMAIL_HOST")},
            {"key": "EMAIL_HOST_USER", "default": os.environ.get("EMAIL_HOST_USER")},
            {
                "key": "EMAIL_HOST_PASSWORD",
                "default": os.environ.get("EMAIL_HOST_PASSWORD"),
            },
            {"key": "EMAIL_PORT", "default": os.environ.get("EMAIL_PORT", 587)},
            {"key": "EMAIL_USE_TLS", "default": os.environ.get("EMAIL_USE_TLS", "1")},
            {"key": "EMAIL_USE_SSL", "default": os.environ.get("EMAIL_USE_SSL", "0")},
            {
                "key": "EMAIL_FROM",
                "default": os.environ.get("EMAIL_FROM", "Team Plane <team@mailer.plane.so>"),
            },
            {
                "key": "EMAIL_FROM_NAME",
                "default": os.environ.get("EMAIL_FROM_NAME", ""),
            },
        ]
    )

    # The senders all unpack seven values and pass the last straight to
    # from_email, so the name is folded in here and every mail picks it up.
    return (
        email_host,
        email_host_user,
        email_host_password,
        email_port,
        email_use_tls,
        email_use_ssl,
        compose_sender(email_from, email_from_name),
    )
