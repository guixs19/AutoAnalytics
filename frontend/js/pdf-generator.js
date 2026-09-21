// frontend/js/pdf-generator.js - VERSÃO 8.0 (BLOB-FIRST + PREVIEW)
/**
 * 🔥 PDF Generator - AutoAnalytics v8.0
 * 
 * ✅ NOVIDADES v8.0:
 * - 🔥 generatePDFBlob(): retorna Blob SEM baixar (não bloqueia)
 * - 🔥 PDFPreview.renderFromBlob(): renderiza Blob já pronto
 * - 🔥 PDFPreview.download(): download instantâneo via Blob
 * - 🔥 Fluxo "PDF-first": PDF aparece antes da IA terminar
 * 
 * ✅ MANTIDO v7.0:
 * - "Ayla" substitui TODAS as menções a ML/modelo/IA
 * - Zoom, fullscreen, preview no iframe
 * 
 * ✅ MANTIDO v6.0:
 * - Extração correta de per_file_analysis
 * - Recomendações com "description"
 * - Créditos normalizados
 * - Acentos pt-BR mantidos
 * - Gráfico com eixo Y
 */

(function() {
    'use strict';

    console.log('📄 PDF Generator v8.0 - Blob-First + Preview + Ayla');

    // ==============================================
    // 🔥 SANITIZADOR (mantém acentos pt-BR)
    // ==============================================

    const TextSanitizer = {
        sanitize: function(text) {
            if (text === undefined || text === null) return '';
            
            let result = String(text);
            
            // Remove emojis (fora do BMP)
            result = result.replace(/[\u{1F000}-\u{1FFFF}]/gu, '');
            result = result.replace(/[\u{2600}-\u{27BF}]/gu, '');
            result = result.replace(/[\u{FE00}-\u{FEFF}]/gu, '');
            
            // Substitui símbolos tipográficos problemáticos
            const typographic = {
                '\u2026': '...', '\u2014': '-', '\u2013': '-',
                '\u2022': '*', '\u201C': '"', '\u201D': '"',
                '\u2018': "'", '\u2019': "'", '\u00A0': ' ',
                '\u20AC': 'EUR', '\u00A3': 'GBP', '\u00A5': 'JPY', '\u00B0': 'o',
            };
            for (const [char, rep] of Object.entries(typographic)) {
                result = result.split(char).join(rep);
            }
            
            // Remove caracteres de controle
            result = result.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, '');
            
            // Colapsa espaços
            result = result.replace(/\s+/g, ' ').trim();
            
            return result;
        },
        
        sanitizeTitle: function(text) {
            if (!text) return '';
            return this.sanitize(text);
        },
        
        sanitizeNumber: function(value) {
            if (value === undefined || value === null) return '0';
            const n = Number(value);
            return isNaN(n) ? '0' : String(n);
        }
    };

    // ==============================================
    // 🔥 GERADOR DE PDF V8.0
    // ==============================================

    class PDFGenerator {
        constructor() {
            console.log('✅ PDFGenerator v8.0');
        }
        
        async generate(options = {}) {
            console.log('📄 [PDF] Iniciando geracao...');
            
            const data = this._collectData();
            
            if (!data) {
                const msg = 'Nenhum dado disponivel para gerar o PDF. Faca um upload primeiro.';
                console.warn('⚠️', msg);
                if (window.toastr) window.toastr.warning(msg);
                else alert(msg);
                return null;
            }
            
            const metrics = this._extractMetrics(data);
            
            if (metrics.totalRegistros === 0 && metrics.totalRevenue === 0) {
                const msg = 'Nenhum dado real encontrado. Faca um upload primeiro.';
                console.warn('⚠️', msg);
                if (window.toastr) window.toastr.warning(msg);
                else alert(msg);
                return null;
            }
            
            console.log(`📊 [PDF] ${metrics.totalRegistros} registros, score ${(metrics.scoreMedio*100).toFixed(0)}%`);
            
            return this._generateReport(metrics, data, options);
        }
        
        // ==============================================
        // 🔥 NOVO v8.0: Gera Blob sem baixar
        // ==============================================
        
        /**
         * 🔥 Gera o PDF e retorna um Blob (SEM baixar, SEM bloquear)
         * Ideal para pré-visualização imediata
         */
        async generatePDFBlob(options = {}) {
            console.log('📦 [PDF Blob] Gerando Blob (sem download)...');
            
            const data = this._collectData();
            
            if (!data) {
                console.warn('⚠️ [PDF Blob] Sem dados');
                return null;
            }
            
            const metrics = this._extractMetrics(data);
            
            if (metrics.totalRegistros === 0 && metrics.totalRevenue === 0) {
                console.warn('⚠️ [PDF Blob] Sem dados reais');
                return null;
            }
            
            // 🔥 Gera o doc SEM salvar
            const doc = this._generateReport(metrics, data, {
                ...options,
                _returnDoc: true,
                _previewMode: true
            });
            
            if (!doc) return null;
            
            // 🔥 Retorna Blob (não URL ainda)
            const blob = doc.output('blob');
            console.log('✅ [PDF Blob] Gerado:', blob.size, 'bytes');
            
            // Guarda o doc para download direto
            if (window.PDFPreview) {
                window.PDFPreview._lastDoc = doc;
            }
            
            return blob;
        }
        
        _collectData() {
            let data = window._lastResult;
            if (data && Object.keys(data).length > 0) {
                console.log('✅ [PDF] Dados de window._lastResult');
                return data;
            }
            
            if (window.UploadSystem && typeof window.UploadSystem.getResult === 'function') {
                data = window.UploadSystem.getResult();
                if (data && Object.keys(data).length > 0) {
                    console.log('✅ [PDF] Dados do UploadSystem');
                    return data;
                }
            }
            
            try {
                const stored = localStorage.getItem('lastAnalysisResult');
                if (stored) {
                    data = JSON.parse(stored);
                    if (data && Object.keys(data).length > 0) {
                        console.log('✅ [PDF] Dados do localStorage');
                        return data;
                    }
                }
            } catch (e) {}
            
            console.warn('⚠️ [PDF] Nenhum dado encontrado');
            return null;
        }
        
        // ==============================================
        // 🔥 EXTRAÇÃO DE MÉTRICAS
        // ==============================================
        
        _extractMetrics(data) {
            const perFile = data.per_file_analysis || {};
            const firstFileKey = Object.keys(perFile)[0];
            const firstFile = firstFileKey ? perFile[firstFileKey] : null;
            const fileMetrics = firstFile?.metrics_extra || {};
            
            const metrics = data.metrics || 
                            data.analysis?.metrics || 
                            data.result?.metrics || 
                            fileMetrics || 
                            {};
            
            const rows = data.rows_processed || 
                         data.result?.rows_processed || 
                         data.total_rows || 
                         fileMetrics.rows ||
                         metrics.total_rows ||
                         (data.files && data.files[0]?.total_rows) ||
                         0;
            
            let score = data.confidence_score ?? 
                        data.result?.confidence_score ??
                        fileMetrics.avg_score ??
                        metrics.mean_prediction ?? 
                        0.65;
            
            if (score > 1) score = score / 100;
            
            let highRisk = data.high_risk ?? 
                           data.result?.high_risk ??
                           fileMetrics.high_pct ??
                           metrics.high_risk_percentage ?? 
                           0;
            let lowRisk = data.low_risk ?? 
                          data.result?.low_risk ??
                          fileMetrics.low_pct ??
                          metrics.low_risk_percentage ?? 
                          0;
            
            if (highRisk > 0 && highRisk <= 1) highRisk *= 100;
            if (lowRisk > 0 && lowRisk <= 1) lowRisk *= 100;
            
            const totalRevenue = data.total_revenue ?? 
                                 fileMetrics.revenue ??
                                 metrics.total_revenue ??
                                 (data.files && data.files[0]?.total_revenue) ??
                                 0;
            
            const totalCosts = data.total_costs ?? 
                               fileMetrics.cost ??
                               metrics.total_costs ??
                               (data.files && data.files[0]?.total_costs) ??
                               0;
            
            const chartData = this._extractChartData(data);
            
            console.log('📊 [PDF] Metrics extraídas:', {
                rows, score, highRisk, lowRisk, totalRevenue, totalCosts
            });
            
            return {
                totalRegistros: rows,
                scoreMedio: score,
                highRisk: highRisk,
                lowRisk: lowRisk,
                totalRevenue: totalRevenue,
                totalCosts: totalCosts,
                chartData: chartData
            };
        }
        
        _extractChartData(data) {
            let chartData = data?.result?.chart_data || 
                            data?.chart_data || 
                            data?.analysis?.chart_data || 
                            data?.data?.chart_data ||
                            data?.per_file_analysis?.[Object.keys(data.per_file_analysis || {})[0]]?.metrics_extra?.chart_data ||
                            {};
            
            if (!chartData.weekly && chartData.revenue) {
                chartData = {
                    weekly: {
                        labels: chartData.labels || ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom'],
                        revenue: chartData.revenue || [],
                        costs: chartData.costs || []
                    }
                };
            }
            
            return chartData;
        }
        
        _extractReport(data) {
            const perFile = data.per_file_analysis || {};
            const firstFileKey = Object.keys(perFile)[0];
            const firstFile = firstFileKey ? perFile[firstFileKey] : null;
            
            return data.executive_summary || 
                   data.result?.executive_summary || 
                   data.analysis?.executive_summary || 
                   firstFile?.summary ||
                   data.full_analysis || 
                   '';
        }
        
        _extractRecommendations(data) {
            const perFile = data.per_file_analysis || {};
            const firstFileKey = Object.keys(perFile)[0];
            const firstFile = firstFileKey ? perFile[firstFileKey] : null;
            
            let recs = data.recommendations || 
                       data.result?.recommendations || 
                       data.analysis?.recommendations || 
                       firstFile?.recommendations ||
                       [];
            
            if (!Array.isArray(recs) || recs.length === 0) return [];
            
            return recs.map(rec => {
                if (typeof rec === 'string') {
                    return { text: rec, priority: 'media' };
                }
                return {
                    text: rec.text || rec.description || rec.message || rec.title || '',
                    priority: rec.priority || 'media',
                    category: rec.category || '',
                };
            }).filter(r => r.text && r.text.length > 0);
        }
        
        _extractScore(data) {
            const perFile = data.per_file_analysis || {};
            const firstFileKey = Object.keys(perFile)[0];
            const firstFile = firstFileKey ? perFile[firstFileKey] : null;
            
            return data.executive_score || 
                   data.result?.executive_score || 
                   data.analysis?.executive_score || 
                   (firstFile?.score !== undefined ? { nota_geral: firstFile.score } : null) ||
                   { nota_geral: 0 };
        }
        
        _extractCredits(data) {
            const c = data.credits || 
                      data.result?.credits || 
                      data.analysis?.credits || 
                      {};
            
            const toNum = (v) => {
                const n = Number(v);
                return isNaN(n) ? 0 : n;
            };
            
            return {
                before:    toNum(c.before ?? c.before_analysis ?? c.inicio ?? c.initial ?? 0),
                consumed:  toNum(c.consumed ?? c.consumed_credits ?? c.usado ?? c.used ?? 0),
                remaining: toNum(c.remaining ?? c.remaining_credits ?? c.restante ?? c.left ?? 0),
            };
        }
        
        _extractFilename(data) {
            return data.filename || 
                   data.result?.filename || 
                   data.analysis?.filename || 
                   (data.files && data.files[0]?.filename) ||
                   'Analise';
        }
        
        // ==============================================
        // 🔥 GERAÇÃO DO RELATÓRIO
        // ==============================================
        
        _generateReport(metrics, data, options = {}) {
            const { jsPDF } = window.jspdf;
            if (!jsPDF) {
                console.error('❌ jsPDF nao encontrado!');
                alert('Erro: Biblioteca jsPDF nao carregada.');
                return;
            }
            
            const doc = new jsPDF('p', 'mm', 'a4');
            const M = { MARGIN_LEFT: 15, MARGIN_TOP: 20, LINE_HEIGHT: 6 };
            const C = {
                primary: [255, 107, 53],
                dark: [44, 62, 80],
                white: [255, 255, 255],
                gray: [149, 165, 166],
                light: [236, 240, 241],
                lightGray: [200, 200, 200],
                danger: [231, 76, 60],
                accent: [46, 204, 113],
                secondary: [52, 152, 219]
            };
            
            const totalRegistros = metrics.totalRegistros || 0;
            const scoreMedio = metrics.scoreMedio || 0.65;
            const highRisk = metrics.highRisk || 0;
            const lowRisk = metrics.lowRisk || 0;
            const revenue = metrics.totalRevenue || 0;
            const costs = metrics.totalCosts || 0;
            const profit = revenue - costs;
            const margin = revenue > 0 ? (profit / revenue) * 100 : 0;
            
            const report = TextSanitizer.sanitize(this._extractReport(data));
            const recommendations = this._extractRecommendations(data);
            const score = this._extractScore(data);
            const chartData = metrics.chartData || {};
            const credits = this._extractCredits(data);
            const filename = TextSanitizer.sanitizeTitle(this._extractFilename(data));
            
            let yPos = M.MARGIN_TOP;
            
            // ==========================================
            // 1. CABEÇALHO
            // ==========================================
            
            doc.setFillColor(C.dark[0], C.dark[1], C.dark[2]);
            doc.rect(0, 0, 210, 45, 'F');
            
            doc.setTextColor(C.white[0], C.white[1], C.white[2]);
            doc.setFontSize(22);
            doc.setFont('helvetica', 'bold');
            doc.text('Ayla Mechanic', M.MARGIN_LEFT, 20);
            
            doc.setFontSize(14);
            doc.setFont('helvetica', 'normal');
            doc.text('Relatório de Análise Financeira', M.MARGIN_LEFT, 30);
            
            doc.setFontSize(8);
            doc.setTextColor(C.lightGray[0], C.lightGray[1], C.lightGray[2]);
            const now = new Date();
            const dateStr = now.toLocaleDateString('pt-BR') + ' ' + now.toLocaleTimeString('pt-BR');
            doc.text('Gerado em: ' + TextSanitizer.sanitize(dateStr), M.MARGIN_LEFT, 38);
            doc.text('Arquivo: ' + filename, 120, 38);
            
            doc.setDrawColor(C.secondary[0], C.secondary[1], C.secondary[2]);
            doc.setLineWidth(0.5);
            doc.line(M.MARGIN_LEFT, 45, 195, 45);
            
            yPos = 55;
            
            // ==========================================
            // 2. MÉTRICAS PRINCIPAIS
            // ==========================================
            
            doc.setTextColor(C.dark[0], C.dark[1], C.dark[2]);
            doc.setFontSize(13);
            doc.setFont('helvetica', 'bold');
            doc.text('Métricas da Análise', M.MARGIN_LEFT, yPos);
            yPos += 8;
            
            const metricsData = [
                { label: 'Registros', value: String(totalRegistros), color: C.primary },
                { label: 'Score', value: (scoreMedio * 100).toFixed(0) + '%', color: C.accent },
                { label: 'Alto Risco', value: highRisk.toFixed(0) + '%', color: C.danger },
                { label: 'Baixo Risco', value: lowRisk.toFixed(0) + '%', color: C.accent }
            ];
            
            const colWidth = 42;
            const startX = M.MARGIN_LEFT;
            
            metricsData.forEach((item, index) => {
                const x = startX + (index * colWidth);
                
                doc.setFillColor(C.light[0], C.light[1], C.light[2]);
                doc.roundedRect(x, yPos, colWidth - 2, 28, 3, 3, 'F');
                
                doc.setDrawColor(item.color[0], item.color[1], item.color[2]);
                doc.setLineWidth(0.3);
                doc.roundedRect(x, yPos, colWidth - 2, 28, 3, 3, 'S');
                
                doc.setTextColor(C.gray[0], C.gray[1], C.gray[2]);
                doc.setFontSize(7);
                doc.setFont('helvetica', 'normal');
                doc.text(item.label, x + 3, yPos + 6);
                
                doc.setTextColor(item.color[0], item.color[1], item.color[2]);
                doc.setFontSize(14);
                doc.setFont('helvetica', 'bold');
                doc.text(String(item.value), x + 3, yPos + 22);
            });
            
            yPos += 38;
            
            // ==========================================
            // 3. MÉTRICAS FINANCEIRAS
            // ==========================================
            
            if (revenue > 0 || costs > 0) {
                doc.setTextColor(C.dark[0], C.dark[1], C.dark[2]);
                doc.setFontSize(11);
                doc.setFont('helvetica', 'bold');
                doc.text('Métricas Financeiras', M.MARGIN_LEFT, yPos);
                yPos += 6;
                
                doc.setFontSize(9);
                doc.setFont('helvetica', 'normal');
                
                const formatMoney = (val) => {
                    return 'R$ ' + Number(val).toLocaleString('pt-BR', {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2
                    });
                };
                
                const finData = [
                    { label: 'Receita Total', value: formatMoney(revenue) },
                    { label: 'Custo Total', value: formatMoney(costs) },
                    { label: 'Lucro', value: formatMoney(profit) },
                    { label: 'Margem', value: margin.toFixed(1).replace('.', ',') + '%' }
                ];
                
                const finColWidth = 90;
                finData.forEach((item, index) => {
                    const col = index % 2;
                    const row = Math.floor(index / 2);
                    const x = M.MARGIN_LEFT + (col * finColWidth);
                    const y = yPos + (row * 6);
                    
                    doc.setTextColor(C.gray[0], C.gray[1], C.gray[2]);
                    doc.text(item.label + ':', x, y);
                    
                    doc.setTextColor(C.dark[0], C.dark[1], C.dark[2]);
                    doc.setFont('helvetica', 'bold');
                    doc.text(item.value, x + 32, y);
                    doc.setFont('helvetica', 'normal');
                });
                
                yPos += 18;
            }
            
            // ==========================================
            // 4. INFO TÉCNICA (AGORA "AYLA", NÃO "MODELO ML")
            // ==========================================
            
            doc.setTextColor(C.gray[0], C.gray[1], C.gray[2]);
            doc.setFontSize(7);
            doc.setFont('helvetica', 'normal');
            doc.text('Análise realizada por: Ayla (IA da Ayla Mechanic)', M.MARGIN_LEFT, yPos);
            yPos += 8;
            
            // ==========================================
            // 5. RELATÓRIO DA AYLA
            // ==========================================
            
            doc.setTextColor(C.dark[0], C.dark[1], C.dark[2]);
            doc.setFontSize(13);
            doc.setFont('helvetica', 'bold');
            doc.text('Relatório da Ayla', M.MARGIN_LEFT, yPos);
            yPos += 8;
            
            doc.setFontSize(10);
            doc.setFont('helvetica', 'normal');
            doc.setTextColor(C.dark[0], C.dark[1], C.dark[2]);
            
            let reportText = report;
            if (!reportText || reportText.length < 20) {
                reportText = 'Análise concluída com sucesso pela Ayla.\n\n' +
                    'Foram analisados ' + totalRegistros.toLocaleString('pt-BR') + ' registros, com um score médio de ' + 
                    (scoreMedio*100).toFixed(0) + '%.\n\n' +
                    highRisk.toFixed(0) + '% dos casos são de alto risco, indicando a necessidade de revisão de processos.\n\n' +
                    lowRisk.toFixed(0) + '% dos casos são de baixo risco, demonstrando boa performance.\n\n' +
                    'Recomendo monitorar de perto os casos de alto risco e manter as boas práticas que geram resultados positivos.';
            }
            
            // 🔥 Substitui menções a "ML"/"IA"/"modelo" por "Ayla"
            reportText = reportText
                .replace(/\bML\b/g, 'Ayla')
                .replace(/\bml\b/g, 'Ayla')
                .replace(/modelo de machine learning/gi, 'Ayla')
                .replace(/machine learning/gi, 'Ayla')
                .replace(/\bmodelo preditivo\b/gi, 'Ayla')
                .replace(/\bmodelo\b/gi, 'Ayla')
                .replace(/\bIA\b/g, 'Ayla')
                .replace(/\bInteligência Artificial\b/gi, 'Ayla');
            
            reportText = TextSanitizer.sanitize(reportText);
            
            const reportLines = doc.splitTextToSize(reportText, 170);
            
            if (yPos + (reportLines.length * M.LINE_HEIGHT) > 250) {
                doc.addPage();
                yPos = M.MARGIN_TOP;
            }
            
            doc.text(reportLines, M.MARGIN_LEFT, yPos);
            yPos += (reportLines.length * M.LINE_HEIGHT) + 10;
            
            // ==========================================
            // 6. RECOMENDAÇÕES
            // ==========================================
            
            if (recommendations.length > 0) {
                if (yPos > 230) {
                    doc.addPage();
                    yPos = M.MARGIN_TOP;
                }
                
                doc.setTextColor(C.dark[0], C.dark[1], C.dark[2]);
                doc.setFontSize(13);
                doc.setFont('helvetica', 'bold');
                doc.text('Recomendações da Ayla', M.MARGIN_LEFT, yPos);
                yPos += 8;
                
                doc.setFontSize(9);
                doc.setFont('helvetica', 'normal');
                
                const priorityLabels = { 
                    alta: 'Alta Prioridade', 
                    media: 'Média Prioridade', 
                    baixa: 'Baixa Prioridade' 
                };
                
                recommendations.slice(0, 8).forEach((rec) => {
                    let text = TextSanitizer.sanitize(rec.text || '');
                    
                    // 🔥 Substitui "ML" por "Ayla" também nas recomendações
                    text = text
                        .replace(/\bML\b/g, 'Ayla')
                        .replace(/\bml\b/g, 'Ayla')
                        .replace(/machine learning/gi, 'Ayla')
                        .replace(/\bmodelo\b/gi, 'Ayla')
                        .replace(/\bIA\b/g, 'Ayla');
                    
                    const priority = rec.priority || 'media';
                    const label = priorityLabels[priority] || 'Média Prioridade';
                    
                    if (!text) return;
                    
                    const lines = doc.splitTextToSize('[' + label + '] ' + text, 165);
                    
                    if (yPos + (lines.length * M.LINE_HEIGHT) + 5 > 270) {
                        doc.addPage();
                        yPos = M.MARGIN_TOP;
                    }
                    
                    if (priority === 'alta') {
                        doc.setTextColor(C.danger[0], C.danger[1], C.danger[2]);
                    } else if (priority === 'media') {
                        doc.setTextColor(230, 126, 34);
                    } else {
                        doc.setTextColor(C.accent[0], C.accent[1], C.accent[2]);
                    }
                    
                    doc.text(lines, M.MARGIN_LEFT + 2, yPos);
                    yPos += (lines.length * M.LINE_HEIGHT) + 3;
                    
                    doc.setTextColor(C.dark[0], C.dark[1], C.dark[2]);
                });
                
                yPos += 5;
            }
            
            // ==========================================
            // 7. SCORE EXECUTIVO
            // ==========================================
            
            if (score.nota_geral > 0) {
                if (yPos > 250) {
                    doc.addPage();
                    yPos = M.MARGIN_TOP;
                }
                
                doc.setTextColor(C.dark[0], C.dark[1], C.dark[2]);
                doc.setFontSize(13);
                doc.setFont('helvetica', 'bold');
                doc.text('Score Executivo (análise da Ayla)', M.MARGIN_LEFT, yPos);
                yPos += 8;
                
                doc.setFontSize(9);
                doc.setFont('helvetica', 'normal');
                doc.setTextColor(C.gray[0], C.gray[1], C.gray[2]);
                
                const scoreItems = [
                    { label: 'Nota Geral', value: (score.nota_geral || 0) + '/10' },
                    { label: 'Saúde Financeira', value: (score.saude_financeira || 0) + '/10' },
                    { label: 'Eficiência', value: (score.eficiencia || 0) + '/10' },
                    { label: 'Crescimento', value: (score.crescimento || 0) + '/10' },
                    { label: 'Nível de Risco', value: score.nivel_risco || 'Moderado' }
                ];
                
                const scoreColWidth = 37;
                scoreItems.forEach((item, index) => {
                    const x = M.MARGIN_LEFT + (index * scoreColWidth);
                    if (x + 30 < 195) {
                        doc.text(TextSanitizer.sanitize(item.label) + ': ' + item.value, x, yPos);
                    }
                });
                
                yPos += 10;
            }
            
            // ==========================================
            // 8. GRÁFICO DE TENDÊNCIA SEMANAL
            // ==========================================
            
            const weeklyData = chartData.weekly || {};
            const labels = weeklyData.labels || ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'];
            const revenueData = weeklyData.revenue || [];
            
            const cleanLabels = labels.map(l => TextSanitizer.sanitize(l));
            
            if (revenueData.length > 0) {
                if (yPos > 210) {
                    doc.addPage();
                    yPos = M.MARGIN_TOP;
                }
                
                doc.setTextColor(C.dark[0], C.dark[1], C.dark[2]);
                doc.setFontSize(12);
                doc.setFont('helvetica', 'bold');
                doc.text('Tendência Semanal', M.MARGIN_LEFT, yPos);
                yPos += 6;
                
                doc.setFontSize(7);
                doc.setFont('helvetica', 'normal');
                
                doc.setFillColor(C.primary[0], C.primary[1], C.primary[2]);
                doc.rect(M.MARGIN_LEFT, yPos, 170, 5, 'F');
                doc.setTextColor(C.white[0], C.white[1], C.white[2]);
                doc.setFont('helvetica', 'bold');
                
                const colWidths = [24, 24, 24, 24, 24, 24, 24];
                let xPos = M.MARGIN_LEFT + 2;
                
                cleanLabels.forEach((label, i) => {
                    doc.text(label, xPos, yPos + 3.5);
                    xPos += colWidths[i] || 24;
                });
                
                yPos += 7;
                
                doc.setTextColor(C.dark[0], C.dark[1], C.dark[2]);
                doc.setFont('helvetica', 'normal');
                
                xPos = M.MARGIN_LEFT + 2;
                revenueData.forEach((val, i) => {
                    const cleanVal = 'R$ ' + Number(val || 0).toFixed(0);
                    doc.text(cleanVal, xPos, yPos + 3.5);
                    xPos += colWidths[i] || 24;
                });
                
                yPos += 10;
                
                const maxVal = Math.max(...revenueData, 1);
                const barWidth = 16;
                const barGap = 6;
                const maxHeight = 45;
                const chartStartX = M.MARGIN_LEFT + 12;
                const chartStartY = yPos + 5;
                
                doc.setDrawColor(220, 220, 220);
                doc.setLineWidth(0.2);
                for (let i = 0; i <= 4; i++) {
                    const gy = chartStartY + (maxHeight * i / 4);
                    doc.line(chartStartX - 2, gy, chartStartX + 7 * (barWidth + barGap), gy);
                    
                    doc.setTextColor(C.gray[0], C.gray[1], C.gray[2]);
                    doc.setFontSize(5);
                    const yVal = maxVal * (4 - i) / 4;
                    doc.text('R$' + yVal.toFixed(0), M.MARGIN_LEFT, gy + 1.5);
                }
                
                revenueData.forEach((val, i) => {
                    const height = Math.max(1, (val / maxVal) * maxHeight);
                    const x = chartStartX + (i * (barWidth + barGap));
                    const y = chartStartY + maxHeight - height;
                    
                    doc.setFillColor(C.primary[0], C.primary[1], C.primary[2]);
                    doc.rect(x, y, barWidth, height, 'F');
                    
                    doc.setTextColor(C.dark[0], C.dark[1], C.dark[2]);
                    doc.setFontSize(5);
                    const labelY = Math.max(y - 1.5, chartStartY - 2);
                    const cleanVal = 'R$' + Number(val).toFixed(0);
                    doc.text(cleanVal, x + 1, labelY);
                });
                
                doc.setDrawColor(150, 150, 150);
                doc.setLineWidth(0.3);
                doc.line(chartStartX - 2, chartStartY + maxHeight, 
                         chartStartX + 7 * (barWidth + barGap) - barGap, 
                         chartStartY + maxHeight);
                
                yPos += maxHeight + 15;
            }
            
            // ==========================================
            // 9. CRÉDITOS
            // ==========================================
            
            const hasCredits = credits.before > 0 || credits.consumed > 0 || credits.remaining > 0;
            
            if (hasCredits) {
                if (yPos > 270) {
                    doc.addPage();
                    yPos = M.MARGIN_TOP;
                }
                
                doc.setTextColor(C.gray[0], C.gray[1], C.gray[2]);
                doc.setFontSize(8);
                doc.setFont('helvetica', 'normal');
                const creditsText = `Créditos: ${credits.before} -> ${credits.consumed} consumido(s) -> ${credits.remaining} restante(s)`;
                doc.text(TextSanitizer.sanitize(creditsText), M.MARGIN_LEFT, yPos);
                yPos += 8;
            }
            
            // ==========================================
            // 10. RODAPÉ
            // ==========================================
            
            const pageCount = doc.internal.getNumberOfPages();
            for (let i = 1; i <= pageCount; i++) {
                doc.setPage(i);
                doc.setFillColor(C.dark[0], C.dark[1], C.dark[2]);
                doc.rect(0, 280, 210, 17, 'F');
                
                doc.setTextColor(C.lightGray[0], C.lightGray[1], C.lightGray[2]);
                doc.setFontSize(7);
                doc.setFont('helvetica', 'normal');
                doc.text('Ayla Mechanic v8.0 - Relatório gerado automaticamente pela Ayla', M.MARGIN_LEFT, 290);
                doc.text(`Página ${i}/${pageCount}`, 180, 290);
            }
            
            // ==========================================
            // 11. RETORNAR OU SALVAR (preview mode)
            // ==========================================
            
            // 🔥 Se for modo preview, retorna o doc SEM salvar
            if (options._returnDoc || options._previewMode) {
                console.log('👁️ [PDF] Modo preview - retornando doc sem salvar');
                return doc;
            }
            
            try {
                const filename_ = options.filename || 'Relatorio_Ayla_' + Date.now() + '.pdf';
                doc.save(filename_);
                console.log('✅ [PDF] Gerado: ' + filename_);
                
                if (window.toastr) {
                    window.toastr.success('PDF gerado com sucesso!');
                }
                
                return doc;
            } catch (error) {
                console.error('❌ [PDF] Erro ao salvar:', error);
                if (window.toastr) {
                    window.toastr.error('Erro ao gerar PDF: ' + error.message);
                }
                return null;
            }
        }
    }

    // ==============================================
    // 🔥 INSTÂNCIA GLOBAL
    // ==============================================

    const pdfGenerator = new PDFGenerator();

    window.generatePDF = async function(options = {}) {
        try {
            return await pdfGenerator.generate(options);
        } catch (error) {
            console.error('❌ [PDF] Erro:', error);
            if (window.toastr) {
                window.toastr.error('Erro ao gerar PDF: ' + error.message);
            }
            return null;
        }
    };

    /**
     * 🔥 NOVO v8.0: Gera o PDF e retorna um Blob (sem baixar)
     * Uso: const blob = await window.generatePDFBlob();
     */
    window.generatePDFBlob = async function(options = {}) {
        try {
            return await pdfGenerator.generatePDFBlob(options);
        } catch (error) {
            console.error('❌ [PDF Blob] Erro:', error);
            if (window.toastr) {
                window.toastr.error('Erro ao gerar PDF: ' + error.message);
            }
            return null;
        }
    };

    // ==============================================
    // 🔥🔥🔥 PRÉ-VISUALIZAÇÃO DO PDF (v8.0)
    // ==============================================

    const PDFPreview = {
        _currentBlobUrl: null,
        _zoomLevel: 100,
        _lastDoc: null,
        _lastBlob: null,   // 🔥 NOVO: guarda o Blob para download instantâneo

        /**
         * Gera o PDF em memória e retorna o Blob URL (sem salvar)
         */
        async generatePreviewBlob(options = {}) {
            const data = pdfGenerator._collectData();
            if (!data) {
                console.warn('⚠️ [PDF Preview] Sem dados para gerar preview');
                return null;
            }

            const metrics = pdfGenerator._extractMetrics(data);
            if (metrics.totalRegistros === 0 && metrics.totalRevenue === 0) {
                console.warn('⚠️ [PDF Preview] Sem dados reais');
                return null;
            }

            // 🔥 Gera o PDF SEM salvar (passa flag _returnDoc)
            const doc = pdfGenerator._generateReport(metrics, data, {
                ...options,
                _previewMode: true,
                _returnDoc: true
            });

            if (!doc) return null;

            this._lastDoc = doc;

            // 🔥 Cria Blob URL em vez de salvar
            const blob = doc.output('blob');
            const blobUrl = URL.createObjectURL(blob);

            // 🔥 Guarda o Blob também
            this._lastBlob = blob;

            // Limpa URL anterior para evitar memory leak
            if (this._currentBlobUrl) {
                URL.revokeObjectURL(this._currentBlobUrl);
            }
            this._currentBlobUrl = blobUrl;

            console.log('✅ [PDF Preview] Blob gerado:', blobUrl);
            return blobUrl;
        },

        /**
         * Renderiza o PDF na div de preview (gera do zero)
         */
        async render() {
            const wrapper = document.getElementById('pdfPreviewWrapper');
            const frame = document.getElementById('pdfPreviewFrame');
            const loading = document.getElementById('pdfPreviewLoading');
            const fallback = document.getElementById('pdfPreviewFallback');

            if (!wrapper || !frame) {
                console.warn('⚠️ [PDF Preview] Elementos não encontrados no DOM');
                return;
            }

            // Mostra wrapper e loading
            wrapper.style.display = 'block';
            if (loading) loading.style.display = 'flex';
            if (fallback) fallback.style.display = 'none';

            try {
                const blobUrl = await this.generatePreviewBlob();

                if (!blobUrl) {
                    throw new Error('Falha ao gerar PDF em memória');
                }

                // Aguarda o iframe carregar
                frame.onload = () => {
                    if (loading) loading.style.display = 'none';
                    console.log('✅ [PDF Preview] Renderizado com sucesso no iframe');
                };

                frame.src = blobUrl;

                // Timeout de segurança (caso onload não dispare)
                setTimeout(() => {
                    if (loading) loading.style.display = 'none';
                }, 3000);

            } catch (error) {
                console.error('❌ [PDF Preview] Erro:', error);
                if (loading) loading.style.display = 'none';
                if (wrapper) wrapper.style.display = 'none';
                if (fallback) fallback.style.display = 'block';
            }
        },

        /**
         * 🔥 NOVO v8.0: Renderiza um Blob já existente (sem gerar de novo)
         * Ideal para quando o PDF já foi gerado em outro lugar
         */
        renderFromBlob(blob) {
            const wrapper = document.getElementById('pdfPreviewWrapper');
            const frame = document.getElementById('pdfPreviewFrame');
            const loading = document.getElementById('pdfPreviewLoading');
            const fallback = document.getElementById('pdfPreviewFallback');

            if (!wrapper || !frame) {
                console.warn('⚠️ [PDF Preview] Elementos não encontrados');
                return false;
            }

            if (!blob) {
                console.warn('⚠️ [PDF Preview] Blob inválido');
                return false;
            }

            console.log('👁️ [PDF Preview] Renderizando Blob:', blob.size, 'bytes');

            // Mostra wrapper
            wrapper.style.display = 'block';
            if (fallback) fallback.style.display = 'none';
            if (loading) loading.style.display = 'flex';

            // Limpa URL anterior (evita memory leak)
            if (this._currentBlobUrl) {
                URL.revokeObjectURL(this._currentBlobUrl);
                this._currentBlobUrl = null;
            }

            // 🔥 Guarda o Blob para download posterior
            this._lastBlob = blob;

            // 🔥 Cria URL do Blob e injeta no iframe
            this._currentBlobUrl = URL.createObjectURL(blob);

            frame.onload = () => {
                if (loading) loading.style.display = 'none';
                console.log('✅ [PDF Preview] Blob renderizado no iframe');
            };

            frame.src = this._currentBlobUrl;

            // Timeout de segurança
            setTimeout(() => {
                if (loading) loading.style.display = 'none';
            }, 2000);

            return true;
        },

        /**
         * Aplica zoom no iframe (via CSS transform)
         */
        applyZoom(level) {
            const frame = document.getElementById('pdfPreviewFrame');
            const zoomLabel = document.getElementById('pdfZoomLevel');

            if (!frame) return;

            this._zoomLevel = Math.max(50, Math.min(200, level));
            if (zoomLabel) zoomLabel.textContent = this._zoomLevel + '%';

            const scale = this._zoomLevel / 100;
            frame.style.transform = `scale(${scale})`;
            frame.style.transformOrigin = 'top left';
            frame.style.width = (100 / scale) + '%';
            frame.style.height = (100 / scale) + '%';
        },

        /**
         * 🔥 Download do PDF (usa Blob se disponível, senão o doc)
         */
        download() {
            // 🔥 Prioridade 1: Blob já gerado (download instantâneo)
            if (this._lastBlob) {
                const url = URL.createObjectURL(this._lastBlob);
                const link = document.createElement('a');
                link.href = url;
                link.download = 'Relatorio_Ayla_' + Date.now() + '.pdf';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                setTimeout(() => URL.revokeObjectURL(url), 1000);
                console.log('✅ [PDF Preview] Download via Blob (instantâneo)');
                return;
            }
            
            // 🔥 Prioridade 2: doc jsPDF em memória
            if (this._lastDoc) {
                const filename = 'Relatorio_Ayla_' + Date.now() + '.pdf';
                this._lastDoc.save(filename);
                console.log('✅ [PDF Preview] Download via doc');
                return;
            }
            
            // 🔥 Fallback: gera do zero e baixa
            console.warn('⚠️ [PDF Preview] Sem PDF em memória, gerando...');
            window.generatePDF();
        },

        /**
         * Abre em tela cheia
         */
        fullscreen() {
            const container = document.getElementById('pdfPreviewContainer');
            if (!container) return;

            if (container.requestFullscreen) {
                container.requestFullscreen();
            } else if (container.webkitRequestFullscreen) {
                container.webkitRequestFullscreen();
            }
        },

        /**
         * Limpa recursos
         */
        destroy() {
            if (this._currentBlobUrl) {
                URL.revokeObjectURL(this._currentBlobUrl);
                this._currentBlobUrl = null;
            }
            this._lastDoc = null;
            this._lastBlob = null;   // 🔥 Limpa também o Blob
        }
    };

    // ==============================================
    // 🔥 EXPOR GLOBALMENTE
    // ==============================================

    window.PDFPreview = PDFPreview;

    window.previewPDF = async function() {
        return await PDFPreview.render();
    };

    window.downloadLastPDF = function() {
        return PDFPreview.download();
    };

    // ==============================================
    // 🔥 DIAGNÓSTICO
    // ==============================================

    window.diagnosticarPDF = function() {
        const data = window._lastResult;
        if (!data) {
            console.warn('⚠️ window._lastResult está vazio!');
            return;
        }
        
        console.log('=== DIAGNÓSTICO PDF ===');
        console.log('1. Chaves raiz:', Object.keys(data));
        console.log('2. rows_processed:', data.rows_processed);
        console.log('3. confidence_score:', data.confidence_score);
        console.log('4. total_revenue:', data.total_revenue);
        console.log('5. total_costs:', data.total_costs);
        console.log('6. recommendations:', data.recommendations);
        console.log('7. credits:', data.credits);
        console.log('8. per_file_analysis:', data.per_file_analysis);
        
        const metrics = pdfGenerator._extractMetrics(data);
        console.log('=== MÉTRICAS EXTRAÍDAS ===');
        console.log(metrics);
        
        const recs = pdfGenerator._extractRecommendations(data);
        console.log('=== RECOMENDAÇÕES EXTRAÍDAS ===');
        console.log(recs);
        
        const credits = pdfGenerator._extractCredits(data);
        console.log('=== CRÉDITOS EXTRAÍDOS ===');
        console.log(credits);
        
        return { metrics, recs, credits };
    };

    window.testPDF = async function() {
        console.log('🧪 [PDF] Testando com dados de exemplo...');
        
        window._lastResult = {
            success: true,
            filename: 'oficina_ficticia_500_linhas.xlsx',
            rows_processed: 500,
            confidence_score: 0.65,
            total_revenue: 3751.73,
            total_costs: 2128.48,
            executive_summary: 'Análise concluída com sucesso. Foram analisados 500 registros, com um score médio de 65%.',
            
            chart_data: {
                weekly: {
                    labels: ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'],
                    revenue: [507, 478, 547, 565, 502, 644, 509],
                    costs: [266, 768, 277, 354, 235, 425, 604]
                }
            },
            
            executive_score: {
                nota_geral: 8.5,
                saude_financeira: 7.8,
                eficiencia: 9.0,
                crescimento: 8.2,
                nivel_risco: 'Moderado'
            },
            
            recommendations: [
                { priority: 'alta', description: 'Reduzir custos operacionais em 15%', category: 'financeiro' },
                { priority: 'media', description: 'Implementar sistema de monitoramento de performance', category: 'operacional' },
                { priority: 'baixa', description: 'Revisar processos administrativos', category: 'operacional' }
            ],
            
            credits: {
                before: 5,
                consumed: 1,
                remaining: 4
            }
        };
        
        // 🔥 Renderiza no preview (não salva)
        await PDFPreview.render();
        console.log('✅ [PDF] Teste concluído! Preview renderizado.');
    };

    // ==============================================
    // 🔥 EVENT LISTENERS
    // ==============================================

    document.addEventListener('DOMContentLoaded', function() {
        // 🔥 BOTÕES DE ZOOM / FULLSCREEN
        const zoomIn = document.getElementById('pdfZoomIn');
        const zoomOut = document.getElementById('pdfZoomOut');
        const fullscreen = document.getElementById('pdfFullscreen');

        if (zoomIn) {
            zoomIn.addEventListener('click', () => PDFPreview.applyZoom(PDFPreview._zoomLevel + 10));
        }
        if (zoomOut) {
            zoomOut.addEventListener('click', () => PDFPreview.applyZoom(PDFPreview._zoomLevel - 10));
        }
        if (fullscreen) {
            fullscreen.addEventListener('click', () => PDFPreview.fullscreen());
        }

        // 🔥 BOTÃO DE DOWNLOAD - usa o PDF já em memória se existir
        const downloadBtn = document.getElementById('downloadPdfBtn');
        if (downloadBtn) {
            // Remove listeners antigos para não duplicar
            const newBtn = downloadBtn.cloneNode(true);
            downloadBtn.parentNode.replaceChild(newBtn, downloadBtn);

            newBtn.addEventListener('click', async function(e) {
                e.preventDefault();
                console.log('📄 [PDF] Botão Download clicado');

                const originalText = this.innerHTML;
                this.disabled = true;
                this.innerHTML = '⏳ Baixando...';

                try {
                    // 🔥 Prioridade 1: Blob em memória (instantâneo)
                    if (PDFPreview._lastBlob || PDFPreview._lastDoc) {
                        PDFPreview.download();
                    } else {
                        // Fallback: gera do zero e baixa
                        console.log('⚠️ [PDF] Sem PDF em memória, gerando...');
                        await window.generatePDF();
                    }
                } catch (error) {
                    console.error('❌ [PDF] Erro no download:', error);
                } finally {
                    this.disabled = false;
                    this.innerHTML = originalText || '📄 Baixar Relatório PDF';
                }
            });
        }
    });

    console.log('✅ PDF Generator v8.0 carregado!');
    console.log('   📄 window.generatePDF()       - gera e BAIXA o PDF');
    console.log('   📦 window.generatePDFBlob()    - gera e retorna BLOB (sem baixar)');
    console.log('   👁️ window.previewPDF()         - gera e PRÉ-VISUALIZA');
    console.log('   ⚡ PDFPreview.download()       - baixa INSTANTÂNEO do Blob');
    console.log('   🧪 window.testPDF()           - testa com dados de exemplo');
    console.log('   🔍 window.diagnosticarPDF()   - debug dos dados');
    console.log('   🔥 NOVIDADES v8.0:');
    console.log('      ✅ Fluxo PDF-first: não bloqueia a IA');
    console.log('      ✅ Blob guardado em memória para download instantâneo');
    console.log('      ✅ renderFromBlob() para uso externo');

})();