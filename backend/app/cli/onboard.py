"""Terminal chat with the onboarding agent, through the API (no frontend yet).

    uv run python -m app.cli.onboard [--api http://localhost:8000]

Type answers as you would in chat. Commands:
    /sample   paste a past schedule, then a line with just END
    /summary  show the profile so far
    /approve  approve the pending profile as the admin
    /quit     leave (the onboarding stays where you left it)
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


class Api:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            f"{self.base}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read() or b"null")
        except urllib.error.HTTPError as error:
            detail = json.loads(error.read() or b"{}").get("detail", error.reason)
            raise SystemExit(f"API error {error.code}: {detail}") from None
        except urllib.error.URLError as error:
            raise SystemExit(f"Can't reach the API at {self.base}: {error.reason}") from None


def read_paste() -> str:
    print("Paste the schedule, then a line with just END:")
    lines = []
    for line in sys.stdin:
        if line.strip() == "END":
            break
        lines.append(line)
    return "".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--api", default=os.environ.get("SHEPHERD_API", "http://localhost:8000"))
    args = parser.parse_args()
    api = Api(args.api)

    church_name = input("Church name: ").strip()
    admin_name = input("Your name: ").strip()
    started = api.call(
        "POST", "/onboarding", {"church_name": church_name, "admin_name": admin_name}
    )
    church, onboarding, admin = (
        started["church_id"],
        started["onboarding_id"],
        started["admin_person_id"],
    )
    base = f"/churches/{church}/onboarding/{onboarding}"
    print(f"\nShepherd: {started['message']}\n")

    while True:
        try:
            text = input("You: ").strip()
        except EOFError:
            break
        if not text:
            continue
        if text == "/quit":
            break
        if text == "/summary":
            print(f"\n{api.call('GET', base)['summary']}\n")
            continue
        if text == "/approve":
            state = api.call("GET", base)
            if not state["proposal_id"]:
                print("\nThere's no profile waiting for approval yet.\n")
                continue
            api.call(
                "POST",
                f"/churches/{church}/proposals/{state['proposal_id']}/approve",
                {"person_id": admin},
            )
            print(f"\nApproved. {church_name} is live (church id {church}).\n")
            break
        if text == "/sample":
            reply = api.call("POST", f"{base}/sample", {"text": read_paste()})
        else:
            reply = api.call("POST", f"{base}/messages", {"text": text})
        print(f"\nShepherd: {reply['message']}\n")
        if reply["status"] == "proposed":
            print("(Type /approve to approve it as the admin, or /quit to leave it pending.)\n")


if __name__ == "__main__":
    main()
