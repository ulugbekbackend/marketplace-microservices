"""Token pairs for test drivers (e2e, load test) without the OTP round trip and its rate
limit. Development only: refuses to run unless DEBUG is on.

    python manage.py issue_tokens --phone +998901110001 --phone +998901110002
    python manage.py issue_tokens --customers 100        # +99899000xxxx load customers

Prints a JSON list of {phone, user_id, role, access, refresh}. Unknown phones become
customers, exactly as a first OTP login would make them.
"""

import json
from typing import Any

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError, CommandParser

from accounts.models import User
from accounts.phone import normalize_phone
from accounts.tokens import issue_tokens

LOAD_PREFIX = "+99899"


def load_phone(index: int) -> str:
    return f"{LOAD_PREFIX}{index:07d}"


class Command(BaseCommand):
    help = "Issue token pairs for test drivers (DEBUG only)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--phone", action="append", default=[], help="repeatable")
        parser.add_argument("--customers", type=int, default=0, help="load customers to issue")

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError("issue_tokens runs only with DEBUG=True")
        phones = [normalize_phone(phone) for phone in options["phone"]]
        phones += [load_phone(i) for i in range(options["customers"])]
        if not phones:
            raise CommandError("pass --phone or --customers")
        issued = []
        for phone in phones:
            user, _ = User.objects.get_or_create(
                phone=phone, defaults={"password": make_password(None)}
            )
            if not user.is_active:
                raise CommandError(f"{phone} is deactivated")
            pair = issue_tokens(user)
            issued.append(
                {
                    "phone": user.phone,
                    "user_id": str(user.id),
                    "role": user.role,
                    "access": pair.access,
                    "refresh": pair.refresh,
                }
            )
        self.stdout.write(json.dumps(issued))
