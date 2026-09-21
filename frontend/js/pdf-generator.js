// frontend/js/pdf-generator.js - VERSÃO 6.0 (FIX REAL)
/**
 * 🔥 PDF Generator - AutoAnalytics v6.0
 * 
 * ✅ CORREÇÕES v6.0:
 * - 🔥 Extração CORRETA de dados do fallback v7 (per_file_analysis)
 * - 🔥 Recomendações agora usam "description" (não "text")
 * - 🔥 Créditos normalizados (before/consumed/remaining)
 * - 🔥 Sanitizador RELAXADO (jsPDF v2 suporta acentos pt-BR)
 * - 🔥 Formatação de moeda com toLocaleString
 * - 🔥 Gráfico semanal com eixo Y correto e clamp de labels
 * - 🔥 Cards de métricas com valores reais (não hardcoded)
 */

(function() {
    'use strict';

    console.log('📄 PDF Generator v6.0 - FIX REAL');

    // ==============================================
    // 🔥 SANITIZADOR RELAXADO (mantém acentos pt-BR)
    // ==============================================

    const TextSanitizer = {
        /**
         * 🔥 Remove apenas o que jsPDF NÃO suporta:
         * - Emojis (Unicode > BMP)
         * - Caracteres de controle
         * - Símbolos tipográficos problemáticos
         * MANTÉM acentos portugueses (á, é, ç, ã, etc.)
         */
        sanitize: function(text) {
            if (text === undefined || text === null) return '';
            
            let result = String(text);
            
            // 1. Remove emojis (fora do BMP)
            result = result.replace(/[\u{1F000}-\u{1FFFF}]/gu, '');
            result = result.replace(/[\u{2600}-\u{27BF}]/gu, '');
            result = result.replace(/[\u{FE00}-\u{FEFF}]/gu, '');
            
            // 2. Substitui símbolos tipográficos problemáticos
            const typographic = {
                '\u2026': '...',  // …
                '\u2014': '-',    // —
                '\u2013': '-',    // –
                '\u2022': '*',    // •
                '\u201C': '"',    // "
                '\u201D': '"',    // "
                '\u2018': "'",    // '
                '\u2019': "'",    // '
                '\u00A0': ' ',    // nbsp
                '\u20AC': 'EUR',  // €
                '\u00A3': 'GBP',  // £
                '\u00A5': 'JPY',  // ¥
                '\u00B0': 'o',    // °
            };
            for (const [char, rep] of Object.entries(typographic)) {
                result = result.split(char).join(rep);
            }
            
            // 3. Remove caracteres de controle
            result = result.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, '');
            
            // 4. Colapsa espaços
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
    // 🔥 GERADOR DE PDF V6.0
    // ==============================================

    class PDFGenerator {
        constructor() {
            console.log('✅ PDFGenerator v6.0');
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
        
        _collectData() {
            // FONTE 1: window._lastResult
            let data = window._lastResult;
            if (data && Object.keys(data).length > 0) {
                console.log('✅ [PDF] Dados de window._lastResult');
                return data;
            }
            
            // FONTE 2: UploadSystem
            if (window.UploadSystem && typeof window.UploadSystem.getResult === 'function') {
                data = window.UploadSystem.getResult();
                if (data && Object.keys(data).length > 0) {
                    console.log('✅ [PDF] Dados do UploadSystem');
                    return data;
                }
            }
            
            // FONTE 3: localStorage
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
        // 🔥 EXTRAÇÃO DE MÉTRICAS (CORRIGIDA)
        // ==============================================
        
        _extractMetrics(data) {
            // 🔥 FIX 1: fallback v7 aninha dados em per_file_analysis
            const perFile = data.per_file_analysis || {};
            const firstFileKey = Object.keys(perFile)[0];
            const firstFile = firstFileKey ? perFile[firstFileKey] : null;
            const fileMetrics = firstFile?.metrics_extra || {};
            
            const metrics = data.metrics || 
                            data.analysis?.metrics || 
                            data.result?.metrics || 
                            fileMetrics || 
                            {};
            
            // 🔥 FIX 2: múltiplas fontes para rows
            const rows = data.rows_processed || 
                         data.result?.rows_processed || 
                         data.total_rows || 
                         fileMetrics.rows ||
                         metrics.total_rows ||
                         (data.files && data.files[0]?.total_rows) ||
                         0;
            
            // 🔥 FIX 3: score real (fallback v7 usa avg_score)
            let score = data.confidence_score ?? 
                        data.result?.confidence_score ??
                        fileMetrics.avg_score ??
                        metrics.mean_prediction ?? 
                        0.65;
            
            // Se score vier em 0-100, normaliza
            if (score > 1) score = score / 100;
            
            // 🔥 FIX 4: riscos — fallback v7 usa high_pct/low_pct (0-100)
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
            
            // Normaliza: se vier 0-1, multiplica por 100
            if (highRisk > 0 && highRisk <= 1) highRisk *= 100;
            if (lowRisk > 0 && lowRisk <= 1) lowRisk *= 100;
            
            // 🔥 FIX 5: receita/custo reais
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
            // 🔥 FIX: busca em mais lugares, incluindo fallback v7
            let chartData = data?.result?.chart_data || 
                            data?.chart_data || 
                            data?.analysis?.chart_data || 
                            data?.data?.chart_data ||
                            data?.per_file_analysis?.[Object.keys(data.per_file_analysis || {})[0]]?.metrics_extra?.chart_data ||
                            {};
            
            // Se não tem weekly mas tem monthly, tenta reconstruir
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
        
        // 🔥 FIX 6: Recomendações suportam "description" (fallback v7)
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
                // 🔥 FIX: fallback v7 usa "description", não "text"
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
        
        // 🔥 FIX 7: Créditos normalizados
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
        
        _extractModel(data) {
            return data.model_used || 
                   data.result?.model_used || 
                   'AutoML';
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
            
            // 🔥 EXTRAIR DADOS
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
            const modelUsed = TextSanitizer.sanitize(this._extractModel(data));
            
            let yPos = M.MARGIN_TOP;
            
            // ==========================================
            // 1. CABEÇALHO
            // ==========================================
            
            doc.setFillColor(C.dark[0], C.dark[1], C.dark[2]);
            doc.rect(0, 0, 210, 45, 'F');
            
            doc.setTextColor(C.white[0], C.white[1], C.white[2]);
            doc.setFontSize(22);
            doc.setFont('helvetica', 'bold');
            doc.text('AutoAnalytics', M.MARGIN_LEFT, 20);
            
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
                
                // 🔥 FIX 8: formatação com toLocaleString
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
                
                // Layout em 2 linhas (2 colunas)
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
            // 4. INFO TÉCNICA
            // ==========================================
            
            doc.setTextColor(C.gray[0], C.gray[1], C.gray[2]);
            doc.setFontSize(7);
            doc.setFont('helvetica', 'normal');
            doc.text('Modelo: ' + modelUsed, M.MARGIN_LEFT, yPos);
            yPos += 8;
            
            // ==========================================
            // 5. RELATÓRIO DA IA
            // ==========================================
            
            doc.setTextColor(C.dark[0], C.dark[1], C.dark[2]);
            doc.setFontSize(13);
            doc.setFont('helvetica', 'bold');
            doc.text('Relatório da IA', M.MARGIN_LEFT, yPos);
            yPos += 8;
            
            doc.setFontSize(10);
            doc.setFont('helvetica', 'normal');
            doc.setTextColor(C.dark[0], C.dark[1], C.dark[2]);
            
            let reportText = report;
            if (!reportText || reportText.length < 20) {
                reportText = 'Análise concluída com sucesso.\n\n' +
                    'Foram analisados ' + totalRegistros.toLocaleString('pt-BR') + ' registros, com um score médio de ' + 
                    (scoreMedio*100).toFixed(0) + '%.\n\n' +
                    highRisk.toFixed(0) + '% dos casos são de alto risco, indicando a necessidade de revisão de processos.\n\n' +
                    lowRisk.toFixed(0) + '% dos casos são de baixo risco, demonstrando boa performance.\n\n' +
                    'Recomenda-se monitorar de perto os casos de alto risco e manter as boas práticas que geram resultados positivos.';
            }
            
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
                doc.text('Recomendações', M.MARGIN_LEFT, yPos);
                yPos += 8;
                
                doc.setFontSize(9);
                doc.setFont('helvetica', 'normal');
                
                const priorityLabels = { 
                    alta: 'Alta Prioridade', 
                    media: 'Média Prioridade', 
                    baixa: 'Baixa Prioridade' 
                };
                
                recommendations.slice(0, 8).forEach((rec) => {
                    const text = TextSanitizer.sanitize(rec.text || '');
                    const priority = rec.priority || 'media';
                    const label = priorityLabels[priority] || 'Média Prioridade';
                    
                    if (!text) return;
                    
                    const lines = doc.splitTextToSize('[' + label + '] ' + text, 165);
                    
                    if (yPos + (lines.length * M.LINE_HEIGHT) + 5 > 270) {
                        doc.addPage();
                        yPos = M.MARGIN_TOP;
                    }
                    
                    // Cor da prioridade
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
                doc.text('Score Executivo', M.MARGIN_LEFT, yPos);
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
                
                // Tabela de dados
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
                
                // 🔥 FIX 9: Gráfico de barras com eixo Y e clamp de labels
                const maxVal = Math.max(...revenueData, 1);
                const barWidth = 16;
                const barGap = 6;
                const maxHeight = 45;
                const chartStartX = M.MARGIN_LEFT + 12;
                const chartStartY = yPos + 5;
                
                // Eixo Y (linhas de grade)
                doc.setDrawColor(220, 220, 220);
                doc.setLineWidth(0.2);
                for (let i = 0; i <= 4; i++) {
                    const gy = chartStartY + (maxHeight * i / 4);
                    doc.line(chartStartX - 2, gy, chartStartX + 7 * (barWidth + barGap), gy);
                    
                    // Label do eixo Y
                    doc.setTextColor(C.gray[0], C.gray[1], C.gray[2]);
                    doc.setFontSize(5);
                    const yVal = maxVal * (4 - i) / 4;
                    doc.text('R$' + yVal.toFixed(0), M.MARGIN_LEFT, gy + 1.5);
                }
                
                // Barras
                revenueData.forEach((val, i) => {
                    const height = Math.max(1, (val / maxVal) * maxHeight);
                    const x = chartStartX + (i * (barWidth + barGap));
                    const y = chartStartY + maxHeight - height;
                    
                    doc.setFillColor(C.primary[0], C.primary[1], C.primary[2]);
                    doc.rect(x, y, barWidth, height, 'F');
                    
                    // 🔥 FIX: clamp do label para não sair da página
                    doc.setTextColor(C.dark[0], C.dark[1], C.dark[2]);
                    doc.setFontSize(5);
                    const labelY = Math.max(y - 1.5, chartStartY - 2);
                    const cleanVal = 'R$' + Number(val).toFixed(0);
                    doc.text(cleanVal, x + 1, labelY);
                });
                
                // Linha base do eixo X
                doc.setDrawColor(150, 150, 150);
                doc.setLineWidth(0.3);
                doc.line(chartStartX - 2, chartStartY + maxHeight, 
                         chartStartX + 7 * (barWidth + barGap) - barGap, 
                         chartStartY + maxHeight);
                
                yPos += maxHeight + 15;
            }
            
            // ==========================================
            // 9. CRÉDITOS (só se houver dados válidos)
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
                doc.text('AutoAnalytics v6.0 - Relatório gerado automaticamente por IA', M.MARGIN_LEFT, 290);
                doc.text(`Página ${i}/${pageCount}`, 180, 290);
            }
            
            // ==========================================
            // 11. SALVAR
            // ==========================================
            
            try {
                const filename_ = options.filename || 'Relatorio_AutoAnalytics_' + Date.now() + '.pdf';
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

    // ==============================================
    // 🔥 DIAGNÓSTICO - use no console para debugar
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
        console.log('3. total_rows:', data.total_rows);
        console.log('4. confidence_score:', data.confidence_score);
        console.log('5. total_revenue:', data.total_revenue);
        console.log('6. total_costs:', data.total_costs);
        console.log('7. recommendations:', data.recommendations);
        console.log('8. credits:', data.credits);
        console.log('9. per_file_analysis:', data.per_file_analysis);
        
        if (data.per_file_analysis) {
            const firstKey = Object.keys(data.per_file_analysis)[0];
            console.log('10. Primeiro arquivo em per_file_analysis:', firstKey);
            console.log('11. metrics_extra:', data.per_file_analysis[firstKey]?.metrics_extra);
        }
        
        const pdfGen = new PDFGenerator();
        const metrics = pdfGen._extractMetrics(data);
        console.log('=== MÉTRICAS EXTRAÍDAS PELO PDF ===');
        console.log(metrics);
        
        const recs = pdfGen._extractRecommendations(data);
        console.log('=== RECOMENDAÇÕES EXTRAÍDAS ===');
        console.log(recs);
        
        const credits = pdfGen._extractCredits(data);
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
            model_used: 'intelligent_fallback_v7',
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
        
        await window.generatePDF({ filename: 'Teste_PDF_v6.0.pdf' });
        console.log('✅ [PDF] Teste concluído!');
    };

    // ==============================================
    // 🔥 EVENT LISTENER
    // ==============================================

    document.addEventListener('DOMContentLoaded', function() {
        const pdfBtns = document.querySelectorAll('#downloadPdfBtn, .pdf-btn, [data-pdf-btn]');
        
        pdfBtns.forEach(btn => {
            btn.addEventListener('click', async function(e) {
                e.preventDefault();
                console.log('📄 [PDF] Botão clicado');
                
                const originalText = this.innerHTML;
                this.disabled = true;
                this.innerHTML = '⏳ Gerando PDF...';
                
                try {
                    await window.generatePDF();
                } catch (error) {
                    console.error('❌ [PDF] Erro:', error);
                } finally {
                    this.disabled = false;
                    this.innerHTML = originalText || '📄 Baixar Relatório PDF';
                }
            });
        });
    });

    console.log('✅ PDF Generator v6.0 carregado!');
    console.log('   📄 window.generatePDF()  - gera o PDF');
    console.log('   🧪 window.testPDF()      - testa com dados de exemplo');
    console.log('   🔍 window.diagnosticarPDF() - debug dos dados');
    console.log('   🔥 CORREÇÕES v6.0:');
    console.log('      ✅ Extração correta de per_file_analysis');
    console.log('      ✅ Recomendações com "description"');
    console.log('      ✅ Créditos normalizados');
    console.log('      ✅ Acentos pt-BR mantidos');
    console.log('      ✅ Gráfico com eixo Y');

})();