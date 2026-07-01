// frontend/js/app.js - ORQUESTRADOR CENTRAL - V6.0 (SINCRONIA TOTAL)
/**
 * AutoAnalytics - Módulo Principal da Aplicação
 * 
 * 🏗️ ARQUITETURA V6.0:
 * 1. 🔥 CENTRALIZAÇÃO: window.appAuth criado nativamente pelo app.js
 * 2. 🔥 ESTADO REATIVO: StateManager com atualização por eventos
 * 3. 🔥 UTILITÁRIOS GLOBAIS: AppUtils exposto para todos os módulos
 * 4. 🔥 FETCH UNIFICADO: fetchWithAuth centralizado com tratamento 401
 * 5. 🔥 EVENTO app:ready com payload completo do estado
 * 6. 🔥 ELIMINAÇÃO DE REDUNDÂNCIA: dashboard.js e payment.js usam AppUtils
 * 7. 🔥 SINCRONIA REATIVA: substitui polling por eventos
 * 8. 🔥 FALLBACK INTELIGENTE: coordenado pelo app.js
 */

(function() {
    'use strict';

    console.log('🚀 Inicializando App (Orquestrador) v6.0...');

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
        CREDITS_UPDATE_INTERVAL: 30000,
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
    // 🔥 ESTADO GLOBAL (REATIVO) - COMPARTILHADO
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
    // 🔥 GERENCIADOR DE ESTADO REATIVO (NOVO)
    // ==============================================

    const StateManager = {
        /**
         * Atualiza o estado e notifica todos os módulos via EventBus
         */
        updateState: function(newState) {
            const previousState = { ...State };
            Object.assign(State, newState);
            
            // Atualiza o display de créditos se necessário
            if (newState.credits !== undefined || newState.isPremium !== undefined || newState.isAdmin !== undefined) {
                State.creditsDisplay = Utils.formatCreditsDisplay(State.credits, State.isPremium);
            }
            
            console.log('📊 [StateManager] Estado atualizado:', {
                credits: State.credits,
                isPremium: State.isPremium,
                isAdmin: State.isAdmin,
                creditsDisplay: State.creditsDisplay
            });
            
            // Notifica todos os módulos sobre a mudança
            const eventData = {
                state: State,
                changes: newState,
                previous: previousState,
                timestamp: Date.now()
            };
            
            // Dispara via EventBus (app.js interno)
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
            
            // Atualiza UI imediatamente
            UI.updateNavbar();
            UI.updateCredits();
            UI.updatePremiumBadge();
            UI.updateVitalicioBadge();
            UI.updateAdminBadge();
            
            return State;
        },
        
        /**
         * Atualiza apenas os créditos
         */
        updateCredits: function(credits, isPremium = null) {
            const updates = { credits: credits };
            if (isPremium !== null) updates.isPremium = isPremium;
            return this.updateState(updates);
        },
        
        /**
         * Atualiza apenas o status premium
         */
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
        
        /**
         * Obtém o estado atual (read-only)
         */
        getState: function() {
            return { ...State };
        }
    };

    // 🔥 EXPORTA ESTADO E GERENCIADOR PARA OUTROS MÓDULOS
    window.__APP_STATE = State;
    window.__APP_STATE_MANAGER = StateManager;

    // ==============================================
    // 🔥 UTILITÁRIOS (AGORA GLOBAIS)
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
            const num = parseFloat(String(value).replace(/[^0-9.,-]/g, '').replace(',', '.'));
            return isNaN(num) ? defaultValue : num;
        },

        formatCreditsDisplay: (credits, isPremium = false) => {
            if (State.isAdmin) return '∞';
            const safeCredits = Utils.sanitizeNumber(credits, 0);
            if (isPremium) {
                return `${safeCredits}/${CONFIG.MAX_CREDITS_BALANCE}`;
            }
            return safeCredits.toString();
        },

        // 🔥 BLINDAGEM: try/catch no showNotification para evitar crash do Toastr
        showNotification: (message, type = 'info') => {
            // 1. Tenta usar appAuth primeiro
            if (window.appAuth?.showNotification) {
                try {
                    return window.appAuth.showNotification(message, type);
                } catch (e) {
                    console.warn('⚠️ appAuth.showNotification falhou:', e);
                }
            }
            
            // 2. Tenta usar Toastr (com try/catch para blindagem)
            if (window.toastr?.[type]) {
                try {
                    window.toastr[type](message);
                    return true;
                } catch (e) {
                    console.warn('⚠️ Toastr falhou ao renderizar. Usando fallback.', e);
                    if (type === 'error' || type === 'warning') {
                        alert(`⚠️ ${message}`);
                        return true;
                    }
                }
            }
            
            // 3. Fallback final
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

        isAuthenticated: () => {
            try {
                const token = localStorage.getItem('access_token');
                const hasValidToken = token && token !== '' && token !== 'undefined' && token !== 'null' && token.length > 10;
                
                if (window.appAuth) {
                    if (typeof window.appAuth.isAuthenticated === 'function') {
                        return window.appAuth.isAuthenticated();
                    }
                    return !!window.appAuth.isAuthenticated;
                }
                return hasValidToken;
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
    // 🔥 EXPORTA UTILITÁRIOS GLOBAIS (NOVO)
    // ==============================================

    /**
     * 🔥 AppUtils - Utilitários globais para todos os módulos
     * Elimina redundância entre payment.js e dashboard.js
     */
    window.AppUtils = {
        sanitizeNumber: Utils.sanitizeNumber,
        formatCreditsDisplay: Utils.formatCreditsDisplay,
        escapeHtml: Utils.escapeHtml,
        formatDate: Utils.formatDate,
        showNotification: Utils.showNotification,
        isAuthenticated: Utils.isAuthenticated,
        getMaxCredits: () => CONFIG.MAX_CREDITS_BALANCE,
        getConfig: () => CONFIG
    };

    // ==============================================
    // 🔥 FETCH UNIFICADO (NOVO)
    // ==============================================

    /**
     * 🔥 fetchWithAuth - Função centralizada para todas as requisições
     * Todos os módulos (payment.js, dashboard.js) devem usar esta função
     */
    async function fetchWithAuth(url, options = {}) {
        try {
            const token = localStorage.getItem('access_token');
            if (!token) {
                console.warn('⚠️ fetchWithAuth: sem token');
                // Dispara evento de não autenticado
                EventBus.emit('auth:unauthorized', { message: 'Token não encontrado' });
                return null;
            }
            
            const headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': `Bearer ${token}`,
                ...options.headers
            };
            
            // Se for FormData, remove Content-Type para o browser definir
            if (options.body instanceof FormData) {
                delete headers['Content-Type'];
            }
            
            const response = await fetch(url, { ...options, headers });
            
            // 🔥 Tratamento de 401 - Token expirado
            if (response.status === 401) {
                console.warn('⚠️ Token expirado, tentando refresh...');
                
                // Tenta renovar o token
                const refreshed = await refreshTokenSafely();
                if (refreshed) {
                    // Re-tenta a requisição com o novo token
                    const newToken = localStorage.getItem('access_token');
                    if (newToken) {
                        headers['Authorization'] = `Bearer ${newToken}`;
                        const retryResponse = await fetch(url, { ...options, headers });
                        if (retryResponse.ok) {
                            return retryResponse;
                        }
                    }
                }
                
                // Se falhou, redireciona para login
                console.error('❌ Falha ao renovar token, redirecionando para login');
                EventBus.emit('auth:unauthorized', { 
                    message: 'Sessão expirada',
                    redirect: true 
                });
                Auth.handleUnauthorized();
                return null;
            }
            
            // 🔥 Tratamento de 429 - Rate Limit
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

    /**
     * 🔥 refreshTokenSafely - Renova o token de forma segura
     */
    async function refreshTokenSafely() {
        try {
            const refreshToken = localStorage.getItem('refresh_token');
            if (!refreshToken) {
                console.warn('⚠️ Sem refresh token disponível');
                return false;
            }
            
            const response = await fetch('/api/auth/refresh', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ refresh_token: refreshToken })
            });
            
            if (response.ok) {
                const data = await response.json();
                if (data.access_token) {
                    localStorage.setItem('access_token', data.access_token);
                    if (data.refresh_token) {
                        localStorage.setItem('refresh_token', data.refresh_token);
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
    // 🔥 INTERFACE DE AUTENTICAÇÃO (window.appAuth) - CENTRALIZADO
    // ==============================================

    /**
     * 🔥 window.appAuth - Interface formal de autenticação
     * Todos os módulos (payment.js, dashboard.js) usam esta interface
     */
    window.appAuth = {
        isAuthenticated: () => Utils.isAuthenticated(),
        isAdmin: () => State.isAdmin,
        isPremium: () => State.isPremium,
        getCredits: () => State.credits,
        getCurrentUser: () => State.user,
        getState: () => StateManager.getState(),
        
        // 🔥 FETCH UNIFICADO
        fetchWithAuth: fetchWithAuth,
        refreshTokenSafely: refreshTokenSafely,
        
        // 🔥 NOTIFICAÇÕES
        showNotification: (msg, type) => Utils.showNotification(msg, type),
        
        // 🔥 ESTADO
        updateState: StateManager.updateState,
        updateCredits: StateManager.updateCredits,
        updatePremiumStatus: StateManager.updatePremiumStatus,
        
        // 🔥 CRÉDITOS
        loadUserCredits: async () => {
            try {
                const response = await fetchWithAuth('/api/auth/me');
                if (response?.ok) {
                    const data = await response.json();
                    if (data.credits !== undefined) {
                        StateManager.updateCredits(data.credits, data.is_premium || false);
                    }
                    if (data.user) {
                        State.user = data.user;
                    }
                    return data;
                }
            } catch (e) {
                console.warn('Erro ao carregar créditos:', e);
            }
            return null;
        },
        
        // 🔥 RATE LIMIT
        getRateLimitStatus: () => ({
            blocked: State.rateLimitBlocked,
            blockedUntil: State.rateLimitBlockedUntil,
            remainingAttempts: State.rateLimitRemainingAttempts,
            for: State.rateLimitBlockedFor,
            timeRemaining: Utils.getRateLimitTimeRemaining()
        }),
        
        // 🔥 LOGOUT
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
            const token = localStorage.getItem('access_token');
            const hasValidToken = token && token !== 'undefined' && token !== 'null' && token.length > 10;
            
            let isAuth = hasValidToken;
            if (window.appAuth && typeof window.appAuth.isAuthenticated === 'function') {
                try {
                    isAuth = window.appAuth.isAuthenticated();
                } catch (e) {
                    isAuth = hasValidToken;
                }
            }
            
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
        _onceHandlers: new Map(),
        
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
            } catch (e) {
                // Ignora erro em ambiente seguro
            }
            
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
            this._onceHandlers.clear();
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

                // Notifica via EventBus
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
                        } catch (e) {
                            // Ignora erro se Bootstrap não estiver carregado
                        }
                    });
                }
            });

            document.querySelectorAll('.modal').forEach(modal => {
                modal.addEventListener('click', (e) => {
                    if (e.target === modal) {
                        try {
                            const instance = bootstrap.Modal.getInstance(modal);
                            if (instance) instance.hide();
                        } catch (e) {
                            // Ignora erro se Bootstrap não estiver carregado
                        }
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
        _tokenCheckInterval: null,

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

        startTokenCheck: () => {
            if (Auth._tokenCheckInterval) {
                clearInterval(Auth._tokenCheckInterval);
            }

            Auth._checkTokenRenewal();
            
            Auth._tokenCheckInterval = setInterval(() => {
                Auth._checkTokenRenewal();
            }, CONFIG.TOKEN_CHECK_INTERVAL);
            
            console.log(`⏰ Verificação de token: ${CONFIG.TOKEN_CHECK_INTERVAL/1000}s`);
        },

        _checkTokenRenewal: async () => {
            const token = localStorage.getItem('access_token');
            if (!token) return;
            
            try {
                const response = await fetch('/api/auth/check-token', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                
                if (response.status === 429) {
                    const data = await response.json().catch(() => ({}));
                    
                    const eventData = {
                        retryAfter: data.retry_after || 60,
                        remaining: data.remaining_attempts || 0,
                        message: data.detail || data.message || 'Muitas requisições. Aguarde um momento.',
                        for: 'token-check'
                    };
                    
                    EventBus.emit('rate_limit:blocked', eventData);
                    window.dispatchEvent(new CustomEvent('rate_limit:blocked', { detail: eventData }));
                    
                    return;
                }
                
                if (response.status === 401) {
                    console.log('🔄 Token expirado, tentando refresh...');
                    
                    const eventData = { message: 'Token expirado, tentando renovar...' };
                    EventBus.emit('auth:token_expired', eventData);
                    window.dispatchEvent(new CustomEvent('auth:token_expired', { detail: eventData }));
                    
                    const refreshed = await refreshTokenSafely();
                    if (refreshed) {
                        console.log('✅ Token renovado com sucesso!');
                        
                        const refreshEvent = { message: 'Token renovado com sucesso' };
                        EventBus.emit('auth:token_refreshed', refreshEvent);
                        window.dispatchEvent(new CustomEvent('auth:token_refreshed', { detail: refreshEvent }));
                        
                        Auth.resetSessionTimer();
                        State.tokenValid = true;
                    } else {
                        console.log('❌ Falha ao renovar token, fazendo logout...');
                        Auth.handleUnauthorized();
                    }
                } else if (response.ok) {
                    const data = await response.json();
                    
                    if (data.status === 'refreshed' && data.access_token) {
                        console.log('🔄 Token renovado via check-token');
                        State.tokenValid = true;
                        
                        const refreshEvent = { message: 'Token renovado automaticamente' };
                        EventBus.emit('auth:token_refreshed', refreshEvent);
                        window.dispatchEvent(new CustomEvent('auth:token_refreshed', { detail: refreshEvent }));
                        
                        if (data.credits !== undefined) {
                            StateManager.updateCredits(data.credits);
                        }
                    }
                    
                    Auth.resetSessionTimer();
                }
            } catch (error) {
                console.warn('Erro ao verificar token:', error);
            }
        },

        handleUnauthorized: function() {
            console.error('❌ [Orquestrador] Sessão inválida ou expirada.');
            
            sessionStorage.setItem(CONFIG.AUTH_BLOCK_KEY, String(Date.now()));
            
            localStorage.clear();
            
            // Atualiza estado via StateManager
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
            if (Auth._tokenCheckInterval) {
                clearInterval(Auth._tokenCheckInterval);
                Auth._tokenCheckInterval = null;
            }
        }
    };

    // ==============================================
    // 🔥 GERENCIADOR DE CRÉDITOS (REATIVO - SEM POLLING EXCESSIVO)
    // ==============================================

    const Credits = {
        _updateInterval: null,
        _premiumInterval: null,

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
            
            // Fallback: via API
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

        startPolling: () => {
            if (Credits._updateInterval) {
                clearInterval(Credits._updateInterval);
            }
            
            Credits.load();
            
            Credits._updateInterval = setInterval(() => {
                Credits.load();
            }, CONFIG.CREDITS_UPDATE_INTERVAL);
            
            console.log(`⏰ Atualização de créditos: ${CONFIG.CREDITS_UPDATE_INTERVAL/1000}s`);
        },

        startPremiumPolling: () => {
            if (Credits._premiumInterval) {
                clearInterval(Credits._premiumInterval);
            }
            
            Credits.loadPremiumStatus();
            
            Credits._premiumInterval = setInterval(() => {
                Credits.loadPremiumStatus();
            }, CONFIG.CREDITS_UPDATE_INTERVAL);
            
            console.log(`⏰ Atualização de status premium: ${CONFIG.CREDITS_UPDATE_INTERVAL/1000}s`);
        },

        stop: () => {
            if (Credits._updateInterval) {
                clearInterval(Credits._updateInterval);
                Credits._updateInterval = null;
            }
            if (Credits._premiumInterval) {
                clearInterval(Credits._premiumInterval);
                Credits._premiumInterval = null;
            }
        }
    };

    // ==============================================
    // 🔥 GERENCIADOR DE PoW (MODO SOB DEMANDA)
    // ==============================================

    const Pow = {
        _autoRefillInterval: null,

        isAvailable: () => {
            return window.powClient !== undefined && window.powClient !== null;
        },

        startAutoRefill: () => {
            if (!Pow.isAvailable()) {
                console.log('⏳ PoW não disponível, aguardando...');
                return;
            }

            try {
                if (typeof window.powClient.startAutoRefill === 'function') {
                    if (Pow._autoRefillInterval) {
                        clearInterval(Pow._autoRefillInterval);
                    }
                    
                    const autoRefillEnabled = false;
                    
                    if (autoRefillEnabled) {
                        window.powClient.startAutoRefill(CONFIG.POW_AUTO_REFILL_INTERVAL);
                        State.powAutoRefillActive = true;
                        console.log(`⚡ PoW auto-refill iniciado (${CONFIG.POW_AUTO_REFILL_INTERVAL/1000}s)`);
                    } else {
                        console.log('⚡ PoW em modo sob demanda (auto-refill desativado)');
                    }
                    
                    setTimeout(() => {
                        if (typeof window.powClient.preSolve === 'function') {
                            window.powClient.preSolve();
                        }
                    }, 100);
                    
                    EventBus.emit('pow:ready', {
                        solutionsReady: State.powSolutionsReady,
                        autoRefill: autoRefillEnabled
                    });
                }
            } catch (e) {
                console.warn('Erro ao iniciar PoW:', e);
            }
        },

        stopAutoRefill: () => {
            if (!Pow.isAvailable()) return;
            
            try {
                if (typeof window.powClient.stopAutoRefill === 'function') {
                    window.powClient.stopAutoRefill();
                    State.powAutoRefillActive = false;
                    console.log('⏹️ PoW auto-refill parado');
                }
            } catch (e) {
                console.warn('Erro ao parar PoW auto-refill:', e);
            }
            
            if (Pow._autoRefillInterval) {
                clearInterval(Pow._autoRefillInterval);
                Pow._autoRefillInterval = null;
            }
        },

        reset: () => {
            if (!Pow.isAvailable()) return;
            
            try {
                if (typeof window.powClient.reset === 'function') {
                    window.powClient.reset();
                    State.powSolutionsReady = 0;
                    console.log('🔄 PoW resetado');
                }
            } catch (e) {
                console.warn('Erro ao resetar PoW:', e);
            }
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

        uploadWithPow: async (file, endpoint = '/api/upload-auto') => {
            if (!Pow.isAvailable()) {
                throw new Error('PoW não disponível');
            }

            try {
                if (typeof window.powClient.uploadWithPow === 'function') {
                    return await window.powClient.uploadWithPow(file, endpoint);
                }
            } catch (e) {
                console.error('Erro no upload com PoW:', e);
                throw e;
            }
            throw new Error('Método uploadWithPow não disponível');
        },

        stop: () => {
            Pow.stopAutoRefill();
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
    // 🔥 GERENCIADOR DE SINCRONIZAÇÃO
    // ==============================================

    const Sync = {
        syncAuth: async () => {
            if (!window.appAuth) {
                console.warn('⚠️ Auth não inicializado.');
                return false;
            }

            try {
                const isAuth = await window.appAuth.checkToken?.();
                
                if (isAuth) {
                    const userData = window.appAuth.getCurrentUser?.() || {};
                    StateManager.updateState({
                        user: userData,
                        credits: userData.credits || 0,
                        isAdmin: userData.is_admin || false,
                        isPremium: userData.plan === 'premium_mensal' || userData.plan === 'PREMIUM_MENSAL',
                        tokenValid: true,
                        userInitialized: true
                    });
                    
                    UI.updateNavbar();
                    Credits.startPolling();
                    Auth.startTokenCheck();
                    Auth.startSessionTimer();
                    
                    if (isAuth && typeof window.initPowClient === 'function') {
                        console.log('🔐 Usuário autenticado, inicializando PoW (modo sob demanda)...');
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
                    
                    Credits.startPremiumPolling();
                    console.log('✅ Payment sincronizado com sucesso!');
                } else {
                    console.warn('⚠️ Payment não carregou. Algumas funcionalidades podem estar indisponíveis.');
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

        syncPow: async () => {
            try {
                const powLoaded = await Utils.waitForPow(20);
                
                if (powLoaded) {
                    console.log('✅ PoW sincronizado com sucesso!');
                    
                    if (Utils.isAuthenticated()) {
                        console.log('⚡ PoW em modo sob demanda (aguardando upload)');
                    }
                    
                    return true;
                } else {
                    console.warn('⚠️ PoW não carregou. Algumas funcionalidades podem estar indisponíveis.');
                    return false;
                }
            } catch (e) {
                console.warn('Erro ao sincronizar PoW:', e);
                return false;
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
    // 🔥 GERENCIADOR DE EVENTOS
    // ==============================================

    const EventManager = {
        setup: () => {
            console.log('📡 Configurando gerenciador de eventos...');
            
            // 🔥 ESCUTA EVENTOS DO payment.js (sem dois pontos)
            document.addEventListener('creditsUpdated', function(e) {
                console.log('📢 [EventManager] creditsUpdated recebido do payment.js');
                const data = e.detail || {};
                StateManager.updateCredits(data.credits || 0, data.isPremium || false);
            });
            
            document.addEventListener('premiumStatusUpdated', function(e) {
                console.log('📢 [EventManager] premiumStatusUpdated recebido do payment.js');
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
                console.log('📢 [EventManager] paymentReady recebido');
                window._paymentReady = true;
                setTimeout(() => {
                    Credits.loadPremiumStatus();
                    Credits.load();
                }, 300);
            });
            
            // 🔥 ESCUTA EVENTOS DO dashboard.js
            document.addEventListener('analysis:success', function(e) {
                console.log('📢 [EventManager] analysis:success recebido do dashboard');
                const detail = e.detail || {};
                if (detail.result?.user_credits !== undefined) {
                    StateManager.updateCredits(detail.result.user_credits);
                }
            });
            
            // 🔥 ESCUTA MUDANÇAS DE ESTADO (para sincronizar com payment.js)
            EventBus.on('app:state_changed', function(data) {
                console.log('📢 [EventManager] app:state_changed', data.changes);
                
                // Notifica payment.js sobre mudanças de créditos
                if (data.changes.credits !== undefined || data.changes.isPremium !== undefined) {
                    window.dispatchEvent(new CustomEvent('creditsUpdated', {
                        detail: {
                            credits: State.credits,
                            display: State.creditsDisplay,
                            maxCredits: CONFIG.MAX_CREDITS_BALANCE,
                            isPremium: State.isPremium
                        }
                    }));
                }
                
                // Notifica payment.js sobre mudanças de status premium
                if (data.changes.isPremium !== undefined || data.changes.daysLeftPremium !== undefined) {
                    window.dispatchEvent(new CustomEvent('premiumStatusUpdated', {
                        detail: {
                            isPremium: State.isPremium,
                            daysLeft: State.daysLeftPremium,
                            hasPromotionalPrice: State.hasPromotionalPrice,
                            promotionalPrice: State.promotionalPrice,
                            canReceiveDailyCredit: State.canReceiveDailyCredit,
                            receivedDailyCreditToday: State.receivedDailyCreditToday,
                            creditsBalance: State.credits
                        }
                    }));
                }
            });
        },

        clear: () => {
            // Limpeza de event listeners se necessário
        }
    };

    // ==============================================
    // 🔥 INICIALIZAÇÃO DA APLICAÇÃO
    // ==============================================

    async function initApp() {
        console.log('🚀 Inicializando App (Orquestrador) v6.0...');

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
            const token = localStorage.getItem('access_token');
            const hasValidToken = token && token !== 'undefined' && token !== 'null' && token.length > 10;
            
            let isAuth = false;
            if (window.appAuth && typeof window.appAuth.isAuthenticated === 'function') {
                try {
                    isAuth = window.appAuth.isAuthenticated();
                } catch (e) {
                    isAuth = hasValidToken;
                }
            } else {
                isAuth = hasValidToken;
            }

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

            // 4. Configurar EventManager (antes de tudo)
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

            // 11. DISPARAR EVENTO app:ready COM PAYLOAD COMPLETO
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
                version: '6.0'
            };

            // Dispara em todos os canais
            EventBus.emit('app:ready', appReadyData);
            window.dispatchEvent(new CustomEvent('app:ready', { detail: appReadyData }));
            document.dispatchEvent(new CustomEvent('app:ready', { detail: appReadyData }));
            
            // 🔥 NOTIFICA PAYMENT.JS
            window.dispatchEvent(new CustomEvent('appReady', { 
                detail: { isReady: true, version: '6.0' }
            }));

            console.log('✅ App (Orquestrador) v6.0 inicializado com sucesso!');
            console.log('📢 Evento app:ready com payload completo');
            console.log(`📌 Autenticado: ${isAuth}`);
            console.log(`📌 Página: ${currentPath}`);
            console.log(`📌 Admin: ${State.isAdmin}`);
            console.log(`📌 Premium: ${State.isPremium}`);
            console.log(`📌 Créditos: ${State.creditsDisplay}`);
            console.log('🌉 window.appAuth centralizado e pronto');
            console.log('📦 AppUtils disponível globalmente');
            console.log('⚡ fetchWithAuth unificado com refresh automático');
            console.log('🔄 Estado reativo via StateManager');

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
    // 🔥 EXPORTAÇÕES GLOBAIS - V6.0
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
                const appInit = !!window._appInitialized;
                const userInit = State && State.userInitialized === true;
                const appReady = State && State.isAppReady === true;
                const flagReady = !!window._appReadyFired;
                
                return appInit && userInit && appReady;
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
        
        // 🔥 INTERFACE DE AUTENTICAÇÃO (já exposta via window.appAuth)
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
        
        isPowAvailable: Pow.isAvailable,
        getPowStats: Pow.getStats,
        preparePowForUpload: Pow.prepareForUpload,
        uploadWithPow: Pow.uploadWithPow,
        startPowAutoRefill: Pow.startAutoRefill,
        stopPowAutoRefill: Pow.stopAutoRefill,
        resetPow: Pow.reset,
        
        loadCredits: Credits.load,
        loadPremiumStatus: Credits.loadPremiumStatus,
        receiveDailyCredit: Credits.receiveDailyCredit,
        getMaxCredits: () => CONFIG.MAX_CREDITS_BALANCE,
        getCreditsBalance: () => State ? State.credits : 0,
        
        startAnalysis: Analysis.startAnalysis,
        updateAnalysisProgress: Analysis.updateProgress,
        completeAnalysis: Analysis.completeAnalysis,
        failAnalysis: Analysis.failAnalysis,
        getActiveAnalyses: Analysis.getActiveAnalyses,
        getRecentAnalyses: Analysis.getRecentAnalyses,
        getTotalAnalyses: Analysis.getTotalAnalyses,
        getAnalysesToday: Analysis.getAnalysesToday,
        clearAnalysisHistory: Analysis.clearHistory,
        
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
        
        // 🔥 FETCH UNIFICADO
        fetchWithAuth: fetchWithAuth,
        refreshTokenSafely: refreshTokenSafely
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
    window.startPowAutoRefill = Pow.startAutoRefill;
    window.stopPowAutoRefill = Pow.stopAutoRefill;
    window.resetPow = Pow.reset;
    window.isPowAvailable = Pow.isAvailable;
    window.getPowStats = Pow.getStats;
    window.preparePowForUpload = Pow.prepareForUpload;
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

    // 🔥 FETCH UNIFICADO
    window.fetchWithAuth = fetchWithAuth;
    window.refreshTokenSafely = refreshTokenSafely;

    // 🔥 LOGOUT
    window.logout = () => {
        Auth.handleUnauthorized();
    };

    window.getCurrentUser = () => {
        return State ? State.user : null;
    };

    // ==============================================
    // 🔥 INICIAR QUANDO O DOM ESTIVER PRONTO
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

    console.log('✅ app.js (Orquestrador) v6.0 carregado!');
    console.log('   🔥 CENTRALIZAÇÃO: window.appAuth criado nativamente');
    console.log('   🔥 ESTADO REATIVO: StateManager com atualização por eventos');
    console.log('   🔥 UTILITÁRIOS GLOBAIS: AppUtils exposto para todos');
    console.log('   🔥 FETCH UNIFICADO: fetchWithAuth com refresh automático');
    console.log('   🔥 EVENTO app:ready com payload completo');
    console.log('   🔥 ELIMINAÇÃO DE REDUNDÂNCIA: payment.js e dashboard.js usam AppUtils');
    console.log('   🔥 SINCRONIA REATIVA: substitui polling por eventos');
    console.log('   🔥 FALLBACK INTELIGENTE: coordenado pelo app.js');

})()