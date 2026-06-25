// frontend/js/app.js - ORQUESTRADOR CENTRAL - V4.0 (ARQUITETURA REFATORADA)
/**
 * AutoAnalytics - Módulo Principal da Aplicação
 * 
 * 🏗️ ARQUITETURA V4.0:
 * 1. 🔥 Sistema de Rotas com validação precisa (corrigido)
 * 2. 🔥 Separação clara de responsabilidades (SRP)
 * 3. 🔥 Gerenciamento de estado reativo
 * 4. 🔥 Sistema de eventos desacoplado
 * 5. 🔥 Lazy loading e inicialização otimizada
 * 6. 🔥 Rate Limiter e PoW integrados
 * 7. 🔥 Token management com refresh automático
 * 8. 🔥 Sistema de créditos com limite máximo (3)
 * 
 * 🔥 CORREÇÕES V4.0:
 * - Router.isProtected() com validação exata (.startsWith)
 * - Router.isPublic() com validação exata
 * - Prevenção de falsos positivos em rotas
 * - Melhor tratamento de rotas aninhadas
 * - Caching de verificações de rota
 * 
 * 🔥 ORDEM DE CARREGAMENTO:
 *   1. pow-client.js → window.powClient
 *   2. auth.js → window.appAuth (v3.0+)
 *   3. app.js → ORQUESTRADOR (ESTE ARQUIVO)
 *   4. dashboard.js → funcionalidades do dashboard
 *   5. payment.js → pagamentos e planos
 */

