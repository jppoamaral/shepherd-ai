class ApprovalError(Exception):
    """A proposal can't be approved or rejected as asked. The message is user-facing."""


class NotFound(ApprovalError):
    pass


class NotAllowed(ApprovalError):
    pass
