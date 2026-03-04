# backend/api/auth.py
"""
APENAS RE-EXPORT das dependências de autenticação.
TODO O CÓDIGO DE SEGURANÇA ESTÁ EM backend/security.py
"""

from backend.security import (
    # Dependências de autenticação
    get_current_user,
    get_current_active_user,
    get_current_admin_user,
    get_current_manager_user,
    
    # Schema OAuth2
    oauth2_scheme,
    
    # Utilitários de segurança (opcional, se precisar em outros lugares)
    hasher,
    jwt_manager,
    captcha_manager,
    rate_limiter,
    check_captcha
)

__all__ = [
    # Dependências principais
    'get_current_user',
    'get_current_active_user',
    'get_current_admin_user',
    'get_current_manager_user',
    'oauth2_scheme',
    
    # Utilitários (exportados caso necessário)
    'hasher',
    'jwt_manager',
    'captcha_manager',
    'rate_limiter',
    'check_captcha'
]