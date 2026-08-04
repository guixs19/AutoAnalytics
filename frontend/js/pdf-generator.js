// frontend/js/pdf-generator.js - VERSÃO 3.0 (INTELIGENTE)
/**
 * 🔥 PDF Generator - AutoAnalytics v3.0
 * 
 * ✅ INTELIGÊNCIA INCORPORADA:
 *    - Detecta encoding automaticamente
 *    - Adapta sanitização ao conteúdo
 *    - Suporta múltiplas fontes de dados
 *    - Gera relatórios em diferentes formatos
 *    - Cache de sanitização para performance
 * 
 * ✅ SUPORTE A:
 *    - Dados da API (/api/...)
 *    - Dados do banco (analysis object)
 *    - Dados do dashboard (__APP_STATE)
 *    - Dados do upload (UploadSystem)
 * 
 * ✅ CORREÇÕES:
 *    - Encoding UTF-8 para PDF
 *    - Caracteres especiais (ç, ã, õ, etc)
 *    - Emojis e símbolos
 *    - Caracteres de controle
 */

(function() {
    'use strict';

    console.log('📄 PDF Generator v3.0 - Modo Inteligente');

    // ==============================================
    // 🔥 CONFIGURAÇÕES
    // ==============================================

    const PDF_CONFIG = {
        // Fontes de dados possíveis (ordem de prioridade)
        DATA_SOURCES: [
            'UploadSystem',
            '__dashboard',
            '__APP_STATE',
            '_lastResult'
        ],
        
        // Caracteres que precisam de sanitização
        SANITIZE_PATTERNS: {
            acentos: /[áàâãäéèêëíìîïóòôõöúùûüçñÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ]/g,
            emojis: /[\u{1F300}-\u{1FAFF}]/gu,
            especiais: /[™®©°±…—–•“‘”’]/g,
            controle: /[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g
        },
        
        // Mapeamento de caracteres
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
            // Emojis e símbolos comuns
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
            '✓': '[x]',
            '✔': '[OK]',
            '✗': '[x]',
            '✘': '[x]',
        }
    };

    // ==============================================
    // 🔥 CACHE DE SANITIZAÇÃO
    // ==============================================

    const SanitizeCache = {
        _cache: new Map(),
        _maxSize: 100,
        
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
        }
    };

    // ==============================================
    // 🔥 DETECTOR DE ENCODING
    // ==============================================

    const EncodingDetector = {
        /**
         * 🔥 Detecta o encoding do texto
         */
        detect: function(text) {
            if (!text) return 'unknown';
            
            // Verificar se tem caracteres UTF-8
            try {
                encodeURIComponent(text);
                // Se passar, pode ser UTF-8
            } catch (e) {
                return 'unknown';
            }
            
            // Verificar se tem caracteres acentuados
            const hasAccents = /[áàâãäéèêëíìîïóòôõöúùûüçñ]/i.test(text);
            if (hasAccents) {
                // Verificar se são UTF-8 válidos
                try {
                    const encoded = encodeURIComponent(text);
                    const decoded = decodeURIComponent(encoded);
                    if (decoded === text) {
                        return 'utf-8';
                    }
                } catch (e) {
                    return 'latin1';
                }
            }
            
            // Verificar caracteres especiais
            if (/[™®©°±…—–•]/g.test(text)) {
                return 'utf-8-special';
            }
            
            return 'ascii';
        },
        
        /**
         * 🔥 Detecta se o texto precisa de sanitização
         */
        needsSanitize: function(text) {
            if (!text) return false;
            return (
                /[áàâãäéèêëíìîïóòôõöúùûüçñ]/i.test(text) ||
                /[\u{1F300}-\u{1FAFF}]/u.test(text) ||
                /[™®©°±…—–•“‘”’]/g.test(text)
            );
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
            
            // 1. Detectar encoding
            const encoding = EncodingDetector.detect(sanitized);
            
            // 2. Se for ASCII puro, não precisa sanitizar
            if (encoding === 'ascii' && !options.force) {
                SanitizeCache.set(text, sanitized);
                return sanitized;
            }
            
            // 3. Substituir caracteres especiais
            for (const [char, replacement] of Object.entries(PDF_CONFIG.CHAR_MAP)) {
                sanitized = sanitized.replace(new RegExp(char, 'g'), replacement);
            }
            
            // 4. Remover caracteres de controle
            sanitized = sanitized.replace(PDF_CONFIG.SANITIZE_PATTERNS.controle, '');
            
            // 5. Remover emojis que não foram mapeados
            if (options.removeUnmappedEmojis !== false) {
                sanitized = sanitized.replace(/[\u{1F000}-\u{1FFFF}]/gu, '');
            }
            
            // 6. Garantir que é UTF-8 válido
            try {
                encodeURIComponent(sanitized);
            } catch (e) {
                // Se falhar, remover caracteres problemáticos
                sanitized = sanitized.replace(/[^\x20-\x7E\u00C0-\u00FF]/g, '');
            }
            
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
    // 🔥 COLETOR DE DADOS INTELIGENTE
    // ==============================================

    const DataCollector = {
        /**
         * 🔥 Coleta dados da melhor fonte disponível
         */
        collect: function() {
            const sources = [];
            
            // 1. UploadSystem (dados do upload atual)
            if (window.UploadSystem && typeof window.UploadSystem.getResult === 'function') {
                const data = window.UploadSystem.getResult();
                if (data && Object.keys(data).length > 0) {
                    sources.push({ source: 'UploadSystem', data: data });
                }
            }
            
            // 2. __dashboard (dados do dashboard)
            if (window.__dashboard) {
                try {
                    const state = window.__dashboard.state?.state || {};
                    const analyses = state.analyses?.active || [];
                    const lastAnalysis = analyses[0] || {};
                    const data = lastAnalysis.result || {};
                    if (data && Object.keys(data).length > 0) {
                        sources.push({ source: '__dashboard', data: data });
                    }
                } catch (e) {
                    // Ignora
                }
            }
            
            // 3. __APP_STATE (dados do estado global)
            if (window.__APP_STATE) {
                const data = {
                    user: window.__APP_STATE.user,
                    credits: window.__APP_STATE.credits,
                    isPremium: window.__APP_STATE.isPremium,
                    isAdmin: window.__APP_STATE.isAdmin,
                    lastAnalysis: window.__APP_STATE.lastAnalysis
                };
                if (data.lastAnalysis && Object.keys(data.lastAnalysis).length > 0) {
                    sources.push({ source: '__APP_STATE', data: data.lastAnalysis });
                }
            }
            
            // 4. _lastResult (fallback)
            if (window._lastResult && Object.keys(window._lastResult).length > 0) {
                sources.push({ source: '_lastResult', data: window._lastResult });
            }
            
            // 5. Tentar buscar da API (se tiver processId)
            const processId = this._getProcessId();
            if (processId) {
                sources.push({ 
                    source: 'API', 
                    data: { processId: processId, needsFetch: true }
                });
            }
            
            return sources;
        },
        
        /**
         * 🔥 Busca dados da API
         */
        fetchFromAPI: async function(processId) {
            try {
                const token = localStorage.getItem('access_token');
                if (!token) return null;
                
                const response = await fetch(`/api/analysis/result/${processId}`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                
                if (response.ok) {
                    const data = await response.json();
                    return data;
                }
            } catch (e) {
                console.warn('⚠️ Erro ao buscar dados da API:', e);
            }
            return null;
        },
        
        _getProcessId: function() {
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
    // 🔥 GERADOR DE PDF INTELIGENTE
    // ==============================================

    class PDFGenerator {
        constructor() {
            this._initialized = false;
            this._cache = new Map();
            this._templates = new Map();
            this._registerTemplates();
        }
        
        _registerTemplates() {
            // Template: Análise Financeira
            this._templates.set('finance', this._generateFinanceReport.bind(this));
            
            // Template: Resumo Executivo
            this._templates.set('executive', this._generateExecutiveReport.bind(this));
            
            // Template: Dados Brutos
            this._templates.set('raw', this._generateRawReport.bind(this));
        }
        
        /**
         * 🔥 Gera PDF inteligente
         */
        async generate(data = null, options = {}) {
            console.log('📄 Gerando PDF inteligente...');
            
            // 1. Coletar dados se não foram fornecidos
            let reportData = data;
            if (!reportData) {
                const sources = DataCollector.collect();
                console.log(`📊 Fontes encontradas: ${sources.length}`);
                
                // Usar a melhor fonte disponível
                for (const source of sources) {
                    if (source.data.needsFetch) {
                        // Buscar da API
                        const apiData = await DataCollector.fetchFromAPI(source.data.processId);
                        if (apiData) {
                            reportData = apiData;
                            break;
                        }
                    } else if (source.data && Object.keys(source.data).length > 0) {
                        reportData = source.data;
                        break;
                    }
                }
            }
            
            if (!reportData || Object.keys(reportData).length === 0) {
                throw new Error('Nenhum dado disponível para gerar o PDF');
            }
            
            // 2. Detectar tipo de relatório
            const reportType = this._detectReportType(reportData);
            console.log(`📄 Tipo de relatório: ${reportType}`);
            
            // 3. Sanitizar os dados
            const sanitizedData = TextSanitizer.sanitizeObject(reportData);
            
            // 4. Gerar o PDF
            const template = this._templates.get(reportType) || this._templates.get('finance');
            return template(sanitizedData, options);
        }
        
        /**
         * 🔥 Detecta o tipo de relatório baseado nos dados
         */
        _detectReportType(data) {
            if (data.executive_score || data.executive_summary) {
                return 'executive';
            }
            if (data.metrics || data.predictions || data.insights) {
                return 'finance';
            }
            if (data.raw_data || data.original_data) {
                return 'raw';
            }
            return 'finance';
        }
        
        /**
         * 🔥 Gera Relatório Financeiro
         */
        _generateFinanceReport(data, options = {}) {
            const { jsPDF } = window.jspdf;
            if (!jsPDF) {
                throw new Error('jsPDF não disponível');
            }
            
            const doc = new jsPDF('p', 'mm', 'a4');
            const primaryColor = [255, 107, 53];
            
            // ==========================================
            // CABEÇALHO
            // ==========================================
            this._addHeader(doc, 'Relatório de Análise Financeira');
            
            // ==========================================
            // MÉTRICAS
            // ==========================================
            let yPos = 55;
            
            const metrics = data.metrics || {};
            const predictions = data.predictions || [];
            const totalRegistros = metrics.dataset_rows || predictions.length || 0;
            const scoreMedio = metrics.mean_prediction || 0.65;
            const highRisk = metrics.high_risk_percentage || 0;
            const lowRisk = metrics.low_risk_percentage || 0;
            
            const metricsData = [
                { label: 'Total Registros', value: totalRegistros.toLocaleString() },
                { label: 'Score Médio', value: (scoreMedio * 100).toFixed(0) + '%' },
                { label: 'Alto Risco', value: highRisk.toFixed(0) + '%' },
                { label: 'Baixo Risco', value: lowRisk.toFixed(0) + '%' }
            ];
            
            this._addMetricsGrid(doc, metricsData, yPos);
            yPos += 38;
            
            // ==========================================
            // RELATÓRIO DA IA
            // ==========================================
            this._addSection(doc, '🤖 Relatório da IA', yPos);
            yPos += 8;
            
            const aiReport = data.ai_report || data.executive_summary || '';
            const reportText = aiReport || this._generateDefaultReport(totalRegistros, scoreMedio, highRisk, lowRisk);
            const sanitizedReport = TextSanitizer.sanitize(reportText);
            const lines = doc.splitTextToSize(sanitizedReport, 170);
            doc.text(lines, 20, yPos);
            yPos += (lines.length * 6) + 10;
            
            // ==========================================
            // RECOMENDAÇÕES
            // ==========================================
            const recommendations = data.recommendations || [];
            if (recommendations.length > 0) {
                this._addSection(doc, '🎯 Recomendações', yPos);
                yPos += 8;
                
                recommendations.slice(0, 4).forEach(rec => {
                    const safeRec = TextSanitizer.sanitize(rec);
                    const recLines = doc.splitTextToSize('• ' + safeRec, 160);
                    doc.text(recLines, 22, yPos);
                    yPos += (recLines.length * 6) + 2;
                });
            }
            
            // ==========================================
            // RODAPÉ
            // ==========================================
            this._addFooter(doc);
            
            // Salvar
            const filename = options.filename || `Relatorio_AutoAnalytics_${Date.now()}.pdf`;
            doc.save(filename);
            
            return doc;
        }
        
        /**
         * 🔥 Gera Relatório Executivo
         */
        _generateExecutiveReport(data, options = {}) {
            const { jsPDF } = window.jspdf;
            if (!jsPDF) {
                throw new Error('jsPDF não disponível');
            }
            
            const doc = new jsPDF('p', 'mm', 'a4');
            
            // Cabeçalho
            this._addHeader(doc, '📊 Relatório Executivo');
            
            let yPos = 55;
            
            // Score Executivo
            const score = data.executive_score || {};
            if (Object.keys(score).length > 0) {
                this._addSection(doc, '🏆 Score Executivo', yPos);
                yPos += 8;
                
                const scoreItems = [
                    { label: 'Nota Geral', value: score.nota_geral || 0 },
                    { label: 'Saúde Financeira', value: score.saude_financeira || 0 },
                    { label: 'Eficiência', value: score.eficiencia || 0 },
                    { label: 'Crescimento', value: score.crescimento || 0 },
                    { label: 'Nível de Risco', value: score.nivel_risco || 'Moderado' }
                ];
                
                scoreItems.forEach(item => {
                    const value = typeof item.value === 'number' ? item.value.toFixed(1) : item.value;
                    doc.setFontSize(10);
                    doc.setFont('helvetica', 'normal');
                    doc.text(`${item.label}: ${value}`, 20, yPos);
                    yPos += 6;
                });
                yPos += 4;
            }
            
            // Resumo Executivo
            if (data.executive_summary) {
                this._addSection(doc, '📋 Resumo', yPos);
                yPos += 8;
                
                const summary = TextSanitizer.sanitize(data.executive_summary);
                const lines = doc.splitTextToSize(summary, 170);
                doc.text(lines, 20, yPos);
                yPos += (lines.length * 6) + 10;
            }
            
            // Rodapé
            this._addFooter(doc);
            
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
                throw new Error('jsPDF não disponível');
            }
            
            const doc = new jsPDF('p', 'mm', 'a4');
            
            // Cabeçalho
            this._addHeader(doc, '📋 Dados da Análise');
            
            let yPos = 55;
            
            // Mostrar dados como JSON formatado
            const rawData = data.raw_data || data.original_data || data;
            const jsonStr = JSON.stringify(rawData, null, 2);
            const sanitized = TextSanitizer.sanitize(jsonStr);
            
            const lines = doc.splitTextToSize(sanitized, 170);
            doc.setFontSize(8);
            doc.setFont('courier', 'normal');
            doc.text(lines, 20, yPos);
            
            // Rodapé
            this._addFooter(doc);
            
            const filename = options.filename || `Dados_Brutos_${Date.now()}.pdf`;
            doc.save(filename);
            
            return doc;
        }
        
        // ==========================================
        // 🔥 HELPERS DE RENDERIZAÇÃO
        // ==========================================
        
        _addHeader(doc, title) {
            const darkBg = [15, 12, 41];
            
            doc.setFillColor(darkBg[0], darkBg[1], darkBg[2]);
            doc.rect(0, 0, 210, 40, 'F');
            
            doc.setTextColor(255, 255, 255);
            doc.setFontSize(22);
            doc.setFont('helvetica', 'bold');
            doc.text('📊 AutoAnalytics', 20, 25);
            
            doc.setFontSize(12);
            doc.setFont('helvetica', 'normal');
            doc.text(TextSanitizer.sanitize(title), 20, 33);
            
            doc.setFontSize(8);
            doc.setTextColor(200, 200, 200);
            const dateStr = new Date().toLocaleDateString('pt-BR');
            doc.text(TextSanitizer.sanitize(`Gerado em: ${dateStr}`), 20, 39);
        }
        
        _addMetricsGrid(doc, metrics, yPos) {
            const primaryColor = [255, 107, 53];
            const colWidth = 42;
            const startX = 20;
            
            metrics.forEach((item, index) => {
                const x = startX + (index * colWidth);
                
                doc.setFillColor(245, 245, 245);
                doc.roundedRect(x, yPos, colWidth - 2, 28, 3, 3, 'F');
                
                doc.setTextColor(100, 100, 100);
                doc.setFontSize(7);
                doc.setFont('helvetica', 'normal');
                doc.text(TextSanitizer.sanitize(item.label), x + 3, yPos + 6);
                
                doc.setTextColor(primaryColor[0], primaryColor[1], primaryColor[2]);
                doc.setFontSize(14);
                doc.setFont('helvetica', 'bold');
                doc.text(TextSanitizer.sanitize(item.value), x + 3, yPos + 22);
            });
        }
        
        _addSection(doc, title, yPos) {
            doc.setTextColor(50, 50, 50);
            doc.setFontSize(14);
            doc.setFont('helvetica', 'bold');
            doc.text(TextSanitizer.sanitize(title), 20, yPos);
        }
        
        _addFooter(doc) {
            const darkBg = [15, 12, 41];
            
            doc.setFillColor(darkBg[0], darkBg[1], darkBg[2]);
            doc.rect(0, 280, 210, 17, 'F');
            
            doc.setTextColor(200, 200, 200);
            doc.setFontSize(7);
            doc.setFont('helvetica', 'normal');
            doc.text('AutoAnalytics v3.0 - Relatório gerado automaticamente por IA', 20, 290);
            doc.text('Página 1/1', 170, 290);
        }
        
        _generateDefaultReport(total, score, highRisk, lowRisk) {
            const safeTotal = TextSanitizer.sanitize(total.toLocaleString());
            const safeScore = TextSanitizer.sanitize((score * 100).toFixed(0));
            const safeHigh = TextSanitizer.sanitize(highRisk.toFixed(0));
            const safeLow = TextSanitizer.sanitize(lowRisk.toFixed(0));
            
            return `Análise concluída com sucesso!\n\n` +
                   `Foram analisados ${safeTotal} registros, com um score médio de ${safeScore}%.\n\n` +
                   `${safeHigh}% dos casos são de alto risco, indicando a necessidade de revisão de processos.\n\n` +
                   `${safeLow}% dos casos são de baixo risco, demonstrando boa performance.\n\n` +
                   `Recomenda-se monitorar de perto os casos de alto risco e manter as boas práticas que geram resultados positivos.`;
        }
    }

    // ==============================================
    // 🔥 INSTÂNCIA GLOBAL
    // ==============================================

    const pdfGenerator = new PDFGenerator();

    // EXPORTAÇÕES
    window.PDFGenerator = pdfGenerator;
    window.generateFinancePDF = async function(data, options) {
        return await pdfGenerator.generate(data, options);
    };
    window.generateExecutivePDF = async function(data, options) {
        return await pdfGenerator.generate(data, { ...options, type: 'executive' });
    };
    window.generateRawPDF = async function(data, options) {
        return await pdfGenerator.generate(data, { ...options, type: 'raw' });
    };
    
    // 🔥 Função de teste para debug
    window.testPDF = async function() {
        const testData = {
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
            executive_summary: 'Análise de dados da oficina concluída com sucesso. A performance geral é excelente.',
            recommendations: [
                '📊 Monitorar KPIs mensalmente',
                '🔄 Revisar dados periodicamente',
                '📈 Comparar com metas estabelecidas'
            ],
            ai_report: 'A análise demonstra alta performance com potencial de crescimento.'
        };
        
        console.log('🧪 Testando PDF Generator...');
        await pdfGenerator.generate(testData, { filename: 'Teste_PDF.pdf' });
        console.log('✅ Teste concluído!');
    };

    console.log('✅ PDF Generator v3.0 (Inteligente) carregado!');
    console.log('   📄 Use window.generateFinancePDF(data) para gerar');
    console.log('   🔧 Use window.testPDF() para testar');

})();