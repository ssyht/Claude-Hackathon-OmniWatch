from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession
from database import get_db
from models import User, WebAuthnCredential, Session as SessionModel
from auth.jwt import create_token
import webauthn
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria, UserVerificationRequirement,
    ResidentKeyRequirement
)
import os, json, base64, uuid

router = APIRouter(prefix="/api/auth", tags=["auth"])

RP_ID     = os.getenv("WEBAUTHN_RP_ID", "localhost")
RP_NAME   = os.getenv("WEBAUTHN_RP_NAME", "OmniWatch")
ORIGIN    = os.getenv("WEBAUTHN_ORIGIN", "http://localhost:3000")

challenges = {}  # in-memory challenge store

@router.post("/register/begin")
async def register_begin(body: dict, db: DBSession = Depends(get_db)):
    username = body.get("username", "").strip()
    display_name = body.get("display_name", username)
    if not username:
        raise HTTPException(400, "Username required")
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        raise HTTPException(409, "User already exists")
    user_id = str(uuid.uuid4())
    opts = webauthn.generate_registration_options(
        rp_id=RP_ID, rp_name=RP_NAME,
        user_id=user_id.encode(), user_name=username,
        user_display_name=display_name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            user_verification=UserVerificationRequirement.REQUIRED,
            resident_key=ResidentKeyRequirement.PREFERRED,
        ),
    )
    challenges[username] = {"challenge": opts.challenge, "user_id": user_id, "display_name": display_name}
    return json.loads(webauthn.options_to_json(opts))

@router.post("/register/complete")
async def register_complete(body: dict, db: DBSession = Depends(get_db)):
    username = body.get("username", "").strip()
    if username not in challenges:
        raise HTTPException(400, "No challenge found")
    stored = challenges.pop(username)
    try:
        verification = webauthn.verify_registration_response(
            credential=body.get("credential"),
            expected_challenge=stored["challenge"],
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
            require_user_verification=True,
        )
    except Exception as e:
        raise HTTPException(400, f"Registration failed: {e}")
    user = User(id=stored["user_id"], username=username, display_name=stored["display_name"])
    db.add(user)
    cred = WebAuthnCredential(
        user_id=stored["user_id"],
        credential_id=base64.b64encode(verification.credential_id).decode(),
        public_key=base64.b64encode(verification.credential_public_key).decode(),
        sign_count=str(verification.sign_count),
    )
    db.add(cred)
    db.commit()
    token = create_token({"sub": stored["user_id"], "username": username, "role": "viewer"})
    session = SessionModel(user_id=stored["user_id"], token=token)
    db.add(session)
    db.commit()
    return {"token": token, "user": {"username": username, "display_name": stored["display_name"]}}

@router.post("/login/begin")
async def login_begin(body: dict, db: DBSession = Depends(get_db)):
    username = body.get("username", "").strip()
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(404, "User not found")
    creds = db.query(WebAuthnCredential).filter(WebAuthnCredential.user_id == user.id).all()
    allow = [{"type": "public-key", "id": c.credential_id} for c in creds]
    opts = webauthn.generate_authentication_options(
        rp_id=RP_ID,
        allow_credentials=allow,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    challenges[username] = {"challenge": opts.challenge, "user": user, "creds": creds}
    return json.loads(webauthn.options_to_json(opts))

@router.post("/login/complete")
async def login_complete(body: dict, db: DBSession = Depends(get_db)):
    username = body.get("username", "").strip()
    if username not in challenges:
        raise HTTPException(400, "No challenge found")
    stored = challenges.pop(username)
    user = stored["user"]
    cred_record = stored["creds"][0]
    try:
        verification = webauthn.verify_authentication_response(
            credential=body.get("credential"),
            expected_challenge=stored["challenge"],
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
            credential_public_key=base64.b64decode(cred_record.public_key),
            credential_current_sign_count=int(cred_record.sign_count),
            require_user_verification=True,
        )
    except Exception as e:
        raise HTTPException(400, f"Login failed: {e}")
    cred_record.sign_count = str(verification.new_sign_count)
    db.commit()
    token = create_token({"sub": user.id, "username": user.username, "role": user.role})
    session = SessionModel(user_id=user.id, token=token)
    db.add(session)
    db.commit()
    return {"token": token, "user": {"username": user.username, "display_name": user.display_name}}

@router.post("/logout")
async def logout(db: DBSession = Depends(get_db)):
    return {"status": "ok"}