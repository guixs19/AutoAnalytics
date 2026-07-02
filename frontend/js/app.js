// frontend/js/app.js - ORQUESTRADOR CENTRAL - V6.2 (ROBUSTO)
/**
 * AutoAnalytics - Módulo Principal da Aplicação
 * 
 * 🏗️ ARQUITETURA V6.2:
 * 1. 🔥 CORREÇÃO: Reconhecimento automático do token + cookie sync
 * 2. 🔥 SINCRONIZAÇÃO: Com auth.js, payment.js, dashboard.js
 * 3. 🔥 ESTADO REATIVO: StateManager com eventos
 * 4. 🔥 FETCH UNIFICADO: Com refresh automático e rate limit
 * 5. 🔥 SISTEMA DE CRÉDITOS: Sincronizado com MAX_CREDITS_PREMIUM = 3
 * 6. 🔥 SEM POLLING EXCESSIVO: Event-driven com fallback
 * 7. 🔥 DEBUG COMPLETO: Logs para monitoramento
 * 8. 🔥 FALLBACK INTELIGENTE: Para casos de timeout
 */

(function() {
    'use strict';

    console.log('🚀 Inicializando App (Orquestrador) v6.2...');

    // ==============================================
    // 🔥 CORREÇÃO: FORÇAR RECONHECIMENTO DO TOKEN (com cookie sync)
    // ==============================================

    (function forceAuthRecognition() {
        try {
            // 🔥 Verifica cookie primeiro (para links HTML puros)
            const getCookie = (name) => {
                const value = `; ${document.cookie}`;
                const parts = value.split(`; ${name}=`);
                if (parts.length === 2) return parts.pop().split(';').shift();
                return null;
            };

            let token = localStorage.getItem('access_token');
            
            // Se não tiver token no localStorage, tenta o cookie
            if (!token || token === '' || token === 'undefined' || token === 'null') {
                const cookieToken = getCookie('access_token');
                if (cookieToken && cookieToken !== '' && cookieToken !== 'undefined' && cookieToken !== 'null') {
                    token = cookieToken;
                    localStorage.setItem('access_token', token);
                    console.log('🍪 Token restaurado do cookie para localStorage');
                }
            }

            const hasValidToken = token && token !== '' && token !== 'undefined' && token !== 'null' && token.length > 10;
            
            if (hasValidToken) {
                console.log('🔐 Token válido encontrado! Forçando autenticação...');
                
                // Pré-configura o estado global
                if (typeof window.__APP_STATE !== 'undefined') {
                    window.__APP_STATE.tokenValid = true;
                    window.__APP_STATE.userInitialized = true;
                    window.__APP_STATE.isAppReady = true;
                    
                    // Tenta restaurar dados do usuário
                    try {
                        const savedUser = localStorage.getItem('user_data');
                        if (savedUser) {
                            window.__APP_STATE.user = JSON.parse(savedUser);
                            console.log('👤 Usuário restaurado do localStorage:', window.__APP_STATE.user?.name);
                        } else {
                            // Cria usuário básico a partir do email salvo
                            const userEmail = localStorage.getItem('user_email') || 'usuario@email.com';
                            window.__APP_STATE.user = {
                                name: userEmail.split('@')[0] || 'Usuário',
                                email: userEmail,
                                credits: window.__APP_STATE.credits || 3
                            };
                            console.log('👤 Usuário padrão criado:', window.__APP_STATE.user.name);
                        }
                    } catch (e) {
                        console.warn('⚠️ Erro ao restaurar usuário:', e);
                        window.__APP_STATE.user = { name: 'Usuário', email: 'usuario@email.com', credits: 3 };
                    }
                }
                
                // 🔥 DISPARA EVENTO APPREADY IMEDIATAMENTE
                setTimeout(() => {
                    const eventData = {
                        isAuthenticated: true,
                        tokenValid: true,
                        userInitialized: true,
                        isReady: true,
                        version: '6.2',
                        user: window.__APP_STATE?.user || { name: 'Usuário' },
                        credits: window.__APP_STATE?.credits || 3,
                        isAdmin: window.__APP_STATE?.isAdmin || false,
                        isPremium: window.__APP_STATE?.isPremium || false
                    };
                    
                    console.log('📡 Disparando appReady (forçado)...');
                    window.dispatchEvent(new CustomEvent('appReady', { detail: eventData }));
                    document.dispatchEvent(new CustomEvent('app:ready', { detail: eventData }));
                    
                    // Dispara paymentReady também
                    setTimeout(() => {
                        window.dispatchEvent(new CustomEvent('paymentReady', {
                            detail: { loaded: true, version: '6.4', forced: true }
                        }));
                    }, 100);
                }, 50);
            } else {
                console.log('🔒 Nenhum token válido encontrado.');
            }
        } catch (e) {
            console.warn('⚠️ Erro no forceAuthRecognition:', e);
        }
    })();

    // ==============================================
    // 🔥 CONFIGURAÇÕES GLOBAIS
    // ==============================================

    const CONFIG = Object.freeze({
        MAX_FILES: 3,
        MAX_FILE_SIZE_KB: 200,
        MAX_CREDITS_BALANCE: 3,
        INITIAL_FREE_CREDITS: 3,
        
        PROMOTIONAL_PRICE: 97.00,
        REGULAR_PRICE: 149.90,
        TOTAL_PROMOTIONAL_SLOTS: 100,
        DAYS_PREMIUM: 30,
        
        TOKEN_EXPIRY_MINUTES: 15,
        SESSION_TIMEOUT: 15 * 60 * 1000,
        TOKEN_CHECK_INTERVAL: 60000,
        
        RATE_LIMIT_LOGIN_MAX: 5,
        RATE_LIMIT_LOGIN_WINDOW: 900,
        RATE_LIMIT_REGISTER_MAX: 5,
        RATE_LIMIT_REGISTER_WINDOW: 3600,
        
        POW_AUTO_REFILL_INTERVAL: 30000,
        POW_STOCK_SIZE: 2,
        
        API_BASE: '/api',
        CREDITS_UPDATE_INTERVAL: 300000, // 5 minutos (fallback)
        MAX_LOAD_ATTEMPTS: 10,
        LOAD_RETRY_DELAY: 500,
        
        ROUTES: {
            PROTECTED: ['/', '/dashboard', '/planos', '/checkout'],
            PUBLIC: ['/login', '/register'],
            HOME: '/dashboard',
            LOGIN: '/login'
        },
        
        RELOAD_COOLDOWN: 3000,
        MAX_RELOADS: 3,
        RELOAD_STORAGE_KEY: '_aa_reload_count',
        AUTH_BLOCK_KEY: '_aa_auth_block'
    });

    // ==============================================
    // 🔥 GERENCIADOR DE RELOAD (ANTI-LOOP)
    // ==============================================

    const ReloadManager = {
        _lastReload: 0,
        _reloadCount: 0,
        
        canReload: function() {
            const now = Date.now();
            
            if (now - this._lastReload < CONFIG.RELOAD_COOLDOWN) {
                console.warn('⛔ Cooldown ativo, evitando reload');
                return false;
            }
            
            let storedCount = parseInt(sessionStorage.getItem(CONFIG.RELOAD_STORAGE_KEY) || '0');
            if (storedCount >= CONFIG.MAX_RELOADS) {
                console.error('❌ Número máximo de reloads atingido. Redirecionando para login.');
                sessionStorage.removeItem(CONFIG.RELOAD_STORAGE_KEY);
                window.location.replace('/login');
                return false;
            }
            
            storedCount++;
            sessionStorage.setItem(CONFIG.RELOAD_STORAGE_KEY, String(storedCount));
            this._reloadCount = storedCount;
            this._lastReload = now;
            
            return true;
        },
        
        reset: function() {
            sessionStorage.removeItem(CONFIG.RELOAD_STORAGE_KEY);
            this._reloadCount = 0;
            this._lastReload = 0;
        },
        
        getCount: function() {
            return parseInt(sessionStorage.getItem(CONFIG.RELOAD_STORAGE_KEY) || '0');
        }
    };

    // ==============================================
    // 🔥 ESTADO GLOBAL (REATIVO)
    // ==============================================

    const State = {
        user: null,
        credits: 0,
        isPremium: false,
        isAdmin: false,
        creditsDisplay: '0',
        
        initialized: false,
        userInitialized: false,
        isAppReady: false,
        tokenValid: false,
        tokenExpiresAt: null,
        lastActivity: Date.now(),
        loadAttempts: 0,
        
        premiumStatus: null,
        hasPromotionalPrice: false,
        promotionalPrice: null,
        isVitalicio: false,
        daysLeftPremium: 0,
        canReceiveDailyCredit: false,
        receivedDailyCreditToday: false,
        
        powReady: false,
        powSolutionsReady: 0,
        powAutoRefillActive: false,
        
        rateLimitBlocked: false,
        rateLimitBlockedUntil: 0,
        rateLimitRemainingAttempts: CONFIG.RATE_LIMIT_LOGIN_MAX,
        rateLimitBlockedFor: 'login',
        
        activeAnalyses: [],
        recentAnalyses: [],
        totalAnalyses: 0,
        analysesToday: 0,
        
        _listeners: [],
        _intervals: []
    };

    // ==============================================
    // 🔥 GERENCIADOR DE ESTADO REATIVO
    // ==============================================

    const StateManager = {
        updateState: function(newState) {
            const previousState = { ...State };
            Object.assign(State, newState);
            
            if (newState.credits !== undefined || newState.isPremium !== undefined || newState.isAdmin !== undefined) {
                State.creditsDisplay = Utils.formatCreditsDisplay(State.credits, State.isPremium);
            }
            
            console.log('📊 [StateManager] Estado atualizado:', {
                credits: State.credits,
                isPremium: State.isPremium,
                isAdmin: State.isAdmin,
                creditsDisplay: State.creditsDisplay,
                tokenValid: State.tokenValid,
                userInitialized: State.userInitialized
            });
            
            const eventData = {
                state: State,
                changes: newState,
                previous: previousState,
                timestamp: Date.now()
            };
            
            // Dispara via EventBus
            EventBus.emit('app:state_changed', eventData);
            
            // Dispara via DOM (para payment.js e dashboard.js)
            window.dispatchEvent(new CustomEvent('app:state_changed', { 
                detail: eventData,
                bubbles: true 
            }));
            document.dispatchEvent(new CustomEvent('app:state_changed', { 
                detail: eventData,
                bubbles: true 
            }));
            
            // Atualiza UI
            UI.updateNavbar();
            UI.updateCredits();
            UI.updatePremiumBadge();
            UI.updateVitalicioBadge();
            UI.updateAdminBadge();
            
            return State;
        },
        
        updateCredits: function(credits, isPremium = null) {
            const updates = { credits: credits };
            if (isPremium !== null) updates.isPremium = isPremium;
            return this.updateState(updates);
        },
        
        updatePremiumStatus: function(status) {
            return this.updateState({
                isPremium: status.is_premium || false,
                daysLeftPremium: status.days_left || 0,
                hasPromotionalPrice: status.promotional_price_locked || false,
                promotionalPrice: status.promotional_price || null,
                canReceiveDailyCredit: status.can_receive_today || false,
                receivedDailyCreditToday: status.received_today || false,
                credits: status.credits_balance || State.credits
            });
        },
        
        getState: function() {
            return { ...State };
        }
    };

    // 🔥 EXPORTA ESTADO E GERENCIADOR
    window.__APP_STATE = State;
    window.__APP_STATE_MANAGER = StateManager;

    // ==============================================
    // 🔥 UTILITÁRIOS (SINCRONIZADOS)
    // ==============================================

    const Utils = {
        formatDate: (date) => {
            const d = new Date(date);
            return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR');
        },

        escapeHtml: (text) => {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        },

        sanitizeNumber: (value, defaultValue = 0) => {
            if (value === undefined || value === null) return defaultValue;
            const num = parseFloat(String(value).replace(/[^0-9.,-]/g, '').replace(',', '.'));
            return isNaN(num) ? defaultValue : num;
        },

        // 🔥 SINCRONIZADO COM crud.py: MAX_CREDITS_PREMIUM = 3
        formatCreditsDisplay: (credits, isPremium = false) => {
            if (State.isAdmin) return '∞';
            const safeCredits = Utils.sanitizeNumber(credits, 0);
            if (isPremium) {
                return `${safeCredits}/${CONFIG.MAX_CREDITS_BALANCE}`;
            }
            return safeCredits.toString();
        },

        // 🔥 BLINDAGEM: try/catch no showNotification
        showNotification: (message, type = 'info') => {
            if (window.appAuth?.showNotification) {
                try {
                    return window.appAuth.showNotification(message, type);
                } catch (e) {
                    console.warn('⚠️ appAuth.showNotification falhou:', e);
                }
            }
            
            if (window.toastr?.[type]) {
                try {
                    window.toastr[type](message);
                    return true;
                } catch (e) {
                    console.warn('⚠️ Toastr falhou:', e);
                    if (type === 'error' || type === 'warning') {
                        alert(`⚠️ ${message}`);
                        return true;
                    }
                }
            }
            
            if (type === 'error' || type === 'warning') {
                console.warn(`[${type}] ${message}`);
                alert(`⚠️ ${message}`);
                return true;
            }
            
            console.log(`[${type}] ${message}`);
            return true;
        },

        getCurrentPath: () => window.location.pathname,
        getQueryParam: (param) => new URLSearchParams(window.location.search).get(param),
        redirectTo: (url) => {
            if (window.location.pathname !== url) {
                window.location.href = url;
            }
        },
        goBack: () => window.history.back(),
        goForward: () => window.history.forward(),
        reload: () => {
            if (ReloadManager.canReload()) {
                window.location.reload();
            }
        },

        // 🔥 CORRIGIDO: SEM LOOP INFINITO
        isAuthenticated: () => {
            try {
                const token = localStorage.getItem('access_token');
                return token && token !== '' && token !== 'undefined' && token !== 'null' && token.length > 10;
            } catch (e) {
                return !!localStorage.getItem('access_token');
            }
        },

        isRateLimitBlocked: () => {
            if (State.rateLimitBlocked && Date.now() < State.rateLimitBlockedUntil) {
                return true;
            }
            if (State.rateLimitBlocked && Date.now() >= State.rateLimitBlockedUntil) {
                State.rateLimitBlocked = false;
                State.rateLimitBlockedUntil = 0;
                State.rateLimitRemainingAttempts = CONFIG.RATE_LIMIT_LOGIN_MAX;
                State.rateLimitBlockedFor = 'login';
                return false;
            }
            return false;
        },

        getRateLimitTimeRemaining: () => {
            if (!State.rateLimitBlocked) return 0;
            return Math.max(0, Math.ceil((State.rateLimitBlockedUntil - Date.now()) / 1000));
        },

        getRateLimitRemainingAttempts: () => State.rateLimitRemainingAttempts,

        waitFor: (condition, timeout = 10000, interval = 200) => {
            return new Promise((resolve, reject) => {
                const startTime = Date.now();
                const check = () => {
                    if (condition()) {
                        resolve(true);
                        return;
                    }
                    if (Date.now() - startTime > timeout) {
                        reject(new Error('Timeout ao aguardar condição'));
                        return;
                    }
                    setTimeout(check, interval);
                };
                check();
            });
        },

        waitForAuth: (maxAttempts = 30) => {
            return Utils.waitFor(
                () => window.appAuth && typeof window.appAuth.isAuthenticated !== 'undefined',
                6000,
                200
            ).catch(() => false);
        },

        waitForPayment: (maxAttempts = 30) => {
            return Utils.waitFor(
                () => !!(window.loadPremiumStatus || window.receiveDailyCredit || window.loadPlans || window.payment),
                6000,
                200
            ).catch(() => false);
        },

        waitForPow: (maxAttempts = 30) => {
            return Utils.waitFor(
                () => window.powClient && typeof window.powClient.preSolve === 'function',
                6000,
                200
            ).catch(() => false);
        }
    };

    // ==============================================
    // 🔥 EXPORTA UTILITÁRIOS GLOBAIS
    // ==============================================

    window.AppUtils = {
        sanitizeNumber: Utils.sanitizeNumber,
        formatCreditsDisplay: Utils.formatCreditsDisplay,
        escapeHtml: Utils.escapeHtml,
        formatDate: Utils.formatDate,
        showNotification: Utils.showNotification,
        isAuthenticated: Utils.isAuthenticated,
        getMaxCredits: () => CONFIG.MAX_CREDITS_BALANCE,
        getConfig: () => CONFIG,
        // 🔥 VALIDAÇÃO DE CPF (sincronizada com back-end)
        validateCPF: function(cpf) {
            const clean = String(cpf).replace(/\D/g, '');
            if (clean.length !== 11) return false;
            const invalid = ['00000000000', '11111111111', '22222222222', '33333333333',
                            '44444444444', '55555555555', '66666666666', '77777777777',
                            '88888888888', '99999999999'];
            if (invalid.includes(clean)) return false;
            let sum = 0;
            for (let i = 0; i < 9; i++) sum += parseInt(clean[i]) * (10 - i);
            let remainder = (sum * 10) % 11;
            if (remainder === 10 || remainder === 11) remainder = 0;
            if (remainder !== parseInt(clean[9])) return false;
            sum = 0;
            for (let i = 0; i < 10; i++) sum += parseInt(clean[i]) * (11 - i);
            remainder = (sum * 10) % 11;
            if (remainder === 10 || remainder === 11) remainder = 0;
            return remainder === parseInt(clean[10]);
        }
    };

    // ==============================================
    // 🔥 FETCH UNIFICADO (COM REFRESH AUTOMÁTICO)
    // ==============================================

    async function fetchWithAuth(url, options = {}) {
        try {
            const token = localStorage.getItem('access_token');
            if (!token) {
                console.warn('⚠️ fetchWithAuth: sem token');
                EventBus.emit('auth:unauthorized', { message: 'Token não encontrado' });
                return null;
            }
            
            const headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': `Bearer ${token}`,
                ...options.headers
            };
            
            if (options.body instanceof FormData) {
                delete headers['Content-Type'];
            }
            
            const response = await fetch(url, { ...options, headers });
            
            // 🔥 Tratamento 401 - Token expirado
            if (response.status === 401) {
                console.warn('⚠️ Token expirado, tentando refresh...');
                
                const refreshed = await refreshTokenSafely();
                if (refreshed) {
                    const newToken = localStorage.getItem('access_token');
                    if (newToken) {
                        headers['Authorization'] = `Bearer ${newToken}`;
                        const retryResponse = await fetch(url, { ...options, headers });
                        if (retryResponse.ok) {
                            return retryResponse;
                        }
                    }
                }
                
                console.error('❌ Falha ao renovar token, redirecionando para login');
                EventBus.emit('auth:unauthorized', { 
                    message: 'Sessão expirada',
                    redirect: true 
                });
                Auth.handleUnauthorized();
                return null;
            }
            
            // 🔥 Tratamento 429 - Rate Limit
            if (response.status === 429) {
                const data = await response.json().catch(() => ({}));
                const retryAfter = data.retry_after || 60;
                const remaining = data.remaining_attempts || 0;
                
                EventBus.emit('rate_limit:blocked', {
                    retryAfter: retryAfter,
                    remaining: remaining,
                    message: data.detail || data.message || 'Muitas requisições. Aguarde um momento.',
                    for: url
                });
                
                Utils.showNotification(`⏳ Aguarde ${retryAfter} segundos antes de tentar novamente.`, 'warning');
                return response;
            }
            
            // 🔥 Tratamento 402 - Créditos insuficientes (upload_routes.py)
            if (response.status === 402) {
                const data = await response.json().catch(() => ({}));
                console.warn('⚠️ Créditos insuficientes:', data);
                EventBus.emit('credits:insufficient', {
                    message: data.message || 'Créditos insuficientes',
                    credits_available: data.credits_available || 0,
                    credits_needed: data.credits_needed || 1
                });
                return response;
            }
            
            return response;
        } catch (error) {
            console.error('❌ fetchWithAuth error:', error);
            EventBus.emit('fetch:error', { 
                url, 
                error: error.message,
                options 
            });
            return null;
        }
    }

    async function refreshTokenSafely() {
        try {
            const refreshToken = localStorage.getItem('refresh_token');
            if (!refreshToken) {
                console.warn('⚠️ Sem refresh token disponível');
                return false;
            }
            
            const response = await fetch('/api/auth/refresh', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: refreshToken })
            });
            
            if (response.ok) {
                const data = await response.json();
                if (data.access_token) {
                    localStorage.setItem('access_token', data.access_token);
                    // 🔥 Sincroniza com cookie
                    document.cookie = `access_token=${data.access_token}; path=/; max-age=900; SameSite=Strict`;
                    if (data.refresh_token) {
                        localStorage.setItem('refresh_token', data.refresh_token);
                    }
                    if (data.user) {
                        localStorage.setItem('user_data', JSON.stringify(data.user));
                        localStorage.setItem('user_email', data.user.email || '');
                    }
                    console.log('✅ Token renovado com sucesso!');
                    EventBus.emit('auth:token_refreshed', { 
                        message: 'Token renovado automaticamente' 
                    });
                    return true;
                }
            }
            
            console.warn('⚠️ Falha ao renovar token');
            return false;
        } catch (error) {
            console.error('❌ Erro ao renovar token:', error);
            return false;
        }
    }

    // ==============================================
    // 🔥 INTERFACE DE AUTENTICAÇÃO (window.appAuth)
    // ==============================================

    window.appAuth = {
        isAuthenticated: () => Utils.isAuthenticated(),
        isAdmin: () => State.isAdmin,
        isPremium: () => State.isPremium,
        getCredits: () => State.credits,
        getCurrentUser: () => State.user,
        getState: () => StateManager.getState(),
        
        fetchWithAuth: fetchWithAuth,
        refreshTokenSafely: refreshTokenSafely,
        
        showNotification: (msg, type) => Utils.showNotification(msg, type),
        
        updateState: StateManager.updateState,
        updateCredits: StateManager.updateCredits,
        updatePremiumStatus: StateManager.updatePremiumStatus,
        
        // 🔥 CORRIGIDO: Carrega créditos e atualiza estado corretamente
        loadUserCredits: async () => {
            try {
                const response = await fetchWithAuth('/api/auth/me');
                if (response?.ok) {
                    const data = await response.json();
                    
                    // 🔥 Atualiza TUDO de uma vez
                    StateManager.updateState({
                        user: data.user || null,
                        credits: data.credits || 0,
                        isPremium: data.is_premium || false,
                        isAdmin: data.is_admin || false,
                        tokenValid: true,
                        userInitialized: true,
                        isAppReady: true
                    });
                    
                    // Salva no localStorage para fallback
                    if (data.user) {
                        try {
                            localStorage.setItem('user_data', JSON.stringify(data.user));
                            localStorage.setItem('user_email', data.user.email || '');
                        } catch (e) {}
                    }
                    
                    console.log(`✅ Créditos carregados: ${data.credits || 0}`);
                    return data;
                }
            } catch (e) {
                console.warn('Erro ao carregar créditos:', e);
            }
            return null;
        },
        
        // 🔥 MÉTODOS DE LOGIN/REGISTER (integração com auth.js)
        handleLogin: async (e) => {
            if (window.appAuth && typeof window.appAuth._handleLogin === 'function') {
                return window.appAuth._handleLogin(e);
            }
            // Fallback: usa o auth.js diretamente
            if (window.appAuthInstance && typeof window.appAuthInstance.handleLogin === 'function') {
                return window.appAuthInstance.handleLogin(e);
            }
            console.warn('⚠️ handleLogin não disponível');
            return false;
        },
        
        handleRegister: async (e) => {
            if (window.appAuth && typeof window.appAuth._handleRegister === 'function') {
                return window.appAuth._handleRegister(e);
            }
            if (window.appAuthInstance && typeof window.appAuthInstance.handleRegister === 'function') {
                return window.appAuthInstance.handleRegister(e);
            }
            console.warn('⚠️ handleRegister não disponível');
            return false;
        },
        
        getRateLimitStatus: () => ({
            blocked: State.rateLimitBlocked,
            blockedUntil: State.rateLimitBlockedUntil,
            remainingAttempts: State.rateLimitRemainingAttempts,
            for: State.rateLimitBlockedFor,
            timeRemaining: Utils.getRateLimitTimeRemaining()
        }),
        
        logout: () => Auth.handleUnauthorized()
    };

    // ==============================================
    // 🔥 ROTEADOR
    // ==============================================

    const Router = {
        _pathCache: new Map(),
        _lastPath: '',

        _getCachedPath: () => {
            const path = Utils.getCurrentPath();
            if (path !== Router._lastPath) {
                Router._pathCache.clear();
                Router._lastPath = path;
            }
            return path;
        },

        _isRouteMatch: (path, route) => {
            const cacheKey = `${path}|${route}`;
            if (Router._pathCache.has(cacheKey)) {
                return Router._pathCache.get(cacheKey);
            }

            let result = false;
            
            if (route === '/') {
                result = path === '/' || path === '/index.html' || path === '';
            } else {
                result = path === route || 
                        path.startsWith(route + '/') || 
                        path.startsWith(route + '?');
            }

            Router._pathCache.set(cacheKey, result);
            return result;
        },

        isProtected: () => {
            const path = Router._getCachedPath();
            return CONFIG.ROUTES.PROTECTED.some(route => 
                Router._isRouteMatch(path, route)
            );
        },

        isPublic: () => {
            const path = Router._getCachedPath();
            return CONFIG.ROUTES.PUBLIC.some(route => 
                Router._isRouteMatch(path, route)
            );
        },

        protect: function() {
            const isAuth = Utils.isAuthenticated();
            
            if (this.isProtected() && !isAuth) {
                console.log('🔒 Rota protegida - redirecionando para login');
                Utils.redirectTo(CONFIG.ROUTES.LOGIN);
                return false;
            }

            if (this.isPublic() && isAuth) {
                console.log('✅ Usuário já logado - redirecionando para dashboard');
                Utils.redirectTo(CONFIG.ROUTES.HOME);
                return false;
            }

            return true;
        },

        navigate: (url) => {
            const isProtected = CONFIG.ROUTES.PROTECTED.some(route => 
                Router._isRouteMatch(url, route)
            );
            
            if (isProtected && !Utils.isAuthenticated()) {
                Utils.showNotification('Faça login para acessar esta página.', 'warning');
                Utils.redirectTo(CONFIG.ROUTES.LOGIN);
                return;
            }

            Utils.redirectTo(url);
        },

        setupNavigation: () => {
            document.querySelectorAll('[data-nav]').forEach(el => {
                el.addEventListener('click', (e) => {
                    e.preventDefault();
                    const target = el.getAttribute('data-nav');
                    if (target) Router.navigate(target);
                });
            });

            document.querySelectorAll('a[href^="/"]').forEach(el => {
                if (el.hasAttribute('data-nav') || 
                    el.getAttribute('target') === '_blank' || 
                    el.id === 'logoutBtn') return;
                
                el.addEventListener('click', (e) => {
                    const href = el.getAttribute('href');
                    if (href && !href.startsWith('http') && !href.startsWith('#')) {
                        e.preventDefault();
                        Router.navigate(href);
                    }
                });
            });
        },

        clearCache: () => {
            Router._pathCache.clear();
            Router._lastPath = '';
        }
    };

    // ==============================================
    // 🔥 BARREMENTO DE EVENTOS UNIFICADO
    // ==============================================

    const EventBus = {
        _handlers: new Map(),
        
        on: function(event, handler, options = {}) {
            if (!this._handlers.has(event)) {
                this._handlers.set(event, []);
            }
            this._handlers.get(event).push({
                handler,
                once: options.once || false,
                priority: options.priority || 0
            });
            
            this._handlers.get(event).sort((a, b) => b.priority - a.priority);
        },
        
        once: function(event, handler) {
            this.on(event, handler, { once: true });
        },
        
        off: function(event, handler) {
            if (!this._handlers.has(event)) return;
            
            const handlers = this._handlers.get(event);
            const index = handlers.findIndex(h => h.handler === handler);
            if (index !== -1) {
                handlers.splice(index, 1);
            }
            
            if (handlers.length === 0) {
                this._handlers.delete(event);
            }
        },
        
        emit: function(event, data = {}) {
            console.log(`📢 [EventBus] ${event}`, data);
            
            try {
                window.dispatchEvent(new CustomEvent(event, { detail: data, bubbles: true }));
                document.dispatchEvent(new CustomEvent(event, { detail: data, bubbles: true }));
            } catch (e) {}
            
            if (!this._handlers.has(event)) return;
            
            const handlers = this._handlers.get(event);
            const toRemove = [];
            
            for (let i = 0; i < handlers.length; i++) {
                const { handler, once } = handlers[i];
                try {
                    handler(data);
                } catch (e) {
                    console.error(`❌ Erro no handler do evento ${event}:`, e);
                }
                if (once) {
                    toRemove.push(i);
                }
            }
            
            if (toRemove.length > 0) {
                const remaining = handlers.filter((_, index) => !toRemove.includes(index));
                if (remaining.length === 0) {
                    this._handlers.delete(event);
                } else {
                    this._handlers.set(event, remaining);
                }
            }
        },
        
        clear: function() {
            this._handlers.clear();
        }
    };

    // ==============================================
    // 🔥 GERENCIADOR DE UI
    // ==============================================

    const UI = {
        _elements: new Map(),

        _getElement: (selector) => {
            if (!UI._elements.has(selector)) {
                const el = document.querySelector(selector);
                UI._elements.set(selector, el);
                return el;
            }
            return UI._elements.get(selector);
        },

        updateNavbar: () => {
            const isAuth = Utils.isAuthenticated();
            
            document.querySelectorAll('.auth-required').forEach(el => {
                el.style.display = isAuth ? 'block' : 'none';
            });
            document.querySelectorAll('.guest-only').forEach(el => {
                el.style.display = isAuth ? 'none' : 'block';
            });

            if (isAuth) {
                try {
                    const name = State.user?.name || 'Usuário';
                    
                    document.querySelectorAll('.user-name').forEach(el => {
                        el.textContent = name;
                    });
                    document.querySelectorAll('.workshop-name').forEach(el => {
                        el.textContent = State.user?.workshop_name || 'Oficina';
                    });

                    UI.updateCredits();
                    UI.updateAdminBadge();
                    UI.updatePremiumBadge();
                    UI.updateVitalicioBadge();
                    UI.updatePowStatus();
                    UI.updateRateLimitStatus();
                } catch (e) {
                    console.warn('Erro ao atualizar navbar:', e);
                }
            }
        },

        updateCredits: () => {
            try {
                const credits = State.credits || 0;
                const isPremium = State.isPremium || false;
                const isAdmin = State.isAdmin || false;
                
                const formattedDisplay = Utils.formatCreditsDisplay(credits, isPremium);
                State.creditsDisplay = formattedDisplay;
                
                const selectors = [
                    '.credits-display', '.user-credits', 
                    '#creditsDisplay', '#creditsCount', '#uploadCredits',
                    '.credits-badge span', '.credits-value'
                ];
                
                document.querySelectorAll(selectors.join(',')).forEach(el => {
                    if (el) el.textContent = formattedDisplay;
                });

                document.querySelectorAll('[data-credits-tooltip]').forEach(el => {
                    if (isPremium) {
                        el.title = `${credits}/${CONFIG.MAX_CREDITS_BALANCE} créditos (máximo ${CONFIG.MAX_CREDITS_BALANCE})`;
                    } else {
                        el.title = `${credits} créditos`;
                    }
                });

                EventBus.emit('credits:updated', {
                    credits,
                    display: formattedDisplay,
                    maxCredits: CONFIG.MAX_CREDITS_BALANCE,
                    isPremium
                });

            } catch (e) {
                console.warn('Erro ao atualizar créditos:', e);
            }
        },

        updateAdminBadge: () => {
            const isAdmin = State.isAdmin || false;
            
            document.querySelectorAll('.admin-badge, .admin-only').forEach(el => {
                el.style.display = isAdmin ? 'inline-block' : 'none';
            });
            document.body.classList.toggle('is-admin', isAdmin);
        },

        updatePremiumBadge: () => {
            const isPremium = State.isPremium || false;
            
            document.querySelectorAll('.premium-badge, .premium-only').forEach(el => {
                el.style.display = isPremium ? 'inline-block' : 'none';
            });

            if (isPremium && State.daysLeftPremium > 0) {
                document.querySelectorAll('.premium-days-badge').forEach(el => {
                    el.textContent = `${State.daysLeftPremium} dias`;
                    el.style.display = 'inline-block';
                });
            } else {
                document.querySelectorAll('.premium-days-badge').forEach(el => {
                    el.style.display = 'none';
                });
            }

            document.body.classList.toggle('is-premium', isPremium);
        },

        updateVitalicioBadge: () => {
            const hasVitalicio = State.hasPromotionalPrice && State.promotionalPrice !== null;
            
            document.querySelectorAll('.vitalicio-badge, .vitalicio-only').forEach(el => {
                el.style.display = hasVitalicio ? 'inline-block' : 'none';
            });

            if (hasVitalicio) {
                document.querySelectorAll('.vitalicio-price').forEach(el => {
                    el.textContent = `R$ ${State.promotionalPrice.toFixed(2).replace('.', ',')}`;
                });
                document.body.classList.add('has-vitalicio');
            } else {
                document.body.classList.remove('has-vitalicio');
            }
        },

        updatePowStatus: () => {
            try {
                if (window.powClient?.getStats) {
                    const stats = window.powClient.getStats();
                    State.powSolutionsReady = stats.solutionsReady || 0;
                    State.powAutoRefillActive = stats.autoRefill || false;
                    
                    const powBadge = document.getElementById('powStatus');
                    if (powBadge) {
                        if (stats.solutionsReady > 0) {
                            powBadge.textContent = `⚡ ${stats.solutionsReady}`;
                            powBadge.className = 'badge bg-success';
                            powBadge.style.display = 'inline-block';
                        } else {
                            powBadge.textContent = '⚡ 0';
                            powBadge.className = 'badge bg-warning';
                            powBadge.style.display = 'inline-block';
                        }
                    }
                }
            } catch (e) {
                console.warn('Erro ao atualizar status PoW:', e);
            }
        },

        updateRateLimitStatus: () => {
            const isBlocked = Utils.isRateLimitBlocked();
            const timeRemaining = Utils.getRateLimitTimeRemaining();
            const remainingAttempts = Utils.getRateLimitRemainingAttempts();
            
            const rateLimitBadge = document.getElementById('rateLimitStatus');
            if (rateLimitBadge) {
                if (isBlocked) {
                    const minutes = Math.floor(timeRemaining / 60);
                    const seconds = timeRemaining % 60;
                    rateLimitBadge.textContent = `⛔ ${minutes}m${seconds}s`;
                    rateLimitBadge.className = 'badge bg-danger';
                    rateLimitBadge.style.display = 'inline-block';
                } else {
                    rateLimitBadge.style.display = 'none';
                }
            }

            const loginBtn = document.getElementById('loginBtn');
            if (loginBtn) {
                if (isBlocked) {
                    const minutes = Math.floor(timeRemaining / 60);
                    const seconds = timeRemaining % 60;
                    let timeMsg = '';
                    if (minutes > 0) {
                        timeMsg = `${minutes}m`;
                        if (seconds > 0) timeMsg += ` ${seconds}s`;
                    } else {
                        timeMsg = `${seconds}s`;
                    }
                    loginBtn.disabled = true;
                    loginBtn.innerHTML = `<i class="fas fa-hourglass-half me-2"></i> Aguarde ${timeMsg}`;
                    
                    clearTimeout(window._rateLimitLoginTimer);
                    window._rateLimitLoginTimer = setTimeout(() => {
                        loginBtn.disabled = false;
                        loginBtn.innerHTML = '<i class="fas fa-sign-in-alt me-2"></i> Entrar';
                        State.rateLimitBlocked = false;
                        State.rateLimitBlockedUntil = 0;
                        UI.updateRateLimitStatus();
                    }, timeRemaining * 1000);
                } else if (!loginBtn.disabled) {
                    loginBtn.disabled = false;
                    loginBtn.innerHTML = '<i class="fas fa-sign-in-alt me-2"></i> Entrar';
                }
            }

            const registerBtn = document.getElementById('registerBtn');
            if (registerBtn) {
                if (isBlocked && State.rateLimitBlockedFor === 'register') {
                    const minutes = Math.floor(timeRemaining / 60);
                    const seconds = timeRemaining % 60;
                    let timeMsg = '';
                    if (minutes > 0) {
                        timeMsg = `${minutes}m`;
                        if (seconds > 0) timeMsg += ` ${seconds}s`;
                    } else {
                        timeMsg = `${seconds}s`;
                    }
                    registerBtn.disabled = true;
                    registerBtn.innerHTML = `<i class="fas fa-hourglass-half me-2"></i> Aguarde ${timeMsg}`;
                    
                    clearTimeout(window._rateLimitRegisterTimer);
                    window._rateLimitRegisterTimer = setTimeout(() => {
                        registerBtn.disabled = false;
                        registerBtn.innerHTML = '<i class="fas fa-user-plus me-2"></i> Criar Conta';
                        State.rateLimitBlocked = false;
                        State.rateLimitBlockedUntil = 0;
                        UI.updateRateLimitStatus();
                    }, timeRemaining * 1000);
                } else if (!registerBtn.disabled) {
                    registerBtn.disabled = false;
                    registerBtn.innerHTML = '<i class="fas fa-user-plus me-2"></i> Criar Conta';
                }
            }

            document.querySelectorAll('[data-rate-limit-tooltip]').forEach(el => {
                if (isBlocked) {
                    const minutes = Math.floor(timeRemaining / 60);
                    const seconds = timeRemaining % 60;
                    el.title = `Bloqueado por ${minutes}m${seconds}s. ${remainingAttempts} tentativas restantes.`;
                } else {
                    el.title = `${remainingAttempts} tentativas disponíveis`;
                }
            });
        },

        showLoading: (message = 'Processando...', submessage = '') => {
            const overlay = document.getElementById('loadingOverlay');
            if (overlay) {
                const text = document.getElementById('loadingText');
                const subtext = document.getElementById('loadingSubtext');
                const progress = document.getElementById('loadingProgressBar');
                
                if (text) text.textContent = message;
                if (subtext) subtext.textContent = submessage || 'Aguarde...';
                if (progress) progress.style.width = '0%';
                
                overlay.classList.add('show');
            } else {
                console.log('⏳ Loading:', message);
            }
        },

        hideLoading: () => {
            const overlay = document.getElementById('loadingOverlay');
            if (overlay) {
                overlay.classList.remove('show');
            }
        },

        updateLoadingProgress: (percent, message = null) => {
            const progress = document.getElementById('loadingProgressBar');
            const text = document.getElementById('loadingText');
            
            if (progress) progress.style.width = `${Math.min(100, percent)}%`;
            if (message && text) text.textContent = message;
        },

        setupModals: () => {
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') {
                    document.querySelectorAll('.modal.show').forEach(modal => {
                        try {
                            const instance = bootstrap.Modal.getInstance(modal);
                            if (instance) instance.hide();
                        } catch (e) {}
                    });
                }
            });

            document.querySelectorAll('.modal').forEach(modal => {
                modal.addEventListener('click', (e) => {
                    if (e.target === modal) {
                        try {
                            const instance = bootstrap.Modal.getInstance(modal);
                            if (instance) instance.hide();
                        } catch (e) {}
                    }
                });
            });
        },

        clearElementCache: () => {
            UI._elements.clear();
        }
    };

    // ==============================================
    // 🔥 GERENCIADOR DE AUTENTICAÇÃO
    // ==============================================

    const Auth = {
        _sessionTimeout: null,

        startSessionTimer: () => {
            if (Auth._sessionTimeout) {
                clearTimeout(Auth._sessionTimeout);
                Auth._sessionTimeout = null;
            }

            if (!Utils.isAuthenticated()) return;

            console.log(`⏰ Timer de sessão: ${CONFIG.SESSION_TIMEOUT/60000} minutos`);

            Auth._sessionTimeout = setTimeout(() => {
                console.log('⏰ Sessão expirada por inatividade');
                Utils.showNotification('⏰ Sessão expirada por inatividade. Faça login novamente.', 'warning');
                
                const eventData = { message: 'Sessão expirada por inatividade' };
                EventBus.emit('auth:session_expired', eventData);
                window.dispatchEvent(new CustomEvent('auth:session_expired', { detail: eventData }));
                
                Auth.handleUnauthorized();
            }, CONFIG.SESSION_TIMEOUT);
        },

        resetSessionTimer: () => {
            if (!Utils.isAuthenticated()) return;
            
            const now = Date.now();
            if (now - State.lastActivity > 30000) {
                Auth.startSessionTimer();
            }
        },

        // 🔥 REMOVIDO: startTokenCheck (desnecessário - fetchWithAuth já trata 401)

        handleUnauthorized: function() {
            console.error('❌ [Orquestrador] Sessão inválida ou expirada.');
            
            sessionStorage.setItem(CONFIG.AUTH_BLOCK_KEY, String(Date.now()));
            
            // 🔥 Limpa localStorage e cookies
            localStorage.clear();
            document.cookie.split(';').forEach(function(c) {
                document.cookie = c.replace(/^ +/, '').replace(/=.*/, '=;expires=' + new Date().toUTCString() + ';path=/');
            });
            
            StateManager.updateState({
                user: null,
                credits: 0,
                isPremium: false,
                isAdmin: false,
                tokenValid: false,
                isAppReady: false,
                userInitialized: false
            });
            
            const eventData = { 
                message: 'Sessão inválida ou expirada',
                redirect: true 
            };
            
            EventBus.emit('auth:unauthorized', eventData);
            window.dispatchEvent(new CustomEvent('auth:unauthorized', { detail: eventData }));
            
            UI.updateNavbar();
            UI.updateRateLimitStatus();
            
            setTimeout(() => {
                window.location.replace('/login');
            }, 300);
        },

        stop: () => {
            if (Auth._sessionTimeout) {
                clearTimeout(Auth._sessionTimeout);
                Auth._sessionTimeout = null;
            }
        }
    };

    // ==============================================
    // 🔥 GERENCIADOR DE CRÉDITOS (EVENT-DRIVEN)
    // ==============================================

    const Credits = {
        _updateInterval: null,

        load: async () => {
            if (window.appAuth?.loadUserCredits) {
                try {
                    await window.appAuth.loadUserCredits();
                    return State;
                } catch (e) {
                    console.warn('Erro ao carregar créditos:', e);
                }
            }
            return null;
        },

        loadPremiumStatus: async () => {
            // 🔥 PRIORIDADE: Usar window.loadPremiumStatus do payment.js
            if (window.loadPremiumStatus && typeof window.loadPremiumStatus === 'function') {
                try {
                    const status = await window.loadPremiumStatus();
                    if (status) {
                        StateManager.updatePremiumStatus(status);
                        return status;
                    }
                } catch (e) {
                    console.warn('Erro ao carregar status premium via payment.js:', e);
                }
            }
            
            try {
                const token = localStorage.getItem('access_token');
                if (!token) return null;
                
                const response = await fetchWithAuth('/api/payments/premium-status');
                if (response?.ok) {
                    const status = await response.json();
                    StateManager.updatePremiumStatus(status);
                    return status;
                }
            } catch (e) {
                console.warn('Erro ao carregar status premium via fallback:', e);
            }
            
            return null;
        },

        receiveDailyCredit: async () => {
            if (window.receiveDailyCredit) {
                try {
                    const result = await window.receiveDailyCredit();
                    if (result?.success) {
                        Utils.showNotification('✅ Crédito diário recebido com sucesso!', 'success');
                        await Credits.load();
                        await Credits.loadPremiumStatus();
                        return result;
                    }
                } catch (e) {
                    console.warn('Erro ao receber crédito diário:', e);
                    Utils.showNotification('Erro ao receber crédito. Tente novamente.', 'error');
                }
            }
            return null;
        },

        // 🔥 POLLING REDUZIDO (apenas fallback - 5 minutos)
        startPolling: () => {
            if (Credits._updateInterval) {
                clearInterval(Credits._updateInterval);
            }
            
            Credits.load();
            
            Credits._updateInterval = setInterval(() => {
                Credits.load();
            }, CONFIG.CREDITS_UPDATE_INTERVAL); // 5 minutos
            
            console.log(`⏰ Atualização de créditos (fallback): ${CONFIG.CREDITS_UPDATE_INTERVAL/1000}s`);
        },

        stop: () => {
            if (Credits._updateInterval) {
                clearInterval(Credits._updateInterval);
                Credits._updateInterval = null;
            }
        }
    };

    // ==============================================
    // 🔥 GERENCIADOR DE EVENTOS (SINCRONIZADO)
    // ==============================================

    const EventManager = {
        setup: () => {
            console.log('📡 Configurando gerenciador de eventos...');
            
            // 🔥 ESCUTA EVENTOS DO payment.js (camelCase)
            document.addEventListener('creditsUpdated', function(e) {
                console.log('📢 creditsUpdated recebido do payment.js');
                const data = e.detail || {};
                StateManager.updateCredits(data.credits || 0, data.isPremium || false);
            });
            
            document.addEventListener('premiumStatusUpdated', function(e) {
                console.log('📢 premiumStatusUpdated recebido do payment.js');
                const data = e.detail || {};
                StateManager.updatePremiumStatus({
                    is_premium: data.isPremium || false,
                    days_left: data.daysLeft || 0,
                    promotional_price_locked: data.hasPromotionalPrice || false,
                    promotional_price: data.promotionalPrice || null,
                    can_receive_today: data.canReceiveDailyCredit || false,
                    received_today: data.receivedDailyCreditToday || false,
                    credits_balance: data.creditsBalance || State.credits
                });
            });
            
            document.addEventListener('paymentReady', function(e) {
                console.log('📢 paymentReady recebido');
                window._paymentReady = true;
                setTimeout(() => {
                    Credits.loadPremiumStatus();
                    Credits.load();
                }, 300);
            });
            
            // 🔥 ESCUTA EVENTOS DO dashboard.js
            document.addEventListener('analysis:success', function(e) {
                console.log('📢 analysis:success recebido do dashboard');
                const detail = e.detail || {};
                if (detail.result?.user_credits !== undefined) {
                    StateManager.updateCredits(detail.result.user_credits);
                }
                if (detail.result?.credits_balance !== undefined) {
                    StateManager.updateCredits(detail.result.credits_balance);
                }
            });
            
            // 🔥 ESCUTA EVENTOS DO upload_routes.py (via fetch)
            document.addEventListener('upload:completed', function(e) {
                console.log('📢 upload:completed recebido');
                const detail = e.detail || {};
                if (detail.credits_remaining !== undefined) {
                    StateManager.updateCredits(detail.credits_remaining);
                }
                setTimeout(() => Credits.load(), 1000);
            });

            // 🔥 ESCUTA CRÉDITOS INSUFICIENTES (402)
            document.addEventListener('credits:insufficient', function(e) {
                console.log('📢 credits:insufficient recebido');
                const detail = e.detail || {};
                Utils.showNotification(detail.message || 'Créditos insuficientes!', 'warning');
                window.dispatchEvent(new CustomEvent('payment:show_upgrade_modal', {
                    detail: {
                        message: detail.message,
                        credits_available: detail.credits_available,
                        credits_needed: detail.credits_needed
                    }
                }));
            });
            
            // 🔥 ESCUTA RATE LIMIT (429)
            document.addEventListener('rate_limit:blocked', function(e) {
                console.log('📢 rate_limit:blocked recebido');
                const detail = e.detail || {};
                State.rateLimitBlocked = true;
                State.rateLimitBlockedUntil = Date.now() + (detail.retryAfter || 60) * 1000;
                State.rateLimitRemainingAttempts = detail.remaining || 0;
                UI.updateRateLimitStatus();
                Utils.showNotification(detail.message || 'Muitas tentativas. Aguarde um momento.', 'warning');
            });
            
            // 🔥 ESCUTA AUTH READY (do auth.js)
            document.addEventListener('authReady', function(e) {
                console.log('📢 authReady recebido do auth.js');
                const detail = e.detail || {};
                if (detail.isAuthenticated) {
                    StateManager.updateState({
                        tokenValid: true,
                        userInitialized: true,
                        isAppReady: true
                    });
                    setTimeout(() => Credits.load(), 500);
                }
            });

            // 🔥 ESCUTA AUTH LOGOUT
            document.addEventListener('authLogout', function() {
                console.log('📢 authLogout recebido');
                Auth.handleUnauthorized();
            });
            
            console.log('✅ Event listeners configurados');
        },

        clear: () => {}
    };

    // ==============================================
    // 🔥 GERENCIADOR DE SINCRONIZAÇÃO
    // ==============================================

    const Sync = {
        syncAuth: async () => {
            if (!window.appAuth) {
                console.warn('⚠️ Auth não inicializado.');
                return false;
            }

            try {
                const isAuth = Utils.isAuthenticated();
                
                if (isAuth) {
                    // Carrega dados do usuário
                    await window.appAuth.loadUserCredits();
                    
                    StateManager.updateState({
                        tokenValid: true,
                        userInitialized: true
                    });
                    
                    UI.updateNavbar();
                    Credits.startPolling();
                    Auth.startSessionTimer();
                    
                    if (typeof window.initPowClient === 'function') {
                        console.log('🔐 Usuário autenticado, inicializando PoW...');
                        setTimeout(() => {
                            window.initPowClient({
                                autoRefill: false,
                                preSolve: false
                            });
                        }, 1000);
                    }
                } else {
                    StateManager.updateState({
                        tokenValid: false,
                        userInitialized: false
                    });
                }

                return isAuth;
            } catch (e) {
                console.error('Erro ao sincronizar auth:', e);
                StateManager.updateState({ userInitialized: false });
                return false;
            }
        },

        syncPayment: async () => {
            if (!window.appAuth) return;
            
            try {
                const paymentLoaded = await Utils.waitForPayment(30);
                
                if (paymentLoaded) {
                    if (typeof window.loadPremiumStatus === 'function') {
                        await Credits.loadPremiumStatus();
                    }
                    console.log('✅ Payment sincronizado com sucesso!');
                } else {
                    console.warn('⚠️ Payment não carregou. Tentando novamente...');
                    setTimeout(() => {
                        if (typeof window.loadPremiumStatus === 'function') {
                            Credits.loadPremiumStatus();
                        }
                    }, 5000);
                }
            } catch (e) {
                console.warn('Erro ao sincronizar payment:', e);
            }
        },

        syncPromotion: async () => {
            try {
                const token = localStorage.getItem('access_token');
                if (!token) return;
                
                const response = await fetchWithAuth('/api/payments/promotion-status');
                if (response?.ok) {
                    const data = await response.json();
                    
                    StateManager.updateState({
                        hasPromotionalPrice: data.user_locked_price !== null && data.user_locked_price !== undefined,
                        promotionalPrice: data.user_locked_price || null,
                        remainingSlots: data.remaining_slots,
                        totalSlots: data.total_slots
                    });
                    
                    EventBus.emit('premium:promotion_updated', {
                        hasPromotionalPrice: State.hasPromotionalPrice,
                        promotionalPrice: State.promotionalPrice,
                        remainingSlots: data.remaining_slots,
                        totalSlots: data.total_slots
                    });
                    
                    UI.updateVitalicioBadge();
                }
            } catch (e) {
                console.warn('Erro ao sincronizar promoção:', e);
            }
        },

        syncRateLimit: () => {
            if (window.appAuth?.getRateLimitStatus) {
                const status = window.appAuth.getRateLimitStatus();
                if (status) {
                    StateManager.updateState({
                        rateLimitBlocked: status.blocked || false,
                        rateLimitBlockedUntil: status.blockedUntil || 0,
                        rateLimitRemainingAttempts: status.remainingAttempts || CONFIG.RATE_LIMIT_LOGIN_MAX,
                        rateLimitBlockedFor: status.for || 'login'
                    });
                    UI.updateRateLimitStatus();
                }
            }
        }
    };

    // ==============================================
    // 🔥 GERENCIADOR DE PoW
    // ==============================================

    const Pow = {
        isAvailable: () => {
            return window.powClient !== undefined && window.powClient !== null;
        },

        getStats: () => {
            if (!Pow.isAvailable()) {
                return { available: false, solutionsReady: 0 };
            }
            try {
                if (typeof window.powClient.getStats === 'function') {
                    const stats = window.powClient.getStats();
                    return {
                        available: true,
                        solutionsReady: stats.solutionsReady || 0,
                        maxStock: stats.maxStock || CONFIG.POW_STOCK_SIZE,
                        autoRefill: stats.autoRefill || false,
                        isSolving: stats.isSolving || false,
                        isAuthenticated: stats.isAuthenticated || false,
                        lastSolutionAge: stats.lastSolutionAge || null
                    };
                }
            } catch (e) {
                console.warn('Erro ao obter stats PoW:', e);
            }
            return { available: false, solutionsReady: 0 };
        },

        prepareForUpload: async () => {
            if (!Pow.isAvailable()) {
                console.log('⏳ PoW não disponível para preparar upload');
                return false;
            }
            try {
                if (typeof window.powClient.prepareForUpload === 'function') {
                    const result = await window.powClient.prepareForUpload();
                    if (typeof window.powClient.getStats === 'function') {
                        const stats = window.powClient.getStats();
                        State.powSolutionsReady = stats.solutionsReady || 0;
                        UI.updatePowStatus();
                    }
                    return result;
                }
            } catch (e) {
                console.warn('Erro ao preparar PoW para upload:', e);
            }
            return false;
        },

        uploadWithPow: async (files, endpoint = '/api/upload-auto') => {
            if (!Pow.isAvailable()) {
                console.log('⏳ PoW não disponível, usando upload normal');
                // Fallback: upload normal
                const formData = new FormData();
                if (Array.isArray(files)) {
                    for (const file of files) {
                        formData.append('files', file);
                    }
                } else {
                    formData.append('files', files);
                }
                
                const token = localStorage.getItem('access_token');
                const response = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` },
                    body: formData
                });
                return response;
            }

            try {
                if (typeof window.powClient.uploadWithPow === 'function') {
                    // Se for array, processa um por um ou usa o método multi
                    if (Array.isArray(files) && files.length > 1) {
                        // Para múltiplos arquivos, usa upload normal com headers PoW
                        const solution = await window.powClient.getSolutionForUpload();
                        const formData = new FormData();
                        for (const file of files) {
                            formData.append('files', file);
                        }
                        
                        const token = localStorage.getItem('access_token');
                        const headers = { 'Authorization': `Bearer ${token}` };
                        if (solution && solution.prefix && solution.nonce) {
                            headers['X-PoW-Challenge'] = solution.prefix;
                            headers['X-PoW-Nonce'] = solution.nonce;
                        }
                        
                        const response = await fetch(endpoint, {
                            method: 'POST',
                            headers: headers,
                            body: formData
                        });
                        return response;
                    }
                    
                    // Arquivo único
                    const file = Array.isArray(files) ? files[0] : files;
                    return await window.powClient.uploadWithPow(file, endpoint);
                }
            } catch (e) {
                console.error('Erro no upload com PoW:', e);
                throw e;
            }
            throw new Error('Método uploadWithPow não disponível');
        }
    };

    // ==============================================
    // 🔥 GERENCIADOR DE ANÁLISES
    // ==============================================

    const Analysis = {
        startAnalysis: (data) => {
            const analysis = {
                id: Date.now(),
                timestamp: new Date().toISOString(),
                status: 'processing',
                progress: 0,
                files: data.files || [],
                ...data
            };
            
            State.activeAnalyses.push(analysis);
            
            EventBus.emit('analysis:started', {
                analysis,
                activeCount: State.activeAnalyses.length
            });
            
            return analysis;
        },

        updateProgress: (analysisId, progress, status = 'processing') => {
            const analysis = State.activeAnalyses.find(a => a.id === analysisId);
            if (analysis) {
                analysis.progress = progress;
                analysis.status = status;
                analysis.lastUpdate = new Date().toISOString();
                EventBus.emit('analysis:progress', { analysis, progress, status });
            }
        },

        completeAnalysis: function(analysisId, result) {
            const index = State.activeAnalyses.findIndex(a => a.id === analysisId);
            if (index !== -1) {
                const analysis = State.activeAnalyses[index];
                analysis.status = 'completed';
                analysis.result = result;
                analysis.completedAt = new Date().toISOString();
                
                State.activeAnalyses.splice(index, 1);
                State.recentAnalyses.unshift(analysis);
                State.totalAnalyses++;
                
                if (State.recentAnalyses.length > 50) {
                    State.recentAnalyses = State.recentAnalyses.slice(0, 50);
                }

                if (result && result.user_credits !== undefined) {
                    StateManager.updateCredits(result.user_credits);
                }
                
                EventBus.emit('analysis:success', {
                    analysis,
                    result,
                    total: State.totalAnalyses,
                    today: State.analysesToday,
                    creditsUpdated: result?.credits || 0
                });
                
                UI.updateCredits();
            }
        },

        failAnalysis: function(analysisId, error) {
            const index = State.activeAnalyses.findIndex(a => a.id === analysisId);
            if (index !== -1) {
                const analysis = State.activeAnalyses[index];
                analysis.status = 'failed';
                analysis.error = error;
                analysis.failedAt = new Date().toISOString();
                
                State.activeAnalyses.splice(index, 1);
                
                EventBus.emit('analysis:error', {
                    analysis,
                    error,
                    message: error.message || 'Erro na análise'
                });
            }
        },

        getActiveAnalyses: () => State.activeAnalyses,
        getRecentAnalyses: () => State.recentAnalyses.slice(0, 10),
        getTotalAnalyses: () => State.totalAnalyses,
        getAnalysesToday: () => State.analysesToday,
        
        clearHistory: () => {
            State.recentAnalyses = [];
            State.totalAnalyses = 0;
            State.analysesToday = 0;
            EventBus.emit('analysis:history_cleared', {});
        }
    };

    // ==============================================
    // 🔥 INICIALIZAÇÃO DA APLICAÇÃO
    // ==============================================

    async function initApp() {
        console.log('🚀 Inicializando App (Orquestrador) v6.2...');

        try {
            // 1. Resetar contador de reloads
            ReloadManager.reset();

            // 2. Aguardar auth.js carregar
            console.log('⏳ Aguardando auth.js carregar...');
            const authLoaded = await Utils.waitForAuth(30);
            
            if (!authLoaded) {
                console.warn('⚠️ Auth não carregou. Tentando continuar...');
                const token = localStorage.getItem('access_token');
                if (!token || token === 'undefined' || token === 'null') {
                    console.log('🔒 Sem token válido, redirecionando para login');
                    Utils.redirectTo(CONFIG.ROUTES.LOGIN);
                    return;
                }
            }

            // 3. Verificar autenticação
            const isAuth = Utils.isAuthenticated();

            const currentPath = Utils.getCurrentPath();
            const isProtectedRoute = CONFIG.ROUTES.PROTECTED.some(route => 
                currentPath === route || currentPath.startsWith(route + '/') || currentPath.startsWith(route + '?')
            );
            const isPublicRoute = CONFIG.ROUTES.PUBLIC.some(route => 
                currentPath === route || currentPath.startsWith(route + '/') || currentPath.startsWith(route + '?')
            );

            if (!isAuth && isProtectedRoute) {
                console.log('🔒 Rota protegida sem autenticação - redirecionando para login');
                Utils.redirectTo(CONFIG.ROUTES.LOGIN);
                return;
            }

            if (isAuth && isPublicRoute) {
                console.log('✅ Usuário já logado - redirecionando para dashboard');
                Utils.redirectTo(CONFIG.ROUTES.HOME);
                return;
            }

            console.log('✅ Rota verificada, continuando inicialização...');

            // 4. Configurar EventManager
            EventManager.setup();

            // 5. Sincronizar com auth.js
            if (window.appAuth) {
                const syncAuth = await Sync.syncAuth();
                if (syncAuth) {
                    console.log('✅ Auth sincronizado com sucesso');
                }
            } else {
                if (isAuth) {
                    StateManager.updateState({
                        tokenValid: true,
                        userInitialized: true
                    });
                    console.log('✅ Autenticação via token (fallback)');
                }
            }
            
            // 6. Sincronizar Rate Limit
            Sync.syncRateLimit();

            // 7. Se estiver autenticado, sincroniza com payment, promoção e PoW
            if (isAuth) {
                console.log('🔐 Usuário autenticado, sincronizando serviços...');
                
                if (typeof window.initPowClient === 'function') {
                    setTimeout(() => {
                        window.initPowClient({
                            autoRefill: false,
                            preSolve: false
                        });
                    }, 1000);
                } else if (window.powClient) {
                    console.log('⚡ PoW disponível, aguardando upload para ativar');
                }
                
                await Sync.syncPayment();
                await Sync.syncPromotion();
            }

            // 8. Configurar UI global
            UI.setupModals();
            UI.updateNavbar();
            UI.updateRateLimitStatus();

            // 9. Configurar navegação
            Router.setupNavigation();

            // 10. Marcar como inicializado
            StateManager.updateState({
                initialized: true,
                isAppReady: true,
                userInitialized: true
            });

            window._appReadyFired = true;
            window._appInitialized = true;

            // 11. DISPARAR EVENTO app:ready
            const appReadyData = {
                isAuthenticated: isAuth,
                user: State.user,
                credits: State.credits,
                creditsDisplay: State.creditsDisplay,
                isAdmin: State.isAdmin,
                isPremium: State.isPremium,
                maxCredits: CONFIG.MAX_CREDITS_BALANCE,
                hasVitalicio: State.hasPromotionalPrice,
                promotionalPrice: State.promotionalPrice,
                tokenValid: State.tokenValid,
                powReady: State.powReady,
                rateLimitBlocked: State.rateLimitBlocked,
                rateLimitTimeRemaining: Utils.getRateLimitTimeRemaining(),
                displayName: State.user?.name || 'Usuário',
                workshopName: State.user?.workshop_name || 'Oficina',
                userInitialized: State.userInitialized,
                isReady: true,
                version: '6.2'
            };

            EventBus.emit('app:ready', appReadyData);
            window.dispatchEvent(new CustomEvent('app:ready', { detail: appReadyData }));
            document.dispatchEvent(new CustomEvent('app:ready', { detail: appReadyData }));
            
            // 🔥 NOTIFICA PAYMENT.JS
            window.dispatchEvent(new CustomEvent('appReady', { 
                detail: { isReady: true, version: '6.2' }
            }));

            console.log('✅ App (Orquestrador) v6.2 inicializado com sucesso!');
            console.log(`📌 Autenticado: ${isAuth}`);
            console.log(`📌 Página: ${currentPath}`);
            console.log(`📌 Admin: ${State.isAdmin}`);
            console.log(`📌 Premium: ${State.isPremium}`);
            console.log(`📌 Créditos: ${State.creditsDisplay}`);
            console.log('🌉 window.appAuth centralizado e pronto');
            console.log('📦 AppUtils disponível globalmente');
            console.log('⚡ fetchWithAuth unificado com refresh automático');
            console.log('🔄 Estado reativo via StateManager');
            console.log('🔐 Sincronizado com back-end (crud.py, security.py, upload_routes.py)');
            console.log('🔗 Integrado com auth.js, payment.js, dashboard.js');

        } catch (error) {
            console.error('❌ Erro na inicialização do App:', error);
            Utils.showNotification('Erro ao inicializar aplicação. Recarregue a página.', 'error');
            
            EventBus.emit('app:error', { 
                error: error.message || 'Erro na inicialização'
            });
            
            StateManager.updateState({
                initialized: false,
                isAppReady: false,
                userInitialized: false
            });
            window._appReadyFired = false;
        }
    }

    // ==============================================
    // 🔥 EXPORTAÇÕES GLOBAIS
    // ==============================================

    const App = {
        CONFIG,
        State: State,
        StateManager: StateManager,
        Utils,
        Router,
        EventBus,
        UI,
        Auth,
        Credits,
        Pow,
        Analysis,
        Sync,
        EventManager,
        ReloadManager,
        
        init: initApp,
        
        isInitialized: function() {
            try {
                return !!(window._appInitialized && State && State.userInitialized === true && State.isAppReady === true);
            } catch (e) {
                return false;
            }
        },
        
        isReady: function() {
            try {
                return State && State.isAppReady === true;
            } catch (e) {
                return false;
            }
        },
        
        auth: Auth,
        pow: Pow,
        credits: Credits,
        analysis: Analysis,
        sync: Sync,
        ui: UI,
        router: Router,
        events: EventBus,
        
        showNotification: Utils.showNotification,
        isAuthenticated: Utils.isAuthenticated,
        getCurrentUser: () => State ? State.user : null,
        getCredits: () => State ? State.credits : 0,
        isAdmin: () => State ? State.isAdmin : false,
        isPremium: () => State ? State.isPremium : false,
        hasVitalicio: () => State ? State.hasPromotionalPrice : false,
        getPromotionalPrice: () => State ? State.promotionalPrice : null,
        canReceiveDailyCredit: () => State ? State.canReceiveDailyCredit : false,
        getDaysLeftPremium: () => State ? State.daysLeftPremium : 0,
        isTokenValid: () => State ? State.tokenValid : false,
        
        isRateLimitBlocked: Utils.isRateLimitBlocked,
        getRateLimitTimeRemaining: Utils.getRateLimitTimeRemaining,
        getRateLimitRemainingAttempts: Utils.getRateLimitRemainingAttempts,
        
        loadCredits: Credits.load,
        loadPremiumStatus: Credits.loadPremiumStatus,
        receiveDailyCredit: Credits.receiveDailyCredit,
        getMaxCredits: () => CONFIG.MAX_CREDITS_BALANCE,
        getCreditsBalance: () => State ? State.credits : 0,
        
        navigate: Router.navigate,
        goBack: Utils.goBack,
        getQueryParam: Utils.getQueryParam,
        
        showLoading: UI.showLoading,
        hideLoading: UI.hideLoading,
        updateLoadingProgress: UI.updateLoadingProgress,
        updateCreditsDisplay: UI.updateCredits,
        updateNavbar: UI.updateNavbar,
        updateRateLimitStatus: UI.updateRateLimitStatus,
        
        escapeHtml: Utils.escapeHtml,
        formatDate: Utils.formatDate,
        sanitizeNumber: Utils.sanitizeNumber,
        formatCreditsDisplay: Utils.formatCreditsDisplay,
        
        fetchWithAuth: fetchWithAuth,
        refreshTokenSafely: refreshTokenSafely,
        
        uploadWithPow: Pow.uploadWithPow,
        preparePowForUpload: Pow.prepareForUpload,
        getPowStats: Pow.getStats,
        isPowAvailable: Pow.isAvailable,
        
        startAnalysis: Analysis.startAnalysis,
        updateAnalysisProgress: Analysis.updateProgress,
        completeAnalysis: Analysis.completeAnalysis,
        failAnalysis: Analysis.failAnalysis,
        getActiveAnalyses: Analysis.getActiveAnalyses,
        getRecentAnalyses: Analysis.getRecentAnalyses,
        getTotalAnalyses: Analysis.getTotalAnalyses,
        getAnalysesToday: Analysis.getAnalysesToday,
        clearAnalysisHistory: Analysis.clearHistory
    };

    // 🔥 EXPORTAÇÕES GLOBAIS
    window.App = App;
    window.AppInstance = App;
    window.app = App;
    window.autoAnalytics = App;
    window.EventBus = EventBus;
    window.__APP_STATE = State;
    window.__APP_STATE_MANAGER = StateManager;
    window.__APP_CONFIG = CONFIG;
    window.AppUtils = AppUtils;
    
    // 🔥 FUNÇÕES AUXILIARES
    window.showNotification = Utils.showNotification;
    window.escapeHtml = Utils.escapeHtml;
    window.isAuthenticated = Utils.isAuthenticated;
    window.updateCreditsDisplay = UI.updateCredits;
    window.updateNavbar = UI.updateNavbar;
    window.updateRateLimitStatus = UI.updateRateLimitStatus;
    window.navigateTo = Router.navigate;
    window.showLoading = UI.showLoading;
    window.hideLoading = UI.hideLoading;
    window.updateLoadingProgress = UI.updateLoadingProgress;
    window.goBack = Utils.goBack;
    window.getQueryParam = Utils.getQueryParam;
    window.receiveDailyCredit = Credits.receiveDailyCredit;
    window.loadPremiumStatus = Credits.loadPremiumStatus;
    window.uploadWithPow = Pow.uploadWithPow;
    window.preparePowForUpload = Pow.prepareForUpload;
    window.isPowAvailable = Pow.isAvailable;
    window.getPowStats = Pow.getStats;
    window.startAnalysis = Analysis.startAnalysis;
    window.updateAnalysisProgress = Analysis.updateProgress;
    window.completeAnalysis = Analysis.completeAnalysis;
    window.failAnalysis = Analysis.failAnalysis;
    window.getActiveAnalyses = Analysis.getActiveAnalyses;
    window.getRecentAnalyses = Analysis.getRecentAnalyses;
    window.getTotalAnalyses = Analysis.getTotalAnalyses;
    window.getAnalysesToday = Analysis.getAnalysesToday;
    window.clearAnalysisHistory = Analysis.clearHistory;
    window.isRateLimitBlocked = Utils.isRateLimitBlocked;
    window.getRateLimitTimeRemaining = Utils.getRateLimitTimeRemaining;
    window.getRateLimitRemainingAttempts = Utils.getRateLimitRemainingAttempts;
    window.getRateLimitStatus = () => ({
        blocked: State.rateLimitBlocked,
        blockedUntil: State.rateLimitBlockedUntil,
        remainingAttempts: State.rateLimitRemainingAttempts,
        for: State.rateLimitBlockedFor,
        timeRemaining: Utils.getRateLimitTimeRemaining()
    });

    window.fetchWithAuth = fetchWithAuth;
    window.refreshTokenSafely = refreshTokenSafely;

    window.logout = () => {
        Auth.handleUnauthorized();
    };

    window.getCurrentUser = () => {
        return State ? State.user : null;
    };

    // ==============================================
    // 🔥 INICIAR
    // ==============================================

    if (window._appInitialized) {
        console.log('⚠️ App já inicializado, ignorando...');
    } else {
        window._appInitialized = true;
        
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initApp);
        } else {
            setTimeout(initApp, 150);
        }
    }

    console.log('✅ app.js (Orquestrador) v6.2 carregado!');
    console.log('   🔥 CORREÇÃO: Reconhecimento automático do token + cookie sync');
    console.log('   🔥 SINCRONIZAÇÃO: Com auth.js, payment.js, dashboard.js');
    console.log('   🔥 ESTADO REATIVO: StateManager com eventos');
    console.log('   🔥 FETCH UNIFICADO: Com refresh automático e rate limit');
    console.log('   🔥 SISTEMA DE CRÉDITOS: MAX_CREDITS_PREMIUM = 3');
    console.log('   🔥 SEM POLLING EXCESSIVO: Event-driven com fallback');
    console.log('   🔥 EVENTOS: app:ready, appReady, paymentReady, creditsUpdated');

})();