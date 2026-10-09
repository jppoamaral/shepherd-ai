"""Proposal types for a volunteer's own answers (applied by `reply_apply`)."""

CONFIRM = "reply_confirm"
DECLINE = "reply_decline"
AWAY = "reply_away"
STOP = "reply_stop"
START = "reply_start"
CAN_SERVE = "reply_can_serve"  # her answer to a leader's ask; the leader still decides
CANT_SERVE = "reply_cant_serve"
TYPES = (CONFIRM, DECLINE, AWAY, STOP, START, CAN_SERVE, CANT_SERVE)
