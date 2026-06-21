// frontend/js/app.js - ORQUESTRADOR CENTRAL - V2.0 COMPLETO
/**
 * AutoAnalytics - Módulo Principal da Aplicação
 * 
 * 🔥 RESPONSABILIDADES:
 * 1. Gerencia o estado global da aplicação
 * 2. Sincroniza todos os módulos (auth, dashboard, payment)
 * 3. Controla navegação e proteção de rotas
 * 4. Gerencia UI global (navbar, modals, notificações)
 * 5. Exporta funções globais para todas as páginas
 * 6. Gerencia timeout de sessão inativa
 * 7. Handlers de erros globais
 * 8. Renovação automática de token
 * 
 * FLUXO DE CARREGAMENTO:
 *   1. auth.js → define window.appAuth
 *   2. app.js → orquestra tudo (ESTE ARQUIVO)
 *   3. dashboard.js → funcionalidades do dashboard
 *   4. payment.js → pagamentos e planos
 * 
 * 🔥 COMPATIBILIDADE:
 *   - window.App (instância principal)
 *   - window.app (alias para compatibilidade)
 *   - window.autoAnalytics (alias para compatibilidade)
 */

(function() {
    'use strict';

    console.log('🚀 Inicializando App (Orquestrador) v2.0...');

    // ==============================================
    // 🔥 CONFIGURAÇÕES GLOBAIS
    // ==============================================

    const CONFIG = {
        MAX_FILES: 3,
        MAX_FILE_SIZE_KB: 200,
        CREDITS_UPDATE_INTERVAL: 30000,
        TOKEN_CHECK_INTERVAL: 60000,
        SESSION_TIMEOUT: 15 * 60 * 1000,
        API_BASE: '/api',
        MAX_LOAD_ATTEMPTS: 10,  // 🔥 LIMITE DE TENTATIVAS
        LOAD_RETRY_DELAY: 500   // 🔥 DELAY ENTRE TENTATIVAS
    };

    // ==============================================
    // 🔥 ESTADO GLOBAL DA APLICAÇÃO
    // ==============================================

    const State = {
        user: null,
        credits: 0,
        isPremium: false,
        isAdmin: false,
        creditsDisplay: '0',
        premiumStatus: null,
        initialized: false,
        lastActivity: Date.now(),
        loadAttempts: 0,  // 🔥 CONTADOR DE TENTATIVAS
        isAppReady: false
    };

    // ==============================================
    // 🔥 FUNÇÕES DE UTILIDADE
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

        showNotification: (message, type = 'info') => {
            // 🔥 Fallback seguro para toastr
            if (window.toastr && typeof window.toastr[type] === 'function') {
                window.toastr[type](message);
                return true;
            }
            
            // 🔥 Fallback para alert nativo se toastr não existir
            if (type === 'error' || type === 'warning') {
                console.warn(`[${type}] ${message}`);
                alert(`⚠️ ${message}`);
                return true;
            }
            
            console.log(`[${type}] ${message}`);
            return true;
        },

        isAuthenticated: () => {
            try {
                if (window.appAuth) {
                    return typeof window.appAuth.isAuthenticated === 'function' 
                        ? window.appAuth.isAuthenticated() 
                        : window.appAuth.isAuthenticated;
                }
                return !!localStorage.getItem('access_token');
            } catch (e) {
                return !!localStorage.getItem('access_token');
            }
        },

        getCurrentPath: () => window.location.pathname,

        isLoginPage: () => {
            const path = window.location.pathname;
            return path.includes('login') || path === '/login';
        },

        isDashboardPage: () => {
            const path = window.location.pathname;
            return path === '/' || path === '' || path === '/dashboard' || path.includes('index.html');
        },

        isPlansPage: () => {
            const path = window.location.pathname;
            return path.includes('planos') || path === '/planos';
        },

        isCheckoutPage: () => {
            const path = window.location.pathname;
            return path.includes('checkout') || path === '/checkout';
        },

        redirectTo: (url) => {
            if (window.location.pathname !== url) {
                window.location.href = url;
            }
        },

        getQueryParam: (param) => {
            return new URLSearchParams(window.location.search).get(param);
        },

        goBack: () => window.history.back(),
        goForward: () => window.history.forward(),
        reload: () => window.location.reload(),

        // 🔥 FUNÇÃO PARA ESPERAR O AUTH CARREGAR
        waitForAuth: (maxAttempts = 30) => {
            return new Promise((resolve) => {
                let attempts = 0;
                const checkAuth = () => {
                    attempts++;
                    if (window.appAuth && typeof window.appAuth.isAuthenticated !== 'undefined') {
                        console.log(`✅ Auth encontrado após ${attempts} tentativas`);
                        resolve(true);
                        return;
                    }
                    if (attempts >= maxAttempts) {
                        console.warn(`⚠️ Auth não encontrado após ${maxAttempts} tentativas`);
                        resolve(false);
                        return;
                    }
                    setTimeout(checkAuth, 200);
                };
                checkAuth();
            });
        }
    };

    // ==============================================
    // 🔥 GERENCIADOR DE ROTAS / NAVEGAÇÃO
    // ==============================================

    const Router = {
        protectedRoutes: ['/', '/dashboard', '/planos', '/checkout'],
        publicRoutes: ['/login', '/register'],

        isProtected: () => {
            const path = Utils.getCurrentPath();
            return Router.protectedRoutes.some(route => path === route || path.includes(route));
        },

        isPublic: () => {
            const path = Utils.getCurrentPath();
            return Router.publicRoutes.some(route => path === route || path.includes(route));
        },

        protect: () => {
            const isAuth = Utils.isAuthenticated();
            
            if (Router.isProtected() && !isAuth) {
                console.log('🔒 Rota protegida - redirecionando para login');
                Utils.redirectTo('/login');
                return false;
            }

            if (Router.isPublic() && isAuth) {
                console.log('✅ Usuário já logado - redirecionando para dashboard');
                Utils.redirectTo('/dashboard');
                return false;
            }

            return true;
        },

        navigate: (url) => {
            const isProtected = Router.protectedRoutes.some(route => url === route || url.includes(route));
            
            if (isProtected && !Utils.isAuthenticated()) {
                Utils.showNotification('Faça login para acessar esta página.', 'warning');
                Utils.redirectTo('/login');
                return;
            }

            Utils.redirectTo(url);
        },

        setupNavigation: function() {
            document.querySelectorAll('[data-nav]').forEach(el => {
                el.addEventListener('click', (e) => {
                    e.preventDefault();
                    const target = el.getAttribute('data-nav');
                    if (target) {
                        Router.navigate(target);
                    }
                });
            });

            document.querySelectorAll('a[href^="/"]').forEach(el => {
                if (el.hasAttribute('data-nav')) return;
                if (el.getAttribute('target') === '_blank') return;
                if (el.id === 'logoutBtn') return;
                
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
    // 🔥 GERENCIADOR DE UI GLOBAL
    // ==============================================

    const UI = {
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
                    const userData = window.appAuth.getCurrentUser ? window.appAuth.getCurrentUser() : {};
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
                } catch (e) {
                    console.warn('Erro ao atualizar navbar:', e);
                }
            }
        },

        updateCredits: () => {
            if (!window.appAuth) return;
            
            try {
                const display = window.appAuth.getCreditsDisplay ? window.appAuth.getCreditsDisplay() : '0';
                State.creditsDisplay = display;
                
                const selectors = [
                    '.credits-display', '.user-credits', 
                    '#creditsDisplay', '#creditsCount', '#uploadCredits',
                    '.credits-badge span', '.credits-value'
                ];
                
                document.querySelectorAll(selectors.join(',')).forEach(el => {
                    if (el) el.textContent = display;
                });

                window.dispatchEvent(new CustomEvent('creditsUpdated', { 
                    detail: { credits: State.credits, display: display } 
                }));
            } catch (e) {
                console.warn('Erro ao atualizar créditos:', e);
            }
        },

        updateAdminBadge: () => {
            if (!window.appAuth) return;
            try {
                const isAdmin = window.appAuth.isAdmin ? window.appAuth.isAdmin() : false;
                State.isAdmin = isAdmin;
                
                document.querySelectorAll('.admin-badge, .admin-only').forEach(el => {
                    el.style.display = isAdmin ? 'inline-block' : 'none';
                });

                if (isAdmin) {
                    document.body.classList.add('is-admin');
                } else {
                    document.body.classList.remove('is-admin');
                }
            } catch (e) {
                console.warn('Erro ao atualizar badge admin:', e);
            }
        },

        updatePremiumBadge: () => {
            if (!window.appAuth) return;
            try {
                const isPremium = window.appAuth.isPremium ? window.appAuth.isPremium() : false;
                State.isPremium = isPremium;
                
                document.querySelectorAll('.premium-badge, .premium-only').forEach(el => {
                    el.style.display = isPremium ? 'inline-block' : 'none';
                });
            } catch (e) {
                console.warn('Erro ao atualizar badge premium:', e);
            }
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
        }
    };

    // ==============================================
    // 🔥 GERENCIADOR DE EVENTOS GLOBAIS
    // ==============================================

    const Events = {
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
                    if (window.appAuth && window.appAuth.logout) {
                        window.appAuth.logout();
                    } else {
                        localStorage.clear();
                        Utils.redirectTo('/login');
                    }
                });
            });

            // Navegação
            document.querySelectorAll('[data-nav]').forEach(el => {
                el.addEventListener('click', (e) => {
                    e.preventDefault();
                    const target = el.getAttribute('data-nav');
                    if (target) {
                        Router.navigate(target);
                    }
                });
            });

            // Botão voltar
            document.querySelectorAll('.btn-back').forEach(el => {
                el.addEventListener('click', () => {
                    window.history.back();
                });
            });

            // Eventos customizados
            window.addEventListener('creditsUpdated', () => {
                UI.updateCredits();
            });

            window.addEventListener('authReady', () => {
                UI.updateNavbar();
            });

            window.addEventListener('premiumStatusUpdated', () => {
                UI.updatePremiumBadge();
                UI.updateCredits();
            });

            // 🔥 Handlers de erros globais
            window.addEventListener('unhandledrejection', (event) => {
                console.error('❌ Erro não tratado (Promise):', event.reason);
                if (event.reason && event.reason.message) {
                    Utils.showNotification(`Erro: ${event.reason.message}`, 'error');
                } else {
                    Utils.showNotification('Erro inesperado. Tente novamente.', 'error');
                }
            });

            window.addEventListener('error', (event) => {
                console.error('❌ Erro global:', event.error || event.message);
                if (event.target && event.target.tagName === 'SCRIPT') {
                    return;
                }
                Utils.showNotification('Erro na aplicação. Recarregue a página se persistir.', 'error');
            });

            // 🔥 Rastrear atividade do usuário
            ['click', 'mousemove', 'keydown', 'scroll', 'touchstart'].forEach(event => {
                document.addEventListener(event, () => {
                    State.lastActivity = Date.now();
                    Auth.resetSessionTimer();
                });
            });
        }
    };

    // ==============================================
    // 🔥 GERENCIADOR DE CRÉDITOS
    // ==============================================

    const Credits = {
        load: async () => {
            if (window.appAuth && window.appAuth.loadUserCredits) {
                try {
                    await window.appAuth.loadUserCredits();
                    UI.updateCredits();
                } catch (e) {
                    console.warn('Erro ao carregar créditos:', e);
                }
            }
        },

        startPolling: () => {
            Credits.load();
            
            setInterval(() => {
                Credits.load();
            }, CONFIG.CREDITS_UPDATE_INTERVAL);
            
            console.log(`⏰ Atualização de créditos: ${CONFIG.CREDITS_UPDATE_INTERVAL/1000}s`);
        }
    };

    // ==============================================
    // 🔥 GERENCIADOR DE AUTENTICAÇÃO
    // ==============================================

    const Auth = {
        sessionTimeout: null,

        startSessionTimer: () => {
            if (Auth.sessionTimeout) {
                clearTimeout(Auth.sessionTimeout);
                Auth.sessionTimeout = null;
            }

            if (!Utils.isAuthenticated()) return;

            console.log(`⏰ Timer de sessão: ${CONFIG.SESSION_TIMEOUT/60000} minutos`);

            Auth.sessionTimeout = setTimeout(() => {
                console.log('⏰ Sessão expirada por inatividade');
                Utils.showNotification('⏰ Sessão expirada por inatividade. Faça login novamente.', 'warning');
                if (window.appAuth && window.appAuth.logout) {
                    window.appAuth.logout();
                } else {
                    localStorage.clear();
                    Utils.redirectTo('/login');
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
            Auth.checkRenewal();
            
            setInterval(() => {
                Auth.checkRenewal();
            }, CONFIG.TOKEN_CHECK_INTERVAL);
            
            console.log(`⏰ Verificação de token: ${CONFIG.TOKEN_CHECK_INTERVAL/1000}s`);
        },

        checkRenewal: async () => {
            if (!window.appAuth) return;
            
            const token = localStorage.getItem('access_token');
            if (!token) return;
            
            try {
                const response = await fetch('/api/auth/check-token', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                
                if (response.status === 401) {
                    console.log('🔄 Token expirado, tentando refresh...');
                    if (window.appAuth.refreshTokenSafely) {
                        const refreshed = await window.appAuth.refreshTokenSafely();
                        if (refreshed) {
                            console.log('✅ Token renovado com sucesso!');
                            Auth.resetSessionTimer();
                        } else {
                            console.log('❌ Falha ao renovar token, fazendo logout...');
                            Utils.showNotification('Sessão expirada. Faça login novamente.', 'warning');
                            if (window.appAuth.logout) {
                                window.appAuth.logout();
                            }
                        }
                    }
                } else if (response.ok) {
                    Auth.resetSessionTimer();
                }
            } catch (error) {
                console.warn('Erro ao verificar token:', error);
            }
        },

        // 🔥 FUNÇÃO PARA ESPERAR O APP FICAR PRONTO
        waitForAppReady: (maxAttempts = CONFIG.MAX_LOAD_ATTEMPTS) => {
            return new Promise((resolve) => {
                let attempts = 0;
                const checkReady = () => {
                    attempts++;
                    State.loadAttempts = attempts;
                    
                    const isAuthReady = window.appAuth !== undefined && window.appAuth !== null;
                    const isAppReady = window.App !== undefined && window.App !== null;
                    
                    if (isAuthReady && isAppReady) {
                        console.log(`✅ App pronto após ${attempts} tentativas`);
                        State.isAppReady = true;
                        resolve(true);
                        return;
                    }
                    
                    if (attempts >= maxAttempts) {
                        console.warn(`⚠️ App não ficou pronto após ${maxAttempts} tentativas`);
                        State.isAppReady = false;
                        resolve(false);
                        return;
                    }
                    
                    setTimeout(checkReady, CONFIG.LOAD_RETRY_DELAY);
                };
                checkReady();
            });
        }
    };

    // ==============================================
    // 🔥 INICIALIZAÇÃO DA APLICAÇÃO
    // ==============================================

    async function initApp() {
        console.log('🚀 Inicializando App (Orquestrador) v2.0...');

        // 1. Proteger rotas
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

        // 4. Se estiver autenticado, sincroniza com payment
        if (isAuth) {
            await Sync.syncPayment();
        }

        // 5. Configurar UI global
        UI.setupModals();
        UI.updateNavbar();

        // 6. Configurar eventos globais
        Events.setup();

        // 7. Configurar navegação
        Router.setupNavigation();

        // 8. Marcar como inicializado
        State.initialized = true;

        console.log('✅ App (Orquestrador) v2.0 inicializado com sucesso!');
        console.log(`📌 Autenticado: ${isAuth}`);
        console.log(`📌 Página: ${Utils.getCurrentPath()}`);
        console.log(`📌 Admin: ${State.isAdmin}`);
        console.log(`📌 Premium: ${State.isPremium}`);
        console.log(`📌 Créditos: ${State.creditsDisplay}`);

        // 🔥 Dispara evento de app pronto
        window.dispatchEvent(new CustomEvent('appReady', { 
            detail: { 
                isAuthenticated: isAuth,
                user: State.user,
                credits: State.credits,
                isAdmin: State.isAdmin,
                isPremium: State.isPremium
            } 
        }));
    }

    // ==============================================
    // 🔥 SINCRONIZAÇÃO COM MÓDULOS EXTERNOS
    // ==============================================

    const Sync = {
        syncAuth: async () => {
            if (!window.appAuth) {
                console.warn('⚠️ Auth não inicializado.');
                return false;
            }

            try {
                const isAuth = await window.appAuth.checkToken();
                
                if (isAuth) {
                    const userData = window.appAuth.getCurrentUser ? window.appAuth.getCurrentUser() : {};
                    State.user = userData;
                    State.credits = userData.credits || 0;
                    State.isAdmin = userData.is_admin || false;
                    State.isPremium = userData.plan === 'premium_mensal' || userData.plan === 'PREMIUM_MENSAL';
                    
                    UI.updateNavbar();
                    Credits.startPolling();
                    Auth.startTokenCheck();
                    Auth.startSessionTimer();
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
                if (window.appAuth.loadPremiumStatus) {
                    await window.appAuth.loadPremiumStatus();
                }
                
                if (window.appAuth.startPremiumStatusPolling) {
                    window.appAuth.startPremiumStatusPolling(60000);
                }
            } catch (e) {
                console.warn('Erro ao sincronizar payment:', e);
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
        credits: Credits,
        auth: Auth,
        sync: Sync,
        
        // Funções utilitárias para outras páginas
        showNotification: Utils.showNotification,
        updateCredits: UI.updateCredits,
        updateNavbar: UI.updateNavbar,
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
        
        // Inicialização
        init: initApp
    };

    // ==============================================
    // 🔥 EXPORTAÇÕES GLOBAIS
    // ==============================================

    // Instância principal
    window.App = AppInstance;
    
    // 🔥 ALIASES PARA COMPATIBILIDADE (CORREÇÃO DO LOOP)
    window.app = AppInstance;
    window.autoAnalytics = AppInstance;

    // Aliases para funções específicas
    window.showNotification = Utils.showNotification;
    window.escapeHtml = Utils.escapeHtml;
    window.isAuthenticated = Utils.isAuthenticated;
    window.updateCreditsDisplay = UI.updateCredits;
    window.updateNavbar = UI.updateNavbar;
    window.navigateTo = Router.navigate;
    window.showLoading = UI.showLoading;
    window.hideLoading = UI.hideLoading;
    window.updateLoadingProgress = UI.updateLoadingProgress;
    window.goBack = Utils.goBack;
    window.getQueryParam = Utils.getQueryParam;

    // ==============================================
    // 🔥 INICIAR QUANDO O DOM ESTIVER PRONTO
    // ==============================================

    // 🔥 CORREÇÃO: Evita múltiplas inicializações
    if (window._appInitialized) {
        console.log('⚠️ App já inicializado, ignorando...');
    } else {
        window._appInitialized = true;
        
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initApp);
        } else {
            // 🔥 Pequeno delay para garantir que auth.js carregou
            setTimeout(initApp, 100);
        }
    }

    console.log('✅ app.js (Orquestrador) v2.0 carregado!');
    console.log('   📌 Aliases criados:');
    console.log('   - window.App (instância principal)');
    console.log('   - window.app (alias para compatibilidade)');
    console.log('   - window.autoAnalytics (alias para compatibilidade)');
    console.log('   📌 Funções globais disponíveis:');
    console.log('   - App.showNotification()');
    console.log('   - App.updateCredits()');
    console.log('   - App.navigate()');
    console.log('   - App.showLoading()');
    console.log('   - App.hideLoading()');
    console.log('   - App.isAuthenticated()');
    console.log('   - App.goBack()');
    console.log('   - App.getQueryParam()');

})();