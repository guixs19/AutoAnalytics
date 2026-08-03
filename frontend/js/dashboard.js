// frontend/js/dashboard.js - VERSÃO 15.1 (CORREÇÃO DE LOOP + MELHORIAS DE CRÉDITOS)
/**
 * 🔥 Dashboard Module - AutoAnalytics v15.1
 * 
 * ✅ CORREÇÕES v15.1:
 * - 🔥 CORRIGIDO: Loop infinito entre dashboard.js e app.js
 * - 🔥 ADICIONADO: Throttle para atualizações de UI
 * - 🔥 ADICIONADO: Flag _silent para eventos internos
 * - 🔥 OTIMIZADO: Sincronização de créditos com debounce
 * - 🔥 MELHORADO: Verificação de mudança real antes de atualizar
 * 
 * ✅ CORREÇÕES CRÍTICAS v15.0:
 * - 🔥 CONSUMO DE CRÉDITOS: 1 crédito por upload
 * - 🔥 SINCERONIZAÇÃO: Verificação de saldo antes/depois
 * - 🔥 DETECÇÃO: Consumo excessivo com rollback automático
 * 
 * ✅ MELHORIAS v15.1:
 * - 📊 Prevenção de stack overflow
 * - 🔄 Sincronização inteligente
 * - 💾 Cache com invalidação controlada
 * - 🛡️ Tratamento robusto de eventos
 * - ⚡ Performance otimizada
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
        CACHE_TTL: 300000, // 5 minutos
        MAX_RETRIES: 3,
        RETRY_DELAY: 1000,
        POW_MAX_ATTEMPTS: 3,
        
        CREDITS: {
            COST_PER_UPLOAD: 1,
            MAX_CREDITS_PREMIUM: 3,
            INITIAL_FREE_CREDITS: 3,
            SYNC_INTERVAL: 15000, // 15 segundos
            UI_THROTTLE: 300, // 300ms entre atualizações
            SYNC_DEBOUNCE: 500, // 500ms de debounce
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

        isAuthenticated: () => !!Utils.getToken(),

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
        
        // 🔥 NOVO: Debounce para sincronização
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
    // 🔥 CREDIT MANAGER - GERENCIADOR DE CRÉDITOS (CORRIGIDO)
    // ==============================================

    class CreditManager {
        constructor() {
            this._balance = 0;
            this._isPremium = false;
            this._isAdmin = false;
            this._lastSync = 0;
            this._pendingRefund = 0;
            this._syncInProgress = false;
            
            // 🔥 NOVO: Controle de throttling
            this._updatingUI = false;
            this._lastUpdate = 0;
            this._uiThrottle = CONFIG.CREDITS.UI_THROTTLE;
            this._updateQueue = [];
            this._isProcessingQueue = false;
            
            // 🔥 NOVO: Cache do display atual
            this._cachedDisplay = null;
        }

        get balance() { return this._balance; }
        get isPremium() { return this._isPremium; }
        get isAdmin() { return this._isAdmin; }
        
        get display() {
            if (this._isAdmin) return '∞';
            if (this._isPremium) return `${this._balance}/${CONFIG.CREDITS.MAX_CREDITS_PREMIUM}`;
            return String(this._balance);
        }

        // 🔥 Sincronizar com o backend (com debounce)
        async sync(force = false) {
            if (this._syncInProgress && !force) return this._balance;
            
            this._syncInProgress = true;
            try {
                const token = Utils.getToken();
                if (!token) return this._balance;

                const response = await fetch('/api/auth/me', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });

                if (response.ok) {
                    const data = await response.json();
                    const newBalance = data.credits || 0;
                    const newIsPremium = data.is_premium || false;
                    const newIsAdmin = data.is_admin || false;
                    
                    // 🔥 Verificar se houve mudança real
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
                }
            } catch (e) {
                console.warn('⚠️ Erro ao sincronizar créditos:', e);
            } finally {
                this._syncInProgress = false;
            }
            return this._balance;
        }

        // 🔥 Sincronização com debounce
        syncDebounced = Utils.debounce(() => {
            this.sync().catch(() => {});
        }, CONFIG.CREDITS.SYNC_DEBOUNCE);

        // 🔥 Verificar se tem créditos suficientes
        hasCredits(required = CONFIG.CREDITS.COST_PER_UPLOAD) {
            if (this._isAdmin) return true;
            return this._balance >= required;
        }

        // 🔥 Verificar se pode receber crédito diário
        canReceiveDaily() {
            if (this._isAdmin) return false;
            if (!this._isPremium) return false;
            return this._balance < CONFIG.CREDITS.MAX_CREDITS_PREMIUM;
        }

        // 🔥 Consumir créditos (com verificação)
        async consume(amount = CONFIG.CREDITS.COST_PER_UPLOAD, description = 'Upload') {
            if (this._isAdmin) {
                console.log('👑 Admin - créditos ilimitados');
                return { success: true, balance: '∞' };
            }

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
                return { success: false, error: e.message };
            }
        }

        // 🔥 Devolver créditos (rollback)
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

        // 🔥 ATUALIZAR UI (COM THROTTLE E PREVENÇÃO DE LOOP)
        _updateUI() {
            // 🔥 Throttle: não atualizar mais de uma vez a cada X ms
            const now = Date.now();
            if (now - this._lastUpdate < this._uiThrottle) {
                // 🔥 Agendar para depois se necessário
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
                
                // 🔥 Verificar se o display mudou realmente
                if (this._cachedDisplay === display) {
                    this._updatingUI = false;
                    return;
                }
                
                // 🔥 Atualizar elementos DOM
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
                    
                    // 🔥 Disparar evento com flag _silent para evitar loop
                    const event = new CustomEvent('creditsUpdated', {
                        detail: {
                            credits: this._balance,
                            display: display,
                            isPremium: this._isPremium,
                            isAdmin: this._isAdmin,
                            _silent: true  // 🔥 Flag crítica para evitar loop
                        }
                    });
                    document.dispatchEvent(event);
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
    // 🔥 DASHBOARD - CLASSE PRINCIPAL (CORRIGIDA)
    // ==============================================

    class Dashboard {
        constructor() {
            this._initialized = false;
            this._uploadInProgress = false;
            this._pollingInterval = null;
            this._creditManager = new CreditManager();
            this._fileCache = new Map();
            this._analysisCache = new Map();
            
            // 🔥 Bind dos métodos
            this.uploadMultipleFiles = this.uploadMultipleFiles.bind(this);
            this._processUploadResult = this._processUploadResult.bind(this);
            this._syncCredits = this._syncCredits.bind(this);
            this._handleCreditsUpdated = this._handleCreditsUpdated.bind(this);
        }

        // ==========================================
        // 🔥 INICIALIZAÇÃO
        // ==========================================

        async init() {
            if (this._initialized) {
                console.log('ℹ️ [Dashboard] Já inicializado');
                return this;
            }

            console.log('🚀 [Dashboard v15.1] Inicializando com correção de loop...');

            // Sincronizar créditos
            await this._creditManager.sync();
            
            // Configurar eventos
            this._setupEvents();
            this._setupUploadHandlers();
            this._setupPolling();
            
            this._initialized = true;
            
            console.log('✅ [Dashboard v15.1] Inicializado com sucesso!');
            console.log(`   💰 Saldo: ${this._creditManager.display}`);
            console.log(`   🔥 Consumo: ${CONFIG.CREDITS.COST_PER_UPLOAD} crédito por upload`);
            console.log(`   🛡️ Throttle: ${CONFIG.CREDITS.UI_THROTTLE}ms`);
            
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
        // 🔥 UPLOAD MÚLTIPLO DE ARQUIVOS
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
                const hasCredits = this._creditManager.hasCredits(CONFIG.CREDITS.COST_PER_UPLOAD);
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
                        return null;
                    }

                    throw new Error(errorDetail);
                }

                const result = await response.json();

                // 🔥 VERIFICAR CONSUMO DE CRÉDITOS
                const balanceAfter = await this._creditManager.sync();
                console.log(`💰 Saldo depois: ${balanceAfter}`);

                const discrepancy = Utils.detectCreditDiscrepancy(
                    balanceBefore,
                    balanceAfter,
                    CONFIG.CREDITS.COST_PER_UPLOAD
                );

                if (discrepancy.isDiscrepancy && discrepancy.shouldRefund) {
                    console.warn(`⚠️ Consumo excessivo detectado: ${discrepancy.actualCost} créditos consumidos (esperado: ${discrepancy.expectedCost})`);
                    console.log(`🔄 Devolvendo ${discrepancy.difference} crédito(s)...`);
                    
                    const refunded = await this._creditManager.refund(
                        discrepancy.difference,
                        `Correção: consumo excessivo de ${discrepancy.actualCost} créditos`
                    );
                    
                    if (refunded) {
                        console.log(`✅ ${discrepancy.difference} crédito(s) devolvido(s)`);
                        await this._creditManager.sync();
                    }
                }

                await this._processUploadResult(result, files);

                this._showUploadStatus('✅', 'Análise concluída!', 'Veja o relatório abaixo', 100);
                this._showToast('✅ Upload concluído com sucesso!', 'success');
                this._showResult();

                await this._invalidateCache();
                this._fileCache.clear();

                this._uploadInProgress = false;
                return result;

            } catch (error) {
                console.error('❌ Erro no upload:', error);
                
                this._showUploadStatus('❌', 'Erro', error.message || 'Falha no processamento', 0);
                this._showToast(`❌ ${error.message || 'Erro ao processar'}`, 'error');
                
                try {
                    await this._creditManager.sync();
                } catch (e) {}

                this._uploadInProgress = false;
                return null;
            }
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
        // 🔥 HANDLER DE CRÉDITOS ATUALIZADOS (CORRIGIDO)
        // ==========================================

        _handleCreditsUpdated(e) {
            const data = e.detail || {};
            
            // 🔥 IGNORAR eventos com flag _silent (já processados)
            if (data._silent) {
                return;
            }
            
            // 🔥 Verificar se houve mudança real
            if (data.credits !== undefined && data.credits !== this._creditManager._balance) {
                this._creditManager._balance = data.credits;
                this._creditManager._isPremium = data.isPremium || false;
                this._creditManager._isAdmin = data.isAdmin || false;
                
                // 🔥 Atualizar UI sem disparar novo evento
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
        // 🔥 SETUP EVENTS E POLLING (CORRIGIDO)
        // ==========================================

        _setupEvents() {
            // 🔥 CORRIGIDO: Eventos de créditos com prevenção de loop
            document.addEventListener('creditsUpdated', this._handleCreditsUpdated);

            // 🔥 Eventos de análise
            document.addEventListener('analysis:success', () => {
                this._invalidateCache();
            });

            // 🔥 Visibility change com debounce
            document.addEventListener('visibilitychange', () => {
                if (!document.hidden) {
                    this._creditManager.syncDebounced();
                }
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
            if (this._pollingInterval) {
                clearInterval(this._pollingInterval);
                this._pollingInterval = null;
            }
            
            // 🔥 Remover event listeners para evitar memory leaks
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
    console.log('🔥 dashboard.js v15.1 carregado - CORREÇÃO DE LOOP + MELHORIAS');
    console.log('   ✅ Consumo: 1 crédito por upload');
    console.log('   ✅ Detecção automática de consumo excessivo');
    console.log('   ✅ Rollback automático com devolução de créditos');
    console.log('   ✅ Sincronização com debounce e throttle');
    console.log('   ✅ PREVENÇÃO DE LOOP INFINITO');
    console.log('   ✅ UI atualizada com throttling');
    console.log('=' .repeat(60));

})();