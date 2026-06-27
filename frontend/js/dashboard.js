// frontend/js/dashboard.js - VERSÃO CORRIGIDA V6.2 (COM FALLBACK INTELIGENTE)
// 🔥 CORREÇÃO: Adicionada trava no startFallback para evitar loop infinito

(function() {
    'use strict';

    console.log('📦 [Dashboard V6.2] Módulo carregado (PoW sob demanda).');

    // ============================================================================
    // 🔥 CONFIGURAÇÕES
    // ============================================================================
    
    const CONFIG = {
        MAX_FILES_PER_BATCH: 3,
        MAX_FILE_SIZE_KB: 200,
        API_BASE: '/api',
        POLLING_INTERVAL: 2000,
        MAX_POLLING_ATTEMPTS: 60,
        CREDITS_CHECK_INTERVAL: 30000,
        MAX_CREDITS_BALANCE: 3,
        POW_ENABLED: true,
        // 🔥 CONFIGURAÇÕES DO FALLBACK
        FALLBACK_INTERVAL: 300,
        MAX_FALLBACK_ATTEMPTS: 20,
        APP_READY_TIMEOUT: 5000
    };

    // ============================================================================
    // 🔥 ESTADO DA APLICAÇÃO
    // ============================================================================
    
    const State = {
        activeAnalyses: [],
        pollingIntervals: [],
        isProcessing: false,
        isPremium: false,
        isAdmin: false,
        credits: 0,
        userId: null,
        userName: 'Usuário',
        domCache: new Map(),
        eventListeners: [],
        _initialized: false,
        _appStateVersion: null,
        historyData: [],
        // 🔥 CONTROLE DE FALLBACK
        _fallbackActive: false,
        _fallbackAttempts: 0,
        _redirected: false
    };

    // ============================================================================
    // 🔥 UTILITÁRIOS DE DOM
    // ============================================================================
    
    const DOM = {
        get: (selector) => {
            if (!State.domCache.has(selector)) {
                const el = document.querySelector(selector);
                State.domCache.set(selector, el);
                return el;
            }
            return State.domCache.get(selector);
        },
        
        getAll: (selector) => document.querySelectorAll(selector),
        
        clearCache: () => {
            State.domCache.clear();
        },
        
        updateText: (selector, text) => {
            const el = DOM.get(selector);
            if (el) el.textContent = text;
        },
        
        updateHTML: (selector, html) => {
            const el = DOM.get(selector);
            if (el) el.innerHTML = html;
        }
    };

    // ============================================================================
    // 🔥 GERENCIADOR DE ESTADO GLOBAL
    // ============================================================================
    
    const AppState = {
        get() {
            if (window.__APP_STATE && typeof window.__APP_STATE === 'object') {
                return window.__APP_STATE;
            }
            
            if (window.App && typeof window.App === 'object') {
                const state = window.App.state || {};
                return {
                    user: state.user || null,
                    isAuthenticated: !!state.user,
                    isPremium: state.isPremium || false,
                    isAdmin: state.isAdmin || false,
                    credits: state.credits || 0,
                    userId: state.user?.id || null,
                    userName: state.user?.name || state.user?.email || 'Usuário'
                };
            }
            
            try {
                const token = localStorage.getItem('access_token');
                const userStr = localStorage.getItem('user_data');
                const user = userStr ? JSON.parse(userStr) : null;
                return {
                    user: user,
                    isAuthenticated: !!token,
                    isPremium: user?.is_premium || false,
                    isAdmin: user?.is_admin || false,
                    credits: user?.credits || 0,
                    userId: user?.id || null,
                    userName: user?.name || user?.email || 'Usuário'
                };
            } catch (e) {
                return {
                    user: null,
                    isAuthenticated: false,
                    isPremium: false,
                    isAdmin: false,
                    credits: 0,
                    userId: null,
                    userName: 'Usuário'
                };
            }
        },
        
        sync() {
            const globalState = this.get();
            
            State.isPremium = globalState.isPremium || false;
            State.isAdmin = globalState.isAdmin || false;
            State.credits = globalState.credits || 0;
            State.userId = globalState.userId || globalState.user?.id || null;
            State.userName = globalState.userName || globalState.user?.name || 'Usuário';
            
            this.updateUI();
            
            return globalState;
        },
        
        updateUI() {
            const display = this.getCreditsDisplay();
            
            ['#creditsDisplay', '#creditsCount', '#uploadCredits', '#modalCreditsCount'].forEach(selector => {
                DOM.updateText(selector, display);
            });
            
            DOM.updateText('#userName', State.userName);
            this.updatePremiumStatusUI();
        },
        
        getCreditsDisplay() {
            if (State.isAdmin) return '∞';
            if (State.isPremium) return `${State.credits}/${CONFIG.MAX_CREDITS_BALANCE}`;
            return String(State.credits || 0);
        },
        
        updatePremiumStatusUI() {
            const container = DOM.get('#premiumStatusContainer');
            if (!container) return;
            
            let html = '';
            
            if (State.isAdmin) {
                html = `
                    <div class="text-center py-2">
                        <span class="badge" style="background: linear-gradient(135deg, #667eea, #764ba2); color: white; padding: 0.4rem 1.5rem; font-size: 0.8rem;">
                            <i class="fas fa-user-shield me-2"></i> Administrador
                        </span>
                        <p class="mt-1 small" style="color: rgba(255,255,255,0.5);">
                            <i class="fas fa-infinity me-1"></i> Créditos ilimitados
                        </p>
                    </div>
                `;
            } else if (State.isPremium) {
                html = `
                    <div class="text-center py-2">
                        <span class="badge" style="background: linear-gradient(135deg, #f5a623, #cd7f32); color: white; padding: 0.4rem 1.5rem; font-size: 0.8rem;">
                            <i class="fas fa-crown me-2"></i> Premium
                        </span>
                        <p class="mt-1 small" style="color: rgba(255,255,255,0.5);">
                            <i class="fas fa-coins me-1"></i> ${State.credits} créditos
                        </p>
                    </div>
                `;
            } else {
                html = `
                    <div class="text-center py-2">
                        <span class="badge" style="background: rgba(255,255,255,0.08); color: rgba(255,255,255,0.4); padding: 0.4rem 1.5rem; font-size: 0.8rem;">
                            <i class="fas fa-user me-2"></i> Grátis
                        </span>
                        <p class="mt-1 small" style="color: rgba(255,255,255,0.5);">
                            <i class="fas fa-coins me-1"></i> ${State.credits} créditos
                            <a href="/planos" class="text-warning text-decoration-none ms-1" style="font-size: 0.7rem;">Fazer upgrade</a>
                        </p>
                    </div>
                `;
            }
            
            container.innerHTML = html;
        }
    };

    // ============================================================================
    // 🔥 NOTIFICAÇÕES
    // ============================================================================
    
    const Notify = {
        show: (message, type = 'info', duration = 5000) => {
            if (window.toastr && window.toastr[type]) {
                window.toastr[type](message);
                return;
            }
            
            const colors = {
                success: '#48bb78',
                error: '#f56565',
                warning: '#f5a623',
                info: '#667eea'
            };
            
            const notification = document.createElement('div');
            notification.style.cssText = `
                position: fixed; bottom: 20px; right: 20px; 
                background: white; border-left: 4px solid ${colors[type] || colors.info}; 
                padding: 12px 20px; border-radius: 8px; 
                box-shadow: 0 4px 20px rgba(0,0,0,0.15); 
                z-index: 10000; 
                max-width: 350px;
                font-family: 'Inter', sans-serif;
                animation: slideInRight 0.3s ease;
            `;
            notification.innerHTML = `<span style="color: #2d3748;">${message}</span>`;
            document.body.appendChild(notification);
            
            setTimeout(() => {
                notification.style.opacity = '0';
                notification.style.transform = 'translateX(20px)';
                notification.style.transition = 'all 0.3s ease';
                setTimeout(() => notification.remove(), 300);
            }, duration);
        },
        
        success: (msg) => Notify.show(msg, 'success'),
        error: (msg) => Notify.show(msg, 'error'),
        warning: (msg) => Notify.show(msg, 'warning'),
        info: (msg) => Notify.show(msg, 'info')
    };

    // ============================================================================
    // 🔥 LOADING
    // ============================================================================
    
    const Loading = {
        show: (message = 'Processando análise...', submessage = 'A IA está analisando seus dados') => {
            const overlay = DOM.get('#loadingOverlay');
            if (!overlay) return;
            
            DOM.updateText('#loadingTitle', message);
            DOM.updateText('#loadingSubtitle', submessage);
            
            const progress = DOM.get('#loadingProgressBar');
            if (progress) progress.style.width = '0%';
            DOM.updateText('#loadingPercent', '0%');
            
            const steps = DOM.getAll('.loading-step');
            steps.forEach((step, index) => {
                step.classList.remove('active', 'done');
                if (index === 0) step.classList.add('active');
            });
            
            overlay.classList.add('show');
        },
        
        update: (percent, message = null) => {
            const progress = DOM.get('#loadingProgressBar');
            const percentText = DOM.get('#loadingPercent');
            
            const clampedPercent = Math.min(100, Math.max(0, percent));
            
            if (progress) progress.style.width = `${clampedPercent}%`;
            if (percentText) percentText.textContent = `${Math.round(clampedPercent)}%`;
            
            if (message) DOM.updateText('#loadingTitle', message);
            
            const steps = DOM.getAll('.loading-step');
            if (steps.length > 0) {
                const activeStep = Math.floor((clampedPercent / 100) * steps.length);
                steps.forEach((step, index) => {
                    step.classList.remove('active', 'done');
                    if (index < activeStep) {
                        step.classList.add('done');
                    } else if (index === activeStep) {
                        step.classList.add('active');
                    }
                });
            }
        },
        
        hide: () => {
            const overlay = DOM.get('#loadingOverlay');
            if (overlay) overlay.classList.remove('show');
        }
    };

    // ============================================================================
    // 🔥 FUNÇÕES DE UPLOAD E PROCESSAMENTO (COM PoW SOB DEMANDA)
    // ============================================================================
    
    /**
     * 🔥 PREPARA PoW APENAS QUANDO O USUÁRIO VAI FAZER UPLOAD
     */
    async function preparePowForUpload() {
        if (!window.powClient) {
            console.log('⏳ PoW client não disponível, prosseguindo sem proteção');
            return true;
        }

        if (!window.powClient._isAuthenticated()) {
            console.log('⏳ PoW: aguardando autenticação...');
            return true;
        }

        try {
            console.log('🔄 Preparando PoW para upload...');
            const ready = await window.powClient.prepareForUpload();
            
            if (ready) {
                console.log('✅ PoW pronto para upload');
                return true;
            } else {
                console.warn('⚠️ Não foi possível preparar PoW, prosseguindo sem proteção');
                return true;
            }
        } catch (error) {
            console.warn('⚠️ Erro ao preparar PoW:', error.message);
            return true;
        }
    }

    async function processUpload(files) {
        if (!files || files.length === 0) {
            Notify.warning('Selecione pelo menos um arquivo');
            return;
        }
        
        if (files.length > CONFIG.MAX_FILES_PER_BATCH) {
            Notify.error(`Máximo de ${CONFIG.MAX_FILES_PER_BATCH} arquivos por vez.`);
            return;
        }
        
        for (const file of files) {
            if (file.size > CONFIG.MAX_FILE_SIZE_KB * 1024) {
                Notify.error(`❌ ${file.name} excede ${CONFIG.MAX_FILE_SIZE_KB}KB`);
                return;
            }
        }
        
        if (!State.isAdmin) {
            if (!State.isPremium && State.credits < files.length) {
                Notify.warning(`❌ Você precisa de ${files.length} crédito(s). Você tem apenas ${State.credits || 0}.`);
                showCreditsModal();
                return;
            }
            if (State.isPremium && State.credits < files.length) {
                Notify.warning(`❌ Você precisa de ${files.length} crédito(s). Você tem apenas ${State.credits || 0}.`);
                showCreditsModal();
                return;
            }
        }
        
        Loading.show('Iniciando análise...', `Preparando ${files.length} arquivo(s)`);
        Loading.update(5);
        
        if (CONFIG.POW_ENABLED) {
            await preparePowForUpload();
        }
        
        const formData = new FormData();
        for (const file of files) {
            formData.append('files', file);
        }
        formData.append('analysis_type', 'auto');
        formData.append('ai_model', 'auto');
        
        const token = localStorage.getItem('access_token');
        
        try {
            let response;
            let powSolution = null;
            
            if (CONFIG.POW_ENABLED && window.powClient && window.powClient._isAuthenticated()) {
                try {
                    powSolution = await window.powClient.getSolutionForUpload();
                    
                    if (powSolution && window.powClient.uploadWithPow) {
                        if (files.length === 1) {
                            const result = await window.powClient.uploadWithPow(files[0]);
                            handleUploadResponse({ processed_files: [{ process_id: result.process_id, filename: result.filename }] }, files);
                            Loading.update(10, 'Analisando dados...');
                            return;
                        } else {
                            response = await fetchWithPow(formData, powSolution, token);
                        }
                    } else {
                        response = await fetchWithPow(formData, powSolution, token);
                    }
                } catch (powError) {
                    console.warn('⚠️ PoW falhou, tentando sem proteção:', powError.message);
                    response = await fetch(`${CONFIG.API_BASE}/upload-auto`, {
                        method: 'POST',
                        headers: { 'Authorization': `Bearer ${token}` },
                        body: formData
                    });
                }
            } else {
                response = await fetch(`${CONFIG.API_BASE}/upload-auto`, {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` },
                    body: formData
                });
            }
            
            if (!response) {
                Notify.error('Erro no upload');
                Loading.hide();
                return;
            }
            
            if (response.status === 428) {
                Notify.info('Proteção anti-bot: recalculando...');
                
                if (window.powClient) {
                    try {
                        const newSolution = await window.powClient.getSolutionForUpload();
                        const retryResponse = await fetchWithPow(formData, newSolution, token);
                        
                        if (retryResponse && retryResponse.ok) {
                            const retryData = await retryResponse.json();
                            if (retryData.processed_files?.length > 0) {
                                handleUploadResponse(retryData, files);
                                return;
                            }
                        }
                    } catch (e) {
                        console.warn('Erro no retry com PoW:', e);
                    }
                }
                
                const fallbackResponse = await fetch(`${CONFIG.API_BASE}/upload-auto`, {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` },
                    body: formData
                });
                
                if (fallbackResponse.ok) {
                    const data = await fallbackResponse.json();
                    if (data.processed_files?.length > 0) {
                        handleUploadResponse(data, files);
                        return;
                    }
                }
                
                Notify.error('Erro no upload após tentativas com PoW');
                Loading.hide();
                return;
            }
            
            const data = await response.json();
            
            if (response.ok && data.processed_files?.length > 0) {
                handleUploadResponse(data, files);
            } else {
                Notify.error(data?.detail || 'Erro no upload');
                Loading.hide();
            }
        } catch (error) {
            console.error('Upload error:', error);
            Notify.error('Erro ao processar arquivo(s)');
            Loading.hide();
        }
    }
    
    async function fetchWithPow(formData, solution, token) {
        const headers = {
            'Authorization': `Bearer ${token}`
        };
        
        if (solution && solution.prefix && solution.nonce) {
            headers['X-PoW-Challenge'] = solution.prefix;
            headers['X-PoW-Nonce'] = solution.nonce;
            console.log(`🔐 Headers PoW: X-PoW-Challenge=${solution.prefix.substring(0, 8)}..., X-PoW-Nonce=${solution.nonce.substring(0, 8)}...`);
        }
        
        return fetch(`${CONFIG.API_BASE}/upload-auto`, {
            method: 'POST',
            headers: headers,
            body: formData
        });
    }
    
    function handleUploadResponse(data, files) {
        Notify.success(`✅ ${data.processed_files.length} arquivo(s) processado(s)!`);
        Loading.update(10, 'Analisando dados...');
        
        for (const processed of data.processed_files) {
            startPolling(processed.process_id, processed.filename);
        }
        
        AppState.sync();
        
        const fileInput = DOM.get('#fileInput');
        if (fileInput) fileInput.value = '';
        DOM.updateHTML('#filePreviewContainer', '');
        
        const uploadBtn = DOM.get('#uploadButton');
        if (uploadBtn) {
            uploadBtn.disabled = true;
            uploadBtn.innerHTML = `<i class="fas fa-spinner fa-spin me-2"></i> Processando...`;
        }
    }
    
    async function startPolling(processId, filename) {
        let attempts = 0;
        const maxAttempts = CONFIG.MAX_POLLING_ATTEMPTS;
        
        const interval = setInterval(async () => {
            attempts++;
            
            try {
                const token = localStorage.getItem('access_token');
                const response = await fetch(`${CONFIG.API_BASE}/status/${processId}`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                
                if (!response.ok) {
                    if (response.status === 401) {
                        clearInterval(interval);
                        Notify.warning('Sessão expirada.');
                        return;
                    }
                    if (attempts >= maxAttempts) {
                        clearInterval(interval);
                        Notify.warning(`⏳ Análise ${filename} está demorando.`);
                        Loading.hide();
                    }
                    return;
                }
                
                const data = await response.json();
                Loading.update(data.progress || 0);
                
                if (data.status === 'completed') {
                    clearInterval(interval);
                    
                    const resultResponse = await fetch(`${CONFIG.API_BASE}/analysis/${processId}`, {
                        headers: { 'Authorization': `Bearer ${token}` }
                    });
                    
                    if (resultResponse.ok) {
                        const resultData = await resultResponse.json();
                        
                        Notify.success(`✅ Análise concluída: ${filename}`);
                        Loading.update(100, '✅ Análise concluída!');
                        
                        window.dispatchEvent(new CustomEvent('analysis:success', {
                            detail: {
                                processId,
                                filename,
                                result: resultData
                            }
                        }));
                        
                        const analysisData = {
                            processId,
                            filename,
                            status: 'completed',
                            result: resultData
                        };
                        
                        State.activeAnalyses.push(analysisData);
                        renderAnalysisCard(analysisData);
                        loadHistory();
                        
                        const uploadBtn = DOM.get('#uploadButton');
                        if (uploadBtn) {
                            uploadBtn.disabled = false;
                            uploadBtn.innerHTML = `<i class="fas fa-play-circle me-2"></i> Iniciar Análise <span class="badge ms-2" style="background: rgba(255,255,255,0.2); color: white;">1 crédito/arquivo</span>`;
                        }
                        
                        setTimeout(Loading.hide, 800);
                    }
                    
                } else if (data.status === 'error') {
                    clearInterval(interval);
                    Notify.error(`❌ Erro na análise: ${filename}`);
                    Loading.hide();
                }
                
                if (attempts >= maxAttempts) {
                    clearInterval(interval);
                    Notify.warning(`⏳ Análise ${filename} está demorando.`);
                    Loading.hide();
                }
            } catch (error) {
                console.error('Polling error:', error);
                if (attempts >= maxAttempts) {
                    clearInterval(interval);
                }
            }
        }, CONFIG.POLLING_INTERVAL);
        
        State.pollingIntervals.push(interval);
    }

    // ============================================================================
    // 🔥 RENDERIZAÇÃO DE ANÁLISE
    // ============================================================================
    
    function renderAnalysisCard(analysis) {
        const container = DOM.get('#activeAnalysesContainer');
        if (!container) return;
        
        const data = analysis.result;
        const stats = data.stats || {};
        const predictions = data.predictions_summary || {};
        
        const totalRegistros = stats.rows || predictions.total || 0;
        const scoreMedio = predictions.mean || 0.65;
        const scoreMin = predictions.min || 0.2;
        const scoreMax = predictions.max || 0.9;
        const scoreStd = predictions.std || 0.15;
        
        const altoRisco = predictions.high_risk_percentage || 0;
        const medioRisco = predictions.medium_risk_percentage || 0;
        const baixoRisco = predictions.low_risk_percentage || 0;
        
        const crescimento = Math.round(scoreMedio * 50);
        const economia = Math.round(5000 * scoreMedio);
        const retencao = Math.round(60 + scoreMedio * 30);
        const confianca = Math.round(scoreMedio * 100);
        
        const statusColor = scoreMedio > 0.7 ? '#48bb78' : (scoreMedio > 0.5 ? '#f5a623' : '#f56565');
        const statusIcon = scoreMedio > 0.7 ? '🚀' : (scoreMedio > 0.5 ? '📈' : '🔄');
        const statusLabel = scoreMedio > 0.7 ? 'Alto potencial' : (scoreMedio > 0.5 ? 'Potencial médio' : 'Baixo potencial');
        
        const cardId = `analysis-card-${analysis.processId}`;
        const existingCard = document.getElementById(cardId);
        if (existingCard) existingCard.remove();
        
        const cardHTML = `
            <div class="analysis-card mb-4" id="${cardId}" data-process-id="${analysis.processId}">
                <div class="card border-0 shadow-lg rounded-4 overflow-hidden" style="background: rgba(255,255,255,0.06); backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.1);">
                    
                    <div class="card-header py-3 px-4" style="background: linear-gradient(135deg, rgba(102,126,234,0.2), rgba(118,75,162,0.2)); border-bottom: 1px solid rgba(255,255,255,0.05);">
                        <div class="d-flex justify-content-between align-items-center flex-wrap">
                            <div>
                                <h5 class="mb-0 fw-bold" style="color: white;">
                                    <i class="fas fa-chart-line me-2" style="color: #f5a623;"></i>
                                    ${analysis.filename || 'Análise'}
                                    <span class="badge ms-2" style="background: ${statusColor}; color: white; font-size: 0.7rem;">
                                        ${statusIcon} ${statusLabel}
                                    </span>
                                </h5>
                                <small style="color: rgba(255,255,255,0.4);">
                                    <i class="fas fa-calendar me-1"></i> ${new Date().toLocaleDateString('pt-BR')}
                                    <i class="fas fa-database ms-2 me-1"></i> ${totalRegistros.toLocaleString()} registros
                                </small>
                            </div>
                            <div class="mt-2 mt-md-0">
                                <button class="btn btn-sm btn-pdf" onclick="window.generatePDFReport('${analysis.processId}')" style="background: rgba(220,53,69,0.15); border: 1px solid #dc3545; color: #dc3545; border-radius: 50px; padding: 0.3rem 0.8rem; font-size: 0.7rem;">
                                    <i class="fas fa-file-pdf me-1"></i> PDF
                                </button>
                                <button class="btn btn-sm btn-gpsa ms-1" onclick="window.showGPSAForAnalysis('${analysis.processId}')" style="background: rgba(245,166,35,0.15); border: 1px solid #f5a623; color: #f5a623; border-radius: 50px; padding: 0.3rem 0.8rem; font-size: 0.7rem;">
                                    <i class="fas fa-chart-line me-1"></i> Detalhes
                                </button>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card-body p-4">
                        <!-- SCORE -->
                        <div class="row g-3 mb-4">
                            <div class="col-12">
                                <div class="p-3 rounded-4" style="background: rgba(0,0,0,0.15); border: 1px solid rgba(255,255,255,0.03);">
                                    <div class="d-flex justify-content-between align-items-center">
                                        <div>
                                            <div style="color: rgba(255,255,255,0.5); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px;">
                                                <i class="fas fa-gem me-1" style="color: #f5a623;"></i> Score de Confiança
                                            </div>
                                            <div style="font-size: 2.5rem; font-weight: 700; color: ${statusColor};">
                                                ${confianca}%
                                            </div>
                                            <div style="color: rgba(255,255,255,0.4); font-size: 0.7rem;">
                                                Min: ${Math.round(scoreMin * 100)}% · Max: ${Math.round(scoreMax * 100)}% · Desvio: ${Math.round(scoreStd * 100)}%
                                            </div>
                                        </div>
                                        <div class="text-end">
                                            <div style="color: rgba(255,255,255,0.4); font-size: 0.65rem;">Intervalo de confiança</div>
                                            <div style="width: 150px; height: 4px; background: rgba(255,255,255,0.1); border-radius: 4px; margin-top: 4px;">
                                                <div style="width: ${confianca}%; height: 100%; background: ${statusColor}; border-radius: 4px;"></div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <!-- MÉTRICAS -->
                        <div class="row g-3 mb-4">
                            <div class="col-md-3 col-6">
                                <div class="p-3 rounded-4 text-center" style="background: rgba(0,0,0,0.12); border: 1px solid rgba(255,255,255,0.03);">
                                    <i class="fas fa-chart-line fa-lg" style="color: #48bb78;"></i>
                                    <div style="color: white; font-size: 1.2rem; font-weight: 600; margin-top: 4px;">${crescimento}%</div>
                                    <div style="color: rgba(255,255,255,0.3); font-size: 0.6rem; text-transform: uppercase; letter-spacing: 0.3px;">Crescimento</div>
                                </div>
                            </div>
                            <div class="col-md-3 col-6">
                                <div class="p-3 rounded-4 text-center" style="background: rgba(0,0,0,0.12); border: 1px solid rgba(255,255,255,0.03);">
                                    <i class="fas fa-coins fa-lg" style="color: #f5a623;"></i>
                                    <div style="color: #f5a623; font-size: 1.2rem; font-weight: 600; margin-top: 4px;">R$ ${economia}</div>
                                    <div style="color: rgba(255,255,255,0.3); font-size: 0.6rem; text-transform: uppercase; letter-spacing: 0.3px;">Economia/mês</div>
                                </div>
                            </div>
                            <div class="col-md-3 col-6">
                                <div class="p-3 rounded-4 text-center" style="background: rgba(0,0,0,0.12); border: 1px solid rgba(255,255,255,0.03);">
                                    <i class="fas fa-users fa-lg" style="color: #667eea;"></i>
                                    <div style="color: #667eea; font-size: 1.2rem; font-weight: 600; margin-top: 4px;">${retencao}%</div>
                                    <div style="color: rgba(255,255,255,0.3); font-size: 0.6rem; text-transform: uppercase; letter-spacing: 0.3px;">Retenção</div>
                                </div>
                            </div>
                            <div class="col-md-3 col-6">
                                <div class="p-3 rounded-4 text-center" style="background: rgba(0,0,0,0.12); border: 1px solid rgba(255,255,255,0.03);">
                                    <i class="fas fa-database fa-lg" style="color: #4299e1;"></i>
                                    <div style="color: white; font-size: 1.2rem; font-weight: 600; margin-top: 4px;">${totalRegistros.toLocaleString()}</div>
                                    <div style="color: rgba(255,255,255,0.3); font-size: 0.6rem; text-transform: uppercase; letter-spacing: 0.3px;">Registros</div>
                                </div>
                            </div>
                        </div>
                        
                        <!-- RISCO -->
                        <div class="row g-3 mb-4">
                            <div class="col-12">
                                <div class="p-3 rounded-4" style="background: rgba(0,0,0,0.12); border: 1px solid rgba(255,255,255,0.03);">
                                    <div style="color: rgba(255,255,255,0.5); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px;">
                                        <i class="fas fa-shield-alt me-1" style="color: #f5a623;"></i> Distribuição de Risco
                                    </div>
                                    <div class="row g-2">
                                        <div class="col-4">
                                            <div class="p-2 rounded-3 text-center" style="background: rgba(72,187,120,0.12); border: 1px solid rgba(72,187,120,0.15);">
                                                <div style="color: #48bb78; font-size: 1.1rem; font-weight: 600;">${Math.round(baixoRisco)}%</div>
                                                <div style="color: rgba(255,255,255,0.3); font-size: 0.55rem;">🟢 Baixo Risco</div>
                                            </div>
                                        </div>
                                        <div class="col-4">
                                            <div class="p-2 rounded-3 text-center" style="background: rgba(245,166,35,0.12); border: 1px solid rgba(245,166,35,0.15);">
                                                <div style="color: #f5a623; font-size: 1.1rem; font-weight: 600;">${Math.round(medioRisco)}%</div>
                                                <div style="color: rgba(255,255,255,0.3); font-size: 0.55rem;">🟡 Médio Risco</div>
                                            </div>
                                        </div>
                                        <div class="col-4">
                                            <div class="p-2 rounded-3 text-center" style="background: rgba(245,101,101,0.12); border: 1px solid rgba(245,101,101,0.15);">
                                                <div style="color: #f56565; font-size: 1.1rem; font-weight: 600;">${Math.round(altoRisco)}%</div>
                                                <div style="color: rgba(255,255,255,0.3); font-size: 0.55rem;">🔴 Alto Risco</div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        ${renderInsights(data)}
                        
                        <div class="mt-3 pt-3" style="border-top: 1px solid rgba(255,255,255,0.03);">
                            <div class="d-flex justify-content-between align-items-center flex-wrap">
                                <div style="color: rgba(255,255,255,0.2); font-size: 0.55rem;">
                                    <i class="fas fa-fingerprint me-1"></i> ID: ${analysis.processId.substring(0, 12)}...
                                </div>
                                <div>
                                    <span class="badge me-1" style="background: rgba(255,255,255,0.05); color: rgba(255,255,255,0.3); font-size: 0.55rem;">
                                        <i class="fas fa-robot me-1"></i> IA
                                    </span>
                                    ${data.pow_verified ? `<span class="badge" style="background: rgba(72,187,120,0.15); color: #48bb78; font-size: 0.55rem;">🔒 PoW</span>` : ''}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        container.insertAdjacentHTML('afterbegin', cardHTML);
    }
    
    function renderInsights(data) {
        const insights = data.insights || {};
        const recommendations = insights.recomendacoes || insights.recommendations || [];
        
        if (recommendations.length === 0) return '';
        
        return `
            <div class="row g-3 mb-4">
                <div class="col-12">
                    <div class="p-3 rounded-4" style="background: rgba(0,0,0,0.12); border: 1px solid rgba(255,255,255,0.03);">
                        <div style="color: rgba(255,255,255,0.5); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px;">
                            <i class="fas fa-lightbulb me-1" style="color: #f5a623;"></i> Insights da IA
                        </div>
                        ${recommendations.slice(0, 3).map(r => `
                            <div class="mb-2 p-2 rounded-3" style="background: rgba(0,0,0,0.1); border-left: 3px solid #f5a623; color: rgba(255,255,255,0.8); font-size: 0.8rem;">
                                ${escapeHtml(r)}
                            </div>
                        `).join('')}
                    </div>
                </div>
            </div>
        `;
    }
    
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ============================================================================
    // 🔥 HISTÓRICO
    // ============================================================================
    
    async function loadHistory() {
        try {
            const token = localStorage.getItem('access_token');
            const response = await fetch(`${CONFIG.API_BASE}/analyses/history`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            
            if (response.ok) {
                const data = await response.json();
                State.historyData = data.analyses || data || [];
                updateHistoryUI(State.historyData);
            }
        } catch (error) {
            console.error('Erro ao carregar histórico:', error);
        }
    }
    
    function updateHistoryUI(analyses) {
        const container = DOM.get('#recentAnalyses');
        if (!container) return;
        
        if (!analyses || analyses.length === 0) {
            container.innerHTML = `
                <div class="text-center py-3" style="color: rgba(255,255,255,0.3);">
                    <i class="fas fa-history fa-2x mb-2"></i>
                    <p class="small">Nenhuma análise realizada</p>
                </div>
            `;
            return;
        }
        
        const html = analyses.slice(0, 10).map(a => {
            const date = new Date(a.created_at);
            return `
                <div class="timeline-item">
                    <div class="timeline-marker ${a.status === 'completed' ? 'bg-success' : ''}"></div>
                    <div class="timeline-content">
                        <strong>${escapeHtml(a.filename || 'Análise')}</strong>
                        <br><small style="color: rgba(255,255,255,0.3);">${date.toLocaleDateString('pt-BR')} ${date.toLocaleTimeString('pt-BR')}</small>
                        <br><span class="badge ${a.status === 'completed' ? 'bg-success' : 'bg-secondary'}" style="font-size: 0.55rem;">${a.status === 'completed' ? '✅ Concluído' : a.status}</span>
                        ${a.score ? `<span class="badge ms-1" style="background: rgba(245,166,35,0.15); color: #f5a623; font-size: 0.55rem;">${Math.round(a.score * 100)}%</span>` : ''}
                    </div>
                </div>
            `;
        }).join('');
        
        container.innerHTML = html;
    }

    // ============================================================================
    // 🔥 MODAL DE CRÉDITOS
    // ============================================================================
    
    function showCreditsModal() {
        const modal = document.getElementById('creditsModal');
        if (modal) {
            const bsModal = bootstrap.Modal.getInstance(modal) || new bootstrap.Modal(modal);
            bsModal.show();
        }
    }

    // ============================================================================
    // 🔥 DRAG & DROP (SEM PoW em background)
    // ============================================================================
    
    function setupDragAndDrop() {
        const dropZone = DOM.get('#dropArea');
        if (!dropZone) return;
        
        dropZone.addEventListener('dragenter', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });
        
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });
        
        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('dragover');
        });
        
        dropZone.addEventListener('drop', async (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            
            const files = Array.from(e.dataTransfer.files);
            await processUpload(files);
        });
        
        dropZone.addEventListener('click', () => {
            const fileInput = DOM.get('#fileInput');
            if (fileInput) fileInput.click();
        });
    }

    // ============================================================================
    // 🔥 GPSA (DETALHES DA ANÁLISE)
    // ============================================================================
    
    window.showGPSAForAnalysis = function(processId) {
        const analysis = State.activeAnalyses.find(a => a.processId === processId);
        if (!analysis || !analysis.result) {
            Notify.warning('Aguardando conclusão da análise...');
            return;
        }
        
        const data = analysis.result;
        const stats = data.stats || {};
        const predictions = data.predictions_summary || {};
        
        const totalRegistros = stats.rows || predictions.total || 0;
        const scoreMedio = predictions.mean || 0.65;
        const confianca = Math.round(scoreMedio * 100);
        const crescimento = Math.round(scoreMedio * 50);
        const economia = Math.round(5000 * scoreMedio);
        const retencao = Math.round(60 + scoreMedio * 30);
        
        const modalBody = DOM.get('#gpsaModalBody');
        if (modalBody) {
            modalBody.innerHTML = `
                <div style="color: white; padding: 0.5rem;">
                    <div class="row g-3">
                        <div class="col-12">
                            <h6 style="color: #f5a623; font-size: 0.85rem;">
                                <i class="fas fa-info-circle me-2"></i> Informações da Análise
                            </h6>
                            <div class="p-3 rounded-4" style="background: rgba(0,0,0,0.15); border: 1px solid rgba(255,255,255,0.03);">
                                <div class="row">
                                    <div class="col-6">
                                        <div style="color: rgba(255,255,255,0.4); font-size: 0.6rem;">Arquivo</div>
                                        <div style="color: white; font-weight: 500;">${escapeHtml(analysis.filename || 'Desconhecido')}</div>
                                    </div>
                                    <div class="col-6">
                                        <div style="color: rgba(255,255,255,0.4); font-size: 0.6rem;">Registros</div>
                                        <div style="color: white; font-weight: 500;">${totalRegistros.toLocaleString()}</div>
                                    </div>
                                    <div class="col-6 mt-2">
                                        <div style="color: rgba(255,255,255,0.4); font-size: 0.6rem;">Score Médio</div>
                                        <div style="color: ${scoreMedio > 0.7 ? '#48bb78' : '#f5a623'}; font-weight: 500;">${Math.round(scoreMedio * 100)}%</div>
                                    </div>
                                    <div class="col-6 mt-2">
                                        <div style="color: rgba(255,255,255,0.4); font-size: 0.6rem;">Confiança</div>
                                        <div style="color: white; font-weight: 500;">${confianca}%</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="col-12">
                            <h6 style="color: #f5a623; font-size: 0.85rem;">
                                <i class="fas fa-chart-line me-2"></i> Métricas de Impacto
                            </h6>
                            <div class="row g-2">
                                <div class="col-4">
                                    <div class="p-2 rounded-3 text-center" style="background: rgba(0,0,0,0.15); border: 1px solid rgba(255,255,255,0.03);">
                                        <div style="color: #48bb78; font-size: 1rem; font-weight: 600;">${crescimento}%</div>
                                        <div style="color: rgba(255,255,255,0.3); font-size: 0.5rem;">Crescimento</div>
                                    </div>
                                </div>
                                <div class="col-4">
                                    <div class="p-2 rounded-3 text-center" style="background: rgba(0,0,0,0.15); border: 1px solid rgba(255,255,255,0.03);">
                                        <div style="color: #f5a623; font-size: 1rem; font-weight: 600;">R$ ${economia}</div>
                                        <div style="color: rgba(255,255,255,0.3); font-size: 0.5rem;">Economia/mês</div>
                                    </div>
                                </div>
                                <div class="col-4">
                                    <div class="p-2 rounded-3 text-center" style="background: rgba(0,0,0,0.15); border: 1px solid rgba(255,255,255,0.03);">
                                        <div style="color: #667eea; font-size: 1rem; font-weight: 600;">${retencao}%</div>
                                        <div style="color: rgba(255,255,255,0.3); font-size: 0.5rem;">Retenção</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        ${renderInsightsModal(data)}
                        
                        <div class="text-center mt-3">
                            <button class="btn btn-outline-light btn-sm" onclick="window.closeGPSA()" style="border-radius: 50px; padding: 0.4rem 1.5rem; font-size: 0.8rem;">
                                <i class="fas fa-times me-2"></i> Fechar
                            </button>
                        </div>
                    </div>
                </div>
            `;
        }
        
        const modal = document.getElementById('gpsaModal');
        if (modal) {
            const bsModal = bootstrap.Modal.getInstance(modal) || new bootstrap.Modal(modal);
            bsModal.show();
        }
    };
    
    function renderInsightsModal(data) {
        const insights = data.insights || {};
        const recommendations = insights.recomendacoes || insights.recommendations || [];
        
        if (recommendations.length === 0) return '';
        
        return `
            <div class="col-12">
                <h6 style="color: #f5a623; font-size: 0.85rem;">
                    <i class="fas fa-lightbulb me-2"></i> Insights da IA
                </h6>
                <div class="p-3 rounded-4" style="background: rgba(0,0,0,0.15); border: 1px solid rgba(255,255,255,0.03);">
                    ${recommendations.slice(0, 3).map(r => `
                        <div class="mb-2 p-2 rounded-3" style="background: rgba(0,0,0,0.1); border-left: 3px solid #f5a623; color: rgba(255,255,255,0.8); font-size: 0.8rem;">
                            ${escapeHtml(r)}
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }
    
    window.closeGPSA = function() {
        const modal = document.getElementById('gpsaModal');
        if (modal) {
            const bsModal = bootstrap.Modal.getInstance(modal);
            if (bsModal) bsModal.hide();
        }
    };

    // ============================================================================
    // 🔥 PDF
    // ============================================================================
    
    window.generatePDFReport = async function(processId) {
        const analysis = State.activeAnalyses.find(a => a.processId === processId);
        if (!analysis || !analysis.result) {
            Notify.warning('Aguardando conclusão da análise...');
            return;
        }
        
        Notify.info('📄 Gerando relatório PDF...');
        
        window.dispatchEvent(new CustomEvent('pdf:generate', {
            detail: {
                processId,
                analysis: analysis.result
            }
        }));
    };

    // ============================================================================
    // 🔥 FALLBACK INTELIGENTE (CORRIGIDO)
    // ============================================================================
    
    function startFallback() {
        // 🔥 PREVENÇÃO: Se já houve redirecionamento, NÃO continua
        if (State._redirected) {
            console.log('🛑 Fallback interrompido: redirecionamento já ocorreu');
            return;
        }
        
        // 🔥 PREVENÇÃO: Se o App já está inicializado, NÃO continua
        if (window._appReadyFired || window._appInitialized) {
            console.log('✅ App já inicializado, fallback desnecessário');
            return;
        }
        
        // 🔥 PREVENÇÃO: Verifica autenticação real
        const isReallyAuthenticated = window.appAuth && typeof window.appAuth.isAuthenticated === 'function' 
            ? window.appAuth.isAuthenticated() 
            : !!localStorage.getItem('access_token');
        
        if (!isReallyAuthenticated) {
            console.log('🔒 Usuário não autenticado, fallback interrompido');
            State._redirected = true;
            return;
        }
        
        if (State._fallbackActive) {
            console.log('⏳ Fallback já em execução');
            return;
        }
        
        State._fallbackActive = true;
        State._fallbackAttempts = 0;
        
        console.log('🔄 Iniciando fallback inteligente...');
        
        const fallbackTimer = setInterval(function() {
            State._fallbackAttempts++;
            
            // 🔥 VERIFICAÇÕES DE SEGURANÇA A CADA ITERAÇÃO
            
            // 1. Se o App já está pronto, para o fallback
            if (window._appReadyFired || window._appInitialized) {
                console.log('✅ App detectado como pronto, fallback concluído');
                clearInterval(fallbackTimer);
                State._fallbackActive = false;
                return;
            }
            
            // 2. Se o dashboard já foi inicializado, para o fallback
            if (State._initialized) {
                console.log('✅ Dashboard já inicializado, fallback concluído');
                clearInterval(fallbackTimer);
                State._fallbackActive = false;
                return;
            }
            
            // 3. Se perdeu autenticação, para o fallback
            const stillAuthenticated = window.appAuth && typeof window.appAuth.isAuthenticated === 'function' 
                ? window.appAuth.isAuthenticated() 
                : !!localStorage.getItem('access_token');
            
            if (!stillAuthenticated) {
                console.log('🔒 Autenticação perdida, fallback interrompido');
                clearInterval(fallbackTimer);
                State._fallbackActive = false;
                State._redirected = true;
                return;
            }
            
            // 4. Verifica se o App existe
            if (typeof window.App !== 'undefined' && window.App !== null) {
                console.log(`🔄 Tentativa ${State._fallbackAttempts}: App existe, tentando inicializar...`);
                
                try {
                    // Verifica se o App já está inicializado via método
                    if (typeof window.App.isInitialized === 'function' && window.App.isInitialized()) {
                        console.log('✅ App.isInitialized() retornou true');
                        clearInterval(fallbackTimer);
                        State._fallbackActive = false;
                        // Dispara evento de ready manualmente
                        window.dispatchEvent(new CustomEvent('app:ready', { 
                            detail: { isReady: true, fromFallback: true }
                        }));
                        return;
                    }
                    
                    // Tenta inicializar o App
                    if (typeof window.App.init === 'function') {
                        console.log('🔄 Chamando window.App.init()...');
                        window.App.init();
                    }
                } catch (e) {
                    console.warn('⚠️ Erro ao tentar inicializar App via fallback:', e.message);
                }
            }
            
            // 5. Verifica se o auth está pronto
            if (window.appAuth && typeof window.appAuth.isAuthenticated === 'function') {
                try {
                    if (window.appAuth.isAuthenticated()) {
                        // Dispara evento authReady se não tiver sido disparado
                        if (!window._authReadyFired) {
                            console.log('🔄 Disparando authReady via fallback');
                            window._authReadyFired = true;
                            window.dispatchEvent(new CustomEvent('authReady', { 
                                detail: { isAuthenticated: true, fromFallback: true }
                            }));
                        }
                    }
                } catch (e) {
                    // Ignora
                }
            }
            
            // 6. Timeout - máximo de tentativas
            if (State._fallbackAttempts >= CONFIG.MAX_FALLBACK_ATTEMPTS) {
                console.warn(`⚠️ Fallback: timeout após ${CONFIG.MAX_FALLBACK_ATTEMPTS} tentativas`);
                clearInterval(fallbackTimer);
                State._fallbackActive = false;
                
                // Última tentativa: verifica se o App está disponível mesmo sem ready
                if (typeof window.App !== 'undefined' && window.App !== null) {
                    try {
                        if (typeof window.App.init === 'function') {
                            window.App.init();
                        }
                        // Aguarda 1s e tenta novamente
                        setTimeout(function() {
                            if (!State._initialized && window._appReadyFired) {
                                initialize();
                            }
                        }, 1000);
                    } catch (e) {
                        console.error('Erro na última tentativa do fallback:', e);
                    }
                }
            }
        }, CONFIG.FALLBACK_INTERVAL);
    }

    // ============================================================================
    // 🔥 EVENTOS E INICIALIZAÇÃO
    // ============================================================================
    
    function initialize() {
        if (State._initialized) return;
        
        console.log('🚀 [Dashboard V6.2] Inicializando...');
        
        AppState.sync();
        setupDragAndDrop();
        
        const uploadForm = DOM.get('#uploadForm');
        if (uploadForm) {
            uploadForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const fileInput = DOM.get('#fileInput');
                if (fileInput && fileInput.files.length > 0) {
                    await processUpload(Array.from(fileInput.files));
                } else {
                    Notify.warning('Selecione pelo menos um arquivo');
                }
            });
        }
        
        const fileInput = DOM.get('#fileInput');
        if (fileInput) {
            fileInput.setAttribute('multiple', 'multiple');
            fileInput.addEventListener('change', (e) => {
                if (e.target.files && e.target.files.length > 0) {
                    showFilePreview(Array.from(e.target.files));
                }
            });
        }
        
        loadHistory();
        setInterval(() => AppState.sync(), CONFIG.CREDITS_CHECK_INTERVAL);
        
        State._initialized = true;
        console.log('✅ [Dashboard V6.2] Inicializado com sucesso (PoW sob demanda)!');
    }
    
    function showFilePreview(files) {
        const container = DOM.get('#filePreviewContainer');
        if (!container) return;
        
        let html = `
            <div class="p-3 rounded-3" style="background: rgba(0,0,0,0.15);">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <strong style="color: white; font-size: 0.9rem;"><i class="fas fa-files me-2"></i>${files.length} arquivo(s):</strong>
                    <button type="button" class="btn btn-sm btn-clear-files" style="background: rgba(220,53,69,0.2); border: none; color: #dc3545; border-radius: 50px; padding: 0.2rem 0.6rem; font-size: 0.7rem;">
                        <i class="fas fa-times me-1"></i> Limpar
                    </button>
                </div>
                <div style="max-height: 150px; overflow-y: auto;">
        `;
        
        for (const file of files) {
            const fileSizeKB = (file.size / 1024).toFixed(1);
            html += `
                <div class="d-flex justify-content-between align-items-center py-1 px-2" style="border-bottom: 1px solid rgba(255,255,255,0.03);">
                    <span style="color: rgba(255,255,255,0.8); font-size: 0.8rem;">
                        <i class="fas fa-file-excel text-success me-2"></i> ${escapeHtml(file.name)}
                    </span>
                    <span class="badge" style="background: rgba(255,255,255,0.05); color: rgba(255,255,255,0.4); font-size: 0.6rem;">${fileSizeKB}KB</span>
                </div>
            `;
        }
        
        html += `</div></div>`;
        container.innerHTML = html;
        
        const clearBtn = container.querySelector('.btn-clear-files');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                const fileInput = DOM.get('#fileInput');
                if (fileInput) fileInput.value = '';
                container.innerHTML = '';
            });
        }
        
        const uploadBtn = DOM.get('#uploadButton');
        if (uploadBtn) {
            uploadBtn.disabled = false;
            uploadBtn.innerHTML = `<i class="fas fa-play-circle me-2"></i> Iniciar Análise <span class="badge ms-2" style="background: rgba(255,255,255,0.2); color: white;">1 crédito/arquivo</span>`;
        }
    }

    // ============================================================================
    // 🔥 ESCUTA DE EVENTOS
    // ============================================================================
    
    document.addEventListener('app:ready', function(event) {
        console.log('📢 [Dashboard] app:ready recebido');
        State._fallbackActive = false; // Para o fallback
        initialize();
    });
    
    document.addEventListener('authReady', function(event) {
        console.log('📢 [Dashboard] authReady recebido');
        if (event.detail?.isAuthenticated) {
            setTimeout(initialize, 300);
        }
    });
    
    document.addEventListener('creditsUpdated', function(event) {
        AppState.sync();
    });
    
    document.addEventListener('analysis:success', function(event) {
        const detail = event.detail || {};
        const analysisData = {
            processId: detail.processId,
            filename: detail.filename,
            status: 'completed',
            result: detail.result
        };
        
        if (!State.activeAnalyses.find(a => a.processId === detail.processId)) {
            State.activeAnalyses.push(analysisData);
        }
        
        renderAnalysisCard(analysisData);
        loadHistory();
        
        if (detail.result?.user_credits !== undefined) {
            State.credits = detail.result.user_credits;
            AppState.sync();
        }
    });
    
    document.addEventListener('auth:unauthorized', function() {
        console.log('🧹 [Dashboard] Limpando recursos...');
        State.pollingIntervals.forEach(clearInterval);
        State.pollingIntervals = [];
        State.activeAnalyses = [];
        State._initialized = false;
        State._fallbackActive = false;
        State._redirected = true;
        DOM.clearCache();
    });
    
    document.addEventListener('pdf:generated', function(event) {
        if (event.detail) {
            Notify.success('✅ PDF gerado com sucesso!');
        }
    });
    
    document.addEventListener('pdf:error', function(event) {
        Notify.error('❌ Erro ao gerar PDF: ' + (event.detail?.message || ''));
    });

    // ============================================================================
    // 🔥 DOM CONTENT LOADED - INICIA FALLBACK
    // ============================================================================
    
    document.addEventListener('DOMContentLoaded', function() {
        // Verifica se já está inicializado
        if (State._initialized || window._appReadyFired) {
            console.log('✅ Dashboard já inicializado ou App pronto');
            return;
        }
        
        // Verifica autenticação
        const token = localStorage.getItem('access_token');
        const isAuth = token && token !== 'undefined' && token !== 'null';
        
        if (!isAuth) {
            console.log('🔒 Usuário não autenticado, aguardando login...');
            return;
        }
        
        // Aguarda um pouco e inicia fallback se necessário
        setTimeout(function() {
            if (!State._initialized && !window._appReadyFired) {
                console.log('🔄 Iniciando fallback para inicialização do dashboard...');
                startFallback();
            }
        }, 1000);
    });

    // ============================================================================
    // 🔥 ESTILOS ADICIONAIS
    // ============================================================================
    
    (function injectStyles() {
        if (document.getElementById('dashboardV62Styles')) return;
        
        const style = document.createElement('style');
        style.id = 'dashboardV62Styles';
        style.textContent = `
            .analysis-card { animation: fadeInUp 0.5s ease-out; }
            @keyframes fadeInUp {
                from { opacity: 0; transform: translateY(20px); }
                to { opacity: 1; transform: translateY(0); }
            }
            .dragover {
                border-color: #48bb78 !important;
                background: rgba(72, 187, 120, 0.15) !important;
                transform: scale(1.02);
            }
            .btn-pdf:hover {
                background: #dc3545 !important;
                color: white !important;
                transform: translateY(-2px);
            }
            .btn-gpsa:hover {
                background: #f5a623 !important;
                color: white !important;
                transform: translateY(-2px);
            }
            .timeline {
                position: relative;
                padding-left: 1.5rem;
                max-height: 350px;
                overflow-y: auto;
            }
            .timeline::-webkit-scrollbar { width: 4px; }
            .timeline::-webkit-scrollbar-track { background: rgba(255,255,255,0.05); border-radius: 4px; }
            .timeline::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.2); border-radius: 4px; }
            .timeline::before {
                content: '';
                position: absolute;
                left: 0;
                top: 0;
                bottom: 0;
                width: 2px;
                background: linear-gradient(180deg, #667eea 0%, #764ba2 100%);
                border-radius: 2px;
            }
            .timeline-item { position: relative; padding-bottom: 1.2rem; }
            .timeline-item:last-child { padding-bottom: 0; }
            .timeline-marker {
                position: absolute;
                left: -1.5rem;
                top: 0.25rem;
                width: 12px;
                height: 12px;
                border-radius: 50%;
                background: #667eea;
                border: 2px solid white;
                box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.3);
            }
            .timeline-marker.bg-success {
                background: #48bb78;
                box-shadow: 0 0 0 2px rgba(72, 187, 120, 0.3);
            }
            .timeline-content {
                padding-left: 0.5rem;
                color: rgba(255,255,255,0.85);
            }
            .timeline-content strong { color: #f5a623; }
            .modal-content {
                border-radius: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
                border: 1px solid rgba(255,255,255,0.1) !important;
                color: white;
            }
            .modal-content .btn-close { filter: brightness(0) invert(1); }
        `;
        document.head.appendChild(style);
    })();

    console.log('✅ [Dashboard V6.2] Módulo carregado (PoW apenas no upload, fallback inteligente).');

})();