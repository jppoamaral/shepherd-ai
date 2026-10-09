"""Rule 5 and brief §11 memory row: health or family situations are never proposed or stored."""

import pytest

from app.services.memory import private_reason


@pytest.mark.parametrize(
    "text",
    [
        "Anna's mom is in the hospital, go easy on her",
        "Rachel is going through a divorce",
        "Megan had surgery last month",
        "Tom needs his background check renewed",
        "Emily doesn't get along with Megan",
        "Pastor is counseling the Turners",
    ],
)
def test_private_content_is_refused(text: str) -> None:
    assert private_reason(text) is not None


@pytest.mark.parametrize(
    "text",
    [
        "You always pair Emily with Rachel.",
        "Emily prefers the 9:30 service.",
        "Rachel is ready to lead a class.",
        "Keep the band together for a whole month.",
    ],
)
def test_ordinary_leader_habits_are_fine(text: str) -> None:
    assert private_reason(text) is None
