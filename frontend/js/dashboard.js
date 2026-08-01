// frontend/js/dashboard.js - VERSÃO 14.0 (COM INATIVIDADE E LIMPEZA)
/**
 * 🔥 Dashboard Module - AutoAnalytics v14.0
 * 
 * ✅ CORREÇÕES CRÍTICAS:
 * - 🔥 PoW CORRIGIDO: Usa getSolutionForUpload() em vez de getSolution()
 * - 🔥 Múltiplos níveis de fallback para PoW (5 níveis)
 * - 🔥 Renovação automática de PoW em caso de erro 428
 * - 🔥 Tratamento robusto de erros com retry inteligente
 * 
 * ✅ MELHORIAS:
 * - 📊 Upload com progresso detalhado
 * - 🔄 Retry automático com backoff exponencial
 * - 💾 Cache com invalidação inteligente
 * - 📈 Métricas em tempo real
 * - 🎯 Recomendações priorizadas
 * - 📥 Exportação de dados
 * - 🛡️ Segurança aprimorada
 * 
 * ✅ NOVAS FUNCIONALIDADES:
 * - 🔄 Renovação automática de PoW
 * - 📊 Dashboard com métricas em tempo real
 * - 📈 Gráficos GPSA interativos
 * - 📄 Relatório executivo da IA
 * - 🎯 Recomendações priorizadas
 * - 📥 Exportação de dados
 * - 🔄 Polling inteligente com backoff
 * - 💾 Cache local com IndexedDB
 * - 🚀 Upload com progresso
 * - ⏰ Sistema de inatividade com limpeza automática
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
        POLLING_BACKOFF: {
            initial: 30000,
            max: 120000,
            factor: 1.5
        },
        CREDITS_CHECK_INTERVAL: 30000,
        HISTORY_LIMIT: 3,
        CACHE_TTL: 300000, // 5 minutos
        MAX_RETRIES: 3,
        RETRY_DELAY: 1000,
        POW_MAX_ATTEMPTS: 3,
        POW_RETRY_DELAY: 1000,
        
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
            let lastResult = null;
            return (...args) => {
                if (!inThrottle) {
                    lastResult = fn.apply(this, args);
                    inThrottle = true;
                    setTimeout(() => inThrottle = false, limit);
                }
                return lastResult;
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
                
                if (window.auth && typeof window.auth.getToken === 'function') {
                    try {
                        const authToken = window.auth.getToken();
                        if (authToken && authToken.length > 10) return authToken;
                    } catch (e) {}
                }
                
                return null;
            } catch (e) {
                console.warn('⚠️ Erro ao obter token:', e);
                return null;
            }
        },

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
        // 🔥 CACHE COM INDEXEDDB
        // ==============================================

        cache: {
            _db: null,
            _dbName: 'AnalyticsCache',
            _storeName: 'analyses',
            
            async init() {
                if (this._db) return this._db;
                
                return new Promise((resolve, reject) => {
                    const request = indexedDB.open(this._dbName, 1);
                    
                    request.onupgradeneeded = (event) => {
                        const db = event.target.result;
                        if (!db.objectStoreNames.contains(this._storeName)) {
                            const store = db.createObjectStore(this._storeName, { keyPath: 'id' });
                            store.createIndex('timestamp', 'timestamp');
                            store.createIndex('userId', 'userId');
                        }
                    };
                    
                    request.onsuccess = (event) => {
                        this._db = event.target.result;
                        resolve(this._db);
                    };
                    
                    request.onerror = (event) => {
                        reject(event.target.error);
                    };
                });
            },
            
            async get(key) {
                try {
                    const db = await this.init();
                    return new Promise((resolve, reject) => {
                        const transaction = db.transaction([this._storeName], 'readonly');
                        const store = transaction.objectStore(this._storeName);
                        const request = store.get(key);
                        
                        request.onsuccess = () => {
                            const data = request.result;
                            if (data && data.timestamp && (Date.now() - data.timestamp) < CONFIG.CACHE_TTL) {
                                resolve(data.value);
                            } else {
                                resolve(null);
                            }
                        };
                        request.onerror = () => reject(request.error);
                    });
                } catch (e) {
                    console.warn('⚠️ Cache get error:', e);
                    return null;
                }
            },
            
            async set(key, value, userId = 'default') {
                try {
                    const db = await this.init();
                    return new Promise((resolve, reject) => {
                        const transaction = db.transaction([this._storeName], 'readwrite');
                        const store = transaction.objectStore(this._storeName);
                        const request = store.put({
                            id: key,
                            value: value,
                            userId: userId,
                            timestamp: Date.now()
                        });
                        
                        request.onsuccess = () => resolve(true);
                        request.onerror = () => reject(request.error);
                    });
                } catch (e) {
                    console.warn('⚠️ Cache set error:', e);
                    return false;
                }
            },
            
            async clear() {
                try {
                    const db = await this.init();
                    return new Promise((resolve, reject) => {
                        const transaction = db.transaction([this._storeName], 'readwrite');
                        const store = transaction.objectStore(this._storeName);
                        const request = store.clear();
                        
                        request.onsuccess = () => resolve(true);
                        request.onerror = () => reject(request.error);
                    });
                } catch (e) {
                    console.warn('⚠️ Cache clear error:', e);
                    return false;
                }
            }
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
    // 🔥 CACHE MANAGER
    // ==============================================

    class CacheManager {
        constructor() {
            this._memoryCache = new Map();
            this._initialized = false;
        }

        async init() {
            if (this._initialized) return;
            try {
                await Utils.cache.init();
                this._initialized = true;
                console.log('✅ Cache Manager inicializado');
            } catch (e) {
                console.warn('⚠️ Cache Manager fallback para memória:', e);
                this._initialized = true;
            }
        }

        async get(key) {
            if (this._memoryCache.has(key)) {
                const entry = this._memoryCache.get(key);
                if (Date.now() - entry.timestamp < CONFIG.CACHE_TTL) {
                    return entry.value;
                }
                this._memoryCache.delete(key);
            }

            try {
                const value = await Utils.cache.get(key);
                if (value !== null) {
                    this._memoryCache.set(key, {
                        value: value,
                        timestamp: Date.now()
                    });
                }
                return value;
            } catch (e) {
                return null;
            }
        }

        async set(key, value, userId = 'default') {
            this._memoryCache.set(key, {
                value: value,
                timestamp: Date.now()
            });

            try {
                await Utils.cache.set(key, value, userId);
            } catch (e) {
                console.warn('⚠️ Erro ao salvar em cache:', e);
            }
        }

        async clear() {
            this._memoryCache.clear();
            try {
                await Utils.cache.clear();
            } catch (e) {
                console.warn('⚠️ Erro ao limpar cache:', e);
            }
        }
    }

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
            this._initialized = false;
            this._cleanupInterval = null;
        }

        async init() {
            if (this._initialized) return;
            
            let attempts = 0;
            while (typeof Chart === 'undefined' && attempts < 20) {
                await Utils.sleep(200);
                attempts++;
            }
            
            if (typeof Chart === 'undefined') {
                console.warn('⚠️ Chart.js não carregado após timeout');
                return;
            }
            
            this._initialized = true;
            // 🔥 Iniciar limpeza automática de gráficos antigos
            this._startAutoCleanup();
            console.log('✅ GPSAChartRenderer inicializado');
        }

        // 🔥 NOVO: Limpeza automática de gráficos antigos
        _startAutoCleanup() {
            if (this._cleanupInterval) {
                clearInterval(this._cleanupInterval);
            }
            
            this._cleanupInterval = setInterval(() => {
                this._cleanupOldCharts();
            }, 5 * 60 * 1000); // A cada 5 minutos
        }

        _cleanupOldCharts() {
            const maxAge = 15 * 60 * 1000; // 15 minutos
            const now = Date.now();
            let removed = 0;

            Object.keys(this._chartInstances).forEach(key => {
                const chart = this._chartInstances[key];
                if (chart && chart._createdAt && (now - chart._createdAt) > maxAge) {
                    try {
                        chart.destroy();
                        delete this._chartInstances[key];
                        removed++;
                    } catch (e) {}
                }
            });

            if (removed > 0) {
                console.log(`🧹 ${removed} gráfico(s) removido(s) por inatividade`);
            }
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

            // 🔥 Marcar data de criação para limpeza
            chart._createdAt = Date.now();
            this._chartInstances[canvasId] = chart;
            return chart;
        }

        destroyAll() {
            if (this._cleanupInterval) {
                clearInterval(this._cleanupInterval);
                this._cleanupInterval = null;
            }
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
            this._initialized = false;
        }

        async init() {
            if (this._initialized) return;
            await this._chartRenderer.init();
            this._initialized = true;
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
                    setTimeout(() => {
                        this._chartRenderer.createGPSAChart(canvasId, gpsaData);
                    }, 100);
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
                                    ${typeof r === 'string' ? r : r.description || r}
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
            this.cache = new CacheManager();
            this._initialized = false;
            this._pollingInterval = null;
            this._pollingBackoff = CONFIG.POLLING_INTERVAL;
            this._metrics = new DashboardMetrics();
            this._uploadStatusTimeout = null;
            this._retryCount = 0;
            // 🔥 NOVO: Flag para controle de limpeza
            this._cleanupDone = false;
        }

        async init() {
            if (this._initialized) {
                console.log('ℹ️ [Dashboard] Já inicializado');
                return this;
            }

            console.log('🚀 [Dashboard v14.0] Inicializando com correções de PoW e inatividade...');

            await this.cache.init();
            await this.tabManager.init();

            await this._waitForApp();
            this.state.syncWithApp();
            this._setupEvents();

            await this._loadAnalysesForTabs();
            this._startPolling();
            this._setupUploadHandlers();

            // 🔥 NOVO: Registrar limpeza no InactivityManager
            this._setupInactivityCleanup();

            this._initialized = true;

            console.log('✅ [Dashboard v14.0] Inicializado com sucesso!');
            console.log('   🔥 PoW: CORRIGIDO com getSolutionForUpload()');
            console.log('   🔥 Fallback: 5 níveis de segurança');
            console.log('   🔥 Renovação automática de PoW');
            console.log('   📊 Upload múltiplo com relatório executivo');
            console.log('   💾 Cache ativo');
            console.log('   🔄 Polling com backoff');
            console.log('   ⏰ Inatividade: limpeza automática registrada');

            return this;
        }

        // ==========================================
        // 🔥 NOVO: SETUP INATIVIDADE
        // ==========================================

        _setupInactivityCleanup() {
            // 🔥 Verificar se o InactivityManager existe
            if (window.InactivityManager && typeof window.InactivityManager.registerCleanup === 'function') {
                // Registrar callback para limpeza do dashboard
                window.InactivityManager.registerCleanup(() => {
                    this._cleanupInactiveData();
                });
                console.log('✅ [Dashboard] Limpeza por inatividade registrada');
            } else {
                console.warn('⚠️ [Dashboard] InactivityManager não disponível');
            }
        }

        // ==========================================
        // 🔥 NOVO: LIMPEZA POR INATIVIDADE
        // ==========================================

        _cleanupInactiveData() {
            if (this._cleanupDone) return;
            this._cleanupDone = true;

            console.log('🧹 [Dashboard] Limpando dados por inatividade...');

            try {
                // 1. Limpar gráficos
                if (this.tabManager && this.tabManager._chartRenderer) {
                    this.tabManager._chartRenderer.destroyAll();
                    console.log('   ✅ Gráficos destruídos');
                }

                // 2. Limpar cache
                if (this.cache) {
                    this.cache.clear().catch(() => {});
                    console.log('   ✅ Cache limpo');
                }

                // 3. Limpar arquivos
                const fileInput = document.getElementById('fileInput');
                if (fileInput) fileInput.value = '';
                
                const previewContainer = document.getElementById('filePreviewContainer');
                if (previewContainer) previewContainer.innerHTML = '';
                console.log('   ✅ Arquivos limpos');

                // 4. Limpar abas
                const tabList = document.getElementById('gpsaTabs');
                if (tabList) tabList.innerHTML = '';
                
                const tabContent = document.getElementById('gpsaTabContent');
                if (tabContent) tabContent.innerHTML = '';
                console.log('   ✅ Abas limpas');

                // 5. Limpar métricas
                const metricsContainer = document.getElementById('metricsContainer');
                if (metricsContainer) metricsContainer.innerHTML = '';
                console.log('   ✅ Métricas limpas');

                // 6. Limpar relatório da IA
                const aiReport = document.getElementById('aiReportContent');
                if (aiReport) {
                    aiReport.innerHTML = `
                        <div style="color: rgba(255,255,255,0.3); font-size: 0.8rem; text-align: center; padding: 1rem;">
                            ⏰ Sessão expirada. Faça um novo upload para gerar o relatório.
                        </div>
                    `;
                    console.log('   ✅ Relatório da IA limpo');
                }

                // 7. Limpar health indicator
                const healthIndicator = document.getElementById('gpsaHealthIndicator');
                if (healthIndicator) {
                    healthIndicator.style.cssText = `
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
                    healthIndicator.innerHTML = '⏳ Sessão expirada';
                    console.log('   ✅ Health indicator limpo');
                }

                // 8. Esconder resultado
                const resultContainer = document.getElementById('resultContainer');
                if (resultContainer) {
                    resultContainer.classList.remove('show');
                    resultContainer.style.display = 'none';
                }
                const resultPlaceholder = document.getElementById('resultPlaceholder');
                if (resultPlaceholder) resultPlaceholder.style.display = 'block';
                console.log('   ✅ Resultado escondido');

                // 9. Limpar status
                const statusEl = document.getElementById('analysisStatus');
                if (statusEl) statusEl.classList.remove('show');
                console.log('   ✅ Status limpo');

                // 10. Resetar estado
                if (this.state) {
                    this.state.reset();
                    console.log('   ✅ Estado resetado');
                }

                // 11. Limpar área de upload
                const dropArea = document.getElementById('dropArea');
                if (dropArea) {
                    dropArea.classList.remove('success', 'error', 'uploading');
                }

                console.log('✅ [Dashboard] Limpeza por inatividade concluída');

            } catch (e) {
                console.warn('⚠️ [Dashboard] Erro na limpeza por inatividade:', e);
            }
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

                const cacheKey = `analyses_${this.state.state.user.email}`;
                let analyses = await this.cache.get(cacheKey);

                if (analyses) {
                    console.log('📦 [Dashboard] Usando cache de análises');
                    this._renderAnalyses(analyses);
                    this._fetchAnalysesInBackground(token, cacheKey);
                    return;
                }

                const response = await fetch('/api/analyses/history?limit=3', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                
                if (response.ok) {
                    const data = await response.json();
                    analyses = data.analyses || [];
                    await this.cache.set(cacheKey, analyses, this.state.state.user.email);
                    this._renderAnalyses(analyses);
                } else if (response.status === 404) {
                    console.warn('⚠️ [Dashboard] Rota /analyses/history não encontrada');
                    this._renderFallbackAnalyses();
                }
            } catch (error) {
                console.warn('⚠️ Erro ao carregar análises para abas:', error);
                this._renderFallbackAnalyses();
            }
        }

        async _fetchAnalysesInBackground(token, cacheKey) {
            try {
                const response = await fetch('/api/analyses/history?limit=3', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                
                if (response.ok) {
                    const data = await response.json();
                    const analyses = data.analyses || [];
                    await this.cache.set(cacheKey, analyses, this.state.state.user.email);
                    this._renderAnalyses(analyses);
                }
            } catch (error) {
                console.warn('⚠️ Erro no fetch em background:', error);
            }
        }

        _renderAnalyses(analyses) {
            if (!analyses || analyses.length === 0) {
                this.tabManager.renderTabs([]);
                return;
            }

            Promise.all(
                analyses.map(async (analysis) => {
                    try {
                        const result = await this._fetchAnalysisResult(analysis.process_id || analysis.id);
                        return {
                            ...analysis,
                            chart_data: result?.chart_data || {},
                            predictions_summary: result?.prediction_stats || {},
                            metrics: result?.prediction_stats || { mean_prediction: 0.65 },
                            insights: result?.insights || {},
                            recommendations: result?.recommendations || [],
                            rows_processed: result?.rows_processed || analysis.rows_processed || 0,
                            total_rows: result?.rows_processed || analysis.rows_processed || 0,
                            filename: analysis.filename || 'Análise',
                            model_used: result?.model_used || analysis.model_used || 'AutoML'
                        };
                    } catch (e) {
                        return analysis;
                    }
                })
            ).then(fullAnalyses => {
                this.tabManager.renderTabs(fullAnalyses);
                if (fullAnalyses.length > 0) {
                    this.tabManager._updateAIReport(fullAnalyses[0]);
                }
            });
        }

        _renderFallbackAnalyses() {
            try {
                const localAnalyses = JSON.parse(localStorage.getItem('recentAnalyses') || '[]');
                if (localAnalyses.length > 0) {
                    this.tabManager.renderTabs(localAnalyses);
                }
            } catch (e) {}
        }

        async _fetchAnalysisResult(processId) {
            try {
                const token = Utils.getToken();
                if (!token) return null;
                
                const cacheKey = `analysis_${processId}`;
                let result = await this.cache.get(cacheKey);
                
                if (result) {
                    return result;
                }
                
                const response = await fetch(`/api/analysis/result/${processId}`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                
                if (response.ok) {
                    result = await response.json();
                    await this.cache.set(cacheKey, result, this.state.state.user.email);
                    return result;
                }
            } catch (error) {
                console.warn(`⚠️ Erro ao buscar resultado ${processId}:`, error);
            }
            return null;
        }

        // ==========================================
        // 🔥 POLLING COM BACKOFF
        // ==========================================

        _startPolling() {
            if (this._pollingInterval) {
                clearInterval(this._pollingInterval);
            }
            
            this._pollingInterval = setInterval(() => {
                this._loadAnalysesForTabs();
                this._pollingBackoff = CONFIG.POLLING_INTERVAL;
            }, this._pollingBackoff);
        }

        _updatePollingBackoff() {
            this._pollingBackoff = Math.min(
                this._pollingBackoff * CONFIG.POLLING_BACKOFF.factor,
                CONFIG.POLLING_BACKOFF.max
            );
            
            if (this._pollingInterval) {
                clearInterval(this._pollingInterval);
                this._pollingInterval = setInterval(() => {
                    this._loadAnalysesForTabs();
                }, this._pollingBackoff);
            }
        }

        // ==========================================
        // 🔥 SETUP EVENTS
        // ==========================================

        _setupEvents() {
            document.addEventListener('analysis:success', (e) => {
                const data = e.detail || {};
                if (data.result) {
                    this.cache.clear();
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

            document.addEventListener('visibilitychange', () => {
                if (!document.hidden) {
                    this._loadAnalysesForTabs();
                }
            });

            // 🔥 Resetar timer de inatividade em eventos do dashboard
            const resetInactivity = () => {
                if (window.InactivityManager && typeof window.InactivityManager.resetTimer === 'function') {
                    window.InactivityManager.resetTimer();
                }
            };

            // Eventos que indicam atividade do usuário no dashboard
            const events = ['upload:started', 'analysis:success', 'tab:changed', 'chart:rendered'];
            events.forEach(event => {
                document.addEventListener(event, resetInactivity);
            });
        }

        // ==========================================
        // 🔥 SETUP UPLOAD HANDLERS
        // ==========================================

        _setupUploadHandlers() {
            const fileInput = document.getElementById('fileInput');
            const dropArea = document.getElementById('dropArea');
            const uploadBtn = document.querySelector('.btn-select');

            if (uploadBtn) {
                uploadBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    if (fileInput) fileInput.click();
                });
            }

            if (fileInput) {
                fileInput.addEventListener('change', (e) => {
                    const files = Array.from(e.target.files);
                    if (files.length > 0) {
                        this.uploadMultipleFiles(files);
                    }
                    e.target.value = '';
                });
            }

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

            const pdfBtn = document.getElementById('downloadPdfBtn');
            if (pdfBtn) {
                pdfBtn.addEventListener('click', () => {
                    this._downloadReport();
                });
            }

            const newAnalysisBtn = document.getElementById('newAnalysisBtn');
            if (newAnalysisBtn) {
                newAnalysisBtn.addEventListener('click', () => {
                    this._resetUploadArea();
                });
            }
        }

        // ==========================================
        // 🔥 RENOVAR PoW (NOVO MÉTODO)
        // ==========================================

        async _renewPow() {
            console.log('🔄 [Dashboard] Renovando PoW...');
            
            try {
                if (!window.powClient) {
                    console.warn('⚠️ [Dashboard] powClient não disponível');
                    return false;
                }
                
                if (typeof window.powClient.clearCache === 'function') {
                    window.powClient.clearCache();
                    console.log('✅ [Dashboard] Cache do PoW limpo');
                }
                
                if (typeof window.powClient.reset === 'function') {
                    window.powClient.reset();
                    console.log('✅ [Dashboard] PoW resetado');
                }
                
                if (typeof window.powClient.prepareForUpload === 'function') {
                    const prepared = await window.powClient.prepareForUpload();
                    if (prepared) {
                        console.log('✅ [Dashboard] PoW preparado com sucesso');
                        
                        if (typeof window.powClient.getStats === 'function') {
                            const stats = window.powClient.getStats();
                            if (stats && stats.cache && stats.cache.hasSolution) {
                                console.log('✅ [Dashboard] PoW pronto para uso');
                                return true;
                            }
                        }
                    }
                }
                
                if (typeof window.powClient.getSolutionForUpload === 'function') {
                    const solution = await window.powClient.getSolutionForUpload();
                    if (solution && solution.nonce) {
                        console.log('✅ [Dashboard] PoW obtido diretamente');
                        return true;
                    }
                }
                
                console.warn('⚠️ [Dashboard] Não foi possível renovar o PoW');
                return false;
                
            } catch (error) {
                console.error('❌ [Dashboard] Erro ao renovar PoW:', error);
                return false;
            }
        }

        // ==========================================
        // 🔥 UPLOAD MÚLTIPLO DE ARQUIVOS COM PoW (CORRIGIDO)
        // ==========================================

        async uploadMultipleFiles(files) {
            try {
                const token = Utils.getToken();
                if (!token) {
                    this._showToast('❌ Token de autenticação não encontrado. Faça login novamente.', 'error');
                    return null;
                }

                if (files.length === 0) {
                    this._showToast('⚠️ Selecione pelo menos um arquivo.', 'warning');
                    return null;
                }

                if (files.length > CONFIG.MAX_FILES_PER_BATCH) {
                    this._showToast(`⚠️ Máximo de ${CONFIG.MAX_FILES_PER_BATCH} arquivos por vez.`, 'warning');
                    return null;
                }

                for (const file of files) {
                    if (file.size > CONFIG.MAX_FILE_SIZE_KB * 1024) {
                        this._showToast(`⚠️ Arquivo ${file.name} excede ${CONFIG.MAX_FILE_SIZE_KB}KB.`, 'warning');
                        return null;
                    }
                }

                const allowedExtensions = ['.csv', '.xlsx', '.xls', '.tsv'];
                for (const file of files) {
                    const ext = '.' + file.name.split('.').pop().toLowerCase();
                    if (!allowedExtensions.includes(ext)) {
                        this._showToast(`⚠️ Arquivo ${file.name} não é suportado. Use: ${allowedExtensions.join(', ')}`, 'warning');
                        return null;
                    }
                }

                this._showUploadStatus('⏳', 'Preparando upload...', 'Inicializando segurança...', 5);
                this.state.set('ui', {
                    isUploading: true,
                    progress: 5,
                    status: 'preparing',
                    message: 'Preparando upload...'
                });

                const formData = new FormData();
                for (const file of files) {
                    formData.append('files', file);
                }
                formData.append('analysis_type', 'auto');
                formData.append('report_format', 'html');

                // ==========================================
                // 🔥 CORREÇÃO: OBTER PoW DE FORMA SEGURA
                // ==========================================
                let powHeaders = {};
                let powAttempts = 0;
                const maxPowAttempts = CONFIG.POW_MAX_ATTEMPTS || 3;

                while (powAttempts < maxPowAttempts) {
                    powAttempts++;
                    try {
                        this._showUploadStatus('⏳', `Obtendo prova de trabalho (${powAttempts}/${maxPowAttempts})...`, 'Aguarde, estamos protegendo sua análise', 10 + powAttempts * 5);

                        if (window.powClient) {
                            let powSolution = null;

                            // 🔥 NÍVEL 1: getSolutionForUpload (CORRETO)
                            if (typeof window.powClient.getSolutionForUpload === 'function') {
                                try {
                                    powSolution = await window.powClient.getSolutionForUpload();
                                    if (powSolution && powSolution.nonce) {
                                        powHeaders = {
                                            'X-PoW-Nonce': powSolution.nonce,
                                            'X-PoW-Challenge': powSolution.prefix || powSolution.challenge || '',
                                            'X-PoW-Difficulty': String(powSolution.complexity || powSolution.difficulty || 4),
                                            'X-PoW-Solution': powSolution.solution || powSolution.hash || '',
                                            'X-PoW-Timestamp': String(powSolution.solvedAt || powSolution.timestamp || Date.now())
                                        };
                                        console.log('✅ [Dashboard] PoW via getSolutionForUpload()');
                                        break;
                                    }
                                } catch (e) {
                                    console.warn(`⚠️ getSolutionForUpload falhou (${powAttempts}):`, e.message);
                                }
                            }

                            // 🔥 NÍVEL 2: prepareForUpload + getSolutionForUpload
                            if (typeof window.powClient.prepareForUpload === 'function' && !powSolution) {
                                try {
                                    const prepared = await window.powClient.prepareForUpload();
                                    if (prepared && typeof window.powClient.getSolutionForUpload === 'function') {
                                        powSolution = await window.powClient.getSolutionForUpload();
                                        if (powSolution && powSolution.nonce) {
                                            powHeaders = {
                                                'X-PoW-Nonce': powSolution.nonce,
                                                'X-PoW-Challenge': powSolution.prefix || powSolution.challenge || '',
                                                'X-PoW-Difficulty': String(powSolution.complexity || powSolution.difficulty || 4),
                                                'X-PoW-Solution': powSolution.solution || powSolution.hash || '',
                                                'X-PoW-Timestamp': String(powSolution.solvedAt || powSolution.timestamp || Date.now())
                                            };
                                            console.log('✅ [Dashboard] PoW via prepareForUpload');
                                            break;
                                        }
                                    }
                                } catch (e) {
                                    console.warn(`⚠️ prepareForUpload falhou (${powAttempts}):`, e.message);
                                }
                            }

                            // 🔥 NÍVEL 3: Cache do powClient (getStats)
                            if (typeof window.powClient.getStats === 'function') {
                                try {
                                    const stats = window.powClient.getStats();
                                    if (stats && stats.cache && stats.cache.hasSolution && stats.cache.solution) {
                                        const cachedSolution = stats.cache.solution;
                                        if (cachedSolution.nonce) {
                                            powHeaders = {
                                                'X-PoW-Nonce': cachedSolution.nonce,
                                                'X-PoW-Challenge': cachedSolution.prefix || cachedSolution.challenge || '',
                                                'X-PoW-Difficulty': String(cachedSolution.complexity || cachedSolution.difficulty || 4),
                                                'X-PoW-Solution': cachedSolution.solution || cachedSolution.hash || '',
                                                'X-PoW-Timestamp': String(cachedSolution.solvedAt || cachedSolution.timestamp || Date.now())
                                            };
                                            console.log('✅ [Dashboard] PoW do cache do powClient');
                                            break;
                                        }
                                    }
                                } catch (e) {
                                    console.warn('⚠️ Erro ao ler cache do powClient:', e);
                                }
                            }
                        }

                        // 🔥 NÍVEL 4: window._powSolution
                        if (Object.keys(powHeaders).length === 0 && window._powSolution) {
                            const pow = window._powSolution;
                            if (pow && pow.nonce) {
                                powHeaders = {
                                    'X-PoW-Nonce': pow.nonce,
                                    'X-PoW-Challenge': pow.challenge || pow.prefix || '',
                                    'X-PoW-Difficulty': String(pow.difficulty || 4),
                                    'X-PoW-Solution': pow.solution || pow.hash || '',
                                    'X-PoW-Timestamp': String(pow.timestamp || Date.now())
                                };
                                console.log('✅ [Dashboard] PoW do fallback _powSolution');
                                break;
                            }
                        }

                        // 🔥 NÍVEL 5: localStorage
                        if (Object.keys(powHeaders).length === 0) {
                            const powNonce = localStorage.getItem('pow_nonce');
                            const powChallenge = localStorage.getItem('pow_challenge');
                            const powSolution = localStorage.getItem('pow_solution');
                            if (powNonce && powChallenge && powSolution) {
                                powHeaders = {
                                    'X-PoW-Nonce': powNonce,
                                    'X-PoW-Challenge': powChallenge,
                                    'X-PoW-Difficulty': '4',
                                    'X-PoW-Solution': powSolution,
                                    'X-PoW-Timestamp': String(Date.now())
                                };
                                console.log('✅ [Dashboard] PoW do localStorage');
                                break;
                            }
                        }

                        if (Object.keys(powHeaders).length === 0 && powAttempts < maxPowAttempts) {
                            console.warn(`⚠️ PoW não disponível, tentativa ${powAttempts}/${maxPowAttempts}, aguardando...`);
                            await Utils.sleep(CONFIG.POW_RETRY_DELAY * powAttempts);
                            if (window.powClient && typeof window.powClient.clearCache === 'function') {
                                window.powClient.clearCache();
                            }
                        }

                    } catch (powError) {
                        console.warn(`⚠️ Erro ao obter PoW (${powAttempts}):`, powError);
                        if (powAttempts >= maxPowAttempts) {
                            console.warn('⚠️ PoW não disponível após múltiplas tentativas, continuando sem...');
                        }
                    }
                }

                if (Object.keys(powHeaders).length === 0) {
                    console.warn('⚠️ Nenhum PoW disponível, enviando sem proteção');
                }

                const headers = {
                    'Authorization': `Bearer ${token}`,
                    ...powHeaders
                };

                this._showUploadStatus('⏳', 'Enviando arquivos...', 'A IA está analisando seus dados', 30);

                const response = await fetch('/api/upload-multi-analyze', {
                    method: 'POST',
                    headers: headers,
                    body: formData
                });

                // 🔥 TRATAMENTO DO ERRO 428
                if (response.status === 428) {
                    console.warn('⚠️ [Dashboard] PoW inválido (428), tentando renovar...');
                    this._showUploadStatus('🔄', 'Renovando prova de trabalho...', 'Aguarde, estamos preparando uma nova', 20);
                    
                    const renewed = await this._renewPow();
                    
                    if (renewed) {
                        this._showToast('🔄 PoW renovado, tentando novamente...', 'info');
                        return this.uploadMultipleFiles(files);
                    } else {
                        throw new Error('Não foi possível renovar o PoW. Tente recarregar a página.');
                    }
                }

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.detail?.message || errorData.message || 'Erro no upload');
                }

                const result = await response.json();

                this._showUploadStatus('✅', 'Análise concluída!', 'Veja o relatório abaixo', 100);
                this.state.set('ui', {
                    isUploading: false,
                    progress: 100,
                    status: 'completed',
                    message: 'Análise concluída!'
                });

                await this._processMultiAnalysisResult(result);

                document.dispatchEvent(new CustomEvent('analysis:success', {
                    detail: { result: result }
                }));

                if (result.credits) {
                    this._updateCreditDisplay(result.credits.remaining);
                }

                try {
                    const recent = JSON.parse(localStorage.getItem('recentAnalyses') || '[]');
                    recent.unshift({
                        filename: files.map(f => f.name).join(', '),
                        timestamp: Date.now(),
                        result: result
                    });
                    if (recent.length > 10) recent.pop();
                    localStorage.setItem('recentAnalyses', JSON.stringify(recent));
                } catch (e) {}

                await this.cache.clear();

                this._showToast('✅ Análise concluída com sucesso!', 'success');
                this._showResult();

                return result;

            } catch (error) {
                console.error('❌ [Dashboard] Erro no upload:', error);
                
                this.state.set('ui', {
                    isUploading: false,
                    status: 'error',
                    message: error.message || 'Erro ao processar'
                });

                if (error.message && error.message.includes('PoW')) {
                    this._showUploadStatus('❌', 'Erro no PoW', 'Tente novamente ou recarregue a página', 0);
                    this._showToast('❌ Erro na prova de trabalho. Recarregue a página e tente novamente.', 'error');
                } else {
                    this._showUploadStatus('❌', 'Erro', error.message || 'Falha no processamento', 0);
                    this._showToast(`❌ ${error.message || 'Erro ao processar'}`, 'error');
                }
                
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

            const executiveScore = analysis?.executive_score || {};
            const executiveSummary = analysis?.executive_summary || '';
            const recommendations = analysis?.recommendations || [];
            const forecast = analysis?.forecast || '';
            const generalConclusion = analysis?.general_conclusion || '';
            const comparison = analysis?.comparison || {};
            const trend = analysis?.trend || {};

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

            await this._updateMetrics({
                executive_score: executiveScore,
                chart_data: chart_data || {}
            });

            if (result.data?.files && result.data.files.length > 0) {
                const analyses = result.data.files.map((file) => ({
                    filename: file.filename || 'Arquivo',
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
            const fileInput = document.getElementById('fileInput');
            if (fileInput) fileInput.value = '';
            
            const previewContainer = document.getElementById('filePreviewContainer');
            if (previewContainer) previewContainer.innerHTML = '';
            
            const statusEl = document.getElementById('analysisStatus');
            if (statusEl) statusEl.classList.remove('show');
            
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

                const analysisData = {
                    metrics: data.prediction_stats || {},
                    predictions: data.predictions || [],
                    insights: data.insights || {},
                    recommendations: data.recommendations || [],
                    chart_data: data.chart_data || {},
                    filename: data.filename || 'Análise',
                    ai_report: data.ai_report || ''
                };

                if (window.generateFinancePDF) {
                    window.generateFinancePDF(analysisData);
                } else {
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
    console.log('🔥 dashboard.js v14.0 carregado - CORREÇÕES DE PoW + INATIVIDADE');
    console.log('   ✅ PoW: getSolutionForUpload() em vez de getSolution()');
    console.log('   ✅ 5 níveis de fallback para PoW');
    console.log('   ✅ Renovação automática de PoW');
    console.log('   ✅ Tratamento robusto do erro 428');
    console.log('   ✅ Upload com progresso detalhado');
    console.log('   ⏰ Sistema de inatividade com limpeza automática');
    console.log('   🧹 Limpeza de gráficos antigos a cada 5 minutos');
    console.log('   📡 Use window.__dashboard para acesso');
    console.log('=' .repeat(60));

})();