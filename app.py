from pathlib import Path
import io
import re
from functools import lru_cache
from threading import Lock
import httpx
from datetime import datetime, timezone
from argostranslate import package as argos_package
from argostranslate import translate as argos_translate
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from auth_config import SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY

APP_VERSION = "1.0.0"
UPDATE_MANIFEST_URL = "https://fgtqhfworgxnldoxgmbd.supabase.co/storage/v1/object/public/voxviet-updates/latest.json"

app = FastAPI(
    title="VietDoc Local",
    version=APP_VERSION,
    description="Vietnamese document and language utility for SoloHost"
)

BASE_DIR = Path(__file__).resolve().parent

# Hạn mức thử nghiệm để kiểm tra cơ chế FREE / PRO
FREE_MONTHLY_CHAR_LIMIT = 5000
STANDARD_MONTHLY_CHAR_LIMIT = 150000
SPECIAL_MONTHLY_CHAR_LIMIT = 350000
VIP_MONTHLY_CHAR_LIMIT = 1000000
DIACRITIC_MODEL_ID = "nrl-ai/vn-diacritic-small"
ARGOS_INSTALL_LOCK = Lock()
TTS_LOCK = Lock()
class TextRequest(BaseModel):
    text: str

class TranslationRequest(BaseModel):
    text: str
    direction: str

class TTSRequest(BaseModel):
    text: str
    language: str = "vi"
    voice: str | None = None
    style: str = "tu_nhien"
class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str



class PaymentCreateRequest(BaseModel):
    plan: str
    months: int


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    new_password: str


@lru_cache(maxsize=1)
def get_tts_engine():
    from vieneu import Vieneu

    return Vieneu()

@lru_cache(maxsize=2)
def get_english_tts_engine(lang_code: str = "a"):
    from kokoro import KPipeline

    return KPipeline(lang_code=lang_code)


def argos_pair_installed(from_code: str, to_code: str) -> bool:
    installed_packages = argos_package.get_installed_packages()

    return any(
        pkg.from_code == from_code
        and pkg.to_code == to_code
        for pkg in installed_packages
    )


def ensure_argos_pair(from_code: str, to_code: str):
    if argos_pair_installed(from_code, to_code):
        return

    with ARGOS_INSTALL_LOCK:

        if argos_pair_installed(from_code, to_code):
            return

        argos_package.update_package_index()

        available_packages = (
            argos_package.get_available_packages()
        )

        package_to_install = next(
            (
                pkg
                for pkg in available_packages
                if pkg.from_code == from_code
                and pkg.to_code == to_code
            ),
            None
        )

        if package_to_install is None:
            raise RuntimeError(
                f"Không tìm thấy model dịch "
                f"{from_code} -> {to_code}."
            )

        package_to_install.install()


@app.post("/api/auth/register")
def register_user(data: RegisterRequest):
    email = data.email.strip().lower()
    password = data.password

    if not email or not password:
        raise HTTPException(
            status_code=400,
            detail="Vui lòng nhập đầy đủ email và mật khẩu."
        )

    if len(password) < 6:
        raise HTTPException(
            status_code=400,
            detail="Mật khẩu phải có ít nhất 6 ký tự."
        )

    try:
        response = httpx.post(
            f"{SUPABASE_URL}/auth/v1/signup",
            headers={
                "apikey": SUPABASE_PUBLISHABLE_KEY,
                "Content-Type": "application/json"
            },
            json={
                "email": email,
                "password": password
            },
            timeout=20.0
        )

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail="Không thể kết nối máy chủ đăng ký tài khoản."
        ) from exc

    try:
        result = response.json()
    except Exception:
        result = {}

    if response.status_code >= 400:
        detail = (
            result.get("msg")
            or result.get("message")
            or result.get("error_description")
            or "Không thể đăng ký tài khoản."
        )

        raise HTTPException(
            status_code=response.status_code,
            detail=detail
        )

    user = result.get("user") or {}
    session = result.get("session")

    return {
        "ok": True,
        "message": (
            "Đăng ký thành công. Vui lòng kiểm tra email để xác nhận tài khoản."
            if session is None
            else "Đăng ký tài khoản thành công."
        ),
        "user": {
            "id": user.get("id"),
            "email": user.get("email")
        },
        "email_confirmation_required": session is None
    }


