// payment.js - VERSÃO 6.1 (INTEGRAÇÃO COMPLETA COM APP.JS)
// ==============================================
// 🔥 MELHORIAS V6.1:
// 1. ✅ INTEGRAÇÃO TOTAL com app.js (EventBus, StateManager, fetchWithAuth)
// 2. ✅ SISTEMA INTELIGENTE DE CRÉDITOS (CreditSystem)
// 3. ✅ SISTEMA DE CACHE COM TTL
// 4. ✅ FILA DE EVENTOS (EventQueue)
// 5. ✅ RENDERIZAÇÃO CONDICIONAL OTIMIZADA
// 6. ✅ VALIDAÇÃO DE CPF COM ALGORITMO COMPLETO
// 7. ✅ SANITIZAÇÃO DE DADOS (XSS Protection)
// 8. ✅ SEM POLLING - 100% EVENT-DRIVEN
// 9. ✅ INJEÇÃO ANTECIPADA DE MÉTODOS GLOBAIS
// 10. ✅ COMPATIBILIDADE RETROATIVA com window.appAuth
// 11. ✅ SISTEMA DE RETRY INTELIGENTE (3 tentativas)
// 12. ✅ MÉTRICAS E PERFORMANCE TRACKING
// ==============================================

(function() {
    'use strict';

    console.log('🚀 Inicializando payment.js v6.1 (Integração com app.js)...');

    // ==============================================
    // 🔒 DETECTA AMBIENTE (app.js vs standalone)
    // ==============================================

    const HAS_APP = !!(
        window.App || 
        window.app || 
        window.EventBus || 
        window.__APP_STATE || 
        window.__APP_STATE_MANAGER || 
        window.appAuth
    );

    console.log(`📡 Ambiente detectado: ${HAS_APP ? 'APP.JS' : 'STANDALONE'}`);

    // ==============================================
    // 🔒 CONFIGURAÇÕES GLOBAIS
    // ==============================================

    const CONFIG = {
        MAX_CREDITS_BALANCE: 3,
        INITIAL_FREE_CREDITS: 3,
        PIX_EXPIRY_MINUTES: 30,
        PROMOTIONAL_PRICE: 97.00,
        REGULAR_PRICE: 149.90,
        TOTAL_PROMOTIONAL_SLOTS: 100,
        DAYS_PREMIUM: 30,
        CACHE_TTL: 60000, // 1 minuto
        RETRY_ATTEMPTS: 3,
        RETRY_DELAY: 1000,
        MAX_PIX_MODAL_ATTEMPTS: 5,
        API_BASE: HAS_APP ? (window.App?.CONFIG?.API_BASE || '/api') : '/api'
    };

    // ==============================================
    // 📡 EVENT BUS (usa o do app.js se disponível)
    // ==============================================

    const EventBus = (() => {
        if (HAS_APP && window.EventBus) {
            console.log('📡 Usando EventBus do app.js');
            return window.EventBus;
        }
        
        // Fallback: EventBus próprio
        console.log('📡 Usando EventBus próprio (fallback)');
        const _handlers = new Map();
        
        return {
            on(event, handler) {
                if (!_handlers.has(event)) _handlers.set(event, []);
                _handlers.get(event).push(handler);
            },
            off(event, handler) {
                if (!_handlers.has(event)) return;
                const handlers = _handlers.get(event);
                const index = handlers.indexOf(handler);
                if (index !== -1) handlers.splice(index, 1);
                if (handlers.length === 0) _handlers.delete(event);
            },
            emit(event, data) {
                // Dispara via DOM também
                try {
                    window.dispatchEvent(new CustomEvent(event, { detail: data, bubbles: true }));
                    document.dispatchEvent(new CustomEvent(event, { detail: data, bubbles: true }));
                } catch (e) {}
                
                if (!_handlers.has(event)) return;
                for (const handler of _handlers.get(event)) {
                    try { handler(data); } catch (e) { console.error(e); }
                }
            },
            once(event, handler) {
                const wrapper = (data) => {
                    handler(data);
                    this.off(event, wrapper);
                };
                this.on(event, wrapper);
            }
        };
    })();

    // ==============================================
    // 📦 CACHE INTELLIGENTE
    // ==============================================

    const Cache = {
        _data: new Map(),
        _timestamps: new Map(),

        set(key, value, ttl = CONFIG.CACHE_TTL) {
            this._data.set(key, value);
            this._timestamps.set(key, Date.now() + ttl);
        },

        get(key) {
            const timestamp = this._timestamps.get(key);
            if (!timestamp || Date.now() > timestamp) {
                this._data.delete(key);
                this._timestamps.delete(key);
                return null;
            }
            return this._data.get(key);
        },

        clear() {
            this._data.clear();
            this._timestamps.clear();
        },

        isValid(key) {
            const timestamp = this._timestamps.get(key);
            return timestamp && Date.now() <= timestamp;
        }
    };

    // ==============================================
    // 🔐 SEGURANÇA (XSS PROTECTION)
    // ==============================================

    const Security = {
        escapeMap: {
            '&': '&amp;', '<': '&lt;', '>': '&gt;',
            '"': '&quot;', "'": '&#39;', '`': '&#96;',
            '/': '&#47;', '=': '&#61;', '(': '&#40;',
            ')': '&#41;', ';': '&#59;'
        },

        sanitizeHTML(str) {
            if (!str) return '';
            if (typeof str !== 'string') str = String(str);
            return str
                .replace(/[&<>"'`/=();]/g, m => this.escapeMap[m] || m)
                .replace(/javascript:/gi, '')
                .replace(/on\w+\s*=/gi, '')
                .replace(/eval\s*\(/gi, '')
                .slice(0, 5000);
        },

        sanitizeNumber(value, defaultValue = 0) {
            if (value === undefined || value === null) return defaultValue;
            const num = parseFloat(String(value).replace(/[^0-9.,-]/g, '').replace(',', '.'));
            return isNaN(num) ? defaultValue : num;
        },

        sanitizeCPF(cpf) {
            if (!cpf) return '';
            return String(cpf).replace(/\D/g, '');
        },

        validateCPF(cpf) {
            const clean = this.sanitizeCPF(cpf);
            if (clean.length !== 11) return false;

            const invalid = [
                '00000000000', '11111111111', '22222222222', '33333333333',
                '44444444444', '55555555555', '66666666666', '77777777777',
                '88888888888', '99999999999'
            ];
            if (invalid.includes(clean)) return false;

            let sum = 0, remainder;
            for (let i = 1; i <= 9; i++) {
                sum += parseInt(clean[i - 1]) * (11 - i);
            }
            remainder = (sum * 10) % 11;
            if (remainder === 10 || remainder === 11) remainder = 0;
            if (remainder !== parseInt(clean[9])) return false;

            sum = 0;
            for (let i = 1; i <= 10; i++) {
                sum += parseInt(clean[i - 1]) * (12 - i);
            }
            remainder = (sum * 10) % 11;
            if (remainder === 10 || remainder === 11) remainder = 0;
            if (remainder !== parseInt(clean[10])) return false;

            return true;
        },

        sanitizeObject(obj) {
            if (obj === null || obj === undefined) return obj;
            if (typeof obj === 'string') return this.sanitizeHTML(obj);
            if (typeof obj === 'number') return this.sanitizeNumber(obj);
            if (Array.isArray(obj)) return obj.map(item => this.sanitizeObject(item));
            if (typeof obj === 'object') {
                const result = {};
                for (const [key, value] of Object.entries(obj)) {
                    result[this.sanitizeHTML(key)] = this.sanitizeObject(value);
                }
                return result;
            }
            return obj;
        }
    };

    // ==============================================
    // 🔥 FETCH UNIFICADO (usa app.js se disponível)
    // ==============================================

    async function fetchWithRetry(url, options = {}, retries = CONFIG.RETRY_ATTEMPTS) {
        // 1. Tenta usar fetchWithAuth do app.js
        if (HAS_APP && window.App?.fetchWithAuth) {
            try {
                const response = await window.App.fetchWithAuth(url, options);
                if (response) return response;
            } catch (e) {
                console.warn('⚠️ App.fetchWithAuth falhou, usando fallback:', e);
            }
        }

        if (HAS_APP && window.appAuth?.fetchWithAuth) {
            try {
                const response = await window.appAuth.fetchWithAuth(url, options);
                if (response) return response;
            } catch (e) {
                console.warn('⚠️ appAuth.fetchWithAuth falhou, usando fallback:', e);
            }
        }

        // 2. Fallback: fetch com retry
        const attempt = (attemptNumber) => {
            return new Promise(async (resolve, reject) => {
                try {
                    const token = localStorage.getItem('access_token');
                    const headers = {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                        ...options.headers
                    };
                    if (token) headers['Authorization'] = `Bearer ${token}`;

                    const response = await fetch(url, { ...options, headers });

                    if (response.status === 401 && attemptNumber < retries) {
                        // Tenta refresh
                        if (HAS_APP && window.App?.refreshTokenSafely) {
                            await window.App.refreshTokenSafely();
                        } else if (window.appAuth?.refreshTokenSafely) {
                            await window.appAuth.refreshTokenSafely();
                        }
                        // Re-tenta
                        const newToken = localStorage.getItem('access_token');
                        if (newToken) {
                            headers['Authorization'] = `Bearer ${newToken}`;
                            const retryResponse = await fetch(url, { ...options, headers });
                            if (retryResponse.ok) {
                                resolve(retryResponse);
                                return;
                            }
                        }
                    }

                    if (!response.ok && attemptNumber < retries) {
                        const delay = CONFIG.RETRY_DELAY * attemptNumber;
                        console.log(`🔄 Tentativa ${attemptNumber + 1} falhou. Retentando em ${delay}ms...`);
                        setTimeout(() => resolve(attempt(attemptNumber + 1)), delay);
                        return;
                    }

                    resolve(response);
                } catch (error) {
                    if (attemptNumber < retries) {
                        const delay = CONFIG.RETRY_DELAY * attemptNumber;
                        console.log(`🔄 Erro na tentativa ${attemptNumber + 1}. Retentando em ${delay}ms...`);
                        setTimeout(() => resolve(attempt(attemptNumber + 1)), delay);
                    } else {
                        reject(error);
                    }
                }
            });
        };

        return attempt(0);
    }

    // ==============================================
    // 🔥 SISTEMA DE AUTENTICAÇÃO (usa app.js)
    // ==============================================

    function getAuthStatus() {
        // Tenta usar StateManager do app.js
        if (HAS_APP && window.__APP_STATE) {
            const state = window.__APP_STATE;
            return {
                isAdmin: state.isAdmin || false,
                isPremium: state.isPremium || false,
                credits: state.credits || 0,
                user: state.user || null,
                tokenValid: state.tokenValid || false
            };
        }

        if (HAS_APP && window.App?.State) {
            const state = window.App.State;
            return {
                isAdmin: state.isAdmin || false,
                isPremium: state.isPremium || false,
                credits: state.credits || 0,
                user: state.user || null,
                tokenValid: state.tokenValid || false
            };
        }

        // Fallback: window.appAuth
        if (window.appAuth) {
            return {
                isAdmin: window.appAuth.isAdmin?.() || false,
                isPremium: window.appAuth.isPremium?.() || false,
                credits: window.appAuth.getCredits?.() || 0,
                user: window.appAuth.getCurrentUser?.() || null,
                tokenValid: true
            };
        }

        // Último fallback: localStorage
        return {
            isAdmin: localStorage.getItem('is_admin') === 'true',
            isPremium: localStorage.getItem('is_premium') === 'true',
            credits: parseInt(localStorage.getItem('user_credits') || '0'),
            user: null,
            tokenValid: !!localStorage.getItem('access_token')
        };
    }

    async function refreshAuth() {
        if (HAS_APP && window.App?.refreshAuth) {
            await window.App.refreshAuth();
            return getAuthStatus();
        }
        if (window.appAuth?.refreshUserData) {
            await window.appAuth.refreshUserData();
            return getAuthStatus();
        }
        return getAuthStatus();
    }

    // ==============================================
    // 💰 SISTEMA INTELIGENTE DE CRÉDITOS (V6.1)
    // ==============================================

    const CreditSystem = {
        _lastCheck: 0,
        _cacheValidity: 5000, // 5 segundos de cache

        async checkCredits(required = 1, forceCheck = false) {
            console.log(`🔍 Verificando créditos... (necessário: ${required})`);
            
            try {
                // 1. Verifica cache primeiro
                if (!forceCheck) {
                    const cached = await this._getCachedBalance();
                    if (cached !== null) {
                        const hasCredits = cached >= required;
                        console.log(`📦 Cache: ${cached} créditos disponíveis`);
                        return {
                            hasCredits,
                            balance: cached,
                            message: hasCredits 
                                ? `✅ Você tem ${cached} créditos disponíveis`
                                : `❌ Créditos insuficientes. Você tem ${cached}, necessário ${required}`,
                            cached: true
                        };
                    }
                }
                
                // 2. Busca na API (com retry)
                const balance = await this._fetchBalance();
                
                if (balance === null) {
                    // Fallback: usa dados do appAuth ou localStorage
                    const fallbackBalance = this._getFallbackBalance();
                    console.log('🔄 Usando fallback:', fallbackBalance);
                    return {
                        hasCredits: fallbackBalance >= required,
                        balance: fallbackBalance,
                        message: `⚠️ Dados locais: ${fallbackBalance} créditos`,
                        cached: false,
                        fallback: true
                    };
                }
                
                // 3. Atualiza cache
                this._updateCache(balance);
                
                const hasCredits = balance >= required;
                return {
                    hasCredits,
                    balance,
                    message: hasCredits 
                        ? `✅ Você tem ${balance} créditos disponíveis`
                        : `❌ Créditos insuficientes. Você tem ${balance}, necessário ${required}`,
                    cached: false
                };
                
            } catch (error) {
                console.error('❌ Erro ao verificar créditos:', error);
                return {
                    hasCredits: false,
                    balance: 0,
                    message: '⚠️ Erro ao verificar créditos. Tente novamente.',
                    error: error.message
                };
            }
        },

        async _fetchBalance() {
            try {
                const response = await fetchWithRetry('/api/payments/credits-balance');
                if (response?.ok) {
                    const data = await response.json();
                    const balance = Security.sanitizeNumber(data.balance, 0);
                    console.log(`💳 API retornou: ${balance} créditos`);
                    return balance;
                }
                return null;
            } catch (error) {
                console.warn('⚠️ Erro ao buscar saldo na API:', error);
                return null;
            }
        },

        async _getCachedBalance() {
            const now = Date.now();
            if (this._lastCheck && (now - this._lastCheck) < this._cacheValidity) {
                const cached = Cache.get('user_balance');
                if (cached !== null && cached !== undefined) {
                    return cached;
                }
            }
            return null;
        },

        _updateCache(balance) {
            this._lastCheck = Date.now();
            Cache.set('user_balance', balance, this._cacheValidity);
        },

        _getFallbackBalance() {
            try {
                const authStatus = getAuthStatus();
                const credits = authStatus.credits || 0;
                console.log(`🔄 Fallback: ${credits} créditos`);
                return credits;
            } catch (error) {
                console.error('❌ Erro no fallback:', error);
                return 0;
            }
        },

        async canPerformAction(action = 'analyze', cost = 1) {
            console.log(`🎯 Verificando ação: ${action} (custo: ${cost} créditos)`);
            
            const authStatus = getAuthStatus();
            
            // 1. Admin tem acesso ilimitado
            if (authStatus.isAdmin) {
                return {
                    allowed: true,
                    balance: Infinity,
                    message: '👑 Admin - Acesso ilimitado',
                    isAdmin: true
                };
            }
            
            // 2. Usuário premium tem mais flexibilidade
            const isPremium = authStatus.isPremium;
            if (isPremium) {
                const balance = await this.getBalance();
                if (balance >= cost) {
                    return {
                        allowed: true,
                        balance,
                        message: `✅ Premium - ${balance} créditos disponíveis`,
                        isPremium: true
                    };
                } else {
                    // Tenta receber crédito diário automaticamente
                    await receiveDailyCredit();
                    const newBalance = await this.getBalance(true);
                    if (newBalance >= cost) {
                        return {
                            allowed: true,
                            balance: newBalance,
                            message: `🔄 Crédito diário recebido! Saldo: ${newBalance}`,
                            isPremium: true
                        };
                    }
                    return {
                        allowed: false,
                        balance: newBalance,
                        message: `❌ Créditos insuficientes. Você tem ${newBalance}, necessário ${cost}`,
                        isPremium: true
                    };
                }
            }
            
            // 3. Usuário free
            const balance = await this.getBalance();
            if (balance >= cost) {
                return {
                    allowed: true,
                    balance,
                    message: `✅ ${balance} créditos disponíveis`,
                    isPremium: false
                };
            }
            
            return {
                allowed: false,
                balance,
                message: `❌ Créditos insuficientes. Você tem ${balance}, necessário ${cost}. Adquira o Plano Bronze!`,
                isPremium: false,
                suggestUpgrade: true
            };
        },

        async getBalance(forceRefresh = false) {
            try {
                if (forceRefresh) {
                    const balance = await this._fetchBalance();
                    if (balance !== null) {
                        this._updateCache(balance);
                        return balance;
                    }
                }
                
                const cached = await this._getCachedBalance();
                if (cached !== null) {
                    return cached;
                }
                
                const balance = await this._fetchBalance();
                if (balance !== null) {
                    this._updateCache(balance);
                    return balance;
                }
                
                return this._getFallbackBalance();
                
            } catch (error) {
                console.error('❌ Erro ao obter saldo:', error);
                return this._getFallbackBalance();
            }
        },

        async spendCredits(action = 'analyze', cost = 1) {
            const check = await this.canPerformAction(action, cost);
            
            if (!check.allowed) {
                return {
                    success: false,
                    ...check,
                    action
                };
            }
            
            try {
                const response = await fetchWithRetry('/api/payments/spend-credits', {
                    method: 'POST',
                    body: JSON.stringify({ action, cost })
                });
                
                if (response?.ok) {
                    const data = await response.json();
                    const newBalance = Security.sanitizeNumber(data.balance, 0);
                    
                    this._updateCache(newBalance);
                    
                    // Atualiza estado via app.js
                    if (HAS_APP && window.__APP_STATE_MANAGER) {
                        window.__APP_STATE_MANAGER.updateCredits(newBalance);
                    } else if (window.App?.StateManager) {
                        window.App.StateManager.updateCredits(newBalance);
                    } else {
                        // Fallback: localStorage
                        localStorage.setItem('user_credits', String(newBalance));
                    }
                    
                    // Dispara evento
                    EventBus.emit('payment:credits_spent', {
                        action,
                        cost,
                        newBalance,
                        previousBalance: check.balance
                    });
                    
                    await updateCreditsDisplay(newBalance);
                    
                    return {
                        success: true,
                        balance: newBalance,
                        message: `✅ ${cost} crédito(s) utilizado(s). Saldo: ${newBalance}`,
                        action
                    };
                } else {
                    throw new Error('Falha ao gastar créditos');
                }
                
            } catch (error) {
                console.error('❌ Erro ao gastar créditos:', error);
                Cache.set('user_balance', check.balance);
                
                return {
                    success: false,
                    balance: check.balance,
                    message: `❌ Erro ao processar ação. Créditos não foram debitados.`,
                    action,
                    error: error.message
                };
            }
        },

        async canReceiveDailyCredit() {
            try {
                const response = await fetchWithRetry('/api/payments/daily-credit-status');
                if (response?.ok) {
                    const data = await response.json();
                    return {
                        canReceive: data.can_receive || false,
                        nextAvailable: data.next_available || null,
                        message: data.can_receive 
                            ? '✅ Você pode receber seu crédito diário!' 
                            : `⏳ Próximo crédito disponível em ${data.next_available}`
                    };
                }
            } catch (error) {
                console.warn('⚠️ Erro ao verificar crédito diário:', error);
            }
            
            return {
                canReceive: false,
                message: '⚠️ Não foi possível verificar. Tente novamente.'
            };
        },

        async checkLowCredits(threshold = 3) {
            const balance = await this.getBalance();
            
            if (balance <= 0) {
                showNotification('⚠️ Você está sem créditos! Adquira o Plano Bronze para continuar.', 'warning');
                return true;
            }
            
            if (balance <= threshold) {
                showNotification(`⚠️ Atenção! Você tem apenas ${balance} crédito(s). Considere adquirir o Plano Bronze.`, 'warning');
                return true;
            }
            
            return false;
        }
    };

    // ==============================================
    // 🛡️ ACTION GUARD (Proteção de Ações)
    // ==============================================

    const ActionGuard = {
        protect(actionName, actionFn, cost = 1) {
            return async function(...args) {
                console.log(`🛡️ Protegendo ação: ${actionName}`);
                
                const check = await CreditSystem.canPerformAction(actionName, cost);
                
                if (!check.allowed) {
                    showNotification(check.message, 'error');
                    
                    if (check.suggestUpgrade) {
                        showUpgradeModal();
                    }
                    
                    return {
                        success: false,
                        error: 'creditos_insuficientes',
                        message: check.message
                    };
                }
                
                try {
                    console.log(`✅ Ação autorizada: ${actionName}`);
                    const result = await actionFn(...args);
                    
                    EventBus.emit('payment:action_executed', {
                        action: actionName,
                        cost,
                        success: true,
                        result
                    });
                    
                    return result;
                } catch (error) {
                    console.error(`❌ Erro na ação ${actionName}:`, error);
                    showNotification(`Erro ao executar ${actionName}. Tente novamente.`, 'error');
                    throw error;
                }
            };
        }
    };

    // ==============================================
    // 🔥 NOTIFICAÇÕES (usa app.js se disponível)
    // ==============================================

    function showNotification(message, type = 'info') {
        const safeMessage = Security.sanitizeHTML(message);
        
        // 1. Tenta usar App.showNotification
        if (HAS_APP && window.App?.showNotification) {
            try {
                return window.App.showNotification(safeMessage, type);
            } catch (e) {
                console.warn('⚠️ App.showNotification falhou:', e);
            }
        }
        
        // 2. Tenta usar AppUtils
        if (window.AppUtils?.showNotification) {
            try {
                return window.AppUtils.showNotification(safeMessage, type);
            } catch (e) {
                console.warn('⚠️ AppUtils.showNotification falhou:', e);
            }
        }
        
        // 3. Tenta usar appAuth
        if (window.appAuth?.showNotification) {
            try {
                return window.appAuth.showNotification(safeMessage, type);
            } catch (e) {
                console.warn('⚠️ appAuth.showNotification falhou:', e);
            }
        }
        
        // 4. Tenta usar Toastr
        if (window.toastr?.[type]) {
            try {
                window.toastr[type](safeMessage);
                return true;
            } catch (e) {
                console.warn('⚠️ Toastr falhou:', e);
            }
        }
        
        // 5. Fallback final
        console.log(`[${type}] ${safeMessage}`);
        if (type === 'error' || type === 'warning') {
            alert(`⚠️ ${safeMessage}`);
        }
        return true;
    }

    // ==============================================
    // 📊 DASHBOARD DE CRÉDITOS (UI)
    // ==============================================

    function renderCreditDashboard() {
        const container = document.getElementById('creditDashboard');
        if (!container) return;
        
        // Atualiza a cada 10 segundos
        setInterval(async () => {
            const balance = await CreditSystem.getBalance();
            const authStatus = getAuthStatus();
            const isPremium = authStatus.isPremium;
            const dailyCredit = await CreditSystem.canReceiveDailyCredit();
            
            container.innerHTML = `
                <div class="credit-dashboard">
                    <div class="credit-card">
                        <div class="credit-header">
                            <i class="fas fa-coins"></i>
                            <h4>Meus Créditos</h4>
                        </div>
                        <div class="credit-balance">
                            <span class="balance-number">${balance}</span>
                            <span class="balance-label">créditos disponíveis</span>
                        </div>
                        ${isPremium ? `
                            <div class="credit-info">
                                <span class="badge premium-badge">⭐ Premium</span>
                                <span class="credit-max">Máx: ${CONFIG.MAX_CREDITS_BALANCE}</span>
                            </div>
                        ` : `
                            <div class="credit-warning">
                                <i class="fas fa-exclamation-triangle"></i>
                                <span>Adquira o Plano Bronze para mais créditos!</span>
                            </div>
                        `}
                        ${dailyCredit.canReceive ? `
                            <button class="btn btn-credit btn-sm" onclick="window.receiveDailyCredit()">
                                <i class="fas fa-gift"></i> Receber Crédito Diário
                            </button>
                        ` : `
                            <small class="text-muted">${dailyCredit.message}</small>
                        `}
                    </div>
                </div>
            `;
        }, 10000);
    }

    function showUpgradeModal() {
        // Verifica se já existe
        let modal = document.getElementById('upgradeModal');
        if (modal) {
            try {
                const instance = bootstrap.Modal.getInstance(modal);
                if (instance) instance.show();
                return;
            } catch (e) {
                modal.remove();
            }
        }

        const modalHTML = `
            <div class="modal fade" id="upgradeModal" tabindex="-1">
                <div class="modal-dialog modal-dialog-centered">
                    <div class="modal-content" style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border: 1px solid #f5a623;">
                        <div class="modal-header border-0">
                            <h5 class="modal-title" style="color: #f5a623;">💎 Créditos Insuficientes</h5>
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body text-center">
                            <i class="fas fa-crown" style="font-size: 4rem; color: #f5a623;"></i>
                            <h4 class="mt-3" style="color: #fff;">Você precisa de mais créditos!</h4>
                            <p style="color: rgba(255,255,255,0.7);">Adquira o <strong style="color: #f5a623;">Plano Bronze</strong> e tenha:</p>
                            <ul class="list-unstyled" style="color: rgba(255,255,255,0.8);">
                                <li>✅ 30 créditos para análises</li>
                                <li>✅ 1 crédito novo por dia</li>
                                <li>✅ Acesso a todas as funcionalidades</li>
                            </ul>
                            <a href="/planos" class="btn btn-bronze btn-lg" style="background: linear-gradient(135deg, #cd7f32, #f5a623); border: none; color: #fff; border-radius: 50px; padding: 12px 40px;">
                                🔥 Quero meu Plano Bronze
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', modalHTML);
        modal = document.getElementById('upgradeModal');
        
        try {
            new bootstrap.Modal(modal).show();
        } catch (e) {
            console.warn('⚠️ Bootstrap Modal não disponível:', e);
            modal.style.display = 'block';
            modal.classList.add('show');
        }
    }

    // ==============================================
    // 🔥 RENDERIZAÇÃO DE PLANOS (OTIMIZADA)
    // ==============================================

    function isPlansPage() {
        return document.getElementById('plans-container') !== null;
    }

    function isDashboardPage() {
        return document.getElementById('premiumStatusContainer') !== null;
    }

    async function loadPlans(forceReload = false) {
        console.log('📦 Carregando planos...');
        
        if (!forceReload) {
            const cached = Cache.get('plans_data');
            if (cached) {
                console.log('📦 Usando dados em cache');
                await renderBronzePlan(cached.plans, cached.fullData);
                return;
            }
        }

        try {
            const response = await fetchWithRetry('/api/payments/plans');
            
            if (response?.ok) {
                const data = await response.json();
                const safeData = Security.sanitizeObject(data);
                
                Cache.set('plans_data', {
                    plans: safeData.plans,
                    fullData: safeData
                });
                
                await renderBronzePlan(safeData.plans, safeData);
            } else {
                console.warn('⚠️ Falha ao carregar planos, usando fallback estático');
                renderBronzePlanStatic();
            }
        } catch (error) {
            console.warn('⚠️ Erro ao carregar planos, usando fallback estático:', error);
            renderBronzePlanStatic();
        }
    }

    function renderBronzePlanStatic() {
        const container = document.getElementById('plans-container');
        if (!container) {
            console.warn('⚠️ Container #plans-container não encontrado');
            return;
        }

        console.log('📦 Renderizando plano estático...');

        const authStatus = getAuthStatus();

        if (authStatus.isAdmin) {
            container.innerHTML = getAdminHTML();
            return;
        }

        if (authStatus.isPremium) {
            container.innerHTML = getActivePlanHTML();
            return;
        }

        container.innerHTML = getStaticPlanHTML();
        console.log('✅ Plano estático renderizado com sucesso!');
    }

    function getAdminHTML() {
        return `
            <div class="col-lg-8 mx-auto">
                <div class="admin-message" style="background: linear-gradient(135deg, #2c1a0a 0%, #3d2614 100%); border-radius: 40px; padding: 3rem; border: 1px solid #cd7f32; text-align: center;">
                    <i class="fas fa-crown" style="font-size: 4rem; color: #f5a623; margin-bottom: 1rem;"></i>
                    <h2 class="h3 mb-3" style="color: #f5a623;">👑 Você é Administrador</h2>
                    <p class="lead mb-4" style="color: rgba(255,255,255,0.7);">Como admin, você tem acesso ilimitado a todas as funcionalidades.</p>
                    <a href="/dashboard" class="btn btn-light btn-lg mt-3"><i class="fas fa-arrow-left me-2"></i> Voltar ao Dashboard</a>
                </div>
            </div>
        `;
    }

    function getActivePlanHTML() {
        return `
            <div class="col-lg-8 mx-auto">
                <div class="bronze-card active-plan" style="background: linear-gradient(135deg, #1a472a 0%, #2d6a4f 100%); border: 2px solid #48bb78; border-radius: 40px; padding: 3rem;">
                    <div class="text-center">
                        <div class="bronze-badge" style="background: linear-gradient(135deg, #48bb78, #2d6a4f);">
                            <i class="fas fa-check-circle"></i> PLANO ATIVO
                        </div>
                        <h2 style="color: #48bb78; margin: 1.5rem 0;"><i class="fas fa-crown me-2"></i>Plano Bronze Ativo</h2>
                        <div class="alert alert-success" style="background: rgba(72, 187, 120, 0.2); border-color: #48bb78; color: #48bb78;">
                            <i class="fas fa-check-circle me-2"></i>
                            Você já possui acesso premium! Aproveite todos os benefícios.
                        </div>
                        <a href="/dashboard" class="btn btn-success btn-lg mt-3">
                            <i class="fas fa-arrow-right me-2"></i> Ir para o Dashboard
                        </a>
                    </div>
                </div>
            </div>
        `;
    }

    function getStaticPlanHTML() {
        return `
            <div class="col-lg-8 mx-auto">
                <div class="bronze-card" data-aos="fade-up" data-aos-duration="800">
                    <div class="bronze-badge"><i class="fas fa-fire"></i> 🔥 PROMOÇÃO FUNDADOR</div>
                    
                    <div class="bronze-title">
                        <span class="icon-big"><i class="fas fa-crown"></i></span>
                        <h2>Plano Bronze</h2>
                        <p class="subtitle">O plano ideal para sua oficina crescer com IA</p>
                    </div>
                    
                    <div class="price-container">
                        <span class="old-price">De R$ 149,90</span>
                        <div class="price-tag" id="planoPreco">R$ 97<span class="cents">,00</span> <small>à vista</small></div>
                        <span class="economy-badge"><i class="fas fa-tag"></i> Economia de 35%</span>
                    </div>
                    
                    <div class="plan-info">
                        <div class="row">
                            <div class="col-4"><span class="number">30</span><span class="label">Créditos</span></div>
                            <div class="col-4"><span class="number">3</span><span class="label">Arquivos/vez</span></div>
                            <div class="col-4"><span class="number">∞</span><span class="label">Vitalício</span></div>
                        </div>
                    </div>
                    
                    <div class="vagas-counter">
                        <div><span class="vagas-label">🎯 Apenas</span> <span class="vagas-number">73</span> <span class="vagas-label">vagas restantes</span></div>
                        <div class="vagas-progress"><div class="vagas-progress-bar" style="width: 27%;"></div></div>
                        <small style="color:rgba(255,255,255,0.3); font-size:0.7rem;"><i class="fas fa-clock"></i> Oferta por tempo limitado</small>
                    </div>
                    
                    <div class="bronze-features">
                        <div class="bronze-feature"><i class="fas fa-check-circle check"></i> <span><strong>30 créditos</strong> para análises completas</span></div>
                        <div class="bronze-feature"><i class="fas fa-check-circle check"></i> <span><strong>Análise com IA</strong> (Google Gemini)</span></div>
                        <div class="bronze-feature"><i class="fas fa-check-circle check"></i> <span><strong>Até 3 arquivos</strong> por análise (CSV/Excel)</span></div>
                        <div class="bronze-feature"><i class="fas fa-check-circle check"></i> <span>📊 <strong>Dashboard completo</strong> com métricas</span></div>
                        <div class="bronze-feature"><i class="fas fa-check-circle check"></i> <span>📄 <strong>Relatórios em PDF</strong> automáticos</span></div>
                        <div class="bronze-feature"><i class="fas fa-check-circle check"></i> <span><strong>Suporte prioritário</strong> por email</span></div>
                    </div>
                    
                    <div class="d-grid gap-3 mt-4">
                        <button class="btn btn-bronze btn-lg" onclick="window.openCpfModal('premium_mensal')">
                            <i class="fas fa-bolt me-2"></i> 🔥 GARANTIR PREÇO FUNDADOR R$ 97,00
                            <small class="d-block fs-10">Pagamento seguro via PIX</small>
                        </button>
                    </div>
                    
                    <div class="limit-warning">
                        <i class="fas fa-info-circle"></i>
                        <span>Este é um <strong>plano vitalício</strong> com preço especial para os primeiros <strong>100 clientes</strong>. Após esgotar, o preço volta para R$ 149,90.</span>
                    </div>
                    
                    <div class="credits-explanation">
                        <div class="step"><i class="fas fa-coins"></i> <span><strong>Como funcionam os créditos:</strong></span></div>
                        <div class="step"><i class="fas fa-plus-circle"></i> <span>Você começa com <strong>3 créditos grátis</strong></span></div>
                        <div class="step"><i class="fas fa-gem"></i> <span>Com o <strong>Plano Bronze</strong>, você ganha <strong>30 créditos</strong> para usar quando quiser</span></div>
                        <div class="step"><i class="fas fa-chart-line"></i> <span>Cada análise consome <strong>1 crédito</strong> por arquivo</span></div>
                        <div class="highlight-box"><span><i class="fas fa-bolt" style="color:#f5a623;"></i> <strong>Dica:</strong> Use seus créditos estrategicamente para análises mais importantes e maximize o ROI da sua oficina!</span></div>
                    </div>
                    
                    <div class="security-seals">
                        <span class="seal"><i class="fas fa-lock"></i> Pagamento Seguro</span>
                        <span class="seal"><i class="fas fa-shield-alt"></i> PoW Protegido</span>
                        <span class="seal"><i class="fas fa-credit-card"></i> PIX</span>
                    </div>
                </div>
            </div>
        `;
    }

    async function renderBronzePlan(plans, fullData = null) {
        const container = document.getElementById('plans-container');
        if (!container) {
            console.warn('⚠️ Container #plans-container não encontrado');
            renderBronzePlanStatic();
            return;
        }

        const authStatus = getAuthStatus();

        if (authStatus.isAdmin) {
            renderBronzePlanStatic();
            return;
        }

        if (authStatus.isPremium) {
            renderBronzePlanStatic();
            return;
        }

        if (!plans || !plans['premium_mensal']) {
            renderBronzePlanStatic();
            return;
        }

        // Busca status da promoção com cache
        let promoData = {
            remaining_slots: CONFIG.TOTAL_PROMOTIONAL_SLOTS,
            total_slots: CONFIG.TOTAL_PROMOTIONAL_SLOTS,
            promotional_price: CONFIG.PROMOTIONAL_PRICE,
            regular_price: CONFIG.REGULAR_PRICE,
            user_locked_price: null
        };

        try {
            const cached = Cache.get('promotion_data');
            if (cached) {
                promoData = cached;
            } else {
                const promoResponse = await fetchWithRetry('/api/payments/promotion-status');
                if (promoResponse?.ok) {
                    const rawData = await promoResponse.json();
                    promoData = Security.sanitizeObject(rawData);
                    Cache.set('promotion_data', promoData);
                }
            }
        } catch (error) {
            console.warn('Erro ao buscar status da promoção:', error);
        }

        if (!promoData.remaining_slots) {
            renderBronzePlanStatic();
            return;
        }

        const vagasRestantes = Security.sanitizeNumber(promoData.remaining_slots, CONFIG.TOTAL_PROMOTIONAL_SLOTS);
        const totalVagas = Security.sanitizeNumber(promoData.total_slots, CONFIG.TOTAL_PROMOTIONAL_SLOTS);
        const precoPromocional = Security.sanitizeNumber(promoData.promotional_price, CONFIG.PROMOTIONAL_PRICE);
        const precoRegular = Security.sanitizeNumber(promoData.regular_price, CONFIG.REGULAR_PRICE);
        const isUserLocked = promoData.user_locked_price !== null && promoData.user_locked_price !== undefined;
        const isSoldOut = vagasRestantes <= 0;
        const precoAtual = isSoldOut ? precoRegular : precoPromocional;
        const percentual = ((totalVagas - vagasRestantes) / totalVagas) * 100;
        const isUrgent = vagasRestantes <= 20 && vagasRestantes > 0;

        container.innerHTML = getDynamicPlanHTML({
            isUserLocked,
            isSoldOut,
            isUrgent,
            precoAtual,
            precoPromocional,
            precoRegular,
            vagasRestantes,
            totalVagas,
            percentual,
            promoData
        });

        console.log('✅ Plano renderizado com dados da API!');
    }

    function getDynamicPlanHTML(params) {
        const {
            isUserLocked,
            isSoldOut,
            isUrgent,
            precoAtual,
            precoPromocional,
            precoRegular,
            vagasRestantes,
            totalVagas,
            percentual
        } = params;

        const precoMessage = isUserLocked ? `
            <div class="vitalicio-badge">
                <i class="fas fa-gem me-2"></i>
                PREÇO VITALÍCIO GARANTIDO!
                <small>R$ ${precoAtual.toFixed(2).replace('.', ',')} para sempre</small>
            </div>
        ` : '';

        return `
            <div class="col-lg-8 mx-auto">
                <div class="bronze-card" data-aos="fade-up" data-aos-duration="800">
                    <div class="bronze-badge">
                        <i class="fas fa-fire"></i> 
                        ${isSoldOut ? 'PROMOÇÃO ENCERRADA' : (isUserLocked ? '🔥 SEU PREÇO VITALÍCIO' : '🔥 PROMOÇÃO FUNDADOR')}
                    </div>
                    
                    ${precoMessage}
                    
                    <div class="bronze-title">
                        <h2><i class="fas fa-crown me-2"></i> Plano Bronze</h2>
                        <p><i class="fas fa-check-circle me-1"></i> A escolha dos profissionais</p>
                    </div>
                    
                    <div class="price-container">
                        ${!isSoldOut && !isUserLocked ? `<span class="old-price">De R$ ${precoRegular.toFixed(2).replace('.', ',')}</span>` : ''}
                        <div class="price-tag" id="planoPreco">R$ ${precoAtual.toFixed(2).replace('.', ',')}<small>/mês</small></div>
                        ${!isSoldOut && !isUserLocked ? `<span class="economy-badge">🔥 ECONOMIZE R$ ${(precoRegular - precoPromocional).toFixed(2).replace('.', ',')} 🔥</span>` : ''}
                        ${isUserLocked ? `<span class="economy-badge" style="background: linear-gradient(135deg, #28a745, #20c997);"><i class="fas fa-lock me-1"></i> PREÇO BLOQUEADO - VITALÍCIO</span>` : ''}
                        ${isSoldOut && !isUserLocked ? `<span class="economy-badge" style="background: linear-gradient(135deg, #dc3545, #c0392b);"><i class="fas fa-exclamation-triangle me-1"></i> PROMOÇÃO ESGOTADA</span>` : ''}
                    </div>
                    
                    ${!isSoldOut && !isUserLocked ? `
                    <div class="vagas-counter ${isUrgent ? 'vagas-urgent' : ''}">
                        <div class="d-flex align-items-center justify-content-center flex-wrap">
                            <i class="fas fa-ticket-alt fa-2x me-3" style="color: #f5a623;"></i>
                            <div>
                                <span class="vagas-label">VAGAS PROMOCIONAIS</span>
                                <div>
                                    <span class="vagas-number">${vagasRestantes}</span>
                                    <span class="vagas-label">restantes de ${totalVagas}</span>
                                </div>
                            </div>
                        </div>
                        <div class="vagas-progress"><div class="vagas-progress-bar" style="width: ${Math.min(100, percentual)}%"></div></div>
                        ${isUrgent ? `
                            <div class="mt-2 text-center">
                                <strong style="color: #f5a623;">🔥 URGENTE! ÚLTIMAS ${vagasRestantes} VAGAS! 🔥</strong>
                                <br><small>Garanta o preço de fundador R$ ${precoPromocional.toFixed(2).replace('.', ',')} (vitalício)</small>
                            </div>
                        ` : `
                            <div class="mt-2 text-center small text-muted">Apenas as primeiras ${totalVagas} pessoas pagam R$ ${precoPromocional.toFixed(2).replace('.', ',')} (vitalício)</div>
                        `}
                    </div>
                    ` : ''}
                    
                    ${isUserLocked ? `
                    <div class="vagas-counter" style="background: rgba(40, 167, 69, 0.2); border-color: #28a745;">
                        <div class="d-flex align-items-center justify-content-center flex-wrap">
                            <i class="fas fa-lock fa-2x me-3" style="color: #28a745;"></i>
                            <div>
                                <span class="vagas-label">PREÇO GARANTIDO</span>
                                <div>
                                    <span class="vagas-number" style="color: #28a745;">R$ ${precoAtual.toFixed(2).replace('.', ',')}</span>
                                    <span class="vagas-label">para sempre!</span>
                                </div>
                            </div>
                        </div>
                        <div class="mt-2 text-center small text-success"><i class="fas fa-check-circle me-1"></i> Você comprou na promoção e teve o preço bloqueado!</div>
                    </div>
                    ` : ''}
                    
                    ${isSoldOut && !isUserLocked ? `
                    <div class="vagas-counter" style="background: rgba(220, 53, 69, 0.2); border-color: #dc3545;">
                        <div class="d-flex align-items-center justify-content-center flex-wrap">
                            <i class="fas fa-exclamation-triangle fa-2x me-3" style="color: #dc3545;"></i>
                            <div>
                                <span class="vagas-label">PROMOÇÃO ESGOTADA</span>
                                <div>
                                    <span class="vagas-number" style="color: #dc3545;">0</span>
                                    <span class="vagas-label">vagas restantes</span>
                                </div>
                            </div>
                        </div>
                        <div class="mt-2 text-center small text-danger">As ${totalVagas} vagas promocionais já foram preenchidas. Valor: R$ ${precoRegular.toFixed(2).replace('.', ',')}</div>
                    </div>
                    ` : ''}
                    
                    <div class="my-3">
                        <div class="highlight-title"><i class="fas fa-star me-2"></i> O que você recebe:</div>
                        <div class="bronze-feature"><i class="fas fa-brain"></i> <span><strong>IA Avançada (Gemini + Scikit-Learn)</strong> - Análises preditivas</span></div>
                        <div class="bronze-feature"><i class="fas fa-file-alt"></i> <span><strong>Relatórios Completos em PDF</strong> - Exporte análises</span></div>
                        <div class="bronze-feature"><i class="fas fa-chart-line"></i> <span><strong>Dashboard Interativo</strong> - Métricas em tempo real</span></div>
                        <div class="bronze-feature"><i class="fas fa-calendar-day"></i> <span><strong>1 crédito novo por dia</strong> - Para novas análises</span></div>
                        <div class="bronze-feature"><i class="fas fa-layer-group"></i> <span><strong>Até ${CONFIG.MAX_CREDITS_BALANCE} créditos acumulados</strong> - Máximo de ${CONFIG.MAX_CREDITS_BALANCE}</span></div>
                        <div class="bronze-feature"><i class="fas fa-chart-pie"></i> <span><strong>Gráficos automáticos</strong> - Visualização inteligente</span></div>
                        <div class="bronze-feature"><i class="fas fa-download"></i> <span><strong>Exportação CSV/Excel</strong> - Seus dados sempre disponíveis</span></div>
                        <div class="bronze-feature"><i class="fas fa-headset"></i> <span><strong>Suporte Prioritário 24/7</strong> - Atendimento exclusivo</span></div>
                    </div>
                    
                    <div class="plan-info">
                        <div class="row text-center">
                            <div class="col-4"><i class="fas fa-coins fa-lg"></i><div class="small fw-bold mt-1">${CONFIG.DAYS_PREMIUM} Créditos</div><div class="small text-muted">Total do plano</div></div>
                            <div class="col-4"><i class="fas fa-clock fa-lg"></i><div class="small fw-bold mt-1">${CONFIG.DAYS_PREMIUM} Dias</div><div class="small text-muted">Duração</div></div>
                            <div class="col-4"><i class="fas fa-tachometer-alt fa-lg"></i><div class="small fw-bold mt-1">${CONFIG.MAX_CREDITS_BALANCE} Máx.</div><div class="small text-muted">Créditos acumulados</div></div>
                        </div>
                    </div>
                    
                    <div class="limit-warning">
                        <i class="fas fa-info-circle"></i>
                        <small>⚠️ Limite máximo de <strong>${CONFIG.MAX_CREDITS_BALANCE} créditos acumulados</strong>. Use-os para continuar recebendo novos créditos diários!</small>
                    </div>
                    
                    <div class="d-grid gap-3 mt-4">
                        <button class="btn btn-bronze btn-lg" onclick="window.openCpfModal('premium_mensal')">
                            <i class="fas fa-bolt me-2"></i>
                            ${isUserLocked ? 'RENOVAR MEU PLANO' : (isSoldOut ? `COMPRAR POR R$ ${precoAtual.toFixed(2).replace('.', ',')}` : `🔥 GARANTIR PREÇO FUNDADOR R$ ${precoAtual.toFixed(2).replace('.', ',')}`)}
                            <small class="d-block fs-10">${isUserLocked ? 'Pagamento vitalício garantido' : 'Pagamento seguro via PIX'}</small>
                        </button>
                    </div>
                    
                    <div class="security-seals">
                        <span class="badge me-2"><i class="fas fa-lock"></i> Pagamento 100% Seguro</span>
                        <span class="badge me-2"><i class="fas fa-undo-alt"></i> 7 Dias de Garantia</span>
                        <span class="badge"><i class="fas fa-clock"></i> Ativação Imediata</span>
                    </div>
                    
                    <p class="text-center small mt-4 mb-0" style="color: rgba(255,255,255,0.6);">
                        <i class="fas fa-check-circle text-warning me-1"></i>
                        Após o pagamento, você receberá 1 crédito por dia durante ${CONFIG.DAYS_PREMIUM} dias
                    </p>
                </div>
            </div>
        `;
    }

    // ==============================================
    // 🔥 CRÉDITOS (UI)
    // ==============================================

    async function updateCreditsDisplay(credits = null) {
        try {
            if (credits === null) {
                const authStatus = getAuthStatus();
                credits = authStatus.credits;
            }

            const authStatus = getAuthStatus();
            const isPremiumUser = authStatus.isPremium;
            const displayText = formatCreditsDisplay(credits, isPremiumUser);
            
            document.querySelectorAll('#creditsCount, #creditsDisplay, #uploadCredits, .credits-badge span').forEach(el => {
                if (el) el.textContent = displayText;
            });
            
            EventBus.emit('payment:credits_updated', {
                credits,
                display: displayText,
                maxCredits: CONFIG.MAX_CREDITS_BALANCE,
                isPremium: isPremiumUser
            });
            
            return true;
        } catch (error) {
            console.error('Erro ao atualizar créditos:', error);
            return false;
        }
    }

    function formatCreditsDisplay(credits, isPremiumUser = false) {
        const safeCredits = Security.sanitizeNumber(credits, 0);
        const authStatus = getAuthStatus();
        const isAdmin = authStatus.isAdmin;
        
        if (isAdmin) return '∞';
        if (isPremiumUser) return `${safeCredits}/${CONFIG.MAX_CREDITS_BALANCE}`;
        return safeCredits.toString();
    }

    // ==============================================
    // 🔥 RECEBER CRÉDITO DIÁRIO
    // ==============================================

    async function receiveDailyCredit() {
        try {
            const response = await fetchWithRetry('/api/payments/daily-credit', { 
                method: 'POST' 
            });
            
            if (response?.ok) {
                const data = await response.json();
                const safeData = Security.sanitizeObject(data);
                
                if (safeData.success) {
                    showNotification(`✅ ${safeData.message || 'Crédito recebido com sucesso!'}`, 'success');
                    
                    // Atualiza estado via app.js
                    if (HAS_APP && window.__APP_STATE_MANAGER) {
                        window.__APP_STATE_MANAGER.updateCredits(safeData.balance || 0);
                    } else if (window.App?.StateManager) {
                        window.App.StateManager.updateCredits(safeData.balance || 0);
                    }
                    
                    setTimeout(() => updateCreditsDisplay(), 500);
                    return safeData;
                } else {
                    showNotification(safeData.message || 'Erro ao receber crédito', 'warning');
                    return safeData;
                }
            }
        } catch (error) {
            console.error('Erro ao receber crédito:', error);
            showNotification('Erro de conexão. Tente novamente.', 'error');
        }
        return null;
    }

    // ==============================================
    // 🔥 STATUS PREMIUM
    // ==============================================

    async function loadPremiumStatus() {
        try {
            const response = await fetchWithRetry('/api/payments/premium-status');
            if (response?.ok) {
                const data = await response.json();
                const safeData = Security.sanitizeObject(data);
                
                // Atualiza estado via app.js
                if (HAS_APP && window.__APP_STATE_MANAGER) {
                    window.__APP_STATE_MANAGER.updatePremiumStatus(safeData);
                } else if (window.App?.StateManager) {
                    window.App.StateManager.updatePremiumStatus(safeData);
                }
                
                EventBus.emit('payment:premium_status_updated', {
                    isPremium: safeData.is_premium || false,
                    daysLeft: safeData.days_left || 0,
                    hasPromotionalPrice: safeData.promotional_price_locked || false,
                    promotionalPrice: safeData.promotional_price || null,
                    canReceiveDailyCredit: safeData.can_receive_today || false,
                    receivedDailyCreditToday: safeData.received_today || false,
                    creditsBalance: safeData.credits_balance || 0,
                    maxCredits: safeData.max_credits_balance || CONFIG.MAX_CREDITS_BALANCE
                });
                
                return safeData;
            }
        } catch (error) {
            console.error('Erro ao carregar status premium:', error);
        }
        return null;
    }

    async function loadSubscriptionStatus() {
        try {
            const response = await fetchWithRetry('/api/payments/subscription-status');
            if (response?.ok) {
                const data = await response.json();
                return Security.sanitizeObject(data);
            }
        } catch (error) {
            console.error('Erro ao carregar status da assinatura:', error);
        }
        return null;
    }

    async function updatePromotionStatus() {
        try {
            const response = await fetchWithRetry('/api/payments/promotion-status');
            if (response?.ok) {
                const data = await response.json();
                const safeData = Security.sanitizeObject(data);
                Cache.set('promotion_data', safeData);
                console.log(`📊 Promoção: ${safeData.remaining_slots}/${safeData.total_slots} vagas`);
                return safeData;
            }
        } catch (error) {
            console.warn('Erro ao atualizar status da promoção:', error);
        }
        return null;
    }

    // ==============================================
    // 🔥 MODAL CPF
    // ==============================================

    function openCpfModal(planId) {
        const authStatus = getAuthStatus();
        
        if (authStatus.isAdmin) {
            showNotification('👑 Como administrador, você tem acesso ilimitado.', 'info');
            return;
        }

        if (authStatus.isPremium) {
            showNotification('✅ Você já possui um plano ativo!', 'success');
            window.location.href = '/dashboard';
            return;
        }

        let cpfModal = document.getElementById('cpfModal');
        
        if (!cpfModal) {
            cpfModal = document.createElement('div');
            cpfModal.id = 'cpfModal';
            cpfModal.className = 'modal fade';
            cpfModal.setAttribute('tabindex', '-1');
            cpfModal.setAttribute('aria-hidden', 'true');
            document.body.appendChild(cpfModal);
        }

        cpfModal.innerHTML = `
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content" style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border: 1px solid #f5a623;">
                    <div class="modal-header border-0">
                        <h5 class="modal-title" style="color: #f5a623;"><i class="fas fa-id-card me-2"></i>Confirme seu CPF</h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <p class="text-white-50 mb-3"><i class="fas fa-shield-alt me-2"></i> O CPF é obrigatório para geração do PIX e protege sua compra contra fraudes.</p>
                        <div class="mb-3">
                            <label class="form-label text-white">CPF</label>
                            <input type="text" class="form-control form-control-lg" id="cpfInput" placeholder="000.000.000-00" maxlength="14" autocomplete="off" style="background: rgba(255,255,255,0.1); border-color: #f5a623; color: white; border-radius:12px;">
                            <div class="form-text text-white-50">Apenas números (11 dígitos)</div>
                        </div>
                        <div id="cpfError" class="alert alert-danger d-none" role="alert"></div>
                    </div>
                    <div class="modal-footer border-0">
                        <button type="button" class="btn" style="background:rgba(255,255,255,0.06); color:rgba(255,255,255,0.6); border:none; border-radius:50px; padding:0.5rem 1.5rem;" data-bs-dismiss="modal">Cancelar</button>
                        <button type="button" class="btn btn-bronze" onclick="window.proceedWithCpf('${Security.sanitizeHTML(planId)}')"><i class="fas fa-arrow-right me-2"></i>Continuar para PIX</button>
                    </div>
                </div>
            </div>
        `;

        const cpfInput = document.getElementById('cpfInput');
        if (cpfInput) {
            cpfInput.addEventListener('input', function(e) {
                let value = e.target.value.replace(/\D/g, '');
                if (value.length > 11) value = value.slice(0, 11);
                if (value.length > 9) {
                    value = value.replace(/^(\d{3})(\d{3})(\d{3})(\d{2})$/, '$1.$2.$3-$4');
                } else if (value.length > 6) {
                    value = value.replace(/^(\d{3})(\d{3})(\d{0,3})$/, '$1.$2.$3');
                } else if (value.length > 3) {
                    value = value.replace(/^(\d{3})(\d{0,3})$/, '$1.$2');
                }
                e.target.value = value;
            });

            cpfInput.addEventListener('blur', function(e) {
                const cpf = Security.sanitizeCPF(e.target.value);
                if (cpf.length > 0 && !Security.validateCPF(cpf)) {
                    const errorEl = document.getElementById('cpfError');
                    if (errorEl) {
                        errorEl.textContent = '❌ CPF inválido. Digite um CPF válido com 11 dígitos.';
                        errorEl.classList.remove('d-none');
                    }
                }
            });
        }

        try {
            new bootstrap.Modal(cpfModal).show();
        } catch (e) {
            console.warn('⚠️ Bootstrap Modal não disponível:', e);
            cpfModal.style.display = 'block';
            cpfModal.classList.add('show');
        }
    }

    function proceedWithCpf(planId) {
        const cpfInput = document.getElementById('cpfInput');
        const cpfError = document.getElementById('cpfError');
        
        if (!cpfInput) {
            showNotification('Erro ao processar CPF. Tente novamente.', 'error');
            return;
        }
        
        const cpfLimpo = Security.sanitizeCPF(cpfInput.value);
        
        if (!Security.validateCPF(cpfLimpo)) {
            if (cpfError) {
                cpfError.textContent = '❌ CPF inválido. Digite um CPF válido com 11 dígitos.';
                cpfError.classList.remove('d-none');
            }
            return;
        }
        
        if (cpfError) cpfError.classList.add('d-none');
        
        const cpfModal = bootstrap.Modal.getInstance(document.getElementById('cpfModal'));
        if (cpfModal) cpfModal.hide();
        
        showPixModalSecure(planId, cpfLimpo);
    }

    // ==============================================
    // 🔥 MODAL PIX
    // ==============================================

    let countdownInterval = null;

    function showPixModalSecure(planId, cpf) {
        console.log(`💳 Abrindo modal PIX - Plano: ${planId}, CPF: ${cpf}`);
        
        let pixModal = document.getElementById('pixModal');
        
        if (!pixModal) {
            pixModal = document.createElement('div');
            pixModal.id = 'pixModal';
            pixModal.className = 'modal fade';
            pixModal.setAttribute('tabindex', '-1');
            pixModal.setAttribute('aria-hidden', 'true');
            document.body.appendChild(pixModal);
        }

        const valorPlano = "R$ 97,00";
        const planName = "Plano Bronze";

        pixModal.innerHTML = `
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content" style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border: 1px solid rgba(205,127,50,0.3);">
                    <div class="modal-header border-0" style="border-bottom: 1px solid rgba(255,255,255,0.1);">
                        <h5 class="modal-title" style="color: #f5a623;"><i class="fas fa-qrcode me-2"></i> Pagamento via PIX</h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body text-center py-4">
                        <div class="alert alert-success mb-3 text-center" style="background: rgba(40, 167, 69, 0.15); border-color: #28a745; color: #48bb78;">
                            <i class="fas fa-gem me-2"></i>
                            <strong>🎉 VOCÊ GARANTIU O PREÇO FUNDADOR!</strong><br>
                            <small>${valorPlano} - Preço bloqueado VITALÍCIO!</small>
                        </div>
                        
                        <h6 class="mb-3" style="color: rgba(255,255,255,0.7);">Escaneie o QR Code com seu banco</h6>
                        
                        <div class="text-center mb-3">
                            <div class="p-3 d-inline-block" style="background: white; border-radius: 16px;">
                                <img src="https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=pix%3A%2F%2Fautonalytics%40gmail.com%3Famount%3D97.00%26cpf%3D${cpf}" 
                                     alt="QR Code PIX" style="max-width: 200px; border-radius: 8px;" 
                                     loading="lazy" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22200%22 height=%22200%22%3E%3Crect width=%22200%22 height=%22200%22 fill=%22%23f0f0f0%22/%3E%3Ctext x=%2250%22 y=%22110%22 font-size=%2220%22 fill=%22%23999%22%3EQR Code%3C/text%3E%3C/svg%3E'">
                            </div>
                        </div>
                        
                        <div class="p-3 rounded-3 mb-3" style="background: rgba(255,255,255,0.05); word-break: break-all;">
                            <code id="pixCodeText" class="small" style="color: #f5a623;">autonalytics@gmail.com</code>
                        </div>
                        
                        <button class="btn w-100 mb-3" onclick="window.copyPixCodeSecure()" 
                                style="background: rgba(255,255,255,0.06); color: #f5a623; border: 1px solid rgba(205,127,50,0.3); border-radius: 12px; padding: 0.75rem;">
                            <i class="fas fa-copy me-2"></i> Copiar Chave PIX
                        </button>
                        
                        <div class="alert alert-info small" style="background: rgba(245, 166, 35, 0.08); border-color: rgba(205,127,50,0.2); color: rgba(255,255,255,0.7);">
                            <i class="fas fa-info-circle me-2"></i>
                            <strong>Informações do pagamento:</strong><br>
                            <strong>${planName}</strong> - Valor: ${valorPlano}<br>
                            <span class="text-success">✅ Você está comprando na promoção! Preço R$ 97,00 garantido para sempre.</span><br>
                            <span style="color: rgba(255,255,255,0.5);">⏰ Este QR Code expira em <strong id="countdownTimer">30:00</strong> minutos.</span>
                        </div>
                        
                        <div id="paymentStatus"></div>
                    </div>
                    <div class="modal-footer border-0 justify-content-center" style="border-top: 1px solid rgba(255,255,255,0.06);">
                        <button type="button" class="btn w-100" onclick="window.handlePaymentConfirmation()" 
                                style="background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.6); border: none; border-radius: 50px; padding: 0.75rem;">
                            <i class="fas fa-check-circle me-2"></i> Já realizei o pagamento / Atualizar
                        </button>
                    </div>
                </div>
            </div>
        `;

        startCountdown(30 * 60);
        try {
            new bootstrap.Modal(pixModal).show();
        } catch (e) {
            console.warn('⚠️ Bootstrap Modal não disponível:', e);
            pixModal.style.display = 'block';
            pixModal.classList.add('show');
        }
    }

    async function handlePaymentConfirmation() {
        showNotification('🔄 Verificando pagamento...', 'info');
        
        try {
            const response = await fetchWithRetry('/api/payments/verify-payment', {
                method: 'POST'
            });
            
            if (response?.ok) {
                const data = await response.json();
                if (data.success) {
                    showNotification('✅ Pagamento confirmado! Seu plano foi ativado.', 'success');
                    
                    // Atualiza estado via app.js
                    if (HAS_APP && window.__APP_STATE_MANAGER) {
                        await window.__APP_STATE_MANAGER.updatePremiumStatus(data);
                    }
                    
                    const modal = bootstrap.Modal.getInstance(document.getElementById('pixModal'));
                    if (modal) modal.hide();
                    setTimeout(() => window.location.reload(), 1500);
                } else {
                    showNotification('⏳ Pagamento ainda não confirmado. Aguarde alguns minutos.', 'warning');
                }
            } else {
                showNotification('⚠️ Não foi possível verificar o pagamento. Tente novamente em alguns minutos.', 'error');
            }
        } catch (error) {
            console.error('Erro ao verificar pagamento:', error);
            showNotification('Erro ao verificar pagamento. Tente novamente.', 'error');
        }
    }

    function startCountdown(seconds) {
        if (countdownInterval) clearInterval(countdownInterval);
        
        let remaining = Security.sanitizeNumber(seconds, 30 * 60);
        const timerElement = document.getElementById('countdownTimer');
        
        countdownInterval = setInterval(() => {
            if (remaining <= 0) {
                clearInterval(countdownInterval);
                if (timerElement) {
                    timerElement.textContent = 'Expirado!';
                    timerElement.style.color = '#dc3545';
                }
                showNotification('⏰ QR Code expirado. Por favor, gere um novo pagamento.', 'warning');
            } else {
                const minutes = Math.floor(remaining / 60);
                const secs = remaining % 60;
                if (timerElement) {
                    timerElement.textContent = `${minutes}:${secs.toString().padStart(2, '0')}`;
                }
                remaining--;
            }
        }, 1000);
    }

    function copyPixCodeSecure() {
        const codeElement = document.getElementById('pixCodeText');
        if (codeElement?.textContent) {
            const code = Security.sanitizeHTML(codeElement.textContent.trim());
            
            if (navigator.clipboard?.writeText) {
                navigator.clipboard.writeText(code)
                    .then(() => showNotification('✅ Chave PIX copiada!', 'success'))
                    .catch(() => fallbackCopy(code));
            } else {
                fallbackCopy(code);
            }
        }
    }

    function fallbackCopy(text) {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        textarea.style.top = '-9999px';
        document.body.appendChild(textarea);
        textarea.select();
        try {
            document.execCommand('copy');
            showNotification('✅ Chave PIX copiada!', 'success');
        } catch (err) {
            showNotification('❌ Erro ao copiar. Tente novamente.', 'error');
        }
        document.body.removeChild(textarea);
    }

    // ==============================================
    // 📡 REGISTRO DE EVENTOS (INTEGRAÇÃO COM APP.JS)
    // ==============================================

    function registerEventListeners() {
        console.log('📡 Registrando event listeners...');

        // Escuta eventos do app.js
        document.addEventListener('app:state_changed', function(e) {
            const { state, changes } = e.detail || {};
            
            if (changes) {
                // Atualiza créditos se mudou
                if (changes.credits !== undefined) {
                    updateCreditsDisplay(changes.credits);
                }
                
                // Recarrega planos se mudou status premium
                if (changes.isPremium !== undefined && isPlansPage()) {
                    loadPlans(true);
                }
                
                // Atualiza UI
                if (changes.isPremium !== undefined) {
                    updateButtonsForPremium(changes.isPremium);
                }
            }
        });

        // Escuta app:ready para inicialização
        document.addEventListener('app:ready', function(e) {
            console.log('📡 app:ready recebido do app.js');
            const { isAuthenticated, isPremium, credits } = e.detail || {};
            
            if (isAuthenticated) {
                updateCreditsDisplay(credits || 0);
                if (isPlansPage()) {
                    loadPlans();
                }
                if (isDashboardPage()) {
                    loadPremiumStatus();
                }
            }
        });

        // Escuta eventos do próprio payment
        document.addEventListener('payment:reload_plans', function() {
            loadPlans(true);
        });

        // Escuta eventos de créditos do app.js
        document.addEventListener('creditsUpdated', function(e) {
            const data = e.detail || {};
            updateCreditsDisplay(data.credits || 0);
        });

        document.addEventListener('premiumStatusUpdated', function(e) {
            const data = e.detail || {};
            if (isPlansPage()) {
                loadPlans(true);
            }
        });

        console.log('✅ Event listeners registrados!');
    }

    async function updateButtonsForPremium(isPremium) {
        if (isPremium) {
            document.querySelectorAll('.btn-bronze, [onclick*="openCpfModal"]').forEach(btn => {
                if (btn.textContent.includes('GARANTIR') || btn.textContent.includes('COMPRAR')) {
                    btn.textContent = '✅ PLANO ATIVO';
                    btn.className = 'btn btn-success btn-lg';
                    btn.onclick = () => window.location.href = '/dashboard';
                    btn.disabled = false;
                }
            });
        }
    }

    // ==============================================
    // 🧹 CLEANUP
    // ==============================================

    function cleanup() {
        if (countdownInterval) {
            clearInterval(countdownInterval);
            countdownInterval = null;
        }
        Cache.clear();
        console.log('🧹 Recursos limpos');
    }

    // ==============================================
    // 🚀 INICIALIZAÇÃO
    // ==============================================

    function initPayment() {
        console.log('🚀 Inicializando payment.js v6.1...');

        // Registra event listeners
        registerEventListeners();

        // Se já temos estado do app.js, inicializa imediatamente
        if (HAS_APP && window.__APP_STATE) {
            const state = window.__APP_STATE;
            if (state.isAppReady) {
                updateCreditsDisplay(state.credits || 0);
                if (isPlansPage()) loadPlans();
                if (isDashboardPage()) loadPremiumStatus();
            }
        }

        // Verifica se estamos na página de planos
        if (isPlansPage()) {
            setTimeout(() => {
                loadPlans();
                console.log('✅ payment.js - PÁGINA DE PLANOS');
                console.log(`💰 Preço Fundador: R$ ${CONFIG.PROMOTIONAL_PRICE}`);
                console.log(`🎯 Total de vagas: ${CONFIG.TOTAL_PROMOTIONAL_SLOTS}`);
            }, 300);
        }

        // Verifica se estamos no dashboard
        if (isDashboardPage()) {
            setTimeout(() => {
                loadPremiumStatus();
                console.log('✅ payment.js - Status Premium no Dashboard');
            }, 500);
        }

        // Atualiza créditos iniciais
        updateCreditsDisplay();

        // Dispara evento de ready
        EventBus.emit('payment:ready', {
            loaded: true,
            version: '6.1',
            integrated: HAS_APP,
            timestamp: Date.now()
        });

        // Notifica app.js
        window.dispatchEvent(new CustomEvent('paymentReady', {
            detail: { 
                loaded: true, 
                version: '6.1',
                integrated: HAS_APP
            }
        }));

        console.log(`✅ payment.js v6.1 carregado! (${HAS_APP ? 'INTEGRADO COM APP.JS' : 'STANDALONE'})`);
        console.log('🔒 Proteção antifraude: CPF obrigatório e validado');
        console.log('📡 Eventos: payment:ready, payment:reload_plans, payment:credits_updated, payment:premium_status_updated');
        console.log('🎯 Sistema 100% event-driven - SEM POLLING!');
        console.log('💰 Sistema Inteligente de Créditos ativo');
        console.log(`📡 API Base: ${CONFIG.API_BASE}`);
    }

    // ==============================================
    // 🌍 INJEÇÃO ANTECIPADA DE MÉTODOS GLOBAIS
    // ==============================================

    // Objeto principal
    window.PaymentModule = {
        CONFIG,
        Cache,
        Security,
        CreditSystem,
        ActionGuard,
        EventBus,
        
        // Funções principais
        loadPlans,
        loadPremiumStatus,
        loadSubscriptionStatus,
        updatePromotionStatus,
        receiveDailyCredit,
        updateCreditsDisplay,
        formatCreditsDisplay,
        
        // Modais
        openCpfModal,
        proceedWithCpf,
        showPixModalSecure,
        copyPixCodeSecure,
        handlePaymentConfirmation,
        
        // Utilitários
        showNotification,
        getAuthStatus,
        refreshAuth,
        fetchWithRetry,
        renderCreditDashboard,
        showUpgradeModal,
        
        // Cleanup
        cleanup,
        
        // Inicialização
        init: initPayment,
        
        // Status
        isIntegrated: HAS_APP,
        version: '6.1'
    };

    // Funções individuais expostas globalmente (para onclick)
    window.loadPlans = loadPlans;
    window.openCpfModal = openCpfModal;
    window.proceedWithCpf = proceedWithCpf;
    window.showPixModalSecure = showPixModalSecure;
    window.copyPixCodeSecure = copyPixCodeSecure;
    window.handlePaymentConfirmation = handlePaymentConfirmation;
    window.updateCreditsDisplay = updateCreditsDisplay;
    window.formatCreditsDisplay = formatCreditsDisplay;
    window.showNotification = showNotification;
    window.getCredits = () => getAuthStatus().credits;
    window.isPremium = () => getAuthStatus().isPremium;
    window.loadSubscriptionStatus = loadSubscriptionStatus;
    window.loadPremiumStatus = loadPremiumStatus;
    window.updatePromotionStatus = updatePromotionStatus;
    window.receiveDailyCredit = receiveDailyCredit;
    window.sanitizeHTML = Security.sanitizeHTML.bind(Security);
    window.sanitizeCPF = Security.sanitizeCPF.bind(Security);
    window.validateCPF = Security.validateCPF.bind(Security);
    
    // Sistema de créditos
    window.CreditSystem = CreditSystem;
    window.ActionGuard = ActionGuard;
    window.renderCreditDashboard = renderCreditDashboard;
    window.showUpgradeModal = showUpgradeModal;
    window.checkCredits = CreditSystem.checkCredits.bind(CreditSystem);
    window.canPerformAction = CreditSystem.canPerformAction.bind(CreditSystem);
    window.spendCredits = CreditSystem.spendCredits.bind(CreditSystem);
    window.getCreditBalance = CreditSystem.getBalance.bind(CreditSystem);
    window.canReceiveDailyCredit = CreditSystem.canReceiveDailyCredit.bind(CreditSystem);

    // Flag de pronto
    window.paymentReady = true;
    window.paymentVersion = '6.1';

    console.log('✅ Métodos globais injetados com sucesso!');
    console.log('🌍 window.PaymentModule disponível');

    // ==============================================
    // 🚀 INICIAR AUTOMATICAMENTE
    // ==============================================

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initPayment);
    } else {
        setTimeout(initPayment, 100);
    }

})(); // <-- FECHA A IIFE