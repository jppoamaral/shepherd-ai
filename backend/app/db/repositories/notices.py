"""One-time notices for leaders from volunteers' chats ("Anna can't make Oct 11").

Not the record: a notice is deleted when the leader dismisses it and is never audited.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import LeaderNotice


class NoticeWriter:
    def __init__(self, session: Session, church_id: uuid.UUID) -> None:
        self.session = session
        self.church_id = church_id

    def add(
        self,
        *,
        ministry_id: uuid.UUID,
        about_person_id: uuid.UUID,
        kind: str,
        text: str,
        note: str | None = None,
    ) -> LeaderNotice:
        notice = LeaderNotice(
            church_id=self.church_id,
            ministry_id=ministry_id,
            about_person_id=about_person_id,
            kind=kind,
            text=text,
            note=note,
        )
        self.session.add(notice)
        self.session.flush()
        return notice

    def dismiss(self, notice_id: uuid.UUID) -> bool:
        notice = self.session.scalar(
            select(LeaderNotice).where(
                LeaderNotice.church_id == self.church_id, LeaderNotice.id == notice_id
            )
        )
        if notice is None:
            return False
        self.session.delete(notice)  # gone for good, including any note
        self.session.flush()
        return True
