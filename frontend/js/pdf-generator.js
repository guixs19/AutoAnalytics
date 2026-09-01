// frontend/js/pdf-generator.js - VERSÃO 5.0 (FIX COMPLETO)
/**
 * 🔥 PDF Generator - AutoAnalytics v5.0
 * 
 * ✅ CORREÇÃO v5.0:
 * - 🔥 CONVERSÃO COMPLETA para ASCII antes de qualquer operação
 * - 🔥 REMOÇÃO de todos os caracteres não-ASCII
 * - 🔥 SUBSTITUIÇÃO de letras acentuadas por equivalentes sem acento
 * - 🔥 GARANTIA que o PDF só recebe caracteres ASCII
 * - 🔥 COMPATIBILIDADE TOTAL com fonte padrão jsPDF
 */

(function() {
    'use strict';

    console.log('📄 PDF Generator v5.0 - ASCII Fix');

    // ==============================================
    // 🔥 MAPA DE ACENTUAÇÃO PARA ASCII
    // ==============================================

    const ACCENT_MAP = {
        // Acentos comuns
        'á': 'a', 'à': 'a', 'â': 'a', 'ã': 'a', 'ä': 'a', 'å': 'a',
        'Á': 'A', 'À': 'A', 'Â': 'A', 'Ã': 'A', 'Ä': 'A', 'Å': 'A',
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'É': 'E', 'È': 'E', 'Ê': 'E', 'Ë': 'E',
        'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
        'Í': 'I', 'Ì': 'I', 'Î': 'I', 'Ï': 'I',
        'ó': 'o', 'ò': 'o', 'ô': 'o', 'õ': 'o', 'ö': 'o', 'ø': 'o',
        'Ó': 'O', 'Ò': 'O', 'Ô': 'O', 'Õ': 'O', 'Ö': 'O', 'Ø': 'O',
        'ú': 'u', 'ù': 'u', 'û': 'u', 'ü': 'u',
        'Ú': 'U', 'Ù': 'U', 'Û': 'U', 'Ü': 'U',
        'ý': 'y', 'ÿ': 'y', 'Ý': 'Y', 'Ÿ': 'Y',
        'ç': 'c', 'Ç': 'C',
        'ñ': 'n', 'Ñ': 'N',
        'ß': 'ss',
        // Cedilha e outros
        'æ': 'ae', 'œ': 'oe',
        'Æ': 'AE', 'Œ': 'OE',
        'ð': 'd', 'Ð': 'D',
        'þ': 'th', 'Þ': 'TH',
    };

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
        '🧢': 'Bone',
        '🎩': 'Cartola',
        '🧣': 'Cachecol',
        '🧤': 'Luva',
        '🧥': 'Casaco',
        '👚': 'Blusa',
        '👙': 'Biquini',
        '👘': 'Quimono',
        '🥻': 'Sari',
        '🩱': 'Maio',
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
        '🧵': 'Linha',
        '🧶': 'La',
        '🎲': 'Dado',
        '♟️': 'Peao',
        '🎳': 'Boliche',
        '🎮': 'Video game',
        '🕹️': 'Joystick',
        '🎰': 'Caca niqueis',
        '♠️': 'Espadas',
        '♥️': 'Copas',
        '♦️': 'Ouros',
        '♣️': 'Paus',
        '🃏': 'Coringa',
        '🀄': 'Mahjong',
        // Ícones de status
        '⏳': 'Aguardando',
        '⏱️': 'Tempo',
        '⌛': 'Esgotado',
        '🔍': 'Buscar',
        '🔎': 'Buscar',
        '🛠️': 'Ferramenta',
        '⚙️': 'Configuracao',
        '📞': 'Telefone',
        '📧': 'Email',
        '📨': 'Email',
        '📩': 'Email',
        '📪': 'Email',
        '📫': 'Email',
        '📬': 'Email',
        '📭': 'Email',
        '📮': 'Email',
    };

    // ==============================================
    // 🔥 SANITIZADOR AVANÇADO v3 - FORÇA ASCII
    // ==============================================

    const TextSanitizer = {
        /**
         * 🔥 CONVERTE PARA ASCII - REMOVE TUDO QUE NÃO É ASCII
         * Esta é a função principal que resolve o problema
         */
        toAscii: function(text) {
            if (!text) return '';
            
            let result = String(text);
            
            // 1. Substituir emojis por texto
            for (const [emoji, replacement] of Object.entries(EMOJI_TO_TEXT)) {
                try {
                    result = result.replace(new RegExp(emoji.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), replacement);
                } catch (e) {
                    // Ignora emojis que não podem ser regex
                }
            }
            
            // 2. Remover todos os emojis não mapeados (Unicode > U+FFFF)
            result = result.replace(/[\u{1F000}-\u{1FFFF}]/gu, '');
            result = result.replace(/[\u2600-\u27BF]/g, '');
            result = result.replace(/[\u{FE00}-\u{FEFF}]/gu, '');
            
            // 3. Substituir caracteres acentuados por equivalentes ASCII
            for (const [accented, ascii] of Object.entries(ACCENT_MAP)) {
                result = result.replace(new RegExp(accented, 'g'), ascii);
            }
            
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
                '·': '.',
                '×': 'x',
                '÷': '/',
                '\u00A0': ' ',
                '\n': ' ',
                '\r': ' ',
                '\t': ' ',
            };
            
            for (const [char, replacement] of Object.entries(specials)) {
                try {
                    result = result.replace(new RegExp(char.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), replacement);
                } catch (e) {
                    // Ignora caracteres que não podem ser regex
                }
            }
            
            // 5. Remover múltiplos espaços
            result = result.replace(/\s+/g, ' ').trim();
            
            // 6. 🔥 FORÇA ASCII - Remove qualquer caractere que não seja ASCII imprimível
            // Isso é a chave para resolver o problema
            result = result.replace(/[^\x20-\x7E]/g, '');
            
            // 7. Garantir que não há caracteres de controle
            result = result.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, '');
            
            return result;
        },
        
        /**
         * 🔥 Sanitiza para uso direto no PDF
         */
        sanitize: function(text) {
            if (!text) return '';
            return this.toAscii(text);
        },
        
        /**
         * 🔥 Sanitiza títulos (versão mais agressiva)
         */
        sanitizeTitle: function(text) {
            if (!text) return '';
            let clean = this.toAscii(text);
            // Remove caracteres especiais que podem causar problemas
            clean = clean.replace(/[^a-zA-Z0-9\s\-_.]/g, '');
            return clean.trim();
        },
        
        /**
         * 🔥 Sanitiza números e valores
         */
        sanitizeNumber: function(value) {
            if (value === undefined || value === null) return '0';
            let str = String(value);
            // Mantém apenas números, pontos e vírgulas
            str = str.replace(/[^0-9.,]/g, '');
            // Remove vírgulas para evitar problemas
            str = str.replace(/,/g, '.');
            return str;
        }
    };

    // ==============================================
    // 🔥 GERADOR DE PDF V5.0
    // ==============================================

    class PDFGenerator {
        constructor() {
            console.log('✅ PDFGenerator v5.0 (ASCII Fix)');
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
            
            if (metrics.totalRegistros === 0) {
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
            // 🔥 Tenta extrair chart_data de múltiplas fontes
            let chartData = data?.result?.chart_data || 
                           data?.chart_data || 
                           data?.analysis?.chart_data || 
                           data?.data?.chart_data || 
                           {};
            
            // Se chartData não tem weekly, tenta construir
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
            
            // 🔥 EXTRAIR DADOS E SANITIZAR TUDO PARA ASCII
            const totalRegistros = metrics.totalRegistros || 0;
            const scoreMedio = metrics.scoreMedio || 0.65;
            const highRisk = metrics.highRisk || 0;
            const lowRisk = metrics.lowRisk || 0;
            const revenue = metrics.totalRevenue || 0;
            const costs = metrics.totalCosts || 0;
            const profit = revenue - costs;
            const margin = revenue > 0 ? (profit / revenue) * 100 : 0;
            
            // 🔥 SANITIZAR TODOS OS TEXTOS PARA ASCII
            const report = TextSanitizer.sanitize(this._extractReport(data));
            const recommendations = this._extractRecommendations(data);
            const score = this._extractScore(data);
            const chartData = metrics.chartData || {};
            const credits = this._extractCredits(data);
            const filename = TextSanitizer.sanitizeTitle(this._extractFilename(data));
            const modelUsed = TextSanitizer.sanitize(this._extractModel(data));
            
            let yPos = M.MARGIN_TOP;
            
            // ==========================================
            // 1. CABECALHO (SEM EMOJIS)
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
            // 🔥 SANITIZAR DATA
            const cleanDateStr = TextSanitizer.sanitize(dateStr);
            doc.text('Gerado em: ' + cleanDateStr, M.MARGIN_LEFT, 38);
            doc.text('Arquivo: ' + filename, 120, 38);
            
            doc.setDrawColor(C.secondary[0], C.secondary[1], C.secondary[2]);
            doc.setLineWidth(0.5);
            doc.line(M.MARGIN_LEFT, 45, 195, 45);
            
            yPos = 55;
            
            // ==========================================
            // 2. METRICAS PRINCIPAIS
            // ==========================================
            
            doc.setTextColor(C.dark[0], C.dark[1], C.dark[2]);
            doc.setFontSize(13);
            doc.setFont('helvetica', 'bold');
            doc.text('Metricas da Analise', M.MARGIN_LEFT, yPos);
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
                
                // 🔥 FORMATAR VALORES SEM VIRGULAS (só ASCII)
                const formatMoney = (val) => {
                    return 'R$ ' + val.toFixed(2).replace('.', ',');
                };
                
                const finData = [
                    { label: 'Receita Total', value: formatMoney(revenue) },
                    { label: 'Custo Total', value: formatMoney(costs) },
                    { label: 'Lucro', value: formatMoney(profit) },
                    { label: 'Margem', value: margin.toFixed(1) + '%' }
                ];
                
                const finColWidth = 45;
                finData.forEach((item, index) => {
                    const x = M.MARGIN_LEFT + (index * finColWidth);
                    const cleanLabel = TextSanitizer.sanitize(item.label);
                    const cleanValue = TextSanitizer.sanitize(item.value);
                    doc.text(cleanLabel + ': ' + cleanValue, x, yPos);
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
            // 5. RELATORIO DA IA
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
            
            // 🔥 SANITIZAR RELATORIO COMPLETO PARA ASCII
            reportText = TextSanitizer.sanitize(reportText);
            
            const reportLines = doc.splitTextToSize(reportText, 170);
            
            if (yPos + (reportLines.length * M.LINE_HEIGHT) > 250) {
                doc.addPage();
                yPos = M.MARGIN_TOP;
            }
            
            doc.text(reportLines, M.MARGIN_LEFT, yPos);
            yPos += (reportLines.length * M.LINE_HEIGHT) + 10;
            
            // ==========================================
            // 6. RECOMENDACOES
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
                    const rawText = rec.text || rec || '';
                    // 🔥 SANITIZAR CADA RECOMENDACAO
                    const text = TextSanitizer.sanitize(rawText);
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
                
                // 🔥 SANITIZAR VALORES
                const cleanNota = TextSanitizer.sanitizeNumber(score.nota_geral);
                const cleanSaude = TextSanitizer.sanitizeNumber(score.saude_financeira || 0);
                const cleanEficiencia = TextSanitizer.sanitizeNumber(score.eficiencia || 0);
                const cleanCrescimento = TextSanitizer.sanitizeNumber(score.crescimento || 0);
                const cleanNivelRisco = TextSanitizer.sanitize(score.nivel_risco || 'Moderado');
                
                const scoreItems = [
                    { label: 'Nota Geral', value: cleanNota + '/10' },
                    { label: 'Saude Financeira', value: cleanSaude + '/10' },
                    { label: 'Eficiencia', value: cleanEficiencia + '/10' },
                    { label: 'Crescimento', value: cleanCrescimento + '/10' },
                    { label: 'Nivel de Risco', value: cleanNivelRisco }
                ];
                
                const scoreColWidth = 37;
                scoreItems.forEach((item, index) => {
                    const x = M.MARGIN_LEFT + (index * scoreColWidth);
                    if (x + 30 < 195) {
                        const cleanLabel = TextSanitizer.sanitize(item.label);
                        doc.text(cleanLabel + ': ' + item.value, x, yPos);
                    }
                });
                
                yPos += 10;
            }
            
            // ==========================================
            // 8. GRAFICO DE TENDENCIA
            // ==========================================
            
            const weeklyData = chartData.weekly || {};
            const labels = weeklyData.labels || ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom'];
            const revenueData = weeklyData.revenue || [];
            
            // 🔥 SANITIZAR LABELS
            const cleanLabels = labels.map(l => TextSanitizer.sanitize(l));
            
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
                
                // Cabecalho
                doc.setFillColor(C.primary[0], C.primary[1], C.primary[2]);
                doc.rect(M.MARGIN_LEFT, yPos, 170, 5, 'F');
                doc.setTextColor(C.white[0], C.white[1], C.white[2]);
                doc.setFont('helvetica', 'bold');
                
                const colWidths = [20, 20, 20, 20, 20, 20, 20];
                let xPos = M.MARGIN_LEFT + 2;
                
                cleanLabels.forEach((label, i) => {
                    doc.text(label, xPos, yPos + 3.5);
                    xPos += colWidths[i] || 20;
                });
                
                yPos += 7;
                
                // Dados - Receita
                doc.setTextColor(C.dark[0], C.dark[1], C.dark[2]);
                doc.setFont('helvetica', 'normal');
                
                xPos = M.MARGIN_LEFT + 2;
                revenueData.forEach((val, i) => {
                    const cleanVal = 'R$ ' + (val || 0).toFixed(0);
                    doc.text(cleanVal, xPos, yPos + 3.5);
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
                    const cleanVal = 'R$' + val.toFixed(0);
                    doc.text(cleanVal, x + 2, y - 2);
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
                const creditsText = 'Creditos: ' + credits.before + ' -> ' + credits.consumed + ' consumido(s) -> ' + credits.remaining + ' restante(s)';
                doc.text(TextSanitizer.sanitize(creditsText), M.MARGIN_LEFT, yPos);
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
            doc.text('AutoAnalytics v5.0 - Relatorio gerado automaticamente por IA', M.MARGIN_LEFT, 290);
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

    // Expor funcoes globalmente
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
            executive_summary: 'Analise de dados da oficina concluida com sucesso. O negocio apresenta boa saude financeira com margens consistentes de 35%.',
            
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
        
        await window.generatePDF({ filename: 'Teste_PDF_v5.0.pdf' });
        console.log('✅ [PDF] Teste concluido!');
    };

    // ==============================================
    // 🔥 EVENT LISTENER
    // ==============================================

    document.addEventListener('DOMContentLoaded', function() {
        const pdfBtns = document.querySelectorAll('#downloadPdfBtn, .pdf-btn, [data-pdf-btn]');
        
        pdfBtns.forEach(btn => {
            btn.addEventListener('click', async function(e) {
                e.preventDefault();
                console.log('📄 [PDF] Botao clicado');
                
                const originalText = this.innerHTML;
                this.disabled = true;
                this.innerHTML = '⏳ Gerando PDF...';
                
                try {
                    await window.generatePDF();
                } catch (error) {
                    console.error('❌ [PDF] Erro:', error);
                } finally {
                    this.disabled = false;
                    this.innerHTML = originalText || '📄 Baixar Relatorio PDF';
                }
            });
        });
    });

    console.log('✅ PDF Generator v5.0 carregado!');
    console.log('   📄 Use window.generatePDF() para gerar');
    console.log('   🧪 Use window.testPDF() para testar');
    console.log('   🔥 CORRECOES v5.0:');
    console.log('      ✅ Conversao completa para ASCII');
    console.log('      ✅ Substituicao de acentos');
    console.log('      ✅ Remocao de todos os caracteres nao-ASCII');
    console.log('      ✅ PDFs 100% legiveis');

})();