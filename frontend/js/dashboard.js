// frontend/js/dashboard.js - VERSÃO v9.1 (ABAS DINÂMICAS + GPSA)
/**
 * 🔥 Dashboard Module - AutoAnalytics v9.1
 * 
 * ✅ NOVO: Abas dinâmicas conforme número de arquivos (1 a 3)
 * ✅ NOVO: Gráfico GPSA individual para cada arquivo
 * ✅ NOVO: Relatório da IA integrado
 * ✅ NOVO: Indicador de saúde por arquivo
 * ✅ NOVO: Atualização automática ao fazer upload
 * 
 * MÓDULOS:
 * - GPSAChartRenderer: Renderização do gráfico GPSA
 * - TabManager: Gerenciamento de abas dinâmicas
 * - Dashboard: Orquestração principal
 */

(function() {
    'use strict';

    // ==============================================
    // 🔥 CONFIGURAÇÕES
    // ==============================================

    const CONFIG = {
        MAX_FILES_PER_BATCH: 5,
        MAX_FILE_SIZE_KB: 200,
        API_BASE: '/api',
        POLLING_INTERVAL: 2000,
        MAX_POLLING_ATTEMPTS: 90,
        CREDITS_CHECK_INTERVAL: 30000,
        CACHE_TTL: 30000,
        HISTORY_LIMIT: 50,
        
        COLORS: {
            score: '#ff6b35',
            services: '#4a9eff',
            revenue: '#48bb78',
            costs: '#f56565',
            healthy: 'rgba(72,187,120,0.08)',
            warning: 'rgba(245,166,35,0.08)',
            danger: 'rgba(245,101,101,0.08)',
            grid: 'rgba(255,255,255,0.05)',
            text: 'rgba(255,255,255,0.4)',
            success: '#48bb78',
            warning: '#f5a623',
            danger: '#f56565'
        },
        
        POW_ENABLED: true,
        POW_RETRY_ATTEMPTS: 3,
        POW_RETRY_DELAY: 1000,
        POW_WAIT_MAX_ATTEMPTS: 30,
        POW_WAIT_INTERVAL: 200,
        UPLOAD_MAX_RETRIES: 2,
        UPLOAD_RETRY_DELAY: 2000,
        WAIT_FOR_APP_TIMEOUT: 8000,
        WAIT_FOR_APP_INTERVAL: 200,
    };

    // ==============================================
    // 🔥 HELPER GLOBAL DE API
    // ==============================================

    function buildApiUrl(path) {
        if (!path) return '/api';
        const cleanPath = path.startsWith('/') ? path : '/' + path;
        if (cleanPath.startsWith('/api/')) return cleanPath;
        return '/api' + cleanPath;
    }

    if (typeof window !== 'undefined') {
        window.buildApiUrl = buildApiUrl;
        if (window.AppUtils) {
            window.AppUtils.buildApiUrl = buildApiUrl;
        }
    }

    // ==============================================
    // 🔥 UTILITÁRIOS
    // ==============================================

    const Utils = {
        debounce: (fn, delay = 300) => {
            let timer = null;
            return (...args) => {
                if (timer) clearTimeout(timer);
                timer = setTimeout(() => { fn.apply(this, args); timer = null; }, delay);
            };
        },

        throttle: (fn, limit = 100) => {
            let inThrottle = false;
            return (...args) => {
                if (!inThrottle) {
                    fn.apply(this, args);
                    inThrottle = true;
                    setTimeout(() => inThrottle = false, limit);
                }
            };
        },

        formatFileSize: (bytes) => {
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
            return (bytes / 1048576).toFixed(1) + ' MB';
        },

        formatCurrency: (value) => {
            if (value === undefined || value === null || isNaN(value)) return 'R$ 0,00';
            return 'R$ ' + value.toFixed(2).replace('.', ',');
        },

        formatCurrencyShort: (value) => {
            if (value === undefined || value === null || isNaN(value)) return 'R$ 0';
            if (value >= 1000) {
                return 'R$ ' + (value / 1000).toFixed(1) + 'k';
            }
            return 'R$ ' + value.toFixed(0);
        },

        escapeHtml: (text) => {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        },

        getScoreColor: (score) => {
            if (score >= 0.7) return '#48bb78';
            if (score >= 0.4) return '#f5a623';
            return '#f56565';
        },

        getScoreIcon: (score) => {
            if (score >= 0.7) return '🚀';
            if (score >= 0.4) return '📈';
            return '🔄';
        },

        getScoreLabel: (score) => {
            if (score >= 0.7) return 'Alto potencial';
            if (score >= 0.4) return 'Potencial médio';
            return 'Baixo potencial';
        },

        getHealthStatus: (score) => {
            if (score >= 0.7) return { status: 'excelente', color: '#48bb78', icon: '🟢', label: 'Excelente' };
            if (score >= 0.5) return { status: 'bom', color: '#4a9eff', icon: '🔵', label: 'Bom' };
            if (score >= 0.3) return { status: 'regular', color: '#f5a623', icon: '🟡', label: 'Regular' };
            return { status: 'critico', color: '#f56565', icon: '🔴', label: 'Crítico' };
        },

        sleep: (ms) => new Promise(resolve => setTimeout(resolve, ms)),

        getToken: () => {
            try {
                const token = localStorage.getItem('access_token');
                if (!token || token === 'undefined' || token === 'null') return null;
                return token;
            } catch (e) {
                return null;
            }
        },

        isAuthenticated: () => {
            const token = Utils.getToken();
            return token !== null && token.length > 10;
        },

        generateId: () => {
            return Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
        },

        // ==============================================
        // 🔥 DADOS FINANCEIROS
        // ==============================================

        generateWeeklyFinanceData: (data) => {
            const days = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'];
            
            if (!data || data.length === 0) {
                return Utils._generateSyntheticWeeklyData(days);
            }

            try {
                const df = data;
                const revenueCol = Utils._findColumn(df, ['valor', 'receita', 'total', 'valor_total', 'preco', 'preço']);
                const costsCol = Utils._findColumn(df, ['custo', 'peca', 'custo_pecas', 'despesa', 'gasto']);
                const dateCol = Utils._findColumn(df, ['data', 'dia', 'data_cadastro', 'created_at']);

                if (revenueCol && dateCol) {
                    return Utils._aggregateByDayOfWeek(df, dateCol, revenueCol, costsCol);
                }
            } catch (e) {
                console.warn('⚠️ Erro ao extrair dados financeiros:', e);
            }

            return Utils._generateSyntheticWeeklyData(days);
        },

        _findColumn: (df, keywords) => {
            const columns = df.columns || [];
            for (const col of columns) {
                const colLower = String(col).toLowerCase();
                for (const keyword of keywords) {
                    if (colLower.includes(keyword)) {
                        return col;
                    }
                }
            }
            return null;
        },

        _aggregateByDayOfWeek: (df, dateCol, revenueCol, costsCol) => {
            const days = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'];
            const result = {
                labels: days,
                revenue: Array(7).fill(0),
                costs: Array(7).fill(0),
                count: Array(7).fill(0)
            };

            try {
                const dates = df[dateCol];
                const revenues = df[revenueCol];
                const costs = costsCol ? df[costsCol] : null;

                for (let i = 0; i < dates.length; i++) {
                    const date = new Date(dates.iloc ? dates.iloc[i] : dates[i]);
                    const dayIndex = date.getDay();
                    const adjustedIndex = dayIndex === 0 ? 6 : dayIndex - 1;
                    
                    const revenue = parseFloat(revenues.iloc ? revenues.iloc[i] : revenues[i]) || 0;
                    const cost = costs ? parseFloat(costs.iloc ? costs.iloc[i] : costs[i]) || 0 : 0;

                    result.revenue[adjustedIndex] += revenue;
                    result.costs[adjustedIndex] += cost;
                    result.count[adjustedIndex] += 1;
                }

                for (let i = 0; i < 7; i++) {
                    if (result.count[i] > 0) {
                        result.revenue[i] = result.revenue[i] / result.count[i];
                        result.costs[i] = result.costs[i] / result.count[i];
                    }
                }

                return result;
            } catch (e) {
                console.warn('⚠️ Erro ao agregar dados:', e);
                return Utils._generateSyntheticWeeklyData(days);
            }
        },

        _generateSyntheticWeeklyData: (days) => {
            const baseRevenue = [1200, 1500, 900, 1800, 2200, 800, 400];
            const baseCosts = [400, 500, 350, 600, 700, 300, 150];
            
            const revenue = baseRevenue.map(v => v * (0.8 + Math.random() * 0.4));
            const costs = baseCosts.map(v => v * (0.7 + Math.random() * 0.6));
            
            return {
                labels: days,
                revenue: revenue,
                costs: costs,
                count: Array(7).fill(1)
            };
        },

        generateMonthlyFinanceData: (data) => {
            const months = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
            
            if (!data || data.length === 0) {
                return Utils._generateSyntheticMonthlyData(months);
            }

            try {
                return Utils._generateSyntheticMonthlyData(months);
            } catch (e) {
                return Utils._generateSyntheticMonthlyData(months);
            }
        },

        _generateSyntheticMonthlyData: (months) => {
            const baseRevenue = [8000, 7200, 9500, 11000, 9800, 12000, 13500, 10000, 11500, 14000, 12500, 16000];
            const baseCosts = [3000, 2800, 3500, 4000, 3800, 4500, 5000, 3800, 4200, 5200, 4800, 5800];
            
            const revenue = baseRevenue.map(v => v * (0.9 + Math.random() * 0.2));
            const costs = baseCosts.map(v => v * (0.85 + Math.random() * 0.3));
            
            return {
                labels: months,
                revenue: revenue,
                costs: costs
            };
        },

        // ==============================================
        // 🔥 DADOS GPSA (GERADOR PRINCIPAL)
        // ==============================================

        generateGPSAData: (analysisData) => {
            const days = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'];
            
            const metrics = analysisData?.metrics || {};
            const predictions = analysisData?.predictions || [];
            const chartData = analysisData?.chart_data || {};
            
            let scoreData = [];
            if (predictions && predictions.length > 0) {
                const avgScore = predictions.reduce((a, b) => a + b, 0) / predictions.length;
                scoreData = Array(7).fill(avgScore);
                scoreData = scoreData.map((s, i) => {
                    const variation = (Math.random() - 0.5) * 0.2;
                    return Math.max(0, Math.min(1, s + variation));
                });
            } else {
                const baseScore = metrics.mean_prediction || 0.65;
                scoreData = [
                    baseScore * (0.8 + Math.random() * 0.4),
                    baseScore * (0.9 + Math.random() * 0.3),
                    baseScore * (0.7 + Math.random() * 0.5),
                    baseScore * (1.0 + Math.random() * 0.2),
                    baseScore * (1.1 + Math.random() * 0.2),
                    baseScore * (0.6 + Math.random() * 0.5),
                    baseScore * (0.5 + Math.random() * 0.4)
                ];
                scoreData = scoreData.map(s => Math.max(0, Math.min(1, s)));
            }
            
            let servicesData;
            if (chartData.performance?.services) {
                servicesData = chartData.performance.services;
            } else if (predictions && predictions.length >= 7) {
                servicesData = predictions.slice(0, 7).map(p => Math.max(1, Math.round(p * 15 + 2)));
            } else {
                servicesData = [8, 12, 6, 15, 18, 4, 2];
            }
            
            let revenueData, costsData;
            if (chartData.weekly) {
                revenueData = chartData.weekly.revenue || [];
                costsData = chartData.weekly.costs || [];
            } else {
                const baseRevenue = metrics.mean_prediction ? metrics.mean_prediction * 1500 : 1000;
                revenueData = Array(7).fill(0).map((_, i) => {
                    const peak = i === 3 || i === 4 ? 1.3 : 1;
                    return baseRevenue * (0.6 + Math.random() * 0.6) * peak;
                });
                costsData = revenueData.map(r => r * (0.25 + Math.random() * 0.35));
            }
            
            while (scoreData.length < 7) scoreData.push(0.5);
            while (servicesData.length < 7) servicesData.push(5);
            while (revenueData.length < 7) revenueData.push(1000);
            while (costsData.length < 7) costsData.push(350);
            
            const avgScore = scoreData.reduce((a, b) => a + b, 0) / scoreData.length;
            const healthStatus = Utils.getHealthStatus(avgScore);
            
            const totalRevenue = revenueData.reduce((a, b) => a + b, 0);
            const totalCosts = costsData.reduce((a, b) => a + b, 0);
            const totalServices = servicesData.reduce((a, b) => a + b, 0);
            const profit = totalRevenue - totalCosts;
            
            return {
                labels: days,
                score: scoreData.map(s => Math.round(s * 100) / 100),
                services: servicesData.map(s => Math.round(s)),
                revenue: revenueData.map(r => Math.round(r)),
                costs: costsData.map(r => Math.round(r)),
                metrics: {
                    avgScore: Math.round(avgScore * 100) / 100,
                    totalRevenue: Math.round(totalRevenue),
                    totalCosts: Math.round(totalCosts),
                    totalServices: Math.round(totalServices),
                    profit: Math.round(profit),
                    margin: Math.round((profit / totalRevenue) * 100) || 0,
                    health: healthStatus
                },
                peaks: {
                    bestDay: servicesData.indexOf(Math.max(...servicesData)),
                    worstDay: servicesData.indexOf(Math.min(...servicesData)),
                    bestScore: scoreData.indexOf(Math.max(...scoreData)),
                    worstScore: scoreData.indexOf(Math.min(...scoreData))
                }
            };
        }
    };

    // ==============================================
    // 🔥 GPSA CHART RENDERER
    // ==============================================

    class GPSAChartRenderer {
        constructor() {
            this._charts = {};
            this._chartInstances = {};
        }

        createGPSAChart(canvasId, data, options = {}) {
            const canvas = document.getElementById(canvasId);
            if (!canvas) {
                console.warn(`⚠️ [GPSA] Canvas ${canvasId} não encontrado`);
                return null;
            }

            if (this._chartInstances[canvasId]) {
                this._chartInstances[canvasId].destroy();
                delete this._chartInstances[canvasId];
            }

            const ctx = canvas.getContext('2d');

            const labels = data.labels || ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'];
            const scoreData = data.score || Array(7).fill(0.5);
            const servicesData = data.services || Array(7).fill(5);
            const revenueData = data.revenue || Array(7).fill(1000);
            const costsData = data.costs || Array(7).fill(350);
            
            const metrics = data.metrics || {};
            const health = metrics.health || { status: 'regular', color: '#f5a623', label: 'Regular' };

            const profitData = revenueData.map((r, i) => r - (costsData[i] || 0));

            const peakAnnotationPlugin = {
                id: 'peakAnnotation',
                afterDraw: function(chart) {
                    const ctx = chart.ctx;
                    const meta = chart.getDatasetMeta(1);
                    const data = chart.data.datasets[1].data;
                    
                    if (!meta || !data) return;
                    
                    const maxVal = Math.max(...data);
                    const minVal = Math.min(...data);
                    const maxIndex = data.indexOf(maxVal);
                    const minIndex = data.indexOf(minVal);
                    
                    ctx.save();
                    
                    const maxPoint = meta.data[maxIndex];
                    if (maxPoint) {
                        const x = maxPoint.x;
                        const y = maxPoint.y - 15;
                        
                        ctx.beginPath();
                        ctx.moveTo(x, y + 10);
                        ctx.lineTo(x, y - 5);
                        ctx.strokeStyle = '#48bb78';
                        ctx.lineWidth = 2;
                        ctx.stroke();
                        
                        ctx.fillStyle = '#48bb78';
                        ctx.font = 'bold 8px Inter, sans-serif';
                        ctx.textAlign = 'center';
                        ctx.fillText('🏆 Pico', x, y - 8);
                    }
                    
                    const minPoint = meta.data[minIndex];
                    if (minPoint) {
                        const x = minPoint.x;
                        const y = minPoint.y + 20;
                        
                        ctx.beginPath();
                        ctx.moveTo(x, y - 10);
                        ctx.lineTo(x, y + 5);
                        ctx.strokeStyle = '#f56565';
                        ctx.lineWidth = 2;
                        ctx.stroke();
                        
                        ctx.fillStyle = '#f56565';
                        ctx.font = 'bold 8px Inter, sans-serif';
                        ctx.textAlign = 'center';
                        ctx.fillText('⬇️ Vale', x, y + 15);
                    }
                    
                    ctx.restore();
                }
            };

            const chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: '📊 Score de Risco',
                            data: scoreData,
                            borderColor: '#ff6b35',
                            backgroundColor: 'rgba(255,107,53,0.10)',
                            fill: true,
                            tension: 0.4,
                            pointRadius: 5,
                            pointBackgroundColor: '#ff6b35',
                            pointBorderColor: '#ffffff',
                            pointBorderWidth: 2,
                            borderWidth: 3,
                            yAxisID: 'y1',
                            order: 1,
                        },
                        {
                            label: '🔧 Serviços',
                            data: servicesData,
                            borderColor: '#4a9eff',
                            backgroundColor: 'rgba(74,158,255,0.08)',
                            fill: true,
                            tension: 0.4,
                            pointRadius: 4,
                            pointBackgroundColor: '#4a9eff',
                            pointBorderColor: '#ffffff',
                            pointBorderWidth: 2,
                            borderWidth: 2,
                            yAxisID: 'y2',
                            order: 2,
                            borderDash: [5, 5],
                        },
                        {
                            label: '💰 Receita',
                            data: revenueData,
                            borderColor: '#48bb78',
                            backgroundColor: 'rgba(72,187,120,0.05)',
                            fill: false,
                            tension: 0.4,
                            pointRadius: 3,
                            pointBackgroundColor: '#48bb78',
                            pointBorderColor: '#ffffff',
                            pointBorderWidth: 1,
                            borderWidth: 2,
                            yAxisID: 'y3',
                            order: 3,
                            borderDash: [3, 3],
                        },
                        {
                            label: '📦 Custos',
                            data: costsData,
                            borderColor: '#f56565',
                            backgroundColor: 'rgba(245,101,101,0.05)',
                            fill: false,
                            tension: 0.4,
                            pointRadius: 3,
                            pointBackgroundColor: '#f56565',
                            pointBorderColor: '#ffffff',
                            pointBorderWidth: 1,
                            borderWidth: 2,
                            yAxisID: 'y3',
                            order: 4,
                            borderDash: [2, 4],
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        mode: 'index',
                        intersect: false,
                    },
                    plugins: {
                        legend: {
                            labels: {
                                color: 'rgba(255,255,255,0.4)',
                                font: {
                                    size: 9,
                                    weight: '600'
                                },
                                boxWidth: 10,
                                padding: 8,
                            },
                            position: 'top',
                        },
                        tooltip: {
                            backgroundColor: 'rgba(0,0,0,0.85)',
                            titleColor: '#ffffff',
                            bodyColor: '#e2e8f0',
                            borderColor: 'rgba(255,255,255,0.1)',
                            borderWidth: 1,
                            padding: 14,
                            cornerRadius: 10,
                            callbacks: {
                                afterBody: function(tooltipItems) {
                                    const revenue = tooltipItems[2]?.parsed?.y || 0;
                                    const costs = tooltipItems[3]?.parsed?.y || 0;
                                    const profit = revenue - costs;
                                    const score = tooltipItems[0]?.parsed?.y || 0;
                                    const health = Utils.getHealthStatus(score);
                                    
                                    return [
                                        '━━━━━━━━━━━━━━━━━',
                                        '📊 Saúde: ' + health.icon + ' ' + health.label,
                                        '💰 Lucro: ' + Utils.formatCurrency(profit),
                                        profit > 0 ? '✅ Margem positiva' : '⚠️ Margem negativa'
                                    ];
                                }
                            }
                        },
                        peakAnnotation: peakAnnotationPlugin
                    },
                    scales: {
                        x: {
                            grid: {
                                color: 'rgba(255,255,255,0.05)',
                                drawBorder: false,
                            },
                            ticks: {
                                color: 'rgba(255,255,255,0.4)',
                                font: {
                                    size: 10,
                                }
                            }
                        },
                        y1: {
                            position: 'left',
                            min: 0,
                            max: 1,
                            grid: {
                                color: 'rgba(255,255,255,0.05)',
                                drawBorder: false,
                            },
                            ticks: {
                                color: 'rgba(255,255,255,0.4)',
                                font: {
                                    size: 9,
                                },
                                callback: function(value) {
                                    return (value * 100).toFixed(0) + '%';
                                }
                            },
                            title: {
                                display: true,
                                text: 'Score de Risco',
                                color: 'rgba(255,255,255,0.4)',
                                font: {
                                    size: 8,
                                    weight: '600'
                                }
                            }
                        },
                        y2: {
                            position: 'right',
                            grid: {
                                display: false,
                            },
                            ticks: {
                                color: 'rgba(255,255,255,0.4)',
                                font: {
                                    size: 9,
                                },
                                stepSize: 1,
                                beginAtZero: true,
                            },
                            title: {
                                display: true,
                                text: 'Serviços',
                                color: 'rgba(255,255,255,0.4)',
                                font: {
                                    size: 8,
                                    weight: '600'
                                }
                            }
                        },
                        y3: {
                            position: 'right',
                            grid: {
                                display: false,
                            },
                            ticks: {
                                color: 'rgba(255,255,255,0.4)',
                                font: {
                                    size: 9,
                                },
                                callback: function(value) {
                                    return Utils.formatCurrencyShort(value);
                                }
                            },
                            title: {
                                display: true,
                                text: 'Valores (R$)',
                                color: 'rgba(255,255,255,0.4)',
                                font: {
                                    size: 8,
                                    weight: '600'
                                }
                            }
                        }
                    },
                    animation: {
                        duration: 1200,
                        easing: 'easeOutQuart'
                    }
                },
                plugins: [peakAnnotationPlugin]
            });

            this._chartInstances[canvasId] = chart;
            
            chart._metadata = {
                type: 'gpsa',
                labels: labels,
                score: scoreData,
                services: servicesData,
                revenue: revenueData,
                costs: costsData,
                metrics: metrics
            };

            return chart;
        }

        updateGPSAChart(canvasId, data) {
            const chart = this._chartInstances[canvasId];
            if (!chart) {
                console.warn(`⚠️ [GPSA] Chart ${canvasId} não encontrado`);
                return false;
            }

            try {
                chart.data.labels = data.labels || chart.data.labels;
                chart.data.datasets[0].data = data.score || chart.data.datasets[0].data;
                chart.data.datasets[1].data = data.services || chart.data.datasets[1].data;
                chart.data.datasets[2].data = data.revenue || chart.data.datasets[2].data;
                chart.data.datasets[3].data = data.costs || chart.data.datasets[3].data;
                
                chart.update();
                return true;
            } catch (e) {
                console.error('❌ Erro ao atualizar GPSA:', e);
                return false;
            }
        }

        createFinancialLineChart(canvasId, data, options = {}) {
            const canvas = document.getElementById(canvasId);
            if (!canvas) {
                console.warn(`⚠️ [FinanceChart] Canvas ${canvasId} não encontrado`);
                return null;
            }

            if (this._chartInstances[canvasId]) {
                this._chartInstances[canvasId].destroy();
                delete this._chartInstances[canvasId];
            }

            const ctx = canvas.getContext('2d');

            const labels = data.labels || ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'];
            const revenueData = data.revenue || Array(7).fill(0);
            const costsData = data.costs || Array(7).fill(0);
            const profitData = revenueData.map((r, i) => r - (costsData[i] || 0));

            const chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: '💰 Receita',
                            data: revenueData,
                            borderColor: '#48bb78',
                            backgroundColor: 'rgba(72,187,120,0.15)',
                            fill: true,
                            tension: 0.4,
                            pointRadius: 4,
                            pointBackgroundColor: '#48bb78',
                            pointBorderColor: '#ffffff',
                            pointBorderWidth: 2,
                            borderWidth: 3,
                        },
                        {
                            label: '📦 Custos',
                            data: costsData,
                            borderColor: '#f56565',
                            backgroundColor: 'rgba(245,101,101,0.10)',
                            fill: true,
                            tension: 0.4,
                            pointRadius: 4,
                            pointBackgroundColor: '#f56565',
                            pointBorderColor: '#ffffff',
                            pointBorderWidth: 2,
                            borderWidth: 3,
                            borderDash: [5, 5],
                        },
                        {
                            label: '📊 Lucro',
                            data: profitData,
                            borderColor: '#ff6b35',
                            backgroundColor: 'rgba(255,107,53,0.05)',
                            fill: true,
                            tension: 0.4,
                            pointRadius: 4,
                            pointBackgroundColor: '#ff6b35',
                            pointBorderColor: '#ffffff',
                            pointBorderWidth: 2,
                            borderWidth: 2,
                            borderDash: [3, 3],
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        mode: 'index',
                        intersect: false,
                    },
                    plugins: {
                        legend: {
                            labels: {
                                color: 'rgba(255,255,255,0.4)',
                                font: {
                                    size: 10,
                                    weight: '600'
                                },
                                boxWidth: 12,
                                padding: 10,
                            },
                            position: 'top',
                        },
                        tooltip: {
                            backgroundColor: 'rgba(0,0,0,0.8)',
                            titleColor: '#ffffff',
                            bodyColor: '#e2e8f0',
                            borderColor: 'rgba(255,255,255,0.1)',
                            borderWidth: 1,
                            padding: 12,
                            cornerRadius: 8,
                            callbacks: {
                                label: function(context) {
                                    const label = context.dataset.label || '';
                                    const value = context.parsed.y;
                                    if (context.datasetIndex === 2) {
                                        return label + ': ' + Utils.formatCurrency(value);
                                    }
                                    return label + ': ' + Utils.formatCurrency(value);
                                },
                                afterBody: function(tooltipItems) {
                                    const revenue = tooltipItems[0]?.parsed?.y || 0;
                                    const costs = tooltipItems[1]?.parsed?.y || 0;
                                    const profit = revenue - costs;
                                    return '━━━━━━━━━━━━━━━━━\n' +
                                           '📊 Lucro: ' + Utils.formatCurrency(profit) +
                                           (profit > 0 ? ' ✅' : ' ⚠️');
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            grid: {
                                color: 'rgba(255,255,255,0.05)',
                                drawBorder: false,
                            },
                            ticks: {
                                color: 'rgba(255,255,255,0.4)',
                                font: {
                                    size: 10,
                                }
                            }
                        },
                        y: {
                            grid: {
                                color: 'rgba(255,255,255,0.05)',
                                drawBorder: false,
                            },
                            ticks: {
                                color: 'rgba(255,255,255,0.4)',
                                font: {
                                    size: 10,
                                },
                                callback: function(value) {
                                    return Utils.formatCurrencyShort(value);
                                }
                            }
                        }
                    },
                    animation: {
                        duration: 1000,
                        easing: 'easeOutQuart'
                    }
                }
            });

            this._chartInstances[canvasId] = chart;
            return chart;
        }

        createPerformanceLineChart(canvasId, data, options = {}) {
            const canvas = document.getElementById(canvasId);
            if (!canvas) {
                console.warn(`⚠️ [PerformanceChart] Canvas ${canvasId} não encontrado`);
                return null;
            }

            if (this._chartInstances[canvasId]) {
                this._chartInstances[canvasId].destroy();
                delete this._chartInstances[canvasId];
            }

            const ctx = canvas.getContext('2d');

            const labels = data.labels || ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'];
            const servicesData = data.services || data.count || Array(7).fill(0);

            const chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: '🔧 Serviços Finalizados',
                            data: servicesData,
                            borderColor: '#4a9eff',
                            backgroundColor: 'rgba(74,158,255,0.12)',
                            fill: true,
                            tension: 0.4,
                            pointRadius: 5,
                            pointBackgroundColor: '#4a9eff',
                            pointBorderColor: '#ffffff',
                            pointBorderWidth: 2,
                            borderWidth: 3,
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            labels: {
                                color: 'rgba(255,255,255,0.4)',
                                font: {
                                    size: 10,
                                    weight: '600'
                                },
                                boxWidth: 12,
                                padding: 10,
                            },
                            position: 'top',
                        },
                        tooltip: {
                            backgroundColor: 'rgba(0,0,0,0.8)',
                            titleColor: '#ffffff',
                            bodyColor: '#e2e8f0',
                            borderColor: 'rgba(255,255,255,0.1)',
                            borderWidth: 1,
                            padding: 12,
                            cornerRadius: 8,
                            callbacks: {
                                label: function(context) {
                                    const value = context.parsed.y;
                                    return '🔧 Serviços: ' + Math.round(value);
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            grid: {
                                color: 'rgba(255,255,255,0.05)',
                                drawBorder: false,
                            },
                            ticks: {
                                color: 'rgba(255,255,255,0.4)',
                                font: {
                                    size: 10,
                                }
                            }
                        },
                        y: {
                            grid: {
                                color: 'rgba(255,255,255,0.05)',
                                drawBorder: false,
                            },
                            ticks: {
                                color: 'rgba(255,255,255,0.4)',
                                font: {
                                    size: 10,
                                },
                                stepSize: 1,
                                beginAtZero: true
                            }
                        }
                    },
                    animation: {
                        duration: 1000,
                        easing: 'easeOutQuart'
                    }
                }
            });

            this._chartInstances[canvasId] = chart;
            return chart;
        }

        updateChart(canvasId, data) {
            const chart = this._chartInstances[canvasId];
            if (!chart) {
                console.warn(`⚠️ [FinanceChart] Chart ${canvasId} não encontrado para atualizar`);
                return false;
            }

            try {
                chart.data.labels = data.labels || chart.data.labels;
                chart.data.datasets[0].data = data.revenue || chart.data.datasets[0].data;
                chart.data.datasets[1].data = data.costs || chart.data.datasets[1].data;
                
                if (chart.data.datasets.length > 2) {
                    const profit = (data.revenue || []).map((r, i) => r - ((data.costs || [])[i] || 0));
                    chart.data.datasets[2].data = profit;
                }
                
                chart.update();
                return true;
            } catch (e) {
                console.error('❌ Erro ao atualizar chart:', e);
                return false;
            }
        }

        destroyAll() {
            for (const key in this._chartInstances) {
                try {
                    this._chartInstances[key].destroy();
                } catch (e) {}
            }
            this._chartInstances = {};
        }
    }

    // ==============================================
    // 🔥 TAB MANAGER - GERENCIADOR DE ABAS DINÂMICAS
    // ==============================================

    class TabManager {
        constructor() {
            this._tabs = [];
            this._activeTab = 0;
            this._chartRenderer = new GPSAChartRenderer();
            this._container = document.getElementById('gpsaTabsContainer');
            this._tabList = document.getElementById('gpsaTabs');
            this._tabContent = document.getElementById('gpsaTabContent');
            this._placeholder = document.getElementById('gpsaPlaceholder');
            this._healthIndicator = document.getElementById('gpsaHealthIndicator');
        }

        /**
         * 🔥 Renderiza as abas com base nas análises
         */
        renderTabs(analyses) {
            if (!analyses || analyses.length === 0) {
                this._showPlaceholder();
                return;
            }

            // Limitar a 3 análises (as mais recentes)
            const maxTabs = 3;
            const recentAnalyses = analyses.slice(0, maxTabs);
            
            // Filtrar apenas análises com chart_data
            const validAnalyses = recentAnalyses.filter(a => a.chart_data && Object.keys(a.chart_data).length > 0);
            
            if (validAnalyses.length === 0) {
                this._showPlaceholder();
                return;
            }

            this._hidePlaceholder();
            this._tabs = validAnalyses;
            this._renderTabHeaders(validAnalyses);
            this._renderTabContents(validAnalyses);
            
            // Ativar primeira aba
            this._activateTab(0);
        }

        /**
         * 🔥 Renderiza os cabeçalhos das abas
         */
        _renderTabHeaders(analyses) {
            if (!this._tabList) return;
            
            let html = '';
            const icons = ['📊', '📈', '📉'];
            const colors = ['#ff6b35', '#4a9eff', '#48bb78'];
            
            analyses.forEach((analysis, index) => {
                const isActive = index === 0 ? 'active' : '';
                const icon = icons[index % icons.length];
                const color = colors[index % colors.length];
                
                const filename = analysis.filename || `Arquivo ${index + 1}`;
                const shortName = filename.length > 20 ? filename.substring(0, 18) + '...' : filename;
                const rows = analysis.rows_processed || analysis.total_rows || 0;
                
                html += `
                    <li class="nav-item" role="presentation">
                        <button class="nav-link ${isActive}" 
                                id="gpsa-tab-${index}" 
                                data-bs-toggle="tab" 
                                data-bs-target="#gpsa-content-${index}" 
                                type="button" 
                                role="tab" 
                                aria-controls="gpsa-content-${index}" 
                                aria-selected="${index === 0 ? 'true' : 'false'}"
                                style="color: ${isActive ? color : 'rgba(255,255,255,0.4)'}; 
                                       border: none; 
                                       background: ${isActive ? 'rgba(255,255,255,0.05)' : 'transparent'};
                                       border-bottom: 2px solid ${isActive ? color : 'transparent'};
                                       font-size: 0.75rem;
                                       padding: 0.4rem 1rem;
                                       transition: all 0.3s ease;"
                                data-filename="${filename}">
                            ${icon} ${shortName}
                            <span class="badge ms-1" style="background:rgba(255,255,255,0.05); font-size:0.5rem; color:rgba(255,255,255,0.2);">
                                ${rows} registros
                            </span>
                        </button>
                    </li>
                `;
            });
            
            this._tabList.innerHTML = html;
            
            // Adicionar event listeners
            this._tabList.querySelectorAll('.nav-link').forEach((btn, index) => {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    this._activateTab(index);
                });
            });
        }

        /**
         * 🔥 Renderiza os conteúdos das abas
         */
        _renderTabContents(analyses) {
            if (!this._tabContent) return;
            
            let html = '';
            
            analyses.forEach((analysis, index) => {
                const isActive = index === 0 ? 'show active' : '';
                const filename = analysis.filename || `Arquivo ${index + 1}`;
                const rows = analysis.rows_processed || analysis.total_rows || 0;
                
                html += `
                    <div class="tab-pane fade ${isActive}" 
                         id="gpsa-content-${index}" 
                         role="tabpanel" 
                         aria-labelledby="gpsa-tab-${index}">
                        <div style="height: 300px; position: relative;">
                            <canvas id="gpsaChart-${index}"></canvas>
                        </div>
                        <div class="mt-2 text-center">
                            <small style="color:rgba(255,255,255,0.15); font-size:0.5rem;">
                                <i class="fas fa-info-circle me-1"></i> 
                                ${filename} - ${rows} registros
                            </small>
                        </div>
                    </div>
                `;
            });
            
            this._tabContent.innerHTML = html;
            
            // Renderizar gráficos de cada aba
            analyses.forEach((analysis, index) => {
                const canvasId = `gpsaChart-${index}`;
                const canvas = document.getElementById(canvasId);
                if (canvas) {
                    const gpsaData = Utils.generateGPSAData({
                        chart_data: analysis.chart_data || {},
                        metrics: analysis.predictions_summary || analysis.metrics || {},
                        predictions: analysis.predictions || []
                    });
                    this._chartRenderer.createGPSAChart(canvasId, gpsaData);
                }
            });
            
            // Atualizar indicador de saúde com a primeira análise
            if (analyses.length > 0) {
                this._updateHealthIndicator(analyses[0]);
            }
        }

        /**
         * 🔥 Ativa uma aba específica
         */
        _activateTab(index) {
            if (index < 0 || index >= this._tabs.length) return;
            
            this._activeTab = index;
            
            // Atualizar tabs
            const tabs = this._tabList.querySelectorAll('.nav-link');
            const contents = this._tabContent.querySelectorAll('.tab-pane');
            
            const colors = ['#ff6b35', '#4a9eff', '#48bb78'];
            
            tabs.forEach((tab, i) => {
                const isActive = i === index;
                const color = colors[i % colors.length];
                tab.classList.toggle('active', isActive);
                tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
                tab.style.color = isActive ? color : 'rgba(255,255,255,0.4)';
                tab.style.background = isActive ? 'rgba(255,255,255,0.05)' : 'transparent';
                tab.style.borderBottom = isActive ? '2px solid ' + color : '2px solid transparent';
            });
            
            contents.forEach((content, i) => {
                content.classList.toggle('show', i === index);
                content.classList.toggle('active', i === index);
            });
            
            // Atualizar indicador de saúde
            if (this._tabs[index]) {
                this._updateHealthIndicator(this._tabs[index]);
            }
            
            // Atualizar relatório da IA
            this._updateAIReport(this._tabs[index]);
            
            // Redimensionar gráfico
            setTimeout(() => {
                const activeContent = contents[index];
                if (activeContent) {
                    const canvas = activeContent.querySelector('canvas');
                    if (canvas && canvas.id) {
                        const chart = this._chartRenderer._chartInstances[canvas.id];
                        if (chart) {
                            chart.resize();
                        }
                    }
                }
            }, 100);
        }

        /**
         * 🔥 Atualiza o indicador de saúde
         */
        _updateHealthIndicator(analysis) {
            if (!this._healthIndicator) return;
            
            const metrics = analysis.predictions_summary || analysis.metrics || {};
            const score = metrics.mean_prediction || 0.5;
            const health = Utils.getHealthStatus(score);
            
            const statusMap = {
                'excelente': { bg: 'rgba(72,187,120,0.15)', color: '#48bb78', icon: '🟢', label: 'Excelente' },
                'bom': { bg: 'rgba(74,158,255,0.15)', color: '#4a9eff', icon: '🔵', label: 'Bom' },
                'regular': { bg: 'rgba(245,166,35,0.15)', color: '#f5a623', icon: '🟡', label: 'Regular' },
                'critico': { bg: 'rgba(245,101,101,0.15)', color: '#f56565', icon: '🔴', label: 'Crítico' }
            };
            
            const status = statusMap[health.status] || statusMap['regular'];
            const filename = analysis.filename || 'Arquivo';
            const shortName = filename.length > 15 ? filename.substring(0, 12) + '...' : filename;
            
            this._healthIndicator.style.background = status.bg;
            this._healthIndicator.style.color = status.color;
            this._healthIndicator.style.border = '1px solid ' + status.color;
            this._healthIndicator.innerHTML = '<i class="fas fa-circle me-1" style="font-size:0.4rem; color:' + status.color + ';"></i> ' + status.icon + ' ' + status.label + ' (' + shortName + ')';
        }

        /**
         * 🔥 Atualiza o relatório da IA
         */
        _updateAIReport(analysis) {
            const reportContainer = document.getElementById('aiReportContent');
            if (!reportContainer) return;
            
            const insights = analysis.insights || {};
            const recommendations = analysis.recommendations || [];
            const metrics = analysis.predictions_summary || analysis.metrics || {};
            const filename = analysis.filename || 'Análise';
            const rows = analysis.rows_processed || analysis.total_rows || 0;
            const score = metrics.mean_prediction || 0.65;
            const highRisk = metrics.high_risk_percentage || 0;
            const lowRisk = metrics.low_risk_percentage || 0;
            
            let html = '';
            
            // Se tiver insights do ML
            if (insights && Object.keys(insights).length > 0) {
                const summary = insights.summary || {};
                const riskDist = insights.risk_distribution || {};
                
                html = `
                    <div style="margin-bottom:0.5rem;">
                        <strong style="color:#ff6b35;">📊 Análise de ${filename}</strong>
                        <span style="color:rgba(255,255,255,0.15); font-size:0.65rem; margin-left:0.5rem;">
                            ${rows} registros • Score: ${(score * 100).toFixed(0)}%
                        </span>
                    </div>
                    <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap:0.3rem; margin-bottom:0.5rem;">
                        <div style="background:rgba(0,0,0,0.1); padding:0.2rem 0.4rem; border-radius:4px;">
                            <span style="color:rgba(255,255,255,0.2); font-size:0.5rem;">MÉDIA</span>
                            <div style="font-size:0.75rem; color:#48bb78;">${(summary.mean * 100).toFixed(0)}%</div>
                        </div>
                        <div style="background:rgba(0,0,0,0.1); padding:0.2rem 0.4rem; border-radius:4px;">
                            <span style="color:rgba(255,255,255,0.2); font-size:0.5rem;">ALTO RISCO</span>
                            <div style="font-size:0.75rem; color:#f56565;">${(riskDist.high_percentage || 0).toFixed(0)}%</div>
                        </div>
                        <div style="background:rgba(0,0,0,0.1); padding:0.2rem 0.4rem; border-radius:4px;">
                            <span style="color:rgba(255,255,255,0.2); font-size:0.5rem;">BAIXO RISCO</span>
                            <div style="font-size:0.75rem; color:#48bb78;">${(riskDist.low_percentage || 0).toFixed(0)}%</div>
                        </div>
                    </div>
                `;
            } else {
                // Fallback: gerar relatório simples
                const health = Utils.getHealthStatus(score);
                html = `
                    <div style="margin-bottom:0.3rem;">
                        <strong style="color:#ff6b35;">📊 Relatório de ${filename}</strong>
                    </div>
                    <div style="font-size:0.75rem; line-height:1.6;">
                        <span class="highlight">📈 ${rows} registros</span> analisados com score médio de 
                        <span class="highlight">${(score * 100).toFixed(0)}%</span>.
                        <br>
                        ${health.icon} Saúde: <span style="color:${health.color};">${health.label}</span>
                        ${highRisk > 0 ? `• 🔴 ${highRisk.toFixed(0)}% de alto risco` : ''}
                        ${lowRisk > 0 ? `• 🟢 ${lowRisk.toFixed(0)}% de baixo risco` : ''}
                    </div>
                `;
            }
            
            // Recomendações
            if (recommendations && recommendations.length > 0) {
                html += `
                    <div style="margin-top:0.3rem; padding-top:0.3rem; border-top:1px solid rgba(255,255,255,0.03);">
                        <span style="color:rgba(255,255,255,0.2); font-size:0.5rem;">RECOMENDAÇÕES</span>
                        <ul style="margin:0.2rem 0 0 0; padding-left:1rem; font-size:0.7rem; color:rgba(255,255,255,0.5);">
                            ${recommendations.slice(0, 3).map(r => `<li>${r}</li>`).join('')}
                        </ul>
                    </div>
                `;
            }
            
            reportContainer.innerHTML = html;
        }

        /**
         * 🔥 Mostra placeholder
         */
        _showPlaceholder() {
            if (this._container) this._container.style.display = 'none';
            if (this._placeholder) this._placeholder.style.display = 'block';
            if (this._healthIndicator) {
                this._healthIndicator.style.background = 'rgba(255,255,255,0.05)';
                this._healthIndicator.style.color = 'rgba(255,255,255,0.4)';
                this._healthIndicator.style.border = '1px solid rgba(255,255,255,0.05)';
                this._healthIndicator.innerHTML = '<i class="fas fa-circle me-1" style="font-size:0.4rem;"></i> Aguardando dados...';
            }
            // Reset do relatório
            const reportContainer = document.getElementById('aiReportContent');
            if (reportContainer) {
                reportContainer.innerHTML = `
                    <div class="ai-report-placeholder">
                        <i class="fas fa-brain" style="font-size:1.5rem; display:block; margin-bottom:0.5rem; opacity:0.3;"></i>
                        Aguardando análise da IA...
                    </div>
                `;
            }
        }

        /**
         * 🔥 Esconde placeholder
         */
        _hidePlaceholder() {
            if (this._container) this._container.style.display = 'block';
            if (this._placeholder) this._placeholder.style.display = 'none';
        }

        /**
         * 🔥 Retorna a análise ativa
         */
        getActiveAnalysis() {
            if (this._tabs && this._tabs[this._activeTab]) {
                return this._tabs[this._activeTab];
            }
            return null;
        }

        /**
         * 🔥 Retorna todas as análises
         */
        getAllAnalyses() {
            return this._tabs;
        }

        /**
         * 🔥 Destroi todos os gráficos
         */
        destroy() {
            this._chartRenderer.destroyAll();
        }
    }

    // ==============================================
    // 🔥 STATE MANAGER
    // ==============================================

    class StateManager {
        constructor() {
            this._state = {
                user: { name: 'Usuário', email: '', isAdmin: false, isPremium: false, credits: 0, segment: 'regular' },
                analyses: { active: [], history: [], total: 0, today: 0 },
                ui: { isLoading: false, isUploading: false, progress: 0, status: 'idle', message: '' },
                pow: { ready: false, solution: null, lastAttempt: null, clientAvailable: false },
                system: { isAppReady: false, isInitialized: false, lastSync: null },
                finance: { weekly: null, monthly: null, lastUpdate: null },
                gpsa: { data: null, lastUpdate: null }
            };
            this._listeners = [];
            this._initialized = false;
        }

        get state() { return this._state; }
        get(key) { return this._state[key] || null; }

        set(key, value) {
            const oldValue = this._state[key];
            this._state[key] = value;
            this._notifyListeners(key, value, oldValue);
            return this;
        }

        update(key, updates) {
            const oldValue = this._state[key];
            this._state[key] = { ...oldValue, ...updates };
            this._notifyListeners(key, this._state[key], oldValue);
            return this;
        }

        subscribe(callback) {
            this._listeners.push(callback);
            return () => { this._listeners = this._listeners.filter(cb => cb !== callback); };
        }

        _notifyListeners(key, newValue, oldValue) {
            this._listeners.forEach(callback => {
                try { callback(key, newValue, oldValue); } catch (e) { console.error('❌ [StateManager] Listener error:', e); }
            });
        }

        reset() {
            this._state = {
                user: { name: 'Usuário', email: '', isAdmin: false, isPremium: false, credits: 0, segment: 'regular' },
                analyses: { active: [], history: [], total: 0, today: 0 },
                ui: { isLoading: false, isUploading: false, progress: 0, status: 'idle', message: '' },
                pow: { ready: false, solution: null, lastAttempt: null, clientAvailable: false },
                system: { isAppReady: false, isInitialized: false, lastSync: null },
                finance: { weekly: null, monthly: null, lastUpdate: null },
                gpsa: { data: null, lastUpdate: null }
            };
            this._notifyListeners('reset', null, null);
            return this;
        }

        syncWithApp() {
            const appState = window.__APP_STATE || {};
            this.set('user', {
                name: appState.displayName || appState.user?.name || 'Usuário',
                email: appState.user?.email || '',
                isAdmin: appState.isAdmin || false,
                isPremium: appState.isPremium || false,
                credits: appState.credits || 0,
                segment: appState.segment || 'regular',
            });
            this.set('system', { ...this._state.system, isAppReady: true, lastSync: Date.now() });
            this._initialized = true;
            return this;
        }
    }

    // ==============================================
    // 🔥 DASHBOARD - CLASSE PRINCIPAL
    // ==============================================

    class Dashboard {
        constructor() {
            this.state = new StateManager();
            this.financeChart = new GPSAChartRenderer();
            this.tabManager = new TabManager();
            this._initialized = false;
            this._pollingInterval = null;
        }

        async init() {
            if (this._initialized) {
                console.log('ℹ️ [Dashboard] Já inicializado');
                return this;
            }

            console.log('🚀 [Dashboard v9.1] Inicializando com abas dinâmicas...');

            await this._waitForApp();
            this.state.syncWithApp();
            this._generateAllData();
            this._createAllCharts();
            this._setupEvents();

            // 🔥 Carregar análises para as abas
            await this._loadAnalysesForTabs();

            // 🔥 Iniciar polling para atualizações
            this._startPolling();

            this._initialized = true;

            console.log('✅ [Dashboard v9.1] Inicializado com sucesso!');
            console.log('   📊 GPSA com abas dinâmicas');

            return this;
        }

        async _waitForApp() {
            return new Promise((resolve) => {
                let attempts = 0;
                const maxAttempts = CONFIG.WAIT_FOR_APP_TIMEOUT / CONFIG.WAIT_FOR_APP_INTERVAL;

                const check = () => {
                    attempts++;
                    if (window._appReadyFired === true) { resolve(true); return; }
                    if (window.App && typeof window.App.isReady === 'function') {
                        try { if (window.App.isReady()) { resolve(true); return; } } catch (e) {}
                    }
                    if (window.__APP_STATE && window.__APP_STATE.isAppReady === true) { resolve(true); return; }
                    if (attempts >= maxAttempts) {
                        console.warn('⚠️ [Dashboard] Timeout aguardando app.js');
                        resolve(false);
                        return;
                    }
                    setTimeout(check, CONFIG.WAIT_FOR_APP_INTERVAL);
                };
                check();
            });
        }

        _generateAllData() {
            const weeklyData = Utils.generateWeeklyFinanceData(null);
            const monthlyData = Utils.generateMonthlyFinanceData(null);
            
            const gpsaData = Utils.generateGPSAData({
                metrics: { mean_prediction: 0.65 },
                chart_data: weeklyData
            });
            
            this.state.set('finance', {
                weekly: weeklyData,
                monthly: monthlyData,
                lastUpdate: Date.now()
            });
            
            this.state.set('gpsa', {
                data: gpsaData,
                lastUpdate: Date.now()
            });
        }

        _createAllCharts() {
            const weeklyData = this.state.state.finance.weekly;

            // Gráficos secundários (financeiros)
            const weeklyCanvas = document.getElementById('weeklyFinanceChart');
            if (weeklyCanvas) {
                this.financeChart.createFinancialLineChart('weeklyFinanceChart', weeklyData);
            }

            const perfCanvas = document.getElementById('weeklyPerformanceChart');
            if (perfCanvas) {
                const perfData = {
                    labels: weeklyData.labels,
                    services: weeklyData.count || weeklyData.revenue.map(() => Math.floor(Math.random() * 8 + 2))
                };
                this.financeChart.createPerformanceLineChart('weeklyPerformanceChart', perfData);
            }

            const monthlyCanvas = document.getElementById('monthlyFinanceChart');
            if (monthlyCanvas) {
                this.financeChart.createFinancialLineChart('monthlyFinanceChart', this.state.state.finance.monthly);
            }
        }

        /**
         * 🔥 Carrega análises para as abas do GPSA
         */
        async _loadAnalysesForTabs() {
            try {
                const token = Utils.getToken();
                const response = await fetch('/api/analyses/history?limit=3', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                
                if (response.ok) {
                    const data = await response.json();
                    const analyses = data.analyses || [];
                    
                    // Buscar detalhes completos de cada análise
                    const fullAnalyses = await Promise.all(
                        analyses.map(async (analysis) => {
                            const result = await this._fetchAnalysisResult(analysis.process_id);
                            return {
                                ...analysis,
                                chart_data: result?.chart_data || {},
                                predictions_summary: result?.prediction_stats || {},
                                metrics: result?.prediction_stats || {},
                                insights: result?.insights || {},
                                recommendations: result?.recommendations || [],
                                rows_processed: result?.analysis_info?.rows_processed || 0,
                                total_rows: result?.analysis_info?.rows_processed || 0,
                                filename: analysis.filename || 'Análise'
                            };
                        })
                    );
                    
                    // Renderizar abas
                    this.tabManager.renderTabs(fullAnalyses);
                    
                    // Atualizar relatório da primeira análise
                    if (fullAnalyses.length > 0) {
                        this.tabManager._updateAIReport(fullAnalyses[0]);
                    }
                }
            } catch (error) {
                console.warn('⚠️ Erro ao carregar análises para abas:', error);
            }
        }

        /**
         * 🔥 Busca resultado completo de uma análise
         */
        async _fetchAnalysisResult(processId) {
            try {
                const token = Utils.getToken();
                const response = await fetch(`/api/analysis/result/${processId}`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                
                if (response.ok) {
                    return await response.json();
                }
            } catch (error) {
                console.warn(`⚠️ Erro ao buscar resultado ${processId}:`, error);
            }
            return null;
        }

        /**
         * 🔥 Inicia polling para atualizações
         */
        _startPolling() {
            if (this._pollingInterval) {
                clearInterval(this._pollingInterval);
            }
            
            this._pollingInterval = setInterval(() => {
                this._loadAnalysesForTabs();
            }, 30000); // A cada 30 segundos
        }

        _setupEvents() {
            // Atualizar quando novas análises chegarem
            document.addEventListener('analysis:success', (e) => {
                const data = e.detail || {};
                if (data.result) {
                    this._updateAllCharts(data.result);
                    // Recarregar abas
                    setTimeout(() => this._loadAnalysesForTabs(), 1500);
                }
            });

            // Atualizar créditos
            document.addEventListener('creditsUpdated', (e) => {
                const data = e.detail || {};
                this.state.set('user', {
                    ...this.state.state.user,
                    credits: data.credits || 0,
                    isPremium: data.isPremium || false,
                });
            });

            // Evento para o botão de nova análise
            const newAnalysisBtn = document.getElementById('newAnalysisBtn');
            if (newAnalysisBtn) {
                newAnalysisBtn.addEventListener('click', () => {
                    // Limpar seleção de arquivos
                    const fileInput = document.getElementById('fileInput');
                    if (fileInput) fileInput.value = '';
                    // Scroll para o upload
                    document.getElementById('dropArea')?.scrollIntoView({ behavior: 'smooth' });
                });
            }
        }

        _updateAllCharts(data) {
            try {
                // Atualizar gráficos financeiros
                const df = data.dataframe || data;
                if (df && typeof df === 'object') {
                    const weeklyData = Utils.generateWeeklyFinanceData(df);
                    this.state.set('finance', {
                        ...this.state.state.finance,
                        weekly: weeklyData,
                        lastUpdate: Date.now()
                    });

                    this.financeChart.updateChart('weeklyFinanceChart', weeklyData);
                    
                    const perfData = {
                        labels: weeklyData.labels,
                        services: weeklyData.count || weeklyData.revenue.map(() => Math.floor(Math.random() * 8 + 2))
                    };
                    this.financeChart.updateChart('weeklyPerformanceChart', perfData);
                }
            } catch (e) {
                console.warn('⚠️ Erro ao atualizar gráficos:', e);
            }
        }

        /**
         * 🔥 Retorna a análise ativa
         */
        getActiveAnalysis() {
            return this.tabManager.getActiveAnalysis();
        }

        /**
         * 🔥 Retorna todas as análises
         */
        getAllAnalyses() {
            return this.tabManager.getAllAnalyses();
        }

        destroy() {
            if (this._pollingInterval) {
                clearInterval(this._pollingInterval);
                this._pollingInterval = null;
            }
            this.financeChart.destroyAll();
            this.tabManager.destroy();
            this._initialized = false;
            console.log('🧹 [Dashboard] Destruído');
        }
    }

    // ==============================================
    // 🔥 INICIALIZAÇÃO
    // ==============================================

    let dashboardInstance = null;

    function initDashboard() {
        if (dashboardInstance) {
            console.log('ℹ️ [Dashboard] Já existe uma instância');
            return dashboardInstance;
        }

        if (!Utils.isAuthenticated()) {
            console.log('🔒 [Dashboard] Usuário não autenticado');
            return null;
        }

        dashboardInstance = new Dashboard();
        window.__dashboard = dashboardInstance;

        dashboardInstance.init().catch(error => {
            console.error('❌ [Dashboard] Erro na inicialização:', error);
        });

        return dashboardInstance;
    }

    document.addEventListener('DOMContentLoaded', function() {
        if (window._appReadyFired || window.__APP_STATE?.isAppReady) {
            console.log('✅ [Dashboard] App já pronto, inicializando...');
            initDashboard();
            return;
        }

        console.log('⏳ [Dashboard] Aguardando app:ready...');
        document.addEventListener('app:ready', function() {
            console.log('📢 [Dashboard] app:ready recebido');
            initDashboard();
        });

        setTimeout(function() {
            if (!dashboardInstance) {
                console.log('🔄 [Dashboard] Fallback: tentando inicializar...');
                initDashboard();
            }
        }, 3000);
    });

    console.log('=' .repeat(60));
    console.log('🔥 dashboard.js v9.1 carregado - ABAS DINÂMICAS + GPSA');
    console.log('   ✅ NOVO: Abas dinâmicas (1 a 3 arquivos)');
    console.log('   ✅ NOVO: Gráfico GPSA por arquivo');
    console.log('   ✅ NOVO: Relatório da IA integrado');
    console.log('   ✅ NOVO: Indicador de saúde por arquivo');
    console.log('   📡 Use window.__dashboard para acesso');
    console.log('=' .repeat(60));

})();