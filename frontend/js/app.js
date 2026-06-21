// frontend/js/app.js - MÓDULO DE APLICAÇÃO PRINCIPAL
/**
 * AutoAnalytics - Módulo Principal da Aplicação
 * 
 * 🔥 IMPORTANTE: Este arquivo NÃO redefine a classe Auth!
 * ✅ Apenas estende funcionalidades e configura a aplicação
 * ✅ Compatível com auth.js, dashboard.js e payment.js
 * 
 * FLUXO: 
 *   1. auth.js carrega primeiro (define window.appAuth)
 *   2. app.js carrega depois (configura UI, eventos, etc)
 *   3. dashboard.js carrega por último (funcionalidades específicas)
 */

(function() {
    'use strict';

    console.log('🚀 Inicializando App...');

    // ==============================================
    // 🔥 CONFIGURAÇÕES GLOBAIS
    // ==============================================

    const CONFIG = {
        MAX_FILES: 3,
        MAX_FILE_SIZE_KB: 200,
        CREDITS_UPDATE_INTERVAL: 30000, // 30 segundos
        TOKEN_CHECK_INTERVAL: 60000, // 60 segundos
        API_BASE: '/api'
    };

    // ==============================================
    // 🔥 FUNÇÕES DE UTILIDADE
    // ==============================================

    const Utils = {
        // Formatar data
        formatDate: (date) => {
            const d = new Date(date);
            return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR');
        },

        // Escape HTML
        escapeHtml: (text) => {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        },

        // Mostrar notificação
        showNotification: (message, type = 'info') => {
            if (window.toastr) {
                window.toastr[type](message);
                return;
            }
            // Fallback
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

        // Verificar autenticação
        isAuthenticated: () => {
            if (window.appAuth) {
                return typeof window.appAuth.isAuthenticated === 'function' 
                    ? window.appAuth.isAuthenticated() 
                    : window.appAuth.isAuthenticated;
            }
            return !!localStorage.getItem('access_token');
        },

        // Redirecionar para login
        redirectToLogin: () => {
            if (!window.location.pathname.includes('/login')) {
                window.location.href = '/login';
            }
        }
    };

    // ==============================================
    // 🔥 FUNÇÕES DE UI
    // ==============================================

    const UI = {
        // Atualizar nome do usuário
        updateUserName: () => {
            if (!window.appAuth) return;
            const userData = window.appAuth.getCurrentUser ? window.appAuth.getCurrentUser() : {};
            const name = userData.name || 'Usuário';
            
            document.querySelectorAll('.user-name').forEach(el => {
                el.textContent = name;
            });
        },

        // Atualizar créditos
        updateCredits: () => {
            if (!window.appAuth) return;
            const display = window.appAuth.getCreditsDisplay ? window.appAuth.getCreditsDisplay() : '0';
            
            document.querySelectorAll('.credits-display, .user-credits, #creditsDisplay, #creditsCount, #uploadCredits').forEach(el => {
                el.textContent = display;
            });
        },

        // Atualizar status de admin
        updateAdminUI: () => {
            if (!window.appAuth) return;
            const isAdmin = window.appAuth.isAdmin ? window.appAuth.isAdmin() : false;
            
            document.querySelectorAll('.admin-only').forEach(el => {
                el.style.display = isAdmin ? 'block' : 'none';
            });
        },

        // Atualizar status premium
        updatePremiumUI: () => {
            if (!window.appAuth) return;
            const isPremium = window.appAuth.isPremium ? window.appAuth.isPremium() : false;
            
            document.querySelectorAll('.premium-only').forEach(el => {
                el.style.display = isPremium ? 'block' : 'none';
            });
        },

        // Mostrar loading
        showLoading: (message = 'Processando...') => {
            const overlay = document.getElementById('loadingOverlay');
            if (overlay) {
                const text = document.getElementById('loadingText');
                if (text) text.textContent = message;
                overlay.classList.add('show');
            }
        },

        // Esconder loading
        hideLoading: () => {
            const overlay = document.getElementById('loadingOverlay');
            if (overlay) {
                overlay.classList.remove('show');
            }
        }
    };

    // ==============================================
    // 🔥 FUNÇÕES DE AUTENTICAÇÃO
    // ==============================================

    const AuthHelpers = {
        // Verificar token ao carregar página
        checkAuth: async () => {
            if (!window.appAuth) {
                console.warn('⚠️ Auth não inicializado');
                return false;
            }

            const isAuth = await window.appAuth.checkToken();
            
            if (!isAuth && !window.location.pathname.includes('/login')) {
                Utils.redirectToLogin();
                return false;
            }

            if (isAuth) {
                UI.updateUserName();
                UI.updateCredits();
                UI.updateAdminUI();
                UI.updatePremiumUI();
            }

            return isAuth;
        },

        // Configurar logout
        setupLogout: () => {
            const logoutBtn = document.getElementById('logoutBtn');
            if (logoutBtn && window.appAuth) {
                logoutBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    if (window.appAuth.logout) {
                        window.appAuth.logout();
                    } else {
                        localStorage.clear();
                        window.location.href = '/login';
                    }
                });
            }
        }
    };

    // ==============================================
    // 🔥 FUNÇÕES DE NAVEGAÇÃO
    // ==============================================

    const Navigation = {
        // Configurar navegação
        setup: () => {
            // Links do menu
            document.querySelectorAll('[data-nav]').forEach(el => {
                el.addEventListener('click', (e) => {
                    e.preventDefault();
                    const target = el.getAttribute('data-nav');
                    if (target) {
                        window.location.href = target;
                    }
                });
            });

            // Voltar
            document.querySelectorAll('.btn-back').forEach(el => {
                el.addEventListener('click', () => {
                    window.history.back();
                });
            });
        }
    };

    // ==============================================
    // 🔥 FUNÇÕES DE CRÉDITOS
    // ==============================================

    const Credits = {
        // Carregar créditos
        load: async () => {
            if (window.appAuth && window.appAuth.loadUserCredits) {
                await window.appAuth.loadUserCredits();
                UI.updateCredits();
            }
        },

        // Configurar atualização periódica
        setupPolling: () => {
            // Atualizar créditos a cada 30 segundos
            setInterval(() => {
                Credits.load();
            }, CONFIG.CREDITS_UPDATE_INTERVAL);
            
            console.log(`⏰ Atualização de créditos: ${CONFIG.CREDITS_UPDATE_INTERVAL/1000}s`);
        }
    };

    // ==============================================
    // 🔥 FUNÇÕES DE PAYMENT (PARA PAYMENT.JS)
    // ==============================================

    const PaymentHelpers = {
        // Configurar status premium
        setupPremium: () => {
            if (window.appAuth && window.appAuth.loadPremiumStatus) {
                // Carregar status inicial
                window.appAuth.loadPremiumStatus();
                
                // Iniciar polling
                if (window.appAuth.startPremiumStatusPolling) {
                    window.appAuth.startPremiumStatusPolling(60000);
                }
            }
        },

        // Configurar botão de crédito diário
        setupDailyCredit: () => {
            const btn = document.getElementById('receiveDailyCreditBtn');
            if (btn && window.appAuth && window.appAuth.receiveDailyCredit) {
                btn.addEventListener('click', async () => {
                    btn.disabled = true;
                    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
                    
                    const result = await window.appAuth.receiveDailyCredit();
                    
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fas fa-gift"></i> Receber Crédito';
                    
                    if (result && result.success) {
                        UI.updateCredits();
                    }
                });
            }
        }
    };

    // ==============================================
    // 🔥 INICIALIZAÇÃO
    // ==============================================

    async function initApp() {
        console.log('🚀 Inicializando App...');

        // 1. Verificar autenticação
        await AuthHelpers.checkAuth();

        // 2. Configurar logout
        AuthHelpers.setupLogout();

        // 3. Configurar navegação
        Navigation.setup();

        // 4. Configurar créditos
        Credits.setupPolling();

        // 5. Configurar premium (se disponível)
        if (window.appAuth) {
            PaymentHelpers.setupPremium();
            PaymentHelpers.setupDailyCredit();
        }

        // 6. Configurar eventos de UI
        setupUIEvents();

        console.log('✅ App inicializado com sucesso!');
        console.log(`📌 Autenticado: ${Utils.isAuthenticated()}`);
        console.log(`📌 Página: ${window.location.pathname}`);
    }

    // ==============================================
    // 🔥 EVENTOS DE UI
    // ==============================================

    function setupUIEvents() {
        // Toggle de senha
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

        // Fechar modais com ESC
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                document.querySelectorAll('.modal.show').forEach(modal => {
                    const instance = bootstrap.Modal.getInstance(modal);
                    if (instance) instance.hide();
                });
            }
        });

        // Evento de créditos atualizados (do auth.js)
        window.addEventListener('creditsUpdated', (e) => {
            UI.updateCredits();
        });

        // Evento de status premium atualizado (do auth.js)
        window.addEventListener('premiumStatusUpdated', (e) => {
            UI.updatePremiumUI();
        });

        // Evento de auth pronto (disparado pelo auth.js)
        window.addEventListener('authReady', (e) => {
            UI.updateUserName();
            UI.updateCredits();
            UI.updateAdminUI();
            UI.updatePremiumUI();
        });
    }

    // ==============================================
    // 🔥 EXPORTA FUNÇÕES GLOBAIS (para outros módulos)
    // ==============================================

    // Funções de utilidade
    window.Utils = Utils;
    window.UI = UI;
    window.Credits = Credits;

    // Funções específicas para dashboard.js
    window.showNotification = Utils.showNotification;
    window.escapeHtml = Utils.escapeHtml;
    window.isAuthenticated = Utils.isAuthenticated;

    // ==============================================
    // 🔥 INICIAR QUANDO O DOM ESTIVER PRONTO
    // ==============================================

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initApp);
    } else {
        initApp();
    }

    console.log('✅ app.js carregado!');
    console.log('   📌 Funções disponíveis:');
    console.log('   - Utils.showNotification()');
    console.log('   - UI.updateCredits()');
    console.log('   - Credits.load()');
    console.log('   - isAuthenticated()');

})();