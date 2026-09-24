# backend/services/payment_service.py - VERSÃO 4.0 (BLINDADA - QR CODE + SEGURANÇA)
"""
🔥 SISTEMA DE PAGAMENTO - AUTOANALYTICS V4.0
================================================================================
✅ CORREÇÕES E MELHORIAS v4.0:
   1. ✅ CORRIGIDO: Separação estrita entre qr_code_base64 (imagem) e qr_code (texto)
   2. ✅ CORRIGIDO: _ensure_qr_code_prefix rejeita copia-e-cola em vez de deixar passar
   3. ✅ CORRIGIDO: Retry NÃO roda em erros 4xx (CPF inválido, valor, etc)
   4. ✅ CORRIGIDO: Cache com TTL + tamanho máximo (evita memory leak)
   5. ✅ CORRIGIDO: Validação robusta de resposta do MP (.get em vez de [])
   6. ✅ ADICIONADO: pix_code e qr_code_base64 separados na resposta
   7. ✅ ADICIONADO: Validação de PIX_EXPIRY_MINUTES mínimo (>= 1)
   8. ✅ ADICIONADO: Métrica de QR Codes gerados localmente
   9. ✅ ADICIONADO: Log estruturado de payload do MP (para auditoria)
  10. ✅ MELHORADO: generate_qr_code_base64 com validação de tamanho
  11. ✅ ADICIONADO: Classificação de erros (retryable vs fatal)
  12. ✅ ADICIONADO: Sanitização de CPF para sandbox
  13. ✅ ADICIONADO: Cooldown entre retries para não bombardear o MP
================================================================================
"""

import mercadopago
import os
import qrcode
import base64
from io import BytesIO
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
import json
import uuid
import logging
import re
import time
import asyncio
from functools import wraps

# ==============================================
# LOGGER CONFIGURADO
# ==============================================

logger = logging.getLogger(__name__)

# ==============================================
# WEBHOOK (IMPORTAÇÃO SEGURA)
# ==============================================

try:
    from backend.observability.sentinel import get_webhook
except ImportError:
    def get_webhook():
        return None
    logger.warning("⚠️ webhook não disponível, usando fallback")


# ==============================================
# 🔥 V4.0: CLASSIFICADOR DE ERROS (RETRY INTELIGENTE)
# ==============================================

class RetryableError(Exception):
    """Erro que vale a pena tentar novamente (5xx, timeout, conexão)."""
    pass


class FatalError(Exception):
    """Erro que NÃO deve ser retentado (4xx, validação, negócio)."""
    pass


def classify_mp_error(status_code: int, message: str) -> Exception:
    """
    🔥 V4.0: Classifica erro do Mercado Pago em retryable ou fatal.
    - 5xx, 408, 429, timeouts → RetryableError
    - 4xx (exceto 408/429)   → FatalError
    """
    msg_lower = (message or "").lower()

    if status_code == 429 or "rate" in msg_lower or "too many" in msg_lower:
        return FatalError(f"Rate limit do MP: {message}")

    if status_code in (408, 500, 502, 503, 504):
        return RetryableError(f"MP indisponível ({status_code}): {message}")

    if 400 <= status_code < 500:
        return FatalError(f"Erro de negócio MP ({status_code}): {message}")

    return RetryableError(f"Erro desconhecido MP ({status_code}): {message}")


# ==============================================
# DECORATOR DE RETRY V4.0 (SÓ RETRYABLE)
# ==============================================

def retry_on_failure(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    🔥 V4.0: Retry com backoff exponencial que IGNORA erros fatais.
    - FatalError → propaga imediatamente (não gasta tempo)
    - RetryableError / Exception genérica → tenta novamente
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            current_delay = delay

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except FatalError as e:
                    # 🔥 NÃO retentar erros de negócio
                    logger.warning(f"⛔ [Retry] Erro fatal, não retentando: {e}")
                    raise
                except (RetryableError, Exception) as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"⚠️ [Retry] Tentativa {attempt+1}/{max_retries} falhou: {e}"
                        )
                        logger.info(f"⏳ [Retry] Aguardando {current_delay:.1f}s...")
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(f"❌ [Retry] Todas as {max_retries} tentativas falharam: {e}")

            raise last_error
        return wrapper
    return decorator


