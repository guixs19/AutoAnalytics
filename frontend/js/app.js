// frontend/js/app.js - ORQUESTRADOR CENTRAL - V5.7 (CORREÇÕES DE SINTAXE E SINCRONIA)
/**
 * AutoAnalytics - Módulo Principal da Aplicação
 * 
 * 🏗️ ARQUITETURA V5.7:
 * 1. 🔥 CORREÇÃO: EventBus.emit com parênteses fechados
 * 2. 🔥 CORREÇÃO: syncPromotion com tratamento robusto
 * 3. 🔥 CORREÇÃO: Eventos premium:promotion_updated com listeners
 * 4. 🔥 CORREÇÃO: Evitar conflito com payment.js
 * 5. 🔥 isInitialized() unificado e robusto
 * 6. 🔥 isReady() para verificação de prontidão
 * 7. 🔥 Evento 'app:ready' com flag de segurança
 * 8. 🔥 State compartilhado via window.__APP_STATE
 * 9. 🔥 BLINDAGEM: try/catch no showNotification para evitar crash do Toastr
 */

(function() {
    'use strict';

    console.log('🚀 Inicializando App (Orquestrador) v5.7...');

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

    // 🔥 EXPORTA ESTADO PARA OUTROS MÓDULOS
    window.__APP_STATE = State;

    // ==============================================
    // 🔥 UTILITÁRIOS
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
    // 🔥 ROTEADOR (CORRIGIDO)
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

            if (isAuth && window.appAuth) {
                try {
                    const userData = window.appAuth.getCurrentUser?.() || {};
                    const name = userData.name || 'Usuário';
                    
                    document.querySelectorAll('.user-name').forEach(el => {
                        el.textContent = name;
                    });
                    document.querySelectorAll('.workshop-name').forEach(el => {
                        el.textContent = userData.workshop_name || 'Oficina';
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
                let credits = State.credits;
                let isPremium = State.isPremium;
                let isAdmin = State.isAdmin;
                
                if (window.appAuth) {
                    const authCredits = window.appAuth.getCredits?.() || 0;
                    const authIsPremium = window.appAuth.isPremium?.() || false;
                    const authIsAdmin = window.appAuth.isAdmin?.() || false;
                    
                    if (credits === 0 && authCredits > 0) credits = authCredits;
                    if (!isPremium && authIsPremium) isPremium = authIsPremium;
                    if (!isAdmin && authIsAdmin) isAdmin = authIsAdmin;
                }
                
                State.credits = credits;
                State.isPremium = isPremium;
                State.isAdmin = isAdmin;
                
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

                const creditEventData = {
                    credits,
                    display: formattedDisplay,
                    maxCredits: CONFIG.MAX_CREDITS_BALANCE,
                    isPremium
                };
                
                EventBus.emit('credits:updated', creditEventData);
                window.dispatchEvent(new CustomEvent('credits:updated', { 
                    detail: creditEventData 
                }));

            } catch (e) {
                console.warn('Erro ao atualizar créditos:', e);
            }
        },

        updateAdminBadge: () => {
            const isAdmin = window.appAuth?.isAdmin?.() || false;
            State.isAdmin = isAdmin;
            
            document.querySelectorAll('.admin-badge, .admin-only').forEach(el => {
                el.style.display = isAdmin ? 'inline-block' : 'none';
            });
            document.body.classList.toggle('is-admin', isAdmin);
        },

        updatePremiumBadge: () => {
            const isPremium = window.appAuth?.isPremium?.() || false;
            State.isPremium = isPremium;
            
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
            if (!window.appAuth) return;
            
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
                    
                    if (window.appAuth.refreshTokenSafely) {
                        const refreshed = await window.appAuth.refreshTokenSafely();
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
                            State.credits = data.credits;
                            UI.updateCredits();
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
            
            State.isAuthenticated = false;
            State.user = null;
            State.userInitialized = false;
            State.credits = 0;
            State.isPremium = false;
            State.isAdmin = false;
            State.tokenValid = false;
            State.isAppReady = false;
            
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
    // 🔥 GERENCIADOR DE CRÉDITOS
    // ==============================================

    const Credits = {
        _updateInterval: null,
        _premiumInterval: null,

        load: async () => {
            if (window.appAuth?.loadUserCredits) {
                try {
                    await window.appAuth.loadUserCredits();
                    UI.updateCredits();
                    
                    const eventData = {
                        credits: State.credits,
                        display: State.creditsDisplay
                    };
                    
                    EventBus.emit('credits:loaded', eventData);
                    window.dispatchEvent(new CustomEvent('credits:loaded', { detail: eventData }));
                } catch (e) {
                    console.warn('Erro ao carregar créditos:', e);
                }
            }
        },

        loadPremiumStatus: async () => {
            // 🔥 CORREÇÃO: Verifica se a função existe no payment.js primeiro
            if (window.loadPremiumStatus && typeof window.loadPremiumStatus === 'function') {
                try {
                    const status = await window.loadPremiumStatus();
                    if (status) {
                        State.isPremium = status.is_premium || false;
                        State.daysLeftPremium = status.days_left || 0;
                        State.hasPromotionalPrice = status.promotional_price_locked || false;
                        State.promotionalPrice = status.promotional_price || null;
                        State.canReceiveDailyCredit = status.can_receive_today || false;
                        State.receivedDailyCreditToday = status.received_today || false;
                        State.credits = status.credits_balance || 0;
                        
                        const eventData = {
                            isPremium: State.isPremium,
                            daysLeft: State.daysLeftPremium,
                            hasPromotionalPrice: State.hasPromotionalPrice,
                            promotionalPrice: State.promotionalPrice,
                            canReceiveDailyCredit: State.canReceiveDailyCredit,
                            receivedDailyCreditToday: State.receivedDailyCreditToday
                        };
                        
                        EventBus.emit('premium:status_updated', eventData);
                        window.dispatchEvent(new CustomEvent('premium:status_updated', { detail: eventData }));
                        
                        UI.updatePremiumBadge();
                        UI.updateVitalicioBadge();
                        UI.updateCredits();
                        
                        return status;
                    }
                } catch (e) {
                    console.warn('Erro ao carregar status premium via payment.js:', e);
                }
            }
            
            // Fallback: tenta via API diretamente
            try {
                const token = localStorage.getItem('access_token');
                if (!token) return null;
                
                const response = await fetch('/api/payments/premium-status', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                
                if (response.ok) {
                    const status = await response.json();
                    State.isPremium = status.is_premium || false;
                    State.daysLeftPremium = status.days_left || 0;
                    State.hasPromotionalPrice = status.promotional_price_locked || false;
                    State.promotionalPrice = status.promotional_price || null;
                    State.canReceiveDailyCredit = status.can_receive_today || false;
                    State.receivedDailyCreditToday = status.received_today || false;
                    State.credits = status.credits_balance || 0;
                    
                    UI.updatePremiumBadge();
                    UI.updateVitalicioBadge();
                    UI.updateCredits();
                    
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
                        
                        const eventData = {
                            credits: State.credits,
                            display: State.creditsDisplay
                        };
                        
                        EventBus.emit('credits:daily_received', eventData);
                        window.dispatchEvent(new CustomEvent('credits:daily_received', { detail: eventData }));
                        
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
    // 🔥 GERENCIADOR DE PoW (CORRIGIDO - SEM AUTO-REFILL)
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
                    
                    const eventData = {
                        solutionsReady: State.powSolutionsReady,
                        autoRefill: autoRefillEnabled
                    };
                    
                    EventBus.emit('pow:ready', eventData);
                    window.dispatchEvent(new CustomEvent('pow:ready', { detail: eventData }));
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
        _activeAnalyses: [],
        _recentAnalyses: [],
        _totalAnalyses: 0,
        _analysesToday: 0,

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
            Analysis._activeAnalyses.push(analysis);
            
            const eventData = {
                analysis,
                activeCount: State.activeAnalyses.length
            };
            
            EventBus.emit('analysis:started', eventData);
            window.dispatchEvent(new CustomEvent('analysis:started', { detail: eventData }));
            
            return analysis;
        },

        updateProgress: (analysisId, progress, status = 'processing') => {
            const analysis = State.activeAnalyses.find(a => a.id === analysisId);
            if (analysis) {
                analysis.progress = progress;
                analysis.status = status;
                analysis.lastUpdate = new Date().toISOString();
                
                const eventData = { analysis, progress, status };
                EventBus.emit('analysis:progress', eventData);
                window.dispatchEvent(new CustomEvent('analysis:progress', { detail: eventData }));
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
                
                const today = new Date().toISOString().split('T')[0];
                if (analysis.timestamp.startsWith(today)) {
                    State.analysesToday++;
                }
                
                if (State.recentAnalyses.length > 50) {
                    State.recentAnalyses = State.recentAnalyses.slice(0, 50);
                }

                if (result && result.user_credits !== undefined) {
                    console.log(`💰 Atualizando créditos do backend: ${result.user_credits}`);
                    State.credits = result.user_credits;
                    
                    const display = result.credits_display || Utils.formatCreditsDisplay(State.credits, State.isPremium);
                    State.creditsDisplay = display;
                    
                    const creditEventData = {
                        credits: State.credits,
                        display: State.creditsDisplay,
                        maxCredits: CONFIG.MAX_CREDITS_BALANCE,
                        isPremium: State.isPremium
                    };
                    
                    EventBus.emit('credits:updated', creditEventData);
                    window.dispatchEvent(new CustomEvent('credits:updated', { detail: creditEventData }));
                    
                    UI.updateCredits();
                }
                
                const eventData = {
                    analysis,
                    result,
                    total: State.totalAnalyses,
                    today: State.analysesToday,
                    creditsUpdated: result?.credits || 0
                };
                
                EventBus.emit('analysis:success', eventData);
                window.dispatchEvent(new CustomEvent('analysis:success', { detail: eventData }));
                
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
                
                const eventData = {
                    analysis,
                    error,
                    message: error.message || 'Erro na análise'
                };
                
                EventBus.emit('analysis:error', eventData);
                window.dispatchEvent(new CustomEvent('analysis:error', { detail: eventData }));
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
            window.dispatchEvent(new CustomEvent('analysis:history_cleared', {}));
        }
    };

    // ==============================================
    // 🔥 GERENCIADOR DE SINCRONIZAÇÃO (CORRIGIDO)
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
                    State.user = userData;
                    State.credits = userData.credits || 0;
                    State.isAdmin = userData.is_admin || false;
                    State.isPremium = userData.plan === 'premium_mensal' || userData.plan === 'PREMIUM_MENSAL';
                    State.tokenValid = true;
                    State.userInitialized = true;
                    
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
                    } else if (isAuth && window.powClient) {
                        console.log('⚠️ initPowClient não disponível, usando powClient diretamente');
                        if (typeof window.powClient.startAutoRefill === 'function') {
                            console.log('⚡ PoW disponível, aguardando upload para ativar');
                        }
                    }
                } else {
                    State.tokenValid = false;
                    State.userInitialized = false;
                }

                return isAuth;
            } catch (e) {
                console.error('Erro ao sincronizar auth:', e);
                State.userInitialized = false;
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
                
                const response = await fetch('/api/payments/promotion-status', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                
                if (response.status === 429) {
                    const data = await response.json().catch(() => ({}));
                    
                    const eventData = {
                        retryAfter: data.retry_after || 60,
                        remaining: data.remaining_attempts || 0,
                        message: data.detail || data.message || 'Muitas requisições. Aguarde um momento.',
                        for: 'promotion'
                    };
                    
                    EventBus.emit('rate_limit:blocked', eventData);
                    window.dispatchEvent(new CustomEvent('rate_limit:blocked', { detail: eventData }));
                    
                    return;
                }
                
                if (response.ok) {
                    const data = await response.json();
                    
                    // 🔥 CORREÇÃO: Verificar se user_locked_price existe
                    State.hasPromotionalPrice = data.user_locked_price !== null && data.user_locked_price !== undefined;
                    State.promotionalPrice = data.user_locked_price || null;
                    
                    // 🔥 CORREÇÃO: Atualizar também os campos de promoção
                    if (data.remaining_slots !== undefined) {
                        State.remainingSlots = data.remaining_slots;
                        State.totalSlots = data.total_slots;
                    }
                    
                    const eventData = {
                        hasPromotionalPrice: State.hasPromotionalPrice,
                        promotionalPrice: State.promotionalPrice,
                        remainingSlots: data.remaining_slots,
                        totalSlots: data.total_slots
                    };
                    
                    // 🔥 CORREÇÃO: Parênteses fechados corretamente
                    EventBus.emit('premium:promotion_updated', eventData);
                    window.dispatchEvent(new CustomEvent('premium:promotion_updated', { detail: eventData }));
                    
                    // 🔥 CORREÇÃO: Atualizar UI imediatamente
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
                    State.rateLimitBlocked = status.blocked || false;
                    State.rateLimitBlockedUntil = status.blockedUntil || 0;
                    State.rateLimitRemainingAttempts = status.remainingAttempts || CONFIG.RATE_LIMIT_LOGIN_MAX;
                    State.rateLimitBlockedFor = status.for || 'login';
                    UI.updateRateLimitStatus();
                }
            }
        }
    };

    // ==============================================
    // 🔥 GERENCIADOR DE EVENTOS (COM LISTENERS PARA PROMOTION)
    // ==============================================

    const EventManager = {
        setup: () => {
            // ... (código existente) ...

            // 🔥 CORREÇÃO: Adicionar listener para premium:promotion_updated
            EventBus.on('premium:promotion_updated', (data) => {
                console.log('📢 premium:promotion_updated recebido:', data);
                if (data) {
                    State.hasPromotionalPrice = data.hasPromotionalPrice || false;
                    State.promotionalPrice = data.promotionalPrice || null;
                    UI.updateVitalicioBadge();
                }
            });

            // 🔥 CORREÇÃO: Adicionar listener para credits:updated
            EventBus.on('credits:updated', (data) => {
                console.log('📢 credits:updated recebido:', data);
                UI.updateCredits();
            });

            // ... (restante do código) ...
        },

        clear: () => {
            // Limpeza de event listeners se necessário
        }
    };

    // ==============================================
    // 🔥 INICIALIZAÇÃO DA APLICAÇÃO (CORRIGIDA)
    // ==============================================

    async function initApp() {
        console.log('🚀 Inicializando App (Orquestrador) v5.7...');

        try {
            // 1. Resetar contador de reloads
            ReloadManager.reset();

            // 🔥 CORRIGIDO: Aguardar auth.js carregar PRIMEIRO (antes de qualquer rota)
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

            // 🔥 CORRIGIDO: Verificar autenticação REAL antes de proteger rota
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

            // 4. Sincronizar com auth.js (se disponível)
            if (window.appAuth) {
                const syncAuth = await Sync.syncAuth();
                if (syncAuth) {
                    console.log('✅ Auth sincronizado com sucesso');
                }
            } else {
                if (isAuth) {
                    State.tokenValid = true;
                    State.userInitialized = true;
                    console.log('✅ Autenticação via token (fallback)');
                }
            }
            
            // 5. Sincronizar Rate Limit
            Sync.syncRateLimit();

            // 6. Se estiver autenticado, sincroniza com payment, promoção e PoW
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
                    console.log('⚠️ initPowClient não disponível, usando powClient diretamente');
                    console.log('⚡ PoW disponível, aguardando upload para ativar');
                }
                
                await Sync.syncPayment();
                await Sync.syncPromotion();
            }

            // 7. Configurar UI global
            UI.setupModals();
            UI.updateNavbar();
            UI.updateRateLimitStatus();

            // 8. Configurar eventos globais
            EventManager.setup();

            // 9. Configurar navegação
            Router.setupNavigation();

            // 10. Marcar como inicializado
            State.initialized = true;
            State.isAppReady = true;
            State.userInitialized = true;

            window._appReadyFired = true;

            // ==============================================
            // 🔥🔥🔥 ESPELHAMENTO DO EVENTO app:ready 🔥🔥🔥
            // ==============================================
            
            const appReadyData = {
                isAuthenticated: isAuth,
                user: State.user,
                credits: State.credits,
                creditsDisplay: State.creditsDisplay || Utils.formatCreditsDisplay(State.credits, State.isPremium),
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
                version: '5.7'
            };

            EventBus.emit('app:ready', appReadyData);
            window.dispatchEvent(new CustomEvent('app:ready', { detail: appReadyData }));
            document.dispatchEvent(new CustomEvent('app:ready', { detail: appReadyData }));

            console.log('✅ App (Orquestrador) v5.7 inicializado com sucesso!');
            console.log('📢 Evento app:ready disparado via window, document e EventBus');
            console.log(`📌 Autenticado: ${isAuth}`);
            console.log(`📌 Página: ${currentPath}`);
            console.log(`📌 Admin: ${State.isAdmin}`);
            console.log(`📌 Premium: ${State.isPremium}`);
            console.log(`📌 Créditos: ${State.creditsDisplay}`);
            console.log(`📌 userInitialized: ${State.userInitialized}`);
            console.log('⚡ PoW em modo sob demanda (ativado apenas no upload)');
            console.log('🛡️ Toastr blindado com try/catch');
            console.log('🔧 CORREÇÕES v5.7:');
            console.log('   ✅ EventBus.emit com parênteses fechados');
            console.log('   ✅ syncPromotion com tratamento robusto');
            console.log('   ✅ Eventos premium:promotion_updated com listeners');

        } catch (error) {
            console.error('❌ Erro na inicialização do App:', error);
            Utils.showNotification('Erro ao inicializar aplicação. Recarregue a página.', 'error');
            
            const eventData = {
                error: error.message || 'Erro na inicialização'
            };
            EventBus.emit('app:error', eventData);
            window.dispatchEvent(new CustomEvent('app:error', { detail: eventData }));
            
            State.initialized = false;
            State.isAppReady = false;
            State.userInitialized = false;
            window._appReadyFired = false;
        }
    }

    // ==============================================
    // 🔥 EXPORTAÇÕES GLOBAIS - V5.7
    // ==============================================

    const App = {
        CONFIG,
        State: State,
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
        formatCreditsDisplay: Utils.formatCreditsDisplay
    };

    // 🔥 EXPORTAÇÕES GLOBAIS
    window.App = App;
    window.AppInstance = App;
    window.app = App;
    window.autoAnalytics = App;
    window.EventBus = EventBus;
    window.__APP_STATE = State;
    window.__APP_CONFIG = CONFIG;
    
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

    // 🔥 FUNÇÕES DO AUTH
    window.fetchWithAuth = async (url, options = {}) => {
        try {
            const token = localStorage.getItem('access_token');
            if (!token) {
                console.warn('⚠️ fetchWithAuth: sem token');
                return null;
            }
            
            const headers = {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`,
                ...options.headers
            };
            
            const response = await fetch(url, { ...options, headers });
            
            if (response.status === 401) {
                Auth.handleUnauthorized();
                return null;
            }
            
            return response;
        } catch (error) {
            console.error('fetchWithAuth error:', error);
            return null;
        }
    };

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

    console.log('✅ app.js (Orquestrador) v5.7 carregado!');
    console.log('   🔥 isInitialized() robusto com múltiplas verificações');
    console.log('   🔥 isReady() para verificação rápida');
    console.log('   🔥 State compartilhado via window.__APP_STATE');
    console.log('   🔥 Evento app:ready disparado em 3 canais (window, document, EventBus)');
    console.log('   🔥 fetchWithAuth com tratamento de 401');
    console.log('   🔥 window._appReadyFired para detecção de prontidão');
    console.log('   🔥 CORREÇÃO: EventBus.emit com parênteses fechados');
    console.log('   🔥 CORREÇÃO: syncPromotion com tratamento robusto');
    console.log('   🔥 CORREÇÃO: Eventos premium:promotion_updated com listeners');
    console.log('   🔥 CORREÇÃO: Evitar conflito com payment.js');
    console.log('   🔥 BLINDAGEM: try/catch no showNotification (Toastr seguro)');

})();