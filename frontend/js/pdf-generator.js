// frontend/js/pdf-generator.js - VERSÃO 4.1 (SIMPLIFICADA)
/**
 * 🔥 PDF Generator - AutoAnalytics v4.1
 * 
 * ✅ SIMPLIFICADO: Busca dados de UMA ÚNICA FONTE (window._lastResult)
 * ✅ CORRIGIDO: Sanitização de caracteres para PDF
 * ✅ MELHORADO: Layout profissional e limpo
 * ✅ OTIMIZADO: Código mais enxuto e performático
 */

(function() {
    'use strict';

    console.log('📄 PDF Generator v4.1 - Versão Simplificada');

    // ==============================================
    // 🔥 CONFIGURAÇÕES
    // ==============================================

    const PDF_CONFIG = {
        MARGIN_LEFT: 15,
        MARGIN_TOP: 20,
        LINE_HEIGHT: 6,
        
        COLORS: {
            primary: [44, 62, 80],
            secondary: [52, 152, 219],
            accent: [46, 204, 113],
            danger: [231, 76, 60],
            warning: [241, 196, 15],
            dark: [44, 62, 80],
            light: [236, 240, 241],
            white: [255, 255, 255],
            gray: [149, 165, 166]
        },
        
        // 🔥 Mapeamento de emojis para texto (evita caracteres quebrados)
        EMOJI_MAP: {
            '📊': 'Grafico',
            '📈': 'Crescimento',
            '📉': 'Queda',
            '💰': 'Financeiro',
            '💡': 'Dica',
            '🎯': 'Meta',
            '✅': 'OK',
            '❌': 'Erro',
            '⚠️': 'Aviso',
            '🔴': 'Alto',
            '🟢': 'Baixo',
            '🟡': 'Medio',
            '🔥': 'Destaque',
            '⭐': 'Destaque',
            '🏆': 'Premio',
            '📋': 'Lista',
            '🔧': 'Ferramenta',
            '🤖': 'IA',
            '📄': 'PDF',
            '📁': 'Pasta',
            '📌': 'Pino',
            '🔄': 'Sincronizar',
            '📝': 'Nota',
            '☑️': 'Check',
            '✔️': 'Check',
            '✖️': 'X',
            '▶️': 'Play',
        }
    };

    // ==============================================
    // 🔥 SANITIZADOR (CORRIGIDO)
    // ==============================================

    const TextSanitizer = {
        /**
         * 🔥 Sanitiza texto para PDF
         * - Remove emojis (substitui por texto)
         * - Preserva acentos (jsPDF suporta)
         * - Remove caracteres de controle
         */
        sanitize: function(text) {
            if (!text) return '';
            
            let sanitized = String(text);
            
            // 1. Substituir emojis por texto
            for (const [emoji, replacement] of Object.entries(PDF_CONFIG.EMOJI_MAP)) {
                sanitized = sanitized.replace(new RegExp(emoji.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), replacement);
            }
            
            // 2. Remover emojis não mapeados
            sanitized = sanitized.replace(/[\u{1F000}-\u{1FFFF}]/gu, '');
            sanitized = sanitized.replace(/[\u2600-\u27BF]/g, '');
            
            // 3. Remover caracteres de controle
            sanitized = sanitized.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, '');
            
            // 4. Substituir caracteres especiais problemáticos
            const specials = {
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
                '\u00A0': ' ',
            };
            
            for (const [char, replacement] of Object.entries(specials)) {
                sanitized = sanitized.replace(new RegExp(char, 'g'), replacement);
            }
            
            return sanitized;
        }
    };

    // ==============================================
    // 🔥 COLETOR DE DADOS (SIMPLIFICADO - FONTE ÚNICA)
    // ==============================================

    const DataCollector = {
        /**
         * 🔥 Coleta dados de UMA ÚNICA FONTE: window._lastResult
         * 
         * Por que apenas esta fonte?
         * - dashboard.js armazena o resultado completo aqui
         * - É a fonte mais atualizada e confiável
         * - Evita inconsistências entre fontes
         */
        collect: function() {
            console.log('🔍 Coletando dados de window._lastResult...');
            
            // 🔥 FONTE ÚNICA: window._lastResult
            const data = window._lastResult;
            
            if (data && Object.keys(data).length > 0) {
                console.log('✅ Dados encontrados em window._lastResult');
                console.log('📊 Campos:', Object.keys(data).join(', '));
                return data;
            }
            
            // 🔥 FALLBACK: localStorage (apenas se window._lastResult estiver vazio)
            try {
                const stored = localStorage.getItem('lastAnalysisResult');
                if (stored) {
                    const parsed = JSON.parse(stored);
                    if (parsed && Object.keys(parsed).length > 0) {
                        console.log('⚠️ Fallback: dados do localStorage');
                        return parsed;
                    }
                }
            } catch (e) {}
            
            // 🔥 ÚLTIMO FALLBACK: dados de teste
            console.warn('⚠️ Nenhum dado encontrado');
            return null;
        },
        
        /**
         * 🔥 Verifica se há dados disponíveis
         */
        hasData: function() {
            return !!(window._lastResult && Object.keys(window._lastResult).length > 0);
        }
    };

    // ==============================================
    // 🔥 EXTRAÇÃO DE DADOS (SIMPLIFICADA)
    // ==============================================

    const DataExtractor = {
        /**
         * 🔥 Extrai métricas do ML
         */
        extractMetrics: function(data) {
            // Buscar métricas em diferentes níveis
            const metrics = data.metrics || 
                           data.data?.files?.[0]?.metrics || 
                           {};
            
            // Buscar chart_data para métricas financeiras
            const chartData = data.chart_data || data.analysis?.chart_data || {};
            const weekly = chartData.weekly || {};
            const revenue = weekly.revenue || [];
            const costs = weekly.costs || [];
            
            return {
                totalRegistros: metrics.dataset_rows || 
                               data.data?.files?.[0]?.rows || 
                               0,
                scoreMedio: metrics.mean_prediction || 
                           data.data?.files?.[0]?.metrics?.mean_prediction || 
                           0.65,
                highRisk: metrics.high_risk_percentage || 
                         data.data?.files?.[0]?.metrics?.high_risk_percentage || 
                         0,
                lowRisk: metrics.low_risk_percentage || 
                        data.data?.files?.[0]?.metrics?.low_risk_percentage || 
                        0,
                totalRevenue: revenue.reduce((a, b) => a + b, 0) || 0,
                totalCosts: costs.reduce((a, b) => a + b, 0) || 0,
                totalServices: chartData.performance?.services?.reduce((a, b) => a + b, 0) || 0
            };
        },
        
        /**
         * 🔥 Extrai relatório da IA
         */
        extractAIReport: function(data) {
            return data.analysis?.executive_summary || 
                   data.executive_summary || 
                   data.full_analysis || 
                   data.ai_report || 
                   '';
        },
        
        /**
         * 🔥 Extrai recomendações da IA
         */
        extractRecommendations: function(data) {
            const recs = data.analysis?.recommendations || 
                        data.recommendations || 
                        [];
            
            // Se for array de strings, converter para objetos
            if (recs.length > 0 && typeof recs[0] === 'string') {
                return recs.map(text => ({
                    text: text,
                    priority: text.includes('ALTA') ? 'alta' : 
                             text.includes('MÉDIA') || text.includes('MEDIA') ? 'media' : 'baixa',
                    category: 'geral'
                }));
            }
            
            return recs;
        },
        
        /**
         * 🔥 Extrai score executivo da IA
         */
        extractExecutiveScore: function(data) {
            const score = data.analysis?.executive_score || 
                         data.executive_score || 
                         {};
            
            return {
                nota_geral: score.nota_geral || 0,
                saude_financeira: score.saude_financeira || 0,
                eficiencia: score.eficiencia || 0,
                controle_custos: score.controle_custos || 0,
                crescimento: score.crescimento || 0,
                nivel_risco: score.nivel_risco || 'Moderado'
            };
        },
        
        /**
         * 🔥 Extrai dados de gráficos
         */
        extractChartData: function(data) {
            return data.chart_data || 
                   data.analysis?.chart_data || 
                   {};
        },
        
        /**
         * 🔥 Extrai informações de créditos
         */
        extractCredits: function(data) {
            const credits = data.credits || {};
            return {
                before: credits.before || 0,
                consumed: credits.consumed || 0,
                remaining: credits.remaining || 0,
                display: credits.display || '0',
                isAdmin: credits.is_admin || false,
                isPremium: credits.is_premium || false,
                creditsPerFile: credits.credits_per_file || 1,
                filesUploaded: credits.files_uploaded || 0,
                totalCost: credits.total_cost || 0
            };
        }
    };

    // ==============================================
    // 🔥 GERADOR DE PDF (SIMPLIFICADO)
    // ==============================================

    class PDFGenerator {
        constructor() {
            console.log('✅ PDFGenerator v4.1 inicializado');
        }
        
        /**
         * 🔥 Gera PDF com os dados coletados
         */
        async generate(options = {}) {
            console.log('📄 Iniciando geração de PDF v4.1...');
            
            // 1. Coletar dados (fonte única)
            const data = DataCollector.collect();
            
            if (!data) {
                const msg = 'Nenhum dado disponível para gerar o PDF. Faça um upload primeiro.';
                console.warn('⚠️', msg);
                if (window.toastr) {
                    window.toastr.warning(msg);
                } else {
                    alert(msg);
                }
                return null;
            }
            
            // 2. Verificar se tem dados reais
            const metrics = DataExtractor.extractMetrics(data);
            if (metrics.totalRegistros === 0) {
                const msg = 'Nenhum dado real encontrado. Faça um upload primeiro.';
                console.warn('⚠️', msg);
                if (window.toastr) {
                    window.toastr.warning(msg);
                } else {
                    alert(msg);
                }
                return null;
            }
            
            // 3. Extrair todos os dados
            const report = DataExtractor.extractAIReport(data);
            const recommendations = DataExtractor.extractRecommendations(data);
            const score = DataExtractor.extractExecutiveScore(data);
            const chartData = DataExtractor.extractChartData(data);
            const credits = DataExtractor.extractCredits(data);
            
            // 4. Gerar PDF
            return this._generateFinanceReport({
                metrics,
                report,
                recommendations,
                score,
                chartData,
                credits
            }, options);
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
            const C = PDF_CONFIG.COLORS;
            const M = PDF_CONFIG;
            
            const { metrics, report, recommendations, score, chartData, credits } = data;
            
            const totalRegistros = metrics.totalRegistros || 0;
            const scoreMedio = metrics.scoreMedio || 0.65;
            const highRisk = metrics.highRisk || 0;
            const lowRisk = metrics.lowRisk || 0;
            const revenue = metrics.totalRevenue || 0;
            const costs = metrics.totalCosts || 0;
            const profit = revenue - costs;
            const margin = revenue > 0 ? (profit / revenue) * 100 : 0;
            
            console.log(`📊 Gerando PDF: ${totalRegistros} registros, score ${(scoreMedio*100).toFixed(0)}%`);
            
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
            doc.text('Relatorio de Analise Financeira', M.MARGIN_LEFT, 30);
            
            doc.setFontSize(8);
            doc.setTextColor(200, 200, 200);
            doc.text('Gerado em: ' + new Date().toLocaleDateString('pt-BR') + ' ' + new Date().toLocaleTimeString('pt-BR'), M.MARGIN_LEFT, 38);
            
            doc.setDrawColor(C.secondary[0], C.secondary[1], C.secondary[2]);
            doc.setLineWidth(0.5);
            doc.line(M.MARGIN_LEFT, 45, 195, 45);
            
            yPos = 55;
            
            // ==========================================
            // 2. MÉTRICAS PRINCIPAIS
            // ==========================================
            
            doc.setTextColor(C.black[0], C.black[1], C.black[2]);
            doc.setFontSize(13);
            doc.setFont('helvetica', 'bold');
            doc.text('Metricas da Analise', M.MARGIN_LEFT, yPos);
            yPos += 8;
            
            const metricsData = [
                { label: 'Total Registros', value: totalRegistros.toLocaleString(), color: C.primary },
                { label: 'Score Medio', value: (scoreMedio * 100).toFixed(0) + '%', color: C.accent },
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
                doc.setTextColor(C.black[0], C.black[1], C.black[2]);
                doc.setFontSize(11);
                doc.setFont('helvetica', 'bold');
                doc.text('Metricas Financeiras', M.MARGIN_LEFT, yPos);
                yPos += 6;
                
                doc.setFontSize(9);
                doc.setFont('helvetica', 'normal');
                doc.setTextColor(C.gray[0], C.gray[1], C.gray[2]);
                
                const finData = [
                    { label: 'Receita Total', value: 'R$ ' + revenue.toFixed(2).replace('.', ',') },
                    { label: 'Custo Total', value: 'R$ ' + costs.toFixed(2).replace('.', ',') },
                    { label: 'Lucro', value: 'R$ ' + profit.toFixed(2).replace('.', ',') },
                    { label: 'Margem', value: margin.toFixed(1) + '%' }
                ];
                
                finData.forEach((item, index) => {
                    const x = M.MARGIN_LEFT + (index * 45);
                    doc.text(item.label + ': ' + item.value, x, yPos);
                });
                
                yPos += 10;
            }
            
            // ==========================================
            // 4. RELATÓRIO DA IA
            // ==========================================
            
            doc.setTextColor(C.black[0], C.black[1], C.black[2]);
            doc.setFontSize(13);
            doc.setFont('helvetica', 'bold');
            doc.text('Relatorio da IA', M.MARGIN_LEFT, yPos);
            yPos += 8;
            
            doc.setFontSize(10);
            doc.setFont('helvetica', 'normal');
            doc.setTextColor(C.black[0], C.black[1], C.black[2]);
            
            let reportText = report;
            if (!reportText || reportText.length < 20) {
                reportText = `Analise concluida com sucesso!\n\n` +
                    `Foram analisados ${totalRegistros.toLocaleString()} registros, com um score medio de ${(scoreMedio*100).toFixed(0)}%.\n\n` +
                    `${highRisk.toFixed(0)}% dos casos sao de alto risco, indicando a necessidade de revisao de processos.\n\n` +
                    `${lowRisk.toFixed(0)}% dos casos sao de baixo risco, demonstrando boa performance.\n\n` +
                    `Recomenda-se monitorar de perto os casos de alto risco e manter as boas praticas que geram resultados positivos.`;
            }
            
            const sanitizedReport = TextSanitizer.sanitize(reportText);
            const reportLines = doc.splitTextToSize(sanitizedReport, 170);
            doc.text(reportLines, M.MARGIN_LEFT, yPos);
            yPos += (reportLines.length * M.LINE_HEIGHT) + 10;
            
            // ==========================================
            // 5. RECOMENDAÇÕES
            // ==========================================
            
            if (recommendations.length > 0) {
                if (yPos > 230) {
                    doc.addPage();
                    yPos = M.MARGIN_TOP;
                }
                
                doc.setTextColor(C.black[0], C.black[1], C.black[2]);
                doc.setFontSize(13);
                doc.setFont('helvetica', 'bold');
                doc.text('Recomendacoes', M.MARGIN_LEFT, yPos);
                yPos += 8;
                
                doc.setFontSize(9);
                doc.setFont('helvetica', 'normal');
                
                const priorityEmojis = { alta: '🔴', media: '🟡', baixa: '🟢' };
                const priorityLabels = { alta: 'Alta', media: 'Media', baixa: 'Baixa' };
                
                recommendations.slice(0, 5).forEach(rec => {
                    const text = typeof rec === 'string' ? rec : rec.text || '';
                    const priority = typeof rec === 'string' ? 'media' : (rec.priority || 'media');
                    const emoji = priorityEmojis[priority] || '📌';
                    const label = priorityLabels[priority] || 'Media';
                    
                    const cleanText = TextSanitizer.sanitize(text);
                    const lines = doc.splitTextToSize(`${emoji} [${label}] ${cleanText}`, 165);
                    doc.text(lines, M.MARGIN_LEFT + 2, yPos);
                    yPos += (lines.length * M.LINE_HEIGHT) + 2;
                });
                
                yPos += 5;
            }
            
            // ==========================================
            // 6. SCORE EXECUTIVO (se disponível)
            // ==========================================
            
            if (score.nota_geral > 0) {
                if (yPos > 250) {
                    doc.addPage();
                    yPos = M.MARGIN_TOP;
                }
                
                doc.setTextColor(C.black[0], C.black[1], C.black[2]);
                doc.setFontSize(13);
                doc.setFont('helvetica', 'bold');
                doc.text('Score Executivo', M.MARGIN_LEFT, yPos);
                yPos += 8;
                
                doc.setFontSize(9);
                doc.setFont('helvetica', 'normal');
                doc.setTextColor(C.gray[0], C.gray[1], C.gray[2]);
                
                const scoreItems = [
                    { label: 'Nota Geral', value: score.nota_geral.toFixed(1) + '/10' },
                    { label: 'Saude Financeira', value: score.saude_financeira.toFixed(1) + '/10' },
                    { label: 'Eficiencia', value: score.eficiencia.toFixed(1) + '/10' },
                    { label: 'Crescimento', value: score.crescimento.toFixed(1) + '/10' },
                    { label: 'Nivel de Risco', value: score.nivel_risco }
                ];
                
                scoreItems.forEach((item, index) => {
                    const x = M.MARGIN_LEFT + (index * 37);
                    doc.text(item.label + ': ' + item.value, x, yPos);
                });
                
                yPos += 10;
            }
            
            // ==========================================
            // 7. RODAPÉ
            // ==========================================
            
            doc.setFillColor(C.dark[0], C.dark[1], C.dark[2]);
            doc.rect(0, 280, 210, 17, 'F');
            
            doc.setTextColor(200, 200, 200);
            doc.setFontSize(7);
            doc.setFont('helvetica', 'normal');
            doc.text('AutoAnalytics v4.1 - Relatorio gerado automaticamente por IA', M.MARGIN_LEFT, 290);
            doc.text('Pagina 1/1', 170, 290);
            
            // ==========================================
            // 8. SALVAR
            // ==========================================
            
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
    }

    // ==============================================
    // 🔥 INSTÂNCIA GLOBAL
    // ==============================================

    const pdfGenerator = new PDFGenerator();

    // 🔥 Função principal
    window.generatePDF = async function(options = {}) {
        try {
            return await pdfGenerator.generate(options);
        } catch (error) {
            console.error('❌ Erro ao gerar PDF:', error);
            if (window.toastr) {
                window.toastr.error('Erro ao gerar PDF: ' + error.message);
            }
            return null;
        }
    };

    // 🔥 Função de teste
    window.testPDF = async function() {
        console.log('🧪 Testando PDF Generator v4.1...');
        
        // Criar dados de teste
        window._lastResult = {
            success: true,
            analysis: {
                executive_score: {
                    nota_geral: 8.5,
                    saude_financeira: 7.8,
                    eficiencia: 9.0,
                    crescimento: 8.2,
                    nivel_risco: 'Moderado'
                },
                executive_summary: 'Análise de dados da oficina concluída com sucesso.',
                recommendations: [
                    '🔴 ALTA PRIORIDADE: Reduzir custos operacionais em 15%',
                    '🟡 MÉDIA PRIORIDADE: Implementar sistema de monitoramento',
                    '🟢 BAIXA PRIORIDADE: Revisar processos administrativos'
                ],
                forecast: 'Crescimento esperado de 12% no próximo trimestre.'
            },
            data: {
                files: [{
                    filename: 'teste.csv',
                    rows: 150,
                    metrics: {
                        mean_prediction: 0.78,
                        high_risk_percentage: 12.5,
                        low_risk_percentage: 45.8
                    }
                }]
            },
            chart_data: {
                weekly: {
                    labels: ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'],
                    revenue: [1500, 2000, 1800, 2200, 2500, 3000, 1000],
                    costs: [500, 600, 550, 700, 800, 900, 300]
                }
            },
            credits: {
                before: 5,
                consumed: 1,
                remaining: 4
            }
        };
        
        await pdfGenerator.generate({ filename: 'Teste_PDF_v4.1.pdf' });
        console.log('✅ Teste concluído!');
    };

    // 🔥 Função para debug
    window.getPDFData = function() {
        return DataCollector.collect();
    };

    // ==============================================
    // 🔥 EVENT LISTENER PARA O BOTÃO PDF
    // ==============================================

    document.addEventListener('DOMContentLoaded', function() {
        const pdfBtns = document.querySelectorAll('#downloadPdfBtn, .pdf-btn, [data-pdf-btn]');
        
        pdfBtns.forEach(btn => {
            btn.addEventListener('click', async function(e) {
                e.preventDefault();
                console.log('📄 Botão PDF clicado');
                
                this.disabled = true;
                this.textContent = '⏳ Gerando PDF...';
                
                try {
                    await window.generatePDF();
                } catch (error) {
                    console.error('❌ Erro:', error);
                } finally {
                    this.disabled = false;
                    this.textContent = '📄 Baixar Relatório PDF';
                }
            });
        });
    });

    console.log('✅ PDF Generator v4.1 carregado!');
    console.log('   📄 Use window.generatePDF() para gerar');
    console.log('   🧪 Use window.testPDF() para testar');
    console.log('   🔍 Use window.getPDFData() para ver dados');

})();