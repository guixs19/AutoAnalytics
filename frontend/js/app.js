// frontend/js/app.js - ORQUESTRADOR CENTRAL - VERSÃO 2.0
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
        CREDITS_UPDATE_INTERVAL: 30000, // 30 segundos
        TOKEN_CHECK_INTERVAL: 60000, // 60 segundos
        SESSION_TIMEOUT: 15 * 60 * 1000, // 15 minutos de inatividade
        API_BASE: '/api'
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
        lastActivity: Date.now()
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
            if (window.toastr) {
                window.toastr[type](message);
                return;
            }
            const colors = {
                success: '#48bb78',
                error: '#f56565',
                warning: '#ed8936',
                info: '#4299e1'
            };
            const bgColor = colors[type] || colors.info;
            const notification = document.createElement('div');
            notification.style.cssText = `
                position: fixed; bottom: 20px; right: 20px; 
                background: white; border-left: 4px solid ${bgColor}; 
                padding: 12px 20px; border-radius: 8px; 
                box-shadow: 0 2px 10px rgba(0,0,0,0.1); 
                z-index: 10000; 
                animation: slideInRight 0.3s ease;
            `;
            notification.innerHTML = `<i class="fas fa-${type === 'success' ? 'check-circle' : 'info-circle'}" 
                style="color: ${bgColor}; margin-right: 8px;"></i>${message}`;
            document.body.appendChild(notification);
            setTimeout(() => notification.remove(), 5000);
        },

        isAuthenticated: () => {
            if (window.appAuth) {
                return typeof window.appAuth.isAuthenticated === 'function' 
                    ? window.appAuth.isAuthenticated() 
                    : window.appAuth.isAuthenticated;
            }
            return !!localStorage.getItem('access_token');
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
        reload: () => window.location.reload()
    };

    // ==============================================
    // 🔥 GERENCIADOR DE ROTAS / NAVEGAÇÃO
    // ==============================================

    const Router = {
        // Rotas protegidas (precisam de login)
        protectedRoutes: ['/', '/dashboard', '/planos', '/checkout'],
        
        // Rotas públicas (não precisam de login)
        publicRoutes: ['/login', '/register'],

        // Verifica se a rota atual é protegida
        isProtected: () => {
            const path = Utils.getCurrentPath();
            return Router.protectedRoutes.some(route => path === route || path.includes(route));
        },

        // Verifica se a rota atual é pública
        isPublic: () => {
            const path = Utils.getCurrentPath();
            return Router.publicRoutes.some(route => path === route || path.includes(route));
        },

        // Protege rotas - redireciona se não autenticado
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

        // Navegação segura entre páginas
        navigate: (url) => {
            // Verifica se a página destino precisa de login
            const isProtected = Router.protectedRoutes.some(route => url === route || url.includes(route));
            
            if (isProtected && !Utils.isAuthenticated()) {
                Utils.showNotification('Faça login para acessar esta página.', 'warning');
                Utils.redirectTo('/login');
                return;
            }

            Utils.redirectTo(url);
        },

        // 🔥 NOVO: Configura navegação após carregar
        setupNavigation: function() {
            // Clique em links com data-nav
            document.querySelectorAll('[data-nav]').forEach(el => {
                el.addEventListener('click', (e) => {
                    e.preventDefault();
                    const target = el.getAttribute('data-nav');
                    if (target) {
                        Router.navigate(target);
                    }
                });
            });

            // Clique em links com href começando com /
            document.querySelectorAll('a[href^="/"]').forEach(el => {
                // Não sobrescreve links com data-nav
                if (el.hasAttribute('data-nav')) return;
                // Não sobrescreve links com target="_blank"
                if (el.getAttribute('target') === '_blank') return;
                // Não sobrescreve links que são botões de logout
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
        // Atualiza a navbar completa
        updateNavbar: () => {
            const isAuth = Utils.isAuthenticated();
            
            // Mostra/esconde elementos autenticados
            document.querySelectorAll('.auth-required').forEach(el => {
                el.style.display = isAuth ? 'block' : 'none';
            });
            document.querySelectorAll('.guest-only').forEach(el => {
                el.style.display = isAuth ? 'none' : 'block';
            });

            if (isAuth && window.appAuth) {
                const userData = window.appAuth.getCurrentUser ? window.appAuth.getCurrentUser() : {};
                const name = userData.name || 'Usuário';
                
                // Atualiza nome
                document.querySelectorAll('.user-name').forEach(el => {
                    el.textContent = name;
                });

                // Atualiza workshop
                document.querySelectorAll('.workshop-name').forEach(el => {
                    el.textContent = userData.workshop_name || 'Oficina';
                });

                // Atualiza créditos
                UI.updateCredits();

                // Atualiza badges
                UI.updateAdminBadge();
                UI.updatePremiumBadge();
            }
        },

        // Atualiza display de créditos em TODAS as páginas
        updateCredits: () => {
            if (!window.appAuth) return;
            
            const display = window.appAuth.getCreditsDisplay ? window.appAuth.getCreditsDisplay() : '0';
            State.creditsDisplay = display;
            
            // Atualiza todos os elementos de créditos
            const selectors = [
                '.credits-display', '.user-credits', 
                '#creditsDisplay', '#creditsCount', '#uploadCredits',
                '.credits-badge span', '.credits-value'
            ];
            
            document.querySelectorAll(selectors.join(',')).forEach(el => {
                el.textContent = display;
            });

            // Dispara evento para outros módulos
            window.dispatchEvent(new CustomEvent('creditsUpdated', { 
                detail: { credits: State.credits, display: display } 
            }));
        },

        // Atualiza badge de administrador
        updateAdminBadge: () => {
            if (!window.appAuth) return;
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
        },

        // Atualiza badge de premium
        updatePremiumBadge: () => {
            if (!window.appAuth) return;
            const isPremium = window.appAuth.isPremium ? window.appAuth.isPremium() : false;
            State.isPremium = isPremium;
            
            document.querySelectorAll('.premium-badge, .premium-only').forEach(el => {
                el.style.display = isPremium ? 'inline-block' : 'none';
            });
        },

        // Mostra loading global
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
            }
        },

        // Esconde loading global
        hideLoading: () => {
            const overlay = document.getElementById('loadingOverlay');
            if (overlay) {
                overlay.classList.remove('show');
            }
        },

        // Atualiza progresso do loading
        updateLoadingProgress: (percent, message = null) => {
            const progress = document.getElementById('loadingProgressBar');
            const text = document.getElementById('loadingText');
            
            if (progress) progress.style.width = `${Math.min(100, percent)}%`;
            if (message && text) text.textContent = message;
        },

        // Configura modais globais
        setupModals: () => {
            // Fechar modais com ESC
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') {
                    document.querySelectorAll('.modal.show').forEach(modal => {
                        const instance = bootstrap.Modal.getInstance(modal);
                        if (instance) instance.hide();
                    });
                }
            });

            // Fechar modais clicando fora
            document.querySelectorAll('.modal').forEach(modal => {
                modal.addEventListener('click', (e) => {
                    if (e.target === modal) {
                        const instance = bootstrap.Modal.getInstance(modal);
                        if (instance) instance.hide();
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
            // Toggle de senha (em todas as páginas)
            document.querySelectorAll('.password-toggle').forEach(btn => {
                btn.addEventListener('click', () => {
                    const targetId = btn.getAttribute('data-target');
                    const field = document.getElementById(targetId);
                    if (field) {
                        const icon = btn.querySelector('i');
                        if (field.type === 'password') {
                            field.type = 'text';
                            icon.classList.remove('fa-eye-slash');
                            icon.classList.add('fa-eye');
                        } else {
                            field.type = 'password';
                            icon.classList.remove('fa-eye');
                            icon.classList.add('fa-eye-slash');
                        }
                    }
                });
            });

            // Logout (em todas as páginas)
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

            // Navegação por data-nav
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

            // 🔥 Eventos customizados
            window.addEventListener('creditsUpdated', (e) => {
                UI.updateCredits();
            });

            window.addEventListener('authReady', (e) => {
                UI.updateNavbar();
            });

            window.addEventListener('premiumStatusUpdated', (e) => {
                UI.updatePremiumBadge();
                UI.updateCredits();
            });

            // 🔥 NOVO: Handlers de erros globais
            window.addEventListener('unhandledrejection', (event) => {
                console.error('❌ Erro não tratado (Promise):', event.reason);
                Utils.showNotification('Erro inesperado. Tente novamente.', 'error');
            });

            window.addEventListener('error', (event) => {
                console.error('❌ Erro global:', event.error || event.message);
                // Não mostra para erros de rede (evita spam)
                if (event.target && event.target.tagName === 'SCRIPT') {
                    return;
                }
                Utils.showNotification('Erro na aplicação. Recarregue a página se persistir.', 'error');
            });

            // 🔥 NOVO: Rastrear atividade do usuário para timeout
            ['click', 'mousemove', 'keydown', 'scroll', 'touchstart'].forEach(event => {
                document.addEventListener(event, () => {
                    State.lastActivity = Date.now();
                    Auth.resetSessionTimer();
                });
            });
        }
    };

    // ==============================================
    // 🔥 SINCRONIZAÇÃO COM MÓDULOS EXTERNOS
    // ==============================================

    const Sync = {
        // Sincroniza com auth.js
        syncAuth: async () => {
            if (!window.appAuth) {
                console.warn('⚠️ Auth não inicializado. Aguardando...');
                return false;
            }

            const isAuth = await window.appAuth.checkToken();
            
            if (isAuth) {
                const userData = window.appAuth.getCurrentUser ? window.appAuth.getCurrentUser() : {};
                State.user = userData;
                State.credits = userData.credits || 0;
                State.isAdmin = userData.is_admin || false;
                State.isPremium = userData.plan === 'premium_mensal' || userData.plan === 'PREMIUM_MENSAL';
                
                // Atualiza UI
                UI.updateNavbar();
                
                // Inicia monitoramento de créditos
                Credits.startPolling();
                
                // Inicia verificação de token
                Auth.startTokenCheck();
                
                // Inicia timer de sessão
                Auth.startSessionTimer();
            }

            return isAuth;
        },

        // Sincroniza com payment.js
        syncPayment: async () => {
            if (!window.appAuth) return;
            
            // Carrega status premium
            if (window.appAuth.loadPremiumStatus) {
                await window.appAuth.loadPremiumStatus();
            }
            
            // Inicia polling de status premium
            if (window.appAuth.startPremiumStatusPolling) {
                window.appAuth.startPremiumStatusPolling(60000);
            }
        }
    };

    // ==============================================
    // 🔥 GERENCIADOR DE CRÉDITOS
    // ==============================================

    const Credits = {
        // Carrega créditos do usuário
        load: async () => {
            if (window.appAuth && window.appAuth.loadUserCredits) {
                await window.appAuth.loadUserCredits();
                UI.updateCredits();
            }
        },

        // Inicia polling de créditos
        startPolling: () => {
            // Carrega imediatamente
            Credits.load();
            
            // Atualiza periodicamente
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
        // Timer de sessão
        sessionTimeout: null,

        // Inicia timer de sessão inativa
        startSessionTimer: () => {
            if (Auth.sessionTimeout) {
                clearTimeout(Auth.sessionTimeout);
                Auth.sessionTimeout = null;
            }

            // Se não estiver autenticado, não inicia timer
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

        // Reseta timer de sessão
        resetSessionTimer: () => {
            // Se não estiver autenticado, não reseta
            if (!Utils.isAuthenticated()) return;
            
            // Só reseta se já tiver passado 30 segundos da última atividade
            const now = Date.now();
            if (now - State.lastActivity > 30000) {
                Auth.startSessionTimer();
            }
        },

        // Verifica token periodicamente
        startTokenCheck: () => {
            // Verifica imediatamente
            Auth.checkRenewal();
            
            // Verifica periodicamente
            setInterval(() => {
                Auth.checkRenewal();
            }, CONFIG.TOKEN_CHECK_INTERVAL);
            
            console.log(`⏰ Verificação de token: ${CONFIG.TOKEN_CHECK_INTERVAL/1000}s`);
        },

        // Verifica se precisa renovar token
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
                            // Reseta timer de sessão
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
                    // Token válido, reseta timer
                    Auth.resetSessionTimer();
                }
            } catch (error) {
                console.warn('Erro ao verificar token:', error);
            }
        }
    };

    // ==============================================
    // 🔥 INICIALIZAÇÃO DA APLICAÇÃO
    // ==============================================

    async function initApp() {
        console.log('🚀 Inicializando App (Orquestrador) v2.0...');

        // 1. Proteger rotas (redireciona se necessário)
        if (!Router.protect()) {
            return; // Já foi redirecionado
        }

        // 2. Sincronizar com auth.js
        const isAuth = await Sync.syncAuth();

        // 3. Se estiver autenticado, sincroniza com payment
        if (isAuth) {
            await Sync.syncPayment();
        }

        // 4. Configurar UI global
        UI.setupModals();
        UI.updateNavbar();

        // 5. Configurar eventos globais
        Events.setup();

        // 6. Configurar navegação
        Router.setupNavigation();

        // 7. Marcar como inicializado
        State.initialized = true;

        console.log('✅ App (Orquestrador) v2.0 inicializado com sucesso!');
        console.log(`📌 Autenticado: ${isAuth}`);
        console.log(`📌 Página: ${Utils.getCurrentPath()}`);
        console.log(`📌 Admin: ${State.isAdmin}`);
        console.log(`📌 Premium: ${State.isPremium}`);
        console.log(`📌 Créditos: ${State.creditsDisplay}`);
        console.log(`📌 Timeout sessão: ${CONFIG.SESSION_TIMEOUT/60000} minutos`);

        // Dispara evento de app pronto
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
    // 🔥 EXPORTA FUNÇÕES GLOBAIS
    // ==============================================

    // Instância principal
    window.App = {
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
        
        // Inicialização
        init: initApp
    };

    // Aliases para compatibilidade com código existente
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

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initApp);
    } else {
        initApp();
    }

    console.log('✅ app.js (Orquestrador) v2.0 carregado!');
    console.log('   📌 Funções globais disponíveis:');
    console.log('   - App.showNotification()');
    console.log('   - App.updateCredits()');
    console.log('   - App.navigate()');
    console.log('   - App.showLoading()');
    console.log('   - App.hideLoading()');
    console.log('   - App.isAuthenticated()');
    console.log('   - App.goBack()');
    console.log('   - App.getQueryParam()');
    console.log('   - window.App (instância completa)');

})();