@app.post("/api/auth/login")
def login_user(data: LoginRequest):
    email = data.email.strip().lower()
    password = data.password

    if not email or not password:
        raise HTTPException(
            status_code=400,
            detail="Vui lòng nhập đầy đủ email và mật khẩu."
        )

    try:
        response = httpx.post(
            f"{SUPABASE_URL}/auth/v1/token",
            params={
                "grant_type": "password"
            },
            headers={
                "apikey": SUPABASE_PUBLISHABLE_KEY,
                "Content-Type": "application/json"
            },
            json={
                "email": email,
                "password": password
            },
            timeout=20.0
        )

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail="Không thể kết nối máy chủ đăng nhập."
        ) from exc

    try:
        result = response.json()
    except Exception:
        result = {}

    if response.status_code >= 400:
        detail = (
            result.get("msg")
            or result.get("message")
            or result.get("error_description")
            or "Không thể đăng nhập."
        )

        if "invalid login credentials" in detail.lower():
            raise HTTPException(
                status_code=401,
                detail="Email hoặc mật khẩu không đúng."
            )

        raise HTTPException(
            status_code=response.status_code,
            detail=detail
        )

    user = result.get("user") or {}

    return {
        "ok": True,
        "message": "Đăng nhập thành công.",
        "access_token": result.get("access_token"),
        "refresh_token": result.get("refresh_token"),
        "expires_in": result.get("expires_in"),
        "token_type": result.get("token_type"),
        "user": {
            "id": user.get("id"),
            "email": user.get("email")
        }
    }

@app.post("/api/auth/forgot-password")
def forgot_password(data: ForgotPasswordRequest):
    email = data.email.strip().lower()

    if not email:
        raise HTTPException(
            status_code=400,
            detail="Vui lòng nhập email."
        )

    try:
        response = httpx.post(
            f"{SUPABASE_URL}/auth/v1/recover",
            params={
                "redirect_to": "http://127.0.0.1:8765/?reset_password=1"
            },
            headers={
                "apikey": SUPABASE_PUBLISHABLE_KEY,
                "Content-Type": "application/json"
            },
            json={
                "email": email
            },
            timeout=20.0
        )

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail="Không thể kết nối máy chủ đặt lại mật khẩu."
        ) from exc

    try:
        result = response.json()
    except Exception:
        result = {}

    if response.status_code >= 400:
        detail = (
            result.get("msg")
            or result.get("message")
            or result.get("error_description")
            or "Không thể gửi email đặt lại mật khẩu."
        )

        raise HTTPException(
            status_code=response.status_code,
            detail=detail
        )

    return {
        "ok": True,
        "message": (
            "Nếu email đã được đăng ký, hệ thống sẽ gửi "
            "liên kết đặt lại mật khẩu đến email đó."
        )
    }


@app.post("/api/auth/reset-password")
def reset_password(
    data: ResetPasswordRequest,
    authorization: str | None = Header(default=None)
):
    new_password = data.new_password

    if len(new_password) < 6:
        raise HTTPException(
            status_code=400,
            detail="Mật khẩu mới phải có ít nhất 6 ký tự."
        )

    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Thiếu phiên đặt lại mật khẩu."
        )

    parts = authorization.split(" ", 1)

    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Phiên đặt lại mật khẩu không hợp lệ."
        )

    recovery_token = parts[1].strip()

    if not recovery_token:
        raise HTTPException(
            status_code=401,
            detail="Phiên đặt lại mật khẩu không hợp lệ."
        )

    try:
        response = httpx.put(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "apikey": SUPABASE_PUBLISHABLE_KEY,
                "Authorization": f"Bearer {recovery_token}",
                "Content-Type": "application/json"
            },
            json={
                "password": new_password
            },
            timeout=20.0
        )

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail="Không thể kết nối máy chủ đặt lại mật khẩu."
        ) from exc

    try:
        result = response.json()
    except Exception:
        result = {}

    if response.status_code >= 400:
        detail = (
            result.get("msg")
            or result.get("message")
            or result.get("error_description")
            or "Không thể đặt lại mật khẩu."
        )

        raise HTTPException(
            status_code=response.status_code,
            detail=detail
        )

    return {
        "ok": True,
        "message": "Đặt lại mật khẩu thành công."
    }