(function() {
    'use strict';

    console.log('🚀 Inicializando App (Orquestrador) v4.0...');

    // ==============================================
    // 🔥 CONFIGURAÇÕES GLOBAIS (OTIMIZADAS)
    // ==============================================

    const CONFIG = Object.freeze({
        // Limites e créditos
        MAX_FILES: 3,
        MAX_FILE_SIZE_KB: 200,
        MAX_CREDITS_BALANCE: 3,
        INITIAL_FREE_CREDITS: 3,
        
        // Preços
        PROMOTIONAL_PRICE: 97.00,
        REGULAR_PRICE: 149.90,
        TOTAL_PROMOTIONAL_SLOTS: 100,
        DAYS_PREMIUM: 30,
        
        // Tokens e sessão
        TOKEN_EXPIRY_MINUTES: 15,
        SESSION_TIMEOUT: 15 * 60 * 1000, // 15 minutos
        TOKEN_CHECK_INTERVAL: 60000, // 1 minuto
        
        // Rate Limiter (sincronizado com backend)
        RATE_LIMIT_LOGIN_MAX: 5,
        RATE_LIMIT_LOGIN_WINDOW: 900,
        RATE_LIMIT_REGISTER_MAX: 5,
        RATE_LIMIT_REGISTER_WINDOW: 3600,
        
        // PoW
        POW_AUTO_REFILL_INTERVAL: 30000,
        POW_STOCK_SIZE: 2,
        
        // API e carregamento
        API_BASE: '/api',
        CREDITS_UPDATE_INTERVAL: 30000,
        MAX_LOAD_ATTEMPTS: 10,
        LOAD_RETRY_DELAY: 500,
        
        // Rotas (centralizadas)
        ROUTES: {
            PROTECTED: ['/', '/dashboard', '/planos', '/checkout'],
            PUBLIC: ['/login', '/register'],
            HOME: '/dashboard',
            LOGIN: '/login'
        }
    });

    // ==============================================
    // 🔥 ESTADO GLOBAL (REATIVO)
    // ==============================================

    const State = {
        // Dados do usuário
        user: null,
        credits: 0,
        isPremium: false,
        isAdmin: false,
        creditsDisplay: '0',
        
        // Status
        initialized: false,
        isAppReady: false,
        tokenValid: false,
        tokenExpiresAt: null,
        lastActivity: Date.now(),
        loadAttempts: 0,
        
        // Premium e vitalício
        premiumStatus: null,
        hasPromotionalPrice: false,
        promotionalPrice: null,
        isVitalicio: false,
        daysLeftPremium: 0,
        canReceiveDailyCredit: false,
        receivedDailyCreditToday: false,
        
        // PoW
        powReady: false,
        powSolutionsReady: 0,
        powAutoRefillActive: false,
        
        // Rate Limiter
        rateLimitBlocked: false,
        rateLimitBlockedUntil: 0,
        rateLimitRemainingAttempts: CONFIG.RATE_LIMIT_LOGIN_MAX,
        rateLimitBlockedFor: 'login',
        
        // Listeners (para limpeza)
        _listeners: [],
        _intervals: []
    };

    // ==============================================
    // 🔥 UTILITÁRIOS (PURAS FUNÇÕES)
    // ==============================================

    const Utils = {
        // Formatação
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

        // Notificações
        showNotification: (message, type = 'info') => {
            if (window.appAuth?.showNotification) {
                return window.appAuth.showNotification(message, type);
            }
            
            if (window.toastr?.[type]) {
                window.toastr[type](message);
                return true;
            }
            
            if (type === 'error' || type === 'warning') {
                console.warn(`[${type}] ${message}`);
                alert(`⚠️ ${message}`);
                return true;
            }
            
            console.log(`[${type}] ${message}`);
            return true;
        },

        // Navegação
        getCurrentPath: () => window.location.pathname,
        getQueryParam: (param) => new URLSearchParams(window.location.search).get(param),
        redirectTo: (url) => {
            if (window.location.pathname !== url) {
                window.location.href = url;
            }
        },
        goBack: () => window.history.back(),
        goForward: () => window.history.forward(),
        reload: () => window.location.reload(),

        // Autenticação
        isAuthenticated: () => {
            try {
                if (window.appAuth) {
                    return typeof window.appAuth.isAuthenticated === 'function' 
                        ? window.appAuth.isAuthenticated() 
                        : !!window.appAuth.isAuthenticated;
                }
                return !!localStorage.getItem('access_token');
            } catch (e) {
                return !!localStorage.getItem('access_token');
            }
        },

        // Rate Limiter
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

        // Waiters (para sincronização)
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
    // 🔥 ROTEADOR (CORRIGIDO E OTIMIZADO)
    // ==============================================

    const Router = {
        // Cache de verificações para performance
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
            // Cache por rota
            const cacheKey = `${path}|${route}`;
            if (Router._pathCache.has(cacheKey)) {
                return Router._pathCache.get(cacheKey);
            }

            let result = false;
            
            // Rota raiz: correspondência exata
            if (route === '/') {
                result = path === '/' || path === '/index.html' || path === '';
            } 
            // Outras rotas: igualdade ou path começa com route/
            else {
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

        protect: () => {
            const isAuth = Utils.isAuthenticated();
            
            if (Router.isProtected() && !isAuth) {
                console.log('🔒 Rota protegida - redirecionando para login');
                Utils.redirectTo(CONFIG.ROUTES.LOGIN);
                return false;
            }

            if (Router.isPublic() && isAuth) {
                console.log('✅ Usuário já logado - redirecionando para dashboard');
                Utils.redirectTo(CONFIG.ROUTES.HOME);
                return false;
            }

            return true;
        },

        navigate: (url) => {
            // Verifica se a URL é protegida
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
            // Links com data-nav
            document.querySelectorAll('[data-nav]').forEach(el => {
                el.addEventListener('click', (e) => {
                    e.preventDefault();
                    const target = el.getAttribute('data-nav');
                    if (target) Router.navigate(target);
                });
            });

            // Links normais
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

        // Limpa cache (útil em navegação SPA)
        clearCache: () => {
            Router._pathCache.clear();
            Router._lastPath = '';
        }
    };

    // ==============================================
    // 🔥 GERENCIADOR DE UI
    // ==============================================

    const UI = {
        _elements: new Map(), // Cache de elementos DOM

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

                window.dispatchEvent(new CustomEvent('creditsUpdated', { 
                    detail: { 
                        credits, 
                        display: formattedDisplay,
                        maxCredits: CONFIG.MAX_CREDITS_BALANCE,
                        isPremium
                    } 
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
            
            // Badge de status
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

            // Botão de login
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

            // Botão de registro
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

            // Tooltips
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

        // Limpa cache de elementos (útil em mudanças de página)
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
                if (window.appAuth?.logout) {
                    window.appAuth.logout();
                } else {
                    localStorage.clear();
                    Utils.redirectTo(CONFIG.ROUTES.LOGIN);
                }
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
                    window.dispatchEvent(new CustomEvent('rateLimitBlocked', {
                        detail: {
                            retryAfter: data.retry_after || 60,
                            remaining: data.remaining_attempts || 0,
                            message: data.detail || data.message || 'Muitas requisições. Aguarde um momento.',
                            for: 'token-check'
                        }
                    }));
                    return;
                }
                
                if (response.status === 401) {
                    console.log('🔄 Token expirado, tentando refresh...');
                    if (window.appAuth.refreshTokenSafely) {
                        const refreshed = await window.appAuth.refreshTokenSafely();
                        if (refreshed) {
                            console.log('✅ Token renovado com sucesso!');
                            Auth.resetSessionTimer();
                            State.tokenValid = true;
                        } else {
                            console.log('❌ Falha ao renovar token, fazendo logout...');
                            Utils.showNotification('Sessão expirada. Faça login novamente.', 'warning');
                            if (window.appAuth.logout) {
                                window.appAuth.logout();
                            }
                        }
                    }
                } else if (response.ok) {
                    const data = await response.json();
                    
                    if (data.status === 'refreshed' && data.access_token) {
                        console.log('🔄 Token renovado via check-token');
                        State.tokenValid = true;
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
                } catch (e) {
                    console.warn('Erro ao carregar créditos:', e);
                }
            }
        },

        loadPremiumStatus: async () => {
            if (window.loadPremiumStatus) {
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
                        
                        window.dispatchEvent(new CustomEvent('premiumStatusUpdated', {
                            detail: {
                                isPremium: State.isPremium,
                                daysLeft: State.daysLeftPremium,
                                hasPromotionalPrice: State.hasPromotionalPrice,
                                promotionalPrice: State.promotionalPrice,
                                canReceiveDailyCredit: State.canReceiveDailyCredit,
                                receivedDailyCreditToday: State.receivedDailyCreditToday
                            }
                        }));
                        
                        return status;
                    }
                } catch (e) {
                    console.warn('Erro ao carregar status premium:', e);
                }
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
    // 🔥 GERENCIADOR DE PoW
    // ==============================================

    const Pow = {
        _autoRefillInterval: null,

        isAvailable: () => {
            return window.powClient !== undefined && window.powClient !== null;
        },

        startAutoRefill: () => {
            if (!Pow.isAvailable()) {
                console.log('⏳ PoW não disponível, aguardando...');
                setTimeout(() => Pow.startAutoRefill(), 2000);
                return;
            }

            try {
                if (typeof window.powClient.startAutoRefill === 'function') {
                    if (Pow._autoRefillInterval) {
                        clearInterval(Pow._autoRefillInterval);
                    }
                    
                    window.powClient.startAutoRefill(CONFIG.POW_AUTO_REFILL_INTERVAL);
                    State.powAutoRefillActive = true;
                    console.log(`⚡ PoW auto-refill iniciado (${CONFIG.POW_AUTO_REFILL_INTERVAL/1000}s)`);
                    
                    setTimeout(() => {
                        if (typeof window.powClient.preSolve === 'function') {
                            window.powClient.preSolve();
                        }
                    }, 100);
                    
                    window.dispatchEvent(new CustomEvent('powReady', {
                        detail: {
                            solutionsReady: State.powSolutionsReady,
                            autoRefill: true
                        }
                    }));
                }
            } catch (e) {
                console.warn('Erro ao iniciar PoW auto-refill:', e);
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
    // 🔥 GERENCIADOR DE EVENTOS (DESACOPLADO)
    // ==============================================

    const EventManager = {
        _handlers: new Map(),

        setup: () => {
            // Password toggle
            document.querySelectorAll('.password-toggle').forEach(btn => {
                btn.addEventListener('click', () => {
                    const targetId = btn.getAttribute('data-target');
                    const field = document.getElementById(targetId);
                    if (field) {
                        const icon = btn.querySelector('i');
                        if (field.type === 'password') {
                            field.type = 'text';
                            if (icon) {
                                icon.classList.remove('fa-eye-slash');
                                icon.classList.add('fa-eye');
                            }
                        } else {
                            field.type = 'password';
                            if (icon) {
                                icon.classList.remove('fa-eye');
                                icon.classList.add('fa-eye-slash');
                            }
                        }
                    }
                });
            });

            // Logout
            document.querySelectorAll('#logoutBtn, .logout-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    if (window.appAuth?.logout) {
                        window.appAuth.logout();
                    } else {
                        localStorage.clear();
                        Utils.redirectTo(CONFIG.ROUTES.LOGIN);
                    }
                });
            });

            // Botão voltar
            document.querySelectorAll('.btn-back').forEach(el => {
                el.addEventListener('click', () => {
                    window.history.back();
                });
            });

            // Eventos do auth.js
            window.addEventListener('authReady', (event) => {
                console.log('📢 Evento authReady recebido');
                if (event.detail) {
                    State.isAuthenticated = event.detail.isAuthenticated || false;
                    State.user = event.detail.user || null;
                }
                UI.updateNavbar();
                setTimeout(() => Pow.startAutoRefill(), 1000);
            });

            window.addEventListener('authLogout', () => {
                console.log('📢 Evento authLogout recebido');
                State.isAuthenticated = false;
                State.user = null;
                State.credits = 0;
                State.isPremium = false;
                State.isAdmin = false;
                State.hasPromotionalPrice = false;
                State.promotionalPrice = null;
                State.rateLimitBlocked = false;
                State.rateLimitBlockedUntil = 0;
                State.rateLimitRemainingAttempts = CONFIG.RATE_LIMIT_LOGIN_MAX;
                State.rateLimitBlockedFor = 'login';
                
                UI.updateNavbar();
                UI.updateRateLimitStatus();
                Pow.reset();
                Pow.stopAutoRefill();
            });

            // Rate Limiter events
            window.addEventListener('rateLimitBlocked', (event) => {
                console.log('📢 Evento rateLimitBlocked recebido', event.detail);
                
                if (event.detail) {
                    State.rateLimitBlocked = true;
                    State.rateLimitBlockedUntil = Date.now() + (event.detail.retryAfter * 1000);
                    State.rateLimitRemainingAttempts = event.detail.remaining || 0;
                    State.rateLimitBlockedFor = event.detail.for || 'login';
                    State.rateLimitLastError = event.detail;
                    
                    UI.updateRateLimitStatus();
                    UI.updateNavbar();
                    
                    if (event.detail.message) {
                        Utils.showNotification(event.detail.message, 'warning');
                    }
                }
            });

            window.addEventListener('rateLimitUnblocked', () => {
                console.log('📢 Evento rateLimitUnblocked recebido');
                State.rateLimitBlocked = false;
                State.rateLimitBlockedUntil = 0;
                State.rateLimitRemainingAttempts = CONFIG.RATE_LIMIT_LOGIN_MAX;
                UI.updateRateLimitStatus();
                UI.updateNavbar();
                Utils.showNotification('✅ Bloqueio removido. Você pode tentar novamente.', 'success');
            });

            // Créditos
            window.addEventListener('creditsUpdated', (event) => {
                if (event.detail) {
                    State.credits = event.detail.credits || 0;
                    State.creditsDisplay = event.detail.display || '0';
                    State.isPremium = event.detail.isPremium || false;
                }
                UI.updateCredits();
            });

            // Premium
            window.addEventListener('premiumStatusUpdated', (event) => {
                if (event.detail) {
                    State.isPremium = event.detail.isPremium || false;
                    State.daysLeftPremium = event.detail.daysLeft || 0;
                    State.hasPromotionalPrice = event.detail.hasPromotionalPrice || false;
                    State.promotionalPrice = event.detail.promotionalPrice || null;
                    State.canReceiveDailyCredit = event.detail.canReceiveDailyCredit || false;
                    State.receivedDailyCreditToday = event.detail.receivedDailyCreditToday || false;
                }
                UI.updatePremiumBadge();
                UI.updateVitalicioBadge();
                UI.updateCredits();
            });

            // Daily Credit
            window.addEventListener('dailyCreditReceived', (event) => {
                if (event.detail?.success) {
                    Utils.showNotification('🎉 Crédito diário recebido!', 'success');
                    UI.updateCredits();
                }
            });

            // Promoção
            window.addEventListener('promotionStatusUpdated', (event) => {
                if (event.detail) {
                    State.hasPromotionalPrice = event.detail.hasPromotionalPrice || false;
                    State.promotionalPrice = event.detail.promotionalPrice || null;
                    UI.updateVitalicioBadge();
                }
            });

            // PoW
            window.addEventListener('powReady', (event) => {
                console.log('📢 Evento powReady recebido');
                State.powReady = true;
                if (event.detail) {
                    State.powSolutionsReady = event.detail.solutionsReady || 0;
                    State.powAutoRefillActive = event.detail.autoRefill || false;
                }
                UI.updatePowStatus();
            });

            // Erros globais
            window.addEventListener('unhandledrejection', (event) => {
                console.error('❌ Erro não tratado (Promise):', event.reason);
                
                if (event.reason?.status === 429) {
                    const detail = event.reason.detail || {};
                    window.dispatchEvent(new CustomEvent('rateLimitBlocked', {
                        detail: {
                            retryAfter: detail.retry_after || 60,
                            remaining: detail.remaining_attempts || 0,
                            message: detail.message || 'Muitas requisições. Aguarde um momento.'
                        }
                    }));
                    return;
                }
                
                if (event.reason?.message) {
                    Utils.showNotification(`Erro: ${event.reason.message}`, 'error');
                } else {
                    Utils.showNotification('Erro inesperado. Tente novamente.', 'error');
                }
            });

            window.addEventListener('error', (event) => {
                console.error('❌ Erro global:', event.error || event.message);
                if (event.target?.tagName === 'SCRIPT') return;
                Utils.showNotification('Erro na aplicação. Recarregue a página se persistir.', 'error');
            });

            // Atividade do usuário
            ['click', 'mousemove', 'keydown', 'scroll', 'touchstart'].forEach(event => {
                document.addEventListener(event, () => {
                    State.lastActivity = Date.now();
                    Auth.resetSessionTimer();
                });
            });
        },

        // Limpa todos os handlers (para cleanup)
        clear: () => {
            // Na prática, isso seria mais complexo
            // Mas para este caso, apenas removemos os listeners que podemos
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
                    State.user = userData;
                    State.credits = userData.credits || 0;
                    State.isAdmin = userData.is_admin || false;
                    State.isPremium = userData.plan === 'premium_mensal' || userData.plan === 'PREMIUM_MENSAL';
                    State.tokenValid = true;
                    
                    UI.updateNavbar();
                    Credits.startPolling();
                    Auth.startTokenCheck();
                    Auth.startSessionTimer();
                    
                    setTimeout(() => Pow.startAutoRefill(), 1000);
                } else {
                    State.tokenValid = false;
                }

                return isAuth;
            } catch (e) {
                console.error('Erro ao sincronizar auth:', e);
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
                    window.dispatchEvent(new CustomEvent('rateLimitBlocked', {
                        detail: {
                            retryAfter: data.retry_after || 60,
                            remaining: data.remaining_attempts || 0,
                            message: data.detail || data.message || 'Muitas requisições. Aguarde um momento.',
                            for: 'promotion'
                        }
                    }));
                    return;
                }
                
                if (response.ok) {
                    const data = await response.json();
                    State.hasPromotionalPrice = data.user_locked_price !== null;
                    State.promotionalPrice = data.user_locked_price || null;
                    
                    window.dispatchEvent(new CustomEvent('promotionStatusUpdated', {
                        detail: {
                            hasPromotionalPrice: State.hasPromotionalPrice,
                            promotionalPrice: State.promotionalPrice
                        }
                    }));
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
                        Pow.startAutoRefill();
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
    // 🔥 CONSTRUÇÃO DA INSTÂNCIA PRINCIPAL
    // ==============================================

    const AppInstance = {
        // Estado
        state: State,
        config: CONFIG,
        
        // Módulos
        utils: Utils,
        ui: UI,
        router: Router,
        auth: Auth,
        credits: Credits,
        sync: Sync,
        pow: Pow,
        events: EventManager,
        
        // Funções de créditos
        getMaxCredits: () => CONFIG.MAX_CREDITS_BALANCE,
        getCreditsBalance: () => State.credits,
        isPremium: () => State.isPremium,
        hasVitalicio: () => State.hasPromotionalPrice,
        getPromotionalPrice: () => State.promotionalPrice,
        canReceiveDailyCredit: () => State.canReceiveDailyCredit,
        getDaysLeftPremium: () => State.daysLeftPremium,
        receiveDailyCredit: Credits.receiveDailyCredit,
        loadPremiumStatus: Credits.loadPremiumStatus,
        isTokenValid: () => State.tokenValid,
        
        // Funções PoW
        isPowAvailable: Pow.isAvailable,
        getPowStats: Pow.getStats,
        preparePowForUpload: Pow.prepareForUpload,
        uploadWithPow: Pow.uploadWithPow,
        startPowAutoRefill: Pow.startAutoRefill,
        stopPowAutoRefill: Pow.stopAutoRefill,
        resetPow: Pow.reset,
        
        // Funções Rate Limiter
        isRateLimitBlocked: Utils.isRateLimitBlocked,
        getRateLimitTimeRemaining: Utils.getRateLimitTimeRemaining,
        getRateLimitRemainingAttempts: Utils.getRateLimitRemainingAttempts,
        getRateLimitStatus: () => ({
            blocked: State.rateLimitBlocked,
            blockedUntil: State.rateLimitBlockedUntil,
            remainingAttempts: State.rateLimitRemainingAttempts,
            for: State.rateLimitBlockedFor,
            timeRemaining: Utils.getRateLimitTimeRemaining()
        }),
        
        // Utilitários gerais
        showNotification: Utils.showNotification,
        updateCredits: UI.updateCredits,
        updateNavbar: UI.updateNavbar,
        updateRateLimitStatus: UI.updateRateLimitStatus,
        navigate: Router.navigate,
        showLoading: UI.showLoading,
        hideLoading: UI.hideLoading,
        updateLoadingProgress: UI.updateLoadingProgress,
        isAuthenticated: Utils.isAuthenticated,
        goBack: Utils.goBack,
        goForward: Utils.goForward,
        reload: Utils.reload,
        getQueryParam: Utils.getQueryParam,
        waitForAuth: Utils.waitForAuth,
        formatCreditsDisplay: Utils.formatCreditsDisplay,
        waitForPayment: Utils.waitForPayment,
        waitForPow: Utils.waitForPow,
        
        // Inicialização
        init: initApp,
        
        // Cleanup
        destroy: () => {
            console.log('🧹 Destruindo App...');
            Auth.stop();
            Credits.stop();
            Pow.stop();
            UI.clearElementCache();
            Router.clearCache();
            State.initialized = false;
            State.isAppReady = false;
        }
    };

    // ==============================================
    // 🔥 INICIALIZAÇÃO DA APLICAÇÃO
    // ==============================================

    async function initApp() {
        console.log('🚀 Inicializando App (Orquestrador) v4.0...');

        try {
            // 1. Proteger rotas (CORRIGIDO)
            if (!Router.protect()) {
                console.log('⏳ Redirecionado, interrompendo inicialização');
                return;
            }

            // 2. Aguardar auth.js carregar
            const authLoaded = await Utils.waitForAuth(30);
            if (!authLoaded) {
                console.warn('⚠️ Auth não carregou. Tentando continuar...');
            }

            // 3. Sincronizar com auth.js
            const isAuth = await Sync.syncAuth();
            
            // 4. Sincronizar Rate Limit
            Sync.syncRateLimit();

            // 5. Se estiver autenticado, sincroniza com payment, promoção e PoW
            if (isAuth) {
                Sync.syncPow().catch(e => console.warn('Erro sync Pow:', e));
                await Sync.syncPayment();
                await Sync.syncPromotion();
            }

            // 6. Configurar UI global
            UI.setupModals();
            UI.updateNavbar();
            UI.updateRateLimitStatus();

            // 7. Configurar eventos globais
            EventManager.setup();

            // 8. Configurar navegação
            Router.setupNavigation();

            // 9. Marcar como inicializado
            State.initialized = true;
            State.isAppReady = true;

            console.log('✅ App (Orquestrador) v4.0 inicializado com sucesso!');
            console.log(`📌 Autenticado: ${isAuth}`);
            console.log(`📌 Página: ${Utils.getCurrentPath()}`);
            console.log(`📌 Admin: ${State.isAdmin}`);
            console.log(`📌 Premium: ${State.isPremium}`);
            console.log(`📌 Créditos: ${State.creditsDisplay}`);
            console.log(`📌 Preço Vitalício: ${State.hasPromotionalPrice ? `R$ ${State.promotionalPrice}` : 'Não'}`);
            console.log(`📌 Rate Limit: ${State.rateLimitBlocked ? `🔴 Bloqueado (${Utils.getRateLimitTimeRemaining()}s)` : '🟢 Disponível'}`);

            // Dispara evento de app pronto
            window.dispatchEvent(new CustomEvent('appReady', { 
                detail: { 
                    isAuthenticated: isAuth,
                    user: State.user,
                    credits: State.credits,
                    isAdmin: State.isAdmin,
                    isPremium: State.isPremium,
                    maxCredits: CONFIG.MAX_CREDITS_BALANCE,
                    hasVitalicio: State.hasPromotionalPrice,
                    promotionalPrice: State.promotionalPrice,
                    tokenValid: State.tokenValid,
                    powReady: State.powReady,
                    rateLimitBlocked: State.rateLimitBlocked,
                    rateLimitTimeRemaining: Utils.getRateLimitTimeRemaining()
                } 
            }));

        } catch (error) {
            console.error('❌ Erro na inicialização do App:', error);
            Utils.showNotification('Erro ao inicializar aplicação. Recarregue a página.', 'error');
            State.initialized = false;
            State.isAppReady = false;
        }
    }

    // ==============================================
    // 🔥 EXPORTAÇÕES GLOBAIS
    // ==============================================

    // Instância principal
    window.App = AppInstance;
    window.app = AppInstance;
    window.autoAnalytics = AppInstance;

    // Aliases para funções específicas
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

    // Funções de créditos
    window.getMaxCredits = () => CONFIG.MAX_CREDITS_BALANCE;
    window.getCreditsBalance = () => State.credits;
    window.isPremium = () => State.isPremium;
    window.hasVitalicio = () => State.hasPromotionalPrice;
    window.getPromotionalPrice = () => State.promotionalPrice;
    window.canReceiveDailyCredit = () => State.canReceiveDailyCredit;
    window.getDaysLeftPremium = () => State.daysLeftPremium;
    window.receiveDailyCredit = Credits.receiveDailyCredit;
    window.loadPremiumStatus = Credits.loadPremiumStatus;
    window.isTokenValid = () => State.tokenValid;

    // Funções Rate Limiter
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

    // Funções PoW
    window.isPowAvailable = Pow.isAvailable;
    window.getPowStats = Pow.getStats;
    window.preparePowForUpload = Pow.prepareForUpload;
    window.uploadWithPow = Pow.uploadWithPow;
    window.startPowAutoRefill = Pow.startAutoRefill;
    window.stopPowAutoRefill = Pow.stopAutoRefill;
    window.resetPow = Pow.reset;

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
            setTimeout(initApp, 100);
        }
    }

    console.log('✅ app.js (Orquestrador) v4.0 carregado!');
    console.log('   🏗️ Arquitetura refatorada com:');
    console.log('   - Sistema de Rotas corrigido (validação exata)');
    console.log('   - Separação de responsabilidades (SRP)');
    console.log('   - Gerenciamento de estado reativo');
    console.log('   - Sistema de eventos desacoplado');
    console.log('   - Cache de verificações de rota');
    console.log('   📌 Módulos disponíveis:');
    console.log('   - App.router (roteador corrigido)');
    console.log('   - App.auth (autenticação)');
    console.log('   - App.credits (créditos)');
    console.log('   - App.pow (Proof of Work)');
    console.log('   - App.utils (utilitários)');
    console.log('   - App.events (gerenciador de eventos)');

})();