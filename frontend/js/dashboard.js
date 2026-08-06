// frontend/js/dashboard.js - VERSÃO 9.1 (COM POLLING E PROGRESSO)
/**
 * 🔥 Dashboard Module - AutoAnalytics v9.1
 * 
 * ✅ NOVIDADES v16.1:
 * - 🔥 POLLING: Acompanhamento de progresso em tempo real
 * - 🔥 BARRA DE PROGRESSO: Mostra % e mensagem durante o processamento
 * - 🔥 RENDERIZAÇÃO ANTECIPADA: Gráficos aparecem assim que concluídos
 * - 🔥 TIMEOUT: Evita polling infinito (60 segundos)
 * - 🔥 FALLBACK: Se o polling falhar, tenta usar a resposta original
 * 
 * ✅ MANTIDO v9.0:
 * - Verificação de créditos com App State primeiro
 * - Sync com fallback múltiplo
 * - Detecção de token via appAuth
 * - Prevenção de loop infinito
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
        
        // 🔥 NOVO: Configurações de polling
        POLLING: {
            INTERVAL: 2000,        // 2 segundos entre cada consulta
            MAX_ATTEMPTS: 60,      // 60 tentativas (2min no total)
            TIMEOUT_MS: 120000,    // 2 minutos de timeout
            RETRY_DELAY: 1000,     // 1 segundo entre tentativas com erro
        },
        
        CREDITS: {
            COST_PER_UPLOAD: 1,
            MAX_CREDITS_PREMIUM: 3,
            INITIAL_FREE_CREDITS: 3,
            SYNC_INTERVAL: 15000,
            UI_THROTTLE: 300,
            SYNC_DEBOUNCE: 500,
        },
        
        COLORS: {
            primary: '#ff6b35',
            success: '#48bb78',
            warning: '#f5a623',
            danger: '#f56565',
            secondary: '#4a9eff',
        },
        
        TIMEOUTS: {
            UPLOAD: 120000,
            SYNC: 5000,
            TOAST: 5000,
        }
    };

    // ==============================================
    // 🔥 UTILITÁRIOS
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

        detectCreditDiscrepancy: (before, after, expectedCost) => {
            const actualCost = before - after;
            return {
                isDiscrepancy: actualCost !== expectedCost,
                actualCost: actualCost,
                expectedCost: expectedCost,
                difference: actualCost - expectedCost,
                shouldRefund: actualCost > expectedCost
            };
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
        }
    };

    // ==============================================
    // 🔥 CREDIT MANAGER (MANTIDO)
    // ==============================================

    class CreditManager {
        constructor() {
            this._balance = 0;
            this._isPremium = false;
            this._isAdmin = false;
            this._lastSync = 0;
            this._pendingRefund = 0;
            this._syncInProgress = false;
            
            this._updatingUI = false;
            this._lastUpdate = 0;
            this._uiThrottle = CONFIG.CREDITS.UI_THROTTLE;
            this._updateQueue = [];
            this._isProcessingQueue = false;
            this._cachedDisplay = null;
            
            this._loadFromAppState();
            this._setupEventListeners();
        }

        _loadFromAppState() {
            try {
                if (window.__APP_STATE) {
                    const appCredits = window.__APP_STATE.credits;
                    if (appCredits !== undefined) {
                        this._balance = appCredits;
                        this._isPremium = window.__APP_STATE.isPremium || false;
                        this._isAdmin = window.__APP_STATE.isAdmin || false;
                        console.log(`💰 [CreditManager] Carregado do App State: ${this._balance}`);
                        this._updateUI();
                        return true;
                    }
                }
                
                try {
                    const userData = localStorage.getItem('user_data');
                    if (userData) {
                        const parsed = JSON.parse(userData);
                        if (parsed.credits !== undefined) {
                            this._balance = parsed.credits;
                            this._isPremium = parsed.is_premium || false;
                            this._isAdmin = parsed.is_admin || false;
                            console.log(`💰 [CreditManager] Carregado do localStorage: ${this._balance}`);
                            this._updateUI();
                            return true;
                        }
                    }
                } catch (e) {}
                
                if (window.App && typeof window.App.getCredits === 'function') {
                    const appCredits = window.App.getCredits();
                    if (appCredits !== undefined) {
                        this._balance = appCredits;
                        this._isPremium = window.App.isPremium ? window.App.isPremium() : false;
                        this._isAdmin = window.App.isAdmin ? window.App.isAdmin() : false;
                        console.log(`💰 [CreditManager] Carregado do App: ${this._balance}`);
                        this._updateUI();
                        return true;
                    }
                }
                
                return false;
            } catch (e) {
                console.warn('⚠️ Erro ao carregar do App State:', e);
                return false;
            }
        }

        _setupEventListeners() {
            document.addEventListener('creditsUpdated', (e) => {
                const data = e.detail || {};
                if (data._silent) return;
                
                if (data.credits !== undefined) {
                    this._balance = data.credits;
                    this._isPremium = data.isPremium || false;
                    this._isAdmin = data.isAdmin || false;
                    this._updateUI();
                }
            });

            document.addEventListener('app:state_changed', (e) => {
                const data = e.detail || {};
                if (data.key === 'credits' || data.key === 'isPremium' || data.key === 'isAdmin') {
                    this._loadFromAppState();
                }
            });
        }

        get balance() { return this._balance; }
        get isPremium() { return this._isPremium; }
        get isAdmin() { return this._isAdmin; }
        
        get display() {
            if (this._isAdmin) return '∞';
            if (this._isPremium) return `${this._balance}/${CONFIG.CREDITS.MAX_CREDITS_PREMIUM}`;
            return String(this._balance);
        }

        async sync(force = false) {
            if (!force) {
                const loaded = this._loadFromAppState();
                if (loaded) {
                    return this._balance;
                }
            }

            if (this._syncInProgress && !force) return this._balance;
            
            this._syncInProgress = true;
            
            try {
                let token = null;
                
                if (window.appAuth && typeof window.appAuth.isAuthenticated === 'function') {
                    if (window.appAuth.isAuthenticated()) {
                        token = localStorage.getItem('access_token');
                    }
                } else {
                    token = Utils.getToken();
                }
                
                if (!token) {
                    console.log('⏳ [CreditManager] Sem token, usando App State');
                    this._loadFromAppState();
                    this._updateUI();
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
                    }
                    
                    return this._balance;
                } else if (response.status === 401) {
                    console.warn('⚠️ Token expirado, usando App State');
                    this._loadFromAppState();
                    this._updateUI();
                    return this._balance;
                }
            } catch (e) {
                console.warn('⚠️ Erro ao sincronizar créditos:', e);
                this._loadFromAppState();
                this._updateUI();
                return this._balance;
            } finally {
                this._syncInProgress = false;
            }
            return this._balance;
        }

        syncDebounced = Utils.debounce(() => {
            this.sync().catch(() => {});
        }, CONFIG.CREDITS.SYNC_DEBOUNCE);

        hasCredits(required = CONFIG.CREDITS.COST_PER_UPLOAD) {
            this._loadFromAppState();
            if (this._isAdmin) return true;
            const hasEnough = this._balance >= required;
            console.log(`💰 [CreditManager] Verificando créditos: ${this._balance} >= ${required} = ${hasEnough}`);
            return hasEnough;
        }

        canReceiveDaily() {
            if (this._isAdmin) return false;
            if (!this._isPremium) return false;
            return this._balance < CONFIG.CREDITS.MAX_CREDITS_PREMIUM;
        }

        async consume(amount = CONFIG.CREDITS.COST_PER_UPLOAD, description = 'Upload') {
            if (this._isAdmin) {
                console.log('👑 Admin - créditos ilimitados');
                return { success: true, balance: '∞' };
            }

            await this.sync(true);
            
            if (!this.hasCredits(amount)) {
                return { 
                    success: false, 
                    error: 'Créditos insuficientes',
                    balance: this._balance,
                    needed: amount
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
                    this._balance = data.remaining || 0;
                    this._updateUI();
                    return { 
                        success: true, 
                        balance: this._balance,
                        consumed: amount,
                        before: before
                    };
                } else {
                    const error = await response.json();
                    return { success: false, error: error.message || 'Erro ao consumir créditos' };
                }
            } catch (e) {
                console.error('❌ Erro ao consumir créditos:', e);
                await this.sync(true);
                return { success: false, error: e.message };
            }
        }

        async refund(amount, description = 'Correção de créditos') {
            if (this._isAdmin || amount <= 0) return true;

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
                    this._balance = data.balance || 0;
                    this._updateUI();
                    console.log(`💰 ${amount} crédito(s) devolvido(s): ${description}`);
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
                
                if (this._cachedDisplay === display) {
                    this._updatingUI = false;
                    return;
                }
                
                const elements = document.querySelectorAll('#creditsCount, #uploadCredits, #creditsDisplay, .credits-display');
                let updated = false;
                
                elements.forEach(el => {
                    if (el && el.textContent !== display) {
                        el.textContent = display;
                        updated = true;
                    }
                });
                
                if (updated) {
                    this._cachedDisplay = display;
                    this._lastUpdate = now;
                    
                    const event = new CustomEvent('creditsUpdated', {
                        detail: {
                            credits: this._balance,
                            display: display,
                            isPremium: this._isPremium,
                            isAdmin: this._isAdmin,
                            _silent: true
                        }
                    });
                    document.dispatchEvent(event);
                    
                    if (window.__APP_STATE_MANAGER) {
                        window.__APP_STATE_MANAGER.updateCredits(this._balance, this._isPremium);
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
    }

    // ==============================================
    // 🔥 DASHBOARD - CLASSE PRINCIPAL (V16.1)
    // ==============================================

    class Dashboard {
        constructor() {
            this._initialized = false;
            this._uploadInProgress = false;
            this._pollingInterval = null;
            this._creditManager = new CreditManager();
            this._fileCache = new Map();
            this._analysisCache = new Map();
            
            // 🔥 NOVO: Estado do polling
            this._pollingState = {
                active: false,
                processId: null,
                attempts: 0,
                startTime: null,
                timeoutId: null,
            };
            
            // 🔥 Bind dos métodos
            this.uploadMultipleFiles = this.uploadMultipleFiles.bind(this);
            this._processUploadResult = this._processUploadResult.bind(this);
            this._syncCredits = this._syncCredits.bind(this);
            this._handleCreditsUpdated = this._handleCreditsUpdated.bind(this);
            this._pollProgress = this._pollProgress.bind(this);
            this._stopPolling = this._stopPolling.bind(this);
        }

        // ==========================================
        // 🔥 INICIALIZAÇÃO
        // ==========================================

        async init() {
            if (this._initialized) {
                console.log('ℹ️ [Dashboard] Já inicializado');
                return this;
            }

            console.log('🚀 [Dashboard v16.1] Inicializando com polling...');

            await this._creditManager.sync();
            
            this._setupEvents();
            this._setupUploadHandlers();
            this._setupPolling();
            
            this._initialized = true;
            
            console.log('✅ [Dashboard v16.1] Inicializado com sucesso!');
            console.log(`   💰 Saldo: ${this._creditManager.display}`);
            console.log(`   🔥 Polling: ${CONFIG.POLLING.INTERVAL}ms / ${CONFIG.POLLING.MAX_ATTEMPTS} tentativas`);
            
            return this;
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
        // 🔥🔥🔥 UPLOAD MÚLTIPLO (COM POLLING)
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

                // 🔥 VERIFICAR CRÉDITOS
                await this._creditManager.sync(true);
                
                const hasCredits = this._creditManager.hasCredits(CONFIG.CREDITS.COST_PER_UPLOAD);
                console.log(`💰 [Dashboard] Verificação de créditos: ${hasCredits} (saldo: ${this._creditManager.balance})`);
                
                if (!hasCredits) {
                    this._showToast('❌ Créditos insuficientes. Adquira o plano Premium.', 'error');
                    this._showUpgradePrompt();
                    return null;
                }

                // 🔥 MOSTRAR LOADING IMEDIATAMENTE
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
                    'X-Expected-Cost': String(CONFIG.CREDITS.COST_PER_UPLOAD),
                    ...powHeaders
                };

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

                // 🔥🔥🔥 VERIFICAR SE TEM PROCESS_ID (POLLING)
                if (result.success && result.process_id) {
                    console.log(`📡 [Dashboard] Process ID: ${result.process_id}`);
                    
                    // 🔥 INICIAR POLLING DE PROGRESSO
                    const pollingResult = await this._pollProgress(result.process_id);
                    
                    if (pollingResult.success && pollingResult.result) {
                        // 🔥 PROCESSAR RESULTADO COMPLETO
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
                        
                        // 🔥 VERIFICAR CRÉDITOS ATUALIZADOS
                        await this._creditManager.sync(true);
                    } else {
                        // 🔥 FALLBACK: Tentar usar a resposta original
                        console.warn('⚠️ Polling falhou, usando resposta original');
                        await this._processUploadResult(result, files);
                        this._showToast('✅ Upload processado!', 'success');
                        this._showResult();
                    }
                } else {
                    // 🔥 SEM PROCESS_ID: Processar resposta normal
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
        // 🔥🔥🔥 POLLING DE PROGRESSO (NOVO)
        // ==========================================

        async _pollProgress(processId) {
            console.log(`📡 [Polling] Iniciando para process_id: ${processId}`);
            
            // 🔥 Resetar estado do polling
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
            
            // 🔥 Atualizar status inicial
            this._showUploadStatus('🔄', 'Processando...', 'Iniciando análise', 10);
            
            return new Promise((resolve) => {
                const poll = async () => {
                    // Verificar se o polling ainda está ativo
                    if (!this._pollingState.active) {
                        console.log('⏹️ [Polling] Interrompido pelo usuário');
                        resolve({ success: false, error: 'Interrompido' });
                        return;
                    }
                    
                    attempts++;
                    this._pollingState.attempts = attempts;
                    
                    // 🔥 Verificar timeout
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
                        
                        // ==========================================
                        // 🔥 PROCESSAR RESPOSTA DO POLLING
                        // ==========================================
                        
                        if (data.status === 'completed') {
                            // 🔥✅ CONCLUÍDO!
                            console.log('✅ [Polling] Análise concluída!');
                            this._stopPolling();
                            
                            // Atualizar status final
                            this._showUploadStatus('✅', 'Análise concluída!', '100%', 100);
                            
                            resolve({
                                success: true,
                                result: data.result || {}
                            });
                            return;
                            
                        } else if (data.status === 'processing') {
                            // 🔥🔄 EM PROCESSAMENTO
                            const progress = data.progress || 0;
                            const message = data.message || 'Processando...';
                            
                            // Atualizar barra de progresso
                            this._showUploadStatus(
                                '🔄',
                                `Processando... ${progress}%`,
                                message,
                                progress
                            );
                            
                            // 🔥 Se tiver resultado parcial, já pode renderizar
                            if (data.result && data.result.chart_data) {
                                console.log('📊 [Polling] Renderizando dados parciais');
                                this._renderChartPartial(data.result.chart_data);
                            }
                            
                            // Continuar polling
                            setTimeout(poll, interval);
                            return;
                            
                        } else if (data.status === 'error') {
                            // 🔥❌ ERRO
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
                            // 🔥 Status desconhecido
                            console.warn(`⚠️ [Polling] Status desconhecido: ${data.status}`);
                            
                            // Se já passou muitas tentativas, tentar uma última vez
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
                            
                            // Continuar polling
                            setTimeout(poll, interval);
                            return;
                        }
                        
                    } catch (error) {
                        console.error('❌ [Polling] Erro:', error);
                        
                        // 🔥 Tentar novamente em caso de erro
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
                
                // 🔥 Iniciar polling
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
        // 🔥 RENDERIZAR GRÁFICO PARCIAL
        // ==========================================

        _renderChartPartial(chartData) {
            if (!chartData || !chartData.weekly) return;
            
            const canvas = document.getElementById('revenueChart');
            if (!canvas) return;
            
            const ctx = canvas.getContext('2d');
            const weekly = chartData.weekly || {};
            const labels = weekly.labels || ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'];
            const revenue = weekly.revenue || [0, 0, 0, 0, 0, 0, 0];
            const costs = weekly.costs || [0, 0, 0, 0, 0, 0, 0];
            
            // 🔥 Atualizar ou criar gráfico
            if (window._revenueChart) {
                window._revenueChart.data.labels = labels;
                window._revenueChart.data.datasets[0].data = revenue;
                window._revenueChart.data.datasets[1].data = costs;
                window._revenueChart.update('none');
            } else {
                window._revenueChart = new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: labels,
                        datasets: [
                            {
                                label: 'Receita',
                                data: revenue,
                                backgroundColor: 'rgba(255,107,53,0.8)',
                                borderColor: 'rgba(255,107,53,1)',
                                borderWidth: 1
                            },
                            {
                                label: 'Custos',
                                data: costs,
                                backgroundColor: 'rgba(74,158,255,0.8)',
                                borderColor: 'rgba(74,158,255,1)',
                                borderWidth: 1
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                labels: {
                                    color: 'rgba(255,255,255,0.7)',
                                    font: { size: 12 }
                                }
                            }
                        },
                        scales: {
                            y: {
                                beginAtZero: true,
                                grid: { color: 'rgba(255,255,255,0.05)' },
                                ticks: { color: 'rgba(255,255,255,0.5)' }
                            },
                            x: {
                                grid: { display: false },
                                ticks: { color: 'rgba(255,255,255,0.5)' }
                            }
                        },
                        animation: {
                            duration: 300
                        }
                    }
                });
            }
            
            console.log('📊 Gráfico parcial renderizado');
        }

        // ==========================================
        // 🔥 PROCESSAR RESULTADO DO UPLOAD
        // ==========================================

        async _processUploadResult(result, files) {
            if (!result || !result.success) {
                console.warn('⚠️ Resultado inválido:', result);
                return;
            }

            const analysis = result.analysis || {};
            const chartData = result.chart_data || {};
            const recommendations = analysis.recommendations || [];
            const executiveScore = analysis.executive_score || {};
            const executiveSummary = analysis.executive_summary || '';

            // 🔥 Renderizar gráfico principal
            if (chartData && chartData.weekly) {
                this._renderChartPartial(chartData);
            }

            await this._updateAIReport({
                executive_score: executiveScore,
                executive_summary: executiveSummary,
                recommendations: recommendations,
                chart_data: chartData,
                forecast: analysis.forecast || '',
                general_conclusion: analysis.general_conclusion || '',
                comparison: analysis.comparison || {},
                trend: analysis.trend || {}
            });

            await this._updateMetrics({
                executive_score: executiveScore,
                chart_data: chartData
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
                    chart_data: chartData,
                    insights: {
                        summary: { mean: file.metrics?.mean_prediction || 0.5 },
                        risk_distribution: {
                            high_percentage: file.metrics?.high_risk_percentage || 0,
                            low_percentage: file.metrics?.low_risk_percentage || 0
                        }
                    },
                    recommendations: recommendations,
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
                    result: result
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
        // 🔥 ATUALIZAR RELATÓRIO DA IA
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
                                        <div style="font-size: 0.9rem; font-weight: 700; color: ${color};">
                                            ${icon} ${isNumber ? value.toFixed(1) : value}
                                        </div>
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
                { value: revenue > 0 ? 'R$ ' + (revenue / 1000).toFixed(1) + 'k' : 'R$ 0', label: 'Receita Total', icon: '💰' },
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
            
            // 🔥 NOVO: Limpar polling ao sair da página
            window.addEventListener('beforeunload', () => {
                this._stopPolling();
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

        destroy() {
            this._stopPolling();
            if (this._pollingInterval) {
                clearInterval(this._pollingInterval);
                this._pollingInterval = null;
            }
            
            document.removeEventListener('creditsUpdated', this._handleCreditsUpdated);
            
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

    console.log('=' .repeat(60));
    console.log('🔥 dashboard.js v9.11 carregado - COM POLLING E PROGRESSO');
    console.log('   ✅ POLLING: Acompanhamento de progresso em tempo real');
    console.log('   ✅ BARRA DE PROGRESSO: Mostra % e mensagem durante o processamento');
    console.log('   ✅ RENDERIZAÇÃO ANTECIPADA: Gráficos aparecem assim que concluídos');
    console.log('   ✅ TIMEOUT: Evita polling infinito (60 segundos)');
    console.log('   ✅ FALLBACK: Se o polling falhar, tenta usar a resposta original');
    console.log('   ✅ Verificação de créditos com App State primeiro');
    console.log('   ✅ Consumo: 1 crédito por upload');
    console.log('=' .repeat(60));

})();