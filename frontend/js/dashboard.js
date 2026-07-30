// frontend/js/dashboard.js - VERSÃO 11.0 COM ANÁLISE MÚLTIPLA
/**
 * 🔥 Dashboard Module - AutoAnalytics v11.0
 * 
 * ✅ NOVO: Upload múltiplo com relatório executivo
 * ✅ NOVO: Processamento de análise da IA
 * ✅ NOVO: Renderização do relatório executivo
 * ✅ NOVO: Download de relatório em PDF
 * ✅ NOVO: Score Executivo com cards visuais
 * ✅ NOVO: Recomendações priorizadas
 * ✅ NOVO: Previsão e tendência
 * ✅ NOVO: Conclusão geral
 * 
 * 🎨 DESIGN PROFISSIONAL:
 * ✅ Cards com gradientes e efeitos glassmorphism
 * ✅ Animações suaves e transições
 * ✅ Métricas com ícones e KPIs em tempo real
 * ✅ Tabs elegantes com indicadores visuais
 * ✅ Relatório da IA com formatação rica
 */

(function() {
    'use strict';

    // ==============================================
    // 🔥 CONFIGURAÇÕES PROFISSIONAIS
    // ==============================================

    const CONFIG = {
        MAX_FILES_PER_BATCH: 3,
        MAX_FILE_SIZE_KB: 200,
        API_BASE: '/api',
        POLLING_INTERVAL: 30000,
        CREDITS_CHECK_INTERVAL: 30000,
        HISTORY_LIMIT: 3,
        
        COLORS: {
            primary: '#ff6b35',
            primaryDark: '#e55a2b',
            secondary: '#4a9eff',
            success: '#48bb78',
            warning: '#f5a623',
            danger: '#f56565',
            purple: '#9f7aea',
            teal: '#38b2ac',
            pink: '#ed64a6',
            indigo: '#667eea',
            
            gradient: {
                primary: 'linear-gradient(135deg, #ff6b35 0%, #f56565 100%)',
                secondary: 'linear-gradient(135deg, #4a9eff 0%, #667eea 100%)',
                success: 'linear-gradient(135deg, #48bb78 0%, #38b2ac 100%)',
                warning: 'linear-gradient(135deg, #f5a623 0%, #ed64a6 100%)',
                danger: 'linear-gradient(135deg, #f56565 0%, #ed64a6 100%)',
                purple: 'linear-gradient(135deg, #9f7aea 0%, #667eea 100%)',
            },
            
            glass: {
                bg: 'rgba(255,255,255,0.03)',
                border: 'rgba(255,255,255,0.06)',
                shadow: '0 8px 32px rgba(0,0,0,0.3)',
            },
            
            text: {
                primary: '#ffffff',
                secondary: 'rgba(255,255,255,0.7)',
                tertiary: 'rgba(255,255,255,0.4)',
                muted: 'rgba(255,255,255,0.2)',
            }
        },
        
        ANIMATION: {
            duration: 500,
            easing: 'cubic-bezier(0.4, 0, 0.2, 1)',
        },
        
        WAIT_FOR_APP_TIMEOUT: 8000,
        WAIT_FOR_APP_INTERVAL: 200,
    };

    // ==============================================
    // 🔥 UTILITÁRIOS AVANÇADOS
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
            if (!bytes || bytes < 0) return '0 B';
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

        formatNumber: (value) => {
            if (value === undefined || value === null || isNaN(value)) return '0';
            return value.toLocaleString('pt-BR');
        },

        formatPercentage: (value) => {
            if (value === undefined || value === null || isNaN(value)) return '0%';
            return (value * 100).toFixed(0) + '%';
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
            if (score >= 0.7) return { 
                status: 'excelente', 
                color: '#48bb78', 
                icon: '🟢', 
                label: 'Excelente',
                bg: 'rgba(72,187,120,0.15)',
                border: 'rgba(72,187,120,0.3)',
            };
            if (score >= 0.5) return { 
                status: 'bom', 
                color: '#4a9eff', 
                icon: '🔵', 
                label: 'Bom',
                bg: 'rgba(74,158,255,0.15)',
                border: 'rgba(74,158,255,0.3)',
            };
            if (score >= 0.3) return { 
                status: 'regular', 
                color: '#f5a623', 
                icon: '🟡', 
                label: 'Regular',
                bg: 'rgba(245,166,35,0.15)',
                border: 'rgba(245,166,35,0.3)',
            };
            return { 
                status: 'critico', 
                color: '#f56565', 
                icon: '🔴', 
                label: 'Crítico',
                bg: 'rgba(245,101,101,0.15)',
                border: 'rgba(245,101,101,0.3)',
            };
        },

        sleep: (ms) => new Promise(resolve => setTimeout(resolve, ms)),

        // 🔥 CORRIGIDO: Função de token mais robusta
        getToken: () => {
            try {
                const token = localStorage.getItem('access_token');
                if (token && token !== 'undefined' && token !== 'null' && token.length > 10) {
                    return token;
                }
                
                const sessionToken = sessionStorage.getItem('access_token');
                if (sessionToken && sessionToken !== 'undefined' && sessionToken !== 'null' && sessionToken.length > 10) {
                    return sessionToken;
                }
                
                if (window.__APP_STATE && window.__APP_STATE.token) {
                    return window.__APP_STATE.token;
                }
                
                return null;
            } catch (e) {
                console.warn('⚠️ Erro ao obter token:', e);
                return null;
            }
        },

        // 🔥 CORRIGIDO: Verificação de autenticação mais robusta
        isAuthenticated: () => {
            const token = Utils.getToken();
            if (token) return true;
            
            if (window.appAuth && typeof window.appAuth.isAuthenticated === 'function') {
                try {
                    return window.appAuth.isAuthenticated();
                } catch (e) {}
            }
            
            if (window.App && typeof window.App.isAuthenticated === 'function') {
                try {
                    return window.App.isAuthenticated();
                } catch (e) {}
            }
            
            if (window.__APP_STATE && window.__APP_STATE.isAuthenticated === true) {
                return true;
            }
            
            return false;
        },

        generateId: () => {
            return Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
        },

        // ==============================================
        // 🔥 ANIMAÇÕES
        // ==============================================

        animateElement: (element, animation, duration = 500) => {
            if (!element) return;
            element.style.animation = 'none';
            element.offsetHeight;
            element.style.animation = `${animation} ${duration}ms ${CONFIG.ANIMATION.easing} forwards`;
        },

        fadeIn: (element, duration = 500) => {
            if (!element) return;
            element.style.opacity = '0';
            element.style.transition = `opacity ${duration}ms ${CONFIG.ANIMATION.easing}`;
            requestAnimationFrame(() => {
                element.style.opacity = '1';
            });
        },

        fadeOut: (element, duration = 300) => {
            if (!element) return;
            element.style.opacity = '1';
            element.style.transition = `opacity ${duration}ms ${CONFIG.ANIMATION.easing}`;
            requestAnimationFrame(() => {
                element.style.opacity = '0';
            });
        },

        // ==============================================
        // 🔥 DADOS FINANCEIROS
        // ==============================================

        generateWeeklyFinanceData: (data) => {
            const days = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'];
            
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
            const days = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'];
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
        // 🔥 DADOS GPSA PROFISSIONAL
        // ==============================================

        generateGPSAData: (analysisData) => {
            const days = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'];
            
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
                    health: healthStatus,
                    bestDay: servicesData.indexOf(Math.max(...servicesData)),
                    worstDay: servicesData.indexOf(Math.min(...servicesData)),
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
    // 🔥 DASHBOARD METRICS - CARDS PROFISSIONAIS
    // ==============================================

    class DashboardMetrics {
        constructor() {
            this._metrics = {};
            this._container = document.getElementById('metricsContainer');
        }

        renderMetrics(data) {
            if (!this._container) return;

            const metrics = this._extractMetrics(data);
            this._metrics = metrics;

            let html = `
                <div class="metrics-grid" style="
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 1rem;
                    margin-bottom: 1.5rem;
                ">
            `;

            const metricCards = [
                {
                    icon: '📊',
                    label: 'Score Médio',
                    value: Utils.formatPercentage(metrics.avgScore),
                    color: Utils.getScoreColor(metrics.avgScore),
                    gradient: metrics.avgScore >= 0.7 ? CONFIG.COLORS.gradient.success : 
                              metrics.avgScore >= 0.4 ? CONFIG.COLORS.gradient.warning : 
                              CONFIG.COLORS.gradient.danger,
                    subtitle: Utils.getScoreLabel(metrics.avgScore),
                },
                {
                    icon: '💰',
                    label: 'Receita Total',
                    value: Utils.formatCurrency(metrics.totalRevenue),
                    color: '#48bb78',
                    gradient: CONFIG.COLORS.gradient.success,
                    subtitle: `+${Utils.formatCurrency(metrics.profit)} lucro`,
                },
                {
                    icon: '🔧',
                    label: 'Serviços',
                    value: Utils.formatNumber(metrics.totalServices),
                    color: '#4a9eff',
                    gradient: CONFIG.COLORS.gradient.secondary,
                    subtitle: metrics.bestDay !== undefined ? `Pico na ${['Seg','Ter','Qua','Qui','Sex','Sáb','Dom'][metrics.bestDay]}` : '',
                },
                {
                    icon: '📈',
                    label: 'Margem',
                    value: metrics.margin + '%',
                    color: metrics.margin > 30 ? '#48bb78' : metrics.margin > 15 ? '#f5a623' : '#f56565',
                    gradient: metrics.margin > 30 ? CONFIG.COLORS.gradient.success : 
                              metrics.margin > 15 ? CONFIG.COLORS.gradient.warning : 
                              CONFIG.COLORS.gradient.danger,
                    subtitle: metrics.margin > 30 ? '✅ Saudável' : metrics.margin > 15 ? '⚠️ Moderada' : '🔴 Baixa',
                }
            ];

            metricCards.forEach((card, index) => {
                html += `
                    <div class="metric-card" style="
                        background: ${CONFIG.COLORS.glass.bg};
                        backdrop-filter: blur(12px);
                        border: 1px solid ${CONFIG.COLORS.glass.border};
                        border-radius: 16px;
                        padding: 1.2rem 1.5rem;
                        position: relative;
                        overflow: hidden;
                        transition: all 0.3s ease;
                        cursor: default;
                        animation: fadeInUp 0.6s ease ${index * 0.1}s both;
                    ">
                        <div style="
                            position: absolute;
                            top: -50%;
                            right: -30%;
                            width: 100%;
                            height: 100%;
                            background: ${card.gradient};
                            opacity: 0.03;
                            border-radius: 50%;
                            pointer-events: none;
                        "></div>
                        
                        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;">
                            <span style="font-size: 1.8rem;">${card.icon}</span>
                            <span style="
                                font-size: 0.65rem;
                                color: ${CONFIG.COLORS.text.tertiary};
                                background: rgba(255,255,255,0.05);
                                padding: 0.2rem 0.6rem;
                                border-radius: 20px;
                                border: 1px solid rgba(255,255,255,0.05);
                            ">${card.label}</span>
                        </div>
                        
                        <div style="
                            font-size: 2rem;
                            font-weight: 700;
                            color: ${card.color};
                            line-height: 1.2;
                            margin-bottom: 0.2rem;
                            text-shadow: 0 0 40px rgba(${card.color}, 0.1);
                        ">${card.value}</div>
                        
                        <div style="
                            font-size: 0.7rem;
                            color: ${CONFIG.COLORS.text.tertiary};
                            display: flex;
                            align-items: center;
                            gap: 0.4rem;
                        ">
                            <span style="
                                display: inline-block;
                                width: 6px;
                                height: 6px;
                                border-radius: 50%;
                                background: ${card.color};
                                opacity: 0.5;
                            "></span>
                            ${card.subtitle}
                        </div>
                    </div>
                `;
            });

            html += '</div>';
            this._container.innerHTML = html;
            this._injectStyles();
        }

        _extractMetrics(data) {
            const metrics = data?.metrics || {};
            const chartData = data?.chart_data || {};
            const weekly = chartData.weekly || {};

            const revenue = weekly.revenue || [];
            const costs = weekly.costs || [];
            const services = weekly.services || weekly.count || [];

            const totalRevenue = revenue.reduce((a, b) => a + b, 0);
            const totalCosts = costs.reduce((a, b) => a + b, 0);
            const totalServices = services.reduce((a, b) => a + b, 0);
            const profit = totalRevenue - totalCosts;

            return {
                avgScore: metrics.mean_prediction || 0.65,
                totalRevenue: totalRevenue,
                totalCosts: totalCosts,
                totalServices: totalServices || 0,
                profit: profit,
                margin: totalRevenue > 0 ? (profit / totalRevenue) * 100 : 0,
                bestDay: services.indexOf(Math.max(...services)),
                worstDay: services.indexOf(Math.min(...services)),
            };
        }

        _injectStyles() {
            if (document.getElementById('dashboard-metrics-styles')) return;

            const styles = document.createElement('style');
            styles.id = 'dashboard-metrics-styles';
            styles.textContent = `
                @keyframes fadeInUp {
                    from {
                        opacity: 0;
                        transform: translateY(20px) scale(0.95);
                    }
                    to {
                        opacity: 1;
                        transform: translateY(0) scale(1);
                    }
                }

                .metric-card:hover {
                    transform: translateY(-2px);
                    border-color: rgba(255,255,255,0.15);
                    box-shadow: 0 12px 40px rgba(0,0,0,0.3);
                }

                .metric-card:hover > div:first-child {
                    opacity: 0.08;
                    transform: scale(1.2);
                    transition: all 0.5s ease;
                }

                @media (max-width: 640px) {
                    .metrics-grid {
                        grid-template-columns: repeat(2, 1fr) !important;
                        gap: 0.75rem !important;
                    }
                    .metric-card {
                        padding: 1rem !important;
                    }
                }
            `;
            document.head.appendChild(styles);
        }

        updateMetrics(data) {
            this.renderMetrics(data);
        }
    }

    // ==============================================
    // 🔥 GPSA CHART RENDERER
    // ==============================================

    class GPSAChartRenderer {
        constructor() {
            this._chartInstances = {};
        }

        createGPSAChart(canvasId, data, options = {}) {
            const canvas = document.getElementById(canvasId);
            if (!canvas) {
                console.warn(`⚠️ [GPSA] Canvas ${canvasId} não encontrado`);
                return null;
            }

            if (typeof Chart === 'undefined') {
                console.warn('⚠️ Chart.js não carregado');
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

            const gradientPlugin = {
                id: 'gradientPlugin',
                beforeDraw: function(chart) {
                    const ctx = chart.ctx;
                    const chartArea = chart.chartArea;
                    if (!chartArea) return;
                    const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
                    gradient.addColorStop(0, 'rgba(255,107,53,0.4)');
                    gradient.addColorStop(1, 'rgba(255,107,53,0.0)');
                    if (chart.data.datasets[0]) {
                        chart.data.datasets[0].backgroundColor = gradient;
                    }
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
                            pointRadius: 6,
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
                            pointRadius: 5,
                            pointBackgroundColor: '#4a9eff',
                            pointBorderColor: '#ffffff',
                            pointBorderWidth: 2,
                            borderWidth: 2.5,
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
                            pointRadius: 4,
                            pointBackgroundColor: '#48bb78',
                            pointBorderColor: '#ffffff',
                            pointBorderWidth: 1.5,
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
                            pointRadius: 4,
                            pointBackgroundColor: '#f56565',
                            pointBorderColor: '#ffffff',
                            pointBorderWidth: 1.5,
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
                                color: 'rgba(255,255,255,0.5)',
                                font: {
                                    size: 10,
                                    weight: '600',
                                    family: 'Inter, sans-serif',
                                },
                                boxWidth: 12,
                                padding: 12,
                                usePointStyle: true,
                                pointStyle: 'circle',
                            },
                            position: 'top',
                        },
                        tooltip: {
                            backgroundColor: 'rgba(15,15,25,0.92)',
                            titleColor: '#ffffff',
                            bodyColor: '#e2e8f0',
                            borderColor: 'rgba(255,255,255,0.08)',
                            borderWidth: 1,
                            padding: 16,
                            cornerRadius: 12,
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
                        }
                    },
                    scales: {
                        x: {
                            grid: {
                                color: 'rgba(255,255,255,0.04)',
                                drawBorder: false,
                            },
                            ticks: {
                                color: 'rgba(255,255,255,0.4)',
                                font: {
                                    size: 11,
                                    weight: '500',
                                }
                            }
                        },
                        y1: {
                            position: 'left',
                            min: 0,
                            max: 1,
                            grid: {
                                color: 'rgba(255,255,255,0.04)',
                                drawBorder: false,
                            },
                            ticks: {
                                color: 'rgba(255,255,255,0.4)',
                                font: {
                                    size: 10,
                                },
                                callback: function(value) {
                                    return (value * 100).toFixed(0) + '%';
                                }
                            },
                            title: {
                                display: true,
                                text: 'Score de Risco',
                                color: 'rgba(255,255,255,0.3)',
                                font: {
                                    size: 9,
                                    weight: '600',
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
                                    size: 10,
                                },
                                stepSize: 1,
                                beginAtZero: true,
                            },
                            title: {
                                display: true,
                                text: 'Serviços',
                                color: 'rgba(255,255,255,0.3)',
                                font: {
                                    size: 9,
                                    weight: '600',
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
                                    size: 10,
                                },
                                callback: function(value) {
                                    return Utils.formatCurrencyShort(value);
                                }
                            },
                            title: {
                                display: true,
                                text: 'Valores (R$)',
                                color: 'rgba(255,255,255,0.3)',
                                font: {
                                    size: 9,
                                    weight: '600',
                                }
                            }
                        }
                    },
                    animation: {
                        duration: 1200,
                        easing: 'easeOutQuart'
                    }
                },
                plugins: [gradientPlugin]
            });

            this._chartInstances[canvasId] = chart;
            return chart;
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
    // 🔥 TAB MANAGER PROFISSIONAL
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
            this._aiReportContainer = document.getElementById('aiReportContent');
            this._metrics = new DashboardMetrics();
        }

        renderTabs(analyses) {
            if (!analyses || analyses.length === 0) {
                this._showPlaceholder();
                return;
            }

            const maxTabs = 3;
            const recentAnalyses = analyses.slice(0, maxTabs);
            const validAnalyses = recentAnalyses.filter(a => a.chart_data && Object.keys(a.chart_data).length > 0);
            
            if (validAnalyses.length === 0) {
                this._showPlaceholder();
                return;
            }

            this._hidePlaceholder();
            this._tabs = validAnalyses;
            this._renderTabHeaders(validAnalyses);
            this._renderTabContents(validAnalyses);
            this._activateTab(0);

            if (validAnalyses.length > 0) {
                this._metrics.renderMetrics(validAnalyses[0]);
            }
        }

        _renderTabHeaders(analyses) {
            if (!this._tabList) return;
            
            let html = '';
            const icons = ['📊', '📈', '📉'];
            const colors = ['#ff6b35', '#4a9eff', '#48bb78'];
            
            analyses.forEach((analysis, index) => {
                const isActive = index === 0;
                const icon = icons[index % icons.length];
                const color = colors[index % colors.length];
                
                const filename = analysis.filename || `Arquivo ${index + 1}`;
                const shortName = filename.length > 20 ? filename.substring(0, 18) + '...' : filename;
                const rows = analysis.rows_processed || analysis.total_rows || 0;
                const score = analysis.metrics?.mean_prediction || 0.5;
                const health = Utils.getHealthStatus(score);
                
                html += `
                    <li class="nav-item" role="presentation" style="
                        margin: 0 0.15rem;
                        flex: 0 0 auto;
                    ">
                        <button class="nav-link ${isActive ? 'active' : ''}" 
                                id="gpsa-tab-${index}" 
                                data-bs-toggle="tab" 
                                data-bs-target="#gpsa-content-${index}" 
                                type="button" 
                                role="tab" 
                                aria-controls="gpsa-content-${index}" 
                                aria-selected="${isActive ? 'true' : 'false'}"
                                style="
                                    color: ${isActive ? '#ffffff' : 'rgba(255,255,255,0.4)'};
                                    border: none;
                                    background: ${isActive ? 'rgba(255,255,255,0.06)' : 'transparent'};
                                    border-radius: 12px;
                                    padding: 0.6rem 1.2rem;
                                    font-size: 0.75rem;
                                    font-weight: 600;
                                    transition: all 0.3s ease;
                                    position: relative;
                                    display: flex;
                                    align-items: center;
                                    gap: 0.5rem;
                                    border: 1px solid ${isActive ? 'rgba(255,255,255,0.08)' : 'transparent'};
                                "
                                data-filename="${filename}">
                            <span style="font-size: 1rem;">${icon}</span>
                            ${shortName}
                            <span style="
                                font-size: 0.5rem;
                                background: ${isActive ? 'rgba(255,255,255,0.06)' : 'rgba(255,255,255,0.03)'};
                                padding: 0.15rem 0.5rem;
                                border-radius: 10px;
                                color: ${isActive ? 'rgba(255,255,255,0.4)' : 'rgba(255,255,255,0.2)'};
                            ">
                                ${rows}
                            </span>
                            <span style="
                                display: inline-block;
                                width: 6px;
                                height: 6px;
                                border-radius: 50%;
                                background: ${health.color};
                                box-shadow: 0 0 12px ${health.color}40;
                            "></span>
                            ${isActive ? `
                                <span style="
                                    position: absolute;
                                    bottom: -1px;
                                    left: 20%;
                                    right: 20%;
                                    height: 2px;
                                    background: linear-gradient(90deg, ${color}, ${color}80);
                                    border-radius: 2px;
                                "></span>
                            ` : ''}
                        </button>
                    </li>
                `;
            });
            
            this._tabList.innerHTML = html;
            
            this._tabList.querySelectorAll('.nav-link').forEach((btn, index) => {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    this._activateTab(index);
                });
            });
        }

        _renderTabContents(analyses) {
            if (!this._tabContent) return;
            
            let html = '';
            
            analyses.forEach((analysis, index) => {
                const isActive = index === 0;
                const filename = analysis.filename || `Arquivo ${index + 1}`;
                const rows = analysis.rows_processed || analysis.total_rows || 0;
                
                html += `
                    <div class="tab-pane fade ${isActive ? 'show active' : ''}" 
                         id="gpsa-content-${index}" 
                         role="tabpanel" 
                         aria-labelledby="gpsa-tab-${index}"
                         style="
                            padding: 0.5rem 0;
                            animation: ${isActive ? 'fadeInTab 0.5s ease' : 'none'};
                         ">
                        <div style="
                            background: rgba(255,255,255,0.02);
                            border-radius: 16px;
                            padding: 1rem;
                            border: 1px solid rgba(255,255,255,0.04);
                        ">
                            <div style="height: 300px; position: relative;">
                                <canvas id="gpsaChart-${index}"></canvas>
                            </div>
                            <div class="mt-2 d-flex justify-content-between align-items-center" style="padding: 0 0.5rem;">
                                <small style="color:rgba(255,255,255,0.15); font-size:0.6rem;">
                                    <i class="fas fa-file-alt me-1"></i> 
                                    ${filename}
                                </small>
                                <small style="color:rgba(255,255,255,0.10); font-size:0.55rem;">
                                    ${rows} registros • ${analysis.model_used || 'AutoML'}
                                </small>
                            </div>
                        </div>
                    </div>
                `;
            });
            
            this._tabContent.innerHTML = html;
            
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
            
            if (analyses.length > 0) {
                this._updateHealthIndicator(analyses[0]);
            }

            this._injectTabStyles();
        }

        _activateTab(index) {
            if (index < 0 || index >= this._tabs.length) return;
            
            this._activeTab = index;
            
            const tabs = this._tabList.querySelectorAll('.nav-link');
            const contents = this._tabContent.querySelectorAll('.tab-pane');
            
            tabs.forEach((tab, i) => {
                const isActive = i === index;
                tab.classList.toggle('active', isActive);
                tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
                tab.style.color = isActive ? '#ffffff' : 'rgba(255,255,255,0.4)';
                tab.style.background = isActive ? 'rgba(255,255,255,0.06)' : 'transparent';
                tab.style.border = isActive ? '1px solid rgba(255,255,255,0.08)' : '1px solid transparent';
                
                const oldIndicator = tab.querySelector('span:last-child');
                if (oldIndicator && oldIndicator.style.position === 'absolute') {
                    oldIndicator.remove();
                }
                
                if (isActive) {
                    const color = ['#ff6b35', '#4a9eff', '#48bb78'][i % 3];
                    const indicator = document.createElement('span');
                    indicator.style.cssText = `
                        position: absolute;
                        bottom: -1px;
                        left: 20%;
                        right: 20%;
                        height: 2px;
                        background: linear-gradient(90deg, ${color}, ${color}80);
                        border-radius: 2px;
                    `;
                    tab.appendChild(indicator);
                }
            });
            
            contents.forEach((content, i) => {
                const isActive = i === index;
                content.classList.toggle('show', isActive);
                content.classList.toggle('active', isActive);
                if (isActive) {
                    content.style.animation = 'fadeInTab 0.5s ease';
                }
            });
            
            if (this._tabs[index]) {
                this._updateHealthIndicator(this._tabs[index]);
                this._updateAIReport(this._tabs[index]);
                this._metrics.updateMetrics(this._tabs[index]);
            }
            
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
            }, 150);
        }

        _updateHealthIndicator(analysis) {
            if (!this._healthIndicator) return;
            
            const metrics = analysis.predictions_summary || analysis.metrics || {};
            const score = metrics.mean_prediction || 0.5;
            const health = Utils.getHealthStatus(score);
            
            const filename = analysis.filename || 'Arquivo';
            const shortName = filename.length > 15 ? filename.substring(0, 12) + '...' : filename;
            
            this._healthIndicator.style.cssText = `
                display: inline-flex;
                align-items: center;
                gap: 0.5rem;
                background: ${health.bg};
                color: ${health.color};
                border: 1px solid ${health.border};
                border-radius: 20px;
                padding: 0.3rem 1rem;
                font-size: 0.7rem;
                font-weight: 600;
                transition: all 0.3s ease;
                box-shadow: 0 0 20px ${health.color}15;
            `;
            this._healthIndicator.innerHTML = `
                <span style="font-size: 0.8rem;">${health.icon}</span>
                ${health.label}
                <span style="opacity:0.5; font-weight:400;">•</span>
                <span style="opacity:0.5; font-weight:400;">${shortName}</span>
                <span style="
                    background: ${health.color}20;
                    padding: 0.1rem 0.4rem;
                    border-radius: 10px;
                    font-size: 0.55rem;
                ">${(score * 100).toFixed(0)}%</span>
            `;
        }

        _updateAIReport(analysis) {
            if (!this._aiReportContainer) return;
            
            const insights = analysis.insights || {};
            const recommendations = analysis.recommendations || [];
            const metrics = analysis.predictions_summary || analysis.metrics || {};
            const filename = analysis.filename || 'Análise';
            const rows = analysis.rows_processed || analysis.total_rows || 0;
            const score = metrics.mean_prediction || 0.65;
            const highRisk = metrics.high_risk_percentage || 0;
            const lowRisk = metrics.low_risk_percentage || 0;
            const health = Utils.getHealthStatus(score);
            
            let html = `
                <div style="
                    background: rgba(255,255,255,0.02);
                    border-radius: 16px;
                    padding: 1.2rem;
                    border: 1px solid rgba(255,255,255,0.04);
                    height: 100%;
                ">
                    <div style="
                        display: flex;
                        align-items: center;
                        justify-content: space-between;
                        margin-bottom: 0.8rem;
                    ">
                        <div style="display: flex; align-items: center; gap: 0.5rem;">
                            <span style="
                                font-size: 1.2rem;
                                background: ${health.bg};
                                padding: 0.3rem;
                                border-radius: 10px;
                            ">📊</span>
                            <div>
                                <div style="
                                    font-size: 0.8rem;
                                    font-weight: 600;
                                    color: #ffffff;
                                ">${filename}</div>
                                <div style="
                                    font-size: 0.6rem;
                                    color: rgba(255,255,255,0.3);
                                ">${rows} registros • Score ${(score * 100).toFixed(0)}%</div>
                            </div>
                        </div>
                        <div style="
                            display: flex;
                            align-items: center;
                            gap: 0.3rem;
                            background: ${health.bg};
                            padding: 0.2rem 0.6rem;
                            border-radius: 12px;
                            border: 1px solid ${health.border};
                        ">
                            <span>${health.icon}</span>
                            <span style="
                                font-size: 0.6rem;
                                font-weight: 600;
                                color: ${health.color};
                            ">${health.label}</span>
                        </div>
                    </div>
            `;
            
            if (insights && Object.keys(insights).length > 0) {
                const summary = insights.summary || {};
                const riskDist = insights.risk_distribution || {};
                
                html += `
                    <div style="
                        display: grid;
                        grid-template-columns: repeat(3, 1fr);
                        gap: 0.5rem;
                        margin-bottom: 0.8rem;
                    ">
                        <div style="
                            background: rgba(255,255,255,0.03);
                            padding: 0.4rem 0.6rem;
                            border-radius: 8px;
                            text-align: center;
                        ">
                            <div style="font-size: 0.45rem; color: rgba(255,255,255,0.2);">MÉDIA</div>
                            <div style="font-size: 1rem; font-weight: 700; color: #48bb78;">
                                ${(summary.mean * 100).toFixed(0)}%
                            </div>
                        </div>
                        <div style="
                            background: rgba(255,255,255,0.03);
                            padding: 0.4rem 0.6rem;
                            border-radius: 8px;
                            text-align: center;
                        ">
                            <div style="font-size: 0.45rem; color: rgba(255,255,255,0.2);">ALTO RISCO</div>
                            <div style="font-size: 1rem; font-weight: 700; color: #f56565;">
                                ${(riskDist.high_percentage || 0).toFixed(0)}%
                            </div>
                        </div>
                        <div style="
                            background: rgba(255,255,255,0.03);
                            padding: 0.4rem 0.6rem;
                            border-radius: 8px;
                            text-align: center;
                        ">
                            <div style="font-size: 0.45rem; color: rgba(255,255,255,0.2);">BAIXO RISCO</div>
                            <div style="font-size: 1rem; font-weight: 700; color: #48bb78;">
                                ${(riskDist.low_percentage || 0).toFixed(0)}%
                            </div>
                        </div>
                    </div>
                `;
            }
            
            if (recommendations && recommendations.length > 0) {
                html += `
                    <div style="
                        margin-top: 0.5rem;
                        padding-top: 0.5rem;
                        border-top: 1px solid rgba(255,255,255,0.04);
                    ">
                        <div style="
                            font-size: 0.5rem;
                            color: rgba(255,255,255,0.2);
                            text-transform: uppercase;
                            letter-spacing: 0.05em;
                            margin-bottom: 0.3rem;
                        ">📝 Recomendações</div>
                        <ul style="
                            margin: 0;
                            padding-left: 1rem;
                            font-size: 0.65rem;
                            color: rgba(255,255,255,0.5);
                            line-height: 1.6;
                            list-style: none;
                        ">
                            ${recommendations.slice(0, 3).map(r => `
                                <li style="
                                    position: relative;
                                    padding: 0.15rem 0 0.15rem 1rem;
                                    border-bottom: 1px solid rgba(255,255,255,0.02);
                                ">
                                    <span style="
                                        position: absolute;
                                        left: 0;
                                        top: 0.15rem;
                                        color: ${CONFIG.COLORS.primary};
                                        font-size: 0.4rem;
                                    ">▸</span>
                                    ${r}
                                </li>
                            `).join('')}
                        </ul>
                    </div>
                `;
            }
            
            html += '</div>';
            this._aiReportContainer.innerHTML = html;
        }

        _showPlaceholder() {
            if (this._container) this._container.style.display = 'none';
            if (this._placeholder) {
                this._placeholder.style.display = 'block';
                this._placeholder.innerHTML = `
                    <div style="
                        display: flex;
                        flex-direction: column;
                        align-items: center;
                        justify-content: center;
                        padding: 3rem 2rem;
                        text-align: center;
                    ">
                        <div style="
                            font-size: 3rem;
                            margin-bottom: 1rem;
                            opacity: 0.3;
                        ">📊</div>
                        <h4 style="
                            color: rgba(255,255,255,0.3);
                            font-weight: 400;
                            margin-bottom: 0.5rem;
                        ">Nenhuma análise disponível</h4>
                        <p style="
                            color: rgba(255,255,255,0.15);
                            font-size: 0.8rem;
                            max-width: 400px;
                        ">
                            Faça upload de um arquivo para visualizar o gráfico GPSA
                            e as análises da IA
                        </p>
                    </div>
                `;
            }
            if (this._healthIndicator) {
                this._healthIndicator.style.cssText = `
                    display: inline-flex;
                    align-items: center;
                    gap: 0.5rem;
                    background: rgba(255,255,255,0.03);
                    color: rgba(255,255,255,0.3);
                    border: 1px solid rgba(255,255,255,0.05);
                    border-radius: 20px;
                    padding: 0.3rem 1rem;
                    font-size: 0.7rem;
                `;
                this._healthIndicator.innerHTML = '⏳ Aguardando dados...';
            }
            if (this._aiReportContainer) {
                this._aiReportContainer.innerHTML = `
                    <div style="
                        display: flex;
                        flex-direction: column;
                        align-items: center;
                        justify-content: center;
                        height: 100%;
                        min-height: 150px;
                        text-align: center;
                        opacity: 0.3;
                    ">
                        <span style="font-size: 2rem; margin-bottom: 0.5rem;">🧠</span>
                        <span style="font-size: 0.8rem;">Aguardando análise da IA...</span>
                    </div>
                `;
            }
            const metricsContainer = document.getElementById('metricsContainer');
            if (metricsContainer) {
                metricsContainer.innerHTML = '';
            }
        }

        _hidePlaceholder() {
            if (this._container) this._container.style.display = 'block';
            if (this._placeholder) this._placeholder.style.display = 'none';
        }

        _injectTabStyles() {
            if (document.getElementById('dashboard-tab-styles')) return;

            const styles = document.createElement('style');
            styles.id = 'dashboard-tab-styles';
            styles.textContent = `
                @keyframes fadeInTab {
                    from {
                        opacity: 0;
                        transform: translateY(10px);
                    }
                    to {
                        opacity: 1;
                        transform: translateY(0);
                    }
                }

                .nav-link {
                    position: relative;
                    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
                }

                .nav-link:hover:not(.active) {
                    color: rgba(255,255,255,0.6) !important;
                    background: rgba(255,255,255,0.03) !important;
                    border-color: rgba(255,255,255,0.05) !important;
                }

                .nav-link.active {
                    box-shadow: 0 4px 20px rgba(0,0,0,0.2);
                }

                .tab-pane {
                    transition: all 0.4s ease;
                }

                .tab-pane.fade {
                    transition: opacity 0.3s ease, transform 0.3s ease;
                }
            `;
            document.head.appendChild(styles);
        }

        getActiveAnalysis() {
            if (this._tabs && this._tabs[this._activeTab]) {
                return this._tabs[this._activeTab];
            }
            return null;
        }

        getAllAnalyses() {
            return this._tabs;
        }

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
            this.tabManager = new TabManager();
            this._initialized = false;
            this._pollingInterval = null;
            this._metrics = new DashboardMetrics();
            this._uploadStatusTimeout = null;
        }

        async init() {
            if (this._initialized) {
                console.log('ℹ️ [Dashboard] Já inicializado');
                return this;
            }

            console.log('🚀 [Dashboard v11.0] Inicializando com análise múltipla...');

            await this._waitForApp();
            this.state.syncWithApp();
            this._setupEvents();

            await this._loadAnalysesForTabs();
            this._startPolling();

            // 🔥 Configurar upload
            this._setupUploadHandlers();

            this._initialized = true;

            console.log('✅ [Dashboard v11.0] Inicializado com sucesso!');
            console.log('   📊 Upload múltiplo com relatório executivo');

            return this;
        }

        // ==========================================
        // 🔥 WAIT FOR APP
        // ==========================================

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

        // ==========================================
        // 🔥 LOAD ANALYSES FOR TABS
        // ==========================================

        async _loadAnalysesForTabs() {
            try {
                const token = Utils.getToken();
                if (!token) {
                    console.warn('⚠️ [Dashboard] Sem token para carregar análises');
                    return;
                }

                const response = await fetch('/api/analyses/history?limit=3', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                
                if (response.ok) {
                    const data = await response.json();
                    const analyses = data.analyses || [];
                    
                    const fullAnalyses = await Promise.all(
                        analyses.map(async (analysis) => {
                            const result = await this._fetchAnalysisResult(analysis.process_id);
                            return {
                                ...analysis,
                                chart_data: result?.chart_data || {},
                                predictions_summary: result?.prediction_stats || {},
                                metrics: result?.prediction_stats || { mean_prediction: 0.65 },
                                insights: result?.insights || {},
                                recommendations: result?.recommendations || [],
                                rows_processed: result?.analysis_info?.rows_processed || 0,
                                total_rows: result?.analysis_info?.rows_processed || 0,
                                filename: analysis.filename || 'Análise',
                                model_used: result?.analysis_info?.model_used || 'AutoML'
                            };
                        })
                    );
                    
                    this.tabManager.renderTabs(fullAnalyses);
                    
                    if (fullAnalyses.length > 0) {
                        this.tabManager._updateAIReport(fullAnalyses[0]);
                    }
                }
            } catch (error) {
                console.warn('⚠️ Erro ao carregar análises para abas:', error);
            }
        }

        async _fetchAnalysisResult(processId) {
            try {
                const token = Utils.getToken();
                if (!token) return null;
                
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

        // ==========================================
        // 🔥 POLLING
        // ==========================================

        _startPolling() {
            if (this._pollingInterval) {
                clearInterval(this._pollingInterval);
            }
            
            this._pollingInterval = setInterval(() => {
                this._loadAnalysesForTabs();
            }, CONFIG.POLLING_INTERVAL);
        }

        // ==========================================
        // 🔥 SETUP EVENTS
        // ==========================================

        _setupEvents() {
            document.addEventListener('analysis:success', (e) => {
                const data = e.detail || {};
                if (data.result) {
                    setTimeout(() => this._loadAnalysesForTabs(), 1500);
                }
            });

            document.addEventListener('creditsUpdated', (e) => {
                const data = e.detail || {};
                this.state.set('user', {
                    ...this.state.state.user,
                    credits: data.credits || 0,
                    isPremium: data.isPremium || false,
                });
                this._updateCreditDisplay(data.credits || 0);
            });
        }

        // ==========================================
        // 🔥 SETUP UPLOAD HANDLERS
        // ==========================================

        _setupUploadHandlers() {
            const fileInput = document.getElementById('fileInput');
            const dropArea = document.getElementById('dropArea');
            const uploadBtn = document.querySelector('.btn-select');

            // Botão de seleção
            if (uploadBtn) {
                uploadBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    if (fileInput) fileInput.click();
                });
            }

            // Input de arquivos
            if (fileInput) {
                fileInput.addEventListener('change', (e) => {
                    const files = Array.from(e.target.files);
                    if (files.length > 0) {
                        this.uploadMultipleFiles(files);
                    }
                    e.target.value = ''; // Reset
                });
            }

            // Drop area
            if (dropArea) {
                dropArea.addEventListener('dragover', (e) => {
                    e.preventDefault();
                    dropArea.classList.add('dragover');
                });

                dropArea.addEventListener('dragleave', (e) => {
                    e.preventDefault();
                    dropArea.classList.remove('dragover');
                });

                dropArea.addEventListener('drop', (e) => {
                    e.preventDefault();
                    dropArea.classList.remove('dragover');
                    const files = Array.from(e.dataTransfer.files);
                    if (files.length > 0) {
                        this.uploadMultipleFiles(files);
                    }
                });
            }

            // Botão PDF
            const pdfBtn = document.getElementById('downloadPdfBtn');
            if (pdfBtn) {
                pdfBtn.addEventListener('click', () => {
                    this._downloadReport();
                });
            }

            // Botão Nova Análise
            const newAnalysisBtn = document.getElementById('newAnalysisBtn');
            if (newAnalysisBtn) {
                newAnalysisBtn.addEventListener('click', () => {
                    this._resetUploadArea();
                });
            }
        }

        // ==========================================
        // 🔥 UPLOAD MÚLTIPLO DE ARQUIVOS
        // ==========================================

        async uploadMultipleFiles(files) {
            try {
                const token = Utils.getToken();
                if (!token) {
                    this._showToast('❌ Token de autenticação não encontrado. Faça login novamente.', 'error');
                    return null;
                }

                // Validar número de arquivos
                if (files.length === 0) {
                    this._showToast('⚠️ Selecione pelo menos um arquivo.', 'warning');
                    return null;
                }

                if (files.length > CONFIG.MAX_FILES_PER_BATCH) {
                    this._showToast(`⚠️ Máximo de ${CONFIG.MAX_FILES_PER_BATCH} arquivos por vez.`, 'warning');
                    return null;
                }

                // Validar tamanho dos arquivos
                for (const file of files) {
                    if (file.size > CONFIG.MAX_FILE_SIZE_KB * 1024) {
                        this._showToast(`⚠️ Arquivo ${file.name} excede ${CONFIG.MAX_FILE_SIZE_KB}KB.`, 'warning');
                        return null;
                    }
                }

                // Validar extensões
                const allowedExtensions = ['.csv', '.xlsx', '.xls', '.tsv'];
                for (const file of files) {
                    const ext = '.' + file.name.split('.').pop().toLowerCase();
                    if (!allowedExtensions.includes(ext)) {
                        this._showToast(`⚠️ Arquivo ${file.name} não é suportado. Use: ${allowedExtensions.join(', ')}`, 'warning');
                        return null;
                    }
                }

                // Atualizar UI - Mostrar status de upload
                this._showUploadStatus('⏳', 'Enviando arquivos...', 'Aguarde, estamos processando seus dados', 10);
                this.state.set('ui', {
                    isUploading: true,
                    progress: 10,
                    status: 'uploading',
                    message: 'Enviando arquivos...'
                });

                // Criar FormData
                const formData = new FormData();
                for (const file of files) {
                    formData.append('files', file);
                }
                formData.append('analysis_type', 'auto');
                formData.append('report_format', 'html');

                // Headers
                const headers = {
                    'Authorization': `Bearer ${token}`
                };

                // PoW headers
                const powNonce = localStorage.getItem('pow_nonce');
                const powChallenge = localStorage.getItem('pow_challenge');
                if (powNonce && powChallenge) {
                    headers['X-PoW-Nonce'] = powNonce;
                    headers['X-PoW-Challenge'] = powChallenge;
                    headers['X-PoW-Difficulty'] = '4';
                }

                // 🔥 CHAMAR O ENDPOINT /upload-multi-analyze
                this._showUploadStatus('⏳', 'Processando análise...', 'A IA está analisando seus dados', 30);

                const response = await fetch('/api/upload-multi-analyze', {
                    method: 'POST',
                    headers: headers,
                    body: formData
                });

                // Processar resposta
                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.detail?.message || errorData.message || 'Erro no upload');
                }

                const result = await response.json();

                // Atualizar UI - Sucesso
                this._showUploadStatus('✅', 'Análise concluída!', 'Veja o relatório abaixo', 100);
                this.state.set('ui', {
                    isUploading: false,
                    progress: 100,
                    status: 'completed',
                    message: 'Análise concluída!'
                });

                // Processar o resultado
                await this._processMultiAnalysisResult(result);

                // Disparar evento
                document.dispatchEvent(new CustomEvent('analysis:success', {
                    detail: { result: result }
                }));

                // Atualizar créditos
                if (result.credits) {
                    this._updateCreditDisplay(result.credits.remaining);
                }

                // Mostrar toast de sucesso
                this._showToast('✅ Análise concluída com sucesso!', 'success');

                // Mostrar resultado
                this._showResult();

                return result;

            } catch (error) {
                console.error('❌ [Dashboard] Erro no upload:', error);
                
                this.state.set('ui', {
                    isUploading: false,
                    status: 'error',
                    message: error.message || 'Erro ao processar'
                });

                this._showUploadStatus('❌', 'Erro', error.message || 'Falha no processamento', 0);
                this._showToast(`❌ ${error.message || 'Erro ao processar'}`, 'error');
                
                return null;
            }
        }

        // ==========================================
        // 🔥 PROCESSAR RESULTADO DA ANÁLISE
        // ==========================================

        async _processMultiAnalysisResult(result) {
            if (!result || !result.success) {
                console.warn('⚠️ Resultado vazio ou inválido');
                return;
            }

            const { analysis, report, chart_data, credits } = result;

            // Extrair dados
            const executiveScore = analysis?.executive_score || {};
            const executiveSummary = analysis?.executive_summary || '';
            const recommendations = analysis?.recommendations || [];
            const forecast = analysis?.forecast || '';
            const generalConclusion = analysis?.general_conclusion || '';
            const comparison = analysis?.comparison || {};
            const trend = analysis?.trend || {};

            // 1. Atualizar relatório da IA
            await this._updateAIReport({
                executive_score: executiveScore,
                executive_summary: executiveSummary,
                recommendations: recommendations,
                forecast: forecast,
                general_conclusion: generalConclusion,
                comparison: comparison,
                trend: trend,
                chart_data: chart_data || {}
            });

            // 2. Atualizar métricas
            await this._updateMetrics({
                executive_score: executiveScore,
                chart_data: chart_data || {}
            });

            // 3. Renderizar abas GPSA
            if (result.data?.files && result.data.files.length > 0) {
                const analyses = result.data.files.map((file, index) => ({
                    filename: file.filename || `Arquivo ${index + 1}`,
                    success: file.success || false,
                    rows_processed: file.rows || 0,
                    metrics: {
                        mean_prediction: file.metrics?.mean_prediction || 0.5,
                        high_risk_percentage: file.metrics?.high_risk_percentage || 0,
                        low_risk_percentage: file.metrics?.low_risk_percentage || 0
                    },
                    chart_data: chart_data || {},
                    insights: {
                        summary: {
                            mean: file.metrics?.mean_prediction || 0.5
                        },
                        risk_distribution: {
                            high_percentage: file.metrics?.high_risk_percentage || 0,
                            low_percentage: file.metrics?.low_risk_percentage || 0
                        }
                    },
                    recommendations: recommendations,
                    predictions: file.predictions || [],
                    model_used: file.model_used || 'AutoML'
                }));

                this.tabManager.renderTabs(analyses);
            }

            // 4. Mostrar resultado
            this._showResult();

            console.log('✅ Análise múltipla processada com sucesso!');
        }

        // ==========================================
        // 🔥 ATUALIZAR RELATÓRIO DA IA
        // ==========================================

        async _updateAIReport(data) {
            const reportContainer = document.getElementById('aiReportContent');
            if (!reportContainer) return;

            const {
                executive_score,
                executive_summary,
                recommendations,
                forecast,
                general_conclusion,
                comparison,
                trend
            } = data;

            let html = '';

            // 1. Score Executivo
            if (executive_score && Object.keys(executive_score).length > 0) {
                const scoreItems = [
                    { key: 'saude_financeira', label: 'Saúde Financeira', icon: '💰' },
                    { key: 'eficiencia', label: 'Eficiência', icon: '⚡' },
                    { key: 'controle_custos', label: 'Controle de Custos', icon: '📊' },
                    { key: 'crescimento', label: 'Crescimento', icon: '📈' },
                    { key: 'nivel_risco', label: 'Nível de Risco', icon: '🛡️' },
                    { key: 'nota_geral', label: 'Nota Geral', icon: '🏆' }
                ];

                html += `
                    <div style="margin-bottom: 1rem;">
                        <strong style="color: #ff6b35;">🏆 Score Executivo</strong>
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 0.5rem; margin-top: 0.5rem;">
                            ${scoreItems.map(({ key, label, icon }) => {
                                const value = executive_score[key];
                                if (value === undefined || value === null) return '';
                                
                                const isNumber = typeof value === 'number';
                                const color = isNumber ? 
                                    (value >= 7 ? '#48bb78' : value >= 5 ? '#f5a623' : '#f56565') : 
                                    (value === 'Baixo' ? '#48bb78' : value === 'Moderado' ? '#f5a623' : '#f56565');
                                
                                return `
                                    <div style="background: rgba(0,0,0,0.1); padding: 0.4rem; border-radius: 8px; text-align: center; border: 1px solid rgba(255,255,255,0.03);">
                                        <div style="font-size: 0.4rem; color: rgba(255,255,255,0.3); text-transform: uppercase; letter-spacing: 0.3px;">${label}</div>
                                        <div style="font-size: 1rem; font-weight: 700; color: ${color};">
                                            ${icon} ${isNumber ? value.toFixed(1) : value}
                                        </div>
                                    </div>
                                `;
                            }).join('')}
                        </div>
                    </div>
                `;
            }

            // 2. Resumo Executivo
            if (executive_summary) {
                html += `
                    <div style="margin-bottom: 0.8rem; padding: 0.8rem; background: rgba(255,107,53,0.05); border-radius: 8px; border-left: 3px solid #ff6b35;">
                        <strong style="color: #ff6b35;">📋 Resumo Executivo</strong>
                        <div style="font-size: 0.8rem; color: rgba(255,255,255,0.7); margin-top: 0.3rem; line-height: 1.5;">
                            ${executive_summary}
                        </div>
                    </div>
                `;
            }

            // 3. Comparação
            if (comparison && Object.keys(comparison).length > 0) {
                const compItems = [
                    { key: 'best_revenue', label: 'Melhor Receita', icon: '💰' },
                    { key: 'best_profit', label: 'Melhor Lucro', icon: '💵' },
                    { key: 'best_growth', label: 'Melhor Crescimento', icon: '📈' },
                    { key: 'highest_risk', label: 'Maior Risco', icon: '⚠️' }
                ];

                html += `
                    <div style="margin-bottom: 0.8rem; padding: 0.6rem; background: rgba(74,158,255,0.05); border-radius: 8px; border-left: 3px solid #4a9eff;">
                        <strong style="color: #4a9eff;">📊 Comparação</strong>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.3rem; margin-top: 0.3rem;">
                            ${compItems.map(({ key, label, icon }) => {
                                const value = comparison[key];
                                return value ? `
                                    <div style="font-size: 0.65rem; color: rgba(255,255,255,0.5);">
                                        ${icon} ${label}: <strong style="color: rgba(255,255,255,0.8);">${value}</strong>
                                    </div>
                                ` : '';
                            }).join('')}
                        </div>
                    </div>
                `;
            }

            // 4. Tendência
            if (trend && trend.description) {
                const directionEmoji = trend.direction === 'crescente' ? '📈' : 
                                       trend.direction === 'decrescente' ? '📉' : '➡️';
                const color = trend.direction === 'crescente' ? '#48bb78' : 
                              trend.direction === 'decrescente' ? '#f56565' : '#f5a623';
                
                html += `
                    <div style="margin-bottom: 0.8rem; padding: 0.6rem; background: rgba(245,166,35,0.05); border-radius: 8px; border-left: 3px solid ${color};">
                        <strong style="color: ${color};">${directionEmoji} Tendência: ${trend.direction.charAt(0).toUpperCase() + trend.direction.slice(1)}</strong>
                        <div style="font-size: 0.75rem; color: rgba(255,255,255,0.6); margin-top: 0.2rem;">
                            ${trend.description}
                        </div>
                        ${trend.key_observations && trend.key_observations.length > 0 ? `
                            <div style="margin-top: 0.2rem; font-size: 0.65rem; color: rgba(255,255,255,0.3);">
                                ${trend.key_observations.map(o => `• ${o}`).join(' ')}
                            </div>
                        ` : ''}
                    </div>
                `;
            }

            // 5. Recomendações Priorizadas
            if (recommendations && recommendations.length > 0) {
                const priorityEmojis = {
                    'alta': '🔴',
                    'media': '🟡',
                    'baixa': '🟢'
                };
                
                const priorityColors = {
                    'alta': '#f56565',
                    'media': '#f5a623',
                    'baixa': '#48bb78'
                };

                html += `
                    <div style="margin-bottom: 0.8rem;">
                        <strong style="color: #ff6b35;">🎯 Recomendações Priorizadas</strong>
                        <ul style="margin: 0.3rem 0 0 0; padding-left: 0; list-style: none; font-size: 0.75rem; color: rgba(255,255,255,0.6);">
                            ${recommendations.slice(0, 5).map(r => {
                                const priority = r.priority || 'media';
                                const emoji = priorityEmojis[priority] || '📌';
                                const color = priorityColors[priority] || '#ff6b35';
                                const desc = r.description || r;
                                const category = r.category || 'geral';
                                const impact = r.expected_impact || '';
                                const effort = r.effort || 'medio';
                                
                                return `
                                    <li style="padding: 0.3rem 0.4rem; border-bottom: 1px solid rgba(255,255,255,0.03); display: flex; align-items: flex-start; gap: 0.5rem;">
                                        <span style="color: ${color}; font-size: 0.6rem; margin-top: 0.1rem;">${emoji}</span>
                                        <div style="flex: 1;">
                                            <div>${typeof desc === 'string' ? desc : desc.description || ''}</div>
                                            <div style="display: flex; gap: 0.5rem; margin-top: 0.1rem; font-size: 0.55rem; color: rgba(255,255,255,0.2);">
                                                <span>📂 ${category}</span>
                                                ${impact ? `<span>💥 ${impact}</span>` : ''}
                                                <span>⚡ ${effort}</span>
                                            </div>
                                        </div>
                                    </li>
                                `;
                            }).join('')}
                        </ul>
                    </div>
                `;
            }

            // 6. Previsão
            if (forecast) {
                html += `
                    <div style="margin-bottom: 0.5rem; padding: 0.5rem; background: rgba(74,158,255,0.05); border-radius: 6px; border-left: 3px solid #4a9eff;">
                        <strong style="color: #4a9eff;">🔮 Previsão</strong>
                        <div style="font-size: 0.75rem; color: rgba(255,255,255,0.6); margin-top: 0.2rem;">
                            ${forecast}
                        </div>
                    </div>
                `;
            }

            // 7. Conclusão Geral
            if (general_conclusion) {
                html += `
                    <div style="padding: 0.5rem; background: rgba(255,255,255,0.02); border-radius: 6px; border-top: 1px solid rgba(255,255,255,0.05);">
                        <strong style="color: #ff6b35;">📌 Conclusão Geral</strong>
                        <div style="font-size: 0.75rem; color: rgba(255,255,255,0.5); margin-top: 0.2rem; line-height: 1.5;">
                            ${general_conclusion}
                        </div>
                    </div>
                `;
            }

            reportContainer.innerHTML = html || '<div style="color: rgba(255,255,255,0.3); font-size: 0.8rem; text-align: center; padding: 1rem;">Análise concluída com sucesso</div>';
        }

        // ==========================================
        // 🔥 ATUALIZAR MÉTRICAS
        // ==========================================

        async _updateMetrics(data) {
            const { executive_score, chart_data } = data;

            const metricsContainer = document.getElementById('resultMetrics');
            if (!metricsContainer) return;

            const score = executive_score?.nota_geral || executive_score?.saude_financeira || 0;
            const revenue = chart_data?.weekly?.revenue?.reduce((a, b) => a + b, 0) || 0;
            const services = chart_data?.performance?.services?.reduce((a, b) => a + b, 0) || 0;
            const risk = executive_score?.nivel_risco || 'Moderado';
            const margin = chart_data?.weekly?.revenue?.length > 0 ? 
                Math.round((revenue - (chart_data?.weekly?.costs?.reduce((a, b) => a + b, 0) || 0)) / revenue * 100) : 0;

            const metrics = [
                { value: typeof score === 'number' ? score.toFixed(1) : score, label: 'Score Geral', icon: '📊' },
                { value: typeof revenue === 'number' ? 'R$ ' + (revenue / 1000).toFixed(1) + 'k' : revenue, label: 'Receita Total', icon: '💰' },
                { value: typeof services === 'number' ? services.toFixed(0) : services, label: 'Serviços', icon: '🔧' },
                { value: margin + '%', label: 'Margem', icon: '📈' }
            ];

            metricsContainer.innerHTML = metrics.map(m => `
                <div class="result-stat">
                    <div class="stat-value" style="color: ${m.label === 'Margem' && parseInt(m.value) > 30 ? '#48bb78' : m.label === 'Margem' && parseInt(m.value) < 15 ? '#f56565' : '#ff6b35'}">
                        ${m.icon} ${m.value}
                    </div>
                    <div class="stat-label">${m.label}</div>
                </div>
            `).join('');
        }

        // ==========================================
        // 🔥 UI HELPERS
        // ==========================================

        _showUploadStatus(icon, title, subtitle, progress) {
            const statusEl = document.getElementById('analysisStatus');
            if (!statusEl) return;

            statusEl.classList.add('show');
            document.getElementById('statusIcon').textContent = icon;
            document.getElementById('statusText').textContent = title;
            document.getElementById('statusSub').textContent = subtitle || '';
            
            const progressBar = document.getElementById('statusProgressBar');
            if (progressBar && progress !== undefined) {
                progressBar.style.width = Math.min(100, progress) + '%';
            }
        }

        _showResult() {
            const resultContainer = document.getElementById('resultContainer');
            const resultPlaceholder = document.getElementById('resultPlaceholder');
            
            if (resultContainer) {
                resultContainer.classList.add('show');
                resultContainer.style.display = 'block';
            }
            if (resultPlaceholder) {
                resultPlaceholder.style.display = 'none';
            }
        }

        _showToast(message, type = 'info') {
            if (window.toastr) {
                const methods = {
                    'success': toastr.success,
                    'error': toastr.error,
                    'warning': toastr.warning,
                    'info': toastr.info
                };
                const method = methods[type] || toastr.info;
                method(message, '', { timeOut: 5000, closeButton: true });
            } else {
                console.log(`[${type}] ${message}`);
            }
        }

        _updateCreditDisplay(credits) {
            const elements = document.querySelectorAll('#creditsCount, #uploadCredits, #creditsDisplay');
            elements.forEach(el => {
                if (el) el.textContent = credits;
            });
        }

        _resetUploadArea() {
            // Limpar seleção de arquivos
            const fileInput = document.getElementById('fileInput');
            if (fileInput) fileInput.value = '';
            
            // Limpar preview
            const previewContainer = document.getElementById('filePreviewContainer');
            if (previewContainer) previewContainer.innerHTML = '';
            
            // Reset status
            const statusEl = document.getElementById('analysisStatus');
            if (statusEl) statusEl.classList.remove('show');
            
            // Scroll para o upload
            const dropArea = document.getElementById('dropArea');
            if (dropArea) dropArea.scrollIntoView({ behavior: 'smooth' });
        }

        // ==========================================
        // 🔥 DOWNLOAD DE RELATÓRIO
        // ==========================================

        async _downloadReport() {
            try {
                this._showToast('⏳ Gerando PDF do relatório...', 'info');

                const activeAnalysis = this.tabManager.getActiveAnalysis();
                if (!activeAnalysis) {
                    this._showToast('⚠️ Nenhuma análise ativa para gerar PDF.', 'warning');
                    return;
                }

                // Buscar dados da análise
                const token = Utils.getToken();
                if (!token) {
                    this._showToast('❌ Token não encontrado.', 'error');
                    return;
                }

                const response = await fetch(`/api/analysis/result/${activeAnalysis.process_id || activeAnalysis.id}`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });

                if (!response.ok) {
                    throw new Error('Erro ao buscar dados da análise');
                }

                const data = await response.json();

                // Preparar dados para o PDF
                const analysisData = {
                    metrics: data.prediction_stats || {},
                    predictions: data.predictions || [],
                    insights: data.insights || {},
                    recommendations: data.recommendations || [],
                    chart_data: data.chart_data || {},
                    filename: data.filename || 'Análise',
                    ai_report: data.ai_report || ''
                };

                // Gerar PDF
                if (window.generateFinancePDF) {
                    window.generateFinancePDF(analysisData);
                } else {
                    // Fallback: usar a função global
                    const pdfBtn = document.getElementById('downloadPdfBtn');
                    if (pdfBtn) pdfBtn.click();
                }

                this._showToast('✅ PDF gerado com sucesso!', 'success');

            } catch (error) {
                console.error('❌ Erro ao gerar PDF:', error);
                this._showToast(`❌ ${error.message || 'Erro ao gerar PDF'}`, 'error');
            }
        }

        // ==========================================
        // 🔥 MÉTODOS PÚBLICOS
        // ==========================================

        getActiveAnalysis() {
            return this.tabManager.getActiveAnalysis();
        }

        getAllAnalyses() {
            return this.tabManager.getAllAnalyses();
        }

        destroy() {
            if (this._pollingInterval) {
                clearInterval(this._pollingInterval);
                this._pollingInterval = null;
            }
            if (this._uploadStatusTimeout) {
                clearTimeout(this._uploadStatusTimeout);
                this._uploadStatusTimeout = null;
            }
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
    console.log('🔥 dashboard.js v11.0 carregado - ANÁLISE MÚLTIPLA INTEGRADA');
    console.log('   ✅ Upload múltiplo com relatório executivo');
    console.log('   ✅ Score Executivo com cards visuais');
    console.log('   ✅ Recomendações priorizadas');
    console.log('   ✅ Previsão e tendência');
    console.log('   ✅ Download de relatório em PDF');
    console.log('   📡 Use window.__dashboard para acesso');
    console.log('=' .repeat(60));

})();