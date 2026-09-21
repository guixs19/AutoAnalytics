// frontend/js/upload-report-system.js - v3.0 (PDF-FIRST + AYLA)
// SISTEMA COMPLETO DE UPLOAD, POLLING E RELATÓRIO
/**
 * 🔥 NOVIDADES v3.0:
 * - 🔥 PDF-FIRST: PDF aparece em ~1s, antes da IA
 * - 🔥 IA roda em PARALELO (não bloqueia)
 * - 🔥 Download INSTANTÂNEO via Blob
 * - 🔥 "Ayla" substitui TODAS as menções a ML/modelo/IA
 * - 🔥 Insights aparecem quando prontos
 * 
 * ✅ MANTIDO v2.7:
 * - PoW renovado corretamente
 * - Headers completos
 * - Sem fallback /upload-auto
 * - Não permite upload sem PoW
 */

(function() {
    'use strict';

    console.log('📊 Inicializando UploadReportSystem v3.0 (PDF-First + Ayla)...');

    // ==============================================
    // 🔥 CONFIGURAÇÕES
    // ==============================================

    const CONFIG = {
        MAX_FILES: 3,
        MAX_FILE_SIZE_KB: 200,
        CREDITS_PER_FILE: 1,
        POLLING_INTERVAL: 2000,
        MAX_POLLING_ATTEMPTS: 300,
        API_BASE: '/api',
        UPLOAD_ENDPOINT: '/upload-multi-analyze',
        UPLOAD_RETRY_ATTEMPTS: 3,
        UPLOAD_RETRY_DELAY: 2000,
        GLOBAL_TIMEOUT: 600000,
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
        BACKEND_PROCESSING_TIMEOUT: 500,
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
        chartData: null,
        pdfBlob: null,        // 🔥 NOVO: guarda o Blob do PDF
        pdfReady: false,      // 🔥 NOVO: flag se o PDF já está pronto
        aiReportDone: false,  // 🔥 NOVO: flag se a IA já terminou
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
        
        elements.revenueChart = document.getElementById('revenueChart');
    }

    // ==============================================
    // 🔥 UTILITÁRIOS
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

    /**
     * 🔥 Substitui menções a ML/IA/modelo por "Ayla"
     */
    function aylify(text) {
        if (!text) return '';
        return String(text)
            .replace(/\bML\b/g, 'Ayla')
            .replace(/\bml\b/g, 'Ayla')
            .replace(/modelo de machine learning/gi, 'Ayla')
            .replace(/machine learning/gi, 'Ayla')
            .replace(/\bmodelo preditivo\b/gi, 'Ayla')
            .replace(/\bmodelo\b/gi, 'Ayla')
            .replace(/\bIA\b/g, 'Ayla')
            .replace(/\bInteligência Artificial\b/gi, 'Ayla')
            .replace(/Análise por Ayla/g, 'Análise por Ayla');
    }

    // ==============================================
    // 🔥 EXTRAÇÃO DE DADOS
    // ==============================================

    function extractChartData(data) {
        let chartData = data?.result?.chart_data || 
                         data?.chart_data || 
                         data?.analysis?.chart_data || 
                         data?.data?.chart_data || 
                         {};
        
        if (!chartData.weekly && chartData.revenue) {
            chartData = {
                weekly: {
                    labels: chartData.labels || ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'],
                    revenue: chartData.revenue || [],
                    costs: chartData.costs || []
                }
            };
        }
        
        return chartData;
    }

    function extractExecutiveScore(data) {
        return data?.result?.executive_score || 
               data?.executive_score || 
               data?.analysis?.executive_score || 
               {};
    }

    function extractRecommendations(data) {
        return data?.result?.recommendations || 
               data?.recommendations || 
               data?.analysis?.recommendations || 
               [];
    }

    function extractInsights(data) {
        return data?.result?.insights || 
               data?.insights || 
               data?.analysis?.insights || 
               {};
    }

    function extractExecutiveSummary(data) {
        return data?.result?.executive_summary || 
               data?.executive_summary || 
               data?.analysis?.executive_summary || 
               '';
    }

    function extractMetrics(data) {
        return data?.result?.metrics || 
               data?.metrics || 
               data?.analysis?.metrics || 
               {};
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
    // 🔥 RESULT DISPLAY (PDF-FIRST v3.0)
    // ==============================================

    /**
     * 🔥 NOVO v3.0: Mostra resultado com PDF PRIMEIRO
     * 
     * ORDEM CORRETA:
     * 1. Métricas resumidas (síncrono, instantâneo)
     * 2. Gráficos Chart.js (paralelo)
     * 3. PDF Blob + preview (RÁPIDO, sem IA)
     * 4. IA em PARALELO (não bloqueia)
     */
    async function showResult(data) {
        if (!data) {
            console.warn('⚠️ showResult: dados vazios');
            return;
        }

        console.log('📊 [showResult v3.0] Iniciando com PDF-first...');
        
        const chartData = extractChartData(data);
        const executiveScore = extractExecutiveScore(data);
        const metrics = extractMetrics(data);

        state.chartData = chartData;
        state.analysisResult = data;
        state.pdfReady = false;
        state.aiReportDone = false;
        window._lastResult = data;
        window._lastChartData = chartData;

        // ==========================================
        // PASSO 1: MOSTRAR CONTAINER (sem esperar nada)
        // ==========================================
        
        if (elements.resultPlaceholder) elements.resultPlaceholder.style.display = 'none';
        if (elements.resultContainer) elements.resultContainer.classList.add('show');

        // ==========================================
        // PASSO 2: MÉTRICAS RESUMIDAS (síncrono)
        // ==========================================
        
        const totalRegistros = data.rows_processed || data.result?.rows_processed || metrics.total_predictions || 0;
        const confidenceScore = data.confidence_score || data.result?.confidence_score || metrics.mean || 0.65;
        const scoreColor = getScoreColor(confidenceScore);
        const scoreLabel = getScoreLabel(confidenceScore);
        const scoreIcon = getScoreIcon(confidenceScore);
        const confianca = Math.round(confidenceScore * 100);
        const filename = data.filename || data.result?.filename || 'Análise';

        if (elements.resultMetrics) {
            elements.resultMetrics.innerHTML = `
                <div class="result-stat">
                    <div class="stat-value">${totalRegistros.toLocaleString()}</div>
                    <div class="stat-label">Registros analisados</div>
                </div>
                <div class="result-stat">
                    <div class="stat-value" style="color: ${scoreColor};">${confianca}%</div>
                    <div class="stat-label">Score da Ayla</div>
                </div>
                <div class="result-stat">
                    <div class="stat-value">${scoreIcon} ${scoreLabel}</div>
                    <div class="stat-label">Classificação</div>
                </div>
                <div class="result-stat">
                    <div class="stat-value">${data.credit_consumed ? 1 : 0}</div>
                    <div class="stat-label">Créditos usados</div>
                </div>
            `;
        }

        // ==========================================
        // PASSO 3: DISPARA GRÁFICOS (Chart.js - paralelo)
        // ==========================================
        
        if (chartData && chartData.weekly) {
            console.log('📊 [showResult] Disparando gráficos Chart.js');
            window.dispatchEvent(new CustomEvent('chart:data_ready', {
                detail: { 
                    chart_data: chartData,
                    analysis_data: data
                }
            }));
        }

        // ==========================================
        // PASSO 4: GERA O PDF PRIMEIRO (não bloqueia a IA)
        // ==========================================
        
        console.log('📄 [showResult] Gerando PDF (antes da IA)...');
        
        try {
            if (window.generatePDFBlob && typeof window.generatePDFBlob === 'function') {
                const pdfBlob = await window.generatePDFBlob();
                
                if (pdfBlob) {
                    console.log('✅ [showResult] PDF Blob gerado:', pdfBlob.size, 'bytes');
                    
                    // Guarda o Blob
                    state.pdfBlob = pdfBlob;
                    window._lastPdfBlob = pdfBlob;
                    state.pdfReady = true;
                    
                    // 🔥 Renderiza no iframe
                    if (window.PDFPreview && typeof window.PDFPreview.renderFromBlob === 'function') {
                        window.PDFPreview.renderFromBlob(pdfBlob);
                        console.log('👁️ [showResult] Preview renderizado no iframe');
                    }
                } else {
                    console.warn('⚠️ [showResult] PDF Blob vazio');
                }
            } else {
                // Fallback: método antigo
                console.warn('⚠️ [showResult] generatePDFBlob não disponível, usando fallback');
                if (window.PDFPreview && typeof window.PDFPreview.render === 'function') {
                    window.PDFPreview.render();
                }
            }
        } catch (pdfError) {
            console.error('❌ [showResult] Erro ao gerar PDF:', pdfError);
            // Fallback
            if (window.PDFPreview && typeof window.PDFPreview.render === 'function') {
                window.PDFPreview.render();
            }
        }

        // ==========================================
        // PASSO 5: RELATÓRIO DA IA EM PARALELO (NÃO BLOQUEIA)
        // ==========================================
        
        console.log('🤖 [showResult] Disparando IA em paralelo...');
        
        // 🔥 NÃO usa await! Roda em background
        generateAIReportAsync(data, {
            chartData,
            executiveScore,
            metrics,
            totalRegistros,
            confidenceScore,
            scoreColor,
            scoreLabel,
            confianca,
            filename
        }).catch(err => {
            console.error('❌ [showResult] Erro na IA:', err);
        });

        // ==========================================
        // PASSO 6: FINALIZA (notificação + scroll)
        // ==========================================
        
        state.analysisResult = data;
        window._lastResult = data;
        window._lastChartData = chartData;

        const userName = getUserName();
        showNotification(`✅ ${userName}, análise concluída!`, 'success');

        const resultCard = document.getElementById('resultCard');
        if (resultCard) {
            setTimeout(() => {
                resultCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }, 300);
        }

        updateCreditsDisplay();
    }

    /**
     * 🔥 Gera o relatório da IA de forma assíncrona (não bloqueia o PDF)
     * Roda em paralelo após o PDF já estar visível.
     */
    async function generateAIReportAsync(data, context) {
        console.log('🤖 [Ayla] Iniciando geração do relatório (paralelo)...');
        
        try {
            const { chartData, executiveScore, metrics, totalRegistros, confidenceScore, scoreColor, scoreLabel, confianca } = context;
            
            // Deixa o PDF respirar antes de mexer no DOM
            await sleep(300);
            
            const recommendations = extractRecommendations(data);
            const insights = extractInsights(data);
            
            // 🔥 Monta os insights da Ayla
            if (elements.resultInsights) {
                let insightsHtml = `
                    <div style="margin-bottom:0.8rem;font-size:0.8rem;color:rgba(255,255,255,0.4);font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">
                        <i class="fas fa-lightbulb" style="color:#ff6b35;margin-right:0.5rem;"></i>
                        Insights da Ayla
                    </div>
                `;

                const finalRecommendations = recommendations.length > 0 ? recommendations : 
                    (insights.recomendacoes || insights.recommendations || []);
                
                if (finalRecommendations.length > 0) {
                    finalRecommendations.slice(0, 5).forEach(r => {
                        const desc = typeof r === 'string' ? r : (r.description || r.text || JSON.stringify(r));
                        insightsHtml += `
                            <div class="result-insight">
                                <span class="insight-icon"><i class="fas fa-chevron-right"></i></span>
                                ${aylify(desc)}
                            </div>
                        `;
                    });
                } else {
                    const defaultInsights = confidenceScore >= 0.7 ? [
                        '✅ Seus dados mostram um alto potencial de performance. Continue com as boas práticas!',
                        '📈 Recomendo manter o foco em treinamento e manutenção preventiva.',
                        '🎯 Considere expandir suas operações para capturar mais oportunidades.'
                    ] : confidenceScore >= 0.4 ? [
                        '📊 Seus dados indicam espaço para melhorias significativas.',
                        '🔍 Recomendo revisar processos e identificar gargalos operacionais.',
                        '📋 Considere investir em treinamento para sua equipe.'
                    ] : [
                        '⚠️ Seus dados mostram oportunidades claras de melhoria.',
                        '🛠️ Recomendo uma revisão completa dos processos da oficina.',
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

            // 🔥 Resumo técnico
            if (elements.resultSummary) {
                elements.resultSummary.innerHTML = `
                    <div style="display:flex; flex-wrap:wrap; gap:0.3rem 1rem; font-size:0.75rem; color:rgba(255,255,255,0.5);">
                        <span><strong style="color:#ff6b35;">📊 ${totalRegistros}</strong> registros</span>
                        <span><strong style="color:${scoreColor};">🎯 ${confianca}%</strong> score</span>
                        <span><strong style="color:#f5a623;">📈 ${scoreLabel}</strong></span>
                        <span><i class="fas fa-robot"></i> Análise por Ayla</span>
                    </div>
                `;
            }

            state.aiReportDone = true;
            console.log('✅ [Ayla] Relatório concluído (sem bloquear o PDF)');
            
        } catch (error) {
            console.error('❌ [Ayla] Erro:', error);
            // Fallback amigável
            if (elements.resultInsights) {
                elements.resultInsights.innerHTML = `
                    <div class="result-insight" style="color: rgba(255,255,255,0.5);">
                        <span class="insight-icon">ℹ️</span>
                        Análise detalhada indisponível no momento. O PDF já está pronto acima.
                    </div>
                `;
            }
        }
    }

    function hideResult() {
        if (elements.resultContainer) elements.resultContainer.classList.remove('show');
        if (elements.resultPlaceholder) elements.resultPlaceholder.style.display = 'block';
        if (elements.resultMetrics) elements.resultMetrics.innerHTML = '';
        if (elements.resultInsights) elements.resultInsights.innerHTML = '';
        if (elements.resultSummary) elements.resultSummary.innerHTML = '';
        
        // Limpa PDF
        state.pdfBlob = null;
        state.pdfReady = false;
        state.aiReportDone = false;
        window._lastPdfBlob = null;
        
        // Destroi preview
        if (window.PDFPreview && typeof window.PDFPreview.destroy === 'function') {
            window.PDFPreview.destroy();
        }
        const pdfWrapper = document.getElementById('pdfPreviewWrapper');
        if (pdfWrapper) pdfWrapper.style.display = 'none';
        
        state.analysisResult = null;
        state.chartData = null;
        window._lastResult = null;
        window._lastChartData = null;
    }

    // ==============================================
    // 🔥 POW - OBTENÇÃO DE SOLUÇÃO (MANTIDO v2.7)
    // ==============================================

    async function getPowSolution(forceRefresh = false) {
        const now = Date.now();
        
        if (forceRefresh || (now - state.powLastRefresh) > CONFIG.POW_MAX_AGE) {
            console.log('🔄 Renovando PoW (forçado)...');
            if (window.powClient) {
                try {
                    window.powClient.clearCache();
                    window.powClient.reset();
                } catch (e) {
                    console.warn('⚠️ Erro ao limpar cache do powClient:', e.message);
                }
            }
            state.powLastRefresh = now;
        }
        
        console.log('🔐 [PoW] Tentando obter solução...');
        console.log('   📦 powClient disponível?', !!window.powClient);
        
        if (!window.powClient) {
            throw new Error('Sistema de segurança (PoW) não carregado. Recarregue a página.');
        }
        
        if (typeof window.powClient.getSolutionForUpload !== 'function') {
            throw new Error('PoW Client inválido (getSolutionForUpload ausente). Recarregue a página.');
        }
        
        if (typeof window.powClient.isPowHealthy === 'function') {
            try {
                const healthy = await window.powClient.isPowHealthy();
                console.log('   🩺 PoW saudável?', healthy);
                
                if (!healthy) {
                    console.log('   ⚠️ PoW não saudável, tentando recuperar...');
                    if (typeof window.powClient.autoRecover === 'function') {
                        const recovered = await window.powClient.autoRecover();
                        state.powRecoveryAttempts++;
                        console.log('   🔄 Recuperação:', recovered ? 'sucesso' : 'falhou');
                    }
                }
            } catch (e) {
                console.warn('   ⚠️ Erro ao verificar saúde do PoW:', e.message);
            }
        }
        
        try {
            const solution = await window.powClient.getSolutionForUpload();
            
            if (!solution || !solution.prefix || !solution.nonce) {
                throw new Error('Solução PoW inválida retornada pelo cliente');
            }
            
            console.log('✅ PoW solução obtida');
            console.log(`   🔑 Prefix: ${solution.prefix.substring(0, 10)}...`);
            console.log(`   🔑 Nonce: ${solution.nonce}`);
            console.log(`   🔑 Complexity: ${solution.complexity}`);
            
            return solution;
            
        } catch (e) {
            console.error('❌ Erro ao obter solução PoW:', e.message);
            throw new Error(`Falha ao obter PoW: ${e.message}`);
        }
    }

    // ==============================================
    // 🔥 UPLOAD E ANÁLISE (MANTIDO v2.7)
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
            `${userName}, preparando ${filesToUpload.length} arquivo(s)`,
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
                updateAnalysisProgress(15, '🔐 Gerando prova de segurança...');
                solution = await getPowSolution(true);
            } catch (e) {
                console.error('❌ Falha crítica ao obter PoW:', e.message);
                showNotification(`❌ Erro de segurança: ${e.message}`, 'error');
                state.isUploading = false;
                state.lastError = e.message;
                state.errorCount++;
                resetAnalysisStatus();
                if (elements.dropArea) elements.dropArea.classList.add('error');
                return;
            }
            
            if (!solution) {
                console.error('❌ PoW retornou null');
                showNotification('❌ Erro de segurança: PoW não disponível.', 'error');
                state.isUploading = false;
                resetAnalysisStatus();
                return;
            }
            
            const result = await uploadWithRetry(formData, solution, filesToUpload);
            
            if (!result) {
                throw new Error('Falha no upload após múltiplas tentativas');
            }

            const data = result;
            
            updateAnalysisProgress(50, '✅ Upload concluído, processando...');

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
                await showResult(data);
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
                    if (confirm('⚠️ Erro de segurança (PoW). Deseja tentar recuperar automaticamente?')) {
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
    // 🔥 UPLOAD COM RETRY (MANTIDO v2.7)
    // ==============================================

    async function uploadWithRetry(formData, solution, files) {
        let lastError = null;
        const maxRetries = CONFIG.UPLOAD_RETRY_ATTEMPTS;
        const endpoints = [CONFIG.UPLOAD_ENDPOINT];
        
        for (let endpoint of endpoints) {
            let endpointFailed = false;
            
            for (let attempt = 1; attempt <= maxRetries; attempt++) {
                try {
                    const token = getToken();
                    if (!token) {
                        throw new Error('Token não encontrado. Faça login novamente.');
                    }
                    
                    if (!solution || !solution.prefix || !solution.nonce) {
                        throw new Error('PoW ausente. Não é possível fazer upload.');
                    }
                    
                    const headers = {
                        'Authorization': `Bearer ${token}`,
                        'Accept': 'application/json',
                        'X-PoW-Challenge': solution.prefix,
                        'X-PoW-Nonce': solution.nonce,
                        'X-PoW-Complexity': String(solution.complexity || 4),
                        'X-PoW-Timestamp': String(Date.now()),
                        'X-Request-ID': Math.random().toString(36).substring(2, 10),
                    };

                    console.log(`📤 Upload com PoW (tentativa ${attempt}/${maxRetries})`);
                    const url = buildApiUrl(endpoint);
                    
                    updateAnalysisProgress(
                        20 + (attempt - 1) * 15,
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
                            } catch (e) {
                                console.log(`📄 Resposta texto: ${responseText.substring(0, 200)}...`);
                            }
                        }
                    } catch (e) {
                        console.warn('⚠️ Não foi possível ler a resposta');
                    }

                    if (response.status === 400) {
                        let errorMessage = 'Erro na requisição.';
                        
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
                        
                        if (isPowError(errorStr)) {
                            if (window.powClient) {
                                window.powClient.clearCache();
                                window.powClient.reset();
                            }
                            state.powLastRefresh = 0;
                            
                            try {
                                const newSolution = await getPowSolution(true);
                                if (newSolution) {
                                    solution = newSolution;
                                    continue;
                                }
                            } catch (e) {
                                throw new Error(`Falha ao renovar PoW: ${e.message}`);
                            }
                        }
                        
                        if (isCreditsError(errorStr)) {
                            throw new Error(`Créditos insuficientes: ${errorStr}`);
                        }
                        
                        throw new Error(errorStr);
                    }

                    if (response.status === 428) {
                        if (window.powClient) {
                            window.powClient.clearCache();
                            window.powClient.reset();
                        }
                        state.powLastRefresh = 0;
                        
                        try {
                            const newSolution = await getPowSolution(true);
                            if (newSolution) {
                                solution = newSolution;
                                continue;
                            }
                        } catch (e) {}
                        throw new Error('PoW expirado. Tente novamente.');
                    }

                    if (response.status === 401) {
                        const app = getApp();
                        if (app && typeof app.refreshTokenSafely === 'function') {
                            const refreshed = await app.refreshTokenSafely();
                            if (refreshed) continue;
                        }
                        throw new Error('Sessão expirada. Faça login novamente.');
                    }

                    if (response.status === 429) {
                        const data = responseData || {};
                        const retryAfter = data.retry_after || 5;
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
                        error.message.includes('Sessão expirada') ||
                        error.message.includes('PoW ausente')) {
                        throw error;
                    }
                    
                    if (endpointFailed) break;
                    
                    if (attempt < maxRetries) {
                        const delay = getBackoffDelay(attempt);
                        await sleep(delay);
                    }
                }
            }
        }

        throw lastError || new Error('Upload falhou após múltiplas tentativas');
    }

    // ==============================================
    // 🔥 POLLING
    // ==============================================

    async function pollAnalysisStatus(processId) {
        let attempts = 0;
        const maxAttempts = CONFIG.MAX_POLLING_ATTEMPTS;
        const interval = CONFIG.POLLING_INTERVAL;
        const startTime = Date.now();
        let consecutiveErrors = 0;
        
        state.isPolling = true;
        state.pollAttempts = 0;

        const totalTimeoutSeconds = Math.round(CONFIG.GLOBAL_TIMEOUT / 1000);

        while (attempts < maxAttempts) {
            attempts++;
            state.pollAttempts = attempts;
            
            if (Date.now() - startTime > CONFIG.GLOBAL_TIMEOUT) {
                throw new Error(`Timeout: análise excedeu ${totalTimeoutSeconds}s.`);
            }
            
            try {
                const token = getToken();
                if (!token) throw new Error('Token não encontrado.');
                
                const statusEndpoint = `/analysis/progress/${processId}`;
                const url = buildApiUrl(statusEndpoint);
                
                console.log(`📊 [Polling ${attempts}/${maxAttempts}]`);
                
                const response = await fetch(url, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });

                if (!response.ok) {
                    if (response.status === 404) {
                        consecutiveErrors = 0;
                        const progress = 50 + (attempts / maxAttempts) * 40;
                        const elapsed = Math.round((Date.now() - startTime) / 1000);
                        updateAnalysisProgress(
                            progress,
                            `⏳ Aguardando... (${elapsed}s / ${totalTimeoutSeconds}s)`
                        );
                        await sleep(interval);
                        continue;
                    }
                    if (response.status === 401) {
                        throw new Error('Sessão expirada. Faça login novamente.');
                    }
                    
                    consecutiveErrors++;
                    if (consecutiveErrors > 3) {
                        throw new Error(`Erro repetido: ${response.status}`);
                    }
                    
                    await sleep(interval * 1.5);
                    continue;
                }

                consecutiveErrors = 0;

                const statusData = await response.json();
                
                const status = statusData.status || statusData.state || 'processing';
                const progress = statusData.progress || 0;
                const message = statusData.message || statusData.stage || 'Processando...';
                
                console.log(`📊 Status: ${status}, ${progress}%`);

                if (status === 'processing') {
                    const pollProgress = Math.min(50 + (attempts / maxAttempts) * 40, 95);
                    const elapsed = Math.round((Date.now() - startTime) / 1000);
                    const progressMsg = progress > 0 ? `${Math.round(progress)}%` : '...';
                    updateAnalysisProgress(
                        pollProgress,
                        `⏳ ${message} (${progressMsg})`
                    );
                    
                    if (elements.statusSub) {
                        const remaining = Math.max(0, totalTimeoutSeconds - elapsed);
                        elements.statusSub.textContent = `Processando... ~${remaining}s`;
                    }
                    
                    await sleep(interval);
                    continue;
                }

                if (status === 'completed' || status === 'complete' || status === 'success') {
                    updateAnalysisProgress(90, '📊 Buscando relatório...');
                    
                    const chartData = extractChartData(statusData);
                    if (chartData && chartData.weekly) {
                        window.dispatchEvent(new CustomEvent('chart:data_ready', {
                            detail: { chart_data: chartData, analysis_data: statusData }
                        }));
                    }
                    
                    const resultData = await fetchAnalysisResult(processId);
                    
                    if (resultData) {
                        updateAnalysisProgress(95, '✅ Relatório pronto!');
                        await sleep(500);
                        const resultChartData = extractChartData(resultData);
                        if (resultChartData && resultChartData.weekly) {
                            window.dispatchEvent(new CustomEvent('chart:data_ready', {
                                detail: { chart_data: resultChartData, analysis_data: resultData }
                            }));
                        }
                        await showResult(resultData);
                        state.isPolling = false;
                        return resultData;
                    } else if (statusData.result || statusData.analysis_info || statusData.chart_data) {
                        await showResult(statusData);
                        state.isPolling = false;
                        return statusData;
                    } else {
                        await sleep(interval);
                        continue;
                    }
                    
                } else if (status === 'error' || status === 'failed') {
                    throw new Error(statusData.error || statusData.message || 'Erro na análise');
                    
                } else {
                    await sleep(interval);
                }

            } catch (error) {
                console.warn('⚠️ Polling error:', error.message);
                if (error.message.includes('Sessão expirada') || error.message.includes('Token')) {
                    throw error;
                }
                if (attempts >= maxAttempts) {
                    throw new Error('Timeout: análise demorando mais que o esperado.');
                }
                await sleep(interval * 1.5);
            }
        }

        state.isPolling = false;
        throw new Error(`Timeout: análise não concluída em ${totalTimeoutSeconds}s.`);
    }

    // ==============================================
    // 🔥 BUSCA RESULTADO
    // ==============================================

    async function fetchAnalysisResult(processId) {
        try {
            const token = getToken();
            if (!token) return null;
            
            const endpoints = [
                `/analysis/result/${processId}`,
                `/result/${processId}`,
                `/analysis/${processId}`,
                `/analyses/${processId}`,
            ];

            for (const endpoint of endpoints) {
                try {
                    const url = buildApiUrl(endpoint);
                    const response = await fetch(url, {
                        headers: { 'Authorization': `Bearer ${token}` }
                    });

                    if (response.ok) {
                        const data = await response.json();
                        if (data.success !== false) return data;
                        if (data.data && data.data.success !== false) return data.data;
                    }
                } catch (e) {
                    console.debug(`⚠️ ${endpoint}:`, e.message);
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
                    
                    if (found) return found;
                }
            } catch (e) {}

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

        // 🔥 BOTÃO DOWNLOAD - v3.0: usa Blob instantâneo
        if (elements.downloadPdfBtn) {
            elements.downloadPdfBtn.addEventListener('click', function() {
                // 🔥 Prioridade 1: Blob em memória (instantâneo)
                if (state.pdfBlob || window._lastPdfBlob) {
                    const blob = state.pdfBlob || window._lastPdfBlob;
                    const url = URL.createObjectURL(blob);
                    const link = document.createElement('a');
                    link.href = url;
                    link.download = 'Relatorio_Ayla_' + Date.now() + '.pdf';
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                    setTimeout(() => URL.revokeObjectURL(url), 1000);
                    showNotification('📄 PDF baixado!', 'success');
                    return;
                }
                
                // 🔥 Prioridade 2: PDFPreview tem Blob
                if (window.PDFPreview && window.PDFPreview._lastBlob) {
                    window.PDFPreview.download();
                    return;
                }
                
                // 🔥 Fallback: gera do zero
                showNotification('📄 Gerando PDF...', 'info');
                if (window.generatePDFBlob) {
                    window.generatePDFBlob().then(blob => {
                        if (blob) {
                            const url = URL.createObjectURL(blob);
                            const link = document.createElement('a');
                            link.href = url;
                            link.download = 'Relatorio_Ayla_' + Date.now() + '.pdf';
                            link.click();
                            setTimeout(() => URL.revokeObjectURL(url), 1000);
                        }
                    });
                } else if (window.generatePDF) {
                    window.generatePDF();
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

        document.addEventListener('chart:data_ready', function(e) {
            const detail = e.detail || {};
            if (detail.chart_data && detail.chart_data.weekly) {
                window.dispatchEvent(new CustomEvent('dashboard:render_chart', {
                    detail: {
                        chart_data: detail.chart_data,
                        analysis_data: detail.analysis_data
                    }
                }));
            }
        });

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
        getChartData: function() { return state.chartData || window._lastChartData || null; },
        getPdfBlob: function() { return state.pdfBlob || window._lastPdfBlob || null; },
        isUploading: function() { return state.isUploading; },
        isPdfReady: function() { return state.pdfReady; },
        isAiReportDone: function() { return state.aiReportDone; },
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
        extractChartData: extractChartData,
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
                    hasChartData: !!state.chartData,
                    pdfReady: state.pdfReady,
                    aiReportDone: state.aiReportDone,
                    hasPdfBlob: !!state.pdfBlob,
                },
                chartData: state.chartData ? {
                    hasWeekly: !!state.chartData.weekly,
                    hasRevenue: !!(state.chartData.weekly?.revenue?.length > 0)
                } : null,
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
            extractChartData: extractChartData,
            aylify: aylify,
        }
    };

    // ==============================================
    // 🔥 INICIALIZAÇÃO
    // ==============================================

    function init() {
        console.log('🚀 Inicializando UploadReportSystem v3.0...');
        
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

        console.log('✅ UploadReportSystem v3.0 inicializado!');
        console.log(`   📁 Max files: ${CONFIG.MAX_FILES}`);
        console.log(`   📊 Max size: ${CONFIG.MAX_FILE_SIZE_KB}KB`);
        console.log(`   💰 Credits per file: ${CONFIG.CREDITS_PER_FILE}`);
        console.log(`   🔄 Polling interval: ${CONFIG.POLLING_INTERVAL}ms`);
        console.log(`   ⏰ GLOBAL_TIMEOUT: ${CONFIG.GLOBAL_TIMEOUT/1000}s`);
        console.log(`   🔥 NOVIDADES v3.0:`);
        console.log(`      ✅ PDF-FIRST: PDF aparece em ~1s`);
        console.log(`      ✅ IA roda em PARALELO (não bloqueia)`);
        console.log(`      ✅ Download INSTANTÂNEO via Blob`);
        console.log(`      ✅ "Ayla" substitui TODAS as menções a ML/modelo/IA`);
        console.log(`   🔧 Use window.UploadSystem.getDiagnostics() para debug`);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        setTimeout(init, 100);
    }

    console.log('📊 upload-report-system.js v3.0 carregado (PDF-FIRST)');
    console.log('   ✅ PDF gerado ANTES da IA');
    console.log('   ✅ IA em paralelo (não bloqueia)');
    console.log('   ✅ Preview instantâneo');
    console.log('   ✅ Download instantâneo via Blob');
    console.log('='.repeat(60));

})();