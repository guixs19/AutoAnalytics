# api/support.py
# ==============================================
# 🔥 ENDPOINT DE SUPORTE - V3.0 (INTEGRADO AO SECURITY.PY)
# ==============================================
# Rota principal: POST /api/support/send
#
# INTEGRAÇÕES COM O SISTEMA EXISTENTE:
# 1. ✅ Reutiliza `rate_limiter` global do security.py
# 2. ✅ Reutiliza `check_redis_health` / `init_redis` do security.py
# 3. ✅ Reutiliza `_now_utc` / `_utc_timestamp` para timestamps consistentes
# 4. ✅ Usa `get_current_user` (opcional) para enriquecer com dados do usuário
# 5. ✅ Usa `get_current_admin_user` para proteger /stats e /test
# 6. ✅ Padrão de logging idêntico ao resto do sistema
#
# FUNCIONALIDADES PRÓPRIAS:
# - Honeypot anti-bot
# - Anti-spam heurístico
# - Bloqueio de emails descartáveis
# - Verificação de MX record (opcional)
# - Retry com backoff exponencial
# - Template HTML bonito + texto puro
# - Reply-To configurado
# - Fallback em arquivo se SMTP falhar
# - Health check sem autenticação
# ==============================================

import os
import re
import time
import json
import html
import smtplib
import logging
import asyncio
import hashlib
from datetime import timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path
from typing import Optional, Dict, List, Tuple

from fastapi import (
    APIRouter, HTTPException, Request, BackgroundTasks,
    Depends, Header, status,
)
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.orm import Session

# ==============================================
# 🔥 IMPORTS DO SISTEMA EXISTENTE
# ==============================================
from backend.security import (
    _now_utc,
    _utc_timestamp,
    rate_limiter,           # 🔥 reutiliza o rate limiter global
    check_redis_health,     # 🔥 reutiliza o health check do Redis
    init_redis,
    get_current_user,       # 🔥 opcional: enriquece com dados do usuário
    get_current_active_user,
    get_current_admin_user,
    get_db,
)
from backend.config.settings import settings as app_settings

# ==============================================
# 🔥 LOGGER (mesmo padrão do security.py)
# ==============================================

logger = logging.getLogger(__name__)

# Handler de arquivo para auditoria (opcional)
LOG_DIR = Path(os.getenv("SUPPORT_LOG_DIR", "logs"))
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _file_handler = logging.FileHandler(LOG_DIR / "support.log", encoding="utf-8")
    _file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    ))
    logger.addHandler(_file_handler)
except Exception as e:
    logger.warning(f"Não foi possível criar log em arquivo: {e}")


# ==============================================
# 🔥 DEPENDÊNCIAS OPCIONAIS (com fallback)
# ==============================================

try:
    import dns.resolver  # dnspython
    DNS_AVAILABLE = True
except ImportError:
    DNS_AVAILABLE = False


# ==============================================
# 🔥 CONFIGURAÇÕES ESPECÍFICAS DE SUPORTE
# ==============================================

class SupportSettings:
    """Configurações apenas do suporte (não duplica as do security.py)."""

    GMAIL_USER: str = os.getenv("GMAIL_USER", "autoanalyticss@gmail.com")
    GMAIL_APP_PASSWORD: str = os.getenv("GMAIL_APP_PASSWORD", "")
    SUPPORT_DESTINATION: str = os.getenv("SUPPORT_EMAIL", "autoanalyticss@gmail.com")
    SUPPORT_CC: str = os.getenv("SUPPORT_CC", "")
    SUPPORT_BCC: str = os.getenv("SUPPORT_BCC", "")

    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "465"))
    SMTP_TIMEOUT: int = int(os.getenv("SMTP_TIMEOUT", "20"))
    SMTP_MAX_RETRIES: int = int(os.getenv("SMTP_MAX_RETRIES", "3"))
    SMTP_RETRY_DELAY: float = float(os.getenv("SMTP_RETRY_DELAY", "2.0"))

    # 🔥 Rate limit específico do suporte (usa o rate_limiter global)
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("SUPPORT_RATE_LIMIT_PER_MINUTE", "3"))
    RATE_LIMIT_PER_HOUR: int = int(os.getenv("SUPPORT_RATE_LIMIT_PER_HOUR", "10"))
    RATE_LIMIT_PER_DAY: int = int(os.getenv("SUPPORT_RATE_LIMIT_PER_DAY", "30"))

    MAX_PAYLOAD_BYTES: int = int(os.getenv("SUPPORT_MAX_PAYLOAD_BYTES", "20000"))
    BLOCK_DISPOSABLE_EMAILS: bool = os.getenv("SUPPORT_BLOCK_DISPOSABLE", "true").lower() == "true"
    VERIFY_MX_RECORD: bool = os.getenv("SUPPORT_VERIFY_MX", "false").lower() == "true"

    FALLBACK_DIR: Path = Path(os.getenv("SUPPORT_FALLBACK_DIR", "logs/support_fallback"))


