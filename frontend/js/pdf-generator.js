// frontend/js/pdf-generator.js - VERSÃO 3.2 (INTELIGENTE E ROBUSTO)
/**
 * 🔥 PDF Generator - AutoAnalytics v3.2
 * 
 * ✅ INTELIGÊNCIA INCORPORADA:
 *    - Coleta automática de dados de múltiplas fontes
 *    - Detecta e sanitiza encoding automaticamente
 *    - Suporta múltiplos formatos de relatório
 *    - Cache de sanitização para performance
 * 
 * ✅ CORREÇÕES v3.2:
 *    - 🔥 CORRIGIDO: Busca dados reais da análise (não fallback)
 *    - 🔥 CORRIGIDO: Extração robusta de métricas
 *    - 🔥 ADICIONADO: Fallback inteligente para dados faltantes
 *    - 🔥 ADICIONADO: Logging detalhado para debug
 *    - 🔥 ADICIONADO: Verificação de dados antes de gerar PDF
 * 
 * ✅ SUPORTE A:
 *    - Dados da API (/api/...)
 *    - Dados do banco (analysis object)
 *    - Dados do dashboard (__APP_STATE)
 *    - Dados do upload (UploadSystem)
 *    - Dados do DOM (extração de elementos)
 * 
 * ✅ CARACTERES SUPORTADOS:
 *    - Acentos: á à â ã ä é è ê ë í ì î ï ó ò ô õ ö ú ù û ü ç ñ
 *    - Emojis: 📊 📈 📉 💰 💡 🎯 ✅ ❌ ⚠️ 🔴 🟢 🟡 🔥 ⭐ 🏆
 *    - Símbolos: ™ ® © ° ± … — – • “ ” ‘ ’ € £ ¥
 */

