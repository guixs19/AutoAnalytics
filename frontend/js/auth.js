// frontend/js/auth.js - VERSÃO 4.1 (COM SISTEMA DE MENSAGENS)
/**
 * Módulo de Autenticação - AutoAnalytics v4.1
 * 
 * 🏗️ ARQUITETURA V4.1:
 * 1. ✅ Sincronização total com __APP_STATE do app.js
 * 2. ✅ Atualização de #userName (ID) e .user-name (classe)
 * 3. ✅ Preservação do nome do usuário entre sessões
 * 4. ✅ Carregamento de dados do localStorage como fallback
 * 5. ✅ Sistema de eventos para notificar mudanças
 * 6. ✅ Rate limiter com UI dinâmica
 * 7. ✅ Cookie sync para links HTML puros
 * 8. ✅ Refresh token com fila de requisições
 * 9. 🔥 NOVO: Sistema de mensagens inteligentes
 * 10. 🔥 NOVO: Carregamento de contexto de mensagem via /session-status
 * 11. 🔥 NOVO: Atualização reativa de mensagens
 * 
 * 🔥 CORREÇÕES V4.1:
 * - Adicionado loadMessageContext() para carregar mensagens do backend
 * - Adicionado _updateMessageState() para sincronizar com __APP_STATE
 * - Adicionado refreshMessageContext() para atualização manual
 * - Integração com o sistema de segmentação de usuários
 * 
 * 🔥 CORREÇÕES V4.0:
 * - Nome do usuário agora aparece corretamente no index.html e planos.html
 * - Sincronização bidirecional entre auth.js e app.js
 * - Fallback inteligente quando o app.js não está pronto
 */