support_settings = SupportSettings()


# ==============================================
# 🔥 SCHEMA DE ENTRADA
# ==============================================

class SupportMessage(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    subject: str = Field(..., min_length=2, max_length=150)
    message: str = Field(..., min_length=5, max_length=5000)

    # Honeypot (deve vir vazio)
    website: Optional[str] = Field(default="", max_length=200)

    # Contexto opcional
    page_url: Optional[str] = Field(default="", max_length=500)
    user_agent: Optional[str] = Field(default="", max_length=500)
    plan: Optional[str] = Field(default="", max_length=50)

    @field_validator("name", "subject", "message")
    @classmethod
    def strip_and_sanitize(cls, v: str) -> str:
        v = v.strip()
        v = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", v)
        return v


# ==============================================
# 🔥 ANTI-SPAM (heurísticas)
# ==============================================

DISPOSABLE_DOMAINS = {
    "tempmail.com", "guerrillamail.com", "10minutemail.com", "mailinator.com",
    "throwaway.email", "yopmail.com", "trashmail.com", "fakeinbox.com",
    "sharklasers.com", "getnada.com", "temp-mail.org", "maildrop.cc",
    "dispostable.com", "tempr.email", "discard.email",
}

SPAM_KEYWORDS = [
    "viagra", "casino", "bitcoin giveaway", "free money", "click here now",
    "crypto airdrop", "nigerian prince", "work from home", "make $5000",
    "seo services", "backlinks", "buy followers",
]

SPAM_PATTERNS = [
    re.compile(r"(https?://\S+){4,}", re.IGNORECASE),
    re.compile(r"<script", re.IGNORECASE),
    re.compile(r"\{\{.*?\}\}"),
    re.compile(r"\$\{[^}]+\}"),
]


def _is_disposable_email(email: str) -> bool:
    domain = email.split("@")[-1].lower()
    return domain in DISPOSABLE_DOMAINS


def _has_mx_record(email: str) -> bool:
    if not DNS_AVAILABLE:
        return True
    domain = email.split("@")[-1]
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=5)
        return len(answers) > 0
    except Exception:
        return False


def _spam_score(payload: "SupportMessage") -> Tuple[int, List[str]]:
    score = 0
    reasons: List[str] = []
    full_text = f"{payload.subject} {payload.message}".lower()

    hits = [kw for kw in SPAM_KEYWORDS if kw in full_text]
    if hits:
        score += len(hits)
        reasons.append(f"palavras-chave: {hits}")

    for pat in SPAM_PATTERNS:
        if pat.search(payload.message) or pat.search(payload.subject):
            score += 2
            reasons.append(f"padrão: {pat.pattern}")

    link_count = len(re.findall(r"https?://", payload.message))
    if link_count >= 5:
        score += 2
        reasons.append(f"muitos links ({link_count})")

    if len(payload.message) < 10 and len(payload.subject) < 8:
        score += 1
        reasons.append("mensagem muito curta")

    if re.search(r"[0-9]{4,}", payload.name):
        score += 1
        reasons.append("nome com números")

    letters = [c for c in payload.message if c.isalpha()]
    if letters and sum(1 for c in letters if c.isupper()) / len(letters) > 0.7:
        score += 1
        reasons.append("CAPS excessivo")

    return score, reasons


# ==============================================
# 🔥 MÉTRICAS EM MEMÓRIA
# ==============================================

