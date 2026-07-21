// frontend/js/app.js - ORQUESTRADOR CENTRAL - v7.3 (CORRIGIDO COMPLETAMENTE)
/**
 * AutoAnalytics - Módulo Principal da Aplicação
 * 
 * 🏗️ ARQUITETURA V7.3:
 * 1. 🔥 CORRIGIDO: Bug this.isAvailable is not a function
 * 2. 🔥 ADICIONADO: Método isAvailable no objeto App
 * 3. 🔥 CORRIGIDO: uploadWithPow usa Pow.isAvailable()
 * 4. 🔥 MELHORADO: Verificação robusta do PoW
 * 5. 🔥 OTIMIZADO: Redução de chamadas redundantes
 * 
 * 🔥 CORREÇÕES V7.3:
 * - Adicionado App.isAvailable()
 * - Corrigido uploadWithPow para usar Pow.isAvailable()
 * - Adicionado fallback para quando o PoW não está disponível
 * - Melhorado tratamento de erros no upload
 */

(function() {
    'use strict';

    console.log('🚀 Inicializando App (Orquestrador) v7.3...');

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
        
        RATE_LIMIT_LOGIN_MAX: 5,
        RATE_LIMIT_LOGIN_WINDOW: 900,
        RATE_LIMIT_REGISTER_MAX: 5,
        RATE_LIMIT_REGISTER_WINDOW: 3600,
        
        POW_STOCK_SIZE: 2,
        API_BASE: '/api',
        
        ROUTES: {
            PROTECTED: ['/', '/dashboard', '/planos', '/checkout'],
            PUBLIC: ['/login', '/register'],
            HOME: '/dashboard',
            LOGIN: '/login'
        },
        
        RELOAD_COOLDOWN: 3000,
        MAX_RELOADS: 3,
        RELOAD_STORAGE_KEY: '_aa_reload_count',
        AUTH_BLOCK_KEY: '_aa_auth_block',
        
        UI_CACHE_TTL: 5000,
        DEBOUNCE_DELAY: 50
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
    // 🔥 EVENT BUS UNIFICADO (COM FILA)
    // ==============================================

    const EventBus = {
        _handlers: new Map(),
        _queue: [],
        _processing: false,
        _maxQueueSize: 1000,
        _eventHistory: [],
        _maxHistory: 100,

        on: function(event, handler, options = {}) {
            if (!this._handlers.has(event)) {
                this._handlers.set(event, []);
            }
            this._handlers.get(event).push({
                handler,
                once: options.once || false,
                priority: options.priority || 0,
                id: options.id || null
            });
            
            this._handlers.get(event).sort((a, b) => b.priority - a.priority);
            
            return () => this.off(event, handler);
        },

        once: function(event, handler) {
            return this.on(event, handler, { once: true });
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

        offById: function(event, id) {
            if (!this._handlers.has(event)) return;
            
            const handlers = this._handlers.get(event);
            const filtered = handlers.filter(h => h.id !== id);
            
            if (filtered.length === 0) {
                this._handlers.delete(event);
            } else {
                this._handlers.set(event, filtered);
            }
        },

        emit: function(event, data = {}) {
            this._eventHistory.push({ event, data, timestamp: Date.now() });
            if (this._eventHistory.length > this._maxHistory) {
                this._eventHistory.shift();
            }
            
            this._queue.push({ event, data, timestamp: Date.now() });
            
            if (this._queue.length > this._maxQueueSize) {
                this._queue.shift();
            }
            
            if (!this._processing) {
                this._processQueue();
            }
            
            try {
                window.dispatchEvent(new CustomEvent(event, { detail: data, bubbles: true }));
                document.dispatchEvent(new CustomEvent(event, { detail: data, bubbles: true }));
            } catch (e) {
                // Ignora
            }
        },

        _processQueue: function() {
            if (this._processing) return;
            if (this._queue.length === 0) return;
            
            this._processing = true;
            
            const batch = this._queue.splice(0, 10);
            
            for (const item of batch) {
                this._dispatch(item.event, item.data);
            }
            
            this._processing = false;
            
            if (this._queue.length > 0) {
                setTimeout(() => this._processQueue(), 0);
            }
        },

        _dispatch: function(event, data) {
            if (CONFIG.DEBUG || true) {
                console.log(`📢 [EventBus] ${event}`, data);
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
            this._queue = [];
            this._eventHistory = [];
        },

        getQueueSize: function() {
            return this._queue.length;
        },
        
        getHistory: function() {
            return this._eventHistory;
        }
    };

    // ==============================================
    // 🔥 ESTADO GLOBAL (COM PROXY)
    // ==============================================

    const initialState = {
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
        
        userSegment: null,
        currentMessage: null,
        lastMessageId: null,
        uiContext: null,
        
        _listeners: [],
        _intervals: [],
        _updateQueue: [],
        _isUpdating: false
    };

    const State = new Proxy(initialState, {
        set(target, key, value) {
            const oldValue = target[key];
            const changed = oldValue !== value;
            
            target[key] = value;
            
            if (changed) {
                if (key === 'credits' || key === 'isPremium' || key === 'isAdmin') {
                    const isAdmin = target.isAdmin;
                    const isPremium = target.isPremium;
                    const credits = target.credits || 0;
                    target.creditsDisplay = isAdmin ? '∞' : (isPremium ? `${credits}/${CONFIG.MAX_CREDITS_BALANCE}` : String(credits));
                }
                
                const eventData = {
                    state: target,
                    key,
                    oldValue,
                    newValue: value,
                    timestamp: Date.now()
                };
                
                EventBus.emit('app:state_changed', eventData);
                window.dispatchEvent(new CustomEvent('app:state_changed', { detail: eventData }));
            }
            
            return true;
        },
        
        get(target, key) {
            return target[key];
        }
    });

    window.__APP_STATE = State;

    // ==============================================
    // 🔥 GERENCIADOR DE ESTADO
    // ==============================================

    const StateManager = {
        updateState: function(newState) {
            for (const [key, value] of Object.entries(newState)) {
                if (value !== undefined) {
                    State[key] = value;
                }
            }
            return State;
        },
        
        updateCredits: function(credits, isPremium = null) {
            if (credits !== undefined) State.credits = credits;
            if (isPremium !== null) State.isPremium = isPremium;
            return State;
        },
        
        updatePremiumStatus: function(status) {
            State.isPremium = status.is_premium || false;
            State.daysLeftPremium = status.days_left || 0;
            State.hasPromotionalPrice = status.promotional_price_locked || false;
            State.promotionalPrice = status.promotional_price || null;
            State.canReceiveDailyCredit = status.can_receive_today || false;
            State.receivedDailyCreditToday = status.received_today || false;
            State.credits = status.credits_balance || State.credits;
            return State;
        },
        
        getState: function() {
            return { ...State };
        },
        
        reset: function() {
            const newState = { ...initialState };
            for (const [key, value] of Object.entries(newState)) {
                State[key] = value;
            }
            return State;
        }
    };

    window.__APP_STATE_MANAGER = StateManager;

    // ==============================================
    // 🔥 UTILITÁRIOS
    // ==============================================

    const Utils = {
        formatDate: (date) => {
            const d = new Date(date);
            return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR');
        },

        escapeHtml: (text) => {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        },

        sanitizeNumber: (value, defaultValue = 0) => {
            if (value === undefined || value === null) return defaultValue;
            const num = parseFloat(String(value).replace(/[^0-9.,-]/g, '').replace(',', '.'));
            return isNaN(num) ? defaultValue : num;
        },

        formatCreditsDisplay: (credits, isPremium = false) => {
            if (State.isAdmin) return '∞';
            const safeCredits = Utils.sanitizeNumber(credits, 0);
            if (isPremium || State.isPremium) {
                return `${safeCredits}/${CONFIG.MAX_CREDITS_BALANCE}`;
            }
            return safeCredits.toString();
        },

        showNotification: (message, type = 'info') => {
            if (window.toastr && window.toastr[type]) {
                try {
                    window.toastr[type](message);
                    return true;
                } catch (e) {
                    console.warn('⚠️ Toastr falhou:', e);
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

        isAuthenticated: () => {
            try {
                const token = localStorage.getItem('access_token');
                return token && token !== '' && token !== 'undefined' && token !== 'null' && token.length > 10;
            } catch (e) {
                return false;
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
                    try {
                        if (condition()) {
                            resolve(true);
                            return;
                        }
                    } catch (e) {
                        // Ignora
                    }
                    
                    if (Date.now() - startTime > timeout) {
                        resolve(false);
                        return;
                    }
                    setTimeout(check, interval);
                };
                check();
            });
        },

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
        },
        
        debounce: function(func, delay = CONFIG.DEBOUNCE_DELAY) {
            let timeoutId;
            return function(...args) {
                clearTimeout(timeoutId);
                timeoutId = setTimeout(() => func.apply(this, args), delay);
            };
        },
        
        throttle: function(func, limit = 100) {
            let inThrottle;
            return function(...args) {
                if (!inThrottle) {
                    func.apply(this, args);
                    inThrottle = true;
                    setTimeout(() => inThrottle = false, limit);
                }
            };
        }
    };

    window.AppUtils = {
        sanitizeNumber: Utils.sanitizeNumber,
        formatCreditsDisplay: Utils.formatCreditsDisplay,
        escapeHtml: Utils.escapeHtml,
        formatDate: Utils.formatDate,
        showNotification: Utils.showNotification,
        isAuthenticated: Utils.isAuthenticated,
        validateCPF: Utils.validateCPF,
        getMaxCredits: () => CONFIG.MAX_CREDITS_BALANCE,
        getConfig: () => CONFIG,
        debounce: Utils.debounce,
        throttle: Utils.throttle
    };

    // ==============================================
    // 🔥 FETCH UNIFICADO (COM REFRESH AUTOMÁTICO)
    // ==============================================

    let _isRefreshing = false;
    let _refreshPromise = null;

    async function refreshTokenSafely() {
        if (_isRefreshing) {
            return _refreshPromise || false;
        }
        
        _isRefreshing = true;
        _refreshPromise = (async () => {
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
                        document.cookie = `access_token=${data.access_token}; path=/; max-age=900; SameSite=Strict; Secure`;
                        
                        if (data.refresh_token) {
                            localStorage.setItem('refresh_token', data.refresh_token);
                        }
                        if (data.user) {
                            localStorage.setItem('user_data', JSON.stringify(data.user));
                            localStorage.setItem('user_email', data.user.email || '');
                        }
                        
                        console.log('✅ Token renovado com sucesso!');
                        EventBus.emit('auth:token_refreshed', { message: 'Token renovado automaticamente' });
                        return true;
                    }
                }
                
                console.warn('⚠️ Falha ao renovar token');
                return false;
            } catch (error) {
                console.error('❌ Erro ao renovar token:', error);
                return false;
            } finally {
                _isRefreshing = false;
                _refreshPromise = null;
            }
        })();
        
        return _refreshPromise;
    }

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
            
            let response = await fetch(url, { ...options, headers });
            
            if (response.status === 401) {
                console.warn('⚠️ Token expirado, tentando refresh...');
                
                const refreshed = await refreshTokenSafely();
                if (refreshed) {
                    const newToken = localStorage.getItem('access_token');
                    if (newToken) {
                        headers['Authorization'] = `Bearer ${newToken}`;
                        response = await fetch(url, { ...options, headers });
                        if (response.ok) {
                            return response;
                        }
                    }
                }
                
                console.error('❌ Falha ao renovar token, redirecionando para login');
                EventBus.emit('auth:unauthorized', { message: 'Sessão expirada', redirect: true });
                handleUnauthorized();
                return null;
            }
            
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
            EventBus.emit('fetch:error', { url, error: error.message, options });
            return null;
        }
    }

    // ==============================================
    // 🔥 HANDLE UNAUTHORIZED
    // ==============================================

    function handleUnauthorized() {
        console.error('❌ [Orquestrador] Sessão inválida ou expirada.');
        
        sessionStorage.setItem(CONFIG.AUTH_BLOCK_KEY, String(Date.now()));
        
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
        
        EventBus.emit('auth:unauthorized', { message: 'Sessão inválida ou expirada', redirect: true });
        
        setTimeout(() => {
            window.location.replace('/login');
        }, 300);
    }

    // ==============================================
    // 🔥 ROTEADOR
    // ==============================================

    const Router = {
        isProtected: function() {
            const path = Utils.getCurrentPath();
            return CONFIG.ROUTES.PROTECTED.some(route => 
                path === route || path.startsWith(route + '/') || path.startsWith(route + '?')
            );
        },

        isPublic: function() {
            const path = Utils.getCurrentPath();
            return CONFIG.ROUTES.PUBLIC.some(route => 
                path === route || path.startsWith(route + '/') || path.startsWith(route + '?')
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

        navigate: function(url) {
            const isProtected = CONFIG.ROUTES.PROTECTED.some(route => 
                url === route || url.startsWith(route + '/') || url.startsWith(route + '?')
            );
            
            if (isProtected && !Utils.isAuthenticated()) {
                Utils.showNotification('Faça login para acessar esta página.', 'warning');
                Utils.redirectTo(CONFIG.ROUTES.LOGIN);
                return;
            }

            Utils.redirectTo(url);
        },

        setupNavigation: function() {
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
        }
    };

    // ==============================================
    // 🔥 UI MANAGER
    // ==============================================

    const UI = {
        _elements: new Map(),
        _elementCache: new Map(),
        _cacheTimestamps: new Map(),
        _updateTimeout: null,
        _isUpdating: false,
        _lastUpdate: 0,

        _getElement: function(selector, forceRefresh = false) {
            const now = Date.now();
            const cached = this._elementCache.get(selector);
            const timestamp = this._cacheTimestamps.get(selector) || 0;
            
            if (!forceRefresh && cached && (now - timestamp) < CONFIG.UI_CACHE_TTL) {
                return cached;
            }
            
            const el = document.querySelector(selector);
            this._elementCache.set(selector, el);
            this._cacheTimestamps.set(selector, now);
            return el;
        },

        invalidateCache: function() {
            this._elementCache.clear();
            this._cacheTimestamps.clear();
        },

        scheduleUpdate: function() {
            if (this._updateTimeout) {
                clearTimeout(this._updateTimeout);
            }
            this._updateTimeout = setTimeout(() => {
                this.updateNavbar();
                this._updateTimeout = null;
            }, CONFIG.DEBOUNCE_DELAY);
        },

        updateNavbar: function() {
            const now = Date.now();
            if (this._isUpdating) return;
            if (now - this._lastUpdate < 50) return;
            
            this._isUpdating = true;
            
            try {
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
                
                this._lastUpdate = now;
            } finally {
                this._isUpdating = false;
            }
        },

        updateCredits: function() {
            try {
                const credits = State.credits || 0;
                const isPremium = State.isPremium || false;
                const isAdmin = State.isAdmin || false;
                
                const formattedDisplay = isAdmin ? '∞' : (isPremium ? `${credits}/${CONFIG.MAX_CREDITS_BALANCE}` : String(credits));
                State.creditsDisplay = formattedDisplay;
                
                const selectors = [
                    '.credits-display', '.user-credits', 
                    '#creditsDisplay', '#creditsCount', '#uploadCredits',
                    '.credits-badge span', '.credits-value'
                ];
                
                document.querySelectorAll(selectors.join(',')).forEach(el => {
                    if (el) el.textContent = formattedDisplay;
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

        updateAdminBadge: function() {
            const isAdmin = State.isAdmin || false;
            document.querySelectorAll('.admin-badge, .admin-only').forEach(el => {
                el.style.display = isAdmin ? 'inline-block' : 'none';
            });
            document.body.classList.toggle('is-admin', isAdmin);
        },

        updatePremiumBadge: function() {
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

        updateVitalicioBadge: function() {
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

        updatePowStatus: function() {
            try {
                if (window.powClient && typeof window.powClient.getStats === 'function') {
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

        updateRateLimitStatus: function() {
            const isBlocked = Utils.isRateLimitBlocked();
            const timeRemaining = Utils.getRateLimitTimeRemaining();
            
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
            if (loginBtn && isBlocked) {
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
            }
        },

        showLoading: function(message = 'Processando...', submessage = '') {
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

        hideLoading: function() {
            const overlay = document.getElementById('loadingOverlay');
            if (overlay) {
                overlay.classList.remove('show');
            }
        },

        updateLoadingProgress: function(percent, message = null) {
            const progress = document.getElementById('loadingProgressBar');
            const text = document.getElementById('loadingText');
            
            if (progress) progress.style.width = `${Math.min(100, percent)}%`;
            if (message && text) text.textContent = message;
        },

        setupModals: function() {
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

        clearElementCache: function() {
            this._elements.clear();
            this._elementCache.clear();
            this._cacheTimestamps.clear();
        }
    };

    // ==============================================
    // 🔥 AUTH
    // ==============================================

    const Auth = {
        _sessionTimeout: null,

        startSessionTimer: function() {
            if (this._sessionTimeout) {
                clearTimeout(this._sessionTimeout);
                this._sessionTimeout = null;
            }

            if (!Utils.isAuthenticated()) return;

            console.log(`⏰ Timer de sessão: ${CONFIG.SESSION_TIMEOUT/60000} minutos`);

            this._sessionTimeout = setTimeout(() => {
                console.log('⏰ Sessão expirada por inatividade');
                Utils.showNotification('⏰ Sessão expirada por inatividade. Faça login novamente.', 'warning');
                handleUnauthorized();
            }, CONFIG.SESSION_TIMEOUT);
        },

        resetSessionTimer: function() {
            if (!Utils.isAuthenticated()) return;
            this.startSessionTimer();
        },

        stop: function() {
            if (this._sessionTimeout) {
                clearTimeout(this._sessionTimeout);
                this._sessionTimeout = null;
            }
        }
    };

    // ==============================================
    // 🔥 INTERFACE DE AUTENTICAÇÃO
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
        
        showNotification: Utils.showNotification,
        
        updateState: StateManager.updateState,
        updateCredits: StateManager.updateCredits,
        updatePremiumStatus: StateManager.updatePremiumStatus,
        
        loadUserCredits: async function() {
            try {
                const response = await fetchWithAuth('/api/auth/me');
                if (response?.ok) {
                    const data = await response.json();
                    
                    StateManager.updateState({
                        user: data.user || null,
                        credits: data.credits || 0,
                        isPremium: data.is_premium || false,
                        isAdmin: data.is_admin || false,
                        tokenValid: true,
                        userInitialized: true,
                        isAppReady: true
                    });
                    
                    if (data.user) {
                        try {
                            localStorage.setItem('user_data', JSON.stringify(data.user));
                            localStorage.setItem('user_email', data.user.email || '');
                        } catch (e) {}
                    }
                    
                    console.log(`✅ Créditos carregados: ${data.credits || 0}`);
                    
                    if (window.App && typeof window.App.updateNavbar === 'function') {
                        window.App.updateNavbar();
                    }
                    
                    return data;
                }
            } catch (e) {
                console.warn('Erro ao carregar créditos:', e);
            }
            return null;
        },
        
        getRateLimitStatus: () => ({
            blocked: State.rateLimitBlocked,
            blockedUntil: State.rateLimitBlockedUntil,
            remainingAttempts: State.rateLimitRemainingAttempts,
            for: State.rateLimitBlockedFor,
            timeRemaining: Utils.getRateLimitTimeRemaining()
        }),
        
        refreshMessageContext: async function() {
            try {
                const token = localStorage.getItem('access_token');
                if (!token) return null;
                
                const response = await fetch('/api/auth/session-status', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                
                if (response.ok) {
                    const data = await response.json();
                    
                    StateManager.updateState({
                        userSegment: data.segment || 'regular',
                        currentMessage: data.message_config || null,
                        lastMessageId: data.message_config?.message_id || null,
                        uiContext: data.ui_context || null
                    });
                    
                    window.dispatchEvent(new CustomEvent('message:context_updated', {
                        detail: {
                            segment: data.segment,
                            message: data.message_config,
                            ui_context: data.ui_context
                        }
                    }));
                    
                    return data;
                }
            } catch (e) {
                console.warn('Erro ao atualizar mensagem:', e);
            }
            return null;
        },
        
        logout: handleUnauthorized
    };

    // ==============================================
    // 🔥 GERENCIADOR DE EVENTOS
    // ==============================================

    const EventManager = {
        setup: function() {
            console.log('📡 Configurando gerenciador de eventos...');
            
            document.addEventListener('creditsUpdated', function(e) {
                const data = e.detail || {};
                StateManager.updateCredits(data.credits || 0, data.isPremium || false);
                if (window.App && typeof window.App.updateCredits === 'function') {
                    window.App.updateCredits();
                }
                setTimeout(() => {
                    if (window.appAuth?.refreshMessageContext) {
                        window.appAuth.refreshMessageContext();
                    }
                }, 300);
            });
            
            document.addEventListener('premiumStatusUpdated', function(e) {
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
                if (window.App && typeof window.App.updateNavbar === 'function') {
                    window.App.updateNavbar();
                }
                setTimeout(() => {
                    if (window.appAuth?.refreshMessageContext) {
                        window.appAuth.refreshMessageContext();
                    }
                }, 400);
            });
            
            document.addEventListener('paymentReady', function(e) {
                window._paymentReady = true;
                setTimeout(() => {
                    if (window.loadPremiumStatus) {
                        window.loadPremiumStatus();
                    }
                    if (window.appAuth?.loadUserCredits) {
                        window.appAuth.loadUserCredits();
                    }
                    if (window.App && typeof window.App.updateNavbar === 'function') {
                        window.App.updateNavbar();
                    }
                    setTimeout(() => {
                        if (window.appAuth?.refreshMessageContext) {
                            window.appAuth.refreshMessageContext();
                        }
                    }, 500);
                }, 300);
            });
            
            document.addEventListener('analysis:success', function(e) {
                const detail = e.detail || {};
                if (detail.result?.user_credits !== undefined) {
                    StateManager.updateCredits(detail.result.user_credits);
                }
                if (detail.result?.credits_balance !== undefined) {
                    StateManager.updateCredits(detail.result.credits_balance);
                }
                if (window.App && typeof window.App.updateCredits === 'function') {
                    window.App.updateCredits();
                }
                setTimeout(() => {
                    if (window.appAuth?.refreshMessageContext) {
                        window.appAuth.refreshMessageContext();
                    }
                }, 300);
            });
            
            document.addEventListener('upload:completed', function(e) {
                const detail = e.detail || {};
                if (detail.credits_remaining !== undefined) {
                    StateManager.updateCredits(detail.credits_remaining);
                }
                if (window.App && typeof window.App.updateCredits === 'function') {
                    window.App.updateCredits();
                }
                setTimeout(() => {
                    if (window.appAuth?.refreshMessageContext) {
                        window.appAuth.refreshMessageContext();
                    }
                }, 300);
            });

            document.addEventListener('credits:insufficient', function(e) {
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
            
            document.addEventListener('rate_limit:blocked', function(e) {
                const detail = e.detail || {};
                State.rateLimitBlocked = true;
                State.rateLimitBlockedUntil = Date.now() + (detail.retryAfter || 60) * 1000;
                State.rateLimitRemainingAttempts = detail.remaining || 0;
                if (window.App && typeof window.App.updateRateLimitStatus === 'function') {
                    window.App.updateRateLimitStatus();
                }
                Utils.showNotification(detail.message || 'Muitas tentativas. Aguarde um momento.', 'warning');
            });
            
            document.addEventListener('authReady', function(e) {
                const detail = e.detail || {};
                if (detail.isAuthenticated) {
                    StateManager.updateState({
                        tokenValid: true,
                        userInitialized: true,
                        isAppReady: true
                    });
                    setTimeout(() => {
                        if (window.appAuth?.loadUserCredits) {
                            window.appAuth.loadUserCredits();
                        }
                        if (window.App && typeof window.App.updateNavbar === 'function') {
                            window.App.updateNavbar();
                        }
                        if (window.appAuth?.refreshMessageContext) {
                            setTimeout(() => {
                                window.appAuth.refreshMessageContext();
                            }, 500);
                        }
                    }, 500);
                }
            });

            document.addEventListener('authLogout', handleUnauthorized);
            
            console.log('✅ Event listeners configurados');
        }
    };

    // ==============================================
    // 🔥🔥🔥 GERENCIADOR DE PoW - CORRIGIDO
    // ==============================================

    const Pow = {
        isAvailable: function() {
            return window.powClient !== undefined && window.powClient !== null;
        },

        getStats: function() {
            if (!this.isAvailable()) {
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

        prepareForUpload: async function() {
            if (!this.isAvailable()) {
                console.log('⏳ PoW não disponível para preparar upload');
                return false;
            }
            try {
                if (typeof window.powClient.prepareForUpload === 'function') {
                    const result = await window.powClient.prepareForUpload();
                    if (typeof window.powClient.getStats === 'function') {
                        const stats = window.powClient.getStats();
                        State.powSolutionsReady = stats.solutionsReady || 0;
                        if (window.App && typeof window.App.updatePowStatus === 'function') {
                            window.App.updatePowStatus();
                        }
                    }
                    return result;
                }
            } catch (e) {
                console.warn('Erro ao preparar PoW para upload:', e);
            }
            return false;
        },

        // 🔥 CORRIGIDO: uploadWithPow agora usa Pow.isAvailable()
        uploadWithPow: async function(files, endpoint = '/api/upload-auto') {
            // ✅ CORRIGIDO: Usando Pow.isAvailable()
            if (!Pow.isAvailable()) {
                console.log('⏳ PoW não disponível, usando upload normal');
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
                    if (Array.isArray(files) && files.length > 1) {
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
        startAnalysis: function(data) {
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

        updateProgress: function(analysisId, progress, status = 'processing') {
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
                    if (window.App && typeof window.App.updateCredits === 'function') {
                        window.App.updateCredits();
                    }
                }
                
                EventBus.emit('analysis:success', {
                    analysis,
                    result,
                    total: State.totalAnalyses,
                    today: State.analysesToday,
                    creditsUpdated: result?.credits || 0
                });
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
        
        clearHistory: function() {
            State.recentAnalyses = [];
            State.totalAnalyses = 0;
            State.analysesToday = 0;
            EventBus.emit('analysis:history_cleared', {});
        }
    };

    // ==============================================
    // 🔥 SINCRONIZAÇÃO
    // ==============================================

    const Sync = {
        syncAuth: async function() {
            if (!window.appAuth) {
                console.warn('⚠️ Auth não inicializado.');
                return false;
            }

            try {
                const isAuth = Utils.isAuthenticated();
                
                if (isAuth) {
                    await window.appAuth.loadUserCredits();
                    
                    StateManager.updateState({
                        tokenValid: true,
                        userInitialized: true
                    });
                    
                    if (window.App && typeof window.App.updateNavbar === 'function') {
                        window.App.updateNavbar();
                    }
                    Auth.startSessionTimer();
                    
                    setTimeout(() => {
                        if (window.appAuth?.refreshMessageContext) {
                            window.appAuth.refreshMessageContext();
                        }
                    }, 500);
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

        syncPayment: async function() {
            if (!window.appAuth) return;
            
            try {
                await Utils.waitFor(() => {
                    return typeof window.loadPremiumStatus === 'function';
                }, 5000, 200);
                
                if (typeof window.loadPremiumStatus === 'function') {
                    await window.loadPremiumStatus();
                    console.log('✅ Payment sincronizado com sucesso!');
                }
            } catch (e) {
                console.warn('⚠️ Payment não carregou. Será sincronizado quando disponível.');
            }
        },

        syncPromotion: async function() {
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
                    
                    if (window.App && typeof window.App.updateVitalicioBadge === 'function') {
                        window.App.updateVitalicioBadge();
                    }
                }
            } catch (e) {
                console.warn('Erro ao sincronizar promoção:', e);
            }
        },

        syncRateLimit: function() {
            if (window.appAuth?.getRateLimitStatus) {
                const status = window.appAuth.getRateLimitStatus();
                if (status) {
                    StateManager.updateState({
                        rateLimitBlocked: status.blocked || false,
                        rateLimitBlockedUntil: status.blockedUntil || 0,
                        rateLimitRemainingAttempts: status.remainingAttempts || CONFIG.RATE_LIMIT_LOGIN_MAX,
                        rateLimitBlockedFor: status.for || 'login'
                    });
                    if (window.App && typeof window.App.updateRateLimitStatus === 'function') {
                        window.App.updateRateLimitStatus();
                    }
                }
            }
        }
    };

    // ==============================================
    // 🔥 INICIALIZAÇÃO DA APLICAÇÃO
    // ==============================================

    async function initApp() {
        console.log('🚀 Inicializando App (Orquestrador) v7.3...');

        try {
            ReloadManager.reset();

            console.log('⏳ Aguardando auth.js carregar...');
            await Utils.waitFor(() => window.appAuth !== undefined, 5000, 200);

            const isAuth = Utils.isAuthenticated();
            const currentPath = Utils.getCurrentPath();

            if (!Router.protect()) {
                return;
            }

            console.log('✅ Rota verificada, continuando inicialização...');

            EventManager.setup();

            if (window.appAuth) {
                await Sync.syncAuth();
            } else {
                if (isAuth) {
                    StateManager.updateState({
                        tokenValid: true,
                        userInitialized: true
                    });
                    console.log('✅ Autenticação via token (fallback)');
                }
            }
            
            Sync.syncRateLimit();

            if (isAuth) {
                console.log('🔐 Usuário autenticado, sincronizando serviços...');
                
                await Sync.syncPayment();
                await Sync.syncPromotion();
                
                setTimeout(() => {
                    if (window.appAuth?.refreshMessageContext) {
                        window.appAuth.refreshMessageContext();
                    }
                }, 800);
            }

            UI.setupModals();
            
            if (window.App && typeof window.App.updateNavbar === 'function') {
                window.App.updateNavbar();
            } else {
                UI.updateNavbar();
            }
            
            if (window.App && typeof window.App.updateRateLimitStatus === 'function') {
                window.App.updateRateLimitStatus();
            } else {
                UI.updateRateLimitStatus();
            }

            Router.setupNavigation();

            StateManager.updateState({
                initialized: true,
                isAppReady: true,
                userInitialized: true
            });

            window._appReadyFired = true;
            window._appInitialized = true;

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
                userSegment: State.userSegment || 'regular',
                isReady: true,
                version: '7.3'
            };

            EventBus.emit('app:ready', appReadyData);
            window.dispatchEvent(new CustomEvent('app:ready', { detail: appReadyData }));
            document.dispatchEvent(new CustomEvent('app:ready', { detail: appReadyData }));
            
            window.dispatchEvent(new CustomEvent('appReady', { 
                detail: { isReady: true, version: '7.3' }
            }));

            console.log('✅ App (Orquestrador) v7.3 inicializado com sucesso!');
            console.log(`📌 Autenticado: ${isAuth}`);
            console.log(`📌 Página: ${currentPath}`);
            console.log(`📌 Admin: ${State.isAdmin}`);
            console.log(`📌 Premium: ${State.isPremium}`);
            console.log(`📌 Créditos: ${State.creditsDisplay}`);
            console.log(`📌 Segmento: ${State.userSegment || 'Não definido'}`);
            console.log(`📌 Mensagem: ${State.currentMessage?.message_id || 'Nenhuma'}`);
            console.log('🌉 window.appAuth centralizado');
            console.log('📦 AppUtils disponível');
            console.log('⚡ fetchWithAuth com refresh automático');
            console.log('🔄 Estado reativo via Proxy');
            console.log('📡 EventBus com fila de eventos');
            console.log('📢 Sistema de mensagens inteligentes ativo');
            console.log('🔗 Integrado com auth.js, payment.js, dashboard.js');
            console.log('🔧 CORREÇÃO V7.3: isAvailable adicionado no objeto App');

        } catch (error) {
            console.error('❌ Erro na inicialização do App:', error);
            Utils.showNotification('Erro ao inicializar aplicação. Recarregue a página.', 'error');
            
            EventBus.emit('app:error', { error: error.message || 'Erro na inicialização' });
            
            StateManager.updateState({
                initialized: false,
                isAppReady: false,
                userInitialized: false
            });
            window._appReadyFired = false;
        }
    }

    // ==============================================
    // 🔥🔥🔥 EXPORTAÇÕES GLOBAIS - CORRIGIDO
    // ==============================================

    const App = {
        CONFIG,
        State,
        StateManager,
        Utils,
        EventBus,
        
        Router,
        UI,
        Auth,
        Pow,
        Analysis,
        Sync,
        
        init: initApp,
        isInitialized: function() {
            return !!(window._appInitialized && State.isAppReady);
        },
        isReady: function() {
            return State.isAppReady === true;
        },
        
        // 🔥🔥🔥 CORREÇÃO: ADICIONADO MÉTODO ISAVAILABLE
        isAvailable: function() {
            return Pow.isAvailable();
        },
        
        showNotification: Utils.showNotification,
        isAuthenticated: Utils.isAuthenticated,
        getCurrentUser: () => State.user,
        getCredits: () => State.credits,
        isAdmin: () => State.isAdmin,
        isPremium: () => State.isPremium,
        hasVitalicio: () => State.hasPromotionalPrice,
        getPromotionalPrice: () => State.promotionalPrice,
        canReceiveDailyCredit: () => State.canReceiveDailyCredit,
        getDaysLeftPremium: () => State.daysLeftPremium,
        isTokenValid: () => State.tokenValid,
        
        getMessageContext: () => ({
            segment: State.userSegment,
            message: State.currentMessage,
            uiContext: State.uiContext
        }),
        getUserSegment: () => State.userSegment,
        hasActiveMessage: () => State.currentMessage !== null,
        dismissMessage: (messageId) => {
            if (messageId) {
                State.lastMessageId = messageId;
                const container = document.getElementById('messageContainer');
                if (container) {
                    container.style.display = 'none';
                    container.innerHTML = '';
                }
                window.dispatchEvent(new CustomEvent('message:dismissed', {
                    detail: { messageId }
                }));
            }
        },
        refreshMessage: async () => {
            if (window.appAuth && typeof window.appAuth.refreshMessageContext === 'function') {
                return await window.appAuth.refreshMessageContext();
            }
            return null;
        },
        
        // MÉTODOS UI COM BIND EXPLÍCITO
        updateNavbar: UI.updateNavbar.bind(UI),
        updateCredits: UI.updateCredits.bind(UI),
        updateAdminBadge: UI.updateAdminBadge.bind(UI),
        updatePremiumBadge: UI.updatePremiumBadge.bind(UI),
        updateVitalicioBadge: UI.updateVitalicioBadge.bind(UI),
        updatePowStatus: UI.updatePowStatus.bind(UI),
        updateRateLimitStatus: UI.updateRateLimitStatus.bind(UI),
        updateLoadingProgress: UI.updateLoadingProgress.bind(UI),
        showLoading: UI.showLoading.bind(UI),
        hideLoading: UI.hideLoading.bind(UI),
        setupModals: UI.setupModals.bind(UI),
        clearElementCache: UI.clearElementCache.bind(UI),
        invalidateCache: UI.invalidateCache.bind(UI),
        scheduleUpdate: UI.scheduleUpdate.bind(UI),
        
        fetchWithAuth: fetchWithAuth,
        refreshTokenSafely: refreshTokenSafely,
        
        // 🔥 CORRIGIDO: uploadWithPow usa o Pow.uploadWithPow
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
        clearAnalysisHistory: Analysis.clearHistory,
        
        isRateLimitBlocked: Utils.isRateLimitBlocked,
        getRateLimitTimeRemaining: Utils.getRateLimitTimeRemaining,
        getRateLimitRemainingAttempts: Utils.getRateLimitRemainingAttempts,
        getRateLimitStatus: function() {
            return {
                blocked: State.rateLimitBlocked,
                blockedUntil: State.rateLimitBlockedUntil,
                remainingAttempts: State.rateLimitRemainingAttempts,
                for: State.rateLimitBlockedFor,
                timeRemaining: Utils.getRateLimitTimeRemaining()
            };
        },
        
        navigate: Router.navigate,
        goBack: Utils.goBack,
        getQueryParam: Utils.getQueryParam,
        
        escapeHtml: Utils.escapeHtml,
        formatDate: Utils.formatDate,
        sanitizeNumber: Utils.sanitizeNumber,
        formatCreditsDisplay: Utils.formatCreditsDisplay,
        validateCPF: Utils.validateCPF,
        debounce: Utils.debounce,
        throttle: Utils.throttle,
        
        loadCredits: window.appAuth?.loadUserCredits || (() => {}),
        loadPremiumStatus: window.loadPremiumStatus || (() => {}),
        receiveDailyCredit: window.receiveDailyCredit || (() => {}),
        getMaxCredits: () => CONFIG.MAX_CREDITS_BALANCE,
        getCreditsBalance: () => State.credits,
        
        logout: handleUnauthorized
    };

    // EXPORTAÇÕES GLOBAIS
    window.App = App;
    window.app = App;
    window.autoAnalytics = App;
    window.EventBus = EventBus;
    window.__APP_STATE = State;
    window.__APP_STATE_MANAGER = StateManager;
    window.__APP_CONFIG = CONFIG;
    window.AppUtils = AppUtils;
    
    window.showNotification = Utils.showNotification;
    window.isAuthenticated = Utils.isAuthenticated;
    window.fetchWithAuth = fetchWithAuth;
    window.refreshTokenSafely = refreshTokenSafely;
    window.logout = handleUnauthorized;
    window.getCurrentUser = () => State.user;
    
    window.updateCreditsDisplay = UI.updateCredits.bind(UI);
    window.updateNavbar = UI.updateNavbar.bind(UI);
    window.updateRateLimitStatus = UI.updateRateLimitStatus.bind(UI);
    window.receiveDailyCredit = window.receiveDailyCredit || (() => {});
    window.loadPremiumStatus = window.loadPremiumStatus || (() => {});

    // INICIAR
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

    console.log('✅ app.js (Orquestrador) v7.3 carregado!');
    console.log('   🔥 CORRIGIDO: Bug this.isAvailable is not a function');
    console.log('   🔥 ADICIONADO: Método isAvailable no objeto App');
    console.log('   🔥 CORRIGIDO: uploadWithPow usa Pow.isAvailable()');
    console.log('   🔥 MELHORADO: Verificação robusta do PoW');
    console.log('   🔥 OTIMIZADO: Redução de chamadas redundantes');
    console.log('   📢 Sistema de mensagens inteligentes integrado');

})();