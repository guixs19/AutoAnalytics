// frontend/js/upload-report-system.js - v2.5 (CORRIGIDO: ENDPOINT E TIMEOUT)
// SISTEMA COMPLETO DE UPLOAD, POLLING E RELATÓRIO

(function() {
    'use strict';

    console.log('📊 Inicializando UploadReportSystem v2.5...');

    // ==============================================
    // 🔥 CONFIGURAÇÕES (CORRIGIDAS)
    // ==============================================

    const CONFIG = {
        MAX_FILES: 3,
        MAX_FILE_SIZE_KB: 200,
        CREDITS_PER_FILE: 1,
        POLLING_INTERVAL: 2000,                      // 2 segundos entre polling
        MAX_POLLING_ATTEMPTS: 300,                   // 🔥 300 * 2s = 10 minutos
        API_BASE: '/api',
        UPLOAD_ENDPOINT: '/upload-multi-analyze',
        UPLOAD_ENDPOINT_FALLBACK: '/upload-auto',
        UPLOAD_RETRY_ATTEMPTS: 3,
        UPLOAD_RETRY_DELAY: 2000,
        GLOBAL_TIMEOUT: 600000,                      // 🔥 10 minutos (600s)
        RESULT_ENDPOINTS: [
            '/analysis/result/',
            '/result/',
            '/analysis/',
            '/analyses/',
        ],
        POW_MAX_AGE: 600000,
        POW_RETRY_ATTEMPTS: 2,
        MAX_RETRY_BACKOFF: 10000,
        HEALTH_CHECK_INTERVAL: 30000,
        // 🔥 NOVO: Tempo máximo de processamento do backend (8.3min)
        BACKEND_PROCESSING_TIMEOUT: 500,             // segundos
    };

    // ==============================================
    // 🔥 STATE
    // ==============================================

    const state = {
        files: [],
        isUploading: false,
        currentProcessId: null,
        analysisResult: null,
        isPolling: false,
        pollAttempts: 0,
        lastResult: null,
        uploadRetryCount: 0,
        startTime: null,
        powLastRefresh: 0,
        powRecoveryAttempts: 0,
        lastError: null,
        errorCount: 0,
        isRecovering: false,
    };

    // ==============================================
    // 🔥 DOM ELEMENTS
    // ==============================================

    const elements = {};

    function cacheElements() {
        elements.dropArea = document.getElementById('dropArea');
        elements.fileInput = document.getElementById('fileInput');
        elements.filePreview = document.getElementById('filePreviewContainer');
        elements.uploadForm = document.getElementById('uploadForm');
        
        elements.analysisStatus = document.getElementById('analysisStatus');
        elements.statusIcon = document.getElementById('statusIcon');
        elements.statusText = document.getElementById('statusText');
        elements.statusSub = document.getElementById('statusSub');
        elements.statusProgress = document.getElementById('statusProgressBar');
        
        elements.resultContainer = document.getElementById('resultContainer');
        elements.resultPlaceholder = document.getElementById('resultPlaceholder');
        elements.resultMetrics = document.getElementById('resultMetrics');
        elements.resultInsights = document.getElementById('resultInsights');
        elements.downloadPdfBtn = document.getElementById('downloadPdfBtn');
        elements.newAnalysisBtn = document.getElementById('newAnalysisBtn');
        elements.resultFilename = document.getElementById('resultFilename');
        elements.resultSummary = document.getElementById('resultSummary');
        
        elements.creditsDisplay = document.getElementById('creditsDisplay');
        elements.creditsCount = document.getElementById('creditsCount');
        elements.uploadCredits = document.getElementById('uploadCredits');
        elements.modalCredits = document.getElementById('modalCreditsCount');
    }

    // ==============================================
    // 🔥 UTILITÁRIOS MELHORADOS
    // ==============================================

    function getApp() {
        return window.App || window.app || window.autoAnalytics;
    }

    function getToken() {
        try {
            const token = localStorage.getItem('access_token');
            if (!token || token === 'undefined' || token === 'null' || token.length < 10) {
                return null;
            }
            return token;
        } catch (e) {
            return null;
        }
    }

    function buildApiUrl(path) {
        if (!path) return '/api';
        const cleanPath = path.startsWith('/') ? path : '/' + path;
        if (cleanPath.startsWith('/api/')) return cleanPath;
        return '/api' + cleanPath;
    }

    function formatFileSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1048576) return (bytes / 1024).toFixed(0) + ' KB';
        return (bytes / 1048576).toFixed(1) + ' MB';
    }

    function getScoreColor(score) {
        if (score >= 0.7) return '#48bb78';
        if (score >= 0.4) return '#f5a623';
        return '#dc3545';
    }

    function getScoreLabel(score) {
        if (score >= 0.7) return 'Alto potencial';
        if (score >= 0.4) return 'Potencial médio';
        return 'Baixo potencial';
    }

    function getScoreIcon(score) {
        if (score >= 0.7) return '🚀';
        if (score >= 0.4) return '📈';
        return '🔄';
    }

    function sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    function getBackoffDelay(attempt, baseDelay = CONFIG.UPLOAD_RETRY_DELAY) {
        const delay = baseDelay * Math.pow(1.5, attempt - 1);
        return Math.min(delay, CONFIG.MAX_RETRY_BACKOFF);
    }

    function showNotification(message, type = 'info') {
        const app = getApp();
        if (app && typeof app.showNotification === 'function') {
            app.showNotification(message, type);
        } else if (window.toastr) {
            const method = window.toastr[type] || window.toastr.info;
            method(message);
        } else {
            console.log(`[${type}] ${message}`);
        }
    }

    function updateCreditsDisplay() {
        const app = getApp();
        let credits = 0;
        
        if (app && typeof app.getCredits === 'function') {
            credits = app.getCredits();
        } else if (window.__APP_STATE && window.__APP_STATE.credits !== undefined) {
            credits = window.__APP_STATE.credits;
        }

        const isAdmin = app && typeof app.isAdmin === 'function' ? app.isAdmin() : false;
        const display = isAdmin ? '∞' : credits.toString();
        
        if (elements.creditsDisplay) elements.creditsDisplay.textContent = display;
        if (elements.creditsCount) elements.creditsCount.textContent = credits;
        if (elements.uploadCredits) elements.uploadCredits.textContent = credits;
        if (elements.modalCredits) elements.modalCredits.textContent = credits;
    }

    function getUserName() {
        const app = getApp();
        if (app && typeof app.getCurrentUser === 'function') {
            const user = app.getCurrentUser();
            if (user && user.name) return user.name;
        }
        if (window.__APP_STATE && window.__APP_STATE.user) {
            return window.__APP_STATE.user.name || 'Usuário';
        }
        try {
            const userData = localStorage.getItem('user_data');
            if (userData) {
                const parsed = JSON.parse(userData);
                return parsed.name || 'Usuário';
            }
        } catch (e) {}
        return 'Usuário';
    }

    function isPowError(error) {
        if (!error) return false;
        const errorStr = typeof error === 'string' ? error : JSON.stringify(error);
        const patterns = ['pow', 'proof', 'nonce', 'challenge', '428', 'precondition'];
        return patterns.some(p => errorStr.toLowerCase().includes(p));
    }

    function isCreditsError(error) {
        if (!error) return false;
        const errorStr = typeof error === 'string' ? error : JSON.stringify(error);
        const patterns = ['crédito', 'credits', '402', 'payment', 'insufficient'];
        return patterns.some(p => errorStr.toLowerCase().includes(p));
    }

    // ==============================================
    // 🔥 FILE MANAGEMENT
    // ==============================================

    function validateFile(file) {
        const errors = [];
        const ext = file.name.split('.').pop().toLowerCase();
        
        if (!['csv', 'xlsx', 'xls'].includes(ext)) {
            errors.push('Formato não suportado. Use CSV, XLSX ou XLS.');
        }
        if (file.size > CONFIG.MAX_FILE_SIZE_KB * 1024) {
            errors.push(`Arquivo excede ${CONFIG.MAX_FILE_SIZE_KB} KB.`);
        }
        
        return { valid: errors.length === 0, errors };
    }

    function addFiles(files) {
        let added = 0;
        const errors = [];

        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            
            if (state.files.length >= CONFIG.MAX_FILES) {
                errors.push(`Limite de ${CONFIG.MAX_FILES} arquivos atingido.`);
                break;
            }

            const validation = validateFile(file);
            if (!validation.valid) {
                errors.push(file.name + ': ' + validation.errors.join(' '));
                continue;
            }

            state.files.push(file);
            added++;
        }

        updateFilePreview();

        if (added > 0) {
            const userName = getUserName();
            showNotification(`${userName}, ${added} arquivo(s) adicionado(s)!`, 'info');
            startAnalysis();
        }

        if (errors.length > 0) {
            showNotification(errors.join(' | '), 'warning');
        }
    }

    function removeFile(index) {
        if (index >= 0 && index < state.files.length) {
            state.files.splice(index, 1);
            updateFilePreview();
            
            if (state.files.length === 0) {
                resetAnalysisStatus();
                hideResult();
            }
        }
    }

    function updateFilePreview() {
        const container = elements.filePreview;
        if (!container) return;

        if (state.files.length === 0) {
            container.innerHTML = '';
            return;
        }

        let html = '';
        state.files.forEach((file, index) => {
            const ext = file.name.split('.').pop().toLowerCase();
            const icon = ext === 'csv' ? 'fa-file-csv' : 'fa-file-excel';
            
            html += `
                <div class="file-preview-item" data-index="${index}">
                    <div class="file-info">
                        <i class="fas ${icon}"></i>
                        <span class="file-name" title="${file.name}">${file.name}</span>
                        <span class="file-size">${formatFileSize(file.size)}</span>
                    </div>
                    <button type="button" class="file-remove" data-index="${index}" title="Remover arquivo">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            `;
        });
        
        container.innerHTML = html;

        container.querySelectorAll('.file-remove').forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                removeFile(parseInt(this.dataset.index));
            });
        });
    }

    // ==============================================
    // 🔥 ANALYSIS STATUS
    // ==============================================

    function showAnalysisStatus(message, submessage, progress) {
        const status = elements.analysisStatus;
        if (!status) return;

        status.classList.add('show');
        if (elements.statusText) elements.statusText.textContent = message || 'Processando...';
        if (elements.statusSub) elements.statusSub.textContent = submessage || 'Aguarde...';
        if (elements.statusProgress && progress !== undefined) {
            elements.statusProgress.style.width = Math.min(100, progress) + '%';
        }
        if (elements.dropArea) elements.dropArea.classList.add('uploading');
    }

    function updateAnalysisProgress(progress, message) {
        if (elements.statusProgress) {
            elements.statusProgress.style.width = Math.min(100, progress) + '%';
        }
        if (message && elements.statusText) {
            elements.statusText.textContent = message;
        }
    }

    function resetAnalysisStatus() {
        const status = elements.analysisStatus;
        if (status) status.classList.remove('show');
        if (elements.statusProgress) elements.statusProgress.style.width = '0%';
        if (elements.dropArea) elements.dropArea.classList.remove('uploading', 'success', 'error');
    }

    // ==============================================
    // 🔥 RESULT DISPLAY
    // ==============================================

    function showResult(data) {
        if (elements.resultPlaceholder) elements.resultPlaceholder.style.display = 'none';
        if (elements.resultContainer) elements.resultContainer.classList.add('show');
        
        const analysisInfo = data.analysis_info || data.metadata || {};
        const predictions = data.predictions || data.predictions_summary || data.metrics || {};
        const insights = data.insights || {};
        const recommendations = data.recommendations || insights.recomendacoes || [];
        const stats = data.stats || {};
        
        const totalRegistros = analysisInfo.rows_processed || predictions.processed_rows || stats.rows || 0;
        const scoreMedio = predictions.mean || predictions.mean_prediction || 0.65;
        const scoreColor = getScoreColor(scoreMedio);
        const scoreLabel = getScoreLabel(scoreMedio);
        const scoreIcon = getScoreIcon(scoreMedio);
        const confianca = Math.round(scoreMedio * 100);
        const filename = data.filename || analysisInfo.filename || 'Análise';
        
        if (elements.resultMetrics) {
            elements.resultMetrics.innerHTML = `
                <div class="result-stat">
                    <div class="stat-value">${totalRegistros.toLocaleString()}</div>
                    <div class="stat-label">Registros analisados</div>
                </div>
                <div class="result-stat">
                    <div class="stat-value" style="color: ${scoreColor};">${confianca}%</div>
                    <div class="stat-label">Score de confiança</div>
                </div>
                <div class="result-stat">
                    <div class="stat-value">${scoreIcon} ${scoreLabel}</div>
                    <div class="stat-label">Classificação</div>
                </div>
                <div class="result-stat">
                    <div class="stat-value">${data.credit_consumed ? 1 : 0}</div>
                    <div class="stat-label">Créditos consumidos</div>
                </div>
            `;
        }
        
        if (elements.resultInsights) {
            let insightsHtml = `
                <div style="margin-bottom:0.8rem;font-size:0.8rem;color:rgba(255,255,255,0.4);font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">
                    <i class="fas fa-lightbulb" style="color:#ff6b35;margin-right:0.5rem;"></i>
                    Insights da IA
                </div>
            `;

            if (recommendations && recommendations.length > 0) {
                recommendations.slice(0, 5).forEach(r => {
                    insightsHtml += `
                        <div class="result-insight">
                            <span class="insight-icon"><i class="fas fa-chevron-right"></i></span>
                            ${r}
                        </div>
                    `;
                });
            } else {
                const defaultInsights = scoreMedio >= 0.7 ? [
                    '✅ Seus dados mostram um alto potencial de performance. Continue com as boas práticas!',
                    '📈 Recomendamos manter o foco em treinamento e manutenção preventiva.',
                    '🎯 Considere expandir suas operações para capturar mais oportunidades.'
                ] : scoreMedio >= 0.4 ? [
                    '📊 Seus dados indicam espaço para melhorias significativas.',
                    '🔍 Recomendamos revisar processos e identificar gargalos operacionais.',
                    '📋 Considere investir em treinamento para sua equipe.'
                ] : [
                    '⚠️ Seus dados mostram oportunidades claras de melhoria.',
                    '🛠️ Recomendamos uma revisão completa dos processos da oficina.',
                    '📊 Considere implementar um sistema de monitoramento de performance.'
                ];
                
                defaultInsights.forEach(r => {
                    insightsHtml += `
                        <div class="result-insight">
                            <span class="insight-icon"><i class="fas fa-chevron-right"></i></span>
                            ${r}
                        </div>
                    `;
                });
            }
            
            elements.resultInsights.innerHTML = insightsHtml;
        }
        
        if (elements.resultSummary) {
            const modelUsed = data.model_used || analysisInfo.model_used || 'AutoML';
            const encodingUsed = data.encoding_used || analysisInfo.encoding_used || 'auto';
            
            elements.resultSummary.innerHTML = `
                <div style="display:flex; flex-wrap:wrap; gap:0.3rem 1rem; font-size:0.75rem; color:rgba(255,255,255,0.5);">
                    <span><strong style="color:#ff6b35;">📊 ${totalRegistros}</strong> registros</span>
                    <span><strong style="color:${scoreColor};">🎯 ${confianca}%</strong> confiança</span>
                    <span><strong style="color:#f5a623;">📈 ${scoreLabel}</strong></span>
                    <span><i class="fas fa-robot"></i> ${modelUsed}</span>
                    <span><i class="fas fa-code"></i> ${encodingUsed}</span>
                </div>
            `;
        }
        
        if (elements.resultFilename) {
            elements.resultFilename.textContent = filename;
        }
        
        state.analysisResult = data;
        window._lastResult = data;
        
        const userName = getUserName();
        showNotification(`✅ ${userName}, análise concluída com sucesso!`, 'success');
        
        const resultCard = document.getElementById('resultCard');
        if (resultCard) {
            setTimeout(() => {
                resultCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }, 400);
        }
        
        updateCreditsDisplay();
    }

    function hideResult() {
        if (elements.resultContainer) elements.resultContainer.classList.remove('show');
        if (elements.resultPlaceholder) elements.resultPlaceholder.style.display = 'block';
        if (elements.resultMetrics) elements.resultMetrics.innerHTML = '';
        if (elements.resultInsights) elements.resultInsights.innerHTML = '';
        if (elements.resultSummary) elements.resultSummary.innerHTML = '';
        state.analysisResult = null;
        window._lastResult = null;
    }

    // ==============================================
    // 🔥 POW - OBTENÇÃO DE SOLUÇÃO
    // ==============================================

    async function getPowSolution(forceRefresh = false) {
        const app = getApp();
        
        const now = Date.now();
        if (forceRefresh || (now - state.powLastRefresh) > CONFIG.POW_MAX_AGE) {
            console.log('🔄 Renovando PoW (idade:', Math.round((now - state.powLastRefresh)/1000), 's)');
            state.powLastRefresh = now;
        }
        
        console.log('🔐 [PoW] Tentando obter solução...');
        console.log('   📦 app disponível?', !!app);
        console.log('   📦 powClient disponível?', !!window.powClient);
        
        if (window.powClient && typeof window.powClient.isPowHealthy === 'function') {
            try {
                const healthy = await window.powClient.isPowHealthy();
                if (healthy) {
                    console.log('   ✅ PoW saudável');
                } else {
                    console.log('   ⚠️ PoW não saudável, tentando recuperar...');
                    if (typeof window.powClient.autoRecover === 'function') {
                        await window.powClient.autoRecover();
                        state.powRecoveryAttempts++;
                    }
                }
            } catch (e) {
                console.warn('   ⚠️ Erro ao verificar saúde do PoW:', e.message);
            }
        }
        
        if (app && app.Pow) {
            try {
                if (typeof app.Pow.prepareForUpload === 'function') {
                    const ready = await app.Pow.prepareForUpload();
                    console.log('   🔐 app.Pow.prepareForUpload result:', ready);
                    if (!ready) {
                        console.log('⏳ PoW não está pronto via app.Pow');
                    }
                }
                
                if (window.powClient && typeof window.powClient.getSolutionForUpload === 'function') {
                    const solution = await window.powClient.getSolutionForUpload();
                    if (solution && solution.prefix && solution.nonce) {
                        console.log('✅ PoW solução obtida via powClient');
                        console.log(`   🔑 Prefix: ${solution.prefix.substring(0, 10)}...`);
                        console.log(`   🔑 Nonce: ${solution.nonce}`);
                        return solution;
                    }
                }
                
                if (typeof app.Pow.getSolution === 'function') {
                    const solution = await app.Pow.getSolution();
                    if (solution && solution.prefix && solution.nonce) {
                        console.log('✅ PoW solução obtida via app.Pow');
                        return solution;
                    }
                }
            } catch (e) {
                console.warn('⚠️ Erro ao obter PoW via app.Pow:', e.message);
            }
        }
        
        if (window.powClient) {
            try {
                console.log('   🔐 Tentando via powClient direto...');
                if (typeof window.powClient.prepareForUpload === 'function') {
                    await window.powClient.prepareForUpload();
                }
                if (typeof window.powClient.getSolutionForUpload === 'function') {
                    const solution = await window.powClient.getSolutionForUpload();
                    if (solution && solution.prefix && solution.nonce) {
                        console.log('✅ PoW solução obtida via powClient');
                        console.log(`   🔑 Prefix: ${solution.prefix.substring(0, 10)}...`);
                        console.log(`   🔑 Nonce: ${solution.nonce}`);
                        return solution;
                    }
                }
            } catch (e) {
                console.warn('⚠️ Erro no powClient:', e.message);
            }
        }
        
        console.log('⏳ PoW não disponível, continuando sem');
        return null;
    }

    // ==============================================
    // 🔥 UPLOAD E ANÁLISE
    // ==============================================

    async function startAnalysis() {
        if (state.isUploading) {
            showNotification('Já existe uma análise em andamento.', 'warning');
            return;
        }

        if (state.files.length === 0) {
            showNotification('Selecione pelo menos um arquivo.', 'warning');
            return;
        }

        state.errorCount = 0;
        state.lastError = null;
        state.isRecovering = false;

        const app = getApp();
        const creditsNeeded = state.files.length * CONFIG.CREDITS_PER_FILE;
        const creditsAvailable = app && typeof app.getCredits === 'function' ? app.getCredits() : 0;

        if (creditsAvailable < creditsNeeded) {
            showNotification(
                `Créditos insuficientes. Você tem ${creditsAvailable}, precisa de ${creditsNeeded}.`,
                'error'
            );
            return;
        }

        state.isUploading = true;
        state.startTime = Date.now();
        state.uploadRetryCount = 0;
        
        const filesToUpload = state.files.slice();
        const userName = getUserName();
        
        showAnalysisStatus(
            '📤 Enviando arquivos...',
            `${userName}, preparando ${filesToUpload.length} arquivo(s) para análise`,
            10
        );

        try {
            const formData = new FormData();
            for (const file of filesToUpload) {
                formData.append('files', file);
            }
            formData.append('analysis_type', 'auto');
            formData.append('report_format', 'html');

            let solution = null;
            try {
                solution = await getPowSolution(true);
            } catch (e) {
                console.warn('⚠️ Erro ao obter PoW:', e.message);
            }
            
            const result = await uploadWithRetry(formData, solution, filesToUpload);
            
            if (!result) {
                throw new Error('Falha no upload após múltiplas tentativas');
            }

            const data = result;
            
            updateAnalysisProgress(50, '✅ Upload concluído, processando resultados...');

            let processId = null;
            
            if (data.data && data.data.accepted_files && data.data.accepted_files.length > 0) {
                processId = data.data.accepted_files[0].process_id;
            } else if (data.process_id) {
                processId = data.process_id;
            } else if (data.processId) {
                processId = data.processId;
            } else if (data.id) {
                processId = data.id;
            }

            if (!processId && data.data && data.data.accepted_files && data.data.accepted_files.length > 0) {
                processId = data.data.accepted_files[0].process_id || data.data.accepted_files[0].id;
            }

            if (processId) {
                state.currentProcessId = processId;
                await pollAnalysisStatus(processId);
            } else {
                if (data.data && data.data.accepted_files) {
                    showResult(data);
                } else {
                    showResult(data);
                }
            }

            state.files = [];
            updateFilePreview();
            updateCreditsDisplay();
            
            resetAnalysisStatus();
            if (elements.dropArea) elements.dropArea.classList.add('success');

            window.dispatchEvent(new CustomEvent('analysis:completed', {
                detail: { result: data, files: filesToUpload }
            }));

        } catch (error) {
            console.error('❌ Erro na análise:', error);
            
            const errorMsg = error.message || 'Erro ao processar análise.';
            state.lastError = errorMsg;
            state.errorCount++;
            
            const userName = getUserName();
            showNotification(`${userName}, ${errorMsg}`, 'error');
            
            if (isPowError(errorMsg)) {
                setTimeout(() => {
                    if (confirm('⚠️ Erro de segurança (PoW) detectado. Deseja tentar recuperar automaticamente?')) {
                        refreshPowAndRetry();
                    }
                }, 500);
            }
            
            if (elements.dropArea) elements.dropArea.classList.add('error');
            resetAnalysisStatus();
        } finally {
            state.isUploading = false;
            if (app && typeof app.hideLoading === 'function') {
                app.hideLoading();
            }
        }
    }

    async function refreshPowAndRetry() {
        if (state.isRecovering) return;
        state.isRecovering = true;
        
        try {
            showNotification('🔄 Tentando recuperar conexão...', 'info');
            showAnalysisStatus('🔄', 'Recuperando segurança...', 20);
            
            if (window.powClient) {
                window.powClient.clearCache();
                window.powClient.reset();
            }
            state.powLastRefresh = 0;
            
            await sleep(1000);
            await startAnalysis();
            
        } catch (e) {
            console.error('❌ Erro na recuperação:', e);
            showNotification('❌ Falha na recuperação. Recarregue a página.', 'error');
        } finally {
            state.isRecovering = false;
        }
    }

    // ==============================================
    // 🔥 UPLOAD COM RETRY
    // ==============================================

    async function uploadWithRetry(formData, solution, files) {
        let lastError = null;
        const maxRetries = CONFIG.UPLOAD_RETRY_ATTEMPTS;
        
        const endpoints = [
            CONFIG.UPLOAD_ENDPOINT,
            CONFIG.UPLOAD_ENDPOINT_FALLBACK
        ];
        
        for (let endpoint of endpoints) {
            let endpointFailed = false;
            
            for (let attempt = 1; attempt <= maxRetries; attempt++) {
                try {
                    const token = getToken();
                    if (!token) {
                        throw new Error('Token não encontrado. Faça login novamente.');
                    }
                    
                    const headers = {
                        'Authorization': `Bearer ${token}`,
                        'Accept': 'application/json',
                    };

                    if (solution && solution.prefix && solution.nonce) {
                        headers['X-PoW-Challenge'] = solution.prefix;
                        headers['X-PoW-Nonce'] = solution.nonce;
                        console.log(`📤 Upload com PoW (tentativa ${attempt}/${maxRetries})`);
                        console.log(`   🔑 Challenge: ${solution.prefix.substring(0, 10)}...`);
                        console.log(`   🔑 Nonce: ${solution.nonce}`);
                        console.log(`   🌐 Endpoint: ${endpoint}`);
                    } else {
                        console.log(`📤 Upload SEM PoW (tentativa ${attempt}/${maxRetries})`);
                    }

                    const url = buildApiUrl(endpoint);
                    
                    updateAnalysisProgress(
                        10 + (attempt - 1) * 15,
                        `📤 Tentativa ${attempt}/${maxRetries}...`
                    );

                    const response = await fetch(url, {
                        method: 'POST',
                        headers: headers,
                        body: formData,
                        credentials: 'include',
                    });

                    console.log(`📡 Resposta: ${response.status} ${response.statusText}`);

                    let responseData = null;
                    let responseText = null;
                    
                    try {
                        responseText = await response.text();
                        if (responseText) {
                            try {
                                responseData = JSON.parse(responseText);
                                console.log(`📄 Resposta JSON:`, responseData);
                            } catch (e) {
                                console.log(`📄 Resposta texto: ${responseText.substring(0, 200)}...`);
                            }
                        }
                    } catch (e) {
                        console.warn('⚠️ Não foi possível ler a resposta');
                    }

                    if (response.status === 400) {
                        let errorMessage = 'Erro na requisição. Verifique os dados enviados.';
                        
                        if (responseData) {
                            if (responseData.detail) {
                                errorMessage = typeof responseData.detail === 'string' 
                                    ? responseData.detail 
                                    : JSON.stringify(responseData.detail);
                            } else if (responseData.message) {
                                errorMessage = responseData.message;
                            } else if (responseData.error) {
                                errorMessage = responseData.error;
                            }
                        }
                        
                        const errorStr = typeof errorMessage === 'string' ? errorMessage : JSON.stringify(errorMessage);
                        console.error(`❌ Erro 400: ${errorStr}`);
                        
                        if (isPowError(errorStr)) {
                            console.log('🔄 Erro de PoW detectado, renovando...');
                            if (window.powClient) {
                                window.powClient.clearCache();
                                window.powClient.reset();
                            }
                            try {
                                const newSolution = await getPowSolution(true);
                                if (newSolution) {
                                    solution = newSolution;
                                    console.log('✅ PoW renovado, tentando novamente...');
                                    continue;
                                }
                            } catch (e) {
                                console.warn('⚠️ Falha ao renovar PoW:', e.message);
                            }
                        }
                        
                        if (isCreditsError(errorStr)) {
                            throw new Error(`Créditos insuficientes: ${errorStr}`);
                        }
                        
                        if (errorStr.includes('not found') || errorStr.includes('404')) {
                            console.log(`🔄 Endpoint ${endpoint} não encontrado, tentando próximo...`);
                            endpointFailed = true;
                            break;
                        }
                        
                        throw new Error(errorStr);
                    }

                    if (response.status === 428) {
                        console.warn('⚠️ PoW expirado (428), obtendo novo...');
                        if (window.powClient) {
                            window.powClient.clearCache();
                            window.powClient.reset();
                        }
                        try {
                            const newSolution = await getPowSolution(true);
                            if (newSolution) {
                                solution = newSolution;
                                continue;
                            }
                        } catch (e) {
                            console.warn('⚠️ Falha ao obter novo PoW:', e.message);
                        }
                        throw new Error('PoW expirado. Tente novamente.');
                    }

                    if (response.status === 401) {
                        console.warn('⚠️ Token expirado (401), tentando refresh...');
                        const app = getApp();
                        if (app && typeof app.refreshTokenSafely === 'function') {
                            const refreshed = await app.refreshTokenSafely();
                            if (refreshed) {
                                continue;
                            }
                        }
                        throw new Error('Sessão expirada. Faça login novamente.');
                    }

                    if (response.status === 429) {
                        const data = responseData || {};
                        const retryAfter = data.retry_after || 5;
                        console.warn(`⚠️ Rate limit, aguardando ${retryAfter}s...`);
                        await sleep(retryAfter * 1000);
                        continue;
                    }

                    if (response.status === 402) {
                        const data = responseData || {};
                        throw new Error(data.message || data.detail || 'Créditos insuficientes.');
                    }

                    if (response.ok) {
                        const data = responseData || await response.json();
                        console.log('✅ Upload bem-sucedido');
                        return data;
                    }

                    let errorMsg = `Erro ${response.status}`;
                    if (responseData) {
                        errorMsg = responseData.detail || responseData.message || responseData.error || errorMsg;
                    }
                    throw new Error(errorMsg);

                } catch (error) {
                    lastError = error;
                    console.error(`❌ Tentativa ${attempt} falhou:`, error.message);
                    
                    if (isCreditsError(error.message) ||
                        error.message.includes('inválido') ||
                        error.message.includes('Sessão expirada')) {
                        throw error;
                    }
                    
                    if (endpointFailed) {
                        break;
                    }
                    
                    if (attempt < maxRetries) {
                        const delay = getBackoffDelay(attempt);
                        console.log(`⏳ Aguardando ${delay}ms antes de tentar novamente...`);
                        await sleep(delay);
                    }
                }
            }
            
            if (endpointFailed) {
                console.log(`🔄 Pulando para próximo endpoint...`);
                continue;
            }
        }

        throw lastError || new Error('Upload falhou após múltiplas tentativas');
    }

    // ==============================================
    // 🔥🔥🔥 POLLING (CORRIGIDO: ENDPOINT + TIMEOUT)
    // ==============================================

    async function pollAnalysisStatus(processId) {
        let attempts = 0;
        const maxAttempts = CONFIG.MAX_POLLING_ATTEMPTS;  // 🔥 300 tentativas
        const interval = CONFIG.POLLING_INTERVAL;          // 2 segundos
        const startTime = Date.now();
        let consecutiveErrors = 0;
        
        state.isPolling = true;
        state.pollAttempts = 0;

        // 🔥 Calcular timeout total em segundos para exibição
        const totalTimeoutSeconds = Math.round(CONFIG.GLOBAL_TIMEOUT / 1000);

        while (attempts < maxAttempts) {
            attempts++;
            state.pollAttempts = attempts;
            
            // 🔥 Verificar timeout global (10 minutos)
            if (Date.now() - startTime > CONFIG.GLOBAL_TIMEOUT) {
                throw new Error(`Timeout: a análise excedeu o tempo limite de ${totalTimeoutSeconds} segundos.`);
            }
            
            try {
                const token = getToken();
                if (!token) {
                    throw new Error('Token não encontrado.');
                }
                
                let statusData = null;
                // 🔥🔥🔥 CORREÇÃO: Endpoint correto do backend
                const statusEndpoint = `/analysis/progress/${processId}`;
                const url = buildApiUrl(statusEndpoint);
                
                console.log(`📊 [Polling ${attempts}/${maxAttempts}] ${url}`);
                
                const response = await fetch(url, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });

                if (!response.ok) {
                    if (response.status === 404) {
                        // 🔥 Análise ainda não encontrada (pode estar inicializando)
                        consecutiveErrors = 0;
                        
                        const progress = 50 + (attempts / maxAttempts) * 40;
                        const elapsed = Math.round((Date.now() - startTime) / 1000);
                        updateAnalysisProgress(
                            progress,
                            `⏳ Aguardando início da análise... (${elapsed}s / ${totalTimeoutSeconds}s)`
                        );
                        await sleep(interval);
                        continue;
                    }
                    if (response.status === 401) {
                        throw new Error('Sessão expirada. Faça login novamente.');
                    }
                    
                    consecutiveErrors++;
                    if (consecutiveErrors > 3) {
                        throw new Error(`Erro repetido ao verificar status: ${response.status}`);
                    }
                    
                    await sleep(interval * 1.5);
                    continue;
                }

                // 🔥 Resetar contador de erros em caso de sucesso
                consecutiveErrors = 0;

                statusData = await response.json();
                
                const status = statusData.status || statusData.state || 'processing';
                const progress = statusData.progress || 0;
                const message = statusData.message || statusData.stage || 'Processando...';
                
                console.log(`📊 [Polling] Status: ${status}, Progresso: ${progress}%, Mensagem: ${message}`);
                
                // 🔥 ANÁLISE CONCLUÍDA
                if (status === 'completed' || status === 'complete' || status === 'success') {
                    updateAnalysisProgress(90, '📊 Buscando relatório completo...');
                    
                    // 🔥 Tentar buscar o resultado completo
                    const resultData = await fetchAnalysisResult(processId);
                    
                    if (resultData) {
                        updateAnalysisProgress(95, '✅ Relatório pronto!');
                        await sleep(500);
                        showResult(resultData);
                        state.isPolling = false;
                        return resultData;
                    } else if (statusData.result || statusData.analysis_info || statusData.chart_data) {
                        // 🔥 Se o próprio polling já tem os dados
                        showResult(statusData);
                        state.isPolling = false;
                        return statusData;
                    } else {
                        // 🔥 Concluído mas sem dados ainda, esperar mais um pouco
                        await sleep(interval);
                        continue;
                    }
                    
                // 🔥 ERRO NA ANÁLISE
                } else if (status === 'error' || status === 'failed') {
                    throw new Error(statusData.error || statusData.message || 'Erro na análise');
                    
                // 🔥 AINDA PROCESSANDO
                } else {
                    const pollProgress = Math.min(50 + (attempts / maxAttempts) * 40, 95);
                    const elapsed = Math.round((Date.now() - startTime) / 1000);
                    
                    // 🔥 Mensagem com tempo decorrido e total
                    const progressMsg = progress > 0 ? `${Math.round(progress)}%` : '...';
                    updateAnalysisProgress(
                        pollProgress,
                        `⏳ ${message} (${progressMsg}) - ${elapsed}s / ${totalTimeoutSeconds}s`
                    );
                    
                    // 🔥 Atualizar subtítulo com informações adicionais
                    if (elements.statusSub) {
                        const remaining = Math.max(0, totalTimeoutSeconds - elapsed);
                        elements.statusSub.textContent = `Processamento em andamento... ~${remaining}s restantes`;
                    }
                }

                await sleep(interval);

            } catch (error) {
                console.warn('⚠️ Polling error:', error.message);
                if (error.message.includes('Sessão expirada') || error.message.includes('Token')) {
                    throw error;
                }
                if (attempts >= maxAttempts) {
                    throw new Error('Timeout: a análise está demorando mais que o esperado.');
                }
                await sleep(interval * 1.5);
            }
        }

        state.isPolling = false;
        throw new Error(`Timeout: a análise não foi concluída dentro de ${totalTimeoutSeconds} segundos.`);
    }

    // ==============================================
    // 🔥 BUSCA RESULTADO
    // ==============================================

    async function fetchAnalysisResult(processId) {
        try {
            const token = getToken();
            
            if (!token) {
                console.warn('⚠️ Sem token para buscar resultado');
                return null;
            }
            
            const endpoints = [
                `/analysis/result/${processId}`,
                `/result/${processId}`,
                `/analysis/${processId}`,
                `/analyses/${processId}`,
            ];

            for (const endpoint of endpoints) {
                try {
                    const url = buildApiUrl(endpoint);
                    console.log(`🔍 Buscando resultado em: ${url}`);
                    
                    const response = await fetch(url, {
                        headers: { 'Authorization': `Bearer ${token}` }
                    });

                    if (response.ok) {
                        const data = await response.json();
                        console.log(`✅ Resultado obtido via ${endpoint}`);
                        
                        if (data.success !== false) {
                            return data;
                        }
                        if (data.data && data.data.success !== false) {
                            return data.data;
                        }
                    }
                } catch (e) {
                    console.debug(`⚠️ Endpoint ${endpoint} falhou:`, e.message);
                }
            }

            try {
                const url = buildApiUrl('/analyses/history');
                const response = await fetch(url, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });

                if (response.ok) {
                    const data = await response.json();
                    const analyses = data.analyses || data.data || [];
                    
                    const found = analyses.find(a => 
                        a.process_id === processId || 
                        a.id === processId || 
                        String(a.id) === processId
                    );
                    
                    if (found) {
                        console.log('✅ Resultado encontrado no histórico');
                        return found;
                    }
                }
            } catch (e) {}

            console.warn(`⚠️ Resultado não encontrado para: ${processId}`);
            return null;

        } catch (error) {
            console.error('❌ Erro ao buscar resultado:', error);
            return null;
        }
    }

    // ==============================================
    // 🔥 EVENTOS
    // ==============================================

    function setupEvents() {
        const dropArea = elements.dropArea;
        if (dropArea) {
            dropArea.addEventListener('dragover', function(e) {
                e.preventDefault();
                this.classList.add('dragover');
            });

            dropArea.addEventListener('dragleave', function(e) {
                e.preventDefault();
                this.classList.remove('dragover');
            });

            dropArea.addEventListener('drop', function(e) {
                e.preventDefault();
                this.classList.remove('dragover');
                if (e.dataTransfer.files.length > 0 && !state.isUploading) {
                    addFiles(e.dataTransfer.files);
                }
            });

            dropArea.addEventListener('click', function() {
                if (!state.isUploading && elements.fileInput) {
                    elements.fileInput.click();
                }
            });
        }

        if (elements.fileInput) {
            elements.fileInput.addEventListener('change', function(e) {
                if (this.files.length > 0) {
                    addFiles(this.files);
                }
                this.value = '';
            });
        }

        if (elements.downloadPdfBtn) {
            elements.downloadPdfBtn.addEventListener('click', function() {
                if (state.analysisResult) {
                    showNotification('📄 Gerando PDF...', 'info');
                    window.dispatchEvent(new CustomEvent('pdf:generate', {
                        detail: { data: state.analysisResult }
                    }));
                } else {
                    showNotification('Nenhum resultado disponível para gerar PDF.', 'warning');
                }
            });
        }

        if (elements.newAnalysisBtn) {
            elements.newAnalysisBtn.addEventListener('click', function() {
                hideResult();
                resetAnalysisStatus();
                if (elements.dropArea) {
                    elements.dropArea.classList.remove('success');
                    elements.dropArea.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            });
        }

        document.addEventListener('creditsUpdated', updateCreditsDisplay);
        document.addEventListener('credits:updated', updateCreditsDisplay);
        document.addEventListener('premiumStatusUpdated', updateCreditsDisplay);

        document.addEventListener('analysis:success', function(e) {
            const detail = e.detail || {};
            if (detail.result) {
                showResult(detail.result);
            }
        });

        const appReadyHandler = function() {
            updateCreditsDisplay();
        };

        document.addEventListener('app:ready', appReadyHandler);
        window.addEventListener('app:ready', appReadyHandler);

        console.log('✅ Eventos configurados');
    }

    // ==============================================
    // 🔥 EXPORTAÇÕES GLOBAIS
    // ==============================================

    window.UploadSystem = {
        addFiles: addFiles,
        removeFile: removeFile,
        clearFiles: function() {
            state.files = [];
            updateFilePreview();
            resetAnalysisStatus();
            hideResult();
        },
        getFiles: function() { return state.files.slice(); },
        startAnalysis: startAnalysis,
        getResult: function() { return state.analysisResult; },
        isUploading: function() { return state.isUploading; },
        updateCredits: updateCreditsDisplay,
        CONFIG: CONFIG,
        refreshPow: async function() {
            state.powLastRefresh = 0;
            state.powRecoveryAttempts = 0;
            if (window.powClient) {
                window.powClient.clearCache();
                window.powClient.reset();
            }
            return await getPowSolution(true);
        },
        recover: refreshPowAndRetry,
        getDiagnostics: function() {
            return {
                state: {
                    files: state.files.length,
                    isUploading: state.isUploading,
                    isPolling: state.isPolling,
                    pollAttempts: state.pollAttempts,
                    errorCount: state.errorCount,
                    lastError: state.lastError,
                    powRecoveryAttempts: state.powRecoveryAttempts,
                    isRecovering: state.isRecovering,
                },
                pow: window.powClient ? window.powClient.getStats() : null,
                config: CONFIG,
                appReady: !!getApp(),
                token: !!getToken(),
            };
        },
        debug: {
            state: state,
            pollStatus: async function(processId) {
                return await fetchAnalysisResult(processId || state.currentProcessId);
            },
            getPowSolution: getPowSolution,
            refreshPowAndRetry: refreshPowAndRetry,
        }
    };

    // ==============================================
    // 🔥 INICIALIZAÇÃO
    // ==============================================

    function init() {
        console.log('🚀 Inicializando UploadReportSystem v2.5...');
        
        cacheElements();
        
        if (typeof toastr !== 'undefined') {
            toastr.options = {
                closeButton: true,
                progressBar: true,
                positionClass: "toast-top-right",
                timeOut: 5000,
                extendedTimeOut: 1000,
                escapeHtml: true
            };
        }

        setupEvents();

        setTimeout(updateCreditsDisplay, 300);
        setInterval(updateCreditsDisplay, 30000);

        console.log('✅ UploadReportSystem v2.5 inicializado!');
        console.log(`   📁 Max files: ${CONFIG.MAX_FILES}`);
        console.log(`   📊 Max size: ${CONFIG.MAX_FILE_SIZE_KB}KB`);
        console.log(`   💰 Credits per file: ${CONFIG.CREDITS_PER_FILE}`);
        console.log(`   🔄 Polling interval: ${CONFIG.POLLING_INTERVAL}ms`);
        console.log(`   🔥 MAX_POLLING_ATTEMPTS: ${CONFIG.MAX_POLLING_ATTEMPTS} (${CONFIG.MAX_POLLING_ATTEMPTS * CONFIG.POLLING_INTERVAL / 1000}s)`);
        console.log(`   ⏰ GLOBAL_TIMEOUT: ${CONFIG.GLOBAL_TIMEOUT/1000}s (10 minutos)`);
        console.log(`   🔄 Upload retries: ${CONFIG.UPLOAD_RETRY_ATTEMPTS}`);
        console.log(`   🔍 Result endpoints: ${CONFIG.RESULT_ENDPOINTS.join(', ')}`);
        console.log(`   🔥 CORREÇÕES v2.5:`);
        console.log(`      ✅ Endpoint de polling: /analysis/progress/{id} (corrigido)`);
        console.log(`      ✅ Timeout aumentado: 3min → 10min (para 8.3min do backend)`);
        console.log(`      ✅ MAX_POLLING_ATTEMPTS: 90 → 300`);
        console.log(`      ✅ Melhor exibição de tempo restante`);
        console.log(`      ✅ Logs mais detalhados durante polling`);
        console.log(`   🔧 Use window.UploadSystem.getDiagnostics() para debug`);
        console.log(`   🔧 Use window.UploadSystem.recover() para forçar recuperação`);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        setTimeout(init, 100);
    }

    console.log('📊 upload-report-system.js v2.5 carregado (CORRIGIDO)');
    console.log(`   🔥 Rota polling: /analysis/progress/{id} (✅ corrigida)`);
    console.log(`   🔥 Timeout: 10min (✅ corrigido)`);
    console.log(`   🔄 Fallback upload: /upload-auto`);
    console.log('   📊 Polling inteligente com fallback');
    console.log('   📈 Busca resultado em múltiplos endpoints');
    console.log('   🔧 Tratamento de erro 400 com auto-recuperação');
    console.log('   🛡️ Detecção de PoW e créditos');

})();