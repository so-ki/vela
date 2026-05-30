from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.chroma_client import chroma_health
from app.core.database import get_db
from app.core.deps import get_authenticated_user, get_current_user
from app.models.user import User
from app.schemas.auth import AcceptDisclaimerRequest, TokenResponse, UserLogin, UserRegister, UserResponse
from app.services.auth_service import accept_disclaimer, authenticate_user, login_user, register_user
from app.services.disclaimer import DISCLAIMER_FULL_TEXT, DISCLAIMER_SECTIONS, DISCLAIMER_TITLE, DISCLAIMER_VERSION

router = APIRouter(prefix="/auth", tags=["认证"])


@router.get("/disclaimer")
def get_disclaimer():
    return {
        "title": DISCLAIMER_TITLE,
        "version": DISCLAIMER_VERSION,
        "sections": DISCLAIMER_SECTIONS,
        "full_text": DISCLAIMER_FULL_TEXT,
    }


@router.post("/register", response_model=UserResponse, status_code=201)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    return register_user(db, payload)


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = authenticate_user(db, payload.email, payload.password)
    token = login_user(db, user)
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.post("/accept-disclaimer", response_model=UserResponse)
def accept_disclaimer_endpoint(
    payload: AcceptDisclaimerRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_authenticated_user),
):
    if not payload.accept:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="须明确同意条款方可继续")
    return accept_disclaimer(db, current_user)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_authenticated_user)):
    return current_user
