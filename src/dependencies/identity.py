"""Local development identity.

X-Stall-ID is a convention for local work only. It is NOT authentication:
any client can set any value, and nothing verifies it. It makes accidental
cross-stall requests loud; it stops nobody deliberate. The service binds to
loopback for that reason. Production identity is explicitly deferred.
"""

from fastapi import Header, HTTPException, Path


def require_matching_stall(
    stall_id: int = Path(..., gt=0),
    x_stall_id: str | None = Header(default=None, alias="X-Stall-ID"),
) -> int:
    """Require the caller to name the stall it is asking about."""
    if x_stall_id is None or not x_stall_id.strip():
        raise HTTPException(status_code=401, detail="Missing X-Stall-ID header")

    try:
        claimed = int(x_stall_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="Malformed X-Stall-ID header") from None

    if claimed != stall_id:
        raise HTTPException(
            status_code=403,
            detail="X-Stall-ID does not match the requested stall",
        )

    return stall_id