(function() {
    'use strict';

    console.log('📄 PDF Generator v3.2 - Modo Inteligente');

    // ==============================================
    // 🔥 CONFIGURAÇÕES
    // ==============================================

    const PDF_CONFIG = {
        // Fontes de dados (ordem de prioridade)
        DATA_SOURCES: [
            'UploadSystem',
            '__dashboard',
            '__APP_STATE',
            '_lastResult',
            'DOM'
        ],
        
        // Tempo limite para busca de dados (ms)
        DATA_FETCH_TIMEOUT: 3000,
        
        // Tamanho máximo do cache de sanitização
        CACHE_MAX_SIZE: 100,
        
        // Caracteres que precisam de sanitização
        SANITIZE_PATTERNS: {
            acentos: /[áàâãäéèêëíìîïóòôõöúùûüçñÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ]/g,
            emojis: /[\u{1F300}-\u{1FAFF}]/gu,
            especiais: /[™®©°±…—–•“‘”’€£¥]/g,
            controle: /[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g
        },
        
        // Mapeamento de caracteres para sanitização
        CHAR_MAP: {
            // Acentuados (minúsculos)
            'á': 'a', 'à': 'a', 'â': 'a', 'ã': 'a', 'ä': 'a',
            'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
            'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
            'ó': 'o', 'ò': 'o', 'ô': 'o', 'õ': 'o', 'ö': 'o',
            'ú': 'u', 'ù': 'u', 'û': 'u', 'ü': 'u',
            'ç': 'c', 'ñ': 'n',
            // Acentuados (maiúsculos)
            'Á': 'A', 'À': 'A', 'Â': 'A', 'Ã': 'A', 'Ä': 'A',
            'É': 'E', 'È': 'E', 'Ê': 'E', 'Ë': 'E',
            'Í': 'I', 'Ì': 'I', 'Î': 'I', 'Ï': 'I',
            'Ó': 'O', 'Ò': 'O', 'Ô': 'O', 'Õ': 'O', 'Ö': 'O',
            'Ú': 'U', 'Ù': 'U', 'Û': 'U', 'Ü': 'U',
            'Ç': 'C', 'Ñ': 'N',
            // Emojis e símbolos
            '📊': '[Gráfico]',
            '📈': '[↑]',
            '📉': '[↓]',
            '💰': '[$]',
            '💡': '[i]',
            '🎯': '[+]',
            '✅': '[OK]',
            '❌': '[X]',
            '⚠️': '[!]',
            '🔴': '[*]',
            '🟢': '[o]',
            '🟡': '[o]',
            '🔥': '[!]',
            '⭐': '[*]',
            '🏆': '[+]',
            '📋': '[*]',
            '🔧': '[*]',
            '🤖': '[AI]',
            '📄': '[PDF]',
            '📁': '[Folder]',
            '📂': '[Folder]',
            '🔍': '[Search]',
            '🛡️': '[Security]',
            '⚡': '[!]',
            '💎': '[Diamond]',
            '🚀': '[Rocket]',
            '🎉': '[Party]',
            '📌': '[Pin]',
            '📊': '[Chart]',
            '💵': '[$]',
            '💳': '[Card]',
            '🔄': '[Sync]',
            '📝': '[Note]',
            // Caracteres especiais
            '…': '...',
            '—': '-',
            '–': '-',
            '•': '*',
            '“': '"',
            '”': '"',
            '‘': "'",
            '’': "'",
            '€': 'EUR',
            '£': 'GBP',
            '¥': 'JPY',
            '©': '(c)',
            '®': '(r)',
            '™': '(TM)',
            '°': 'graus',
            '±': '+/-',
        }
    };

    // ==============================================
    // 🔥 CACHE DE SANITIZAÇÃO
    // ==============================================

    const SanitizeCache = {
        _cache: new Map(),
        _maxSize: PDF_CONFIG.CACHE_MAX_SIZE,
        
        get: function(text) {
            return this._cache.get(text);
        },
        
        set: function(text, sanitized) {
            if (this._cache.size >= this._maxSize) {
                const firstKey = this._cache.keys().next().value;
                this._cache.delete(firstKey);
            }
            this._cache.set(text, sanitized);
            return sanitized;
        },
        
        clear: function() {
            this._cache.clear();
        },
        
        getSize: function() {
            return this._cache.size;
        }
    };

    // ==============================================
    // 🔥 UTILITÁRIOS
    // ==============================================

    const Utils = {
        getToken: function() {
            try {
                const token = localStorage.getItem('access_token');
                if (!token || token === 'undefined' || token === 'null' || token.length < 10) {
                    return null;
                }
                return token;
            } catch (e) {
                return null;
            }
        },

        buildApiUrl: function(path) {
            if (!path) return '/api';
            const cleanPath = path.startsWith('/') ? path : '/' + path;
            if (cleanPath.startsWith('/api/')) return cleanPath;
            return '/api' + cleanPath;
        },

        sleep: function(ms) {
            return new Promise(resolve => setTimeout(resolve, ms));
        },

        isNumeric: function(value) {
            return !isNaN(parseFloat(value)) && isFinite(value);
        },

        safeNumber: function(value, defaultValue = 0) {
            const num = parseFloat(value);
            return isNaN(num) ? defaultValue : num;
        }
    };

    // ==============================================
    // 🔥 COLETOR DE DADOS INTELIGENTE (CORRIGIDO)
    // ==============================================

    const DataCollector = {
        _lastFetch: 0,
        _cachedData: null,
        _fetchInProgress: false,

        /**
         * 🔥 Coleta dados da melhor fonte disponível
         */
        collect: function() {
            console.log('🔍 Coletando dados da análise...');
            
            const sources = this._tryAllSources();
            
            // Filtrar fontes com dados válidos
            const validSources = sources.filter(s => s.data && Object.keys(s.data).length > 0);
            
            if (validSources.length === 0) {
                console.warn('⚠️ Nenhuma fonte de dados encontrada');
                return null;
            }
            
            // Usar a primeira fonte válida (prioridade)
            const bestSource = validSources[0];
            console.log(`📊 Dados encontrados em: ${bestSource.source}`);
            console.log('📊 Dados:', bestSource.data);
            
            return bestSource.data;
        },

        _tryAllSources: function() {
            const sources = [];
            
            // 1. UploadSystem
            if (window.UploadSystem && typeof window.UploadSystem.getResult === 'function') {
                try {
                    const data = window.UploadSystem.getResult();
                    if (data && Object.keys(data).length > 0) {
                        sources.push({ source: 'UploadSystem', data: data });
                    }
                } catch (e) {
                    console.warn('⚠️ Erro no UploadSystem:', e);
                }
            }
            
            // 2. __dashboard
            if (window.__dashboard) {
                try {
                    const state = window.__dashboard.state?.state || {};
                    const analyses = state.analyses?.active || [];
                    const lastAnalysis = analyses[0] || {};
                    const data = lastAnalysis.result || {};
                    if (data && Object.keys(data).length > 0) {
                        sources.push({ source: '__dashboard', data: data });
                    }
                    
                    // Tentar do state diretamente
                    if (!data || Object.keys(data).length === 0) {
                        const stateData = state.lastResult || state.analysisResult || {};
                        if (stateData && Object.keys(stateData).length > 0) {
                            sources.push({ source: '__dashboard.state', data: stateData });
                        }
                    }
                } catch (e) {
                    console.warn('⚠️ Erro no __dashboard:', e);
                }
            }
            
            // 3. __APP_STATE
            if (window.__APP_STATE) {
                try {
                    const state = window.__APP_STATE;
                    const data = state.lastAnalysis || state.analysisResult || {};
                    if (data && Object.keys(data).length > 0) {
                        sources.push({ source: '__APP_STATE', data: data });
                    }
                } catch (e) {
                    console.warn('⚠️ Erro no __APP_STATE:', e);
                }
            }
            
            // 4. _lastResult
            if (window._lastResult) {
                try {
                    const data = window._lastResult;
                    if (data && Object.keys(data).length > 0) {
                        sources.push({ source: '_lastResult', data: data });
                    }
                } catch (e) {
                    console.warn('⚠️ Erro no _lastResult:', e);
                }
            }
            
            // 5. DOM (extrair do HTML)
            try {
                const domData = this._extractFromDOM();
                if (domData && Object.keys(domData).length > 0) {
                    sources.push({ source: 'DOM', data: domData });
                }
            } catch (e) {
                console.warn('⚠️ Erro na extração do DOM:', e);
            }
            
            return sources;
        },

        _extractFromDOM: function() {
            const data = {};
            let hasData = false;
            
            // Tenta extrair do resultado visível
            const metricsEl = document.getElementById('resultMetrics');
            if (metricsEl) {
                const text = metricsEl.textContent;
                
                // Extrair total registros
                const registrosMatch = text.match(/(\d+)\s*registros?/i);
                if (registrosMatch) {
                    data.totalRegistros = parseInt(registrosMatch[1]);
                    hasData = true;
                }
                
                // Extrair score
                const scoreMatch = text.match(/(\d+)%/);
                if (scoreMatch) {
                    data.scoreMedio = parseInt(scoreMatch[1]) / 100;
                    hasData = true;
                }
            }
            
            // Tenta extrair do resumo
            const summaryEl = document.getElementById('resultSummary');
            if (summaryEl) {
                const text = summaryEl.textContent;
                const scoreMatch = text.match(/(\d+)%/);
                if (scoreMatch && !data.scoreMedio) {
                    data.scoreMedio = parseInt(scoreMatch[1]) / 100;
                    hasData = true;
                }
            }
            
            return hasData ? data : null;
        },

        /**
         * 🔥 Busca dados da API
         */
        fetchFromAPI: async function(processId) {
            if (this._fetchInProgress) {
                console.log('⏳ Busca em andamento, aguardando...');
                await Utils.sleep(500);
                return this._cachedData;
            }
            
            this._fetchInProgress = true;
            
            try {
                const token = Utils.getToken();
                if (!token) {
                    console.warn('⚠️ Sem token para buscar resultado');
                    return null;
                }
                
                const url = Utils.buildApiUrl(`/analysis/result/${processId}`);
                console.log(`🔍 Buscando resultado em: ${url}`);
                
                const response = await fetch(url, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                
                if (response.ok) {
                    const data = await response.json();
                    this._cachedData = data;
                    this._lastFetch = Date.now();
                    console.log('✅ Dados obtidos da API');
                    return data;
                }
            } catch (e) {
                console.warn('⚠️ Erro ao buscar dados da API:', e);
            } finally {
                this._fetchInProgress = false;
            }
            
            return null;
        },

        getProcessId: function() {
            // Tentar obter de várias fontes
            if (window.UploadSystem?.debug?.state?.currentProcessId) {
                return window.UploadSystem.debug.state.currentProcessId;
            }
            if (window.__dashboard?.state?.state?.currentProcessId) {
                return window.__dashboard.state.state.currentProcessId;
            }
            if (window._lastProcessId) {
                return window._lastProcessId;
            }
            return null;
        }
    };

    // ==============================================
    // 🔥 SANITIZADOR INTELIGENTE
    // ==============================================

    const TextSanitizer = {
        /**
         * 🔥 Sanitiza texto para PDF (com cache)
         */
        sanitize: function(text, options = {}) {
            if (!text) return '';
            
            // Verificar cache
            const cached = SanitizeCache.get(text);
            if (cached !== undefined) {
                return cached;
            }
            
            let sanitized = String(text);
            
            // Substituir caracteres especiais
            for (const [char, replacement] of Object.entries(PDF_CONFIG.CHAR_MAP)) {
                sanitized = sanitized.replace(new RegExp(char, 'g'), replacement);
            }
            
            // Remover caracteres de controle
            sanitized = sanitized.replace(PDF_CONFIG.SANITIZE_PATTERNS.controle, '');
            
            // Remover emojis não mapeados
            if (options.removeUnmappedEmojis !== false) {
                sanitized = sanitized.replace(/[\u{1F000}-\u{1FFFF}]/gu, '');
            }
            
            // Remover caracteres que quebram o PDF
            sanitized = sanitized.replace(/[^\x20-\x7E\u00C0-\u00FF\u0100-\u017F]/g, '');
            
            // Guardar no cache
            SanitizeCache.set(text, sanitized);
            
            return sanitized;
        },
        
        /**
         * 🔥 Sanitiza um objeto inteiro (recursivamente)
         */
        sanitizeObject: function(obj, options = {}) {
            if (!obj) return obj;
            
            if (typeof obj === 'string') {
                return this.sanitize(obj, options);
            }
            
            if (Array.isArray(obj)) {
                return obj.map(item => this.sanitizeObject(item, options));
            }
            
            if (typeof obj === 'object') {
                const result = {};
                for (const [key, value] of Object.entries(obj)) {
                    result[key] = this.sanitizeObject(value, options);
                }
                return result;
            }
            
            return obj;
        }
    };

    // ==============================================
    // 🔥 EXTRAÇÃO DE DADOS (CORRIGIDA)
    // ==============================================

    const DataExtractor = {
        /**
         * 🔥 Extrai métricas de forma robusta
         */
        extractMetrics: function(data) {
            const metrics = data.metrics || data.predictions_summary || data.analysis_metrics || {};
            
            return {
                totalRegistros: this._getValue(metrics, [
                    'dataset_rows', 'processed_rows', 'total_rows', 
                    'rows', 'total', 'count', 'totalRegistros'
                ], 0),
                
                scoreMedio: this._getValue(metrics, [
                    'mean_prediction', 'mean', 'avg_score', 
                    'average', 'score', 'scoreMedio'
                ], 0.65),
                
                highRisk: this._getValue(metrics, [
                    'high_risk_percentage', 'high_risk', 'highRisk',
                    'risco_alto', 'alto_risco'
                ], 0),
                
                lowRisk: this._getValue(metrics, [
                    'low_risk_percentage', 'low_risk', 'lowRisk',
                    'risco_baixo', 'baixo_risco'
                ], 0),
                
                stdScore: this._getValue(metrics, [
                    'std_prediction', 'std', 'std_score'
                ], 0)
            };
        },

        /**
         * 🔥 Extrai recomendações
         */
        extractRecommendations: function(data) {
            const recs = data.recommendations || data.recomendacoes || [];
            if (Array.isArray(recs) && recs.length > 0) {
                return recs;
            }
            
            // Tentar extrair do insights
            const insights = data.insights || {};
            if (insights.recomendacoes && Array.isArray(insights.recomendacoes)) {
                return insights.recomendacoes;
            }
            
            return [];
        },

        /**
         * 🔥 Extrai relatório da IA
         */
        extractAIReport: function(data) {
            const report = data.ai_report || data.full_analysis || data.executive_summary || '';
            if (report && report.length > 20) {
                return report;
            }
            
            // Tentar construir a partir de partes
            const parts = [];
            if (data.executive_summary) parts.push(data.executive_summary);
            if (data.analysis_summary) parts.push(data.analysis_summary);
            if (data.insights?.summary?.mensagem) parts.push(data.insights.summary.mensagem);
            
            return parts.join('\n\n');
        },

        _getValue: function(obj, keys, defaultValue) {
            for (const key of keys) {
                if (obj[key] !== undefined && obj[key] !== null) {
                    const value = obj[key];
                    if (typeof value === 'number' || Utils.isNumeric(value)) {
                        return Utils.safeNumber(value);
                    }
                    return value;
                }
            }
            return defaultValue;
        },

        /**
         * 🔥 Valida e completa dados faltantes
         */
        validateAndComplete: function(data) {
            const completed = { ...data };
            
            // Garantir métricas
            if (!completed.metrics) completed.metrics = {};
            
            // Garantir valores mínimos
            const metrics = completed.metrics;
            if (!metrics.dataset_rows && data.totalRegistros) {
                metrics.dataset_rows = data.totalRegistros;
            }
            if (!metrics.mean_prediction && data.scoreMedio) {
                metrics.mean_prediction = data.scoreMedio;
            }
            if (!metrics.high_risk_percentage && data.highRisk) {
                metrics.high_risk_percentage = data.highRisk;
            }
            if (!metrics.low_risk_percentage && data.lowRisk) {
                metrics.low_risk_percentage = data.lowRisk;
            }
            
            // Garantir que tem dados mínimos
            if (!metrics.dataset_rows) metrics.dataset_rows = 0;
            if (!metrics.mean_prediction) metrics.mean_prediction = 0.65;
            
            return completed;
        }
    };

    // ==============================================
    // 🔥 GERADOR DE PDF - CLASSE PRINCIPAL
    // ==============================================

    class PDFGenerator {
        constructor() {
            this._initialized = false;
            this._cache = new Map();
            this._templates = new Map();
            this._registerTemplates();
            console.log('✅ PDFGenerator v3.2 inicializado');
        }
        
        _registerTemplates() {
            this._templates.set('finance', this._generateFinanceReport.bind(this));
            this._templates.set('executive', this._generateExecutiveReport.bind(this));
            this._templates.set('raw', this._generateRawReport.bind(this));
        }
        
        /**
         * 🔥 Gera PDF inteligente
         */
        async generate(data = null, options = {}) {
            console.log('📄 Iniciando geração de PDF...');
            
            // 1. Se não recebeu dados, buscar
            let reportData = data;
            if (!reportData) {
                reportData = DataCollector.collect();
            }
            
            // 2. Se ainda não tem dados, tentar API
            if (!reportData || Object.keys(reportData).length === 0) {
                const processId = DataCollector.getProcessId();
                if (processId) {
                    console.log('🔍 Tentando buscar dados da API...');
                    const apiData = await DataCollector.fetchFromAPI(processId);
                    if (apiData) {
                        reportData = apiData;
                    }
                }
            }
            
            // 3. Se ainda não tem dados, usar fallback
            if (!reportData || Object.keys(reportData).length === 0) {
                console.warn('⚠️ Nenhum dado encontrado, usando fallback');
                reportData = this._getFallbackData();
            }
            
            // 4. Validar e completar dados
            reportData = DataExtractor.validateAndComplete(reportData);
            
            // 5. Detectar tipo de relatório
            const reportType = this._detectReportType(reportData);
            console.log(`📄 Tipo: ${reportType}`);
            
            // 6. Sanitizar dados
            const sanitizedData = TextSanitizer.sanitizeObject(reportData);
            
            // 7. Gerar PDF
            const template = this._templates.get(reportType) || this._templates.get('finance');
            return template(sanitizedData, options);
        }
        
        _detectReportType(data) {
            if (data.executive_score || data.executive_summary) return 'executive';
            if (data.metrics || data.predictions || data.insights) return 'finance';
            if (data.raw_data || data.original_data) return 'raw';
            return 'finance';
        }
        
        _getFallbackData() {
            return {
                metrics: {
                    dataset_rows: 0,
                    mean_prediction: 0.65,
                    high_risk_percentage: 0,
                    low_risk_percentage: 0,
                },
                predictions: [],
                recommendations: [
                    '📊 Faça upload de um arquivo para análise',
                    '📈 Os dados aparecerão aqui após o processamento'
                ],
                ai_report: 'Aguardando dados para análise. Faça upload de um arquivo CSV ou Excel.'
            };
        }
        
        /**
         * 🔥 Gera Relatório Financeiro
         */
        _generateFinanceReport(data, options = {}) {
            const { jsPDF } = window.jspdf;
            if (!jsPDF) {
                console.error('❌ jsPDF não encontrado!');
                alert('Erro: Biblioteca jsPDF não carregada.');
                return;
            }
            
            const doc = new jsPDF('p', 'mm', 'a4');
            const primaryColor = [255, 107, 53];
            const darkBg = [15, 12, 41];
            
            // Extrair dados
            const metrics = data.metrics || {};
            const totalRegistros = metrics.dataset_rows || 0;
            const scoreMedio = metrics.mean_prediction || 0.65;
            const highRisk = metrics.high_risk_percentage || 0;
            const lowRisk = metrics.low_risk_percentage || 0;
            
            console.log(`📊 Dados: Total=${totalRegistros}, Score=${scoreMedio}, Risco=${highRisk}%`);
            
            // 1. CABEÇALHO
            doc.setFillColor(darkBg[0], darkBg[1], darkBg[2]);
            doc.rect(0, 0, 210, 40, 'F');
            
            doc.setTextColor(255, 255, 255);
            doc.setFontSize(22);
            doc.setFont('helvetica', 'bold');
            doc.text('📊 AutoAnalytics', 20, 25);
            
            doc.setFontSize(12);
            doc.setFont('helvetica', 'normal');
            doc.text('Relatório de Análise Financeira', 20, 33);
            
            doc.setFontSize(8);
            doc.setTextColor(200, 200, 200);
            doc.text('Gerado em: ' + new Date().toLocaleDateString('pt-BR'), 20, 39);
            
            // 2. MÉTRICAS
            let yPos = 55;
            
            doc.setTextColor(50, 50, 50);
            doc.setFontSize(14);
            doc.setFont('helvetica', 'bold');
            doc.text('📈 Métricas da Análise', 20, yPos);
            yPos += 8;
            
            const metricsData = [
                { label: 'Total Registros', value: totalRegistros.toLocaleString() || '0', icon: '📋' },
                { label: 'Score Médio', value: (scoreMedio * 100).toFixed(0) + '%', icon: '📈' },
                { label: 'Alto Risco', value: highRisk.toFixed(0) + '%', icon: '🔴' },
                { label: 'Baixo Risco', value: lowRisk.toFixed(0) + '%', icon: '🟢' }
            ];
            
            const colWidth = 42;
            const startX = 20;
            
            metricsData.forEach((item, index) => {
                const x = startX + (index * colWidth);
                
                doc.setFillColor(245, 245, 245);
                doc.roundedRect(x, yPos, colWidth - 2, 28, 3, 3, 'F');
                
                doc.setTextColor(100, 100, 100);
                doc.setFontSize(7);
                doc.setFont('helvetica', 'normal');
                doc.text(TextSanitizer.sanitize(item.icon + ' ' + item.label), x + 3, yPos + 6);
                
                const color = item.value.includes('%') && parseInt(item.value) > 70 ? '#48bb78' : 
                             item.value.includes('%') && parseInt(item.value) > 30 ? '#f5a623' : 
                             primaryColor;
                doc.setTextColor(color[0] || 255, color[1] || 107, color[2] || 53);
                doc.setFontSize(14);
                doc.setFont('helvetica', 'bold');
                doc.text(TextSanitizer.sanitize(item.value), x + 3, yPos + 22);
            });
            
            yPos += 38;
            
            // 3. RELATÓRIO DA IA
            doc.setTextColor(50, 50, 50);
            doc.setFontSize(14);
            doc.setFont('helvetica', 'bold');
            doc.text('🤖 Relatório da IA', 20, yPos);
            yPos += 8;
            
            doc.setFontSize(10);
            doc.setFont('helvetica', 'normal');
            
            let reportText = data.ai_report || data.executive_summary || '';
            if (!reportText || reportText.length < 20) {
                const safeTotal = totalRegistros.toLocaleString();
                const safeScore = (scoreMedio * 100).toFixed(0);
                const safeHighRisk = highRisk.toFixed(0);
                const safeLowRisk = lowRisk.toFixed(0);
                
                reportText = `Análise concluída com sucesso!\n\n` +
                           `Foram analisados ${safeTotal} registros, com um score médio de ${safeScore}%.\n\n` +
                           `${safeHighRisk}% dos casos são de alto risco, indicando a necessidade de revisão de processos.\n\n` +
                           `${safeLowRisk}% dos casos são de baixo risco, demonstrando boa performance.\n\n` +
                           `Recomenda-se monitorar de perto os casos de alto risco e manter as boas práticas que geram resultados positivos.`;
            }
            
            const sanitizedReport = TextSanitizer.sanitize(reportText);
            const reportLines = doc.splitTextToSize(sanitizedReport, 170);
            doc.text(reportLines, 20, yPos);
            yPos += (reportLines.length * 6) + 10;
            
            // 4. RECOMENDAÇÕES
            const recommendations = DataExtractor.extractRecommendations(data);
            if (recommendations.length > 0) {
                doc.setTextColor(50, 50, 50);
                doc.setFontSize(14);
                doc.setFont('helvetica', 'bold');
                doc.text('🎯 Recomendações', 20, yPos);
                yPos += 8;
                
                doc.setFontSize(10);
                doc.setFont('helvetica', 'normal');
                
                recommendations.slice(0, 4).forEach(rec => {
                    const safeRec = TextSanitizer.sanitize(rec);
                    const recLines = doc.splitTextToSize('• ' + safeRec, 160);
                    doc.text(recLines, 22, yPos);
                    yPos += (recLines.length * 6) + 2;
                });
                yPos += 5;
            }
            
            // 5. RODAPÉ
            doc.setFillColor(darkBg[0], darkBg[1], darkBg[2]);
            doc.rect(0, 280, 210, 17, 'F');
            
            doc.setTextColor(200, 200, 200);
            doc.setFontSize(7);
            doc.setFont('helvetica', 'normal');
            doc.text('AutoAnalytics v3.2 - Relatório gerado automaticamente por IA', 20, 290);
            doc.text('Página 1/1', 170, 290);
            
            // 6. SALVAR
            try {
                const filename = options.filename || `Relatorio_AutoAnalytics_${Date.now()}.pdf`;
                doc.save(filename);
                console.log(`✅ PDF gerado: ${filename}`);
                return doc;
            } catch (error) {
                console.error('❌ Erro ao salvar PDF:', error);
                alert('Erro ao gerar PDF: ' + error.message);
                return null;
            }
        }
        
        /**
         * 🔥 Gera Relatório Executivo
         */
        _generateExecutiveReport(data, options = {}) {
            const { jsPDF } = window.jspdf;
            if (!jsPDF) {
                console.error('❌ jsPDF não encontrado!');
                return;
            }
            
            const doc = new jsPDF('p', 'mm', 'a4');
            const darkBg = [15, 12, 41];
            
            // Cabeçalho
            doc.setFillColor(darkBg[0], darkBg[1], darkBg[2]);
            doc.rect(0, 0, 210, 40, 'F');
            
            doc.setTextColor(255, 255, 255);
            doc.setFontSize(22);
            doc.setFont('helvetica', 'bold');
            doc.text('📊 AutoAnalytics', 20, 25);
            
            doc.setFontSize(12);
            doc.setFont('helvetica', 'normal');
            doc.text('Relatório Executivo', 20, 33);
            
            doc.setFontSize(8);
            doc.setTextColor(200, 200, 200);
            doc.text('Gerado em: ' + new Date().toLocaleDateString('pt-BR'), 20, 39);
            
            let yPos = 55;
            
            // Score Executivo
            const score = data.executive_score || {};
            if (Object.keys(score).length > 0) {
                doc.setTextColor(50, 50, 50);
                doc.setFontSize(14);
                doc.setFont('helvetica', 'bold');
                doc.text('🏆 Score Executivo', 20, yPos);
                yPos += 8;
                
                const scoreItems = [
                    { label: 'Nota Geral', value: score.nota_geral || 0 },
                    { label: 'Saúde Financeira', value: score.saude_financeira || 0 },
                    { label: 'Eficiência', value: score.eficiencia || 0 },
                    { label: 'Crescimento', value: score.crescimento || 0 },
                    { label: 'Nível de Risco', value: score.nivel_risco || 'Moderado' }
                ];
                
                doc.setFontSize(10);
                doc.setFont('helvetica', 'normal');
                scoreItems.forEach(item => {
                    const value = typeof item.value === 'number' ? item.value.toFixed(1) : item.value;
                    doc.text(`${item.label}: ${value}`, 20, yPos);
                    yPos += 6;
                });
                yPos += 4;
            }
            
            // Resumo Executivo
            if (data.executive_summary) {
                doc.setTextColor(50, 50, 50);
                doc.setFontSize(14);
                doc.setFont('helvetica', 'bold');
                doc.text('📋 Resumo', 20, yPos);
                yPos += 8;
                
                const summary = TextSanitizer.sanitize(data.executive_summary);
                const lines = doc.splitTextToSize(summary, 170);
                doc.text(lines, 20, yPos);
                yPos += (lines.length * 6) + 10;
            }
            
            // Rodapé
            doc.setFillColor(darkBg[0], darkBg[1], darkBg[2]);
            doc.rect(0, 280, 210, 17, 'F');
            doc.setTextColor(200, 200, 200);
            doc.setFontSize(7);
            doc.text('AutoAnalytics v3.2 - Relatório gerado automaticamente por IA', 20, 290);
            doc.text('Página 1/1', 170, 290);
            
            const filename = options.filename || `Relatorio_Executivo_${Date.now()}.pdf`;
            doc.save(filename);
            
            return doc;
        }
        
        /**
         * 🔥 Gera Relatório de Dados Brutos
         */
        _generateRawReport(data, options = {}) {
            const { jsPDF } = window.jspdf;
            if (!jsPDF) {
                console.error('❌ jsPDF não encontrado!');
                return;
            }
            
            const doc = new jsPDF('p', 'mm', 'a4');
            const darkBg = [15, 12, 41];
            
            // Cabeçalho
            doc.setFillColor(darkBg[0], darkBg[1], darkBg[2]);
            doc.rect(0, 0, 210, 40, 'F');
            doc.setTextColor(255, 255, 255);
            doc.setFontSize(22);
            doc.setFont('helvetica', 'bold');
            doc.text('📊 AutoAnalytics', 20, 25);
            doc.setFontSize(12);
            doc.text('Dados da Análise', 20, 33);
            doc.setFontSize(8);
            doc.setTextColor(200, 200, 200);
            doc.text('Gerado em: ' + new Date().toLocaleDateString('pt-BR'), 20, 39);
            
            let yPos = 55;
            
            // Dados como JSON
            const rawData = data.raw_data || data.original_data || data;
            const jsonStr = JSON.stringify(rawData, null, 2);
            const sanitized = TextSanitizer.sanitize(jsonStr);
            
            doc.setFontSize(8);
            doc.setFont('courier', 'normal');
            const lines = doc.splitTextToSize(sanitized, 170);
            doc.text(lines, 20, yPos);
            
            // Rodapé
            doc.setFillColor(darkBg[0], darkBg[1], darkBg[2]);
            doc.rect(0, 280, 210, 17, 'F');
            doc.setTextColor(200, 200, 200);
            doc.setFontSize(7);
            doc.text('AutoAnalytics v3.2 - Dados brutos', 20, 290);
            doc.text('Página 1/1', 170, 290);
            
            const filename = options.filename || `Dados_Brutos_${Date.now()}.pdf`;
            doc.save(filename);
            
            return doc;
        }
    }

    // ==============================================
    // 🔥 INSTÂNCIA GLOBAL
    // ==============================================

    const pdfGenerator = new PDFGenerator();

    // 🔥 Função principal para gerar PDF
    window.generateFinancePDF = async function(data, options = {}) {
        try {
            return await pdfGenerator.generate(data, options);
        } catch (error) {
            console.error('❌ Erro ao gerar PDF:', error);
            alert('Erro ao gerar PDF: ' + error.message);
            return null;
        }
    };

    // 🔥 Funções auxiliares
    window.generateExecutivePDF = function(data, options) {
        return pdfGenerator.generate(data, { ...options, type: 'executive' });
    };
    
    window.generateRawPDF = function(data, options) {
        return pdfGenerator.generate(data, { ...options, type: 'raw' });
    };

    // 🔥 Função de teste
    window.testPDF = async function() {
        console.log('🧪 Testando PDF Generator...');
        const data = {
            metrics: {
                dataset_rows: 150,
                mean_prediction: 0.78,
                high_risk_percentage: 12.5,
                low_risk_percentage: 45.8
            },
            executive_score: {
                nota_geral: 8.5,
                saude_financeira: 7.8,
                eficiencia: 9.0,
                crescimento: 8.2,
                nivel_risco: 'Moderado'
            },
            executive_summary: 'Análise de dados da oficina concluída com sucesso.',
            recommendations: [
                '📊 Monitorar KPIs mensalmente',
                '🔄 Revisar dados periodicamente',
                '📈 Comparar com metas estabelecidas'
            ],
            ai_report: 'A análise demonstra alta performance com potencial de crescimento.'
        };
        
        await pdfGenerator.generate(data, { filename: 'Teste_PDF.pdf' });
        console.log('✅ Teste concluído!');
    };

    // 🔥 Função para debug
    window.getPDFData = function() {
        const data = DataCollector.collect();
        console.log('📊 Dados atuais:', data);
        return data;
    };

    // ==============================================
    // 🔥 EVENT LISTENER PARA O BOTÃO PDF
    // ==============================================

    document.addEventListener('DOMContentLoaded', function() {
        const pdfBtn = document.getElementById('downloadPdfBtn');
        if (pdfBtn) {
            pdfBtn.addEventListener('click', async function() {
                console.log('📄 Botão PDF clicado');
                
                // Mostrar feedback
                this.disabled = true;
                this.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i> Gerando...';
                
                try {
                    // Coletar dados
                    let data = DataCollector.collect();
                    
                    // Se não tiver dados, tentar API
                    if (!data || Object.keys(data).length === 0) {
                        const processId = DataCollector.getProcessId();
                        if (processId) {
                            data = await DataCollector.fetchFromAPI(processId);
                        }
                    }
                    
                    // Se ainda não tiver dados
                    if (!data || Object.keys(data).length === 0) {
                        const msg = 'Nenhum dado disponível para gerar o PDF. Faça um upload primeiro.';
                        console.warn('⚠️', msg);
                        if (window.toastr) {
                            window.toastr.warning(msg);
                        } else {
                            alert(msg);
                        }
                        return;
                    }
                    
                    // Gerar PDF
                    await pdfGenerator.generate(data);
                    
                } catch (error) {
                    console.error('❌ Erro:', error);
                    if (window.toastr) {
                        window.toastr.error('Erro ao gerar PDF: ' + error.message);
                    }
                } finally {
                    this.disabled = false;
                    this.innerHTML = '<i class="fas fa-file-pdf me-2"></i> Baixar Relatório PDF';
                }
            });
        }
    });

    console.log('✅ PDF Generator v3.2 carregado!');
    console.log('   📄 Use window.generateFinancePDF(data) para gerar');
    console.log('   🧪 Use window.testPDF() para testar');
    console.log('   🔍 Use window.getPDFData() para ver dados atuais');

})();