_metrics = {
    "success": 0,
    "failures": 0,
    "auth_failures": 0,
    "rate_limited": 0,
    "honeypot": 0,
    "spam_blocked": 0,
    "disposable_blocked": 0,
    "started_at": _now_utc().isoformat(),
}


# ==============================================
# 🔥 UTILITÁRIOS
# ==============================================

def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"


# ==============================================
# 🔥 GUARDA DE PROTEÇÕES
# ==============================================

async def _guard_request(request: Request, payload: SupportMessage) -> str:
    """
    Aplica todas as proteções. Retorna o IP se OK.
    Lança HTTPException caso contrário.

    🔥 INTEGRADO: usa `rate_limiter` global do security.py
    """
    ip = _client_ip(request)

    # 1. Honeypot
    if payload.website:
        logger.warning(f"🍯 Honeypot | IP={ip} | valor={payload.website!r}")
        raise HTTPException(status_code=200, detail="__honeypot__")

    # 2. Tamanho do payload
    raw_size = len(payload.model_dump_json().encode("utf-8"))
    if raw_size > support_settings.MAX_PAYLOAD_BYTES:
        logger.warning(f"📦 Payload grande | IP={ip} | {raw_size}b")
        raise HTTPException(status_code=413, detail="Mensagem muito grande.")

    # 3. 🔥 RATE LIMIT usando o rate_limiter GLOBAL do security.py
    #    Isso mantém consistência com o resto do sistema (Redis compartilhado)
    try:
        # minuto
        allowed = await rate_limiter.check_rate_limit(
            key=f"support:min:{ip}",
            max_requests=support_settings.RATE_LIMIT_PER_MINUTE,
            window=60,
        )
        if not allowed:
            _metrics["rate_limited"] += 1
            raise HTTPException(
                status_code=429,
                detail="Muitas mensagens em pouco tempo. Aguarde 1 minuto.",
                headers={"Retry-After": "60"},
            )

        # hora
        allowed = await rate_limiter.check_rate_limit(
            key=f"support:hour:{ip}",
            max_requests=support_settings.RATE_LIMIT_PER_HOUR,
            window=3600,
        )
        if not allowed:
            _metrics["rate_limited"] += 1
            raise HTTPException(
                status_code=429,
                detail="Limite por hora atingido. Aguarde e tente novamente.",
                headers={"Retry-After": "3600"},
            )

        # dia
        allowed = await rate_limiter.check_rate_limit(
            key=f"support:day:{ip}",
            max_requests=support_settings.RATE_LIMIT_PER_DAY,
            window=86400,
        )
        if not allowed:
            _metrics["rate_limited"] += 1
            raise HTTPException(
                status_code=429,
                detail="Limite diário atingido. Tente novamente amanhã.",
                headers={"Retry-After": "86400"},
            )
    except HTTPException:
        raise
    except Exception as e:
        # 🔥 Fallback seguro: se der erro no rate limiter, permite
        logger.error(f"⚠️ Erro no rate limit (permitindo): {e}")

    # 4. Email descartável
    if support_settings.BLOCK_DISPOSABLE_EMAILS and _is_disposable_email(payload.email):
        _metrics["disposable_blocked"] += 1
        logger.warning(f"🗑️ Email descartável | IP={ip} | {payload.email}")
        raise HTTPException(
            status_code=400,
            detail="Emails temporários não são aceitos. Use um email válido.",
        )

    # 5. MX record (opcional)
    if support_settings.VERIFY_MX_RECORD and not _has_mx_record(payload.email):
        logger.warning(f"📭 Sem MX | IP={ip} | {payload.email}")
        raise HTTPException(
            status_code=400,
            detail="Domínio de email inválido ou inexistente.",
        )

    # 6. Spam score
    score, reasons = _spam_score(payload)
    if score >= 3:
        _metrics["spam_blocked"] += 1
        logger.warning(f"🕵️ Spam | IP={ip} | score={score} | {reasons}")
        raise HTTPException(
            status_code=400,
            detail="Mensagem bloqueada por suspeita de spam.",
        )

    return ip


# ==============================================
# 🔥 TEMPLATES DE EMAIL
# ==============================================

