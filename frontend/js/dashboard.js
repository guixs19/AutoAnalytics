// frontend/js/dashboard.js - VERSÃO 16.16 (BUSCA INTELIGENTE DE DADOS)
/**
 * 🔥 Dashboard Module - AutoAnalytics v16.16
 * 
 * ✅ CORREÇÕES v16.16:
 * - 🔥 BUSCA INTELIGENTE: chart_data em MULTIPLAS fontes
 * - 🔥 CORRIGIDO: extração de dados do ML em todos os cenários
 * - 🔥 CORRIGIDO: _processUploadResult busca do backend se necessário
 * - 🔥 MELHORADO: logs para debug
 * - 🔥 REMOVIDO fallback de dados para gráficos
 * - 🔥 GRÁFICOS DE LINHA com dados reais
 * - 🔥 GPSA com dados reais do ML
 */

(function() {
    'use strict';

    const CONFIG = {
        MAX_FILES_PER_BATCH: 3,
        MAX_FILE_SIZE_KB: 200,
        API_BASE: '/api',
        
        POLLING: {
            INTERVAL: 2000,
            MAX_ATTEMPTS: 60,
            TIMEOUT_MS: 120000,
            RETRY_DELAY: 1000,
        },
        
        CREDITS: {
            COST_PER_UPLOAD: 1,
            MAX_CREDITS_PREMIUM: 3,
            SYNC_INTERVAL: 30000,
        },
        
        COLORS: {
            primary: '#ff6b35',
            primaryLight: 'rgba(255,107,53,0.3)',
            primaryDark: '#e55a2b',
            success: '#48bb78',
            warning: '#f5a623',
            danger: '#f56565',
            secondary: '#4a9eff',
            secondaryLight: 'rgba(74,158,255,0.3)',
            tertiary: '#9b59b6',
            tertiaryLight: 'rgba(155,89,182,0.3)',
            text: 'rgba(255,255,255,0.8)',
            textMuted: 'rgba(255,255,255,0.4)',
            grid: 'rgba(255,255,255,0.06)',
        },
        
        CHART: {
            ANIMATION_DURATION: 600,
            BAR_THICKNESS: 28,
            BAR_PERCENTAGE: 0.7,
            CATEGORY_PERCENTAGE: 0.8,
            FONT_SIZE: 10,
            LEGEND_PADDING: 12,
            LINE_TENSION: 0.4,
            POINT_RADIUS: 4,
        }
    };

    // ==============================================
    // 🔥 UTILITÁRIOS (OTIMIZADOS)
    // ==============================================

    const Utils = {
        sleep: (ms) => new Promise(resolve => setTimeout(resolve, ms)),
        
        getToken: () => {
            try {
                const token = localStorage.getItem('access_token');
                if (token && token.length > 10) return token;
                return null;
            } catch (e) { return null; }
        },

        isAuthenticated: () => {
            if (window.appAuth) {
                if (typeof window.appAuth.isAuthenticated === 'boolean') {
                    return window.appAuth.isAuthenticated;
                }
                if (typeof window.appAuth.isAuthenticated === 'function') {
                    return window.appAuth.isAuthenticated();
                }
                if (window.appAuth.userData && window.appAuth.userData.email) {
                    return true;
                }
                if (window.__APP_STATE && window.__APP_STATE.tokenValid === true) {
                    return true;
                }
            }
            return !!Utils.getToken();
        },

        getCredits: () => {
            if (window.appAuth) {
                if (typeof window.appAuth.getCredits === 'function') {
                    return window.appAuth.getCredits() || 0;
                }
                if (window.appAuth.userData && window.appAuth.userData.credits !== undefined) {
                    return window.appAuth.userData.credits || 0;
                }
            }
            if (window.__APP_STATE && window.__APP_STATE.credits !== undefined) {
                return window.__APP_STATE.credits || 0;
            }
            return 0;
        },

        getCreditsDisplay: () => {
            if (window.appAuth && window.appAuth.userData) {
                const credits = Utils.getCredits();
                const isAdmin = window.appAuth.userData.is_admin || false;
                const isPremium = window.appAuth.userData.is_premium || false;
                if (isAdmin) return '∞';
                if (isPremium) return `${Math.min(credits, CONFIG.CREDITS.MAX_CREDITS_PREMIUM)}/${CONFIG.CREDITS.MAX_CREDITS_PREMIUM}`;
                return String(credits);
            }
            return String(Utils.getCredits());
        },

        formatCurrency: (value) => {
            if (value === undefined || value === null || isNaN(value)) return 'R$ 0,00';
            return 'R$ ' + Number(value).toFixed(2).replace('.', ',');
        },

        formatCompactCurrency: (value) => {
            if (value === undefined || value === null || isNaN(value)) return 'R$ 0';
            const num = Number(value);
            if (num >= 1000000) return 'R$ ' + (num / 1000000).toFixed(1) + 'M';
            if (num >= 1000) return 'R$ ' + (num / 1000).toFixed(1) + 'k';
            return 'R$ ' + num.toFixed(0);
        },

        formatPercentage: (value) => {
            if (value === undefined || value === null || isNaN(value)) return '0%';
            return (Number(value) * 100).toFixed(0) + '%';
        },

        // 🔥 CORRIGIDO v16.16: BUSCA INTELIGENTE EM MULTIPLAS FONTES
        extractRealChartData: (data) => {
            if (!data) {
                console.warn('⚠️ [extractRealChartData] Dados vazios');
                return null;
            }

            console.log('🔍 [extractRealChartData] Buscando chart_data em:', Object.keys(data));

            let chartData = null;
            let sourceFound = 'nenhum';

            // 🔥 TENTA TODAS AS FONTES POSSÍVEIS

            // 1. Direto no objeto
            if (data.chart_data) {
                chartData = data.chart_data;
                sourceFound = 'data.chart_data';
                console.log('   ✅ Encontrado em data.chart_data');
            }
            // 2. Dentro de result
            else if (data.result && data.result.chart_data) {
                chartData = data.result.chart_data;
                sourceFound = 'result.chart_data';
                console.log('   ✅ Encontrado em result.chart_data');
            }
            // 3. Dentro de analysis
            else if (data.analysis && data.analysis.chart_data) {
                chartData = data.analysis.chart_data;
                sourceFound = 'analysis.chart_data';
                console.log('   ✅ Encontrado em analysis.chart_data');
            }
            // 4. Dentro de data.data
            else if (data.data && data.data.chart_data) {
                chartData = data.data.chart_data;
                sourceFound = 'data.data.chart_data';
                console.log('   ✅ Encontrado em data.data.chart_data');
            }
            // 5. Dentro de result.analysis
            else if (data.result && data.result.analysis && data.result.analysis.chart_data) {
                chartData = data.result.analysis.chart_data;
                sourceFound = 'result.analysis.chart_data';
                console.log('   ✅ Encontrado em result.analysis.chart_data');
            }
            // 6. Se o próprio objeto tem weekly
            else if (data.weekly) {
                chartData = data;
                sourceFound = 'data.weekly';
                console.log('   ✅ Encontrado diretamente (tem weekly)');
            }
            // 7. Dentro de result se tem weekly
            else if (data.result && data.result.weekly) {
                chartData = data.result;
                sourceFound = 'result.weekly';
                console.log('   ✅ Encontrado em result (tem weekly)');
            }
            // 8. Dentro de analysis se tem weekly
            else if (data.analysis && data.analysis.weekly) {
                chartData = data.analysis;
                sourceFound = 'analysis.weekly';
                console.log('   ✅ Encontrado em analysis (tem weekly)');
            }
            // 9. Tentar extrair de files
            else if (data.files && Array.isArray(data.files)) {
                for (const file of data.files) {
                    if (file.chart_data) {
                        chartData = file.chart_data;
                        sourceFound = 'files[].chart_data';
                        console.log('   ✅ Encontrado em files');
                        break;
                    }
                    if (file.weekly) {
                        chartData = file;
                        sourceFound = 'files[].weekly';
                        console.log('   ✅ Encontrado em files (weekly)');
                        break;
                    }
                }
            }

            if (!chartData) {
                console.warn('⚠️ [extractRealChartData] Nenhum chart_data encontrado');
                console.log('   📦 Estrutura do data:', JSON.stringify(data, null, 2).slice(0, 500));
                return null;
            }

            // 🔥 VERIFICA SE TEM DADOS REAIS
            if (chartData.weekly) {
                const revenue = chartData.weekly.revenue || [];
                const costs = chartData.weekly.costs || [];
                const services = chartData.performance?.services || [];

                const hasRevenue = revenue.some(v => v > 0);
                const hasCosts = costs.some(v => v > 0);
                const hasServices = services.some(v => v > 0);

                console.log(`📊 [extractRealChartData] Dados encontrados (fonte: ${sourceFound}):`);
                console.log(`   Revenue: ${revenue.length} valores, ${hasRevenue ? '✅ com dados' : '⚠️ vazio'}`);
                console.log(`   Costs: ${costs.length} valores, ${hasCosts ? '✅ com dados' : '⚠️ vazio'}`);
                console.log(`   Services: ${services.length} valores, ${hasServices ? '✅ com dados' : '⚠️ vazio'}`);

                // 🔥 SE PELO MENOS UM TIPO DE DADO EXISTE, RETORNA
                if (hasRevenue || hasCosts || hasServices) {
                    return chartData;
                }

                console.warn('⚠️ [extractRealChartData] Dados vazios (todos os arrays vazios ou com zeros)');
                return null;
            }

            console.warn('⚠️ [extractRealChartData] Formato inválido - sem weekly');
            return null;
        },

        getHealthStatus: (score) => {
            if (score >= 0.7) return { status: 'excelente', color: '#48bb78', icon: '🟢', label: 'Excelente' };
            if (score >= 0.5) return { status: 'bom', color: '#4a9eff', icon: '🔵', label: 'Bom' };
            if (score >= 0.3) return { status: 'regular', color: '#f5a623', icon: '🟡', label: 'Regular' };
            return { status: 'critico', color: '#f56565', icon: '🔴', label: 'Crítico' };
        },

        debounce: (func, wait) => {
            let timeout;
            return function(...args) {
                clearTimeout(timeout);
                timeout = setTimeout(() => func.apply(this, args), wait);
            };
        }
    };

    // ==============================================
    // 🔥 MESSAGE GUIDE - GUIAS PARA O USUÁRIO
    // ==============================================

    class MessageGuide {
        constructor() {
            this.container = document.getElementById('messageContainer');
            this._dismissedMessages = new Set();
            this._loadDismissedState();
            this._setupListeners();
        }

        _loadDismissedState() {
            try {
                const saved = localStorage.getItem('_dismissed_messages');
                if (saved) {
                    const parsed = JSON.parse(saved);
                    if (Array.isArray(parsed)) {
                        this._dismissedMessages = new Set(parsed);
                    }
                }
            } catch (e) {}
        }

        _saveDismissedState() {
            try {
                const arr = Array.from(this._dismissedMessages);
                localStorage.setItem('_dismissed_messages', JSON.stringify(arr));
            } catch (e) {}
        }

        _setupListeners() {
            document.addEventListener('app:state_changed', () => {
                setTimeout(() => this.render(), 100);
            });
            document.addEventListener('analysis:success', () => {
                setTimeout(() => this.renderAnalysisGuide(), 500);
            });
        }

        render() {
            const state = window.__APP_STATE || {};
            const credits = state.credits || 0;
            const isPremium = state.isPremium || false;
            const totalAnalyses = state.totalAnalyses || 0;

            // 🔥 GUIA BASEADO NO ESTADO DO USUÁRIO
            if (totalAnalyses === 0 && credits > 0) {
                this._showMessage({
                    id: 'welcome_guide',
                    title: '🚀 Comece sua primeira análise!',
                    message: 'Faça upload de um arquivo CSV ou Excel para começar. Você tem <strong>' + credits + ' créditos</strong> disponíveis.',
                    icon: 'fa-rocket',
                    color: 'primary',
                    show_action: true,
                    action_text: 'Enviar arquivo',
                    action_url: '#upload',
                    priority: 10
                });
            } else if (credits === 0 && !isPremium) {
                this._showMessage({
                    id: 'no_credits_guide',
                    title: '💡 Seus créditos acabaram!',
                    message: 'Assine o plano Premium para receber <strong>1 crédito por dia</strong> e continuar analisando.',
                    icon: 'fa-coins',
                    color: 'warning',
                    show_action: true,
                    action_text: 'Ver planos Premium',
                    action_url: '/planos',
                    priority: 8
                });
            } else if (isPremium && credits < CONFIG.CREDITS.MAX_CREDITS_PREMIUM) {
                this._showMessage({
                    id: 'premium_credits_guide',
                    title: '⭐ Você tem créditos Premium!',
                    message: 'Você tem <strong>' + credits + ' créditos</strong> disponíveis. Clique no botão "Receber Crédito" para ganhar mais 1 crédito hoje.',
                    icon: 'fa-star',
                    color: 'success',
                    show_action: false,
                    priority: 5
                });
            }
        }

        renderAnalysisGuide() {
            this._showMessage({
                id: 'analysis_done_guide',
                title: '✅ Análise concluída!',
                message: 'Os gráficos abaixo mostram os insights gerados pela IA. Passe o mouse para ver detalhes.',
                icon: 'fa-check-circle',
                color: 'success',
                show_action: false,
                priority: 7,
                auto_dismiss: 8000
            });
        }

        _showMessage(config) {
            if (!this.container) return;
            
            const id = config.id || 'msg_' + Date.now();
            if (this._dismissedMessages.has(id)) return;

            const { title, message, icon, color, show_action, action_text, action_url, priority, auto_dismiss } = config;

            const colorClass = color || 'info';
            const iconClass = icon || 'fa-info-circle';
            const isExternal = action_url && (action_url.startsWith('http') || action_url.startsWith('//'));
            const targetAttr = isExternal ? 'target="_blank" rel="noopener noreferrer"' : '';

            this.container.innerHTML = '';

            const banner = document.createElement('div');
            banner.className = `message-banner message-${colorClass}`;
            banner.dataset.messageId = id;
            banner.dataset.priority = priority || 0;
            
            banner.innerHTML = `
                <div class="message-content">
                    <div class="message-icon"><i class="fas ${iconClass}"></i></div>
                    <div class="message-text">
                        <div class="message-title">${title}</div>
                        <div class="message-body">${message}</div>
                        ${show_action ? `
                            <div class="message-action">
                                <a href="${action_url || '#'}" class="btn btn-${colorClass}" ${targetAttr}>
                                    ${action_text || 'Ver mais'} <i class="fas fa-arrow-right ms-1"></i>
                                </a>
                            </div>
                        ` : ''}
                    </div>
                    <button class="message-dismiss btn-close" aria-label="Fechar"></button>
                </div>
            `;

            this.container.appendChild(banner);
            this.container.style.display = 'block';

            requestAnimationFrame(() => {
                banner.classList.add('message-visible');
            });

            const dismissBtn = banner.querySelector('.message-dismiss');
            if (dismissBtn) {
                dismissBtn.addEventListener('click', () => {
                    this._dismissedMessages.add(id);
                    this._saveDismissedState();
                    this._hideContainer();
                });
            }

            if (auto_dismiss) {
                setTimeout(() => {
                    this._dismissedMessages.add(id);
                    this._saveDismissedState();
                    this._hideContainer();
                }, auto_dismiss);
            }
        }

        _hideContainer() {
            if (this.container) {
                this.container.style.display = 'none';
                this.container.innerHTML = '';
            }
        }

        refresh() {
            this._dismissedMessages.clear();
            this._saveDismissedState();
            this.render();
        }
    }

    // ==============================================
    // 🔥 DASHBOARD - CLASSE PRINCIPAL (v16.16)
    // ==============================================

    class Dashboard {
        constructor() {
            this._initialized = false;
            this._uploadInProgress = false;
            this._pollingInterval = null;
            this._creditManager = null;
            
            this._chartInstances = {
                revenue: null,
                performance: null,
                monthly: null
            };
            
            this._analysisHistory = [];
            this._currentAnalysisId = null;
            this._lastChartData = null;
            
            // 🔥 BINDS
            this.uploadMultipleFiles = this.uploadMultipleFiles.bind(this);
            this._handleChartDataReady = this._handleChartDataReady.bind(this);
            this._renderAllCharts = this._renderAllCharts.bind(this);
            this._renderRevenueChart = this._renderRevenueChart.bind(this);
            this._renderPerformanceChart = this._renderPerformanceChart.bind(this);
            this._renderMonthlyChart = this._renderMonthlyChart.bind(this);
            this._renderGPSA = this._renderGPSA.bind(this);
            this._switchAnalysis = this._switchAnalysis.bind(this);
        }

        // ==========================================
        // 🔥 INICIALIZAÇÃO
        // ==========================================

        async init() {
            if (this._initialized) {
                console.log('ℹ️ [Dashboard] Já inicializado');
                return this;
            }

            console.log('🚀 [Dashboard v16.16] Inicializando com busca inteligente de dados...');

            this._creditManager = new CreditManager();
            await this._creditManager.sync(true);
            
            this._messageGuide = new MessageGuide();
            
            this._setupChartListener();
            this._setupUploadHandlers();
            this._setupPolling();
            
            this._initialized = true;
            
            console.log('✅ [Dashboard v16.16] Inicializado com sucesso!');
            console.log(`   💰 Saldo: ${this._creditManager.display}`);
            console.log(`   📊 3 gráficos + GPSA (Performance da Oficina)`);
            
            return this;
        }

        // ==========================================
        // 🔥 SETUP CHART LISTENER
        // ==========================================

        _setupChartListener() {
            console.log('📊 [Dashboard] Configurando chart listeners...');
            
            document.removeEventListener('chart:data_ready', this._handleChartDataReady);
            document.removeEventListener('dashboard:render_chart', this._handleChartDataReady);
            window.removeEventListener('chart:data_ready', this._handleChartDataReady);
            
            document.addEventListener('chart:data_ready', this._handleChartDataReady);
            document.addEventListener('dashboard:render_chart', this._handleChartDataReady);
            window.addEventListener('chart:data_ready', this._handleChartDataReady);
            
            console.log('📊 [Dashboard] Chart listeners configurados');
        }

        // 🔥 CORRIGIDO v16.16: HANDLER COM EXTRAÇÃO MELHORADA
        _handleChartDataReady(e) {
            const detail = e.detail || {};
            const chartData = detail.chart_data || detail;
            
            console.log('📊 [Dashboard] Evento chart:data_ready recebido');
            
            const realData = Utils.extractRealChartData(chartData);
            
            if (realData) {
                this._lastChartData = realData;
                this._renderAllCharts(realData);
                this._renderGPSA(realData);
                
                const resultContainer = document.getElementById('resultContainer');
                if (resultContainer) {
                    resultContainer.classList.add('show');
                    resultContainer.style.display = 'block';
                }
                
                const placeholder = document.getElementById('resultPlaceholder');
                if (placeholder) {
                    placeholder.style.display = 'none';
                }
                
                if (this._messageGuide) {
                    this._messageGuide.renderAnalysisGuide();
                }
            } else {
                console.warn('⚠️ [Dashboard] Nenhum dado real recebido do ML');
                this._showToast('⚠️ Aguardando dados da análise...', 'info');
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
                        if (this._messageGuide) {
                            this._messageGuide._showMessage({
                                id: 'upload_started_guide',
                                title: '📤 Upload iniciado!',
                                message: 'A IA está processando seu arquivo. Aguarde alguns segundos...',
                                icon: 'fa-spinner fa-spin',
                                color: 'info',
                                show_action: false,
                                priority: 9,
                                auto_dismiss: 5000
                            });
                        }
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
                        if (this._messageGuide) {
                            this._messageGuide._showMessage({
                                id: 'upload_started_guide',
                                title: '📤 Upload iniciado!',
                                message: 'A IA está processando seu arquivo. Aguarde alguns segundos...',
                                icon: 'fa-spinner fa-spin',
                                color: 'info',
                                show_action: false,
                                priority: 9,
                                auto_dismiss: 5000
                            });
                        }
                        this.uploadMultipleFiles(files);
                    }
                });
            }
        }

        // ==========================================
        // 🔥 UPLOAD MÚLTIPLO
        // ==========================================

        async uploadMultipleFiles(files) {
            if (this._uploadInProgress) {
                this._showToast('⏳ Um upload já está em andamento.', 'warning');
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
                    this._showToast(`⚠️ Máximo de ${CONFIG.MAX_FILES_PER_BATCH} arquivos.`, 'warning');
                    return null;
                }

                for (const file of files) {
                    if (file.size > CONFIG.MAX_FILE_SIZE_KB * 1024) {
                        this._showToast(`⚠️ ${file.name} excede ${CONFIG.MAX_FILE_SIZE_KB}KB.`, 'warning');
                        return null;
                    }
                }

                await this._creditManager.sync(true);
                
                if (!this._creditManager.hasCredits(CONFIG.CREDITS.COST_PER_UPLOAD)) {
                    this._showToast('❌ Créditos insuficientes.', 'error');
                    this._showUpgradePrompt();
                    return null;
                }

                this._showUploadStatus('⏳', 'Preparando upload...', 'Verificando créditos', 5);
                this._uploadInProgress = true;

                const formData = new FormData();
                for (const file of files) {
                    formData.append('files', file);
                }
                formData.append('analysis_type', 'auto');
                formData.append('report_format', 'html');

                const token = Utils.getToken();
                const powHeaders = await this._getPowHeaders();

                this._showUploadStatus('⏳', 'Enviando arquivos...', `Processando ${files.length} arquivo(s)`, 30);

                const response = await fetch('/api/upload-multi-analyze', {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        ...powHeaders
                    },
                    body: formData
                });

                if (!response.ok) {
                    let errorDetail = 'Erro no upload';
                    try {
                        const errorData = await response.json();
                        errorDetail = errorData.detail?.message || errorData.message || errorDetail;
                    } catch (e) {}

                    if (response.status === 428 || response.status === 400) {
                        this._showUploadStatus('🔄', 'Renovando segurança...', 'Tentando novamente', 20);
                        await this._renewPow();
                        this._showToast('🔄 Tentando novamente...', 'info');
                        return this.uploadMultipleFiles(files);
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
                        
                        await this._forceSyncCredits();
                    } else {
                        console.warn('⚠️ Polling falhou, usando resposta original');
                        await this._processUploadResult(result, files);
                        this._showToast('✅ Upload processado!', 'success');
                        this._showResult();
                        await this._forceSyncCredits();
                    }
                }

                this._uploadInProgress = false;
                return result;

            } catch (error) {
                console.error('❌ Erro no upload:', error);
                this._showUploadStatus('❌', 'Erro', error.message || 'Falha no processamento', 0);
                this._showToast(`❌ ${error.message || 'Erro ao processar'}`, 'error');
                this._uploadInProgress = false;
                return null;
            }
        }

        // ==========================================
        // 🔥 PROCESSAR RESULTADO DO UPLOAD (CORRIGIDO v16.16)
        // ==========================================

        async _processUploadResult(result, files) {
            if (!result || !result.success) {
                console.warn('⚠️ Resultado inválido:', result);
                return;
            }

            console.log('📊 [ProcessResult] Processando resultado do ML...');
            console.log('   📦 Dados recebidos:', Object.keys(result));

            const analysis = result.analysis || {};
            
            // 🔥 EXTRAIR CHART_DATA - TENTA TODAS AS FONTES
            let chartData = null;
            
            // Tenta várias fontes
            if (result.chart_data) {
                chartData = result.chart_data;
                console.log('   ✅ chart_data encontrado em result');
            } else if (result.result && result.result.chart_data) {
                chartData = result.result.chart_data;
                console.log('   ✅ chart_data encontrado em result.result');
            } else if (analysis.chart_data) {
                chartData = analysis.chart_data;
                console.log('   ✅ chart_data encontrado em analysis');
            } else if (result.data && result.data.chart_data) {
                chartData = result.data.chart_data;
                console.log('   ✅ chart_data encontrado em result.data');
            } else if (result.weekly) {
                chartData = result;
                console.log('   ✅ chart_data encontrado diretamente (tem weekly)');
            } else if (result.result && result.result.weekly) {
                chartData = result.result;
                console.log('   ✅ chart_data encontrado em result (weekly)');
            }
            
            // 🔥 SE NÃO ENCONTROU, BUSCAR DO BACKEND DIRETAMENTE
            if (!chartData && result.process_id) {
                console.log('🔄 [ProcessResult] Buscando chart_data do backend...');
                try {
                    const token = Utils.getToken();
                    const response = await fetch(`/api/analysis/result/${result.process_id}`, {
                        headers: { 'Authorization': `Bearer ${token}` }
                    });
                    if (response.ok) {
                        const fullResult = await response.json();
                        chartData = fullResult.chart_data || 
                                   fullResult.analysis?.chart_data || 
                                   fullResult.result?.chart_data || 
                                   null;
                        console.log('📊 [ProcessResult] Chart_data do backend:', chartData ? '✅' : '❌');
                        if (chartData) {
                            console.log('   📈 Revenue:', chartData.weekly?.revenue?.length || 0, 'valores');
                        }
                    }
                } catch (e) {
                    console.warn('⚠️ [ProcessResult] Erro ao buscar do backend:', e);
                }
            }

            // 🔥 MOSTRAR DADOS ENCONTRADOS
            if (chartData) {
                console.log('📊 [ProcessResult] ChartData encontrado!');
                console.log('   📈 Revenue:', chartData.weekly?.revenue?.length || 0, 'valores');
                console.log('   📊 Services:', chartData.performance?.services?.length || 0, 'valores');
                console.log('   📅 Monthly:', chartData.monthly?.revenue?.length || 0, 'valores');
            } else {
                console.warn('⚠️ [ProcessResult] Nenhum chartData encontrado');
                this._showToast('⚠️ Dados da análise não disponíveis.', 'warning');
                return;
            }

            // 🔥 SALVAR NO HISTÓRICO
            const analysisEntry = {
                id: result.process_id || Date.now(),
                filename: files[0]?.name || 'Análise',
                rows: analysis.rows_processed || 0,
                chart_data: chartData,
                metrics: analysis.metrics || {},
                recommendations: analysis.recommendations || [],
                insights: analysis.insights || {},
                executive_score: analysis.executive_score || {},
                executive_summary: analysis.executive_summary || '',
                isActive: true,
                success: true,
                predictions: analysis.predictions || []
            };

            this._analysisHistory.unshift(analysisEntry);
            this._currentAnalysisId = analysisEntry.id;

            // 🔥 RENDERIZAR GRÁFICOS
            this._lastChartData = chartData;
            this._renderAllCharts(chartData);
            this._renderGPSA(chartData);

            // 🔥 ATUALIZAR UI
            await this._updateMetrics({
                executive_score: analysis.executive_score || {},
                chart_data: chartData || {}
            });

            await this._updateAIReport({
                executive_score: analysis.executive_score || {},
                executive_summary: analysis.executive_summary || '',
                recommendations: analysis.recommendations || [],
                chart_data: chartData || {},
                forecast: analysis.forecast || '',
                general_conclusion: analysis.general_conclusion || '',
                comparison: analysis.comparison || {},
                trend: analysis.trend || {}
            });

            document.dispatchEvent(new CustomEvent('analysis:success', {
                detail: { result: result }
            }));

            console.log('✅ [ProcessResult] Upload processado com sucesso!');
        }

        // ==========================================
        // 🔥 POLLING DE PROGRESSO
        // ==========================================

        async _pollProgress(processId) {
            console.log(`📡 [Polling] Iniciando para process_id: ${processId}`);
            
            let attempts = 0;
            const maxAttempts = CONFIG.POLLING.MAX_ATTEMPTS;
            const interval = CONFIG.POLLING.INTERVAL;
            const startTime = Date.now();
            
            this._showUploadStatus('🔄', 'Processando...', 'Iniciando análise', 10);
            
            return new Promise((resolve) => {
                const poll = async () => {
                    attempts++;
                    
                    if (Date.now() - startTime > CONFIG.POLLING.TIMEOUT_MS) {
                        console.warn('⏰ [Polling] Timeout excedido');
                        this._showUploadStatus('⏳', 'Tempo limite', 'A análise está demorando', 95);
                        resolve({ success: false, error: 'Timeout' });
                        return;
                    }
                    
                    try {
                        const token = Utils.getToken();
                        if (!token) {
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
                                resolve({ success: false, error: 'Processo não encontrado' });
                                return;
                            }
                            throw new Error(`Status: ${response.status}`);
                        }
                        
                        const data = await response.json();
                        console.log(`📡 [Polling] Tentativa ${attempts}: status=${data.status}, progress=${data.progress}%`);
                        
                        if (data.status === 'completed') {
                            console.log('✅ [Polling] Análise concluída!');
                            this._showUploadStatus('✅', 'Análise concluída!', '100%', 100);
                            
                            // 🔥 EXTRAIR CHART DATA - TENTA TODAS AS FONTES
                            let chartData = null;
                            
                            if (data.result && data.result.chart_data) {
                                chartData = data.result.chart_data;
                                console.log('📊 [Polling] chart_data em result');
                            } else if (data.chart_data) {
                                chartData = data.chart_data;
                                console.log('📊 [Polling] chart_data em data');
                            } else if (data.analysis && data.analysis.chart_data) {
                                chartData = data.analysis.chart_data;
                                console.log('📊 [Polling] chart_data em analysis');
                            } else if (data.result && data.result.weekly) {
                                chartData = data.result;
                                console.log('📊 [Polling] chart_data em result (weekly)');
                            } else if (data.weekly) {
                                chartData = data;
                                console.log('📊 [Polling] chart_data em data (weekly)');
                            }
                            
                            if (chartData) {
                                console.log('📊 [Polling] ChartData encontrado!');
                                console.log(`   Revenue: ${chartData.weekly?.revenue?.length || 0} valores`);
                                this._lastChartData = chartData;
                                this._renderAllCharts(chartData);
                                this._renderGPSA(chartData);
                            } else {
                                console.warn('⚠️ [Polling] Nenhum chartData encontrado');
                                console.log('   📦 Estrutura do data:', Object.keys(data));
                                if (data.result) {
                                    console.log('   📦 Estrutura do result:', Object.keys(data.result));
                                }
                            }
                            
                            const resultData = data.result || data;
                            if (chartData) {
                                resultData.chart_data = chartData;
                            }
                            
                            resolve({
                                success: true,
                                result: resultData
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
                            
                            const partialChartData = Utils.extractRealChartData(data);
                            if (partialChartData && partialChartData.weekly) {
                                this._renderAllCharts(partialChartData);
                                this._renderGPSA(partialChartData);
                            }
                            
                            setTimeout(poll, interval);
                            return;
                            
                        } else if (data.status === 'pending_credit') {
                            this._showUploadStatus('💳', 'Aguardando crédito', 'Assine Premium para liberar', 95);
                            setTimeout(poll, interval * 2);
                            return;
                            
                        } else {
                            if (attempts >= maxAttempts) {
                                this._showUploadStatus('⏳', 'Tempo limite', 'A análise está demorando', 95);
                                resolve({ success: false, error: 'Timeout' });
                                return;
                            }
                            setTimeout(poll, interval);
                            return;
                        }
                        
                    } catch (error) {
                        console.error('❌ [Polling] Erro:', error);
                        if (attempts < maxAttempts) {
                            await Utils.sleep(CONFIG.POLLING.RETRY_DELAY);
                            poll();
                        } else {
                            resolve({ success: false, error: error.message });
                        }
                    }
                };
                
                poll();
            });
        }

        // ==========================================
        // 🔥 RENDERIZAR GRÁFICOS (DADOS REAIS)
        // ==========================================

        _renderAllCharts(chartData) {
            if (!chartData) {
                console.warn('⚠️ [Charts] Nenhum dado para renderizar');
                return;
            }

            console.log('📊 [Charts] Renderizando 3 gráficos com dados reais...');

            this._renderRevenueChart(chartData);
            this._renderPerformanceChart(chartData);
            this._renderMonthlyChart(chartData);

            console.log('✅ [Charts] Todos os gráficos renderizados!');
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
            const revenue = weekly.revenue || [];
            const costs = weekly.costs || [];

            const hasRevenue = revenue.some(v => v > 0);
            const hasCosts = costs.some(v => v > 0);

            if (!hasRevenue && !hasCosts) {
                console.warn('⚠️ [Chart] Dados vazios - NÃO RENDERIZANDO');
                this._showToast('⚠️ Dados financeiros não disponíveis.', 'warning');
                return;
            }

            console.log(`📊 [RevenueChart] Renderizando: ${revenue.length} valores de receita, ${costs.length} de custos`);

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
                            data: revenue.length ? revenue : [0, 0, 0, 0, 0, 0, 0],
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
                            data: costs.length ? costs : [0, 0, 0, 0, 0, 0, 0],
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
                    animation: { duration: CONFIG.CHART.ANIMATION_DURATION, easing: 'easeOutQuart' },
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

            console.log('✅ [Chart] Gráfico de receita renderizado');
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
                console.warn('⚠️ [Chart] Dados de serviços vazios - NÃO RENDERIZANDO');
                return;
            }

            console.log(`📊 [PerformanceChart] Renderizando: ${services.length} valores de serviços`);

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
                    animation: { duration: CONFIG.CHART.ANIMATION_DURATION, easing: 'easeOutQuart' },
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
                console.warn('⚠️ [Chart] Dados mensais vazios - NÃO RENDERIZANDO');
                return;
            }

            console.log(`📊 [MonthlyChart] Renderizando: ${revenue.length} valores mensais`);

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
                    animation: { duration: CONFIG.CHART.ANIMATION_DURATION, easing: 'easeOutQuart' },
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
        // 🔥 GPSA (COM DADOS REAIS)
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
            
            console.log('✅ [GPSA] Renderizado com sucesso!');
        }

        // ==========================================
        // 🔥 GPSA - ABAS (MANTIDAS)
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

        _renderGPSAServicos(labels, services, totalServices, avgServices, maxService, peakDay) {
            const daysWithServices = services.filter(s => s > 0).length;
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
        // 🔥 ATUALIZAR RELATÓRIO DA IA
        // ==========================================

        async _updateAIReport(data) {
            const reportContainer = document.getElementById('aiReportContent');
            if (!reportContainer) return;

            const { executive_score, executive_summary, recommendations, forecast, general_conclusion, trend } = data;

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
        // 🔥 MÉTODOS AUXILIARES
        // ==========================================

        _switchAnalysis(analysisId) {
            if (analysisId === this._currentAnalysisId) return;

            console.log(`🔄 [Dashboard] Alternando para análise: ${analysisId}`);

            this._analysisHistory.forEach(a => {
                a.isActive = a.id === analysisId;
            });
            this._currentAnalysisId = analysisId;

            const analysis = this._analysisHistory.find(a => a.id === analysisId);
            if (!analysis || !analysis.chart_data) {
                console.warn('⚠️ [Dashboard] Análise sem dados');
                return;
            }

            this._renderAllCharts(analysis.chart_data);
            this._renderGPSA(analysis.chart_data);
        }

        _forceSyncCredits = async () => {
            console.log('🔄 [Dashboard] Sincronizando créditos...');
            try {
                await this._creditManager.sync(true);
                if (window.App && typeof window.App.updateCredits === 'function') {
                    window.App.updateCredits();
                }
                console.log(`✅ [Dashboard] Sincronizado: ${this._creditManager.display}`);
                return true;
            } catch (e) {
                console.error('❌ [Dashboard] Erro na sincronização:', e);
                return false;
            }
        }

        _getPowHeaders = async () => {
            try {
                if (window.powClient && typeof window.powClient.getSolutionForUpload === 'function') {
                    const solution = await window.powClient.getSolutionForUpload();
                    if (solution && solution.nonce) {
                        return {
                            'X-PoW-Nonce': solution.nonce,
                            'X-PoW-Challenge': solution.prefix || '',
                            'X-PoW-Difficulty': String(solution.difficulty || 4),
                            'X-PoW-Solution': solution.solution || '',
                            'X-PoW-Timestamp': String(Date.now())
                        };
                    }
                }
                return {};
            } catch (e) {
                console.warn('⚠️ Erro ao obter PoW:', e);
                return {};
            }
        }

        _renewPow = async () => {
            try {
                if (window.powClient) {
                    if (typeof window.powClient.clearCache === 'function') {
                        window.powClient.clearCache();
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

        _setupPolling() {
            setInterval(() => {
                if (this._creditManager) {
                    this._creditManager.syncDebounced();
                }
            }, CONFIG.CREDITS.SYNC_INTERVAL);
        }

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
                method(message, '', { timeOut: 5000, closeButton: true, progressBar: true });
            } else {
                console.log(`[${type}] ${message}`);
            }
        }

        _showUpgradePrompt() {
            setTimeout(() => {
                if (confirm('💎 Créditos insuficientes! Deseja ver os planos Premium?')) {
                    window.location.href = '/planos';
                }
            }, 500);
        }

        // ==========================================
        // 🔥 EXPORTAÇÃO
        // ==========================================

        getCredits() { return this._creditManager?.balance || 0; }
        getCreditsDisplay() { return this._creditManager?.display || '0'; }
        isPremium() { return this._creditManager?.isPremium || false; }
        isAdmin() { return this._creditManager?.isAdmin || false; }
        async refreshCredits() { return await this._creditManager?.sync(true); }
        async syncCredits() { return await this._creditManager?.syncCredits(); }
        async forceSyncCredits() { return await this._forceSyncCredits(); }
    }

    // ==============================================
    // 🔥 CREDIT MANAGER
    // ==============================================

    class CreditManager {
        constructor() {
            this._balance = 0;
            this._isPremium = false;
            this._isAdmin = false;
            this._lastSync = 0;
            this._syncInProgress = false;
            this._loadFromAppState();
            this._setupEventListeners();
            setTimeout(() => this.sync(true).catch(() => {}), 500);
            console.log('💰 [CreditManager] Inicializado');
        }

        _loadFromAppState() {
            try {
                if (window.__APP_STATE) {
                    this._balance = window.__APP_STATE.credits || 0;
                    this._isPremium = window.__APP_STATE.isPremium || false;
                    this._isAdmin = window.__APP_STATE.isAdmin || false;
                    return true;
                }
                if (window.appAuth) {
                    if (window.appAuth.userData) {
                        this._balance = window.appAuth.userData.credits || 0;
                        this._isPremium = window.appAuth.userData.is_premium || false;
                        this._isAdmin = window.appAuth.userData.is_admin || false;
                        return true;
                    }
                }
                const userData = localStorage.getItem('user_data');
                if (userData) {
                    const parsed = JSON.parse(userData);
                    this._balance = parsed.credits || 0;
                    this._isPremium = parsed.is_premium || false;
                    this._isAdmin = parsed.is_admin || false;
                    return true;
                }
            } catch (e) {}
            return false;
        }

        _setupEventListeners() {
            document.addEventListener('creditsUpdated', (e) => {
                const data = e.detail || {};
                if (data.credits !== undefined) {
                    this._balance = data.credits;
                    this._isPremium = data.isPremium || false;
                    this._isAdmin = data.isAdmin || false;
                    this._updateUI();
                }
            });
            document.addEventListener('app:state_changed', () => this._loadFromAppState());
            document.addEventListener('authLoginSuccess', () => setTimeout(() => this.sync(true), 500));
        }

        get balance() { return this._balance; }
        get isPremium() { return this._isPremium; }
        get isAdmin() { return this._isAdmin; }
        get display() {
            if (this.isAdmin) return '∞';
            if (this.isPremium) {
                const maxCredits = CONFIG.CREDITS.MAX_CREDITS_PREMIUM;
                return `${Math.min(this.balance, maxCredits)}/${maxCredits}`;
            }
            return String(Math.max(0, this.balance));
        }

        async sync(force = false) {
            if (this._syncInProgress && !force) return this._balance;
            this._syncInProgress = true;

            try {
                if (window.appAuth && typeof window.appAuth.getCredits === 'function') {
                    this._balance = window.appAuth.getCredits() || 0;
                    this._syncInProgress = false;
                    this._updateUI();
                    return this._balance;
                }

                const token = Utils.getToken();
                if (!token) {
                    this._syncInProgress = false;
                    return this._balance;
                }

                const response = await fetch('/api/auth/me', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });

                if (response.ok) {
                    const data = await response.json();
                    this._balance = data.credits || 0;
                    this._isPremium = data.is_premium || false;
                    this._isAdmin = data.is_admin || false;
                    this._lastSync = Date.now();
                    this._updateUI();
                }
            } catch (e) {
                console.warn('⚠️ [CreditManager] Erro sync:', e);
            } finally {
                this._syncInProgress = false;
            }
            return this._balance;
        }

        syncDebounced = Utils.debounce(() => this.sync().catch(() => {}), CONFIG.CREDITS.SYNC_DEBOUNCE || 300);

        hasCredits(required = 1) {
            if (this.isAdmin) return true;
            return this.balance >= required;
        }

        _updateUI() {
            const display = this.display;
            const selectors = [
                '#creditsCount', '#uploadCredits', '#creditsDisplay',
                '.credits-display', '#modalCreditsCount', '.credits-badge-nav span',
                '.user-credits', '#navbarCredits span'
            ];
            selectors.forEach(selector => {
                document.querySelectorAll(selector).forEach(el => {
                    if (el) el.textContent = display;
                });
            });
        }

        async syncCredits() { return await this.sync(true); }
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

    window.Dashboard = Dashboard;
    window.initDashboard = initDashboard;

    window.forceSyncCredits = function() {
        if (window.__dashboard) {
            return window.__dashboard.forceSyncCredits();
        }
        console.warn('⚠️ Dashboard não inicializado');
        return null;
    };

    console.log('='.repeat(60));
    console.log('🔥 dashboard.js v16.16 carregado');
    console.log('   ✅ BUSCA INTELIGENTE: chart_data em múltiplas fontes');
    console.log('   ✅ RECEBE dados reais do ML');
    console.log('   ✅ GRÁFICOS com dados reais (SEM FALLBACK)');
    console.log('   ✅ MENSAGENS para guiar o usuário');
    console.log('   📊 3 gráficos + GPSA');
    console.log('='.repeat(60));

})();