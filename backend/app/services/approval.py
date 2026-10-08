"""ApprovalService: the ONLY code allowed to apply a Proposal's side effects.

Every approval or rejection writes an AuditLog entry (architecture rules 1 and 9).
Proposal types and their handlers arrive with the milestones that create them
(rosters in M5, reminders in M6, memory in M7).
"""