def _render_text_template(
    payload: SupportMessage,
    ip: str,
    ua: str,
    user_context: Optional[Dict] = None,
) -> str:
    user_block = ""
    if user_context:
        user_block = f"""
👤 Usuário autenticado:
   • Nome:    {user_context.get('name', 'N/A')}
   • Email:   {user_context.get('email', 'N/A')}
   • Plano:   {user_context.get('plan', 'N/A')}
   • Créditos:{user_context.get('credits', 'N/A')}
   • Admin:   {user_context.get('is_admin', False)}
"""

    return f"""Nova mensagem de suporte - AutoAnalytics

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👤 Nome:     {payload.name}
📧 Email:    {payload.email}
📝 Assunto:  {payload.subject}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{user_block}
💬 Mensagem:
{payload.message}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌐 Contexto:
   • IP:         {ip}
   • User-Agent: {ua or "N/A"}
   • Página:     {payload.page_url or "N/A"}
   • Plano (front): {payload.plan or "N/A"}
   • Recebido:   {_now_utc().strftime("%Y-%m-%d %H:%M:%S UTC")}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Enviado automaticamente pelo formulário de suporte.
"""


def _render_html_template(
    payload: SupportMessage,
    ip: str,
    ua: str,
    user_context: Optional[Dict] = None,
) -> str:
    safe_name = html.escape(payload.name)
    safe_email = html.escape(payload.email)
    safe_subject = html.escape(payload.subject)
    safe_message = html.escape(payload.message).replace("\n", "<br>")
    safe_ip = html.escape(ip)
    safe_ua = html.escape(ua or "N/A")
    safe_page = html.escape(payload.page_url or "N/A")
    safe_plan = html.escape(payload.plan or "N/A")
    ts = _now_utc().strftime("%Y-%m-%d %H:%M:%S UTC")

    user_html = ""
    if user_context:
        user_html = f"""
      <div class="row">
        <div class="label">👤 Usuário autenticado</div>
        <div class="value">
          {html.escape(str(user_context.get('name', 'N/A')))} —
          {html.escape(str(user_context.get('email', 'N/A')))}<br>
          Plano: <strong>{html.escape(str(user_context.get('plan', 'N/A')))}</strong> |
          Créditos: <strong>{html.escape(str(user_context.get('credits', 'N/A')))}</strong>
          {'| 👑 ADMIN' if user_context.get('is_admin') else ''}
        </div>
      </div>"""

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: 'Inter', Arial, sans-serif; background: #000; color: #fff; margin:0; padding:0; }}
  .container {{ max-width: 640px; margin: 0 auto; background: linear-gradient(160deg, #0A1628 0%, #050A14 100%); border-radius: 16px; overflow: hidden; border: 1px solid rgba(0,180,255,0.25); }}
  .header {{ background: linear-gradient(135deg, #00B4FF, #0077B6); padding: 24px; text-align: center; }}
  .header h1 {{ margin: 0; color: #fff; font-size: 20px; font-weight: 800; }}
  .header p {{ margin: 4px 0 0; color: rgba(255,255,255,0.85); font-size: 12px; }}
  .body {{ padding: 24px; }}
  .row {{ margin-bottom: 14px; }}
  .label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: #00B4FF; font-weight: 700; margin-bottom: 4px; }}
  .value {{ font-size: 14px; color: #fff; background: rgba(255,255,255,0.04); padding: 10px 14px; border-radius: 10px; border: 1px solid rgba(0,180,255,0.15); word-break: break-word; }}
  .message {{ white-space: pre-wrap; line-height: 1.6; }}
  .meta {{ margin-top: 24px; padding-top: 18px; border-top: 1px solid rgba(0,180,255,0.15); font-size: 11px; color: rgba(255,255,255,0.4); }}
  .btn {{ display:inline-block; padding: 12px 22px; background: linear-gradient(135deg, #00B4FF, #0077B6); color: #fff !important; text-decoration: none; border-radius: 50px; font-weight: 700; font-size: 13px; margin-top: 18px; }}
</style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>📩 Nova mensagem de suporte</h1>
      <p>AutoAnalytics — Formulário de contato</p>
    </div>
    <div class="body">
      <div class="row">
        <div class="label">Nome</div>
        <div class="value">{safe_name}</div>
      </div>
      <div class="row">
        <div class="label">Email</div>
        <div class="value">{safe_email}</div>
      </div>
      <div class="row">
        <div class="label">Assunto</div>
        <div class="value">{safe_subject}</div>
      </div>
      {user_html}
      <div class="row">
        <div class="label">Mensagem</div>
        <div class="value message">{safe_message}</div>
      </div>

      <a href="mailto:{safe_email}?subject=Re: {safe_subject}" class="btn">
        ✉️ Responder diretamente
      </a>

      <div class="meta">
        <strong>🌐 Contexto</strong><br>
        IP: {safe_ip}<br>
        User-Agent: {safe_ua}<br>
        Página: {safe_page}<br>
        Plano (front): {safe_plan}<br>
        Recebido: {ts}
      </div>
    </div>
  </div>
</body>
</html>"""


# ==============================================
# 🔥 ENVIO DE EMAIL COM RETRY
# ==============================================

def _send_email_sync(
    payload: SupportMessage,
    ip: str,
    ua: str,
    user_context: Optional[Dict] = None,
) -> None:
    if not support_settings.GMAIL_APP_PASSWORD:
        raise RuntimeError("GMAIL_APP_PASSWORD não configurado")

    msg = MIMEMultipart("alternative")
    msg["From"] = formataddr(("AutoAnalytics Suporte", support_settings.GMAIL_USER))
    msg["To"] = support_settings.SUPPORT_DESTINATION
    msg["Subject"] = f"[Suporte] {payload.subject}"
    msg["Reply-To"] = formataddr((payload.name, payload.email))
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="autoanalytics.local")

    if support_settings.SUPPORT_CC:
        msg["Cc"] = support_settings.SUPPORT_CC
    if support_settings.SUPPORT_BCC:
        msg["Bcc"] = support_settings.SUPPORT_BCC

    msg.attach(MIMEText(
        _render_text_template(payload, ip, ua, user_context), "plain", "utf-8"
    ))
    msg.attach(MIMEText(
        _render_html_template(payload, ip, ua, user_context), "html", "utf-8"
    ))

    recipients = [support_settings.SUPPORT_DESTINATION]
    if support_settings.SUPPORT_CC:
        recipients += [e.strip() for e in support_settings.SUPPORT_CC.split(",") if e.strip()]
    if support_settings.SUPPORT_BCC:
        recipients += [e.strip() for e in support_settings.SUPPORT_BCC.split(",") if e.strip()]

    if support_settings.SMTP_PORT == 465:
        with smtplib.SMTP_SSL(
            support_settings.SMTP_HOST,
            support_settings.SMTP_PORT,
            timeout=support_settings.SMTP_TIMEOUT,
        ) as server:
            server.login(support_settings.GMAIL_USER, support_settings.GMAIL_APP_PASSWORD)
            server.send_message(msg, to_addrs=recipients)
    else:
        with smtplib.SMTP(
            support_settings.SMTP_HOST,
            support_settings.SMTP_PORT,
            timeout=support_settings.SMTP_TIMEOUT,
        ) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(support_settings.GMAIL_USER, support_settings.GMAIL_APP_PASSWORD)
            server.send_message(msg, to_addrs=recipients)


async def _send_email_with_retry(
    payload: SupportMessage,
    ip: str,
    ua: str,
    user_context: Optional[Dict] = None,
) -> None:
    last_error: Optional[Exception] = None

    for attempt in range(1, support_settings.SMTP_MAX_RETRIES + 1):
        try:
            await asyncio.to_thread(_send_email_sync, payload, ip, ua, user_context)
            logger.info(f"✅ Email enviado (tentativa {attempt})")
            _metrics["success"] += 1
            return
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"❌ Falha de autenticação SMTP: {e}")
            _metrics["auth_failures"] += 1
            raise
        except (smtplib.SMTPException, OSError, TimeoutError) as e:
            last_error = e
            logger.warning(f"⚠️ Tentativa {attempt}/{support_settings.SMTP_MAX_RETRIES}: {e}")
            if attempt < support_settings.SMTP_MAX_RETRIES:
                delay = support_settings.SMTP_RETRY_DELAY * (2 ** (attempt - 1))
                await asyncio.sleep(delay)

    _metrics["failures"] += 1
    raise RuntimeError(f"Falha após {support_settings.SMTP_MAX_RETRIES} tentativas: {last_error}")


# ==============================================
# 🔥 FALLBACK EM ARQUIVO
# ==============================================

def _save_fallback(
    payload: SupportMessage,
    ip: str,
    ua: str,
    error: str,
    user_context: Optional[Dict] = None,
) -> Path:
    support_settings.FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
    ts = _now_utc().strftime("%Y%m%d_%H%M%S")
    digest = hashlib.sha1(f"{payload.email}{ts}".encode()).hexdigest()[:8]
    filepath = support_settings.FALLBACK_DIR / f"support_{ts}_{digest}.json"

    data = {
        "received_at": _now_utc().isoformat(),
        "ip": ip,
        "user_agent": ua,
        "payload": payload.model_dump(),
        "user_context": user_context,
        "error": error,
    }
    filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.warning(f"💾 Fallback salvo: {filepath}")
    return filepath


# ==============================================
# 🔥 DEPENDÊNCIA OPCIONAL: usuário autenticado
# ==============================================

async def optional_current_user(request: Request) -> Optional[Dict]:
    """
    🔥 Retorna dados do usuário autenticado SE houver token válido,
    mas NÃO bloqueia se não houver (formulário é público).
    """
    try:
        auth_header = request.headers.get("authorization", "")
        if not auth_header:
            return None

        # Reutiliza a dependência do security.py
        from backend.security import jwt_manager
        token = jwt_manager.extract_token_from_header(auth_header)
        if not token:
            return None

        payload = await jwt_manager.verify_token(token)
        if not payload:
            return None

        return {
            "email": payload.get("email") or payload.get("sub"),
            "name": payload.get("name", ""),
            "plan": payload.get("plan", "basico"),
            "credits": payload.get("credits", 0),
            "is_admin": payload.get("is_admin", False),
        }
    except Exception as e:
        logger.debug(f"Não foi possível obter usuário autenticado: {e}")
        return None


# ==============================================
# 🔥 ROUTER
# ==============================================

router = APIRouter(prefix="/api/support", tags=["Suporte"])


# --------- ROTA PRINCIPAL ---------
@router.post("/send")
async def send_support_message(
    payload: SupportMessage,
    request: Request,
    background_tasks: BackgroundTasks,
    user_context: Optional[Dict] = Depends(optional_current_user),
):
    """
    Recebe mensagem do formulário de suporte e envia por email via Gmail.

    🔥 Público (não requer autenticação), mas se o usuário estiver logado,
    enriquece o email com os dados dele.
    """
    ip = _client_ip(request)
    ua = request.headers.get("user-agent", "")[:500]

    # 🔥 Aplica todas as proteções
    try:
        ip = await _guard_request(request, payload)
    except HTTPException as e:
        if e.detail == "__honeypot__":
            _metrics["honeypot"] += 1
            # Resposta fake pra enganar bots
            return {"success": True, "message": "Mensagem enviada com sucesso."}
        raise

    logger.info(
        f"📩 Suporte | IP={ip} | from={payload.email} | "
        f"user={user_context.get('email') if user_context else 'anônimo'} | "
        f"assunto={payload.subject!r}"
    )

    try:
        await _send_email_with_retry(payload, ip, ua, user_context)
        return {
            "success": True,
            "message": "Mensagem enviada com sucesso. Responderemos em breve.",
        }
    except smtplib.SMTPAuthenticationError:
        raise HTTPException(
            status_code=500,
            detail="Erro de autenticação no servidor de email.",
        )
    except Exception as e:
        try:
            _save_fallback(payload, ip, ua, str(e), user_context)
        except Exception as save_err:
            logger.error(f"❌ Falha no fallback: {save_err}")

        raise HTTPException(
            status_code=502,
            detail="Não foi possível enviar o email agora. Tente novamente em instantes.",
        )


# --------- HEALTH CHECK ---------
@router.get("/health")
async def support_health():
    """
    Verifica se o serviço de email está configurado.
    🔥 Público (não expõe credenciais).
    """
    configured = bool(support_settings.GMAIL_APP_PASSWORD) and bool(support_settings.GMAIL_USER)

    redis_ok = False
    try:
        redis_ok = await check_redis_health()
    except Exception:
        pass

    result = {
        "status": "ok" if configured else "misconfigured",
        "smtp_host": support_settings.SMTP_HOST,
        "smtp_port": support_settings.SMTP_PORT,
        "gmail_user_set": bool(support_settings.GMAIL_USER),
        "app_password_set": bool(support_settings.GMAIL_APP_PASSWORD),
        "destination": support_settings.SUPPORT_DESTINATION,
        "dns_available": DNS_AVAILABLE,
        "redis_available": redis_ok,
        "verify_mx": support_settings.VERIFY_MX_RECORD,
        "block_disposable": support_settings.BLOCK_DISPOSABLE_EMAILS,
        "rate_limits": {
            "per_minute": support_settings.RATE_LIMIT_PER_MINUTE,
            "per_hour": support_settings.RATE_LIMIT_PER_HOUR,
            "per_day": support_settings.RATE_LIMIT_PER_DAY,
        },
    }

    if configured:
        try:
            if support_settings.SMTP_PORT == 465:
                with smtplib.SMTP_SSL(
                    support_settings.SMTP_HOST,
                    support_settings.SMTP_PORT,
                    timeout=5,
                ) as s:
                    s.noop()
            else:
                with smtplib.SMTP(
                    support_settings.SMTP_HOST,
                    support_settings.SMTP_PORT,
                    timeout=5,
                ) as s:
                    s.ehlo()
            result["smtp_connection"] = "ok"
        except Exception as e:
            result["smtp_connection"] = f"error: {e}"
            result["status"] = "degraded"

    return result


# --------- ESTATÍSTICAS (admin) ---------
@router.get("/stats")
async def support_stats(
    current_user = Depends(get_current_admin_user),  # 🔥 reutiliza do security.py
):
    """
    Métricas de uso. 🔥 Requer admin autenticado.
    """
    uptime = _now_utc() - _now_utc().fromisoformat(_metrics["started_at"])
    return {
        "uptime_seconds": int(uptime.total_seconds()),
        "metrics": dict(_metrics),
        "rate_limits": {
            "per_minute": support_settings.RATE_LIMIT_PER_MINUTE,
            "per_hour": support_settings.RATE_LIMIT_PER_HOUR,
            "per_day": support_settings.RATE_LIMIT_PER_DAY,
        },
        "requested_by": current_user.email,
    }


# --------- TESTE DE ENVIO (admin) ---------
@router.post("/test")
async def support_test(
    current_user = Depends(get_current_admin_user),  # 🔥 reutiliza do security.py
):
    """Envia email de teste. 🔥 Requer admin autenticado."""
    fake = SupportMessage(
        name="Teste AutoAnalytics",
        email=current_user.email,  # 🔥 envia pro admin que pediu
        subject="Teste de configuração SMTP",
        message="Se você recebeu este email, o endpoint de suporte está funcionando.",
    )
    try:
        await _send_email_with_retry(
            fake,
            ip="127.0.0.1",
            ua="support-test",
            user_context={
                "email": current_user.email,
                "name": current_user.name,
                "is_admin": True,
            },
        )
        return {"success": True, "message": f"Email de teste enviado para {current_user.email}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha no teste: {e}")


# --------- LISTAR FALLBACKS (admin) ---------
@router.get("/fallbacks")
async def list_fallbacks(
    current_user = Depends(get_current_admin_user),
):
    """
    Lista mensagens salvas em fallback (que não conseguiram ser enviadas).
    🔥 Requer admin.
    """
    if not support_settings.FALLBACK_DIR.exists():
        return {"count": 0, "items": []}

    items = []
    for fp in sorted(support_settings.FALLBACK_DIR.glob("support_*.json"), reverse=True)[:50]:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            items.append({
                "file": fp.name,
                "received_at": data.get("received_at"),
                "email": data.get("payload", {}).get("email"),
                "subject": data.get("payload", {}).get("subject"),
                "error": data.get("error", "")[:200],
            })
        except Exception:
            continue

    return {"count": len(items), "items": items}


# ==============================================
# 🔥 EXPORTAÇÕES
# ==============================================

__all__ = ["router"]

logger.info("✅ api/support.py v3.0 carregado (integrado ao security.py)")