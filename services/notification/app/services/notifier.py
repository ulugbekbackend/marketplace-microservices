"""Render a template and deliver it to one user over every channel that applies.

A failed channel raises after the others were tried, so the event is retried; channels that
already delivered are remembered in Redis per (event, user, channel) and skipped on the
retry, so the customer does not get the same SMS twice.
"""

import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.channels import Channel, Message
from app.services.directory import Directory

logger = logging.getLogger(__name__)

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
SENT_TTL_SECONDS = 7 * 24 * 3600


class DeliveryError(RuntimeError):
    """At least one channel failed; the event goes back for a retry."""


def make_environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATES),
        undefined=StrictUndefined,
        autoescape=False,  # plain text for SMS, Telegram and text/plain email
        keep_trailing_newline=False,
    )


def render(environment: Environment, template: str, context: dict[str, Any]) -> Message:
    """The first line of a template is the subject, the rest is the text."""
    rendered = environment.get_template(f"{template}.j2").render(**context)
    # An empty optional part (e.g. no cancel reason) must not leave a dangling space.
    lines = [line.rstrip() for line in rendered.strip().splitlines()]
    return Message(subject=lines[0], text="\n".join(lines[1:]).strip())


class Notifier:
    def __init__(
        self,
        directory: Directory,
        channels: list[Channel],
        redis: Any,
        environment: Environment | None = None,
    ) -> None:
        self._directory = directory
        self._channels = channels
        self._redis = redis
        self._environment = environment or make_environment()

    async def notify(
        self, event_id: UUID, user_id: UUID, template: str, context: dict[str, Any]
    ) -> list[str]:
        """Deliver to one user. Returns the channels used now (already sent ones excluded)."""
        contact = await self._directory.contact(user_id)
        if contact is None:
            logger.warning(
                "nobody to notify", extra={"user_id": str(user_id), "template": template}
            )
            return []
        message = render(self._environment, template, {**context, "name": contact.full_name})
        delivered: list[str] = []
        failed: list[str] = []
        for channel in self._channels:
            if not channel.applies_to(contact):
                continue
            key = f"notification:sent:{event_id}:{user_id}:{channel.name}"
            if await self._redis.get(key):
                continue
            try:
                await channel.send(contact, message)
            except Exception:
                logger.warning(
                    "channel failed",
                    exc_info=True,
                    extra={"channel": channel.name, "template": template},
                )
                failed.append(channel.name)
                continue
            await self._redis.set(key, "1", ex=SENT_TTL_SECONDS)
            delivered.append(channel.name)
        if failed:
            raise DeliveryError(f"{template}: {', '.join(failed)} failed")
        return delivered
