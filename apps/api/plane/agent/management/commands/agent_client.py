# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Register, change and switch off the apps that may ask people to connect them.

Registering an app is a decision about the whole installation, so it is made here, by
whoever runs the server, and not through the web app. The secret is printed once,
when it is made or replaced, and only its hash is kept: there is no way to read it
back, and losing it means making a new one.

    python manage.py agent_client create --name "Telegram bot" \\
        --redirect-uri https://bot.example.com/plane/callback
    python manage.py agent_client list
    python manage.py agent_client rotate-secret plane_client_...
    python manage.py agent_client deactivate plane_client_...
"""

# Django imports
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

# Module imports
from plane.agent import oauth
from plane.agent.models import AgentClient, AgentGrant
from plane.agent.scopes import SCOPES, unknown_scopes
from plane.agent.tokens import CLIENT_ID_PREFIX, CLIENT_SECRET_PREFIX, hash_secret, new_secret


def _check_redirect_uris(uris):
    for uri in uris:
        problem = oauth.validate_redirect_uri(uri)
        if problem:
            raise CommandError(f"Redirect URI {uri!r} {problem}.")


def _find(client_id):
    client = AgentClient.objects.filter(client_id=client_id).first()
    if client is None:
        raise CommandError(f"No client with id {client_id}.")
    return client


class Command(BaseCommand):
    help = "Register and manage the apps that may be connected to people's Plane accounts."

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="action", required=True)

        create = sub.add_parser("create", help="Register an app and print its credentials.")
        create.add_argument("--name", required=True)
        create.add_argument("--description", default="")
        create.add_argument(
            "--redirect-uri",
            action="append",
            required=True,
            dest="redirect_uris",
            help="An exact address people may be sent back to. May be repeated.",
        )
        create.add_argument(
            "--scope",
            action="append",
            dest="scopes",
            help=f"A scope the app may ask for (default: all of {', '.join(SCOPES)}). May be repeated.",
        )

        sub.add_parser("list", help="Show registered apps.")

        rotate = sub.add_parser("rotate-secret", help="Make a new secret; the old one stops working at once.")
        rotate.add_argument("client_id")

        for name, text in (("deactivate", "Switch an app off."), ("activate", "Switch an app back on.")):
            sub.add_parser(name, help=text).add_argument("client_id")

        update = sub.add_parser("update", help="Change an app's redirect addresses or scopes.")
        update.add_argument("client_id")
        update.add_argument("--add-redirect-uri", action="append", default=[], dest="add_uris")
        update.add_argument("--remove-redirect-uri", action="append", default=[], dest="remove_uris")
        update.add_argument("--set-scopes", nargs="+", dest="set_scopes")

        revoke = sub.add_parser("revoke-grants", help="End every connection an app has, or one person's.")
        revoke.add_argument("client_id")
        revoke.add_argument("--email", help="Only this person's connections.")

    def handle(self, *args, **options):
        getattr(self, f"_{options['action'].replace('-', '_')}")(options)

    def _create(self, options):
        scopes = options["scopes"] or list(SCOPES)
        if unknown_scopes(scopes):
            raise CommandError(f"Unknown scope(s): {', '.join(unknown_scopes(scopes))}.")
        _check_redirect_uris(options["redirect_uris"])

        secret = new_secret(CLIENT_SECRET_PREFIX)
        client = AgentClient.objects.create(
            client_id=new_secret(CLIENT_ID_PREFIX)[: len(CLIENT_ID_PREFIX) + 24],
            name=options["name"],
            description=options["description"],
            secret_hash=hash_secret(secret),
            redirect_uris=list(dict.fromkeys(options["redirect_uris"])),
            allowed_scopes=list(dict.fromkeys(scopes)),
        )
        self.stdout.write(self.style.SUCCESS(f"Registered {client.name}."))
        self.stdout.write(f"  client_id:     {client.client_id}")
        self.stdout.write(f"  client_secret: {secret}")
        self.stdout.write(self.style.WARNING("The secret is shown only now. Store it in the app's secret store."))

    def _list(self, options):
        for client in AgentClient.objects.all():
            live = AgentGrant.objects.filter(client=client, revoked_at__isnull=True).count()
            state = "active" if client.is_active else "OFF"
            self.stdout.write(f"{client.client_id}  {state:<6} {client.name}  ({live} connection(s))")
            self.stdout.write(f"    redirect: {', '.join(client.redirect_uris)}")
            self.stdout.write(f"    scopes:   {' '.join(client.allowed_scopes)}")

    def _rotate_secret(self, options):
        client = _find(options["client_id"])
        secret = new_secret(CLIENT_SECRET_PREFIX)
        client.secret_hash = hash_secret(secret)
        client.secret_rotated_at = timezone.now()
        client.save(update_fields=["secret_hash", "secret_rotated_at", "updated_at"])
        self.stdout.write(self.style.SUCCESS("New secret (the old one no longer works):"))
        self.stdout.write(f"  client_secret: {secret}")
        self.stdout.write(self.style.WARNING("Shown only now."))

    def _deactivate(self, options):
        client = _find(options["client_id"])
        client.is_active = False
        client.save(update_fields=["is_active", "updated_at"])
        self.stdout.write(self.style.SUCCESS(f"{client.name} is off. Its tokens stop working on their next call."))

    def _activate(self, options):
        client = _find(options["client_id"])
        client.is_active = True
        client.save(update_fields=["is_active", "updated_at"])
        self.stdout.write(self.style.SUCCESS(f"{client.name} is on."))

    def _update(self, options):
        client = _find(options["client_id"])
        _check_redirect_uris(options["add_uris"])
        uris = [uri for uri in client.redirect_uris if uri not in options["remove_uris"]]
        uris += [uri for uri in options["add_uris"] if uri not in uris]
        if not uris:
            raise CommandError("An app needs at least one redirect address.")
        client.redirect_uris = uris
        if options["set_scopes"]:
            if unknown_scopes(options["set_scopes"]):
                raise CommandError(f"Unknown scope(s): {', '.join(unknown_scopes(options['set_scopes']))}.")
            client.allowed_scopes = list(dict.fromkeys(options["set_scopes"]))
        client.save(update_fields=["redirect_uris", "allowed_scopes", "updated_at"])
        self.stdout.write(
            self.style.SUCCESS("Updated. Connections that already exist keep the scopes they were given.")
        )

    def _revoke_grants(self, options):
        client = _find(options["client_id"])
        grants = AgentGrant.objects.filter(client=client, revoked_at__isnull=True).select_related("user", "client")
        if options["email"]:
            grants = grants.filter(user__email__iexact=options["email"])
        count = 0
        for grant in grants:
            oauth.revoke_grant(grant, oauth.BY_ADMIN)
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Ended {count} connection(s)."))
