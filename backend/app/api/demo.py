"""Demo-only endpoints. Off unless `DEMO_MODE=true` (synthetic data only)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import SessionDep, TodayDep
from app.config import get_settings
from app.services.demo import reset_demo

router = APIRouter(tags=["demo"])


def demo_mode() -> bool:
    return get_settings().demo_mode


class DemoResetOut(BaseModel):
    churches: list[str]


@router.post("/demo/reset")
def reset(
    session: SessionDep, today: TodayDep, enabled: Annotated[bool, Depends(demo_mode)]
) -> DemoResetOut:
    """Reload the synthetic seeds, so the demo week is the coming one and nothing is left over."""
    if not enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    churches = reset_demo(session, today)
    session.commit()
    return DemoResetOut(churches=churches)
