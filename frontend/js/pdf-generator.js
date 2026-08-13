// frontend/js/pdf-generator.js - VERSÃO 4.4 (FIX ENCODING DEFINITIVO)
/**
 * 🔥 PDF Generator - AutoAnalytics v4.4
 * 
 * ✅ CORREÇÃO v4.4:
 * - 🔥 REMOÇÃO COMPLETA de emojis e caracteres especiais para jsPDF
 * - 🔥 USO DE TEXTO PURO em todo o documento
 * - 🔥 SUBSTITUIÇÃO por texto descritivo
 * - 🔥 COMPATIBILIDADE TOTAL com fonte padrão jsPDF
 * - 🔥 TESTADO com caracteres problemáticos
 */

(function() {
    'use strict';

    console.log('📄 PDF Generator v4.4 - Encoding Fix');

    // ==============================================
    // 🔥 MAPA DE EMOJIS PARA TEXTO (COMPLETO)
    // ==============================================

    const EMOJI_TO_TEXT = {
        // Emojis comuns
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
        '🚀': 'Destaque',
        '📅': 'Data',
        '📑': 'Documento',
        '📤': 'Enviar',
        '📥': 'Receber',
        '💻': 'Computador',
        '🖥️': 'Monitor',
        '🖱️': 'Mouse',
        '⌨️': 'Teclado',
        '🖨️': 'Impressora',
        '☕': 'Cafe',
        '🍕': 'Pizza',
        '🍔': 'Hamburguer',
        '🌮': 'Taco',
        '🥗': 'Salada',
        '🍣': 'Sushi',
        '🍜': 'Ramen',
        '🍰': 'Bolo',
        '🎂': 'Bolo',
        '🍩': 'Donut',
        '🍪': 'Biscoito',
        '🧁': 'Cupcake',
        '🥤': 'Bebida',
        '🧃': 'Suco',
        '🧋': 'Boba',
        '🍵': 'Cha',
        '🍺': 'Cerveja',
        '🍷': 'Vinho',
        '🥂': 'Toast',
        '🥃': 'Whisky',
        '🧊': 'Gelo',
        '🍽️': 'Comida',
        '🥄': 'Colher',
        '🔪': 'Faca',
        '🏠': 'Casa',
        '🏢': 'Predio',
        '🏪': 'Loja',
        '🏫': 'Escola',
        '🏥': 'Hospital',
        '🏦': 'Banco',
        '🏭': 'Fabrica',
        '🏗️': 'Construcao',
        '🌆': 'Cidade',
        '🌃': 'Noite',
        '🌅': 'Nascer do sol',
        '🌄': 'Amanhecer',
        '🌇': 'Por do sol',
        '🎄': 'Natal',
        '🎅': 'Papai Noel',
        '🎃': 'Abobora',
        '🎆': 'Fogos',
        '🎇': 'Fogos',
        '🧨': 'Fogos',
        '✨': 'Brilho',
        '🌟': 'Estrela',
        '🌠': 'Estrela',
        '🌌': 'Galaxia',
        '🌍': 'Terra',
        '🌎': 'Terra',
        '🌏': 'Terra',
        '🌐': 'Internet',
        '🗺️': 'Mapa',
        '🧭': 'Bussola',
        '🧳': 'Bagagem',
        '🎒': 'Mochila',
        '👕': 'Camisa',
        '👖': 'Calca',
        '👗': 'Vestido',
        '👔': 'Gravata',
        '👠': 'Salto',
        '👞': 'Sapato',
        '👟': 'Tenis',
        '🧦': 'Meia',
        '🧢': 'Boné',
        '🎩': 'Cartola',
        '🧣': 'Cachecol',
        '🧤': 'Luva',
        '🧥': 'Casaco',
        '👚': 'Blusa',
        '👙': 'Biquini',
        '👘': 'Quimono',
        '🥻': 'Sari',
        '🩱': 'Maiô',
        '🩳': 'Short',
        '🩴': 'Chinelo',
        '👑': 'Coroa',
        '💍': 'Anel',
        '💎': 'Diamante',
        '🔮': 'Bola de cristal',
        '🎨': 'Arte',
        '🎭': 'Teatro',
        '🎪': 'Circo',
        '🎢': 'Montanha russa',
        '🎠': 'Carrossel',
        '🎡': 'Roda gigante',
        '🎨': 'Paleta',
        '🧵': 'Linha',
        '🧶': 'La',
        '🎲': 'Dado',
        '♟️': 'Peao',
        '🎯': 'Alvo',
        '🎳': 'Boliche',
        '🎮': 'Video game',
        '🕹️': 'Joystick',
        '🎰': 'Caça niqueis',
        '🎲': 'Dados',
        '♠️': 'Espadas',
        '♥️': 'Copas',
        '♦️': 'Ouros',
        '♣️': 'Paus',
        '🃏': 'Coringa',
        '🀄': 'Mahjong',
    };

    // ==============================================
    // 🔥 SANITIZADOR AVANÇADO v2
    // ==============================================

    const TextSanitizer = {
        /**
         * 🔥 SANITIZAÇÃO COMPLETA para jsPDF
         * Remove todos os caracteres que quebram o PDF
         */
        sanitize: function(text) {
            if (!text) return '';
            
            let sanitized = String(text);
            
            // 1. Substituir emojis por texto
            for (const [emoji, replacement] of Object.entries(EMOJI_TO_TEXT)) {
                sanitized = sanitized.replace(new RegExp(emoji.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), replacement);
            }
            
            // 2. Remover emojis não mapeados (incluindo todos os emojis Unicode)
            sanitized = sanitized.replace(/[\u{1F000}-\u{1FFFF}]/gu, '');
            sanitized = sanitized.replace(/[\u2600-\u27BF]/g, '');
            sanitized = sanitized.replace(/[\u{FE00}-\u{FEFF}]/gu, '');
            
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
                '≠': '!=',
                '≤': '<=',
                '≥': '>=',
                '∞': 'infinito',
                '∑': 'soma',
                '∏': 'produto',
                '√': 'raiz',
                '∂': 'derivada',
                '∆': 'delta',
                '∇': 'nabla',
                '∫': 'integral',
                '∮': 'integral',
                '∴': 'portanto',
                '∵': 'porque',
                '∝': 'proporcional',
                '∅': 'vazio',
                '∈': 'pertence',
                '∉': 'nao pertence',
                '⊂': 'subconjunto',
                '⊃': 'superconjunto',
                '⊆': 'subconjunto ou igual',
                '⊇': 'superconjunto ou igual',
                '∪': 'uniao',
                '∩': 'intersecao',
                '∀': 'para todo',
                '∃': 'existe',
                '∄': 'nao existe',
                '¬': 'negacao',
                '∧': 'e',
                '∨': 'ou',
                '⊕': 'ou exclusivo',
                '⊗': 'produto tensorial',
                '†': 'crucifixo',
                '‡': 'duplo crucifixo',
                '•': '*',
                '·': '.',
                '×': 'x',
                '÷': '/',
                '±': '+/-',
                '\u00A0': ' ',
                '\n': ' ',
                '\r': ' ',
                '\t': ' ',
            };
            
            for (const [char, replacement] of Object.entries(specials)) {
                sanitized = sanitized.replace(new RegExp(char, 'g'), replacement);
            }
            
            // 5. Remover múltiplos espaços
            sanitized = sanitized.replace(/\s+/g, ' ').trim();
            
            // 6. Remover qualquer caractere não ASCII que não seja letra, número ou pontuação básica
            sanitized = sanitized.replace(/[^a-zA-Z0-9À-ÿ\s\-_.:,;!?()\[\]{}<>"'\/*=+$%#@&]/g, '');
            
            return sanitized;
        },
        
        /**
         * 🔥 Sanitiza para uso em strings JS (evita quebras)
         */
        sanitizeForJS: function(text) {
            if (!text) return '';
            return text.replace(/[\\"']/g, '\\$&').replace(/\u0000/g, '');
        },
        
        /**
         * 🔥 Sanitiza títulos (removendo completamente emojis)
         */
        sanitizeTitle: function(text) {
            if (!text) return '';
            let clean = this.sanitize(text);
            // Remove qualquer caractere estranho que possa ter sobrado
            clean = clean.replace(/[^a-zA-Z0-9À-ÿ\s\-]/g, '');
            return clean.trim();
        }
    };

    // ==============================================
    // 🔥 GERADOR DE PDF V4.4
    // ==============================================

    class PDFGenerator {
        constructor() {
            console.log('✅ PDFGenerator v4.4 (Encoding Fix)');
        }
        
        async generate(options = {}) {
            console.log('📄 [PDF] Iniciando geração...');
            
            const data = this._collectData();
            
            if (!data) {
                const msg = 'Nenhum dado disponível para gerar o PDF. Faça um upload primeiro.';
                console.warn('⚠️', msg);
                if (window.toastr) window.toastr.warning(msg);
                else alert(msg);
                return null;
            }
            
            const metrics = this._extractMetrics(data);
            
            if (metrics.totalRegistros === 0) {
                const msg = 'Nenhum dado real encontrado. Faça um upload primeiro.';
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
        
        _extractMetrics(data) {
            const metrics = data.metrics || data.analysis?.metrics || data.result?.metrics || {};
            
            const rows = data.rows_processed || 
                        data.result?.rows_processed || 
                        data.total_rows || 0;
            
            const score = data.confidence_score || 
                         data.result?.confidence_score ||
                         metrics.mean_prediction || 0.65;
            
            const highRisk = data.high_risk || 
                            data.result?.high_risk ||
                            metrics.high_risk_percentage || 0;
            
            const lowRisk = data.low_risk || 
                           data.result?.low_risk ||
                           metrics.low_risk_percentage || 0;
            
            const chartData = this._extractChartData(data);
            const weekly = chartData.weekly || {};
            const revenue = weekly.revenue || [];
            const costs = weekly.costs || [];
            
            return {
                totalRegistros: rows,
                scoreMedio: score,
                highRisk: highRisk,
                lowRisk: lowRisk,
                totalRevenue: revenue.reduce((a, b) => a + b, 0) || 0,
                totalCosts: costs.reduce((a, b) => a + b, 0) || 0,
                totalServices: chartData.performance?.services?.reduce((a, b) => a + b, 0) || 0,
                chartData: chartData
            };
        }
        
        _extractChartData(data) {
            return data.chart_data || 
                   data.result?.chart_data || 
                   data.analysis?.chart_data || 
                   {};
        }
        
        _extractReport(data) {
            return data.executive_summary || 
                   data.result?.executive_summary || 
                   data.analysis?.executive_summary || 
                   data.full_analysis || 
                   '';
        }
        
        _extractRecommendations(data) {
            let recs = data.recommendations || 
                       data.result?.recommendations || 
                       data.analysis?.recommendations || 
                       [];
            
            if (recs.length === 0) return [];
            
            if (typeof recs[0] === 'string') {
                return recs.map(text => ({ text: text, priority: 'media' }));
            }
            
            return recs;
        }
        
        _extractScore(data) {
            return data.executive_score || 
                   data.result?.executive_score || 
                   data.analysis?.executive_score || 
                   { nota_geral: 0 };
        }
        
        _extractCredits(data) {
            return data.credits || 
                   data.result?.credits || 
                   { before: 0, consumed: 0, remaining: 0 };
        }
        
        _extractFilename(data) {
            return data.filename || 
                   data.result?.filename || 
                   data.analysis?.filename || 
                   'Analise';
        }
        
        _extractModel(data) {
            return data.model_used || 
                   data.result?.model_used || 
                   'AutoML';
        }
        
        _generateReport(metrics, data, options = {}) {
            const { jsPDF } = window.jspdf;
            if (!jsPDF) {
                console.error('❌ jsPDF não encontrado!');
                alert('Erro: Biblioteca jsPDF não carregada.');
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
            // 1. CABEÇALHO (SEM EMOJIS)
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
            doc.setTextColor(C.lightGray[0], C.lightGray[1], C.lightGray[2]);
            const now = new Date();
            const dateStr = now.toLocaleDateString('pt-BR') + ' ' + now.toLocaleTimeString('pt-BR');
            doc.text('Gerado em: ' + dateStr, M.MARGIN_LEFT, 38);
            doc.text('Arquivo: ' + filename, 120, 38);
            
            doc.setDrawColor(C.secondary[0], C.secondary[1], C.secondary[2]);
            doc.setLineWidth(0.5);
            doc.line(M.MARGIN_LEFT, 45, 195, 45);
            
            yPos = 55;
            
            // ==========================================
            // 2. METRICAS PRINCIPAIS (SEM EMOJIS)
            // ==========================================
            
            doc.setTextColor(C.dark[0], C.dark[1], C.dark[2]);
            doc.setFontSize(13);
            doc.setFont('helvetica', 'bold');
            doc.text('Metricas da Analise', M.MARGIN_LEFT, yPos);
            yPos += 8;
            
            const metricsData = [
                { label: 'Registros', value: totalRegistros.toLocaleString(), color: C.primary },
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
            // 3. METRICAS FINANCEIRAS
            // ==========================================
            
            if (revenue > 0 || costs > 0) {
                doc.setTextColor(C.dark[0], C.dark[1], C.dark[2]);
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
                
                const finColWidth = 45;
                finData.forEach((item, index) => {
                    const x = M.MARGIN_LEFT + (index * finColWidth);
                    doc.text(item.label + ': ' + item.value, x, yPos);
                });
                
                yPos += 10;
            }
            
            // ==========================================
            // 4. INFORMACOES TECNICAS
            // ==========================================
            
            doc.setTextColor(C.gray[0], C.gray[1], C.gray[2]);
            doc.setFontSize(7);
            doc.setFont('helvetica', 'normal');
            doc.text('Modelo: ' + modelUsed, M.MARGIN_LEFT, yPos);
            yPos += 8;
            
            // ==========================================
            // 5. RELATORIO DA IA (SEM EMOJIS)
            // ==========================================
            
            doc.setTextColor(C.dark[0], C.dark[1], C.dark[2]);
            doc.setFontSize(13);
            doc.setFont('helvetica', 'bold');
            doc.text('Relatorio da IA', M.MARGIN_LEFT, yPos);
            yPos += 8;
            
            doc.setFontSize(10);
            doc.setFont('helvetica', 'normal');
            doc.setTextColor(C.dark[0], C.dark[1], C.dark[2]);
            
            let reportText = report;
            if (!reportText || reportText.length < 20) {
                reportText = 'Analise concluida com sucesso.\n\n' +
                    'Foram analisados ' + totalRegistros.toLocaleString() + ' registros, com um score medio de ' + 
                    (scoreMedio*100).toFixed(0) + '%.\n\n' +
                    highRisk.toFixed(0) + '% dos casos sao de alto risco, indicando a necessidade de revisao de processos.\n\n' +
                    lowRisk.toFixed(0) + '% dos casos sao de baixo risco, demonstrando boa performance.\n\n' +
                    'Recomenda-se monitorar de perto os casos de alto risco e manter as boas praticas que geram resultados positivos.';
            }
            
            const reportLines = doc.splitTextToSize(reportText, 170);
            
            if (yPos + (reportLines.length * M.LINE_HEIGHT) > 250) {
                doc.addPage();
                yPos = M.MARGIN_TOP;
            }
            
            doc.text(reportLines, M.MARGIN_LEFT, yPos);
            yPos += (reportLines.length * M.LINE_HEIGHT) + 10;
            
            // ==========================================
            // 6. RECOMENDACOES (SEM EMOJIS)
            // ==========================================
            
            if (recommendations.length > 0) {
                if (yPos > 230) {
                    doc.addPage();
                    yPos = M.MARGIN_TOP;
                }
                
                doc.setTextColor(C.dark[0], C.dark[1], C.dark[2]);
                doc.setFontSize(13);
                doc.setFont('helvetica', 'bold');
                doc.text('Recomendacoes', M.MARGIN_LEFT, yPos);
                yPos += 8;
                
                doc.setFontSize(9);
                doc.setFont('helvetica', 'normal');
                
                const priorityLabels = { alta: 'Alta Prioridade', media: 'Media Prioridade', baixa: 'Baixa Prioridade' };
                
                recommendations.slice(0, 5).forEach((rec) => {
                    const text = TextSanitizer.sanitize(rec.text || rec);
                    const priority = rec.priority || 'media';
                    const label = priorityLabels[priority] || 'Media Prioridade';
                    
                    const lines = doc.splitTextToSize('[' + label + '] ' + text, 165);
                    
                    if (yPos + (lines.length * M.LINE_HEIGHT) + 5 > 270) {
                        doc.addPage();
                        yPos = M.MARGIN_TOP;
                    }
                    
                    doc.text(lines, M.MARGIN_LEFT + 2, yPos);
                    yPos += (lines.length * M.LINE_HEIGHT) + 3;
                });
                
                yPos += 5;
            }
            
            // ==========================================
            // 7. SCORE EXECUTIVO (SEM EMOJIS)
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
                    { label: 'Nota Geral', value: score.nota_geral.toFixed(1) + '/10' },
                    { label: 'Saude Financeira', value: (score.saude_financeira || 0).toFixed(1) + '/10' },
                    { label: 'Eficiencia', value: (score.eficiencia || 0).toFixed(1) + '/10' },
                    { label: 'Crescimento', value: (score.crescimento || 0).toFixed(1) + '/10' },
                    { label: 'Nivel de Risco', value: score.nivel_risco || 'Moderado' }
                ];
                
                const scoreColWidth = 37;
                scoreItems.forEach((item, index) => {
                    const x = M.MARGIN_LEFT + (index * scoreColWidth);
                    if (x + 30 < 195) {
                        doc.text(item.label + ': ' + item.value, x, yPos);
                    }
                });
                
                yPos += 10;
            }
            
            // ==========================================
            // 8. GRAFICO DE TENDENCIA (SEM EMOJIS)
            // ==========================================
            
            const weeklyData = chartData.weekly || {};
            const labels = weeklyData.labels || ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom'];
            const revenueData = weeklyData.revenue || [];
            
            if (revenueData.length > 0) {
                if (yPos > 240) {
                    doc.addPage();
                    yPos = M.MARGIN_TOP;
                }
                
                doc.setTextColor(C.dark[0], C.dark[1], C.dark[2]);
                doc.setFontSize(12);
                doc.setFont('helvetica', 'bold');
                doc.text('Tendencia Semanal', M.MARGIN_LEFT, yPos);
                yPos += 6;
                
                // Tabela de dados semanais
                doc.setFontSize(7);
                doc.setFont('helvetica', 'normal');
                
                // Cabeçalho
                doc.setFillColor(C.primary[0], C.primary[1], C.primary[2]);
                doc.rect(M.MARGIN_LEFT, yPos, 170, 5, 'F');
                doc.setTextColor(C.white[0], C.white[1], C.white[2]);
                doc.setFont('helvetica', 'bold');
                
                const colWidths = [20, 20, 20, 20, 20, 20, 20];
                let xPos = M.MARGIN_LEFT + 2;
                
                labels.forEach((label, i) => {
                    doc.text(label, xPos, yPos + 3.5);
                    xPos += colWidths[i] || 20;
                });
                
                yPos += 7;
                
                // Dados
                doc.setTextColor(C.dark[0], C.dark[1], C.dark[2]);
                doc.setFont('helvetica', 'normal');
                
                xPos = M.MARGIN_LEFT + 2;
                revenueData.forEach((val, i) => {
                    doc.text('R$ ' + (val || 0).toFixed(0), xPos, yPos + 3.5);
                    xPos += colWidths[i] || 20;
                });
                
                yPos += 10;
                
                // Grafico de barras simples
                const maxVal = Math.max(...revenueData, 1);
                const barWidth = 18;
                const maxHeight = 40;
                const chartStartX = M.MARGIN_LEFT + 5;
                const chartStartY = yPos + 5;
                
                doc.setFillColor(C.primary[0], C.primary[1], C.primary[2]);
                
                revenueData.forEach((val, i) => {
                    const height = (val / maxVal) * maxHeight;
                    const x = chartStartX + (i * (barWidth + 4));
                    const y = chartStartY + maxHeight - height;
                    
                    doc.setFillColor(C.primary[0], C.primary[1], C.primary[2]);
                    doc.rect(x, y, barWidth, height, 'F');
                    
                    doc.setTextColor(C.dark[0], C.dark[1], C.dark[2]);
                    doc.setFontSize(5);
                    doc.text('R$' + val.toFixed(0), x + 2, y - 2);
                });
                
                yPos += maxHeight + 15;
            }
            
            // ==========================================
            // 9. CREDITOS
            // ==========================================
            
            if (credits.consumed > 0 || credits.before > 0) {
                if (yPos > 270) {
                    doc.addPage();
                    yPos = M.MARGIN_TOP;
                }
                
                doc.setTextColor(C.gray[0], C.gray[1], C.gray[2]);
                doc.setFontSize(8);
                doc.setFont('helvetica', 'normal');
                doc.text(
                    'Creditos: ' + credits.before + ' -> ' + credits.consumed + ' consumido(s) -> ' + credits.remaining + ' restante(s)',
                    M.MARGIN_LEFT,
                    yPos
                );
                yPos += 8;
            }
            
            // ==========================================
            // 10. RODAPE
            // ==========================================
            
            doc.setFillColor(C.dark[0], C.dark[1], C.dark[2]);
            doc.rect(0, 280, 210, 17, 'F');
            
            doc.setTextColor(C.lightGray[0], C.lightGray[1], C.lightGray[2]);
            doc.setFontSize(7);
            doc.setFont('helvetica', 'normal');
            doc.text('AutoAnalytics v4.4 - Relatorio gerado automaticamente por IA', M.MARGIN_LEFT, 290);
            doc.text('Pagina 1/1', 170, 290);
            
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
    // 🔥 INSTANCIA GLOBAL
    // ==============================================

    const pdfGenerator = new PDFGenerator();

    // Expor funções globalmente
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

    window.testPDF = async function() {
        console.log('🧪 [PDF] Testando...');
        
        window._lastResult = {
            success: true,
            process_id: 42,
            filename: 'orcamentos_oficina_100_linhas.xlsx',
            rows_processed: 100,
            model_used: 'RandomForest',
            confidence_score: 0.78,
            executive_summary: 'Análise de dados da oficina concluída com sucesso. O negócio apresenta boa saúde financeira com margens consistentes de 35%.',
            
            chart_data: {
                weekly: {
                    labels: ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom'],
                    revenue: [897, 431, 632, 1035, 538, 776, 1031],
                    costs: [266, 768, 277, 354, 235, 425, 604]
                },
                performance: {
                    labels: ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom'],
                    services: [12, 15, 10, 18, 14, 8, 6]
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
                { priority: 'alta', text: 'Reduzir custos operacionais em 15%' },
                { priority: 'media', text: 'Implementar sistema de monitoramento de performance' },
                { priority: 'baixa', text: 'Revisar processos administrativos' }
            ],
            
            credits: {
                before: 5,
                consumed: 1,
                remaining: 4
            }
        };
        
        await window.generatePDF({ filename: 'Teste_PDF_v4.4.pdf' });
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

    console.log('✅ PDF Generator v4.4 carregado!');
    console.log('   📄 Use window.generatePDF() para gerar');
    console.log('   🧪 Use window.testPDF() para testar');
    console.log('   🔥 CORRECOES v4.4:');
    console.log('      ✅ Remocao completa de emojis');
    console.log('      ✅ Sanitizacao avancada');
    console.log('      ✅ Compatibilidade total com jsPDF');
    console.log('      ✅ Nao aparecem mais caracteres estranhos');

})();