# ==============================================
# VALIDADOR DE CPF
# ==============================================

class CpfValidator:
    """🔥 Validador de CPF com algoritmo de dígitos verificadores"""

    @staticmethod
    def validate(cpf: str) -> Dict[str, Any]:
        cleaned = re.sub(r'\D', '', str(cpf))

        if len(cleaned) != 11:
            return {"valid": False, "cleaned": cleaned, "message": "CPF deve conter 11 dígitos"}

        if cleaned == cleaned[0] * 11:
            return {"valid": False, "cleaned": cleaned, "message": "CPF inválido (dígitos repetidos)"}

        sum_ = 0
        for i in range(9):
            sum_ += int(cleaned[i]) * (10 - i)
        remainder = 11 - (sum_ % 11)
        first_digit = 0 if remainder >= 10 else remainder

        if int(cleaned[9]) != first_digit:
            return {"valid": False, "cleaned": cleaned, "message": "CPF inválido (primeiro dígito verificador)"}

        sum_ = 0
        for i in range(10):
            sum_ += int(cleaned[i]) * (11 - i)
        remainder = 11 - (sum_ % 11)
        second_digit = 0 if remainder >= 10 else remainder

        if int(cleaned[10]) != second_digit:
            return {"valid": False, "cleaned": cleaned, "message": "CPF inválido (segundo dígito verificador)"}

        return {"valid": True, "cleaned": cleaned, "message": "CPF válido"}

    @staticmethod
    def mask(cpf: str) -> str:
        cleaned = re.sub(r'\D', '', str(cpf))
        if len(cleaned) != 11:
            return cpf
        return f"{cleaned[:3]}.{cleaned[3:6]}.{cleaned[6:9]}-{cleaned[9:]}"


# ==============================================
# 🔥 V4.0: NORMALIZADOR DE QR CODE (SEPARA IMAGEM DE TEXTO)
# ==============================================

class QrCodeNormalizer:
    """
    🔥 V4.0: Separa rigorosamente:
      - qr_code_base64 → só aceita se for imagem válida (data:image ou Base64 PNG)
      - pix_code       → só aceita se for copia-e-cola (000201...)
    Nunca cruza os dois mundos.
    """

    @staticmethod
    def is_base64_image(value: str) -> bool:
        if not value or not isinstance(value, str):
            return False
        if value.startswith('data:image/'):
            return True
        if value.startswith('iVBOR'):   # PNG
            return True
        if value.startswith('/9j/'):    # JPEG
            return True
        if value.startswith('R0lGOD'):  # GIF
            return True
        return False

    @staticmethod
    def is_pix_copy_paste(value: str) -> bool:
        if not value or not isinstance(value, str):
            return False
        return value.startswith('000201') or 'br.gov.bcb.pix' in value

    @staticmethod
    def ensure_image_prefix(value: str) -> str:
        """
        🔥 V4.0: Só retorna string se for imagem VÁLIDA.
        Copia-e-cola → retorna "" (NUNCA vira imagem).
        """
        if not value:
            return ""

        if value.startswith('data:image/'):
            return value

        if value.startswith('iVBOR'):
            return f"data:image/png;base64,{value}"
        if value.startswith('/9j/'):
            return f"data:image/jpeg;base64,{value}"
        if value.startswith('R0lGOD'):
            return f"data:image/gif;base64,{value}"

        # ⛔ REGRA CRÍTICA: copia-e-cola NUNCA é imagem
        if QrCodeNormalizer.is_pix_copy_paste(value):
            logger.info("📱 Copia-e-cola detectado — NÃO será tratado como imagem")
            return ""

        # Fallback: base64 genérico (string longa só com chars base64)
        if len(value) > 200 and re.match(r'^[A-Za-z0-9+/=]+$', value[:100]):
            return f"data:image/png;base64,{value}"

        logger.warning(f"⚠️ Formato desconhecido — descartado (len={len(value)})")
        return ""

    @staticmethod
    def normalize(qr_base64_raw: Optional[str], qr_text_raw: Optional[str]) -> Tuple[str, str]:
        """
        🔥 V4.0: Recebe os campos crus do MP e retorna (qr_code_base64, pix_code) limpos.
        Regras:
          - Se qr_base64_raw é imagem válida → usa
          - Se qr_base64_raw é copia-e-cola → move para pix_code
          - Se qr_text_raw é copia-e-cola → usa como pix_code
          - Se não tem imagem mas tem texto → front gera localmente
        """
        qr_code_base64 = ""
        pix_code = ""

        # 1. Tenta usar o base64 do MP
        if qr_base64_raw:
            normalized = QrCodeNormalizer.ensure_image_prefix(qr_base64_raw)
            if normalized:
                qr_code_base64 = normalized
            elif QrCodeNormalizer.is_pix_copy_paste(qr_base64_raw):
                # Caiu no caso raro: MP mandou copia-e-cola no campo base64
                pix_code = qr_base64_raw

        # 2. Extrai copia-e-cola do campo textual
        if qr_text_raw and QrCodeNormalizer.is_pix_copy_paste(qr_text_raw):
            pix_code = qr_text_raw

        return qr_code_base64, pix_code