@app.post("/api/auth/refresh")
def refresh_user_token(data: RefreshRequest):
    refresh_token = data.refresh_token.strip()

    if not refresh_token:
        raise HTTPException(
            status_code=400,
            detail="Thiếu refresh token."
        )

    try:
        response = httpx.post(
            f"{SUPABASE_URL}/auth/v1/token",
            params={
                "grant_type": "refresh_token"
            },
            headers={
                "apikey": SUPABASE_PUBLISHABLE_KEY,
                "Content-Type": "application/json"
            },
            json={
                "refresh_token": refresh_token
            },
            timeout=20.0
        )

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail="Không thể kết nối máy chủ làm mới phiên đăng nhập."
        ) from exc

    try:
        result = response.json()
    except Exception:
        result = {}

    if response.status_code >= 400:
        detail = (
            result.get("msg")
            or result.get("message")
            or result.get("error_description")
            or "Không thể làm mới phiên đăng nhập."
        )

        raise HTTPException(
            status_code=response.status_code,
            detail=detail
        )

    return {
        "ok": True,
        "access_token": result.get("access_token"),
        "refresh_token": result.get("refresh_token"),
        "expires_in": result.get("expires_in"),
        "token_type": result.get("token_type")
    }


def require_user(
    authorization: str | None = Header(default=None)
):
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Bạn chưa đăng nhập."
        )

    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="Token đăng nhập không hợp lệ."
        )

    access_token = authorization.split(" ", 1)[1].strip()

    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="Token đăng nhập không hợp lệ."
        )

    try:
        response = httpx.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "apikey": SUPABASE_PUBLISHABLE_KEY,
                "Authorization": f"Bearer {access_token}"
            },
            timeout=20.0
        )

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail="Không thể xác thực tài khoản."
        ) from exc

    if response.status_code != 200:
        raise HTTPException(
            status_code=401,
            detail="Phiên đăng nhập đã hết hạn hoặc không hợp lệ."
        )

    try:
        user = response.json()
    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail="Không đọc được thông tin tài khoản."
        ) from exc

    return user
@app.get("/api/account/profile")
def get_account_profile(
    authorization: str | None = Header(default=None),
    user=Depends(require_user)
):
    user_id = user.get("id")

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Không xác định được tài khoản."
        )

    access_token = authorization.split(" ", 1)[1].strip()

    try:
        response = httpx.get(
            f"{SUPABASE_URL}/rest/v1/profiles",
            headers={
                "apikey": SUPABASE_PUBLISHABLE_KEY,
                "Authorization": f"Bearer {access_token}"
            },
            params={
                "id": f"eq.{user_id}",
                "select": "id,email,plan,plan_expires_at"
            },
            timeout=20.0
        )

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail="Không thể đọc thông tin gói tài khoản."
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail="Không thể đọc hồ sơ tài khoản."
        )

    try:
        rows = response.json()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Dữ liệu hồ sơ tài khoản không hợp lệ."
        ) from exc

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy hồ sơ tài khoản."
        )

    profile = rows[0]

    stored_plan = str(
        profile.get("plan") or "free"
    ).lower()

    expires_at = profile.get("plan_expires_at")

    effective_plan = "free"

    if (
        stored_plan in {"standard", "special", "vip"}
        and expires_at
    ):
        try:
            expires_dt = datetime.fromisoformat(
                expires_at.replace("Z", "+00:00")
            )

            if expires_dt > datetime.now(timezone.utc):
                effective_plan = stored_plan

        except (ValueError, TypeError):
            effective_plan = "free"

    profile["plan"] = effective_plan

    return {
        "ok": True,
        "profile": profile
    }
