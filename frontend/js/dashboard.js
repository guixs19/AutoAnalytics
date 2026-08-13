// frontend/js/dashboard.js - VERSÃO 16.8 (CORREÇÃO DE CRÉDITOS)
/**
 * 🔥 Dashboard Module - AutoAnalytics v16.8
 * 
 * ✅ NOVIDADES v16.8:
 * - 🔥 CORRIGIDO: NÃO CONSOLE créditos no upload (apenas verifica)
 * - 🔥 CORRIGIDO: CreditManager.consume() NÃO é chamado no upload
 * - 🔥 CORRIGIDO: Sincronização de créditos via /auth/me
 * - 🔥 CORRIGIDO: Evento analysis:success agora sincroniza
 * - 🔥 ADICIONADO: syncCredits() público para sincronização manual
 * 
 * ✅ MANTIDO v16.7:
 * - HISTÓRICO DE ANÁLISES: Mantém todos os arquivos processados
 * - ALTERNÂNCIA: Troca entre análises sem re-processar ML
 * - SELETOR DE ARQUIVOS: Interface para escolher qual análise ver
 * - SEM FALLBACK: Apenas dados reais do backend
 * - GPSA - Performance da Oficina (3 abas)
 * - 3 gráficos: Barras + Linha (Serviços) + Linha (Mensal)
 */

