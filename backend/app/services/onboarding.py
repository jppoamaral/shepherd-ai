"""Starting onboarding: the admin's own action, so it may create the draft church.

The church starts as a draft with a placeholder time zone; nothing runs for it
until the onboarding proposal is approved (see `profile_apply`).
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Church, OnboardingSession, Person
from app.domain.enums import OnboardingStatus, ProfileStatus
from app.domain.profile import ChurchProfileDraft
from app.services.errors import ApprovalError
from app.services.profile import next_topic, question_for

PLACEHOLDER_TIMEZONE = "UTC"


@dataclass(frozen=True)
class Started:
    church: Church
    admin: Person
    session: OnboardingSession
    question: str


def start_onboarding(session: Session, church_name: str, admin_name: str) -> Started:
    name = church_name.strip()
    if session.scalar(select(Church.id).where(Church.name == name)) is not None:
        raise ApprovalError(f"a church called {name!r} already exists")
    church = Church(name=name, timezone=PLACEHOLDER_TIMEZONE, profile_status=ProfileStatus.DRAFT)
    session.add(church)
    session.flush()
    admin = Person(church_id=church.id, name=admin_name.strip(), is_admin=True, opted_in=True)
    session.add(admin)
    session.flush()
    draft = ChurchProfileDraft()
    topic = next_topic(draft)
    question = question_for(topic)
    onboarding = OnboardingSession(
        church_id=church.id,
        admin_person_id=admin.id,
        status=OnboardingStatus.ACTIVE,
        topic=topic,
        draft=draft.model_dump(mode="json"),
        pending_question=question,
    )
    session.add(onboarding)
    session.flush()
    return Started(church, admin, onboarding, question)