@app.get("/api/account/usage")
def get_account_usage(
    authorization: str | None = Header(default=None),
    user=Depends(require_user)
):
    user_id = user.get("id")

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Không xác định được tài khoản."
        )

    access_token = authorization.split(" ", 1)[1].strip()

    month_start = (
        datetime.now(timezone.utc)
        .date()
        .replace(day=1)
        .isoformat()
    )

    try:
        response = httpx.get(
            f"{SUPABASE_URL}/rest/v1/tts_usage_monthly",
            headers={
                "apikey": SUPABASE_PUBLISHABLE_KEY,
                "Authorization": f"Bearer {access_token}"
            },
            params={
                "user_id": f"eq.{user_id}",
                "month_start": f"eq.{month_start}",
                "select": "characters_used"
            },
            timeout=20.0
        )

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail="Không thể đọc hạn mức sử dụng."
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail="Không thể đọc dữ liệu sử dụng."
        )

    try:
        rows = response.json()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Dữ liệu sử dụng không hợp lệ."
        ) from exc

    characters_used = 0

    if rows:
        characters_used = int(
            rows[0].get("characters_used") or 0
        )

        profile_result = get_account_profile(
        authorization=authorization,
        user=user
    )

    profile = profile_result.get("profile") or {}

    effective_plan = str(
        profile.get("plan") or "free"
    ).lower()

    monthly_limit = {
        "free": FREE_MONTHLY_CHAR_LIMIT,
        "standard": STANDARD_MONTHLY_CHAR_LIMIT,
        "special": SPECIAL_MONTHLY_CHAR_LIMIT,
        "vip": VIP_MONTHLY_CHAR_LIMIT
    }.get(
        effective_plan,
        FREE_MONTHLY_CHAR_LIMIT
    )

    characters_remaining = max(
        monthly_limit - characters_used,
        0
    )

    return {
        "ok": True,
        "month_start": month_start,
        "plan": effective_plan,
        "characters_used": characters_used,
        "monthly_limit": monthly_limit,
        "characters_remaining": characters_remaining
    }
@app.post("/api/payment/create")
def create_payment(
    data: PaymentCreateRequest,
    authorization: str | None = Header(default=None),
    user=Depends(require_user)
):
    plan = data.plan.strip().lower()
    months = data.months

    if plan not in {"standard", "special", "vip"}:
        raise HTTPException(
            status_code=400,
            detail="Gói nâng cấp không hợp lệ."
        )

    if months not in {1, 12, 24, 60}:
        raise HTTPException(
            status_code=400,
            detail="Thời hạn nâng cấp không hợp lệ."
        )

    access_token = authorization.split(" ", 1)[1].strip()

    try:
        response = httpx.post(
            f"{SUPABASE_URL}/functions/v1/create-payos-payment-v2",
            headers={
                "apikey": SUPABASE_PUBLISHABLE_KEY,
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            json={
                "plan": plan,
                "months": months
            },
            timeout=30.0
        )

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail="Không thể kết nối máy chủ thanh toán."
        ) from exc

    try:
        result = response.json()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Máy chủ thanh toán trả dữ liệu không hợp lệ."
        ) from exc

    if response.status_code >= 400 or not result.get("ok"):
        detail = (
            result.get("message")
            or "Không thể tạo đơn thanh toán."
        )

        status_code = (
            response.status_code
            if 400 <= response.status_code < 600
            else 502
        )

        raise HTTPException(
            status_code=status_code,
            detail=detail
        )

    return {
        "ok": True,
        "order_code": result.get("order_code"),
        "plan": result.get("plan"),
        "months": result.get("months"),
        "amount": result.get("amount"),
        "checkout_url": result.get("checkout_url"),
        "payment_link_id": result.get("payment_link_id")
    }
@app.get("/")
def home():
    return FileResponse(BASE_DIR / "index.html")
@app.get("/logo-voxviet.png")
def logo_voxviet():
    return FileResponse(
        BASE_DIR / "logo-voxviet.png",
        media_type="image/png"
    )


@app.get("/voxviet-ai.ico")
def voxviet_favicon():
    return FileResponse(
        BASE_DIR / "voxviet-ai.ico",
        media_type="image/x-icon"
    )
@app.get("/voxviet-icon.png")
def voxviet_icon_png():
    return FileResponse(
        BASE_DIR / "voxviet-icon.png",
        media_type="image/png"
    )
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "app": "VietDoc Local",
        "version": APP_VERSION,
        "diacritic_model": DIACRITIC_MODEL_ID
    }

@app.get("/api/update/check")
def check_for_update():
    try:
        response = httpx.get(
            UPDATE_MANIFEST_URL,
            params={
                "t": int(
                    datetime.now(timezone.utc).timestamp()
                )
            },
            timeout=10.0
        )

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail="Không thể kiểm tra bản cập nhật."
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail="Máy chủ cập nhật không phản hồi hợp lệ."
        )

    try:
        manifest = response.json()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Dữ liệu phiên bản cập nhật không hợp lệ."
        ) from exc

    latest_version = str(
        manifest.get("version") or ""
    ).strip()

    if not re.fullmatch(
        r"\d+\.\d+\.\d+",
        latest_version
    ):
        raise HTTPException(
            status_code=502,
            detail="Số phiên bản cập nhật không hợp lệ."
        )

    def version_tuple(value):
        return tuple(
            int(part)
            for part in value.split(".")
        )

    update_available = (
        version_tuple(latest_version)
        > version_tuple(APP_VERSION)
    )

    return {
        "ok": True,
        "current_version": APP_VERSION,
        "latest_version": latest_version,
        "update_available": update_available,
        "download_url": manifest.get("download_url") or "",
        "sha256": manifest.get("sha256") or "",
        "notes": manifest.get("notes") or "",
        "mandatory": bool(
            manifest.get("mandatory", False)
        )
    }