(function() {
    'use strict';

    // ==============================================
    // 🔥 CONSTANTES SINCRONIZADAS COM BACKEND
    // ==============================================

    const MAX_CREDITS_BALANCE = 3;
    const TOKEN_EXPIRY_MINUTES = 15;
    const REFRESH_TOKEN_EXPIRY_DAYS = 7;

    const RATE_LIMIT = {
        LOGIN_MAX_ATTEMPTS: 5,
        LOGIN_WINDOW_SECONDS: 900,
        REGISTER_MAX_ATTEMPTS: 5,
        REGISTER_WINDOW_SECONDS: 3600
    };

    // ==============================================
    // 🔥 CLASSE AUTH
    // ==============================================

    class Auth {
        constructor() {
            // 🔥 Configuração
            this.apiBase = '/api';
            
            // 🔥 Estado do usuário
            this.currentUser = null;
            this.userData = null;
            
            // 🔥 Status de autenticação
            this._isAuthenticated = false;
            this.initialized = false;
            this._initializing = false;
            
            // 🔥 Token management
            this._isRefreshing = false;
            this._refreshPromise = null;
            this.pendingRequests = [];
            this._tokenExpiryTimer = null;
            this._tokenCheckInterval = null;
            this._lastTokenCheck = 0;
            
            // 🔥 UI Updates
            this._uiUpdateTimeout = null;
            this._uiUpdateScheduled = false;
            
            // 🔥 Rate Limit
            this._rateLimitBlocked = false;
            this._rateLimitBlockedUntil = 0;
            this._rateLimitRemainingAttempts = RATE_LIMIT.LOGIN_MAX_ATTEMPTS;
            this._lastRateLimitError = null;
            this._loginAttempts = 0;
            this._maxLoginAttempts = 5;
            
            // 🔥 Referência ao app.js
            this._globalState = null;
            this._stateManager = null;
            
            // 🔥 Event listeners internos
            this._listeners = [];
            
            // 🔥 INICIALIZA
            this.init();
        }

        // ==============================================
        // 🔥 GETTERS / SETTERS
        // ==============================================

        get isAuthenticated() {
            return this._isAuthenticated;
        }

        set isAuthenticated(value) {
            const changed = this._isAuthenticated !== value;
            this._isAuthenticated = value;
            if (changed) {
                console.log(`🔄 [Auth] Estado de autenticação: ${value}`);
                this._scheduleUIUpdate();
                
                // 🔥 Dispara evento
                window.dispatchEvent(new CustomEvent('auth:state_changed', {
                    detail: {
                        isAuthenticated: value,
                        user: this.userData,
                        timestamp: Date.now()
                    }
                }));
            }
        }

        // ==============================================
        // 🔥 SYNC COM APP.JS (NOVO - ROBUSTO)
        // ==============================================

        /**
         * Obtém referência ao estado global do app.js
         */
        _getGlobalState() {
            if (!this._globalState) {
                this._globalState = window.__APP_STATE || null;
            }
            return this._globalState;
        }

        /**
         * Obtém referência ao state manager do app.js
         */
        _getStateManager() {
            if (!this._stateManager) {
                this._stateManager = window.__APP_STATE_MANAGER || null;
            }
            return this._stateManager;
        }

        /**
         * Sincroniza o estado do auth com o __APP_STATE do app.js
         * 🔥 MÉTODO PRINCIPAL DE SINCRONIZAÇÃO
         */
        _syncWithGlobalState() {
            const stateManager = this._getStateManager();
            
            if (!stateManager) {
                console.warn('⚠️ [Auth] StateManager não disponível, sincronização adiada');
                
                // 🔥 Tenta novamente em 500ms
                setTimeout(() => {
                    if (this.userData) {
                        this._syncWithGlobalState();
                    }
                }, 500);
                return;
            }

            if (this.userData) {
                // 🔥 Prepara dados do usuário com fallbacks
                const userName = this.userData.name || 
                                this.userData.displayName || 
                                localStorage.getItem('user_name') || 
                                'Usuário';
                
                const workshopName = this.userData.workshop_name || 
                                    this.userData.workshopName || 
                                    'Oficina';

                // 🔥 Atualiza o estado global
                stateManager.updateState({
                    user: {
                        ...this.userData,
                        name: userName,
                        displayName: userName,
                        workshop_name: workshopName,
                        workshopName: workshopName
                    },
                    credits: this.userData.credits || 0,
                    isPremium: this.isPremium(),
                    isAdmin: this.isAdmin(),
                    tokenValid: this.isAuthenticated,
                    userInitialized: true,
                    isAppReady: true
                });

                console.log(`🔄 [Auth] Estado sincronizado com __APP_STATE (Usuário: ${userName})`);
                
                // 🔥 Força atualização da UI
                this._forceUIRefresh();
            }
        }

        /**
         * Força atualização completa da UI
         */
        _forceUIRefresh() {
            // 🔥 Atualiza a UI do auth
            this.updateUI();
            
            // 🔥 Dispara evento para outros módulos
            window.dispatchEvent(new CustomEvent('auth:sync_completed', {
                detail: {
                    user: this.userData,
                    isAuthenticated: this.isAuthenticated,
                    timestamp: Date.now()
                }
            }));
            
            // 🔥 Tenta atualizar via app.js também
            if (window.App && typeof window.App.updateNavbar === 'function') {
                try {
                    window.App.updateNavbar();
                } catch (e) {
                    // Ignora erro
                }
            }
        }

        // ==============================================
        // 🔥 COOKIE HELPERS
        // ==============================================

        _setCookie(name, value, maxAgeSeconds = 900) {
            document.cookie = `${name}=${value}; path=/; max-age=${maxAgeSeconds}; SameSite=Strict; Secure`;
        }

        _getCookie(name) {
            const value = `; ${document.cookie}`;
            const parts = value.split(`; ${name}=`);
            if (parts.length === 2) return parts.pop().split(';').shift();
            return null;
        }

        _deleteCookie(name) {
            document.cookie = `${name}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 UTC;`;
        }

        _syncTokenToCookie(token) {
            if (token) {
                this._setCookie('access_token', token, TOKEN_EXPIRY_MINUTES * 60);
                console.log('🍪 [Auth] Token sincronizado com cookie (15min)');
            } else {
                this._deleteCookie('access_token');
            }
        }

        // ==============================================
        // 🔥 UI UPDATE (CORRIGIDO - TODOS OS SELETORES)
        // ==============================================

        /**
         * Atualiza a UI com os dados do usuário
         * 🔥 CORRIGIDO: Agora atualiza #userName E .user-name
         */
        updateUI() {
            const isAuth = this.isAuthenticated;
            
            // 🔥 Atualiza elementos de autenticação
            document.querySelectorAll('.auth-required').forEach(el => {
                el.style.display = isAuth ? 'block' : 'none';
            });
            
            document.querySelectorAll('.guest-only').forEach(el => {
                el.style.display = isAuth ? 'none' : 'block';
            });
            
            if (isAuth && this.userData) {
                // 🔥 Obtém nome do usuário com fallbacks
                const userName = this.userData.name || 
                                this.userData.displayName || 
                                localStorage.getItem('user_name') || 
                                'Usuário';
                
                const workshopName = this.userData.workshop_name || 
                                    this.userData.workshopName || 
                                    'Oficina';

                // 🔥 ATUALIZA TODOS OS SELETORES DE NOME
                // Isso resolve o problema do index.html (#userName) e planos.html (.user-name)
                const nameSelectors = [
                    '#userName',                    // ID (index.html)
                    '.user-name',                   // Classe (planos.html)
                    '.user-name-display span:last-child',
                    '.navbar .user-name-display span',
                    '#userNameDisplay',
                    '.user-display-name'
                ];
                
                nameSelectors.forEach(selector => {
                    document.querySelectorAll(selector).forEach(el => {
                        if (el) {
                            el.textContent = userName;
                            el.setAttribute('data-username', userName);
                        }
                    });
                });

                // 🔥 ATUALIZA NOME DA OFICINA
                const workshopSelectors = [
                    '.workshop-name',
                    '#workshopName',
                    '.workshop-display-name'
                ];
                
                workshopSelectors.forEach(selector => {
                    document.querySelectorAll(selector).forEach(el => {
                        if (el) el.textContent = workshopName;
                    });
                });

                // 🔥 Atualiza créditos
                this.updateCreditsDisplay();
                this.updateAdminBadge();
                this.updatePremiumBadge();
                this.updateUserStatusBadge();

                console.log(`👤 [Auth] UI atualizada: ${userName} (${workshopName})`);
            }
        }

        /**
         * Atualiza o badge de status do usuário
         */
        updateUserStatusBadge() {
            const badge = document.getElementById('userStatusBadge');
            if (!badge) return;

            if (this.isAdmin()) {
                badge.innerHTML = '<i class="fas fa-crown me-1"></i> Administrador';
                badge.style.background = 'linear-gradient(135deg, #f39c12, #e67e22)';
                badge.style.color = 'white';
            } else if (this.isPremium()) {
                badge.innerHTML = '<i class="fas fa-star me-1"></i> Premium';
                badge.style.background = 'linear-gradient(135deg, #48bb78, #2d6a4f)';
                badge.style.color = 'white';
            } else {
                badge.innerHTML = '<i class="fas fa-user me-1"></i> Plano Grátis';
                badge.style.background = 'rgba(255,255,255,0.08)';
                badge.style.color = 'rgba(255,255,255,0.5)';
            }
        }

        /**
         * Agenda atualização da UI (debounced)
         */
        _scheduleUIUpdate() {
            if (this._uiUpdateTimeout) {
                clearTimeout(this._uiUpdateTimeout);
            }
            this._uiUpdateTimeout = setTimeout(() => {
                this.updateUI();
                this._syncWithGlobalState();
                this._uiUpdateTimeout = null;
            }, 50);
        }

        // ==============================================
        // 🔥 CRÉDITOS E BADGES
        // ==============================================

        updateCreditsDisplay() {
            const display = this.getCreditsDisplay();
            
            const selectors = [
                '.credits-display',
                '.user-credits',
                '#creditsDisplay',
                '#creditsCount',
                '#uploadCredits',
                '.credits-badge span',
                '.credits-value',
                '.user-credits-display'
            ];
            
            selectors.forEach(selector => {
                document.querySelectorAll(selector).forEach(el => {
                    if (el) el.textContent = display;
                });
            });

            // 🔥 Dispara evento de créditos
            window.dispatchEvent(new CustomEvent('creditsUpdated', {
                detail: {
                    credits: this.getCredits(),
                    display: display,
                    maxCredits: MAX_CREDITS_BALANCE,
                    isPremium: this.isPremium()
                }
            }));
        }

        updateAdminBadge() {
            const isAdmin = this.isAdmin();
            document.querySelectorAll('.admin-badge, .admin-only').forEach(el => {
                el.style.display = isAdmin ? 'inline-block' : 'none';
            });
            document.body.classList.toggle('is-admin', isAdmin);
        }

        updatePremiumBadge() {
            const isPremium = this.isPremium();
            document.querySelectorAll('.premium-badge, .premium-only').forEach(el => {
                el.style.display = isPremium ? 'inline-block' : 'none';
            });
            document.body.classList.toggle('is-premium', isPremium);
        }

        getCredits() {
            return this.userData?.credits || 0;
        }

        getCreditsDisplay() {
            if (this.isAdmin()) return '∞';
            if (this.isPremium()) {
                const credits = this.getCredits();
                return `${credits}/${MAX_CREDITS_BALANCE}`;
            }
            return String(this.getCredits());
        }

        isAdmin() {
            return this.userData?.is_admin === true;
        }

        isPremium() {
            return this.userData?.plan === 'premium_mensal' || 
                   this.userData?.plan === 'PREMIUM_MENSAL' ||
                   this.userData?.is_premium === true;
        }

        isPromotionalPriceLocked() {
            return this.userData?.promotional_price_locked || false;
        }

        getPromotionalPrice() {
            return this.userData?.promotional_price || null;
        }

        getCurrentUser() {
            return this.userData || {};
        }

        // ==============================================
        // 🔥 RATE LIMITER
        // ==============================================

        _isRateLimitBlocked() {
            if (this._rateLimitBlocked && Date.now() < this._rateLimitBlockedUntil) {
                return true;
            }
            if (this._rateLimitBlocked && Date.now() >= this._rateLimitBlockedUntil) {
                this._rateLimitBlocked = false;
                this._rateLimitBlockedUntil = 0;
                this._rateLimitRemainingAttempts = RATE_LIMIT.LOGIN_MAX_ATTEMPTS;
            }
            return false;
        }

        _getRateLimitTimeRemaining() {
            if (!this._rateLimitBlocked) return 0;
            return Math.max(0, Math.ceil((this._rateLimitBlockedUntil - Date.now()) / 1000));
        }

        _handleRateLimitError(response, data) {
            const retryAfter = response.headers.get('Retry-After') || data.retry_after || 60;
            const remaining = data.remaining_attempts || 0;
            const resetTime = data.reset_time || 0;
            
            this._rateLimitBlocked = true;
            this._rateLimitBlockedUntil = Date.now() + (parseInt(retryAfter) * 1000);
            this._rateLimitRemainingAttempts = remaining;
            this._lastRateLimitError = {
                retryAfter: parseInt(retryAfter),
                remaining: remaining,
                resetTime: resetTime,
                timestamp: Date.now()
            };
            
            console.warn(`⚠️ [Auth] Rate Limit: ${remaining} tentativas, aguarde ${retryAfter}s`);
            
            window.dispatchEvent(new CustomEvent('rateLimitBlocked', {
                detail: {
                    retryAfter: parseInt(retryAfter),
                    remaining: remaining,
                    resetTime: resetTime
                }
            }));
            
            return {
                blocked: true,
                retryAfter: parseInt(retryAfter),
                remaining: remaining,
                message: data.detail || data.message || 'Muitas tentativas. Aguarde alguns segundos.'
            };
        }

        _showRateLimitWarning(retryAfter) {
            const minutes = Math.floor(retryAfter / 60);
            const seconds = retryAfter % 60;
            let timeMsg = '';
            if (minutes > 0) {
                timeMsg = `${minutes} minuto${minutes > 1 ? 's' : ''}`;
                if (seconds > 0) timeMsg += ` e ${seconds} segundo${seconds > 1 ? 's' : ''}`;
            } else {
                timeMsg = `${seconds} segundo${seconds > 1 ? 's' : ''}`;
            }
            
            if (window.toastr) {
                toastr.warning(`⏳ Muitas tentativas. Aguarde ${timeMsg} antes de tentar novamente.`);
            } else {
                alert(`Muitas tentativas em curto período. Por favor, aguarde ${timeMsg} e tente novamente.`);
            }
            
            const loginBtn = document.getElementById('loginBtn');
            if (loginBtn) {
                loginBtn.disabled = true;
                loginBtn.innerHTML = `<i class="fas fa-hourglass-half me-2"></i> Aguarde ${timeMsg}`;
                setTimeout(() => {
                    loginBtn.disabled = false;
                    loginBtn.innerHTML = '<i class="fas fa-sign-in-alt me-2"></i> Entrar';
                }, retryAfter * 1000);
            }
            
            const registerBtn = document.getElementById('registerBtn');
            if (registerBtn) {
                registerBtn.disabled = true;
                registerBtn.innerHTML = `<i class="fas fa-hourglass-half me-2"></i> Aguarde ${timeMsg}`;
                setTimeout(() => {
                    registerBtn.disabled = false;
                    registerBtn.innerHTML = '<i class="fas fa-user-plus me-2"></i> Criar Conta';
                }, retryAfter * 1000);
            }
        }

        // ==============================================
        // 🔥 LOGIN (CORRIGIDO)
        // ==============================================

        async handleLogin(e) {
            e.preventDefault();
            
            if (this._isRateLimitBlocked()) {
                const remaining = this._getRateLimitTimeRemaining();
                this._showRateLimitWarning(remaining);
                return;
            }
            
            const emailInput = document.getElementById('loginEmail');
            const passwordInput = document.getElementById('loginPassword');
            
            const email = emailInput?.value?.trim();
            const password = passwordInput?.value;
            
            if (!email || !password) {
                if (window.toastr) toastr.error('Por favor, preencha todos os campos.');
                return;
            }
            
            const submitBtn = document.getElementById('loginBtn');
            const originalText = submitBtn?.innerHTML;
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i> Entrando...';
            }
            
            try {
                const payload = {
                    email: email,
                    password: password,
                    session_type: 'login'
                };
                
                const response = await fetch(`${this.apiBase}/auth/login`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                
                const data = await response.json();
                
                if (response.status === 429) {
                    const rateInfo = this._handleRateLimitError(response, data);
                    this._showRateLimitWarning(rateInfo.retryAfter);
                    if (rateInfo.remaining !== undefined) {
                        console.log(`📊 [Auth] Tentativas restantes: ${rateInfo.remaining}`);
                        if (window.toastr) {
                            toastr.warning(`⏳ ${rateInfo.message} (${rateInfo.remaining} tentativas restantes)`);
                        }
                    }
                    return false;
                }
                
                if (response.ok && (data.success || data.access_token)) {
                    console.log('✅ [Auth] Login bem-sucedido!');
                    
                    this._rateLimitBlocked = false;
                    this._rateLimitBlockedUntil = 0;
                    this._rateLimitRemainingAttempts = RATE_LIMIT.LOGIN_MAX_ATTEMPTS;
                    this._loginAttempts = 0;
                    
                    // 🔥 GUARDA TOKEN
                    if (data.access_token) {
                        localStorage.setItem('access_token', data.access_token);
                        this._syncTokenToCookie(data.access_token);
                    }
                    if (data.refresh_token) {
                        localStorage.setItem('refresh_token', data.refresh_token);
                    }
                    
                    // 🔥 CRIA USERDATA COM NOME CORRETO
                    const userName = data.user_name || 
                                    data.user_name_display || 
                                    email.split('@')[0] || 
                                    'Usuário';
                    
                    const workshopName = data.workshop_name || 'Oficina';
                    
                    this.userData = {
                        email: data.user_email || email,
                        name: userName,
                        displayName: userName,
                        workshop_name: workshopName,
                        workshopName: workshopName,
                        role: data.role || 'user',
                        plan: data.plan || 'free',
                        credits: data.credits || 0,
                        is_admin: data.is_admin || false,
                        is_premium: data.is_premium || false,
                        credits_display: data.credits_display || String(data.credits || 0),
                        promotional_price_locked: data.promotional_price_locked || false,
                        promotional_price: data.promotional_price || null
                    };
                    
                    this.currentUser = this.userData;
                    this.isAuthenticated = true;
                    
                    // 🔥 SALVA NO LOCALSTORAGE
                    localStorage.setItem('user_data', JSON.stringify(this.userData));
                    localStorage.setItem('user_email', this.userData.email);
                    localStorage.setItem('user_name', this.userData.name);
                    localStorage.setItem('workshop_name', this.userData.workshop_name);
                    
                    if (passwordInput) passwordInput.value = '';
                    
                    // 🔥 SINCRONIZA COM APP.JS
                    this._syncWithGlobalState();
                    
                    // 🔥 FORÇA ATUALIZAÇÃO DA UI
                    this._forceUIRefresh();
                    
                    // 🔥 DISPARA EVENTO DE SUCESSO
                    window.dispatchEvent(new CustomEvent('authLoginSuccess', {
                        detail: {
                            user: this.userData,
                            credits: this.userData.credits,
                            isPremium: this.isPremium(),
                            isAdmin: this.isAdmin()
                        }
                    }));
                    
                    // 🔥 CARREGA CONTEXTO DE MENSAGEM
                    await this.loadMessageContext();
                    
                    this.startTokenMonitoring();
                    
                    if (window.toastr) toastr.success('Login realizado com sucesso!');
                    
                    setTimeout(() => {
                        window.location.href = '/dashboard';
                    }, 600);
                    
                    return true;
                    
                } else {
                    // 🔥 TRATAMENTO DE ERRO
                    let errorMsg = data.detail || data.message || 'Erro ao realizar login.';
                    
                    if (response.status === 422) {
                        if (data.detail && Array.isArray(data.detail)) {
                            errorMsg = data.detail.map(err => 
                                `${err.loc?.join('.') || 'campo'}: ${err.msg}`
                            ).join('; ');
                        } else if (typeof data.detail === 'string') {
                            errorMsg = data.detail;
                        }
                    } else if (response.status === 404) {
                        errorMsg = 'Serviço de autenticação indisponível. Tente novamente.';
                    } else if (response.status === 500) {
                        errorMsg = 'Erro interno do servidor. Tente novamente.';
                    } else if (response.status === 401) {
                        errorMsg = 'Email ou senha incorretos.';
                    }
                    
                    this._loginAttempts++;
                    
                    if (this._loginAttempts >= this._maxLoginAttempts) {
                        this._rateLimitBlocked = true;
                        this._rateLimitBlockedUntil = Date.now() + (5 * 60 * 1000);
                        if (window.toastr) toastr.warning('⏳ Muitas tentativas falhas. Aguarde 5 minutos.');
                        if (submitBtn) {
                            submitBtn.disabled = true;
                            submitBtn.innerHTML = '<i class="fas fa-hourglass-half me-2"></i> Aguarde 5 min';
                            setTimeout(() => {
                                submitBtn.disabled = false;
                                submitBtn.innerHTML = originalText;
                                this._rateLimitBlocked = false;
                                this._rateLimitBlockedUntil = 0;
                                this._loginAttempts = 0;
                            }, 5 * 60 * 1000);
                        }
                    } else if (window.toastr) {
                        toastr.error(errorMsg);
                    }
                    return false;
                }
                
            } catch (error) {
                console.error('❌ [Auth] Erro na requisição de login:', error);
                if (window.toastr) toastr.error('Erro de comunicação com o servidor.');
                return false;
                
            } finally {
                if (submitBtn && !submitBtn.disabled) {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = originalText;
                }
            }
        }

        // ==============================================
        // 🔥 REGISTER
        // ==============================================

        async handleRegister(e) {
            e.preventDefault();
            
            if (this._isRateLimitBlocked()) {
                const remaining = this._getRateLimitTimeRemaining();
                this._showRateLimitWarning(remaining);
                return;
            }
            
            const nameInput = document.getElementById('registerName');
            const emailInput = document.getElementById('registerEmail');
            const passwordInput = document.getElementById('registerPassword');
            const confirmPasswordInput = document.getElementById('registerConfirmPassword');
            const workshopInput = document.getElementById('registerWorkshop');
            const phoneInput = document.getElementById('registerPhone');
            
            const name = nameInput?.value?.trim();
            const email = emailInput?.value?.trim();
            const password = passwordInput?.value;
            const confirmPassword = confirmPasswordInput?.value;
            const workshopName = workshopInput?.value?.trim();
            const phone = phoneInput?.value?.trim();
            
            // Validações
            if (!name || !email || !password || !workshopName) {
                if (window.toastr) toastr.error('Preencha todos os campos obrigatórios.');
                return;
            }
            
            if (name.length < 3) {
                if (window.toastr) toastr.error('Nome deve ter pelo menos 3 caracteres.');
                return;
            }
            
            if (workshopName.length < 2) {
                if (window.toastr) toastr.error('Nome da oficina deve ter pelo menos 2 caracteres.');
                return;
            }
            
            if (phone) {
                const phoneClean = phone.replace(/\D/g, '');
                if (phoneClean.length > 0 && phoneClean.length < 10) {
                    if (window.toastr) toastr.warning('Telefone deve ter pelo menos 10 dígitos (incluindo DDD).');
                    return;
                }
                if (phoneClean.length > 11) {
                    if (window.toastr) toastr.warning('Telefone deve ter no máximo 11 dígitos.');
                    return;
                }
            }
            
            if (password.length < 6) {
                if (window.toastr) toastr.error('Senha deve ter no mínimo 6 caracteres.');
                return;
            }
            
            if (password !== confirmPassword) {
                if (window.toastr) toastr.error('As senhas não coincidem.');
                return;
            }
            
            const submitBtn = document.getElementById('registerBtn');
            const originalText = submitBtn?.innerHTML;
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i> Criando conta...';
            }
            
            try {
                const requestBody = {
                    name: name,
                    email: email,
                    password: password,
                    workshop_name: workshopName,
                    phone: phone || null,
                    session_type: 'register'
                };
                
                const response = await fetch(`${this.apiBase}/auth/register`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestBody)
                });
                
                const data = await response.json();
                
                if (response.status === 429) {
                    const rateInfo = this._handleRateLimitError(response, data);
                    this._showRateLimitWarning(rateInfo.retryAfter);
                    if (window.toastr) toastr.warning(`⏳ ${rateInfo.message}`);
                    return false;
                }
                
                if (!response.ok) {
                    let errorMsg = data.detail || data.message || 'Falha no registro';
                    
                    if (response.status === 422) {
                        if (data.detail && Array.isArray(data.detail)) {
                            errorMsg = data.detail.map(err => 
                                `${err.loc?.join('.') || 'campo'}: ${err.msg}`
                            ).join('; ');
                        } else if (typeof data.detail === 'string') {
                            errorMsg = data.detail;
                        }
                    } else if (response.status === 409) {
                        errorMsg = 'Este email já está cadastrado. Faça login.';
                    } else if (response.status === 400) {
                        errorMsg = data.detail || 'Dados inválidos. Verifique os campos.';
                    }
                    
                    if (window.toastr) toastr.error(errorMsg);
                    return false;
                }
                
                if (data.success) {
                    if (window.toastr) toastr.success('✅ Conta criada! Faça login para continuar.');
                    
                    // Limpa campos
                    if (nameInput) nameInput.value = '';
                    if (emailInput) emailInput.value = '';
                    if (passwordInput) passwordInput.value = '';
                    if (confirmPasswordInput) confirmPasswordInput.value = '';
                    if (workshopInput) workshopInput.value = '';
                    if (phoneInput) phoneInput.value = '';
                    
                    setTimeout(() => {
                        window.location.href = '/login';
                    }, 2000);
                    
                    return true;
                }
                
                throw new Error(data.message || 'Erro no registro');
                
            } catch (error) {
                console.error('❌ [Auth] Erro no registro:', error);
                if (window.toastr) toastr.error(error.message || 'Erro ao criar conta. Tente novamente.');
                return false;
            } finally {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = originalText;
                }
            }
        }

        // ==============================================
        // 🔥 TOKEN MANAGEMENT
        // ==============================================

        async refreshTokenSafely() {
            if (this._isRefreshing) {
                return new Promise((resolve) => {
                    this.pendingRequests.push(resolve);
                });
            }
            
            if (this._isRateLimitBlocked()) {
                console.warn('⚠️ [Auth] Rate Limit bloqueado - não pode fazer refresh');
                return false;
            }
            
            this._isRefreshing = true;
            
            try {
                const refreshToken = localStorage.getItem('refresh_token');
                const accessToken = localStorage.getItem('access_token');
                
                if (!refreshToken) return false;
                
                const response = await fetch(`${this.apiBase}/auth/refresh`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        refresh_token: refreshToken,
                        old_access_token: accessToken || null
                    })
                });
                
                if (response.status === 429) {
                    const data = await response.json().catch(() => ({}));
                    this._handleRateLimitError(response, data);
                    console.warn('⚠️ [Auth] Rate Limit no refresh token');
                    return false;
                }
                
                if (response.status === 404) {
                    console.warn('⚠️ [Auth] Endpoint /auth/refresh não encontrado');
                    return false;
                }
                
                if (response.ok) {
                    const data = await response.json();
                    
                    localStorage.setItem('access_token', data.access_token);
                    this._syncTokenToCookie(data.access_token);
                    
                    if (data.refresh_token) {
                        localStorage.setItem('refresh_token', data.refresh_token);
                    }
                    
                    if (data.user_email) {
                        const userName = data.user_name || 
                                        data.user_email.split('@')[0] || 
                                        this.userData?.name || 
                                        'Usuário';
                        
                        this.userData = {
                            ...this.userData,
                            email: data.user_email,
                            name: userName,
                            displayName: userName,
                            workshop_name: data.workshop_name || this.userData?.workshop_name || 'Oficina',
                            role: data.role || this.userData?.role || 'user',
                            plan: data.plan || this.userData?.plan || 'free',
                            credits: data.credits || this.userData?.credits || 0,
                            is_admin: data.is_admin || this.userData?.is_admin || false,
                            credits_display: data.credits_display || String(data.credits || 0)
                        };
                        
                        this.currentUser = this.userData;
                        
                        // 🔥 Salva no localStorage
                        localStorage.setItem('user_data', JSON.stringify(this.userData));
                        localStorage.setItem('user_name', this.userData.name);
                        
                        // 🔥 Sincroniza com app.js
                        this._syncWithGlobalState();
                        this.updateCreditsDisplay();
                        this._forceUIRefresh();
                    }
                    
                    this.stopTokenMonitoring();
                    this.startTokenMonitoring();
                    
                    console.log('✅ [Auth] Token refresh realizado com sucesso');
                    return true;
                }
                return false;
            } catch (error) {
                console.error('❌ [Auth] Erro no refresh:', error);
                return false;
            } finally {
                this._isRefreshing = false;
                while (this.pendingRequests.length) {
                    const resolve = this.pendingRequests.pop();
                    resolve(false);
                }
            }
        }

        async refreshToken() {
            return this.refreshTokenSafely();
        }

        // ==============================================
        // 🔥 CHECK TOKEN (CORRIGIDO)
        // ==============================================

        async checkTokenHealth() {
            const now = Date.now();
            if (now - this._lastTokenCheck < 5000) return;
            this._lastTokenCheck = now;
            
            if (this._isRateLimitBlocked()) {
                console.log('⏳ [Auth] Rate Limit bloqueado - pulando health check');
                return;
            }
            
            try {
                const token = localStorage.getItem('access_token');
                if (!token) {
                    this.handleTokenExpired();
                    return;
                }
                
                const response = await fetch(`${this.apiBase}/auth/check-token`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                
                if (response.status === 429) {
                    const data = await response.json().catch(() => ({}));
                    this._handleRateLimitError(response, data);
                    console.warn('⚠️ [Auth] Rate Limit no health check');
                    return;
                }
                
                if (response.status === 404) {
                    console.warn('⚠️ [Auth] Endpoint /auth/check-token não encontrado');
                    return;
                }
                
                const data = await response.json();
                
                if (response.status === 401) {
                    console.log('🔄 [Auth] Token expirou, tentando refresh...');
                    const refreshed = await this.refreshToken();
                    if (!refreshed) {
                        this.handleTokenExpired();
                    }
                } else if (response.ok) {
                    if (data.status === 'refreshed' && data.access_token) {
                        console.log('🔄 [Auth] Token renovado via check-token');
                        localStorage.setItem('access_token', data.access_token);
                        this._syncTokenToCookie(data.access_token);
                        if (data.refresh_token) {
                            localStorage.setItem('refresh_token', data.refresh_token);
                        }
                        
                        this.stopTokenMonitoring();
                        this.startTokenMonitoring();
                    }
                    
                    if (data.user) {
                        const userName = data.name || 
                                        data.user.split('@')[0] || 
                                        this.userData?.name || 
                                        'Usuário';
                        
                        this.userData = {
                            ...this.userData,
                            email: data.user,
                            name: userName,
                            displayName: userName,
                            is_admin: data.is_admin || this.userData?.is_admin || false,
                            credits: data.credits || this.userData?.credits || 0,
                            credits_display: data.credits_display || String(data.credits || 0),
                            workshop_name: data.workshop_name || this.userData?.workshop_name || 'Oficina'
                        };
                        
                        this.currentUser = this.userData;
                        
                        // 🔥 Salva no localStorage
                        localStorage.setItem('user_data', JSON.stringify(this.userData));
                        localStorage.setItem('user_name', this.userData.name);
                        
                        // 🔥 Sincroniza com app.js
                        this._syncWithGlobalState();
                        this.updateCreditsDisplay();
                        this._forceUIRefresh();
                    }
                }
            } catch (error) {
                console.warn('⚠️ [Auth] Erro ao verificar token:', error);
            }
        }

        // ==============================================
        // 🔥 CHECK TOKEN INICIAL (CORRIGIDO)
        // ==============================================

        async checkToken() {
            const token = localStorage.getItem('access_token');
            if (!token) {
                this.isAuthenticated = false;
                return false;
            }
            
            try {
                const response = await fetch(`${this.apiBase}/auth/check-token`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                
                if (response.status === 429) {
                    const data = await response.json().catch(() => ({}));
                    this._handleRateLimitError(response, data);
                    console.warn('⚠️ [Auth] Rate Limit no check inicial');
                    return false;
                }
                
                if (response.ok) {
                    const data = await response.json();
                    if (data.status === 'valid') {
                        this.isAuthenticated = true;
                        
                        // 🔥 Preserva ou carrega nome do usuário
                        const userName = data.name || 
                                        localStorage.getItem('user_name') || 
                                        data.user?.split('@')[0] || 
                                        'Usuário';
                        
                        const workshopName = data.workshop_name || 
                                            localStorage.getItem('workshop_name') || 
                                            'Oficina';
                        
                        this.userData = {
                            ...this.userData,
                            email: data.user || data.email || this.userData?.email,
                            name: userName,
                            displayName: userName,
                            workshop_name: workshopName,
                            workshopName: workshopName,
                            is_admin: data.is_admin || this.userData?.is_admin || false,
                            credits: data.credits || this.userData?.credits || 0,
                            credits_display: data.credits_display || String(data.credits || 0),
                            plan: data.plan || this.userData?.plan || 'free'
                        };
                        
                        this.currentUser = this.userData;
                        
                        // 🔥 Salva no localStorage
                        localStorage.setItem('user_data', JSON.stringify(this.userData));
                        localStorage.setItem('user_name', this.userData.name);
                        localStorage.setItem('workshop_name', this.userData.workshop_name);
                        
                        // 🔥 Sincroniza com app.js
                        this._syncWithGlobalState();
                        this._forceUIRefresh();
                        this.updateCreditsDisplay();
                        
                        return true;
                    }
                }
                
                if (response.status === 401) {
                    const refreshed = await this.refreshToken();
                    if (refreshed) {
                        this.isAuthenticated = true;
                        return true;
                    }
                }
                
                this.isAuthenticated = false;
                return false;
                
            } catch (error) {
                console.warn('⚠️ [Auth] Erro ao verificar token:', error);
                this.isAuthenticated = false;
                return false;
            }
        }

        // ==============================================
        // 🔥 FETCH WITH AUTH
        // ==============================================

        async fetchWithAuth(url, options = {}) {
            let token = localStorage.getItem('access_token');
            
            if (!token) {
                return null;
            }
            
            const headers = {
                'Content-Type': 'application/json',
                ...options.headers
            };
            
            headers['Authorization'] = `Bearer ${token}`;
            
            try {
                let response = await fetch(url, { ...options, headers });
                
                if (response.status === 429) {
                    const data = await response.json().catch(() => ({}));
                    const rateInfo = this._handleRateLimitError(response, data);
                    console.warn(`⚠️ [Auth] Rate Limit bloqueado para ${url}: ${rateInfo.message}`);
                    window.dispatchEvent(new CustomEvent('rateLimitBlocked', {
                        detail: {
                            url: url,
                            retryAfter: rateInfo.retryAfter,
                            remaining: rateInfo.remaining
                        }
                    }));
                    return response;
                }
                
                if (response.status === 401) {
                    const refreshed = await this.refreshToken();
                    
                    if (refreshed) {
                        const newToken = localStorage.getItem('access_token');
                        headers['Authorization'] = `Bearer ${newToken}`;
                        response = await fetch(url, { ...options, headers });
                    } else {
                        this.clearTokens();
                        this.isAuthenticated = false;
                        this.currentUser = null;
                        this.userData = null;
                        
                        if (!window.location.pathname.includes('/login')) {
                            window.location.href = '/login';
                        }
                        return null;
                    }
                }
                
                return response;
                
            } catch (error) {
                console.error('❌ [Auth] Erro na requisição:', error);
                return null;
            }
        }

        // ==============================================
        // 🔥 TOKEN MONITORING
        // ==============================================

        startTokenMonitoring() {
            this.stopTokenMonitoring();
            
            this._tokenCheckInterval = setInterval(() => {
                this.checkTokenHealth();
            }, 30000);
            
            const token = localStorage.getItem('access_token');
            if (token) {
                try {
                    const payload = JSON.parse(atob(token.split('.')[1]));
                    const expiresIn = (payload.exp * 1000) - Date.now();
                    if (expiresIn > 0) {
                        this._tokenExpiryTimer = setTimeout(() => {
                            console.log('⏰ [Auth] Token expirou, tentando refresh...');
                            this.refreshToken();
                        }, expiresIn - 60000);
                    }
                } catch (e) {
                    // Ignora
                }
            }
            
            console.log('⏰ [Auth] Monitoramento de token iniciado');
        }

        stopTokenMonitoring() {
            if (this._tokenCheckInterval) {
                clearInterval(this._tokenCheckInterval);
                this._tokenCheckInterval = null;
            }
            if (this._tokenExpiryTimer) {
                clearTimeout(this._tokenExpiryTimer);
                this._tokenExpiryTimer = null;
            }
        }

        // ==============================================
        // 🔥 CLEAR TOKENS E LOGOUT
        // ==============================================

        clearTokens() {
            localStorage.removeItem('access_token');
            localStorage.removeItem('refresh_token');
            localStorage.removeItem('user_data');
            localStorage.removeItem('user_email');
            localStorage.removeItem('user_name');
            localStorage.removeItem('workshop_name');
            
            this._deleteCookie('access_token');
            
            console.log('🧹 [Auth] Tokens e dados limpos');
        }

        async logout() {
            const refreshToken = localStorage.getItem('refresh_token');
            const accessToken = localStorage.getItem('access_token');
            
            this._rateLimitBlocked = false;
            this._rateLimitBlockedUntil = 0;
            this._rateLimitRemainingAttempts = RATE_LIMIT.LOGIN_MAX_ATTEMPTS;
            this._loginAttempts = 0;
            
            if (refreshToken) {
                try {
                    await fetch(`${this.apiBase}/auth/logout`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': accessToken ? `Bearer ${accessToken}` : ''
                        },
                        body: JSON.stringify({
                            refresh_token: refreshToken
                        })
                    });
                } catch (error) {
                    console.error('❌ [Auth] Logout API error:', error);
                }
            }
            
            this.stopTokenMonitoring();
            this.clearTokens();
            this.isAuthenticated = false;
            this.currentUser = null;
            this.userData = null;
            
            // 🔥 Atualiza estado global
            const stateManager = this._getStateManager();
            if (stateManager) {
                stateManager.updateState({
                    user: null,
                    credits: 0,
                    isPremium: false,
                    isAdmin: false,
                    tokenValid: false,
                    userInitialized: false,
                    isAppReady: false
                });
            }
            
            window.dispatchEvent(new CustomEvent('authLogout'));
            window.dispatchEvent(new CustomEvent('auth:unauthorized', {
                detail: { message: 'Logout realizado' }
            }));
            
            window.location.href = '/login';
        }

        handleTokenExpired() {
            console.log('⏰ [Auth] Token expirado');
            this.clearTokens();
            this.isAuthenticated = false;
            this.currentUser = null;
            this.userData = null;
            
            // 🔥 Atualiza estado global
            const stateManager = this._getStateManager();
            if (stateManager) {
                stateManager.updateState({
                    user: null,
                    credits: 0,
                    isPremium: false,
                    isAdmin: false,
                    tokenValid: false,
                    userInitialized: false,
                    isAppReady: false
                });
            }
            
            window.dispatchEvent(new CustomEvent('auth:unauthorized', {
                detail: { message: 'Token expirado' }
            }));
            
            if (!window.location.pathname.includes('/login')) {
                window.location.href = '/login?session=expired';
            }
        }

        // ==============================================
        // 🔥 LOAD USER CREDITS
        // ==============================================

        async loadUserCredits() {
            try {
                const token = localStorage.getItem('access_token');
                if (!token) return;
                
                const response = await fetch(`${this.apiBase}/payments/balance`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                
                if (response.ok) {
                    const data = await response.json();
                    if (data.success && data.credits !== undefined) {
                        this.userData = {
                            ...this.userData,
                            credits: data.credits,
                            credits_display: data.credits_display || String(data.credits),
                            is_admin: data.is_admin || this.userData?.is_admin || false,
                            plan: data.plan?.type || this.userData?.plan || 'free'
                        };
                        this.currentUser = this.userData;
                        
                        // 🔥 Sincroniza com app.js
                        this._syncWithGlobalState();
                        this.updateCreditsDisplay();
                        this._forceUIRefresh();
                        
                        // 🔥 Atualiza contexto de mensagem após mudança de créditos
                        await this.refreshMessageContext();
                    }
                }
            } catch (error) {
                console.warn('⚠️ [Auth] Erro ao carregar créditos:', error);
            }
        }

        // ==============================================
        // 🔥 SISTEMA DE MENSAGENS INTELIGENTES (NOVO V4.1)
        // ==============================================

        /**
         * 🔥 Carrega o contexto de mensagem do backend
         * Chamado automaticamente após login ou refresh
         */
        async loadMessageContext() {
            try {
                const token = localStorage.getItem('access_token');
                if (!token) {
                    console.log('ℹ️ [Auth] Sem token, pulando loadMessageContext');
                    return null;
                }
                
                // Usa fetch com auth se disponível
                let response;
                if (window.fetchWithAuth) {
                    response = await window.fetchWithAuth('/api/auth/session-status');
                } else {
                    response = await fetch('/api/auth/session-status', {
                        headers: { 'Authorization': `Bearer ${token}` }
                    });
                }
                
                if (!response) return null;
                
                if (response.ok) {
                    const data = await response.json();
                    console.log('📢 [Auth] Contexto de mensagem carregado:', {
                        segment: data.segment,
                        message_id: data.message_config?.message_id,
                        credits: data.credits,
                        hasMessage: !!data.message_config
                    });
                    
                    // 🔥 Atualiza o estado global com os dados da mensagem
                    this._updateMessageState(data);
                    
                    return data;
                } else if (response.status === 401) {
                    console.warn('⚠️ [Auth] Token expirado ao carregar mensagem');
                }
            } catch (error) {
                console.warn('⚠️ [Auth] Erro ao carregar contexto de mensagem:', error);
            }
            return null;
        }

        /**
         * 🔥 Atualiza o estado global com informações de mensagem
         */
        _updateMessageState(data) {
            if (!data) return;
            
            const stateManager = this._getStateManager();
            if (!stateManager) {
                console.warn('⚠️ [Auth] StateManager não disponível para mensagem');
                return;
            }
            
            // Prepara os dados da mensagem
            const messageConfig = data.message_config || null;
            const segment = data.segment || 'regular';
            const uiContext = data.ui_context || null;
            
            // 🔥 Atualiza o estado global com todos os campos
            const updates = {
                userSegment: segment,
                currentMessage: messageConfig,
                lastMessageId: messageConfig?.message_id || null,
                uiContext: uiContext
            };
            
            // Se tiver dados de promoção, atualiza também
            if (data.promotional) {
                updates.hasPromotionalPrice = data.promotional.has_locked_price || false;
                updates.promotionalPrice = data.promotional.locked_price || null;
            }
            
            stateManager.updateState(updates);
            
            console.log(`📢 [Auth] Estado de mensagem atualizado: segment=${segment}, hasMessage=${!!messageConfig}`);
            
            // Dispara evento para o MessageRenderer
            window.dispatchEvent(new CustomEvent('message:context_updated', {
                detail: {
                    segment: segment,
                    message: messageConfig,
                    ui_context: uiContext
                }
            }));
        }

        /**
         * 🔥 Força atualização da mensagem (chamado após mudança de créditos)
         */
        async refreshMessageContext() {
            console.log('🔄 [Auth] Atualizando contexto de mensagem...');
            return this.loadMessageContext();
        }

        // ==============================================
        // 🔥 SETUP LISTENERS
        // ==============================================

        setupAuthPageListeners() {
            document.getElementById('loginForm')?.addEventListener('submit', (e) => {
                e.preventDefault();
                this.handleLogin(e);
            });
            
            document.getElementById('registerForm')?.addEventListener('submit', (e) => {
                e.preventDefault();
                this.handleRegister(e);
            });
        }

        // ==============================================
        // 🔥 INICIALIZAÇÃO (CORRIGIDA)
        // ==============================================

        async init() {
            console.log('🚀 [Auth v4.1] Inicializando com sistema de mensagens...');
            
            this._initializing = true;
            this.initialized = true;
            
            this._rateLimitBlocked = false;
            this._rateLimitBlockedUntil = 0;
            this._rateLimitRemainingAttempts = RATE_LIMIT.LOGIN_MAX_ATTEMPTS;
            this._loginAttempts = 0;
            
            // 🔥 1. Carrega dados do localStorage (fallback)
            try {
                const userDataStr = localStorage.getItem('user_data');
                if (userDataStr) {
                    const userData = JSON.parse(userDataStr);
                    if (userData && userData.name) {
                        this.userData = {
                            ...userData,
                            name: userData.name || 'Usuário',
                            displayName: userData.name || 'Usuário',
                            workshop_name: userData.workshop_name || userData.workshopName || 'Oficina'
                        };
                        this.currentUser = this.userData;
                        console.log('📦 [Auth] Dados carregados do localStorage');
                    }
                }
            } catch (e) {
                // Ignora erro
            }
            
            // 🔥 2. Verifica token e sincroniza cookie
            const token = localStorage.getItem('access_token');
            if (token) {
                this._syncTokenToCookie(token);
                console.log('🍪 [Auth] Token sincronizado com cookie');
            }
            
            // 🔥 3. Verifica token com o backend
            await this.checkToken();
            
            // 🔥 4. Configura listeners
            this.setupAuthPageListeners();
            
            // 🔥 5. Se autenticado, carrega créditos e contexto de mensagem
            if (this.isAuthenticated) {
                await this.loadUserCredits();
                await this.loadMessageContext(); // 🔥 NOVO: Carrega mensagem
                this.startTokenMonitoring();
            }
            
            // 🔥 6. Sincroniza com app.js
            if (this.isAuthenticated && this.userData) {
                this._syncWithGlobalState();
            }
            
            // 🔥 7. Atualiza UI
            this._forceUIRefresh();
            
            this._initializing = false;
            
            console.log(`✅ [Auth v4.1] Inicializado. Autenticado: ${this.isAuthenticated}`);
            console.log(`👤 [Auth] Usuário: ${this.userData?.name || 'Não definido'}`);
            console.log(`👑 [Auth] Admin: ${this.isAdmin()}`);
            console.log(`⭐ [Auth] Premium: ${this.isPremium()}`);
            console.log(`💰 [Auth] Créditos: ${this.getCreditsDisplay()}`);
            console.log(`📢 [Auth] Segmento: ${this.userData?.segment || 'Não definido'}`);
            
            // 🔥 8. Dispara evento de ready
            window.dispatchEvent(new CustomEvent('authReady', {
                detail: {
                    isAuthenticated: this.isAuthenticated,
                    user: this.userData,
                    credits: this.getCredits(),
                    isPremium: this.isPremium(),
                    isAdmin: this.isAdmin(),
                    segment: this.userData?.segment || 'regular'
                }
            }));
            
            // 🔥 9. Verifica se o app.js está pronto e sincroniza novamente
            setTimeout(() => {
                if (this.isAuthenticated && this.userData) {
                    this._syncWithGlobalState();
                }
            }, 500);
            
            // 🔥 10. Recarrega mensagem após 1s para garantir
            setTimeout(() => {
                if (this.isAuthenticated) {
                    this.refreshMessageContext();
                }
            }, 1000);
        }
    }

    // ==============================================
    // 🔥 INSTÂNCIA GLOBAL
    // ==============================================

    window.appAuth = new Auth();

    console.log('✅ Auth carregado (v4.1 - Com Sistema de Mensagens)');
    console.log('   🔥 SINCRONIZADO com __APP_STATE');
    console.log('   🔥 ATUALIZA #userName (ID) e .user-name (classe)');
    console.log('   🔥 PRESERVA nome do usuário entre sessões');
    console.log('   🔥 FALLBACK: localStorage para dados do usuário');
    console.log('   🔥 EVENTOS: auth:state_changed, authLoginSuccess, authLogout');
    console.log('   📢 NOVO: Sistema de mensagens inteligentes');
    console.log('   📢 NOVO: loadMessageContext() para carregar mensagens');
    console.log('   📢 NOVO: refreshMessageContext() para atualização manual');
    console.log(`   ✅ MAX_CREDITS_BALANCE: ${MAX_CREDITS_BALANCE}`);
    console.log(`   ✅ TOKEN_EXPIRY_MINUTES: ${TOKEN_EXPIRY_MINUTES}`);
    console.log(`   ✅ RATE LIMITER: ${RATE_LIMIT.LOGIN_MAX_ATTEMPTS} tentativas/${RATE_LIMIT.LOGIN_WINDOW_SECONDS}s`);
    console.log('   🍪 COOKIE SYNC: Token sincronizado com cookie para links HTML');

})();