(function() {
    'use strict';

    // ==============================================
    // 🔥 CONFIGURAÇÕES
    // ==============================================

    const CONFIG = {
        MAX_FILES_PER_BATCH: 3,
        MAX_FILE_SIZE_KB: 200,
        API_BASE: '/api',
        POLLING_INTERVAL: 30000,
        CACHE_TTL: 300000,
        MAX_RETRIES: 3,
        RETRY_DELAY: 1000,
        POW_MAX_ATTEMPTS: 3,
        
        POLLING: {
            INTERVAL: 2000,
            MAX_ATTEMPTS: 60,
            TIMEOUT_MS: 120000,
            RETRY_DELAY: 1000,
        },
        
        CREDITS: {
            COST_PER_UPLOAD: 1,
            MAX_CREDITS_PREMIUM: 3,
            INITIAL_FREE_CREDITS: 3,
            SYNC_INTERVAL: 15000,
            UI_THROTTLE: 300,
            SYNC_DEBOUNCE: 500,
            AUTO_SYNC_DELAY: 1000,
        },
        
        COLORS: {
            primary: '#ff6b35',
            primaryLight: 'rgba(255,107,53,0.3)',
            primaryDark: '#e55a2b',
            success: '#48bb78',
            successLight: 'rgba(72,187,120,0.3)',
            warning: '#f5a623',
            warningLight: 'rgba(245,166,35,0.3)',
            danger: '#f56565',
            dangerLight: 'rgba(245,101,101,0.3)',
            secondary: '#4a9eff',
            secondaryLight: 'rgba(74,158,255,0.3)',
            tertiary: '#9b59b6',
            tertiaryLight: 'rgba(155,89,182,0.3)',
            background: 'rgba(255,255,255,0.05)',
            text: 'rgba(255,255,255,0.8)',
            textMuted: 'rgba(255,255,255,0.4)',
            grid: 'rgba(255,255,255,0.06)',
            border: 'rgba(255,255,255,0.08)',
        },
        
        CHART: {
            ANIMATION_DURATION: 800,
            ANIMATION_EASING: 'easeOutQuart',
            BAR_THICKNESS: 28,
            BAR_PERCENTAGE: 0.7,
            CATEGORY_PERCENTAGE: 0.8,
            FONT_SIZE: 10,
            LEGEND_PADDING: 12,
            LINE_TENSION: 0.4,
            POINT_RADIUS: 4,
        },
        
        TIMEOUTS: {
            UPLOAD: 120000,
            SYNC: 5000,
            TOAST: 5000,
        }
    };

    // ==============================================
    // 🔥 UTILITÁRIOS (SEM FALLBACK)
    // ==============================================

    const Utils = {
        sleep: (ms) => new Promise(resolve => setTimeout(resolve, ms)),
        
        getToken: () => {
            try {
                const token = localStorage.getItem('access_token');
                if (token && token.length > 10) return token;
                return null;
            } catch (e) {
                return null;
            }
        },

        isAuthenticated: () => {
            if (window.appAuth && typeof window.appAuth.isAuthenticated === 'function') {
                return window.appAuth.isAuthenticated();
            }
            return !!Utils.getToken();
        },

        formatCurrency: (value) => {
            if (value === undefined || value === null || isNaN(value)) return 'R$ 0,00';
            return 'R$ ' + value.toFixed(2).replace('.', ',');
        },

        formatCompactCurrency: (value) => {
            if (value === undefined || value === null || isNaN(value)) return 'R$ 0';
            if (value >= 1000000) return 'R$ ' + (value / 1000000).toFixed(1) + 'M';
            if (value >= 1000) return 'R$ ' + (value / 1000).toFixed(1) + 'k';
            return 'R$ ' + value.toFixed(0);
        },

        formatPercentage: (value) => {
            if (value === undefined || value === null || isNaN(value)) return '0%';
            return (value * 100).toFixed(0) + '%';
        },

        getHealthStatus: (score) => {
            if (score >= 0.7) return { status: 'excelente', color: '#48bb78', icon: '🟢', label: 'Excelente' };
            if (score >= 0.5) return { status: 'bom', color: '#4a9eff', icon: '🔵', label: 'Bom' };
            if (score >= 0.3) return { status: 'regular', color: '#f5a623', icon: '🟡', label: 'Regular' };
            return { status: 'critico', color: '#f56565', icon: '🔴', label: 'Crítico' };
        },

        debounce: (func, wait) => {
            let timeout;
            return function executedFunction(...args) {
                const later = () => {
                    clearTimeout(timeout);
                    func(...args);
                };
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
            };
        },

        // 🔥 SEM FALLBACK - apenas extrai dados reais
        extractChartData: (data) => {
            if (!data) {
                console.warn('⚠️ [extractChartData] Dados vazios');
                return null;
            }
            
            console.log('🔍 [extractChartData] Extraindo chart_data de:', Object.keys(data));
            
            let chartData = data.chart_data || 
                           data.result?.chart_data || 
                           data.analysis?.chart_data || 
                           data.data?.chart_data || 
                           null;
            
            if (chartData && !chartData.weekly && chartData.revenue) {
                console.log('📊 [extractChartData] Convertendo formato antigo para weekly');
                chartData = {
                    weekly: {
                        labels: chartData.labels || ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'],
                        revenue: chartData.revenue || [],
                        costs: chartData.costs || []
                    },
                    performance: chartData.performance || {},
                    monthly: chartData.monthly || {}
                };
            }
            
            if (chartData && chartData.weekly) {
                const hasData = chartData.weekly.revenue?.some(v => v > 0) || 
                               chartData.weekly.costs?.some(v => v > 0);
                
                if (!hasData) {
                    console.warn('⚠️ [extractChartData] Dados vazios - SEM FALLBACK');
                    return null;
                }
            }
            
            console.log('📊 [extractChartData] Resultado:', chartData ? '✅' : '❌');
            if (chartData) {
                console.log('   Weekly:', chartData.weekly ? '✅' : '❌');
                console.log('   Revenue:', chartData.weekly?.revenue?.length || 0, 'valores');
            }
            
            return chartData;
        },
    };

    // ==============================================
    // 🔥 CREDIT MANAGER (V16.8 - CORRIGIDO)
    // ==============================================

    class CreditManager {
        constructor() {
            this._balance = 0;
            this._isPremium = false;
            this._isAdmin = false;
            this._lastSync = 0;
            this._pendingRefund = 0;
            this._syncInProgress = false;
            this._initialized = false;
            
            this._updatingUI = false;
            this._lastUpdate = 0;
            this._uiThrottle = CONFIG.CREDITS.UI_THROTTLE;
            this._updateQueue = [];
            this._isProcessingQueue = false;
            this._cachedDisplay = null;
            this._cachedBalance = null;
            
            this._loadFromAppState();
            this._setupEventListeners();
            
            setTimeout(() => {
                this.sync(true).catch(() => {});
            }, CONFIG.CREDITS.AUTO_SYNC_DELAY);
            
            console.log('💰 [CreditManager] Inicializado');
        }

        _loadFromAppState() {
            console.log('🔄 [CreditManager] Carregando créditos...');
            
            try {
                if (window.__APP_STATE) {
                    const appCredits = window.__APP_STATE.credits;
                    if (appCredits !== undefined && appCredits !== null) {
                        this._balance = appCredits;
                        this._isPremium = window.__APP_STATE.isPremium || false;
                        this._isAdmin = window.__APP_STATE.isAdmin || false;
                        console.log(`💰 [CreditManager] App State: ${this._balance}`);
                        this._updateUI();
                        return true;
                    }
                }
            } catch (e) {}
            
            try {
                if (window.appAuth) {
                    if (typeof window.appAuth.getCredits === 'function') {
                        const authCredits = window.appAuth.getCredits();
                        if (authCredits !== undefined && authCredits !== null) {
                            this._balance = authCredits;
                            this._isPremium = window.appAuth.isPremium ? window.appAuth.isPremium() : false;
                            this._isAdmin = window.appAuth.isAdmin ? window.appAuth.isAdmin() : false;
                            console.log(`💰 [CreditManager] appAuth: ${this._balance}`);
                            this._updateUI();
                            return true;
                        }
                    }
                    if (window.appAuth.userData && window.appAuth.userData.credits !== undefined) {
                        this._balance = window.appAuth.userData.credits;
                        this._isPremium = window.appAuth.userData.is_premium || false;
                        this._isAdmin = window.appAuth.userData.is_admin || false;
                        console.log(`💰 [CreditManager] appAuth.userData: ${this._balance}`);
                        this._updateUI();
                        return true;
                    }
                }
            } catch (e) {}
            
            try {
                if (window.App && typeof window.App.getCredits === 'function') {
                    const appCredits = window.App.getCredits();
                    if (appCredits !== undefined && appCredits !== null) {
                        this._balance = appCredits;
                        this._isPremium = window.App.isPremium ? window.App.isPremium() : false;
                        this._isAdmin = window.App.isAdmin ? window.App.isAdmin() : false;
                        console.log(`💰 [CreditManager] App: ${this._balance}`);
                        this._updateUI();
                        return true;
                    }
                }
            } catch (e) {}
            
            try {
                const userData = localStorage.getItem('user_data');
                if (userData) {
                    const parsed = JSON.parse(userData);
                    if (parsed.credits !== undefined) {
                        this._balance = parsed.credits;
                        this._isPremium = parsed.is_premium || false;
                        this._isAdmin = parsed.is_admin || false;
                        console.log(`💰 [CreditManager] localStorage: ${this._balance}`);
                        this._updateUI();
                        return true;
                    }
                }
            } catch (e) {}
            
            console.log('⚠️ [CreditManager] Nenhuma fonte encontrada');
            return false;
        }

        _setupEventListeners() {
            // 🔥 V16.8: Só atualiza se o evento vier do backend
            document.addEventListener('creditsUpdated', (e) => {
                const data = e.detail || {};
                if (data._silent) return;
                
                // 🔥 Só atualiza se vier do backend ou for explicitamente permitido
                if (data._source === 'backend' || data._source === 'loadUserCredits') {
                    if (data.credits !== undefined) {
                        this._balance = data.credits;
                        this._isPremium = data.isPremium || false;
                        this._isAdmin = data.isAdmin || false;
                        this._updateUI();
                        console.log(`💰 [CreditManager] Atualizado via backend: ${this._balance}`);
                    }
                }
            });

            document.addEventListener('app:state_changed', (e) => {
                const data = e.detail || {};
                if (data.key === 'credits' || data.key === 'isPremium' || data.key === 'isAdmin') {
                    this._loadFromAppState();
                }
            });
            
            document.addEventListener('authLoginSuccess', (e) => {
                const data = e.detail || {};
                if (data.credits !== undefined) {
                    this._balance = data.credits;
                    this._isPremium = data.isPremium || false;
                    this._isAdmin = data.isAdmin || false;
                    this._updateUI();
                }
                setTimeout(() => this.sync(true), 500);
            });
            
            // 🔥 V16.8: analysis:success NÃO atualiza créditos diretamente
            document.addEventListener('analysis:success', (e) => {
                // 🔥 NÃO FAZ NADA COM CRÉDITOS AQUI!
                // Apenas força sincronização com o backend
                console.log('📊 [CreditManager] Análise concluída, sincronizando créditos...');
                setTimeout(() => this.sync(true), 800);
            });
            
            document.addEventListener('eligibility:updated', (e) => {
                const data = e.detail || {};
                if (data.credits_balance !== undefined) {
                    this._balance = data.credits_balance;
                    this._isPremium = data.is_premium || false;
                    this._isAdmin = data.is_admin || false;
                    this._updateUI();
                }
            });
            
            // 🔥 V16.8: upload:completed NÃO atualiza créditos diretamente
            document.addEventListener('upload:completed', (e) => {
                // 🔥 NÃO FAZ NADA COM CRÉDITOS AQUI!
                console.log('📤 [CreditManager] Upload concluído, sincronizando créditos...');
                setTimeout(() => this.sync(true), 500);
            });

            // 🔥 V16.8: Escuta evento de créditos consumidos pelo backend
            document.addEventListener('credits:consumed', (e) => {
                const data = e.detail || {};
                console.log(`💰 [CreditManager] Créditos consumidos pelo backend: ${data.amount}`);
                if (data.balance !== undefined) {
                    this._balance = data.balance;
                    this._updateUI();
                }
                setTimeout(() => this.sync(true), 300);
            });
        }

        get balance() { 
            if (window.__APP_STATE && window.__APP_STATE.credits !== undefined) {
                this._balance = window.__APP_STATE.credits;
            }
            return this._balance; 
        }
        
        get isPremium() { 
            if (window.__APP_STATE && window.__APP_STATE.isPremium !== undefined) {
                this._isPremium = window.__APP_STATE.isPremium;
            }
            return this._isPremium; 
        }
        
        get isAdmin() { 
            if (window.__APP_STATE && window.__APP_STATE.isAdmin !== undefined) {
                this._isAdmin = window.__APP_STATE.isAdmin;
            }
            return this._isAdmin; 
        }
        
        get display() {
            const balance = this.balance;
            const isAdmin = this.isAdmin;
            const isPremium = this.isPremium;
            
            if (isAdmin) return '∞';
            if (isPremium) {
                const maxCredits = CONFIG.CREDITS.MAX_CREDITS_PREMIUM;
                return `${Math.min(balance, maxCredits)}/${maxCredits}`;
            }
            return String(Math.max(0, balance));
        }

        // 🔥 V16.8: SYNC - Agora usa /auth/me corretamente
        async sync(force = false) {
            if (!force) {
                const loaded = this._loadFromAppState();
                if (loaded && this._balance > 0) {
                    console.log(`💰 [CreditManager] Cache: ${this._balance}`);
                    return this._balance;
                }
            }

            if (this._syncInProgress && !force) {
                console.log('⏳ [CreditManager] Sync em andamento');
                return this._balance;
            }
            
            this._syncInProgress = true;
            
            try {
                // 🔥 Primeiro tenta via appAuth
                if (window.appAuth && typeof window.appAuth.getCredits === 'function') {
                    const credits = window.appAuth.getCredits();
                    if (credits !== undefined && credits !== null) {
                        this._balance = credits;
                        this._isPremium = window.appAuth.isPremium ? window.appAuth.isPremium() : false;
                        this._isAdmin = window.appAuth.isAdmin ? window.appAuth.isAdmin() : false;
                        console.log(`💰 [CreditManager] Sync Auth: ${this._balance}`);
                        this._updateUI();
                        this._syncInProgress = false;
                        return this._balance;
                    }
                }
                
                // 🔥 Fallback: chamada direta ao /auth/me
                const token = Utils.getToken();
                if (!token) {
                    console.log('⏳ [CreditManager] Sem token');
                    this._syncInProgress = false;
                    return this._balance;
                }

                const response = await fetch('/api/auth/me', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });

                if (response.ok) {
                    const data = await response.json();
                    const newBalance = data.credits || 0;
                    const newIsPremium = data.is_premium || false;
                    const newIsAdmin = data.is_admin || false;
                    
                    const changed = (
                        newBalance !== this._balance ||
                        newIsPremium !== this._isPremium ||
                        newIsAdmin !== this._isAdmin
                    );
                    
                    if (changed) {
                        this._balance = newBalance;
                        this._isPremium = newIsPremium;
                        this._isAdmin = newIsAdmin;
                        this._lastSync = Date.now();
                        this._updateUI();
                        console.log(`💰 [CreditManager] Sync API: ${this._balance}`);
                    }
                    
                    this._syncInProgress = false;
                    return this._balance;
                } else if (response.status === 401) {
                    console.warn('⚠️ [CreditManager] Token expirado');
                    this._loadFromAppState();
                    this._updateUI();
                }
            } catch (e) {
                console.warn('⚠️ [CreditManager] Erro sync:', e);
                this._loadFromAppState();
                this._updateUI();
            } finally {
                this._syncInProgress = false;
            }
            return this._balance;
        }

        syncDebounced = Utils.debounce(() => {
            this.sync().catch(() => {});
        }, CONFIG.CREDITS.SYNC_DEBOUNCE);

        // 🔥 V16.8: hasCredits - APENAS VERIFICA, NÃO CONSOLE
        hasCredits(required = CONFIG.CREDITS.COST_PER_UPLOAD) {
            this._loadFromAppState();
            
            if (this.isAdmin) {
                console.log('👑 [CreditManager] Admin - ilimitado');
                return true;
            }
            
            const balance = this.balance;
            const hasEnough = balance >= required;
            
            console.log(`💰 [CreditManager] Verificando: ${balance} >= ${required} = ${hasEnough}`);
            
            // 🔥 V16.8: NÃO CONSOLE CRÉDITOS AQUI!
            // Apenas verifica e retorna
            // O consumo será feito pelo backend no final do ML
            
            return hasEnough;
        }

        canReceiveDaily() {
            if (this.isAdmin) return false;
            if (!this.isPremium) return false;
            
            if (window.__APP_STATE && window.__APP_STATE.canReceiveDailyCredit !== undefined) {
                return window.__APP_STATE.canReceiveDailyCredit;
            }
            
            return this.balance < CONFIG.CREDITS.MAX_CREDITS_PREMIUM;
        }

        // 🔥 V16.8: consume - NÃO DEVE SER CHAMADO NO UPLOAD!
        // Mantido apenas para compatibilidade, mas NÃO é usado no fluxo principal
        async consume(amount = CONFIG.CREDITS.COST_PER_UPLOAD, description = 'Upload') {
            console.warn('⚠️ [CreditManager] consume() não deve ser chamado no upload! O consumo é feito pelo backend.');
            console.warn('⚠️ [CreditManager] Este método está disponível apenas para compatibilidade.');
            
            if (this.isAdmin) {
                console.log('👑 Admin - créditos ilimitados');
                return { success: true, balance: '∞' };
            }

            await this.sync(true);
            
            const currentBalance = this.balance;
            
            if (!this.hasCredits(amount)) {
                return { 
                    success: false, 
                    error: 'Créditos insuficientes',
                    balance: currentBalance,
                    needed: amount,
                    canPurchase: true
                };
            }

            try {
                const token = Utils.getToken();
                if (!token) {
                    return { success: false, error: 'Token não encontrado' };
                }

                const response = await fetch('/api/credits/consume', {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ amount, description })
                });

                if (response.ok) {
                    const data = await response.json();
                    const before = this._balance;
                    this._balance = data.remaining || Math.max(0, before - amount);
                    this._updateUI();
                    
                    console.log(`💰 [CreditManager] Consumido: ${amount}, Saldo: ${this._balance}`);
                    
                    window.dispatchEvent(new CustomEvent('credits:consumed', {
                        detail: { amount, balance: this._balance, before, description }
                    }));
                    
                    return { 
                        success: true, 
                        balance: this._balance,
                        consumed: amount,
                        before: before
                    };
                } else {
                    const error = await response.json();
                    console.error('❌ [CreditManager] Erro no consumo:', error);
                    await this.sync(true);
                    return { 
                        success: false, 
                        error: error.message || 'Erro ao consumir créditos',
                        balance: this._balance
                    };
                }
            } catch (e) {
                console.error('❌ [CreditManager] Erro:', e);
                await this.sync(true);
                return { success: false, error: e.message, balance: this._balance };
            }
        }

        async refund(amount, description = 'Correção de créditos') {
            if (this.isAdmin || amount <= 0) return true;

            try {
                const token = Utils.getToken();
                if (!token) return false;

                const response = await fetch('/api/credits/add', {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ amount, description })
                });

                if (response.ok) {
                    const data = await response.json();
                    this._balance = data.balance || (this._balance + amount);
                    this._updateUI();
                    console.log(`💰 ${amount} crédito(s) devolvido(s): ${description}`);
                    
                    window.dispatchEvent(new CustomEvent('credits:refunded', {
                        detail: { amount, balance: this._balance, description }
                    }));
                    
                    return true;
                }
            } catch (e) {
                console.error('❌ Erro ao devolver créditos:', e);
            }
            return false;
        }

        _updateUI() {
            const now = Date.now();
            
            if (now - this._lastUpdate < this._uiThrottle) {
                if (!this._updateQueue.includes('update')) {
                    this._updateQueue.push('update');
                    setTimeout(() => this._processQueue(), this._uiThrottle);
                }
                return;
            }
            
            if (this._updatingUI) return;
            this._updatingUI = true;

            try {
                const display = this.display;
                const balance = this.balance;
                
                if (this._cachedDisplay === display && this._cachedBalance === balance) {
                    this._updatingUI = false;
                    return;
                }
                
                console.log(`🔄 [CreditManager] UI: ${display} (${balance})`);
                
                const selectors = [
                    '#creditsCount',
                    '#uploadCredits',
                    '#creditsDisplay',
                    '.credits-display',
                    '#modalCreditsCount',
                    '.credits-badge-nav span',
                    '.user-credits'
                ];
                
                let updated = false;
                selectors.forEach(selector => {
                    document.querySelectorAll(selector).forEach(el => {
                        if (el && el.textContent !== display) {
                            el.textContent = display;
                            updated = true;
                        }
                    });
                });
                
                const navbarCredits = document.getElementById('navbarCredits');
                if (navbarCredits) {
                    const span = navbarCredits.querySelector('span');
                    if (span && span.textContent !== display) {
                        span.textContent = display;
                        updated = true;
                    }
                }
                
                if (updated) {
                    this._cachedDisplay = display;
                    this._cachedBalance = balance;
                    this._lastUpdate = now;
                    
                    const event = new CustomEvent('creditsUpdated', {
                        detail: {
                            credits: balance,
                            display: display,
                            isPremium: this.isPremium,
                            isAdmin: this.isAdmin,
                            _silent: true,
                            _source: 'dashboard'
                        }
                    });
                    document.dispatchEvent(event);
                    
                    if (window.__APP_STATE_MANAGER) {
                        window.__APP_STATE_MANAGER.updateCredits(balance, this.isPremium);
                    }
                }
                
            } catch (e) {
                console.warn('⚠️ Erro ao atualizar UI de créditos:', e);
            } finally {
                this._updatingUI = false;
                this._lastUpdate = Date.now();
            }
        }

        _processQueue() {
            if (this._isProcessingQueue) return;
            this._isProcessingQueue = true;
            
            try {
                while (this._updateQueue.length > 0) {
                    this._updateQueue.shift();
                    this._updateUI();
                }
            } finally {
                this._isProcessingQueue = false;
            }
        }

        // 🔥 V16.8: Método público para sincronizar créditos
        async syncCredits() {
            return await this.sync(true);
        }
    }

    // ==============================================
    // 🔥 DASHBOARD - CLASSE PRINCIPAL (V16.8)
    // ==============================================

    class Dashboard {
        constructor() {
            this._initialized = false;
            this._uploadInProgress = false;
            this._pollingInterval = null;
            this._creditManager = new CreditManager();
            this._fileCache = new Map();
            this._analysisCache = new Map();
            
            // 🔥 Instâncias dos gráficos
            this._chartInstances = {
                revenue: null,
                performance: null,
                monthly: null
            };
            
            this._pendingChartData = null;
            
            this._pollingState = {
                active: false,
                processId: null,
                attempts: 0,
                startTime: null,
                timeoutId: null,
            };
            
            // 🔥 Histórico de análises
            this._analysisHistory = [];
            this._currentAnalysisId = null;
            this._isMultiFile = false;
            
            this.uploadMultipleFiles = this.uploadMultipleFiles.bind(this);
            this._processUploadResult = this._processUploadResult.bind(this);
            this._syncCredits = this._syncCredits.bind(this);
            this._handleCreditsUpdated = this._handleCreditsUpdated.bind(this);
            this._pollProgress = this._pollProgress.bind(this);
            this._stopPolling = this._stopPolling.bind(this);
            this._renderAllCharts = this._renderAllCharts.bind(this);
            this._handleChartDataReady = this._handleChartDataReady.bind(this);
            this._renderGPSA = this._renderGPSA.bind(this);
            this._switchAnalysis = this._switchAnalysis.bind(this);
            this._updateFileSelector = this._updateFileSelector.bind(this);
            this._createFileSelector = this._createFileSelector.bind(this);
            this._showAllFiles = this._showAllFiles.bind(this);
        }

        // ==========================================
        // 🔥 INICIALIZAÇÃO
        // ==========================================

        async init() {
            if (this._initialized) {
                console.log('ℹ️ [Dashboard] Já inicializado');
                return this;
            }

            console.log('🚀 [Dashboard v16.8] Inicializando com correção de créditos...');

            await this._creditManager.sync(true);
            
            this._setupEvents();
            this._setupUploadHandlers();
            this._setupPolling();
            this._setupChartListener();
            this._createFileSelector();
            
            const canvases = {
                revenue: document.getElementById('revenueChart'),
                performance: document.getElementById('performanceChart'),
                monthly: document.getElementById('monthlyChart')
            };
            
            console.log('📊 [Dashboard] Canvases:');
            console.log(`   revenueChart: ${canvases.revenue ? '✅' : '❌'}`);
            console.log(`   performanceChart: ${canvases.performance ? '✅' : '❌'}`);
            console.log(`   monthlyChart: ${canvases.monthly ? '✅' : '❌'}`);
            
            this._initialized = true;
            
            console.log('✅ [Dashboard v16.8] Inicializado com sucesso!');
            console.log(`   💰 Saldo: ${this._creditManager.display}`);
            console.log(`   🔥 Polling: ${CONFIG.POLLING.INTERVAL}ms / ${CONFIG.POLLING.MAX_ATTEMPTS} tentativas`);
            console.log(`   📊 3 gráficos + GPSA (Performance da Oficina)`);
            console.log(`   📁 Histórico de análises: ${this._analysisHistory.length} arquivos`);
            console.log(`   🔥 Sem fallback de dados - apenas dados reais do backend`);
            console.log(`   🔥 V16.8: NÃO CONSOLE créditos no upload`);
            
            return this;
        }

        // ==========================================
        // 🔥 MÉTODOS DE CRÉDITOS (PÚBLICOS)
        // ==========================================

        getCredits() {
            return this._creditManager.balance;
        }

        getCreditsDisplay() {
            return this._creditManager.display;
        }

        isPremium() {
            return this._creditManager.isPremium;
        }

        isAdmin() {
            return this._creditManager.isAdmin;
        }

        hasCredits(amount = 1) {
            return this._creditManager.hasCredits(amount);
        }

        async refreshCredits() {
            return await this._creditManager.sync(true);
        }

        // 🔥 V16.8: syncCredits - Sincroniza créditos com o backend
        async syncCredits() {
            return await this._creditManager.syncCredits();
        }

        // 🔥 V16.8: consumeCredits - NÃO DEVE SER USADO NO UPLOAD!
        async consumeCredits(amount = 1, description = 'Upload') {
            console.warn('⚠️ [Dashboard] consumeCredits não deve ser usado no upload!');
            return await this._creditManager.consume(amount, description);
        }

        // ==========================================
        // 🔥 SETUP CHART LISTENER
        // ==========================================

        _setupChartListener() {
            console.log('📊 [Dashboard] Configurando chart listeners...');
            
            document.removeEventListener('chart:data_ready', this._handleChartDataReady);
            document.removeEventListener('dashboard:render_chart', this._handleChartDataReady);
            window.removeEventListener('chart:data_ready', this._handleChartDataReady);
            window.removeEventListener('dashboard:render_chart', this._handleChartDataReady);
            
            document.addEventListener('chart:data_ready', this._handleChartDataReady);
            document.addEventListener('dashboard:render_chart', this._handleChartDataReady);
            window.addEventListener('chart:data_ready', this._handleChartDataReady);
            window.addEventListener('dashboard:render_chart', this._handleChartDataReady);
            
            console.log('📊 [Dashboard] Chart listeners configurados');
        }

        _handleChartDataReady(e) {
            const detail = e.detail || {};
            const chartData = detail.chart_data || detail;
            
            console.log('📊 [Dashboard] Evento chart:data_ready recebido');
            console.log('   ChartData:', chartData ? '✅' : '❌');
            console.log('   Weekly:', chartData?.weekly ? '✅' : '❌');
            
            if (chartData) {
                this._renderAllCharts(chartData);
                this._renderGPSA(chartData);
                
                const resultContainer = document.getElementById('resultContainer');
                if (resultContainer) {
                    resultContainer.classList.add('show');
                    resultContainer.style.display = 'block';
                }
                
                const placeholder = document.getElementById('resultPlaceholder');
                if (placeholder) {
                    placeholder.style.display = 'none';
                }
            } else {
                console.warn('⚠️ [Dashboard] chart_data inválido ou vazio - SEM FALLBACK');
            }
        }

        // ==========================================
        // 🔥 SETUP UPLOAD HANDLERS
        // ==========================================

        _setupUploadHandlers() {
            const fileInput = document.getElementById('fileInput');
            const dropArea = document.getElementById('dropArea');
            const uploadBtn = document.querySelector('.btn-select');

            if (uploadBtn) {
                uploadBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    if (fileInput) fileInput.click();
                });
            }

            if (fileInput) {
                fileInput.addEventListener('change', (e) => {
                    const files = Array.from(e.target.files);
                    if (files.length > 0) {
                        this.uploadMultipleFiles(files);
                    }
                    e.target.value = '';
                });
            }

            if (dropArea) {
                dropArea.addEventListener('dragover', (e) => {
                    e.preventDefault();
                    dropArea.classList.add('dragover');
                });

                dropArea.addEventListener('dragleave', (e) => {
                    e.preventDefault();
                    dropArea.classList.remove('dragover');
                });

                dropArea.addEventListener('drop', (e) => {
                    e.preventDefault();
                    dropArea.classList.remove('dragover');
                    const files = Array.from(e.dataTransfer.files);
                    if (files.length > 0) {
                        this.uploadMultipleFiles(files);
                    }
                });
            }
        }

        // ==========================================
        // 🔥 UPLOAD MÚLTIPLO (V16.8 - NÃO CONSOLE CRÉDITOS)
        // ==========================================

        async uploadMultipleFiles(files) {
            if (this._uploadInProgress) {
                this._showToast('⏳ Um upload já está em andamento. Aguarde.', 'warning');
                return null;
            }

            try {
                if (!Utils.isAuthenticated()) {
                    this._showToast('❌ Faça login para realizar uploads.', 'error');
                    return null;
                }

                if (!files || files.length === 0) {
                    this._showToast('⚠️ Selecione pelo menos um arquivo.', 'warning');
                    return null;
                }

                if (files.length > CONFIG.MAX_FILES_PER_BATCH) {
                    this._showToast(`⚠️ Máximo de ${CONFIG.MAX_FILES_PER_BATCH} arquivos por vez.`, 'warning');
                    return null;
                }

                for (const file of files) {
                    if (file.size > CONFIG.MAX_FILE_SIZE_KB * 1024) {
                        this._showToast(`⚠️ Arquivo ${file.name} excede ${CONFIG.MAX_FILE_SIZE_KB}KB.`, 'warning');
                        return null;
                    }
                }

                await this._creditManager.sync(true);
                
                // 🔥 V16.8: APENAS VERIFICA CRÉDITOS - NÃO CONSOLE!
                const hasCredits = this._creditManager.hasCredits(CONFIG.CREDITS.COST_PER_UPLOAD);
                console.log(`💰 [Dashboard] Verificação de créditos: ${hasCredits} (saldo: ${this._creditManager.balance})`);
                
                if (!hasCredits) {
                    this._showToast('❌ Créditos insuficientes. Adquira o plano Premium.', 'error');
                    this._showUpgradePrompt();
                    return null;
                }

                this._showUploadStatus('⏳', 'Preparando upload...', 'Verificando créditos', 5);
                this._uploadInProgress = true;

                const balanceBefore = this._creditManager.balance;
                console.log(`💰 Saldo antes: ${balanceBefore}`);

                const formData = new FormData();
                for (const file of files) {
                    formData.append('files', file);
                }
                formData.append('analysis_type', 'auto');
                formData.append('report_format', 'html');

                const token = Utils.getToken();
                let powHeaders = await this._getPowHeaders();

                this._showUploadStatus('⏳', 'Enviando arquivos...', `Processando ${files.length} arquivo(s)`, 30);

                const headers = {
                    'Authorization': `Bearer ${token}`,
                    'X-Files-Count': String(files.length),
                    ...powHeaders
                };

                // 🔥 V16.8: NÃO ENVIA X-Expected-Cost - O backend decide o custo
                const response = await fetch('/api/upload-multi-analyze', {
                    method: 'POST',
                    headers: headers,
                    body: formData
                });

                if (!response.ok) {
                    let errorDetail = 'Erro no upload';
                    try {
                        const errorData = await response.json();
                        errorDetail = errorData.detail?.message || errorData.message || errorDetail;
                    } catch (e) {}

                    if (response.status === 428) {
                        this._showUploadStatus('🔄', 'Renovando segurança...', 'Tentando novamente', 20);
                        await this._renewPow();
                        this._showToast('🔄 Tentando novamente com nova prova de trabalho...', 'info');
                        return this.uploadMultipleFiles(files);
                    }

                    if (response.status === 402) {
                        this._showUploadStatus('❌', 'Créditos insuficientes', 'Adquira o plano Premium', 0);
                        this._showToast('❌ Créditos insuficientes. Adquira o plano Premium.', 'error');
                        this._showUpgradePrompt();
                        await this._creditManager.sync(true);
                        return null;
                    }

                    throw new Error(errorDetail);
                }

                const result = await response.json();

                if (result.success && result.process_id) {
                    console.log(`📡 [Dashboard] Process ID: ${result.process_id}`);
                    
                    const pollingResult = await this._pollProgress(result.process_id);
                    
                    if (pollingResult.success && pollingResult.result) {
                        await this._processUploadResult({
                            success: true,
                            analysis: pollingResult.result,
                            chart_data: pollingResult.result.chart_data,
                            data: {
                                files: pollingResult.result.files || []
                            }
                        }, files);
                        
                        this._showUploadStatus('✅', 'Análise concluída!', 'Veja o relatório abaixo', 100);
                        this._showToast('✅ Upload concluído com sucesso!', 'success');
                        this._showResult();
                        
                        // 🔥 V16.8: Sincroniza créditos após conclusão
                        await this._creditManager.sync(true);
                    } else {
                        console.warn('⚠️ Polling falhou, usando resposta original');
                        await this._processUploadResult(result, files);
                        this._showToast('✅ Upload processado!', 'success');
                        this._showResult();
                    }
                } else {
                    await this._processUploadResult(result, files);
                    this._showUploadStatus('✅', 'Análise concluída!', 'Veja o relatório abaixo', 100);
                    this._showToast('✅ Upload concluído com sucesso!', 'success');
                    this._showResult();
                }

                await this._invalidateCache();
                this._fileCache.clear();

                this._uploadInProgress = false;
                return result;

            } catch (error) {
                console.error('❌ Erro no upload:', error);
                
                this._showUploadStatus('❌', 'Erro', error.message || 'Falha no processamento', 0);
                this._showToast(`❌ ${error.message || 'Erro ao processar'}`, 'error');
                
                try {
                    await this._creditManager.sync(true);
                } catch (e) {}

                this._uploadInProgress = false;
                this._stopPolling();
                return null;
            }
        }

        // ==========================================
        // 🔥 POLLING DE PROGRESSO
        // ==========================================

        async _pollProgress(processId) {
            console.log(`📡 [Polling] Iniciando para process_id: ${processId}`);
            
            this._stopPolling();
            this._pollingState = {
                active: true,
                processId: processId,
                attempts: 0,
                startTime: Date.now(),
                timeoutId: null,
            };
            
            let attempts = 0;
            const maxAttempts = CONFIG.POLLING.MAX_ATTEMPTS;
            const interval = CONFIG.POLLING.INTERVAL;
            
            this._showUploadStatus('🔄', 'Processando...', 'Iniciando análise', 10);
            
            return new Promise((resolve) => {
                const poll = async () => {
                    if (!this._pollingState.active) {
                        console.log('⏹️ [Polling] Interrompido pelo usuário');
                        resolve({ success: false, error: 'Interrompido' });
                        return;
                    }
                    
                    attempts++;
                    this._pollingState.attempts = attempts;
                    
                    const elapsed = Date.now() - this._pollingState.startTime;
                    if (elapsed > CONFIG.POLLING.TIMEOUT_MS) {
                        console.warn('⏰ [Polling] Timeout excedido');
                        this._showUploadStatus('⏳', 'Tempo limite', 'A análise está demorando mais que o esperado', 95);
                        this._showToast('⏳ A análise está demorando. Verifique o histórico.', 'warning');
                        this._stopPolling();
                        resolve({ success: false, error: 'Timeout' });
                        return;
                    }
                    
                    try {
                        const token = Utils.getToken();
                        if (!token) {
                            console.warn('⚠️ [Polling] Token expirado');
                            this._stopPolling();
                            resolve({ success: false, error: 'Token expirado' });
                            return;
                        }
                        
                        const response = await fetch(`/api/analysis/progress/${processId}`, {
                            headers: {
                                'Authorization': `Bearer ${token}`,
                                'Content-Type': 'application/json'
                            }
                        });
                        
                        if (!response.ok) {
                            if (response.status === 404) {
                                console.warn('⚠️ [Polling] Process ID não encontrado');
                                this._stopPolling();
                                resolve({ success: false, error: 'Processo não encontrado' });
                                return;
                            }
                            throw new Error(`Status: ${response.status}`);
                        }
                        
                        const data = await response.json();
                        console.log(`📡 [Polling] Tentativa ${attempts}: status=${data.status}, progress=${data.progress}%`);
                        
                        if (data.status === 'completed') {
                            console.log('✅ [Polling] Análise concluída!');
                            this._stopPolling();
                            this._showUploadStatus('✅', 'Análise concluída!', '100%', 100);
                            
                            const chartData = Utils.extractChartData(data);
                            if (chartData) {
                                console.log('📊 [Polling] ChartData extraído, renderizando...');
                                this._renderAllCharts(chartData);
                                this._renderGPSA(chartData);
                            } else {
                                console.warn('⚠️ [Polling] Nenhum chartData encontrado nos dados');
                            }
                            
                            resolve({
                                success: true,
                                result: data.result || data
                            });
                            return;
                            
                        } else if (data.status === 'processing') {
                            const progress = data.progress || 0;
                            const message = data.message || 'Processando...';
                            
                            this._showUploadStatus(
                                '🔄',
                                `Processando... ${progress}%`,
                                message,
                                progress
                            );
                            
                            const partialChartData = Utils.extractChartData(data);
                            if (partialChartData && partialChartData.weekly) {
                                console.log('📊 [Polling] Renderizando dados parciais');
                                this._renderAllCharts(partialChartData);
                                this._renderGPSA(partialChartData);
                            }
                            
                            setTimeout(poll, interval);
                            return;
                            
                        } else if (data.status === 'error') {
                            console.error('❌ [Polling] Erro no processamento:', data.message);
                            this._stopPolling();
                            this._showUploadStatus('❌', 'Erro', data.message || 'Falha no processamento', 0);
                            this._showToast(`❌ ${data.message || 'Erro no processamento'}`, 'error');
                            
                            resolve({
                                success: false,
                                error: data.message || 'Erro no processamento'
                            });
                            return;
                            
                        } else {
                            console.warn(`⚠️ [Polling] Status desconhecido: ${data.status}`);
                            
                            if (attempts >= maxAttempts) {
                                this._stopPolling();
                                this._showUploadStatus('⏳', 'Tempo limite', 'A análise está demorando mais que o esperado', 95);
                                this._showToast('⏳ A análise está demorando. Verifique o histórico.', 'warning');
                                
                                resolve({
                                    success: false,
                                    error: 'Timeout - análise demorou muito'
                                });
                                return;
                            }
                            
                            setTimeout(poll, interval);
                            return;
                        }
                        
                    } catch (error) {
                        console.error('❌ [Polling] Erro:', error);
                        
                        if (attempts < maxAttempts) {
                            console.log(`🔄 [Polling] Tentando novamente em ${CONFIG.POLLING.RETRY_DELAY}ms...`);
                            await Utils.sleep(CONFIG.POLLING.RETRY_DELAY);
                            poll();
                        } else {
                            this._stopPolling();
                            this._showUploadStatus('⚠️', 'Erro de comunicação', 'Tentando reconectar...', 50);
                            this._showToast('⚠️ Erro ao acompanhar progresso. Verifique o histórico.', 'warning');
                            
                            resolve({
                                success: false,
                                error: error.message || 'Erro de comunicação'
                            });
                        }
                    }
                };
                
                poll();
            });
        }

        // ==========================================
        // 🔥 PARAR POLLING
        // ==========================================

        _stopPolling() {
            if (this._pollingState.timeoutId) {
                clearTimeout(this._pollingState.timeoutId);
                this._pollingState.timeoutId = null;
            }
            this._pollingState.active = false;
            console.log('⏹️ [Polling] Parado');
        }

        // ==========================================
        // 🔥 RENDERIZAR TODOS OS GRÁFICOS (MANTIDO)
        // ==========================================

        _renderAllCharts(chartData) {
            if (!chartData) {
                console.warn('⚠️ [Charts] Nenhum dado para renderizar');
                return;
            }

            console.log('📊 [Charts] Renderizando 3 gráficos...');

            this._renderRevenueChart(chartData);
            this._renderPerformanceChart(chartData);
            this._renderMonthlyChart(chartData);

            console.log('✅ [Charts] Todos os gráficos renderizados!');
            
            window.dispatchEvent(new CustomEvent('dashboard:all_charts_rendered', {
                detail: {
                    charts: ['revenue', 'performance', 'monthly'],
                    timestamp: Date.now()
                }
            }));
        }

        // ==========================================
        // 🔥 GRÁFICO 1: RECEITA VS CUSTOS (BARRAS)
        // ==========================================

        _renderRevenueChart(chartData) {
            const canvas = document.getElementById('revenueChart');
            if (!canvas) {
                console.warn('⚠️ [Chart] Canvas #revenueChart não encontrado');
                return;
            }

            const weekly = chartData.weekly || chartData;
            const labels = weekly.labels || ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'];
            const revenue = weekly.revenue || [0, 0, 0, 0, 0, 0, 0];
            const costs = weekly.costs || [0, 0, 0, 0, 0, 0, 0];

            const hasData = revenue.some(v => v > 0) || costs.some(v => v > 0);
            
            if (!hasData) {
                console.warn('⚠️ [Chart] Dados vazios - SEM FALLBACK, não renderizando');
                return;
            }

            const ctx = canvas.getContext('2d');

            if (this._chartInstances.revenue) {
                try { this._chartInstances.revenue.destroy(); } catch (e) {}
                this._chartInstances.revenue = null;
            }

            this._chartInstances.revenue = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: '📊 Receita',
                            data: revenue,
                            backgroundColor: CONFIG.COLORS.primaryLight,
                            borderColor: CONFIG.COLORS.primary,
                            borderWidth: 2,
                            borderRadius: 6,
                            barThickness: CONFIG.CHART.BAR_THICKNESS,
                            barPercentage: CONFIG.CHART.BAR_PERCENTAGE,
                            categoryPercentage: CONFIG.CHART.CATEGORY_PERCENTAGE,
                            hoverBackgroundColor: CONFIG.COLORS.primary,
                            hoverBorderColor: CONFIG.COLORS.primaryDark,
                            hoverBorderWidth: 3,
                        },
                        {
                            label: '📉 Custos',
                            data: costs,
                            backgroundColor: CONFIG.COLORS.secondaryLight,
                            borderColor: CONFIG.COLORS.secondary,
                            borderWidth: 2,
                            borderRadius: 6,
                            barThickness: CONFIG.CHART.BAR_THICKNESS,
                            barPercentage: CONFIG.CHART.BAR_PERCENTAGE,
                            categoryPercentage: CONFIG.CHART.CATEGORY_PERCENTAGE,
                            hoverBackgroundColor: CONFIG.COLORS.secondary,
                            hoverBorderColor: '#3a7fd4',
                            hoverBorderWidth: 3,
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: { duration: CONFIG.CHART.ANIMATION_DURATION, easing: CONFIG.CHART.ANIMATION_EASING },
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        legend: {
                            position: 'top',
                            labels: {
                                color: CONFIG.COLORS.text,
                                font: { size: CONFIG.CHART.FONT_SIZE, weight: '500' },
                                padding: CONFIG.CHART.LEGEND_PADDING,
                                usePointStyle: true,
                                pointStyle: 'circle',
                            }
                        },
                        tooltip: {
                            backgroundColor: 'rgba(0,0,0,0.85)',
                            titleColor: '#fff',
                            titleFont: { size: 13, weight: '600' },
                            bodyColor: CONFIG.COLORS.text,
                            bodyFont: { size: 12 },
                            borderColor: 'rgba(255,255,255,0.1)',
                            borderWidth: 1,
                            cornerRadius: 10,
                            padding: 12,
                            usePointStyle: true,
                            callbacks: {
                                label: function(context) {
                                    return context.dataset.label + ': ' + Utils.formatCurrency(context.parsed.y);
                                }
                            }
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            grid: { color: CONFIG.COLORS.grid, drawBorder: false },
                            ticks: {
                                color: CONFIG.COLORS.textMuted,
                                font: { size: CONFIG.CHART.FONT_SIZE - 1 },
                                callback: function(value) { return Utils.formatCompactCurrency(value); },
                                maxTicksLimit: 8,
                            }
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: CONFIG.COLORS.textMuted, font: { size: CONFIG.CHART.FONT_SIZE } }
                        }
                    }
                }
            });

            console.log('✅ [Chart] Gráfico de barras renderizado');
        }

        // ==========================================
        // 🔥 GRÁFICO 2: SERVIÇOS SEMANAIS (LINHA)
        // ==========================================

        _renderPerformanceChart(chartData) {
            const canvas = document.getElementById('performanceChart');
            if (!canvas) {
                console.warn('⚠️ [Chart] Canvas #performanceChart não encontrado');
                return;
            }

            const performance = chartData.performance || {};
            const weekly = chartData.weekly || {};
            const labels = performance.labels || weekly.labels || ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'];
            const services = performance.services || weekly.services || [];

            if (!services.length || services.every(v => v === 0)) {
                console.warn('⚠️ [Chart] Dados de serviços vazios - SEM FALLBACK');
                return;
            }

            const ctx = canvas.getContext('2d');

            if (this._chartInstances.performance) {
                try { this._chartInstances.performance.destroy(); } catch (e) {}
                this._chartInstances.performance = null;
            }

            this._chartInstances.performance = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: '🔧 Serviços',
                        data: services,
                        borderColor: CONFIG.COLORS.secondary,
                        backgroundColor: CONFIG.COLORS.secondaryLight,
                        fill: true,
                        tension: CONFIG.CHART.LINE_TENSION,
                        pointBackgroundColor: CONFIG.COLORS.secondary,
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2,
                        pointRadius: CONFIG.CHART.POINT_RADIUS,
                        pointHoverRadius: CONFIG.CHART.POINT_RADIUS + 3,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: { duration: CONFIG.CHART.ANIMATION_DURATION, easing: CONFIG.CHART.ANIMATION_EASING },
                    plugins: {
                        legend: {
                            position: 'top',
                            labels: {
                                color: CONFIG.COLORS.text,
                                font: { size: CONFIG.CHART.FONT_SIZE, weight: '500' },
                                usePointStyle: true,
                                pointStyle: 'circle',
                            }
                        },
                        tooltip: {
                            backgroundColor: 'rgba(0,0,0,0.85)',
                            titleColor: '#fff',
                            bodyColor: CONFIG.COLORS.text,
                            borderColor: 'rgba(255,255,255,0.1)',
                            borderWidth: 1,
                            cornerRadius: 10,
                            padding: 12,
                            callbacks: { label: function(context) { return context.parsed.y + ' serviços'; } }
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            grid: { color: CONFIG.COLORS.grid, drawBorder: false },
                            ticks: { color: CONFIG.COLORS.textMuted, font: { size: CONFIG.CHART.FONT_SIZE - 1 }, stepSize: 1 }
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: CONFIG.COLORS.textMuted, font: { size: CONFIG.CHART.FONT_SIZE } }
                        }
                    }
                }
            });

            console.log('✅ [Chart] Gráfico de serviços renderizado');
        }

        // ==========================================
        // 🔥 GRÁFICO 3: EVOLUÇÃO MENSAL (LINHA)
        // ==========================================

        _renderMonthlyChart(chartData) {
            const canvas = document.getElementById('monthlyChart');
            if (!canvas) {
                console.warn('⚠️ [Chart] Canvas #monthlyChart não encontrado');
                return;
            }

            const monthly = chartData.monthly || {};
            const labels = monthly.labels || ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
            const revenue = monthly.revenue || [];

            if (!revenue.length || revenue.every(v => v === 0)) {
                console.warn('⚠️ [Chart] Dados mensais vazios - SEM FALLBACK');
                return;
            }

            const ctx = canvas.getContext('2d');

            if (this._chartInstances.monthly) {
                try { this._chartInstances.monthly.destroy(); } catch (e) {}
                this._chartInstances.monthly = null;
            }

            this._chartInstances.monthly = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: '💰 Receita Mensal',
                        data: revenue,
                        borderColor: CONFIG.COLORS.tertiary,
                        backgroundColor: CONFIG.COLORS.tertiaryLight,
                        fill: true,
                        tension: CONFIG.CHART.LINE_TENSION,
                        pointBackgroundColor: CONFIG.COLORS.tertiary,
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2,
                        pointRadius: CONFIG.CHART.POINT_RADIUS,
                        pointHoverRadius: CONFIG.CHART.POINT_RADIUS + 3,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: { duration: CONFIG.CHART.ANIMATION_DURATION, easing: CONFIG.CHART.ANIMATION_EASING },
                    plugins: {
                        legend: {
                            position: 'top',
                            labels: {
                                color: CONFIG.COLORS.text,
                                font: { size: CONFIG.CHART.FONT_SIZE, weight: '500' },
                                usePointStyle: true,
                                pointStyle: 'circle',
                            }
                        },
                        tooltip: {
                            backgroundColor: 'rgba(0,0,0,0.85)',
                            titleColor: '#fff',
                            bodyColor: CONFIG.COLORS.text,
                            borderColor: 'rgba(255,255,255,0.1)',
                            borderWidth: 1,
                            cornerRadius: 10,
                            padding: 12,
                            callbacks: { label: function(context) { return Utils.formatCurrency(context.parsed.y); } }
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            grid: { color: CONFIG.COLORS.grid, drawBorder: false },
                            ticks: {
                                color: CONFIG.COLORS.textMuted,
                                font: { size: CONFIG.CHART.FONT_SIZE - 1 },
                                callback: function(value) { return Utils.formatCompactCurrency(value); },
                                maxTicksLimit: 8,
                            }
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: CONFIG.COLORS.textMuted, font: { size: CONFIG.CHART.FONT_SIZE }, maxTicksLimit: 12 }
                        }
                    }
                }
            });

            console.log('✅ [Chart] Gráfico mensal renderizado');
        }

        // ==========================================
        // 🔥🔥🔥 GPSA - PERFORMANCE DA OFICINA (MANTIDO)
        // ==========================================

        _renderGPSA(chartData) {
            console.log('📊 [GPSA] Renderizando Performance da Oficina...');
            
            const tabsContainer = document.getElementById('gpsaTabs');
            const tabContent = document.getElementById('gpsaTabContent');
            const placeholder = document.getElementById('gpsaPlaceholder');
            const healthIndicator = document.getElementById('gpsaHealthIndicator');
            
            if (!tabsContainer || !tabContent) {
                console.warn('⚠️ [GPSA] Elementos não encontrados');
                return;
            }
            
            if (placeholder) {
                placeholder.style.display = 'none';
            }
            
            const weekly = chartData.weekly || {};
            const performance = chartData.performance || {};
            const monthly = chartData.monthly || {};
            
            const labels = weekly.labels || ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'];
            const revenue = weekly.revenue || [];
            const costs = weekly.costs || [];
            const services = performance.services || [];
            const monthlyRevenue = monthly.revenue || [];
            const monthlyLabels = monthly.labels || ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
            
            const totalRevenue = revenue.reduce((a, b) => a + b, 0);
            const totalCosts = costs.reduce((a, b) => a + b, 0);
            const totalServices = services.reduce((a, b) => a + b, 0);
            const profit = totalRevenue - totalCosts;
            const margin = totalRevenue > 0 ? (profit / totalRevenue) * 100 : 0;
            const avgServices = services.length > 0 ? Math.round(totalServices / services.length) : 0;
            const maxService = services.length > 0 ? Math.max(...services) : 0;
            const peakDay = services.length > 0 ? labels[services.indexOf(maxService)] : '-';
            const ticketMedio = totalServices > 0 ? totalRevenue / totalServices : 0;
            
            const score = Math.min(100, Math.max(0, Math.round(
                (margin > 30 ? 40 : margin > 15 ? 25 : 10) +
                (avgServices > 10 ? 30 : avgServices > 5 ? 20 : 10) +
                (totalServices > 50 ? 20 : totalServices > 20 ? 10 : 5) +
                (totalRevenue > 5000 ? 10 : 5)
            )));
            
            if (healthIndicator) {
                const status = this._getGPSAStatus(score);
                healthIndicator.innerHTML = `
                    <i class="fas fa-circle me-1" style="color: ${status.color}; font-size: 0.4rem;"></i>
                    ${status.icon} ${status.label} (${score}%)
                `;
                healthIndicator.style.background = status.bgColor;
                healthIndicator.style.color = status.textColor;
                healthIndicator.style.borderColor = status.borderColor;
            }
            
            const tabs = [
                {
                    id: 'gpsa-financeiro',
                    icon: 'fa-chart-bar',
                    label: '💰 Financeiro',
                    active: true,
                    content: this._renderGPSAFinanceiro(totalRevenue, totalCosts, profit, margin, ticketMedio, totalServices)
                },
                {
                    id: 'gpsa-servicos',
                    icon: 'fa-wrench',
                    label: '🔧 Serviços',
                    active: false,
                    content: this._renderGPSAServicos(labels, services, totalServices, avgServices, maxService, peakDay)
                },
                {
                    id: 'gpsa-tendencia',
                    icon: 'fa-chart-line',
                    label: '📈 Tendência',
                    active: false,
                    content: this._renderGPSATendencia(monthlyLabels, monthlyRevenue)
                }
            ];
            
            tabsContainer.innerHTML = tabs.map((tab, index) => `
                <li class="nav-item" role="presentation">
                    <button class="nav-link ${tab.active ? 'active' : ''}" 
                            id="${tab.id}-tab" 
                            data-bs-toggle="tab" 
                            data-bs-target="#${tab.id}" 
                            type="button" 
                            role="tab" 
                            style="color: rgba(255,255,255,0.6); border: none; background: transparent; padding: 0.4rem 1rem; font-size: 0.7rem; font-weight: 600; transition: all 0.3s;"
                            onmouseover="this.style.color='#ff6b35'"
                            onmouseout="this.style.color='rgba(255,255,255,0.6)'">
                        <i class="fas ${tab.icon}" style="margin-right: 0.3rem;"></i>
                        ${tab.label}
                    </button>
                </li>
            `).join('');
            
            tabContent.innerHTML = tabs.map((tab, index) => `
                <div class="tab-pane fade ${tab.active ? 'show active' : ''}" 
                     id="${tab.id}" 
                     role="tabpanel" 
                     aria-labelledby="${tab.id}-tab"
                     style="padding: 0.5rem 0;">
                    ${tab.content}
                </div>
            `).join('');
            
            const styleEl = document.getElementById('gpsa-tab-style');
            if (!styleEl) {
                const style = document.createElement('style');
                style.id = 'gpsa-tab-style';
                style.textContent = `
                    #gpsaTabs .nav-link.active {
                        color: #ff6b35 !important;
                        background: rgba(255,107,53,0.08) !important;
                        border-radius: 8px !important;
                    }
                    #gpsaTabs .nav-link {
                        border-radius: 8px !important;
                    }
                    #gpsaTabs .nav-link:hover {
                        color: #ff6b35 !important;
                        background: rgba(255,107,53,0.04) !important;
                    }
                    .gpsa-stat-card {
                        background: rgba(0,0,0,0.15);
                        border-radius: 10px;
                        padding: 0.6rem;
                        text-align: center;
                        border: 1px solid rgba(255,255,255,0.04);
                        transition: all 0.3s;
                    }
                    .gpsa-stat-card:hover {
                        background: rgba(255,107,53,0.06);
                        border-color: rgba(255,107,53,0.1);
                        transform: translateY(-2px);
                    }
                    .gpsa-stat-value {
                        font-size: 1.2rem;
                        font-weight: 800;
                        color: #ff6b35;
                        line-height: 1.2;
                    }
                    .gpsa-stat-label {
                        font-size: 0.55rem;
                        color: rgba(255,255,255,0.4);
                        text-transform: uppercase;
                        letter-spacing: 0.3px;
                        margin-top: 2px;
                    }
                    .gpsa-stat-value.success { color: #48bb78; }
                    .gpsa-stat-value.danger { color: #f56565; }
                    .gpsa-stat-value.warning { color: #f5a623; }
                    .gpsa-insight {
                        padding: 0.4rem 0.6rem;
                        background: rgba(0,0,0,0.1);
                        border-radius: 6px;
                        border-left: 3px solid #ff6b35;
                        font-size: 0.75rem;
                        color: rgba(255,255,255,0.7);
                        margin-bottom: 0.3rem;
                    }
                    .gpsa-insight:last-child { margin-bottom: 0; }
                    .gpsa-insight .icon { margin-right: 0.4rem; }
                `;
                document.head.appendChild(style);
            }
            
            console.log('✅ [GPSA] Renderizado com sucesso!');
        }

        // ==========================================
        // 🔥 GPSA - ABA FINANCEIRO
        // ==========================================

        _renderGPSAFinanceiro(totalRevenue, totalCosts, profit, margin, ticketMedio, totalServices) {
            const profitColor = profit >= 0 ? 'success' : 'danger';
            const marginColor = margin > 30 ? 'success' : margin > 15 ? 'warning' : 'danger';
            
            return `
                <div class="row g-2">
                    <div class="col-6 col-md-3">
                        <div class="gpsa-stat-card">
                            <div class="gpsa-stat-value">${Utils.formatCompactCurrency(totalRevenue)}</div>
                            <div class="gpsa-stat-label">📊 Receita Total</div>
                        </div>
                    </div>
                    <div class="col-6 col-md-3">
                        <div class="gpsa-stat-card">
                            <div class="gpsa-stat-value">${Utils.formatCompactCurrency(totalCosts)}</div>
                            <div class="gpsa-stat-label">📉 Custos Totais</div>
                        </div>
                    </div>
                    <div class="col-6 col-md-3">
                        <div class="gpsa-stat-card">
                            <div class="gpsa-stat-value ${profitColor}">${Utils.formatCompactCurrency(profit)}</div>
                            <div class="gpsa-stat-label">💰 Lucro</div>
                        </div>
                    </div>
                    <div class="col-6 col-md-3">
                        <div class="gpsa-stat-card">
                            <div class="gpsa-stat-value ${marginColor}">${margin.toFixed(1)}%</div>
                            <div class="gpsa-stat-label">📈 Margem</div>
                        </div>
                    </div>
                </div>
                <div class="row g-2 mt-1">
                    <div class="col-6 col-md-3">
                        <div class="gpsa-stat-card">
                            <div class="gpsa-stat-value">${Utils.formatCompactCurrency(ticketMedio)}</div>
                            <div class="gpsa-stat-label">🎫 Ticket Médio</div>
                        </div>
                    </div>
                    <div class="col-6 col-md-3">
                        <div class="gpsa-stat-card">
                            <div class="gpsa-stat-value">${totalServices}</div>
                            <div class="gpsa-stat-label">🔧 Total Serviços</div>
                        </div>
                    </div>
                    <div class="col-12 col-md-6">
                        <div class="gpsa-insight">
                            <span class="icon">💡</span>
                            ${margin > 30 ? 'Ótima margem! Sua oficina está muito saudável financeiramente.' :
                              margin > 15 ? 'Margem saudável. Continue monitorando custos.' :
                              'Margem abaixo do ideal. Reveja custos e precificação.'}
                        </div>
                        <div class="gpsa-insight">
                            <span class="icon">📌</span>
                            ${totalServices > 50 ? 'Alto volume de serviços. Mantenha a qualidade!' :
                              totalServices > 20 ? 'Bom volume de serviços. Busque crescer mais.' :
                              'Volume de serviços baixo. Invista em marketing e retenção.'}
                        </div>
                    </div>
                </div>
            `;
        }

        // ==========================================
        // 🔥 GPSA - ABA SERVIÇOS
        // ==========================================

        _renderGPSAServicos(labels, services, totalServices, avgServices, maxService, peakDay) {
            const daysWithServices = services.filter(s => s > 0).length;
            const weekdays = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'];
            const dayLabels = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'];
            
            const distribution = labels.map((label, i) => ({
                day: dayLabels[i] || label,
                short: label,
                value: services[i] || 0,
                percentage: totalServices > 0 ? ((services[i] || 0) / totalServices * 100) : 0
            }));
            
            const sorted = [...distribution].sort((a, b) => b.value - a.value);
            const topDay = sorted[0] || { day: '-', value: 0, percentage: 0 };
            
            return `
                <div class="row g-2">
                    <div class="col-6 col-md-3">
                        <div class="gpsa-stat-card">
                            <div class="gpsa-stat-value">${totalServices}</div>
                            <div class="gpsa-stat-label">🔧 Total Serviços</div>
                        </div>
                    </div>
                    <div class="col-6 col-md-3">
                        <div class="gpsa-stat-card">
                            <div class="gpsa-stat-value">${avgServices}</div>
                            <div class="gpsa-stat-label">📊 Média/Semana</div>
                        </div>
                    </div>
                    <div class="col-6 col-md-3">
                        <div class="gpsa-stat-card">
                            <div class="gpsa-stat-value">${maxService}</div>
                            <div class="gpsa-stat-label">🔥 Pico Diário</div>
                        </div>
                    </div>
                    <div class="col-6 col-md-3">
                        <div class="gpsa-stat-card">
                            <div class="gpsa-stat-value" style="color: #f5a623;">${peakDay}</div>
                            <div class="gpsa-stat-label">📅 Dia de Pico</div>
                        </div>
                    </div>
                </div>
                <div class="row g-2 mt-1">
                    <div class="col-12">
                        <div class="gpsa-insight">
                            <span class="icon">📊</span>
                            ${daysWithServices >= 7 ? 'Atendimento em todos os dias da semana!' :
                              daysWithServices >= 5 ? 'Boa distribuição de serviços durante a semana.' :
                              'Concentração de serviços em poucos dias. Considere distribuir melhor.'}
                        </div>
                        <div class="gpsa-insight">
                            <span class="icon">🎯</span>
                            ${topDay.value > avgServices * 1.5 ? 
                              `${topDay.day} tem ${topDay.percentage.toFixed(0)}% dos serviços. Aproveite esse dia para ações especiais.` :
                              'Distribuição equilibrada de serviços ao longo da semana.'}
                        </div>
                        <div style="margin-top: 0.3rem;">
                            ${distribution.map(d => `
                                <div style="display: flex; align-items: center; gap: 0.3rem; margin-bottom: 0.1rem; font-size: 0.6rem;">
                                    <span style="width: 40px; color: rgba(255,255,255,0.3);">${d.short}</span>
                                    <div style="flex: 1; height: 4px; background: rgba(255,255,255,0.04); border-radius: 4px; overflow: hidden;">
                                        <div style="height: 100%; width: ${d.percentage}%; background: linear-gradient(90deg, ${d.value > avgServices ? '#ff6b35' : '#4a9eff'}, ${d.value > avgServices ? '#f7931e' : '#6db3ff'}); border-radius: 4px;"></div>
                                    </div>
                                    <span style="width: 30px; text-align: right; color: rgba(255,255,255,0.5); font-weight: 600;">${d.value}</span>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>
            `;
        }

        // ==========================================
        // 🔥 GPSA - ABA TENDÊNCIA
        // ==========================================

        _renderGPSATendencia(monthlyLabels, monthlyRevenue) {
            const totalYear = monthlyRevenue.reduce((a, b) => a + b, 0);
            const avgMonth = monthlyRevenue.length > 0 ? totalYear / monthlyRevenue.length : 0;
            const maxMonth = monthlyRevenue.length > 0 ? Math.max(...monthlyRevenue) : 0;
            const minMonth = monthlyRevenue.length > 0 ? Math.min(...monthlyRevenue) : 0;
            const maxIdx = monthlyRevenue.indexOf(maxMonth);
            const minIdx = monthlyRevenue.indexOf(minMonth);
            
            const half = Math.floor(monthlyRevenue.length / 2);
            const firstHalf = monthlyRevenue.slice(0, half).reduce((a, b) => a + b, 0);
            const secondHalf = monthlyRevenue.slice(half).reduce((a, b) => a + b, 0);
            const growth = firstHalf > 0 ? ((secondHalf - firstHalf) / firstHalf * 100) : 0;
            
            const growthColor = growth > 10 ? 'success' : growth > -5 ? 'warning' : 'danger';
            const growthIcon = growth > 10 ? '📈' : growth > -5 ? '➡️' : '📉';
            
            return `
                <div class="row g-2">
                    <div class="col-6 col-md-3">
                        <div class="gpsa-stat-card">
                            <div class="gpsa-stat-value">${Utils.formatCompactCurrency(totalYear)}</div>
                            <div class="gpsa-stat-label">📊 Total Anual</div>
                        </div>
                    </div>
                    <div class="col-6 col-md-3">
                        <div class="gpsa-stat-card">
                            <div class="gpsa-stat-value">${Utils.formatCompactCurrency(avgMonth)}</div>
                            <div class="gpsa-stat-label">📅 Média Mensal</div>
                        </div>
                    </div>
                    <div class="col-6 col-md-3">
                        <div class="gpsa-stat-card">
                            <div class="gpsa-stat-value" style="color: #48bb78;">${Utils.formatCompactCurrency(maxMonth)}</div>
                            <div class="gpsa-stat-label">📈 Melhor Mês (${monthlyLabels[maxIdx] || '-'})</div>
                        </div>
                    </div>
                    <div class="col-6 col-md-3">
                        <div class="gpsa-stat-card">
                            <div class="gpsa-stat-value" style="color: #f56565;">${Utils.formatCompactCurrency(minMonth)}</div>
                            <div class="gpsa-stat-label">📉 Pior Mês (${monthlyLabels[minIdx] || '-'})</div>
                        </div>
                    </div>
                </div>
                <div class="row g-2 mt-1">
                    <div class="col-12">
                        <div class="gpsa-insight">
                            <span class="icon">${growthIcon}</span>
                            <strong>Crescimento:</strong> ${growth > 0 ? '+' : ''}${growth.toFixed(1)}% 
                            ${growth > 10 ? '🚀 Excelente crescimento!' :
                              growth > 0 ? '📈 Crescimento positivo' :
                              growth > -5 ? '📊 Estabilidade' :
                              '⚠️ Queda detectada. Revise estratégias.'}
                        </div>
                        <div class="gpsa-insight">
                            <span class="icon">📌</span>
                            <strong>Variação:</strong> ${Utils.formatCompactCurrency(maxMonth - minMonth)} entre melhor e pior mês 
                            (${((maxMonth - minMonth) / (minMonth || 1) * 100).toFixed(0)}% de diferença)
                        </div>
                        <div style="display: flex; gap: 0.1rem; margin-top: 0.3rem; align-items: flex-end; height: 40px;">
                            ${monthlyRevenue.map((val, i) => {
                                const height = Math.max(3, (val / (maxMonth || 1)) * 35);
                                const isMax = val === maxMonth;
                                const isMin = val === minMonth;
                                return `
                                    <div style="flex: 1; display: flex; flex-direction: column; align-items: center; gap: 0.05rem;">
                                        <div style="height: ${height}px; width: 100%; background: ${isMax ? '#ff6b35' : isMin ? '#f56565' : 'rgba(74,158,255,0.5)'}; border-radius: 2px 2px 0 0; transition: all 0.3s;"></div>
                                        <span style="font-size: 0.4rem; color: rgba(255,255,255,0.2);">${monthlyLabels[i] || ''}</span>
                                    </div>
                                `;
                            }).join('')}
                        </div>
                    </div>
                </div>
            `;
        }

        // ==========================================
        // 🔥 GPSA - STATUS DE SAÚDE
        // ==========================================

        _getGPSAStatus(score) {
            if (score >= 80) {
                return {
                    label: 'Excelente',
                    icon: '🟢',
                    color: '#48bb78',
                    bgColor: 'rgba(72,187,120,0.12)',
                    textColor: '#48bb78',
                    borderColor: 'rgba(72,187,120,0.2)'
                };
            } else if (score >= 60) {
                return {
                    label: 'Bom',
                    icon: '🔵',
                    color: '#4a9eff',
                    bgColor: 'rgba(74,158,255,0.12)',
                    textColor: '#4a9eff',
                    borderColor: 'rgba(74,158,255,0.2)'
                };
            } else if (score >= 40) {
                return {
                    label: 'Regular',
                    icon: '🟡',
                    color: '#f5a623',
                    bgColor: 'rgba(245,166,35,0.12)',
                    textColor: '#f5a623',
                    borderColor: 'rgba(245,166,35,0.2)'
                };
            } else {
                return {
                    label: 'Atenção',
                    icon: '🔴',
                    color: '#f56565',
                    bgColor: 'rgba(245,101,101,0.12)',
                    textColor: '#f56565',
                    borderColor: 'rgba(245,101,101,0.2)'
                };
            }
        }

        // ==========================================
        // 🔥🔥🔥 PROCESSAR RESULTADO DO UPLOAD (COM HISTÓRICO)
        // ==========================================

        async _processUploadResult(result, files) {
            if (!result || !result.success) {
                console.warn('⚠️ Resultado inválido:', result);
                return;
            }

            const analysis = result.analysis || {};
            const chartData = Utils.extractChartData(result);
            const recommendations = analysis.recommendations || result.recommendations || [];
            const executiveScore = analysis.executive_score || result.executive_score || {};
            const executiveSummary = analysis.executive_summary || result.executive_summary || '';

            console.log('📊 [ProcessResult] chartData:', chartData ? '✅' : '❌');

            const filesList = result.data?.files || [];
            const isMultiFile = filesList.length > 1;

            console.log(`📁 [ProcessResult] ${filesList.length} arquivo(s) encontrado(s)`);

            if (isMultiFile && chartData) {
                this._isMultiFile = true;
                this._analysisHistory = filesList.map((file, index) => ({
                    id: file.process_id || file.id || `file-${index}`,
                    filename: file.filename || `Arquivo ${index + 1}`,
                    rows: file.rows || 0,
                    chart_data: file.chart_data || chartData,
                    metrics: file.metrics || {},
                    recommendations: file.recommendations || recommendations,
                    insights: file.insights || {},
                    executive_score: file.executive_score || executiveScore,
                    executive_summary: file.executive_summary || executiveSummary,
                    isActive: index === 0,
                    success: file.success || false
                }));

                this._currentAnalysisId = this._analysisHistory[0].id;
                
                console.log(`📁 [ProcessResult] ${this._analysisHistory.length} arquivos no histórico`);
            } else {
                this._isMultiFile = false;
                this._analysisHistory = [{
                    id: result.process_id || Date.now(),
                    filename: files[0]?.name || 'Análise',
                    rows: result.rows_processed || 0,
                    chart_data: chartData,
                    metrics: result.metrics || {},
                    recommendations: recommendations,
                    insights: analysis.insights || {},
                    executive_score: executiveScore,
                    executive_summary: executiveSummary,
                    isActive: true,
                    success: true
                }];
                this._currentAnalysisId = this._analysisHistory[0].id;
            }

            const currentAnalysis = this._getCurrentAnalysis();
            if (currentAnalysis && currentAnalysis.chart_data) {
                console.log('📊 [ProcessResult] Renderizando gráficos da análise atual');
                this._renderAllCharts(currentAnalysis.chart_data);
                this._renderGPSA(currentAnalysis.chart_data);
            } else {
                console.warn('⚠️ [ProcessResult] Sem dados para renderizar');
            }

            this._updateFileSelector();

            await this._updateAIReport({
                executive_score: executiveScore,
                executive_summary: executiveSummary,
                recommendations: recommendations,
                chart_data: chartData || {},
                forecast: analysis.forecast || '',
                general_conclusion: analysis.general_conclusion || '',
                comparison: analysis.comparison || {},
                trend: analysis.trend || {}
            });

            await this._updateMetrics({
                executive_score: executiveScore,
                chart_data: chartData || {}
            });

            if (result.data?.files && result.data.files.length > 0) {
                const analyses = result.data.files.map((file, index) => ({
                    filename: file.filename || `Arquivo ${index + 1}`,
                    success: file.success || false,
                    rows_processed: file.rows || 0,
                    metrics: {
                        mean_prediction: file.metrics?.mean_prediction || 0.5,
                        high_risk_percentage: file.metrics?.high_risk_percentage || 0,
                        low_risk_percentage: file.metrics?.low_risk_percentage || 0
                    },
                    chart_data: file.chart_data || chartData,
                    insights: {
                        summary: { mean: file.metrics?.mean_prediction || 0.5 },
                        risk_distribution: {
                            high_percentage: file.metrics?.high_risk_percentage || 0,
                            low_percentage: file.metrics?.low_risk_percentage || 0
                        }
                    },
                    recommendations: file.recommendations || recommendations,
                    predictions: file.predictions || [],
                    model_used: file.model_used || 'AutoML'
                }));

                const tabManager = this._getTabManager();
                if (tabManager) {
                    tabManager.renderTabs(analyses);
                }
            }

            try {
                const recent = JSON.parse(localStorage.getItem('recentAnalyses') || '[]');
                recent.unshift({
                    filename: files.map(f => f.name).join(', '),
                    timestamp: Date.now(),
                    result: result,
                    isMultiFile: isMultiFile,
                    files: this._analysisHistory.map(a => ({
                        filename: a.filename,
                        rows: a.rows
                    }))
                });
                if (recent.length > 10) recent.pop();
                localStorage.setItem('recentAnalyses', JSON.stringify(recent));
            } catch (e) {}

            document.dispatchEvent(new CustomEvent('analysis:success', {
                detail: { result: result }
            }));

            console.log('✅ Upload processado com sucesso!');
        }

        // ==========================================
        // 🔥 OBTER ANÁLISE ATUAL
        // ==========================================

        _getCurrentAnalysis() {
            return this._analysisHistory.find(a => a.id === this._currentAnalysisId) || this._analysisHistory[0];
        }

        // ==========================================
        // 🔥 ALTERNAR ANÁLISE
        // ==========================================

        _switchAnalysis(analysisId) {
            if (analysisId === this._currentAnalysisId) return;

            console.log(`🔄 [Dashboard] Alternando para análise: ${analysisId}`);

            this._analysisHistory.forEach(a => {
                a.isActive = a.id === analysisId;
            });
            this._currentAnalysisId = analysisId;

            const analysis = this._getCurrentAnalysis();
            if (!analysis) return;

            console.log(`📊 [Dashboard] Carregando análise: ${analysis.filename}`);

            this._updateFileSelector();

            if (analysis.chart_data) {
                this._renderAllCharts(analysis.chart_data);
                this._renderGPSA(analysis.chart_data);
            } else {
                console.warn('⚠️ [Dashboard] Análise sem chart_data');
            }

            this._updateAIReport({
                executive_score: analysis.executive_score || {},
                executive_summary: analysis.executive_summary || '',
                recommendations: analysis.recommendations || [],
                chart_data: analysis.chart_data || {},
                forecast: '',
                general_conclusion: '',
                comparison: {},
                trend: {}
            });

            this._updateMetrics({
                executive_score: analysis.executive_score || {},
                chart_data: analysis.chart_data || {}
            });

            const filenameEl = document.getElementById('resultFilename');
            if (filenameEl) {
                filenameEl.textContent = analysis.filename || 'Análise';
            }

            console.log(`✅ [Dashboard] Alternado para: ${analysis.filename}`);
        }

        // ==========================================
        // 🔥 ATUALIZAR SELETOR DE ARQUIVOS
        // ==========================================

        _updateFileSelector() {
            const container = document.getElementById('analysisSelector');
            if (!container) {
                this._createFileSelector();
                return;
            }

            if (this._analysisHistory.length <= 1) {
                container.style.display = 'none';
                return;
            }

            container.style.display = 'block';

            let html = `
                <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; padding: 0.2rem 0;">
                    <span style="font-size: 0.6rem; color: rgba(255,255,255,0.3); text-transform: uppercase; letter-spacing: 0.3px; font-weight: 600;">
                        📁 Arquivos:
                    </span>
            `;

            this._analysisHistory.forEach((analysis) => {
                const isActive = analysis.isActive;
                const status = analysis.success ? '✅' : '❌';
                const filename = analysis.filename.length > 28 
                    ? analysis.filename.substring(0, 25) + '...' 
                    : analysis.filename;

                html += `
                    <button class="analysis-selector-btn ${isActive ? 'active' : ''}" 
                            data-analysis-id="${analysis.id}"
                            style="
                                padding: 0.2rem 0.8rem;
                                border-radius: 20px;
                                border: 1px solid ${isActive ? '#ff6b35' : 'rgba(255,255,255,0.08)'};
                                background: ${isActive ? 'rgba(255,107,53,0.15)' : 'rgba(255,255,255,0.03)'};
                                color: ${isActive ? '#ff6b35' : 'rgba(255,255,255,0.5)'};
                                font-size: 0.65rem;
                                font-weight: ${isActive ? '700' : '400'};
                                cursor: pointer;
                                transition: all 0.3s;
                                display: inline-flex;
                                align-items: center;
                                gap: 0.3rem;
                                font-family: inherit;
                            "
                            onmouseover="this.style.borderColor='#ff6b35'; this.style.background='rgba(255,107,53,0.08)'"
                            onmouseout="this.style.borderColor='${isActive ? '#ff6b35' : 'rgba(255,255,255,0.08)'}'; this.style.background='${isActive ? 'rgba(255,107,53,0.15)' : 'rgba(255,255,255,0.03)'}'"
                            onclick="window.__dashboard?._switchAnalysis('${analysis.id}')">
                        ${status} ${filename}
                        <span style="font-size: 0.5rem; color: rgba(255,255,255,0.2);">
                            ${analysis.rows} registros
                        </span>
                    </button>
                `;
            });

            html += `
                    <button class="analysis-selector-btn" 
                            style="
                                padding: 0.2rem 0.6rem;
                                border-radius: 20px;
                                border: none;
                                background: rgba(255,255,255,0.03);
                                color: rgba(255,255,255,0.2);
                                font-size: 0.6rem;
                                cursor: pointer;
                                transition: all 0.3s;
                                font-family: inherit;
                            "
                            onmouseover="this.style.color='rgba(255,255,255,0.5)'"
                            onmouseout="this.style.color='rgba(255,255,255,0.2)'"
                            onclick="window.__dashboard?._showAllFiles()"
                            title="Ver todos os arquivos">
                        <i class="fas fa-expand"></i>
                    </button>
                </div>
            `;

            container.innerHTML = html;
        }

        // ==========================================
        // 🔥 CRIAR SELETOR DE ARQUIVOS
        // ==========================================

        _createFileSelector() {
            if (document.getElementById('analysisSelector')) return;

            const resultCard = document.getElementById('resultCard');
            if (!resultCard) return;

            const container = document.createElement('div');
            container.id = 'analysisSelector';
            container.style.cssText = `
                display: none;
                padding: 0.2rem 0.5rem;
                margin-bottom: 0.3rem;
                background: rgba(255,255,255,0.02);
                border-radius: 10px;
                border: 1px solid rgba(255,255,255,0.04);
            `;

            const resultContainer = document.getElementById('resultContainer');
            if (resultContainer) {
                resultCard.insertBefore(container, resultContainer);
            } else {
                resultCard.appendChild(container);
            }
        }

        // ==========================================
        // 🔥 MOSTRAR TODOS OS ARQUIVOS
        // ==========================================

        _showAllFiles() {
            if (this._analysisHistory.length <= 1) return;

            let html = `
                <div style="padding: 0.5rem;">
                    <h6 style="color: #ff6b35; font-size: 0.9rem; margin-bottom: 0.5rem; display: flex; align-items: center; gap: 0.5rem;">
                        <span>📁 ${this._analysisHistory.length} arquivos analisados</span>
                        <span style="font-size: 0.6rem; color: rgba(255,255,255,0.2); font-weight: 400;">
                            clique para alternar
                        </span>
                    </h6>
                    <div style="display: grid; gap: 0.3rem;">
            `;

            this._analysisHistory.forEach((analysis) => {
                const status = analysis.success ? '✅' : '❌';
                const isActive = analysis.isActive;
                html += `
                    <div style="
                        display: flex;
                        align-items: center;
                        justify-content: space-between;
                        padding: 0.3rem 0.6rem;
                        background: ${isActive ? 'rgba(255,107,53,0.06)' : 'rgba(255,255,255,0.02)'};
                        border-radius: 6px;
                        border-left: 3px solid ${isActive ? '#ff6b35' : 'transparent'};
                        cursor: pointer;
                        transition: all 0.3s;
                    "
                    onclick="window.__dashboard?._switchAnalysis('${analysis.id}')"
                    onmouseover="this.style.background='rgba(255,255,255,0.05)'"
                    onmouseout="this.style.background='${isActive ? 'rgba(255,107,53,0.06)' : 'rgba(255,255,255,0.02)'}'">
                        <span style="font-size: 0.75rem; color: rgba(255,255,255,0.7); display: flex; align-items: center; gap: 0.4rem;">
                            ${status} 
                            <span style="font-weight: ${isActive ? '600' : '400'};">${analysis.filename}</span>
                        </span>
                        <span style="font-size: 0.6rem; color: rgba(255,255,255,0.2); display: flex; align-items: center; gap: 0.5rem;">
                            ${analysis.rows} registros
                            ${isActive ? '<span style="color: #ff6b35; font-size: 0.5rem; font-weight: 600;">👈 ATUAL</span>' : ''}
                        </span>
                    </div>
                `;
            });

            html += `
                    </div>
                    <div style="margin-top: 0.5rem; text-align: center; font-size: 0.55rem; color: rgba(255,255,255,0.15);">
                        Clique em qualquer arquivo para ver seus gráficos
                    </div>
                </div>
            `;

            if (window.toastr) {
                toastr.info(html, '📁 Arquivos Analisados', {
                    timeOut: 0,
                    closeButton: true,
                    extendedTimeOut: 0,
                    enableHtml: true,
                    positionClass: 'toast-top-center',
                    progressBar: false,
                    tapToDismiss: false,
                    newestOnTop: false
                });
            } else {
                alert(html.replace(/<[^>]*>/g, ''));
            }
        }

        // ==========================================
        // 🔥 ATUALIZAR RELATÓRIO DA IA (MANTIDO)
        // ==========================================

        async _updateAIReport(data) {
            const reportContainer = document.getElementById('aiReportContent');
            if (!reportContainer) return;

            const {
                executive_score,
                executive_summary,
                recommendations,
                chart_data,
                forecast,
                general_conclusion,
                comparison,
                trend
            } = data;

            let html = '';

            if (executive_score && Object.keys(executive_score).length > 0) {
                const scoreItems = [
                    { key: 'nota_geral', label: 'Nota Geral', icon: '🏆' },
                    { key: 'saude_financeira', label: 'Saúde Financeira', icon: '💰' },
                    { key: 'eficiencia', label: 'Eficiência', icon: '⚡' },
                    { key: 'controle_custos', label: 'Controle de Custos', icon: '📊' },
                    { key: 'crescimento', label: 'Crescimento', icon: '📈' },
                    { key: 'nivel_risco', label: 'Nível de Risco', icon: '🛡️' }
                ];

                html += `
                    <div style="margin-bottom: 1rem;">
                        <strong style="color: #ff6b35;">🏆 Score Executivo</strong>
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(100px, 1fr)); gap: 0.5rem; margin-top: 0.5rem;">
                            ${scoreItems.map(({ key, label, icon }) => {
                                const value = executive_score[key];
                                if (value === undefined || value === null) return '';
                                
                                const isNumber = typeof value === 'number';
                                const color = isNumber ? 
                                    (value >= 7 ? '#48bb78' : value >= 5 ? '#f5a623' : '#f56565') : 
                                    (value === 'Baixo' ? '#48bb78' : value === 'Moderado' ? '#f5a623' : '#f56565');
                                
                                return `
                                    <div style="background: rgba(0,0,0,0.1); padding: 0.3rem; border-radius: 8px; text-align: center; border: 1px solid rgba(255,255,255,0.03);">
                                        <div style="font-size: 0.4rem; color: rgba(255,255,255,0.3); text-transform: uppercase;">${label}</div>
                                        <div style="font-size: 0.9rem; font-weight: 700; color: ${color};">${icon} ${isNumber ? value.toFixed(1) : value}</div>
                                    </div>
                                `;
                            }).join('')}
                        </div>
                    </div>
                `;
            }

            if (executive_summary) {
                html += `
                    <div style="margin-bottom: 0.8rem; padding: 0.8rem; background: rgba(255,107,53,0.05); border-radius: 8px; border-left: 3px solid #ff6b35;">
                        <strong style="color: #ff6b35;">📋 Resumo Executivo</strong>
                        <div style="font-size: 0.8rem; color: rgba(255,255,255,0.7); margin-top: 0.3rem; line-height: 1.5;">
                            ${executive_summary}
                        </div>
                    </div>
                `;
            }

            if (recommendations && recommendations.length > 0) {
                const priorityColors = { alta: '#f56565', media: '#f5a623', baixa: '#48bb78' };
                const priorityEmojis = { alta: '🔴', media: '🟡', baixa: '🟢' };

                html += `
                    <div style="margin-bottom: 0.8rem;">
                        <strong style="color: #ff6b35;">🎯 Recomendações</strong>
                        <ul style="margin: 0.3rem 0 0 0; padding-left: 0; list-style: none; font-size: 0.75rem; color: rgba(255,255,255,0.6);">
                            ${recommendations.slice(0, 5).map(r => {
                                const priority = r.priority || 'media';
                                const color = priorityColors[priority] || '#ff6b35';
                                const emoji = priorityEmojis[priority] || '📌';
                                const desc = r.description || r;
                                return `
                                    <li style="padding: 0.2rem 0.4rem; border-bottom: 1px solid rgba(255,255,255,0.03); display: flex; align-items: flex-start; gap: 0.5rem;">
                                        <span style="color: ${color}; font-size: 0.6rem; margin-top: 0.1rem;">${emoji}</span>
                                        <div>${typeof desc === 'string' ? desc : desc.description || ''}</div>
                                    </li>
                                `;
                            }).join('')}
                        </ul>
                    </div>
                `;
            }

            if (trend && trend.description) {
                const directionEmoji = trend.direction === 'crescente' ? '📈' : 
                                       trend.direction === 'decrescente' ? '📉' : '➡️';
                const color = trend.direction === 'crescente' ? '#48bb78' : 
                              trend.direction === 'decrescente' ? '#f56565' : '#f5a623';
                
                html += `
                    <div style="margin-bottom: 0.8rem; padding: 0.6rem; background: rgba(245,166,35,0.05); border-radius: 8px; border-left: 3px solid ${color};">
                        <strong style="color: ${color};">${directionEmoji} Tendência: ${trend.direction?.charAt(0).toUpperCase() + trend.direction?.slice(1) || 'Estável'}</strong>
                        <div style="font-size: 0.75rem; color: rgba(255,255,255,0.6); margin-top: 0.2rem;">
                            ${trend.description}
                        </div>
                    </div>
                `;
            }

            if (forecast) {
                html += `
                    <div style="margin-bottom: 0.5rem; padding: 0.5rem; background: rgba(74,158,255,0.05); border-radius: 6px; border-left: 3px solid #4a9eff;">
                        <strong style="color: #4a9eff;">🔮 Previsão</strong>
                        <div style="font-size: 0.75rem; color: rgba(255,255,255,0.6); margin-top: 0.2rem;">
                            ${forecast}
                        </div>
                    </div>
                `;
            }

            if (general_conclusion) {
                html += `
                    <div style="padding: 0.5rem; background: rgba(255,255,255,0.02); border-radius: 6px; border-top: 1px solid rgba(255,255,255,0.05);">
                        <strong style="color: #ff6b35;">📌 Conclusão</strong>
                        <div style="font-size: 0.75rem; color: rgba(255,255,255,0.5); margin-top: 0.2rem; line-height: 1.5;">
                            ${general_conclusion}
                        </div>
                    </div>
                `;
            }

            reportContainer.innerHTML = html || '<div style="color: rgba(255,255,255,0.3); font-size: 0.8rem; text-align: center; padding: 1rem;">Análise concluída</div>';
        }

        // ==========================================
        // 🔥 ATUALIZAR MÉTRICAS
        // ==========================================

        async _updateMetrics(data) {
            const metricsContainer = document.getElementById('resultMetrics');
            if (!metricsContainer) return;

            const { executive_score, chart_data } = data;
            const score = executive_score?.nota_geral || executive_score?.saude_financeira || 0;
            const revenue = chart_data?.weekly?.revenue?.reduce((a, b) => a + b, 0) || 0;
            const services = chart_data?.performance?.services?.reduce((a, b) => a + b, 0) || 0;
            const margin = chart_data?.weekly?.revenue?.length > 0 ? 
                Math.round((revenue - (chart_data?.weekly?.costs?.reduce((a, b) => a + b, 0) || 0)) / revenue * 100) : 0;

            const metrics = [
                { value: typeof score === 'number' ? score.toFixed(1) : score, label: 'Score Geral', icon: '📊' },
                { value: revenue > 0 ? Utils.formatCompactCurrency(revenue) : 'R$ 0', label: 'Receita Total', icon: '💰' },
                { value: services > 0 ? services.toFixed(0) : '0', label: 'Serviços', icon: '🔧' },
                { value: margin + '%', label: 'Margem', icon: '📈' }
            ];

            metricsContainer.innerHTML = metrics.map(m => `
                <div class="result-stat">
                    <div class="stat-value" style="color: ${m.label === 'Margem' && parseInt(m.value) > 30 ? '#48bb78' : m.label === 'Margem' && parseInt(m.value) < 15 ? '#f56565' : '#ff6b35'}">
                        ${m.icon} ${m.value}
                    </div>
                    <div class="stat-label">${m.label}</div>
                </div>
            `).join('');
        }

        // ==========================================
        // 🔥 OBTER HEADERS PoW
        // ==========================================

        async _getPowHeaders() {
            let powHeaders = {};
            let attempts = 0;
            const maxAttempts = CONFIG.POW_MAX_ATTEMPTS;

            while (attempts < maxAttempts) {
                attempts++;
                try {
                    if (window.powClient) {
                        if (typeof window.powClient.getSolutionForUpload === 'function') {
                            const solution = await window.powClient.getSolutionForUpload();
                            if (solution && solution.nonce) {
                                return {
                                    'X-PoW-Nonce': solution.nonce,
                                    'X-PoW-Challenge': solution.prefix || solution.challenge || '',
                                    'X-PoW-Difficulty': String(solution.complexity || solution.difficulty || 4),
                                    'X-PoW-Solution': solution.solution || solution.hash || '',
                                    'X-PoW-Timestamp': String(solution.solvedAt || solution.timestamp || Date.now())
                                };
                            }
                        }

                        if (typeof window.powClient.prepareForUpload === 'function') {
                            await window.powClient.prepareForUpload();
                            const stats = window.powClient.getStats?.();
                            if (stats?.cache?.hasSolution && stats.cache.solution) {
                                const s = stats.cache.solution;
                                return {
                                    'X-PoW-Nonce': s.nonce,
                                    'X-PoW-Challenge': s.prefix || s.challenge || '',
                                    'X-PoW-Difficulty': String(s.complexity || s.difficulty || 4),
                                    'X-PoW-Solution': s.solution || s.hash || '',
                                    'X-PoW-Timestamp': String(s.solvedAt || s.timestamp || Date.now())
                                };
                            }
                        }
                    }

                    const nonce = localStorage.getItem('pow_nonce');
                    const challenge = localStorage.getItem('pow_challenge');
                    const solution = localStorage.getItem('pow_solution');
                    if (nonce && challenge && solution) {
                        return {
                            'X-PoW-Nonce': nonce,
                            'X-PoW-Challenge': challenge,
                            'X-PoW-Difficulty': '4',
                            'X-PoW-Solution': solution,
                            'X-PoW-Timestamp': String(Date.now())
                        };
                    }

                    if (attempts < maxAttempts) {
                        await Utils.sleep(1000 * attempts);
                    }
                } catch (e) {
                    console.warn(`⚠️ Tentativa ${attempts} de PoW falhou:`, e.message);
                }
            }

            return powHeaders;
        }

        // ==========================================
        // 🔥 RENOVAR PoW
        // ==========================================

        async _renewPow() {
            try {
                if (window.powClient) {
                    if (typeof window.powClient.clearCache === 'function') {
                        window.powClient.clearCache();
                    }
                    if (typeof window.powClient.reset === 'function') {
                        window.powClient.reset();
                    }
                    if (typeof window.powClient.prepareForUpload === 'function') {
                        await window.powClient.prepareForUpload();
                        return true;
                    }
                }
                return false;
            } catch (e) {
                console.warn('⚠️ Erro ao renovar PoW:', e);
                return false;
            }
        }

        // ==========================================
        // 🔥 SINCERONIZAR CRÉDITOS
        // ==========================================

        async _syncCredits() {
            return await this._creditManager.sync();
        }

        // ==========================================
        // 🔥 HANDLER DE CRÉDITOS ATUALIZADOS
        // ==========================================

        _handleCreditsUpdated(e) {
            const data = e.detail || {};
            
            if (data._silent) {
                return;
            }
            
            // 🔥 V16.8: Só atualiza se vier do backend
            if (data._source === 'backend' || data._source === 'loadUserCredits') {
                if (data.credits !== undefined && data.credits !== this._creditManager._balance) {
                    this._creditManager._balance = data.credits;
                    this._creditManager._isPremium = data.isPremium || false;
                    this._creditManager._isAdmin = data.isAdmin || false;
                    
                    const display = this._creditManager.display;
                    const elements = document.querySelectorAll('#creditsCount, #uploadCredits, #creditsDisplay, .credits-display');
                    elements.forEach(el => {
                        if (el) el.textContent = display;
                    });
                    
                    this._creditManager._cachedDisplay = display;
                    this._creditManager._lastUpdate = Date.now();
                }
            }
        }

        // ==========================================
        // 🔥 INVALIDAR CACHE
        // ==========================================

        async _invalidateCache() {
            try {
                if (Utils.cache && typeof Utils.cache.clear === 'function') {
                    await Utils.cache.clear();
                }
                this._analysisCache.clear();
                this._fileCache.clear();
                console.log('🧹 Cache invalidado');
            } catch (e) {
                console.warn('⚠️ Erro ao invalidar cache:', e);
            }
        }

        // ==========================================
        // 🔥 OBTER TAB MANAGER
        // ==========================================

        _getTabManager() {
            if (window.__dashboard && window.__dashboard.tabManager) {
                return window.__dashboard.tabManager;
            }
            
            try {
                const { TabManager } = window;
                if (TabManager) {
                    const manager = new TabManager();
                    manager.init();
                    return manager;
                }
            } catch (e) {
                console.warn('⚠️ Erro ao obter TabManager:', e);
            }
            
            return null;
        }

        // ==========================================
        // 🔥 UI HELPERS
        // ==========================================

        _showUploadStatus(icon, title, subtitle, progress) {
            const statusEl = document.getElementById('analysisStatus');
            if (!statusEl) return;

            statusEl.classList.add('show');
            const iconEl = document.getElementById('statusIcon');
            const textEl = document.getElementById('statusText');
            const subEl = document.getElementById('statusSub');
            const progressBar = document.getElementById('statusProgressBar');

            if (iconEl) iconEl.textContent = icon;
            if (textEl) textEl.textContent = title;
            if (subEl) subEl.textContent = subtitle || '';
            if (progressBar && progress !== undefined) {
                progressBar.style.width = Math.min(100, progress) + '%';
            }
        }

        _showResult() {
            const resultContainer = document.getElementById('resultContainer');
            const resultPlaceholder = document.getElementById('resultPlaceholder');
            
            if (resultContainer) {
                resultContainer.classList.add('show');
                resultContainer.style.display = 'block';
            }
            if (resultPlaceholder) {
                resultPlaceholder.style.display = 'none';
            }
        }

        _showToast(message, type = 'info') {
            if (window.toastr) {
                const methods = {
                    'success': toastr.success,
                    'error': toastr.error,
                    'warning': toastr.warning,
                    'info': toastr.info
                };
                const method = methods[type] || toastr.info;
                method(message, '', { 
                    timeOut: CONFIG.TIMEOUTS.TOAST, 
                    closeButton: true,
                    progressBar: true
                });
            } else {
                console.log(`[${type}] ${message}`);
            }
        }

        _showUpgradePrompt() {
            const modal = document.getElementById('upgradeModal');
            if (modal) {
                const instance = bootstrap.Modal.getInstance(modal) || new bootstrap.Modal(modal);
                instance.show();
            } else {
                setTimeout(() => {
                    if (confirm('💎 Créditos insuficientes! Deseja ver os planos Premium?')) {
                        window.location.href = '/planos';
                    }
                }, 500);
            }
        }

        // ==========================================
        // 🔥 SETUP EVENTS E POLLING
        // ==========================================

        _setupEvents() {
            document.addEventListener('creditsUpdated', this._handleCreditsUpdated);

            document.addEventListener('analysis:success', () => {
                this._invalidateCache();
                setTimeout(() => this._creditManager.sync(true), 500);
            });

            document.addEventListener('visibilitychange', () => {
                if (!document.hidden) {
                    this._creditManager.syncDebounced();
                }
            });
            
            document.addEventListener('app:state_changed', (e) => {
                const data = e.detail || {};
                if (data.key === 'credits' || data.key === 'isPremium') {
                    this._creditManager._loadFromAppState();
                }
            });
            
            window.addEventListener('beforeunload', () => {
                this._stopPolling();
                this._destroyAllCharts();
            });
        }

        _setupPolling() {
            if (this._pollingInterval) {
                clearInterval(this._pollingInterval);
            }

            this._pollingInterval = setInterval(() => {
                this._creditManager.syncDebounced();
            }, CONFIG.CREDITS.SYNC_INTERVAL);
        }

        // ==========================================
        // 🔥 DESTRUIR TODOS OS GRÁFICOS
        // ==========================================

        _destroyAllCharts() {
            Object.keys(this._chartInstances).forEach(key => {
                if (this._chartInstances[key]) {
                    try {
                        this._chartInstances[key].destroy();
                    } catch (e) {}
                    this._chartInstances[key] = null;
                }
            });
            console.log('🧹 [Charts] Todos os gráficos destruídos');
        }

        // ==========================================
        // 🔥 MÉTODOS PÚBLICOS
        // ==========================================

        getCredits() {
            return this._creditManager.balance;
        }

        getCreditsDisplay() {
            return this._creditManager.display;
        }

        isPremium() {
            return this._creditManager.isPremium;
        }

        isAdmin() {
            return this._creditManager.isAdmin;
        }

        async refreshCredits() {
            return await this._creditManager.sync(true);
        }

        // 🔥 V16.8: Método público para sincronizar créditos
        async syncCredits() {
            return await this._creditManager.syncCredits();
        }

        renderAllCharts(chartData) {
            return this._renderAllCharts(chartData);
        }

        renderGPSA(chartData) {
            return this._renderGPSA(chartData);
        }

        switchToAnalysis(analysisId) {
            this._switchAnalysis(analysisId);
        }

        getAnalysisHistory() {
            return this._analysisHistory;
        }

        destroy() {
            this._stopPolling();
            if (this._pollingInterval) {
                clearInterval(this._pollingInterval);
                this._pollingInterval = null;
            }
            
            this._destroyAllCharts();
            
            document.removeEventListener('creditsUpdated', this._handleCreditsUpdated);
            document.removeEventListener('chart:data_ready', this._handleChartDataReady);
            document.removeEventListener('dashboard:render_chart', this._handleChartDataReady);
            
            this._initialized = false;
            console.log('🧹 [Dashboard] Destruído');
        }
    }

    // ==============================================
    // 🔥 INICIALIZAÇÃO
    // ==============================================

    let dashboardInstance = null;

    function initDashboard() {
        if (dashboardInstance) {
            console.log('ℹ️ [Dashboard] Já existe uma instância');
            return dashboardInstance;
        }

        if (!Utils.isAuthenticated()) {
            console.log('🔒 [Dashboard] Usuário não autenticado');
            return null;
        }

        dashboardInstance = new Dashboard();
        window.__dashboard = dashboardInstance;

        dashboardInstance.init().catch(error => {
            console.error('❌ [Dashboard] Erro na inicialização:', error);
        });

        return dashboardInstance;
    }

    document.addEventListener('DOMContentLoaded', function() {
        if (window._appReadyFired || window.__APP_STATE?.isAppReady) {
            console.log('✅ [Dashboard] App já pronto, inicializando...');
            initDashboard();
            return;
        }

        console.log('⏳ [Dashboard] Aguardando app:ready...');
        document.addEventListener('app:ready', function() {
            console.log('📢 [Dashboard] app:ready recebido');
            initDashboard();
        });

        setTimeout(function() {
            if (!dashboardInstance) {
                console.log('🔄 [Dashboard] Fallback: tentando inicializar...');
                initDashboard();
            }
        }, 3000);
    });

    // 🔥 EXPORTAÇÃO GLOBAL
    window.Dashboard = Dashboard;
    window.initDashboard = initDashboard;

    console.log('='.repeat(60));
    console.log('🔥 dashboard.js v16.8 carregado - CORREÇÃO DE CRÉDITOS');
    console.log('   ✅ NÃO CONSOLE créditos no upload (apenas verifica)');
    console.log('   ✅ CreditManager.consume() NÃO é chamado no upload');
    console.log('   ✅ Sincronização de créditos via /auth/me');
    console.log('   ✅ Evento analysis:success agora sincroniza');
    console.log('   ✅ syncCredits() público para sincronização manual');
    console.log('   ✅ HISTÓRICO: Mantém todos os arquivos processados');
    console.log('   ✅ ALTERNÂNCIA: Troca entre análises sem re-processar ML');
    console.log('   ✅ SEM FALLBACK: Apenas dados reais do backend');
    console.log('   ✅ GRÁFICOS: 3 gráficos + GPSA');
    console.log('='.repeat(60));

})();