@app.post("/api/translate")
def translate_text(
    data: TranslationRequest,
    user=Depends(require_user)
):

    text = data.text.strip()

    if not text:
        raise HTTPException(
            status_code=400,
            detail="Chưa có văn bản để dịch."
        )

    directions = {
        "vi-en": ("vi", "en"),
        "en-vi": ("en", "vi")
    }

    language_pair = directions.get(
        data.direction
    )

    if language_pair is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Chỉ hỗ trợ dịch Việt → Anh "
                "và Anh → Việt."
            )
        )

    from_code, to_code = language_pair

    try:

        ensure_argos_pair(
            from_code,
            to_code
        )

        translated = argos_translate.translate(
            data.text,
            from_code,
            to_code
        )

        return {
            "text": translated,
            "direction": data.direction
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Không thể dịch văn bản. "
                "Vui lòng kiểm tra model dịch."
            )
        ) from exc
@app.get("/api/tts/voices")
def tts_voices(language: str = "vi"):
    try:
        if language == "en":
            return {
                "voices": [
                    {"id": "af_heart", "label": "Heart — Nữ — Mỹ"},
                    {"id": "af_bella", "label": "Bella — Nữ — Mỹ"},
                    {"id": "af_nicole", "label": "Nicole — Nữ — Mỹ"},
                    {"id": "am_michael", "label": "Michael — Nam — Mỹ"},
                    {"id": "bf_emma", "label": "Emma — Nữ — Anh"},
                    {"id": "bm_george", "label": "George — Nam — Anh"}
                ],
                "styles": [
                    {"id": "tu_nhien", "label": "Tự nhiên"}
                ]
            }
        engine = get_tts_engine()

        voices = [
            {
                "label": label,
                "id": voice_id
            }
            for label, voice_id in engine.list_preset_voices()
        ]

        return {
            "voices": voices,
            "styles": [
                {"id": "tu_nhien", "label": "Tự nhiên"},
                {"id": "tin_tuc", "label": "Tin tức"},
                {"id": "doc_truyen", "label": "Kể chuyện"}
            ]
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Không thể tải danh sách giọng AI."
        ) from exc


@app.post("/api/tts")
def text_to_speech(
    data: TTSRequest,
    authorization: str | None = Header(default=None),
    user=Depends(require_user)
):

    text = data.text.strip()

    if not text:
        raise HTTPException(
            status_code=400,
            detail="Chưa có văn bản để đọc."
        )

    allowed_styles = {
        "tu_nhien",
        "tin_tuc",
        "doc_truyen"
    }

    style = (
        data.style
        if data.style in allowed_styles
        else "tu_nhien"
    )

    try:
        with TTS_LOCK:
            if data.language == "en":
                voice_id = data.voice or "af_heart"

                lang_code = (
                    "b"
                    if voice_id.startswith(("bf_", "bm_"))
                    else "a"
                )

                pipeline = get_english_tts_engine(lang_code)

                generator = pipeline(
                    text,
                    voice=voice_id
                )

                audio_parts = [
                    item[2]
                    for item in generator
                ]

                if not audio_parts:
                    raise ValueError("Không tạo được âm thanh tiếng Anh.")

                import numpy as np

                audio = np.concatenate(audio_parts)
                sample_rate = 24000

            else:
                engine = get_tts_engine()

                audio = engine.infer(
                    text,
                    voice=data.voice or None,
                    style=style
                )

                sample_rate = engine.sample_rate

            import soundfile as sf

            buffer = io.BytesIO()

            sf.write(
                buffer,
                audio,
                sample_rate,
                format="WAV"
            )

            wav_bytes = buffer.getvalue()
        access_token = authorization.split(" ", 1)[1].strip()

        try:
            usage_response = httpx.post(
                f"{SUPABASE_URL}/rest/v1/rpc/consume_tts_usage",
                headers={
                    "apikey": SUPABASE_PUBLISHABLE_KEY,
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                },
                json={
                    "p_characters": len(text)
                },
                timeout=20.0
            )

        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=503,
                detail="Không thể kiểm tra hạn mức sử dụng."
            ) from exc

        if usage_response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail="Không thể kiểm tra hạn mức ký tự."
            )

        try:
            usage_result = usage_response.json()
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail="Dữ liệu hạn mức không hợp lệ."
            ) from exc

        if not usage_result.get("ok", False):
            remaining = int(
                usage_result.get("characters_remaining") or 0
            )

            raise HTTPException(
                status_code=429,
                detail=(
                    "Bạn đã vượt hạn mức ký tự tháng này. "
                    f"Hiện chỉ còn {remaining} ký tự."
                )
            )
        return Response(
            content=wav_bytes,
            media_type="audio/wav",
            headers={
                "Content-Disposition":
                    'inline; filename="voxviet-ai.wav"'
            }
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Không thể tạo giọng đọc AI. "
                "Vui lòng kiểm tra model TTS."
            )
        ) from exc
