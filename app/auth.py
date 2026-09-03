from fastapi import HTTPException, Request


def require_user(request: Request) -> None:
    if not request.session.get("user"):
        raise HTTPException(status_code=401, detail="Ikke logget ind")
