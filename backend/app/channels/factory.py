"""Picks each church's channel: its own setting, unless CHANNEL_BY_CHURCH overrides it."""

from sqlalchemy.orm import Session

from app.channels.base import ChannelAdapter
from app.channels.copy_paste import CopyPasteChannel
from app.channels.simulator import SimulatorChannel
from app.config import get_settings
from app.db.models import Church

CHANNELS = ("copy_paste", "simulator")


def channel_name(church: Church) -> str:
    name = get_settings().channel_by_church.get(church.name, church.channel)
    return name if name in CHANNELS else "copy_paste"


def channel_for(session: Session, church: Church) -> ChannelAdapter:
    if channel_name(church) == "simulator":
        return SimulatorChannel(session, church.id)
    return CopyPasteChannel()
