"""A leader asking someone to serve a place ("Could you serve as Helper on Sun Oct 11?").

Drafted by Ask Shepherd; sent only when the leader taps Send, which approves a `serve_ask`
proposal (see `serve_ask_apply`). Her answer goes back to the leader as a notice; the
roster changes only when the leader puts her in.
"""

PROPOSAL_TYPE = "serve_ask"
BUTTONS = ["Yes, I can", "No, sorry"]