@app.post("/api/text/clean")
def clean_text(data: TextRequest):
    text = data.text

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?])([^\s\n])", r"\1 \2", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return {
        "text": text.strip()
    }


@app.post("/api/text/stats")
def text_stats(data: TextRequest):
    text = data.text

    words = re.findall(r"\S+", text)
    lines = text.splitlines()

    return {
        "characters": len(text),
        "characters_without_spaces": len(re.sub(r"\s", "", text)),
        "words": len(words),
        "lines": len(lines)
    }


@app.post("/api/text/uppercase")
def uppercase(data: TextRequest):
    return {
        "text": data.text.upper()
    }


@app.post("/api/text/lowercase")
def lowercase(data: TextRequest):
    return {
        "text": data.text.lower()
    }


@lru_cache(maxsize=1)
def get_diacritic_model():
    """
    Tải model khi người dùng sử dụng chức năng thêm dấu lần đầu.
    Model chỉ được giữ một bản trong bộ nhớ của container.
    """

    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

    tokenizer = AutoTokenizer.from_pretrained(
        DIACRITIC_MODEL_ID
    )

    model = AutoModelForSeq2SeqLM.from_pretrained(
        DIACRITIC_MODEL_ID
    )

    model.eval()

    return tokenizer, model


def split_long_sentence(text, max_words=70):
    """
    Chia câu quá dài thành các đoạn nhỏ để tránh vượt giới hạn model.
    """

    words = text.split()

    if len(words) <= max_words:
        return [text]

    chunks = []

    for i in range(0, len(words), max_words):
        chunks.append(
            " ".join(words[i:i + max_words])
        )

    return chunks


def restore_diacritics_piece(text, tokenizer, model):
    import torch

    clean = text.strip()

    if not clean:
        return text

    inputs = tokenizer(
        clean,
        return_tensors="pt",
        truncation=True,
        max_length=256
    )

    with torch.inference_mode():
        output = model.generate(
            **inputs,
            max_length=256,
            num_beams=1,
            do_sample=False
        )

    restored = tokenizer.decode(
        output[0],
        skip_special_tokens=True
    )

    return restored.strip()


def restore_diacritics_text(text):
    tokenizer, model = get_diacritic_model()

    output_lines = []

    for line in text.split("\n"):

        if not line.strip():
            output_lines.append("")
            continue

        sentence_parts = re.split(
            r"(?<=[.!?])\s+",
            line.strip()
        )

        restored_sentences = []

        for sentence in sentence_parts:

            chunks = split_long_sentence(sentence)

            restored_chunks = []

            for chunk in chunks:
                restored_chunks.append(
                    restore_diacritics_piece(
                        chunk,
                        tokenizer,
                        model
                    )
                )

            restored_sentences.append(
                " ".join(restored_chunks)
            )

        output_lines.append(
            " ".join(restored_sentences)
        )

    return "\n".join(output_lines)


@app.post("/api/text/diacritics")
def add_diacritics(data: TextRequest):

    text = data.text.strip()

    if not text:
        raise HTTPException(
            status_code=400,
            detail="Chưa có văn bản để thêm dấu."
        )

    try:
        restored = restore_diacritics_text(
            data.text
        )

        return {
            "text": restored,
            "model": DIACRITIC_MODEL_ID
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Không thể chạy chức năng thêm dấu. "
                "Vui lòng kiểm tra model hoặc kết nối mạng."
            )
        ) from exc
