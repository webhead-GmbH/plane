# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Register, change and switch off the apps that may ask people to connect them.

Registering an app is a decision about the whole installation, so it is made by whoever
runs the server: here, or on the "Connected apps" page of the admin app, which does the
same thing (both use `plane.agent.services.registry`). Never through the people's own web
app. The secret is printed once, when it is made or replaced, and only its hash is kept:
there is no way to read it back, and losing it means making a new one.

    python manage.py agent_client create --name "Telegram bot" \\
        --redirect-uri https://bot.example.com/plane/callback
    python manage.py agent_client list
    python manage.py agent_client rotate-secret plane_client_...
    python manage.py agent_client deactivate plane_client_...
"""

# Django imports
from django.core.management.base import BaseCommand, CommandError

# Module imports
from plane.agent.models import AgentClient
from plane.agent.scopes import DEFAULT_SCOPES
from plane.agent.services import events, registry
from plane.agent.services.registry import RegistryError


def _find(client_id):
    try:
        return registry.find(client_id)
    except RegistryError as error:
        raise CommandError(str(error))


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
            help=(
                "A scope the app may ask for. May be repeated. Default: the scopes that only read the "
                f"linking person's own information ({', '.join(DEFAULT_SCOPES)}); scopes that change things, "
                "or show other people's information (team:read), must be named."
            ),
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

        webhook = sub.add_parser(
            "webhook",
            help="Say where an app is told about events (assigned, due date or state changed, connection ended).",
        )
        webhook.add_argument("client_id")
        webhook.add_argument("--url", help="An https:// address. Replaces the old one and switches delivery back on.")
        webhook.add_argument("--off", action="store_true", help="Stop telling this app about events.")
        webhook.add_argument(
            "--new-secret", action="store_true", dest="new_secret", help="Change the signing secret at once."
        )
        webhook.add_argument(
            "--show-secret", action="store_true", dest="show_secret", help="Print the signing secret again."
        )
        webhook.add_argument(
            "--send-test",
            action="store_true",
            dest="send_test",
            help="Send one signed `webhook.test` to the address now and say whether the app answered.",
        )

        revoke = sub.add_parser("revoke-grants", help="End every connection an app has, or one person's.")
        revoke.add_argument("client_id")
        revoke.add_argument("--email", help="Only this person's connections.")

    def handle(self, *args, **options):
        try:
            getattr(self, f"_{options['action'].replace('-', '_')}")(options)
        except RegistryError as error:
            raise CommandError(str(error))

    def _create(self, options):
        client, secret = registry.create_client(
            name=options["name"],
            description=options["description"],
            redirect_uris=options["redirect_uris"],
            scopes=options["scopes"],
        )
        self.stdout.write(self.style.SUCCESS(f"Registered {client.name}."))
        self.stdout.write(f"  client_id:     {client.client_id}")
        self.stdout.write(f"  client_secret: {secret}")
        self.stdout.write(self.style.WARNING("The secret is shown only now. Store it in the app's secret store."))

    def _list(self, options):
        for client in AgentClient.objects.all():
            live = registry.live_grants(client).count()
            state = "active" if client.is_active else "OFF"
            self.stdout.write(f"{client.client_id}  {state:<6} {client.name}  ({live} connection(s))")
            self.stdout.write(f"    redirect: {', '.join(client.redirect_uris)}")
            self.stdout.write(f"    scopes:   {' '.join(client.allowed_scopes)}")
            if client.webhook_url:
                state = "OFF after repeated failures" if client.webhook_disabled_at else "on"
                self.stdout.write(f"    events:   {client.webhook_url} ({state})")

    def _rotate_secret(self, options):
        secret = registry.rotate_secret(_find(options["client_id"]))
        self.stdout.write(self.style.SUCCESS("New secret (the old one no longer works):"))
        self.stdout.write(f"  client_secret: {secret}")
        self.stdout.write(self.style.WARNING("Shown only now."))

    def _deactivate(self, options):
        client = _find(options["client_id"])
        registry.update_client(client, is_active=False)
        self.stdout.write(self.style.SUCCESS(f"{client.name} is off. Its tokens stop working on their next call."))

    def _activate(self, options):
        client = _find(options["client_id"])
        registry.update_client(client, is_active=True)
        self.stdout.write(self.style.SUCCESS(f"{client.name} is on."))

    def _update(self, options):
        client = _find(options["client_id"])
        uris = [uri for uri in client.redirect_uris if uri not in options["remove_uris"]]
        uris += [uri for uri in options["add_uris"] if uri not in uris]
        registry.update_client(client, redirect_uris=uris, allowed_scopes=options["set_scopes"] or None)
        self.stdout.write(
            self.style.SUCCESS("Updated. Connections that already exist keep the scopes they were given.")
        )

    def _webhook(self, options):
        client = _find(options["client_id"])
        changed = registry.set_webhook(client, url=options["url"], off=options["off"], new_secret=options["new_secret"])

        if not client.webhook_url:
            self.stdout.write("Events are off for this app: it is not told anything, and polls instead.")
            return
        state = (
            "OFF after repeated failures (set --url again to switch it back on)" if client.webhook_disabled_at else "on"
        )
        self.stdout.write(f"  address:   {client.webhook_url} ({state})")
        self.stdout.write(f"  failures:  {client.webhook_failures} in a row")
        if options["send_test"]:
            heard, what = events.send_test(client)
            style = self.style.SUCCESS if heard else self.style.ERROR
            self.stdout.write(style(f"  test:      {'the app answered' if heard else 'NOT delivered'} ({what})"))
        if changed or options["show_secret"]:
            self.stdout.write(f"  secret:    {events.webhook_secret(client)}")
            self.stdout.write(
                self.style.WARNING(
                    "Give the secret to the app's developer through your secret-sharing channel. It is not stored: "
                    "--show-secret prints it again, --new-secret replaces it."
                )
            )

    def _revoke_grants(self, options):
        client = _find(options["client_id"])
        count = registry.revoke_grants(client, email=options["email"])
        self.stdout.write(self.style.SUCCESS(f"Ended {count} connection(s)."))