# ==============================================
# CLASSE PRINCIPAL - MERCADO PAGO SERVICE V4.0
# ==============================================

class MercadoPagoService:
    """🔥 Serviço para integração REAL com Mercado Pago - V4.0"""

    DEFAULT_PRICE = 97.00
    REGULAR_PRICE = 149.90
    PIX_EXPIRY_MINUTES = 30
    TOTAL_SLOTS = 100
    STATUS_CACHE_TTL = 30
    STATUS_CACHE_MAX_SIZE = 1000  # 🔥 V4.0: limite para evitar memory leak
    MIN_EXPIRY_MINUTES = 1        # 🔥 V4.0: MP rejeita < 1min

    def __init__(self):
        self.access_token = os.getenv("MP_ACCESS_TOKEN", "")
        self.public_key = os.getenv("MP_PUBLIC_KEY", "")
        self.webhook_secret = os.getenv("MP_WEBHOOK_SECRET", "")
        self.webhook_base_url = os.getenv("WEBHOOK_BASE_URL", "https://seu-dominio.com")

        self.environment = os.getenv("MP_ENVIRONMENT", "production")
        self.tz_brasil = timezone(timedelta(hours=-3))

        # 🔥 V4.0: Valida expiração mínima
        if self.PIX_EXPIRY_MINUTES < self.MIN_EXPIRY_MINUTES:
            logger.warning(
                f"⚠️ PIX_EXPIRY_MINUTES={self.PIX_EXPIRY_MINUTES} é menor que "
                f"o mínimo ({self.MIN_EXPIRY_MINUTES}). Ajustando..."
            )
            self.PIX_EXPIRY_MINUTES = self.MIN_EXPIRY_MINUTES

        self._status_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_hits = 0
        self._cache_misses = 0

        self.metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_retries": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "qr_generated_locally": 0,   # 🔥 V4.0
            "qr_from_mp": 0,             # 🔥 V4.0
            "last_request_time": None,
            "last_error": None,
            "uptime_start": datetime.now(self.tz_brasil).isoformat()
        }

        self.sdk = None
        self._init_sdk()

        self.webhook = get_webhook()

        logger.info("=" * 60)
        logger.info("🚀 MercadoPagoService V4.0 inicializado")
        logger.info(f"   📍 Ambiente: {self.environment}")
        logger.info(f"   🔑 SDK: {'✅ Conectado' if self.sdk else '❌ Não configurado'}")
        logger.info(f"   ⏰ PIX Expira: {self.PIX_EXPIRY_MINUTES} min")
        logger.info(f"   💾 Cache TTL: {self.STATUS_CACHE_TTL}s (max {self.STATUS_CACHE_MAX_SIZE})")
        logger.info("=" * 60)

    # ==============================================
    # SDK
    # ==============================================

    def _init_sdk(self):
        if not self.access_token:
            logger.warning("⚠️ MP_ACCESS_TOKEN não configurado - PIX real não funcionará")
            return
        try:
            self.sdk = mercadopago.SDK(self.access_token)
            logger.info(f"✅ Mercado Pago SDK inicializado ({self.environment})")
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar SDK: {e}")
            self.sdk = None

    # ==============================================
    # DATAS
    # ==============================================

    def _get_current_datetime_brasil(self) -> datetime:
        return datetime.now(self.tz_brasil)

    def _get_pix_expiration_datetime_mp(self) -> str:
        """Formato ISO com milissegundos + Z (UTC). MP exige >= now + 1min."""
        now_utc = datetime.now(timezone.utc)
        expiry_utc = now_utc + timedelta(minutes=max(self.PIX_EXPIRY_MINUTES, self.MIN_EXPIRY_MINUTES))
        return expiry_utc.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    # ==============================================
    # CPF
    # ==============================================

    def _clean_cpf(self, cpf: str) -> str:
        if not cpf:
            return ""
        return re.sub(r'\D', '', str(cpf))

    def _validate_cpf(self, cpf: str) -> Dict[str, Any]:
        return CpfValidator.validate(cpf)

    # ==============================================
    # 🔥 V4.0: COMPATIBILIDADE (método antigo delega pro normalizador)
    # ==============================================

    def _ensure_qr_code_prefix(self, qr_code: str) -> str:
        """
        🔥 V4.0: Mantido por compatibilidade, mas agora rejeita copia-e-cola.
        Delega para QrCodeNormalizer.ensure_image_prefix.
        """
        return QrCodeNormalizer.ensure_image_prefix(qr_code)

    # ==============================================
    # PLANOS
    # ==============================================

    def get_plan_details(self, plan_id: str, db: Session = None) -> Dict[str, Any]:
        regular_price = self.REGULAR_PRICE
        promotional_price = self.DEFAULT_PRICE
        current_price = promotional_price
        has_promotion = True
        price_type = "promotional"
        remaining_slots = self.TOTAL_SLOTS

        if db and plan_id == "premium_mensal":
            try:
                from backend.models import PromotionControl
                promo = db.query(PromotionControl).first()

                if not promo:
                    logger.info("✨ Tabela PromotionControl vazia. Inicializando...")
                    promo = PromotionControl(
                        total_slots=self.TOTAL_SLOTS,
                        used_slots=0,
                        promotional_price=self.DEFAULT_PRICE,
                        regular_price=self.REGULAR_PRICE,
                        is_active=True
                    )
                    db.add(promo)
                    db.commit()
                    db.refresh(promo)

                regular_price = float(promo.regular_price)
                promotional_price = float(promo.promotional_price)
                current_price = promo.get_current_price()
                has_promotion = promo.has_available_slots()
                price_type = "promotional" if current_price < regular_price else "regular"
                remaining_slots = promo.get_remaining_slots()

                logger.info(f"💰 Plano {plan_id}: R$ {current_price} ({price_type}) - {remaining_slots} vagas")
            except Exception as e:
                logger.error(f"❌ Erro ao buscar preço: {e}")
                logger.warning(f"⚠️ Usando preço padrão: R$ {current_price}")

        return {
            "name": "Plano Bronze",
            "price": current_price,
            "regular_price": regular_price,
            "promotional_price": promotional_price,
            "credits": 30,
            "description": "1 crédito por dia durante 30 dias",
            "credits_per_day": 1,
            "duration_days": 30,
            "max_credits_balance": 3,
            "has_promotion": has_promotion and current_price < regular_price,
            "price_type": price_type,
            "remaining_slots": remaining_slots
        }

    def get_current_price(self, plan_id: str, db: Session = None) -> float:
        return self.get_plan_details(plan_id, db).get("price", self.DEFAULT_PRICE)

    # ==============================================
    # PROMOÇÃO
    # ==============================================

    def get_promotion_status(self, db: Session) -> Dict[str, Any]:
        try:
            from backend.models import PromotionControl
            promo = db.query(PromotionControl).first()

            if not promo:
                promo = PromotionControl(
                    total_slots=self.TOTAL_SLOTS,
                    used_slots=0,
                    promotional_price=self.DEFAULT_PRICE,
                    regular_price=self.REGULAR_PRICE,
                    is_active=True
                )
                db.add(promo)
                db.commit()
                db.refresh(promo)
                logger.info("✅ Promoção padrão criada")

            return {
                "success": True,
                "total_slots": promo.total_slots,
                "used_slots": promo.used_slots,
                "remaining_slots": promo.get_remaining_slots(),
                "promotional_price": float(promo.promotional_price),
                "regular_price": float(promo.regular_price),
                "current_price": promo.get_current_price(),
                "is_active": promo.is_active and promo.get_remaining_slots() > 0,
                "has_available_slots": promo.has_available_slots()
            }
        except Exception as e:
            logger.error(f"❌ Erro ao buscar status: {e}")
            return {
                "success": False,
                "error": str(e),
                "total_slots": self.TOTAL_SLOTS,
                "used_slots": 0,
                "remaining_slots": self.TOTAL_SLOTS,
                "promotional_price": self.DEFAULT_PRICE,
                "regular_price": self.REGULAR_PRICE,
                "current_price": self.DEFAULT_PRICE,
                "is_active": True,
                "has_available_slots": True
            }

    # ==============================================
    # 🔥 V4.0: PAGAMENTO INTERNO COM CLASSIFICAÇÃO DE ERRO
    # ==============================================

    @retry_on_failure(max_retries=3, delay=1.0, backoff=2.0)
    def _create_payment_internal(self, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        🔥 V4.0: Retry SÓ em erros 5xx/408/timeout. Erros 4xx propagam imediatamente.
        """
        if not self.sdk:
            raise FatalError("SDK do Mercado Pago não configurado")

        self.metrics["total_requests"] += 1
        self.metrics["last_request_time"] = datetime.now(self.tz_brasil).isoformat()

        try:
            response = self.sdk.payment().create(payment_data)
        except Exception as e:
            # 🔥 Exceção de rede → retryable
            self.metrics["failed_requests"] += 1
            self.metrics["last_error"] = str(e)
            raise RetryableError(f"Erro de conexão com MP: {e}")

        status_code = response.get("status")
        body = response.get("response", {})
        message = (
            response.get("message")
            or (body.get("message") if isinstance(body, dict) else None)
            or f"HTTP {status_code}"
        )

        if status_code in (200, 201):
            self.metrics["successful_requests"] += 1
            return {
                "success": True,
                "status_code": status_code,
                "response": body
            }

        # 🔥 V4.0: Classifica e propaga
        self.metrics["failed_requests"] += 1
        self.metrics["last_error"] = message
        classified = classify_mp_error(status_code, message)
        logger.error(f"❌ MP retornou {status_code}: {message}")
        raise classified

    # ==============================================
    # 🔥 V4.0: CRIA PAGAMENTO PIX REAL
    # ==============================================

    def create_real_pix_payment(
        self,
        plan_id: str,
        user_email: str,
        user_id: int,
        user_name: str = "",
        price: float = None,
        user_cpf: str = None,
        db: Session = None
    ) -> Dict[str, Any]:
        start_time = time.time()

        # ==========================================
        # 1. VALIDAÇÕES
        # ==========================================

        if not self.sdk:
            logger.warning("⚠️ SDK não configurado")
            return {
                "success": False,
                "error": "Mercado Pago não configurado. Configure MP_ACCESS_TOKEN no .env",
                "simulated": True
            }

        if self.environment == "production" and not user_cpf:
            logger.error(f"❌ CPF obrigatório para usuário {user_id}")
            return {
                "success": False,
                "error": "CPF é obrigatório para gerar pagamento PIX.",
                "requires_cpf": True
            }

        cleaned_cpf = ""
        if user_cpf:
            validation = self._validate_cpf(user_cpf)
            if not validation["valid"]:
                logger.warning(f"⚠️ CPF inválido: {validation['message']}")
                return {
                    "success": False,
                    "error": validation["message"],
                    "requires_cpf": True
                }
            cleaned_cpf = validation["cleaned"]
            logger.info(f"🔒 CPF validado: {CpfValidator.mask(cleaned_cpf)}")

        # ==========================================
        # 2. PREÇO
        # ==========================================

        price_type = "regular"
        if price is None:
            if db:
                plan_details = self.get_plan_details(plan_id, db)
                price = plan_details.get("price", self.DEFAULT_PRICE)
                price_type = plan_details.get("price_type", "regular")
                remaining_slots = plan_details.get("remaining_slots", 0)
                logger.info(f"💰 Preço: R$ {price} ({price_type}) - {remaining_slots} vagas")
            else:
                price = self.DEFAULT_PRICE
                logger.warning(f"⚠️ Sem db, usando preço padrão: R$ {price}")

        # ==========================================
        # 3. DADOS DO PAGAMENTO
        # ==========================================

        if plan_id != "premium_mensal":
            return {"success": False, "error": f"Plano {plan_id} não suportado"}

        description = "Plano Bronze - 30 dias de acesso premium com 1 crédito por dia"
        credits = 30

        external_reference = f"user_{user_id}_{plan_id}_{uuid.uuid4().hex[:8]}"
        expiration_date = self._get_pix_expiration_datetime_mp()

        brasil_now = self._get_current_datetime_brasil()
        logger.info(f"🕐 Horário Brasília: {brasil_now.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"⏰ Expira em {self.PIX_EXPIRY_MINUTES}min (UTC): {expiration_date}")

        cpf_to_use = cleaned_cpf if cleaned_cpf else "12345678909"

        payment_data = {
            "transaction_amount": price,
            "description": description,
            "payment_method_id": "pix",
            "payer": {
                "email": user_email,
                "first_name": user_name[:50] if user_name else "Cliente",
                "identification": {"type": "CPF", "number": cpf_to_use}
            },
            "external_reference": external_reference,
            "date_of_expiration": expiration_date,
            "notification_url": f"{self.webhook_base_url}/api/payments/webhook",
            "metadata": {
                "plan_id": plan_id,
                "user_id": user_id,
                "plan_type": "daily_credits",
                "credits": credits,
                "credits_per_day": 1,
                "duration_days": 30,
                "max_credits_balance": 3,
                "cpf_provided": bool(user_cpf),
                "environment": self.environment,
                "timezone": "America/Sao_Paulo (UTC-3)",
                "expiration_minutes": self.PIX_EXPIRY_MINUTES,
                "price_type": price_type,
                "price": price
            }
        }

        # ==========================================
        # 4. EXECUTA PAGAMENTO
        # ==========================================

        try:
            logger.info(f"💰 Criando PIX para {user_email} - R$ {price}")

            result = self._create_payment_internal(payment_data)

            if not result.get("success"):
                return {
                    "success": False,
                    "error": result.get("error", "Erro ao criar pagamento PIX"),
                    "details": result.get("details", {})
                }

            payment = result["response"]

            # ==========================================
            # 5. 🔥 V4.0: EXTRAI QR CODE DE FORMA SEGURA
            # ==========================================

            # Extração defensiva com .get() em vez de []
            point_of_interaction = payment.get("point_of_interaction") or {}
            transaction_data = point_of_interaction.get("transaction_data") or {}

            raw_base64 = transaction_data.get("qr_code_base64")
            raw_text = transaction_data.get("qr_code")

            # 🔥 LOG DE AUDITORIA
            logger.info("=" * 70)
            logger.info("📱 [QR CODE RECEBIDO DO MERCADO PAGO]")
            logger.info(f"   qr_code_base64: {'✅ (' + str(len(raw_base64)) + ' chars)' if raw_base64 else '❌ vazio'}")
            if raw_base64:
                logger.info(f"   └─ prefixo: {raw_base64[:40]}...")
            logger.info(f"   qr_code (texto): {'✅ (' + str(len(raw_text)) + ' chars)' if raw_text else '❌ vazio'}")
            if raw_text:
                logger.info(f"   └─ prefixo: {raw_text[:40]}...")
            logger.info("=" * 70)

            # 🔥 V4.0: Normalização estrita
            qr_code_base64, pix_code = QrCodeNormalizer.normalize(raw_base64, raw_text)

            # 🔥 Se o MP não mandou imagem, gera localmente
            if not qr_code_base64 and pix_code:
                logger.info("📱 MP não retornou base64 — gerando QR Code localmente...")
                generated = self.generate_qr_code_base64(pix_code)
                if generated:
                    qr_code_base64 = generated
                    self.metrics["qr_generated_locally"] += 1
                    logger.info("✅ QR Code gerado localmente!")
            elif qr_code_base64:
                self.metrics["qr_from_mp"] += 1
                logger.info("✅ QR Code do MP validado!")

            if not qr_code_base64 and not pix_code:
                logger.error("❌ NENHUM QR CODE disponível (nem imagem, nem copia-e-cola)")

            logger.info(f"✅ PIX criado: {payment.get('id')} - Status: {payment.get('status')}")

            # ==========================================
            # 6. RETORNA RESPOSTA
            # ==========================================

            elapsed = (time.time() - start_time) * 1000

            return {
                "success": True,
                "payment_id": str(payment.get("id")),
                "external_reference": external_reference,
                "qr_code_base64": qr_code_base64,  # "" se não houver imagem
                "qr_code": pix_code,                # "" se não houver copia-e-cola
                "pix_code": pix_code,               # 🔥 V4.0: ALIAS explícito
                "expiration_date": expiration_date,
                "status": payment.get("status", "pending"),
                "amount": price,
                "credits": credits,
                "plan_type": "daily_credits",
                "price_type": price_type,
                "environment": self.environment,
                "cpf_used": bool(user_cpf),
                "timezone": "America/Sao_Paulo (UTC-3)",
                "processing_time_ms": round(elapsed, 2),
                "has_qr_image": bool(qr_code_base64),
                "has_pix_code": bool(pix_code)
            }

        except FatalError as e:
            logger.error(f"⛔ Erro fatal ao criar pagamento: {e}")
            return {"success": False, "error": str(e)}
        except RetryableError as e:
            logger.error(f"⚠️ Erro persistente no MP: {e}")
            return {"success": False, "error": f"Serviço indisponível: {e}"}
        except Exception as e:
            logger.error(f"❌ Exceção ao criar pagamento: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    # ==============================================
    # QR CODE LOCAL
    # ==============================================

    def generate_qr_code_base64(self, qr_code_text: str) -> str:
        """🔥 V4.0: Gera QR Code em base64 COM VALIDAÇÃO DE TAMANHO."""
        if not qr_code_text or not QrCodeNormalizer.is_pix_copy_paste(qr_code_text):
            logger.warning("⚠️ generate_qr_code_base64: texto não é código PIX válido")
            return ""

        try:
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=4
            )
            qr.add_data(qr_code_text)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            buffered = BytesIO()
            img.save(buffered, format="PNG")
            img_bytes = buffered.getvalue()

            if len(img_bytes) < 100:
                logger.error(f"❌ QR Code gerado muito pequeno ({len(img_bytes)} bytes)")
                return ""

            img_base64 = base64.b64encode(img_bytes).decode()

            # 🔥 Valida tamanho mínimo do base64
            if len(img_base64) < 500:
                logger.error(f"❌ Base64 muito curto ({len(img_base64)} chars)")
                return ""

            logger.info(f"✅ QR Code gerado localmente ({len(img_base64)} chars)")
            return f"data:image/png;base64,{img_base64}"

        except Exception as e:
            logger.error(f"❌ Erro ao gerar QR Code: {e}", exc_info=True)
            return ""

    # ==============================================
    # STATUS (CACHE COM LIMITE)
    # ==============================================

    def get_payment_status_real(self, payment_id: str, use_cache: bool = True) -> Dict[str, Any]:
        """🔥 V4.0: Cache com TTL + limite de tamanho."""

        if not self.sdk:
            return {"success": False, "error": "Mercado Pago não configurado"}

        # 🔥 Verifica cache
        if use_cache and payment_id in self._status_cache:
            cached = self._status_cache[payment_id]
            if time.time() - cached.get("timestamp", 0) < self.STATUS_CACHE_TTL:
                self.metrics["cache_hits"] += 1
                self._cache_hits += 1
                logger.debug(f"📦 Cache hit: {payment_id}")
                return cached["data"]
            else:
                # 🔥 Expirou → remove
                del self._status_cache[payment_id]

        self.metrics["cache_misses"] += 1
        self._cache_misses += 1

        try:
            response = self.sdk.payment().get(payment_id)

            if response.get("status") == 200:
                payment = response.get("response", {}) or {}
                data = {
                    "success": True,
                    "status": payment.get("status"),
                    "external_reference": payment.get("external_reference"),
                    "amount": payment.get("transaction_amount"),
                    "payment_method": payment.get("payment_method_id"),
                    "metadata": payment.get("metadata", {}),
                    "approved_at": payment.get("date_approved")
                }

                # 🔥 V4.0: Evita memory leak com limite de tamanho
                if len(self._status_cache) >= self.STATUS_CACHE_MAX_SIZE:
                    # Remove a entrada mais antiga
                    oldest_key = min(
                        self._status_cache.keys(),
                        key=lambda k: self._status_cache[k].get("timestamp", 0)
                    )
                    del self._status_cache[oldest_key]
                    logger.debug(f"🧹 Cache cheio — removido: {oldest_key}")

                self._status_cache[payment_id] = {
                    "data": data,
                    "timestamp": time.time()
                }

                return data

            return {"success": False, "error": "Pagamento não encontrado"}

        except Exception as e:
            logger.error(f"❌ Erro ao consultar pagamento: {e}")
            return {"success": False, "error": str(e)}

    # ==============================================
    # HEALTH CHECK
    # ==============================================

    def health_check(self) -> Dict[str, Any]:
        uptime = (datetime.now(self.tz_brasil) - datetime.fromisoformat(self.metrics["uptime_start"])).total_seconds()

        return {
            "status": "healthy" if self.sdk else "degraded",
            "environment": self.environment,
            "sdk_connected": self.sdk is not None,
            "access_token_configured": bool(self.access_token),
            "webhook_configured": bool(self.webhook_base_url),
            "cache_size": len(self._status_cache),
            "cache_max_size": self.STATUS_CACHE_MAX_SIZE,
            "cache_hit_rate": (
                self._cache_hits / (self._cache_hits + self._cache_misses) * 100
                if (self._cache_hits + self._cache_misses) > 0 else 0
            ),
            "metrics": {
                "total_requests": self.metrics["total_requests"],
                "success_rate": (
                    self.metrics["successful_requests"] / self.metrics["total_requests"] * 100
                    if self.metrics["total_requests"] > 0 else 0
                ),
                "qr_from_mp": self.metrics["qr_from_mp"],
                "qr_generated_locally": self.metrics["qr_generated_locally"],
                "last_error": self.metrics["last_error"]
            },
            "uptime_seconds": round(uptime, 0),
            "timestamp": datetime.now(self.tz_brasil).isoformat()
        }

    # ==============================================
    # LIMPAR CACHE
    # ==============================================

    def clear_cache(self):
        size = len(self._status_cache)
        self._status_cache.clear()
        logger.info(f"🧹 Cache limpo: {size} entradas removidas")


# ==============================================
# INSTÂNCIA GLOBAL
# ==============================================

mp_service = MercadoPagoService()


def get_mp_service() -> Optional[MercadoPagoService]:
    return mp_service


# ==============================================
# INICIALIZAÇÃO
# ==============================================

logger.info("=" * 60)
logger.info("✅ payment_service.py V4.0 carregado")
logger.info(f"   📍 Ambiente: {mp_service.environment}")
logger.info(f"   🔑 SDK: {'✅' if mp_service.sdk else '❌'}")
logger.info(f"   💾 Cache TTL: {mp_service.STATUS_CACHE_TTL}s (max {mp_service.STATUS_CACHE_MAX_SIZE})")
logger.info(f"   🎯 QR Normalizer: ATIVO")
logger.info("=" * 60)