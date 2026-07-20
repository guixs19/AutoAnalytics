// frontend/js/dashboard.js - VERSÃO 7.1 (CORRIGIDO - CHART MANAGER)
/**
 * Dashboard Module - AutoAnalytics v7.1
 * 
 * 🏗️ ARQUITETURA V7.1:
 * 1. 🔥 CORRIGIDO: ChartManager com retry inteligente
 * 2. 🔥 MELHORADO: Detecção de container com MutationObserver
 * 3. 🔥 ADICIONADO: Fallback com timeout
 * 4. 🔥 OTIMIZADO: Criação sob demanda com lazy rendering
 * 5. 🔥 ADICIONADO: Verificação de visibilidade do container
 */

(function() {
    'use strict';

    console.log('📦 [Dashboard v7.1] Carregando módulo corrigido...');

    // ==============================================
    // 🔥 CONFIGURAÇÕES
    // ==============================================

    const CONFIG = {
        MAX_FILES_PER_BATCH: 3,
        MAX_FILE_SIZE_KB: 200,
        API_BASE: '/api',
        POLLING_INTERVAL: 2000,
        MAX_POLLING_ATTEMPTS: 60,
        CREDITS_CHECK_INTERVAL: 30000,
        MAX_CREDITS_BALANCE: 3,
        POW_ENABLED: true,
        
        // 🔥 CHART CONFIG
        CHART_RETRY_ATTEMPTS: 10,
        CHART_RETRY_DELAY: 300,
        CHART_CONTAINER_TIMEOUT: 5000,
        
        // ANIMAÇÕES
        ANIMATION_DURATION: 0.6,
        STAGGER_DELAY: 0.08,
        CHART_ANIMATION_DURATION: 800,
        
        // TIMEOUTS
        WAIT_FOR_APP_TIMEOUT: 8000,
        WAIT_FOR_APP_INTERVAL: 200,
        
        // HISTÓRICO
        HISTORY_LIMIT: 50,
        VIRTUAL_SCROLL_ITEM_HEIGHT: 60,
        VIRTUAL_SCROLL_BUFFER: 5
    };

    // ==============================================
    // 🔥 ESTADO (USANDO APP.JS)
    // ==============================================

    const State = {
        activeAnalyses: [],
        pollingIntervals: [],
        isProcessing: false,
        _initialized: false,
        _appReady: false,
        _chartInstance: null,
        _chartData: null,
        _historyData: [],
        _visibleHistory: [],
        _scrollTop: 0,
        _containerHeight: 0
    };

    // ==============================================
    // 🔥 UTILITÁRIOS
    // ==============================================

    const Utils = {
        debounce: function(fn, delay = 300) {
            let timer = null;
            return function(...args) {
                if (timer) clearTimeout(timer);
                timer = setTimeout(() => {
                    fn.apply(this, args);
                    timer = null;
                }, delay);
            };
        },

        throttle: function(fn, limit = 100) {
            let inThrottle = false;
            return function(...args) {
                if (!inThrottle) {
                    fn.apply(this, args);
                    inThrottle = true;
                    setTimeout(() => inThrottle = false, limit);
                }
            };
        },

        formatFileSize: function(bytes) {
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
            return (bytes / 1048576).toFixed(1) + ' MB';
        },

        formatRelativeTime: function(date) {
            const now = new Date();
            const diff = now - new Date(date);
            const minutes = Math.floor(diff / 60000);
            const hours = Math.floor(diff / 3600000);
            const days = Math.floor(diff / 86400000);

            if (minutes < 1) return 'agora pouco';
            if (minutes < 60) return `${minutes}m atrás`;
            if (hours < 24) return `${hours}h atrás`;
            if (days < 7) return `${days}d atrás`;
            return new Date(date).toLocaleDateString('pt-BR');
        },

        escapeHtml: function(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        },

        getScoreColor: function(score) {
            if (score >= 0.7) return '#48bb78';
            if (score >= 0.4) return '#f5a623';
            return '#f56565';
        },

        getScoreIcon: function(score) {
            if (score >= 0.7) return '🚀';
            if (score >= 0.4) return '📈';
            return '🔄';
        },

        getScoreLabel: function(score) {
            if (score >= 0.7) return 'Alto potencial';
            if (score >= 0.4) return 'Potencial médio';
            return 'Baixo potencial';
        },
        
        // 🔥 NOVO: Aguarda elemento no DOM
        waitForElement: function(selector, timeout = CONFIG.CHART_CONTAINER_TIMEOUT) {
            return new Promise((resolve) => {
                // Verifica se já existe
                const existing = document.getElementById(selector) || document.querySelector(selector);
                if (existing) {
                    resolve(existing);
                    return;
                }
                
                // Aguarda com MutationObserver
                const observer = new MutationObserver(() => {
                    const el = document.getElementById(selector) || document.querySelector(selector);
                    if (el) {
                        observer.disconnect();
                        resolve(el);
                    }
                });
                
                observer.observe(document.body, {
                    childList: true,
                    subtree: true
                });
                
                // Timeout de segurança
                setTimeout(() => {
                    observer.disconnect();
                    const el = document.getElementById(selector) || document.querySelector(selector);
                    resolve(el || null);
                }, timeout);
            });
        },
        
        // 🔥 NOVO: Verifica se elemento está visível
        isElementVisible: function(element) {
            if (!element) return false;
            const rect = element.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0 && element.offsetParent !== null;
        }
    };

    // ==============================================
    // 🔥 GERENCIADOR DE ANIMAÇÕES
    // ==============================================

    const Animator = {
        _gsapLoaded: false,

        init: function() {
            this._gsapLoaded = typeof gsap !== 'undefined';
            if (this._gsapLoaded) {
                console.log('🎬 [Animator] GSAP disponível');
            } else {
                console.log('🎬 [Animator] Usando CSS animations (fallback)');
            }
        },

        fadeIn: function(element, options = {}) {
            const defaults = {
                duration: CONFIG.ANIMATION_DURATION,
                delay: 0,
                y: 20,
                opacity: 0
            };
            const opts = { ...defaults, ...options };

            if (this._gsapLoaded && element) {
                gsap.fromTo(element, 
                    { opacity: opts.opacity, y: opts.y },
                    { 
                        opacity: 1, 
                        y: 0, 
                        duration: opts.duration, 
                        delay: opts.delay,
                        ease: 'power3.out'
                    }
                );
            } else if (element) {
                element.style.opacity = '0';
                element.style.transform = `translateY(${opts.y}px)`;
                element.style.transition = `all ${opts.duration}s cubic-bezier(0.34, 1.56, 0.64, 1) ${opts.delay}s`;
                requestAnimationFrame(() => {
                    element.style.opacity = '1';
                    element.style.transform = 'translateY(0)';
                });
            }
        },

        staggerIn: function(elements, options = {}) {
            const defaults = {
                duration: CONFIG.ANIMATION_DURATION,
                stagger: CONFIG.STAGGER_DELAY,
                y: 30,
                opacity: 0
            };
            const opts = { ...defaults, ...options };

            if (this._gsapLoaded && elements && elements.length) {
                gsap.fromTo(elements,
                    { opacity: opts.opacity, y: opts.y },
                    {
                        opacity: 1,
                        y: 0,
                        duration: opts.duration,
                        stagger: opts.stagger,
                        ease: 'power3.out',
                        clearProps: 'all'
                    }
                );
            } else if (elements && elements.length) {
                elements.forEach((el, i) => {
                    el.style.opacity = '0';
                    el.style.transform = `translateY(${opts.y}px)`;
                    el.style.transition = `all ${opts.duration}s cubic-bezier(0.34, 1.56, 0.64, 1) ${i * opts.stagger}s`;
                    requestAnimationFrame(() => {
                        el.style.opacity = '1';
                        el.style.transform = 'translateY(0)';
                    });
                });
            }
        },

        countUp: function(element, target, options = {}) {
            const defaults = {
                duration: 1000,
                start: 0,
                format: (v) => v
            };
            const opts = { ...defaults, ...options };

            if (!element) return;

            if (this._gsapLoaded && typeof gsap.utils.interpolate === 'function') {
                const start = opts.start;
                const obj = { value: start };
                gsap.to(obj, {
                    value: target,
                    duration: opts.duration / 1000,
                    ease: 'power2.out',
                    onUpdate: () => {
                        element.textContent = opts.format(Math.round(obj.value));
                    }
                });
            } else {
                const startTime = performance.now();
                const startValue = opts.start;

                function update() {
                    const elapsed = performance.now() - startTime;
                    const progress = Math.min(1, elapsed / opts.duration);
                    const eased = 1 - Math.pow(1 - progress, 3);
                    const current = startValue + (target - startValue) * eased;
                    element.textContent = opts.format(Math.round(current));
                    
                    if (progress < 1) {
                        requestAnimationFrame(update);
                    }
                }
                update();
            }
        },

        animateMetric: function(element, value, label) {
            if (!element) return;
            this.fadeIn(element, { y: 10, duration: 0.4 });
            const numberEl = element.querySelector('.metric-value');
            if (numberEl) {
                this.countUp(numberEl, value, {
                    duration: 800,
                    format: (v) => v
                });
            }
        }
    };

    // ==============================================
    // 🔥 GERENCIADOR DE GRÁFICOS (CORRIGIDO)
    // ==============================================

    const ChartManager = {
        _instance: null,
        _container: null,
        _data: null,
        _retryCount: 0,
        _maxRetries: CONFIG.CHART_RETRY_ATTEMPTS,
        _retryTimeout: null,
        _initialized: false,
        _pendingData: null,
        _observer: null,

        /**
         * 🔥 CORRIGIDO: Inicializa o gráfico com retry
         */
        init: function(containerId, data = null) {
            // Se já inicializado, apenas atualiza dados
            if (this._initialized && this._instance) {
                if (data) {
                    this._data = data;
                    this.update();
                }
                return;
            }

            console.log(`📊 [ChartManager] Inicializando gráfico: #${containerId}`);

            // Guarda dados pendentes
            if (data) {
                this._pendingData = data;
            }

            // Tenta encontrar o container
            const container = document.getElementById(containerId);
            
            if (container && Utils.isElementVisible(container)) {
                // Container encontrado e visível
                this._container = container;
                this._renderChart();
                this._initialized = true;
                this._retryCount = 0;
                console.log('✅ [ChartManager] Gráfico inicializado com sucesso');
                return;
            }

            // Se o container não está visível, tenta com retry
            console.log(`⏳ [ChartManager] Container #${containerId} não encontrado, tentando retry...`);
            this._retryWithDelay(containerId);
        },

        /**
         * 🔥 Retry com delay progressivo
         */
        _retryWithDelay: function(containerId) {
            // Limpa timeout anterior
            if (this._retryTimeout) {
                clearTimeout(this._retryTimeout);
                this._retryTimeout = null;
            }

            // Verifica se atingiu o limite de tentativas
            if (this._retryCount >= this._maxRetries) {
                console.warn(`⚠️ [ChartManager] Desistindo após ${this._maxRetries} tentativas para #${containerId}`);
                
                // Tenta com MutationObserver como fallback
                this._setupMutationObserver(containerId);
                return;
            }

            this._retryCount++;
            
            // Delay progressivo: 300ms, 500ms, 800ms, 1200ms...
            const delay = CONFIG.CHART_RETRY_DELAY * (1 + (this._retryCount - 1) * 0.5);
            
            console.log(`🔄 [ChartManager] Tentativa ${this._retryCount}/${this._maxRetries} em ${delay}ms`);

            this._retryTimeout = setTimeout(() => {
                const container = document.getElementById(containerId);
                
                if (container && Utils.isElementVisible(container)) {
                    this._container = container;
                    this._renderChart();
                    this._initialized = true;
                    this._retryCount = 0;
                    console.log('✅ [ChartManager] Gráfico inicializado após retry');
                    return;
                }

                // Continua tentando
                this._retryWithDelay(containerId);
            }, delay);
        },

        /**
         * 🔥 MutationObserver como fallback final
         */
        _setupMutationObserver: function(containerId) {
            if (this._observer) {
                this._observer.disconnect();
            }

            console.log(`👀 [ChartManager] Observando DOM pelo container #${containerId}`);

            this._observer = new MutationObserver(() => {
                const container = document.getElementById(containerId);
                if (container && Utils.isElementVisible(container)) {
                    this._observer.disconnect();
                    this._observer = null;
                    
                    this._container = container;
                    this._renderChart();
                    this._initialized = true;
                    console.log('✅ [ChartManager] Gráfico inicializado via MutationObserver');
                }
            });

            this._observer.observe(document.body, {
                childList: true,
                subtree: true
            });

            // Timeout de segurança
            setTimeout(() => {
                if (this._observer) {
                    this._observer.disconnect();
                    this._observer = null;
                    console.warn(`⚠️ [ChartManager] Timeout aguardando #${containerId}`);
                }
            }, CONFIG.CHART_CONTAINER_TIMEOUT);
        },

        /**
         * 🔥 Renderiza o gráfico (Chart.js)
         */
        _renderChart: function() {
            if (!this._container) {
                console.warn('⚠️ [ChartManager] Container vazio, não é possível renderizar');
                return;
            }

            if (typeof Chart === 'undefined') {
                console.warn('⚠️ [ChartManager] Chart.js não carregado, aguardando...');
                // Tenta carregar Chart.js dinamicamente
                this._loadChartJS();
                return;
            }

            // Destroi instância anterior
            if (this._instance) {
                this._instance.destroy();
                this._instance = null;
            }

            // Prepara dados
            const data = this._pendingData || this._data || {
                labels: ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun'],
                values: [0, 0, 0, 0, 0, 0]
            };
            this._data = data;

            const ctx = this._container.getContext('2d');
            
            // Configuração otimizada para performance
            this._instance = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.labels,
                    datasets: [{
                        label: 'Análises',
                        data: data.values,
                        borderColor: '#ff6b35',
                        backgroundColor: 'rgba(255, 107, 53, 0.05)',
                        borderWidth: 3,
                        pointRadius: 3,
                        pointBackgroundColor: '#ff6b35',
                        pointBorderColor: '#ffffff',
                        pointBorderWidth: 2,
                        tension: 0.4,
                        fill: true
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    plugins: {
                        legend: {
                            display: false
                        },
                        tooltip: {
                            backgroundColor: 'rgba(26, 26, 46, 0.9)',
                            titleColor: '#ffffff',
                            bodyColor: '#ff6b35',
                            borderColor: 'rgba(255, 107, 53, 0.3)',
                            borderWidth: 1,
                            cornerRadius: 12,
                            padding: 12
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            grid: {
                                color: 'rgba(255, 255, 255, 0.05)',
                                drawBorder: false
                            },
                            ticks: {
                                color: 'rgba(255, 255, 255, 0.3)',
                                font: { size: 10 }
                            }
                        },
                        x: {
                            grid: {
                                display: false
                            },
                            ticks: {
                                color: 'rgba(255, 255, 255, 0.3)',
                                font: { size: 10 }
                            }
                        }
                    },
                    animation: {
                        duration: CONFIG.CHART_ANIMATION_DURATION,
                        easing: 'easeOutQuart'
                    },
                    elements: {
                        line: {
                            borderJoinStyle: 'round'
                        }
                    },
                    interaction: {
                        intersect: false,
                        mode: 'index'
                    }
                }
            });

            // Anima entrada do gráfico
            Animator.fadeIn(this._container, { y: 20, duration: 0.8 });

            console.log('📊 [ChartManager] Gráfico renderizado com sucesso');
        },

        /**
         * 🔥 Carrega Chart.js dinamicamente se necessário
         */
        _loadChartJS: function() {
            // Verifica se já está carregando
            if (document.querySelector('script[src*="chart.js"]')) {
                // Aguarda o carregamento
                const checkChart = setInterval(() => {
                    if (typeof Chart !== 'undefined') {
                        clearInterval(checkChart);
                        this._renderChart();
                    }
                }, 200);
                setTimeout(() => clearInterval(checkChart), 5000);
                return;
            }

            console.log('📥 [ChartManager] Carregando Chart.js dinamicamente...');
            
            const script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js';
            script.async = true;
            script.onload = () => {
                console.log('✅ [ChartManager] Chart.js carregado');
                this._renderChart();
            };
            script.onerror = () => {
                console.warn('⚠️ [ChartManager] Falha ao carregar Chart.js');
            };
            document.head.appendChild(script);
        },

        /**
         * 🔥 Atualiza dados do gráfico
         */
        update: function(data) {
            // Se não inicializado, guarda dados e tenta inicializar
            if (!this._initialized || !this._instance) {
                this._pendingData = data || this._data;
                this.init('analysisChart', this._pendingData);
                return;
            }

            if (data) {
                this._data = data;
            }

            this._instance.data.labels = this._data.labels;
            this._instance.data.datasets[0].data = this._data.values;
            this._instance.update('none');
        },

        /**
         * 🔥 Adiciona ponto ao gráfico
         */
        addPoint: function(label, value) {
            // Se não inicializado, guarda dados pendentes
            if (!this._initialized || !this._instance) {
                if (!this._pendingData) {
                    this._pendingData = {
                        labels: [],
                        values: []
                    };
                }
                this._pendingData.labels.push(label);
                this._pendingData.values.push(value);
                
                // Limita a 12 pontos
                if (this._pendingData.labels.length > 12) {
                    this._pendingData.labels.shift();
                    this._pendingData.values.shift();
                }
                
                this.init('analysisChart', this._pendingData);
                return;
            }

            this._data.labels.push(label);
            this._data.values.push(value);

            // Limita a 12 pontos
            if (this._data.labels.length > 12) {
                this._data.labels.shift();
                this._data.values.shift();
            }

            this.update();
        },

        /**
         * 🔥 Destroi o gráfico
         */
        destroy: function() {
            if (this._retryTimeout) {
                clearTimeout(this._retryTimeout);
                this._retryTimeout = null;
            }
            if (this._observer) {
                this._observer.disconnect();
                this._observer = null;
            }
            if (this._instance) {
                this._instance.destroy();
                this._instance = null;
            }
            this._initialized = false;
            this._retryCount = 0;
            this._container = null;
            console.log('🧹 [ChartManager] Destruído');
        },

        /**
         * 🔥 Verifica se o gráfico está pronto
         */
        isReady: function() {
            return this._initialized && this._instance !== null;
        }
    };

    // ==============================================
    // 🔥 GERENCIADOR DE HISTÓRICO (VIRTUAL SCROLL)
    // ==============================================

    const HistoryManager = {
        _data: [],
        _visible: [],
        _container: null,
        _scrollTop: 0,
        _itemHeight: CONFIG.VIRTUAL_SCROLL_ITEM_HEIGHT,
        _buffer: CONFIG.VIRTUAL_SCROLL_BUFFER,
        _totalHeight: 0,
        _initialized: false,

        init: function(containerId) {
            this._container = document.getElementById(containerId);
            if (!this._container) {
                console.warn('⚠️ [HistoryManager] Container não encontrado:', containerId);
                return;
            }

            this._initialized = true;
            
            const onScroll = Utils.throttle(() => {
                this._handleScroll();
            }, 50);

            this._container.addEventListener('scroll', onScroll);

            const onResize = Utils.debounce(() => {
                this._updateVisible();
            }, 200);

            window.addEventListener('resize', onResize);

            console.log('✅ [HistoryManager] Inicializado com virtual scroll');
        },

        setData: function(data) {
            this._data = data || [];
            this._totalHeight = this._data.length * this._itemHeight;
            this._updateVisible();
            
            if (this._data.length > 0) {
                Animator.fadeIn(this._container, { y: 10, duration: 0.4 });
            }
        },

        _updateVisible: function() {
            if (!this._container || !this._initialized) return;

            const containerHeight = this._container.clientHeight;
            const scrollTop = this._container.scrollTop || 0;

            const startIndex = Math.max(0, Math.floor(scrollTop / this._itemHeight) - this._buffer);
            const endIndex = Math.min(
                this._data.length,
                Math.ceil((scrollTop + containerHeight) / this._itemHeight) + this._buffer
            );

            this._visible = this._data.slice(startIndex, endIndex);
            this._scrollTop = scrollTop;

            this._renderVisible(startIndex);
        },

        _renderVisible: function(startIndex) {
            if (!this._container) return;

            const startOffset = startIndex * this._itemHeight;
            
            let html = `
                <div style="height: ${this._totalHeight}px; position: relative; padding: 0;">
                    <div style="position: absolute; top: ${startOffset}px; left: 0; right: 0; padding: 0 0.5rem;">
            `;

            if (this._visible.length === 0) {
                html += `
                    <div class="text-center py-4" style="color: rgba(255,255,255,0.3);">
                        <i class="fas fa-history fa-2x mb-2 opacity-50"></i>
                        <p class="small mb-0">Nenhuma análise realizada</p>
                    </div>
                `;
            } else {
                this._visible.forEach((item, index) => {
                    const date = new Date(item.created_at || item.timestamp);
                    const status = item.status || 'completed';
                    const isCompleted = status === 'completed';
                    const score = item.score || item.result?.score || 0;
                    const scoreColor = Utils.getScoreColor(score);
                    const scoreIcon = Utils.getScoreIcon(score);
                    
                    html += `
                        <div class="history-item" data-index="${startIndex + index}" 
                             style="animation: slideIn 0.3s ease-out ${index * 0.05}s both;
                                    padding: 0.6rem 0.8rem;
                                    margin-bottom: 0.3rem;
                                    background: rgba(255,255,255,0.03);
                                    border-radius: 12px;
                                    border: 1px solid rgba(255,255,255,0.04);
                                    transition: all 0.3s ease;
                                    cursor: default;">
                            <div class="d-flex justify-content-between align-items-center flex-wrap">
                                <div class="d-flex align-items-center gap-2">
                                    <span style="width: 8px; height: 8px; border-radius: 50%; 
                                          background: ${isCompleted ? '#48bb78' : '#f56565'};
                                          display: inline-block;
                                          box-shadow: 0 0 10px ${isCompleted ? 'rgba(72,187,120,0.3)' : 'rgba(245,101,101,0.3)'};">
                                    </span>
                                    <span style="color: rgba(255,255,255,0.8); font-size: 0.8rem; font-weight: 500;">
                                        ${Utils.escapeHtml(item.filename || 'Análise')}
                                    </span>
                                    ${score > 0 ? `
                                        <span class="badge" style="background: ${scoreColor}20; color: ${scoreColor}; font-size: 0.55rem; border: 1px solid ${scoreColor}30;">
                                            ${scoreIcon} ${Math.round(score * 100)}%
                                        </span>
                                    ` : ''}
                                </div>
                                <div class="d-flex align-items-center gap-2">
                                    <small style="color: rgba(255,255,255,0.2); font-size: 0.55rem;">
                                        ${Utils.formatRelativeTime(date)}
                                    </small>
                                    <span class="badge" style="background: ${isCompleted ? 'rgba(72,187,120,0.1)' : 'rgba(245,101,101,0.1)'}; 
                                          color: ${isCompleted ? '#48bb78' : '#f56565'}; font-size: 0.5rem; border: 1px solid ${isCompleted ? 'rgba(72,187,120,0.2)' : 'rgba(245,101,101,0.2)'};">
                                        ${isCompleted ? '✅ Concluído' : status}
                                    </span>
                                </div>
                            </div>
                        </div>
                    `;
                });
            }

            html += `
                    </div>
                </div>
            `;

            this._container.innerHTML = html;
        },

        _handleScroll: function() {
            this._updateVisible();
        },

        addItem: function(item) {
            this._data.unshift(item);
            if (this._data.length > CONFIG.HISTORY_LIMIT) {
                this._data.pop();
            }
            this._totalHeight = this._data.length * this._itemHeight;
            
            if (this._scrollTop < this._itemHeight * 2) {
                this._updateVisible();
            }
        },

        clear: function() {
            this._data = [];
            this._visible = [];
            this._totalHeight = 0;
            this._updateVisible();
        }
    };

    // ==============================================
    // 🔥 FUNÇÕES PRINCIPAIS
    // ==============================================

    function waitForApp(maxAttempts) {
        maxAttempts = maxAttempts || 40;
        return new Promise(function(resolve) {
            let attempts = 0;
            const check = function() {
                attempts++;
                
                if (window._appReadyFired === true) {
                    resolve(true);
                    return;
                }
                
                if (window.App && typeof window.App.isReady === 'function') {
                    try {
                        if (window.App.isReady()) {
                            resolve(true);
                            return;
                        }
                    } catch (e) { /* ignora */ }
                }
                
                if (window.__APP_STATE && window.__APP_STATE.isAppReady === true) {
                    resolve(true);
                    return;
                }
                
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

    function getAppState() {
        return window.__APP_STATE || {};
    }

    function getCreditsDisplay() {
        const state = getAppState();
        if (state.isAdmin) return '∞';
        if (state.isPremium) return `${state.credits || 0}/${CONFIG.MAX_CREDITS_BALANCE}`;
        return String(state.credits || 0);
    }

    // ==============================================
    // 🔥 UPLOAD E PROCESSAMENTO
    // ==============================================

    async function preparePowForUpload() {
        if (!window.powClient) {
            console.log('⏳ [Dashboard] PoW client não disponível');
            return true;
        }

        if (!window.powClient._isAuthenticated?.()) {
            console.log('⏳ [Dashboard] PoW aguardando autenticação');
            return true;
        }

        try {
            console.log('🔄 [Dashboard] Preparando PoW para upload...');
            const ready = await window.powClient.prepareForUpload?.();
            
            if (ready) {
                console.log('✅ [Dashboard] PoW pronto para upload');
                return true;
            }
            return true;
        } catch (error) {
            console.warn('⚠️ [Dashboard] Erro ao preparar PoW:', error.message);
            return true;
        }
    }

    async function processUpload(files) {
        if (!files || files.length === 0) {
            showNotification('Selecione pelo menos um arquivo', 'warning');
            return;
        }
        
        if (files.length > CONFIG.MAX_FILES_PER_BATCH) {
            showNotification(`Máximo de ${CONFIG.MAX_FILES_PER_BATCH} arquivos por vez.`, 'error');
            return;
        }
        
        for (const file of files) {
            if (file.size > CONFIG.MAX_FILE_SIZE_KB * 1024) {
                showNotification(`❌ ${file.name} excede ${CONFIG.MAX_FILE_SIZE_KB}KB`, 'error');
                return;
            }
        }
        
        const state = getAppState();
        const isAdmin = state.isAdmin || false;
        const credits = state.credits || 0;
        const isPremium = state.isPremium || false;
        
        if (!isAdmin) {
            if (credits < files.length) {
                showNotification(`❌ Você precisa de ${files.length} crédito(s). Você tem apenas ${credits}.`, 'warning');
                showCreditsModal();
                return;
            }
        }
        
        showLoading('Iniciando análise...', `Preparando ${files.length} arquivo(s)`);
        updateLoadingProgress(5);
        
        if (CONFIG.POW_ENABLED) {
            await preparePowForUpload();
        }
        
        const formData = new FormData();
        for (const file of files) {
            formData.append('files', file);
        }
        formData.append('analysis_type', 'auto');
        formData.append('ai_model', 'auto');
        
        const token = localStorage.getItem('access_token');
        
        try {
            let response;
            let powSolution = null;
            
            if (CONFIG.POW_ENABLED && window.powClient && window.powClient._isAuthenticated?.()) {
                try {
                    powSolution = await window.powClient.getSolutionForUpload?.();
                    
                    if (powSolution && window.powClient.uploadWithPow) {
                        if (files.length === 1) {
                            const result = await window.powClient.uploadWithPow(files[0]);
                            if (result) {
                                handleUploadResponse({ 
                                    processed_files: [{ 
                                        process_id: result.process_id, 
                                        filename: result.filename 
                                    }] 
                                }, files);
                                updateLoadingProgress(10, 'Analisando dados...');
                                return;
                            }
                        }
                    }
                } catch (powError) {
                    console.warn('⚠️ [Dashboard] PoW falhou:', powError.message);
                }
            }
            
            const headers = { 'Authorization': `Bearer ${token}` };
            if (powSolution?.prefix && powSolution?.nonce) {
                headers['X-PoW-Challenge'] = powSolution.prefix;
                headers['X-PoW-Nonce'] = powSolution.nonce;
            }
            
            response = await fetch(`${CONFIG.API_BASE}/upload-auto`, {
                method: 'POST',
                headers: headers,
                body: formData
            });
            
            if (!response) {
                throw new Error('Falha na conexão');
            }
            
            if (response.status === 428) {
                showNotification('🔄 Proteção anti-bot: recalculando...', 'info');
                const fallbackResponse = await fetch(`${CONFIG.API_BASE}/upload-auto`, {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` },
                    body: formData
                });
                
                if (fallbackResponse.ok) {
                    const data = await fallbackResponse.json();
                    if (data.processed_files?.length > 0) {
                        handleUploadResponse(data, files);
                        return;
                    }
                }
                throw new Error('Erro no upload após tentativas');
            }
            
            const data = await response.json();
            
            if (response.ok && data.processed_files?.length > 0) {
                handleUploadResponse(data, files);
            } else {
                showNotification(data?.detail || 'Erro no upload', 'error');
                hideLoading();
            }
        } catch (error) {
            console.error('❌ [Dashboard] Upload error:', error);
            showNotification('Erro ao processar arquivo(s)', 'error');
            hideLoading();
        }
    }

    function handleUploadResponse(data, files) {
        showNotification(`✅ ${data.processed_files.length} arquivo(s) processado(s)!`, 'success');
        updateLoadingProgress(10, 'Analisando dados...');
        
        for (const processed of data.processed_files) {
            startPolling(processed.process_id, processed.filename);
        }
        
        if (window.__APP_STATE_MANAGER) {
            window.__APP_STATE_MANAGER.updateCredits(
                data.credits_balance || 0,
                data.is_premium || false
            );
        }
        
        const fileInput = document.getElementById('fileInput');
        if (fileInput) fileInput.value = '';
        document.getElementById('filePreviewContainer').innerHTML = '';
        
        const uploadBtn = document.getElementById('uploadButton');
        if (uploadBtn) {
            uploadBtn.disabled = true;
            uploadBtn.innerHTML = `<i class="fas fa-spinner fa-spin me-2"></i> Processando...`;
        }
        
        updateMetrics();
    }

    async function startPolling(processId, filename) {
        let attempts = 0;
        const maxAttempts = CONFIG.MAX_POLLING_ATTEMPTS;
        
        const interval = setInterval(async () => {
            attempts++;
            
            try {
                const token = localStorage.getItem('access_token');
                const response = await fetch(`${CONFIG.API_BASE}/status/${processId}`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                
                if (!response.ok) {
                    if (response.status === 401) {
                        clearInterval(interval);
                        showNotification('Sessão expirada.', 'warning');
                        return;
                    }
                    if (attempts >= maxAttempts) {
                        clearInterval(interval);
                        showNotification(`⏳ Análise ${filename} está demorando.`, 'warning');
                        hideLoading();
                    }
                    return;
                }
                
                const data = await response.json();
                updateLoadingProgress(data.progress || 0);
                
                if (data.status === 'completed') {
                    clearInterval(interval);
                    
                    const resultResponse = await fetch(`${CONFIG.API_BASE}/analysis/${processId}`, {
                        headers: { 'Authorization': `Bearer ${token}` }
                    });
                    
                    if (resultResponse.ok) {
                        const resultData = await resultResponse.json();
                        
                        showNotification(`✅ Análise concluída: ${filename}`, 'success');
                        updateLoadingProgress(100, '✅ Análise concluída!');
                        
                        window.dispatchEvent(new CustomEvent('analysis:success', {
                            detail: {
                                processId,
                                filename,
                                result: resultData
                            }
                        }));
                        
                        const analysisData = {
                            processId,
                            filename,
                            status: 'completed',
                            result: resultData,
                            created_at: new Date().toISOString()
                        };
                        
                        State.activeAnalyses.push(analysisData);
                        renderAnalysisCard(analysisData);
                        HistoryManager.addItem(analysisData);
                        ChartManager.addPoint(
                            new Date().toLocaleDateString('pt-BR', { month: 'short' }),
                            State.activeAnalyses.length
                        );
                        updateMetrics();
                        
                        const uploadBtn = document.getElementById('uploadButton');
                        if (uploadBtn) {
                            uploadBtn.disabled = false;
                            uploadBtn.innerHTML = `<i class="fas fa-play-circle me-2"></i> Iniciar Análise <span class="badge ms-2" style="background: rgba(255,255,255,0.2); color: white;">1 crédito/arquivo</span>`;
                        }
                        
                        setTimeout(hideLoading, 800);
                    }
                    
                } else if (data.status === 'error') {
                    clearInterval(interval);
                    showNotification(`❌ Erro na análise: ${filename}`, 'error');
                    hideLoading();
                }
                
                if (attempts >= maxAttempts) {
                    clearInterval(interval);
                    showNotification(`⏳ Análise ${filename} está demorando.`, 'warning');
                    hideLoading();
                }
            } catch (error) {
                console.error('❌ [Dashboard] Polling error:', error);
                if (attempts >= maxAttempts) {
                    clearInterval(interval);
                }
            }
        }, CONFIG.POLLING_INTERVAL);
        
        State.pollingIntervals.push(interval);
    }

    // ==============================================
    // 🔥 RENDERIZAÇÃO DE ANÁLISE
    // ==============================================

    function renderAnalysisCard(analysis) {
        const container = document.getElementById('activeAnalysesContainer');
        if (!container) return;
        
        const data = analysis.result || {};
        const stats = data.stats || {};
        const predictions = data.predictions_summary || {};
        
        const totalRegistros = stats.rows || predictions.total || 0;
        const scoreMedio = predictions.mean || 0.65;
        const scoreMin = predictions.min || 0.2;
        const scoreMax = predictions.max || 0.9;
        const scoreStd = predictions.std || 0.15;
        
        const scoreColor = Utils.getScoreColor(scoreMedio);
        const scoreIcon = Utils.getScoreIcon(scoreMedio);
        const scoreLabel = Utils.getScoreLabel(scoreMedio);
        const confianca = Math.round(scoreMedio * 100);
        const crescimento = Math.round(scoreMedio * 50);
        const economia = Math.round(5000 * scoreMedio);
        const retencao = Math.round(60 + scoreMedio * 30);
        
        const altoRisco = predictions.high_risk_percentage || 0;
        const medioRisco = predictions.medium_risk_percentage || 0;
        const baixoRisco = predictions.low_risk_percentage || 0;
        
        const cardId = `analysis-card-${analysis.processId}`;
        const existingCard = document.getElementById(cardId);
        if (existingCard) existingCard.remove();
        
        const cardHTML = `
            <div class="analysis-card" id="${cardId}" data-process-id="${analysis.processId}"
                 style="opacity: 0; transform: translateY(20px);">
                <div class="card border-0 shadow-lg rounded-4 overflow-hidden" 
                     style="background: rgba(255,255,255,0.04); backdrop-filter: blur(20px); 
                            border: 1px solid rgba(255,255,255,0.06);">
                    <!-- ... conteúdo do card ... -->
                    <div class="card-header py-3 px-4" 
                         style="background: linear-gradient(135deg, rgba(255,107,53,0.08), rgba(247,147,30,0.08)); 
                                border-bottom: 1px solid rgba(255,255,255,0.04);">
                        <div class="d-flex justify-content-between align-items-center flex-wrap">
                            <div>
                                <h5 class="mb-0 fw-bold" style="color: white; font-size: 0.95rem;">
                                    <i class="fas fa-chart-line me-2" style="color: #ff6b35;"></i>
                                    ${Utils.escapeHtml(analysis.filename || 'Análise')}
                                    <span class="badge ms-2" style="background: ${scoreColor}; color: white; font-size: 0.6rem; padding: 0.2rem 0.6rem;">
                                        ${scoreIcon} ${scoreLabel}
                                    </span>
                                </h5>
                                <small style="color: rgba(255,255,255,0.3); font-size: 0.65rem;">
                                    <i class="fas fa-calendar me-1"></i> ${new Date().toLocaleDateString('pt-BR')}
                                    <i class="fas fa-database ms-2 me-1"></i> ${totalRegistros.toLocaleString()} registros
                                </small>
                            </div>
                            <div class="mt-2 mt-md-0">
                                <button class="btn btn-sm btn-pdf" onclick="window.generatePDFReport('${analysis.processId}')" 
                                        style="background: rgba(220,53,69,0.1); border: 1px solid rgba(220,53,69,0.2); 
                                               color: #dc3545; border-radius: 50px; padding: 0.2rem 0.8rem; font-size: 0.65rem;
                                               transition: all 0.3s;">
                                    <i class="fas fa-file-pdf me-1"></i> PDF
                                </button>
                                <button class="btn btn-sm btn-gpsa ms-1" onclick="window.showGPSAForAnalysis('${analysis.processId}')" 
                                        style="background: rgba(255,107,53,0.1); border: 1px solid rgba(255,107,53,0.2); 
                                               color: #ff6b35; border-radius: 50px; padding: 0.2rem 0.8rem; font-size: 0.65rem;
                                               transition: all 0.3s;">
                                    <i class="fas fa-expand me-1"></i> Detalhes
                                </button>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card-body p-4">
                        <div class="row g-3 mb-4">
                            <div class="col-12">
                                <div class="p-3 rounded-4" style="background: rgba(0,0,0,0.15); border: 1px solid rgba(255,255,255,0.03);">
                                    <div class="d-flex justify-content-between align-items-center">
                                        <div>
                                            <div style="color: rgba(255,255,255,0.4); font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.5px;">
                                                <i class="fas fa-gem me-1" style="color: #ff6b35;"></i> Score de Confiança
                                            </div>
                                            <div style="font-size: 2.2rem; font-weight: 700; color: ${scoreColor}; line-height: 1;">
                                                ${confianca}%
                                            </div>
                                            <div style="color: rgba(255,255,255,0.3); font-size: 0.6rem;">
                                                Min: ${Math.round(scoreMin * 100)}% · Max: ${Math.round(scoreMax * 100)}% · Desvio: ${Math.round(scoreStd * 100)}%
                                            </div>
                                        </div>
                                        <div class="text-end">
                                            <div style="color: rgba(255,255,255,0.3); font-size: 0.55rem;">Intervalo de confiança</div>
                                            <div style="width: 120px; height: 4px; background: rgba(255,255,255,0.06); border-radius: 4px; margin-top: 4px; overflow: hidden;">
                                                <div style="width: ${confianca}%; height: 100%; background: ${scoreColor}; border-radius: 4px; transition: width 1s ease;"></div>
                                            </div>
                                            <div style="color: ${scoreColor}; font-size: 0.55rem; margin-top: 2px;">${scoreIcon} ${scoreLabel}</div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="row g-3 mb-4">
                            <div class="col-md-3 col-6">
                                <div class="p-3 rounded-4 text-center metric-box" 
                                     style="background: rgba(0,0,0,0.12); border: 1px solid rgba(255,255,255,0.03); transition: all 0.3s;">
                                    <i class="fas fa-chart-line fa-lg" style="color: #48bb78;"></i>
                                    <div class="metric-value" style="color: white; font-size: 1.1rem; font-weight: 600; margin-top: 2px;">0%</div>
                                    <div style="color: rgba(255,255,255,0.25); font-size: 0.55rem; text-transform: uppercase; letter-spacing: 0.3px;">Crescimento</div>
                                </div>
                            </div>
                            <div class="col-md-3 col-6">
                                <div class="p-3 rounded-4 text-center metric-box"
                                     style="background: rgba(0,0,0,0.12); border: 1px solid rgba(255,255,255,0.03); transition: all 0.3s;">
                                    <i class="fas fa-coins fa-lg" style="color: #f5a623;"></i>
                                    <div class="metric-value" style="color: #f5a623; font-size: 1.1rem; font-weight: 600; margin-top: 2px;">R$ 0</div>
                                    <div style="color: rgba(255,255,255,0.25); font-size: 0.55rem; text-transform: uppercase; letter-spacing: 0.3px;">Economia/mês</div>
                                </div>
                            </div>
                            <div class="col-md-3 col-6">
                                <div class="p-3 rounded-4 text-center metric-box"
                                     style="background: rgba(0,0,0,0.12); border: 1px solid rgba(255,255,255,0.03); transition: all 0.3s;">
                                    <i class="fas fa-users fa-lg" style="color: #667eea;"></i>
                                    <div class="metric-value" style="color: #667eea; font-size: 1.1rem; font-weight: 600; margin-top: 2px;">0%</div>
                                    <div style="color: rgba(255,255,255,0.25); font-size: 0.55rem; text-transform: uppercase; letter-spacing: 0.3px;">Retenção</div>
                                </div>
                            </div>
                            <div class="col-md-3 col-6">
                                <div class="p-3 rounded-4 text-center metric-box"
                                     style="background: rgba(0,0,0,0.12); border: 1px solid rgba(255,255,255,0.03); transition: all 0.3s;">
                                    <i class="fas fa-database fa-lg" style="color: #4299e1;"></i>
                                    <div class="metric-value" style="color: white; font-size: 1.1rem; font-weight: 600; margin-top: 2px;">0</div>
                                    <div style="color: rgba(255,255,255,0.25); font-size: 0.55rem; text-transform: uppercase; letter-spacing: 0.3px;">Registros</div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="row g-3 mb-3">
                            <div class="col-12">
                                <div class="p-3 rounded-4" style="background: rgba(0,0,0,0.12); border: 1px solid rgba(255,255,255,0.03);">
                                    <div style="color: rgba(255,255,255,0.4); font-size: 0.6rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px;">
                                        <i class="fas fa-shield-alt me-1" style="color: #ff6b35;"></i> Distribuição de Risco
                                    </div>
                                    <div class="row g-2">
                                        <div class="col-4">
                                            <div class="p-2 rounded-3 text-center risk-bar" 
                                                 style="background: rgba(72,187,120,0.08); border: 1px solid rgba(72,187,120,0.12);">
                                                <div style="color: #48bb78; font-size: 1rem; font-weight: 600;">${Math.round(baixoRisco)}%</div>
                                                <div style="color: rgba(255,255,255,0.25); font-size: 0.5rem;">🟢 Baixo Risco</div>
                                            </div>
                                        </div>
                                        <div class="col-4">
                                            <div class="p-2 rounded-3 text-center risk-bar"
                                                 style="background: rgba(245,166,35,0.08); border: 1px solid rgba(245,166,35,0.12);">
                                                <div style="color: #f5a623; font-size: 1rem; font-weight: 600;">${Math.round(medioRisco)}%</div>
                                                <div style="color: rgba(255,255,255,0.25); font-size: 0.5rem;">🟡 Médio Risco</div>
                                            </div>
                                        </div>
                                        <div class="col-4">
                                            <div class="p-2 rounded-3 text-center risk-bar"
                                                 style="background: rgba(245,101,101,0.08); border: 1px solid rgba(245,101,101,0.12);">
                                                <div style="color: #f56565; font-size: 1rem; font-weight: 600;">${Math.round(altoRisco)}%</div>
                                                <div style="color: rgba(255,255,255,0.25); font-size: 0.5rem;">🔴 Alto Risco</div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        ${renderInsights(data)}
                        
                        <div class="mt-3 pt-3" style="border-top: 1px solid rgba(255,255,255,0.03);">
                            <div class="d-flex justify-content-between align-items-center flex-wrap">
                                <div style="color: rgba(255,255,255,0.15); font-size: 0.5rem;">
                                    <i class="fas fa-fingerprint me-1"></i> ID: ${analysis.processId.substring(0, 12)}...
                                </div>
                                <div>
                                    <span class="badge me-1" style="background: rgba(255,255,255,0.03); color: rgba(255,255,255,0.2); font-size: 0.5rem;">
                                        <i class="fas fa-robot me-1"></i> IA
                                    </span>
                                    ${data.pow_verified ? `<span class="badge" style="background: rgba(72,187,120,0.1); color: #48bb78; font-size: 0.5rem;">🔒 PoW</span>` : ''}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        container.insertAdjacentHTML('afterbegin', cardHTML);
        
        const cardElement = document.getElementById(cardId);
        if (cardElement) {
            Animator.fadeIn(cardElement, { y: 20, duration: 0.5 });
            
            const metricBoxes = cardElement.querySelectorAll('.metric-box');
            Animator.staggerIn(metricBoxes, { y: 10, stagger: 0.1, duration: 0.4 });
            
            const riskBars = cardElement.querySelectorAll('.risk-bar');
            Animator.staggerIn(riskBars, { y: 10, stagger: 0.08, duration: 0.3 });
            
            const metricValues = cardElement.querySelectorAll('.metric-value');
            const targets = [crescimento, economia, retencao, totalRegistros];
            metricValues.forEach((el, i) => {
                if (i < targets.length) {
                    Animator.countUp(el, targets[i], {
                        duration: 1000,
                        format: (v) => {
                            if (i === 1) return 'R$ ' + v.toLocaleString();
                            if (i === 3) return v.toLocaleString();
                            return v + '%';
                        }
                    });
                }
            });
        }
    }

    function renderInsights(data) {
        const insights = data.insights || {};
        const recommendations = insights.recomendacoes || insights.recommendations || [];
        
        if (recommendations.length === 0) return '';
        
        return `
            <div class="row g-3 mb-3">
                <div class="col-12">
                    <div class="p-3 rounded-4" style="background: rgba(0,0,0,0.12); border: 1px solid rgba(255,255,255,0.03);">
                        <div style="color: rgba(255,255,255,0.4); font-size: 0.6rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px;">
                            <i class="fas fa-lightbulb me-1" style="color: #ff6b35;"></i> Insights da IA
                        </div>
                        ${recommendations.slice(0, 3).map((r, i) => `
                            <div class="insight-item mb-2 p-2 rounded-3" 
                                 style="background: rgba(0,0,0,0.1); border-left: 3px solid #ff6b35; 
                                        color: rgba(255,255,255,0.75); font-size: 0.75rem;
                                        transition: all 0.3s;">
                                ${Utils.escapeHtml(r)}
                            </div>
                        `).join('')}
                    </div>
                </div>
            </div>
        `;
    }

    // ==============================================
    // 🔥 HISTÓRICO (CARREGAMENTO)
    // ==============================================

    async function loadHistory() {
        try {
            const token = localStorage.getItem('access_token');
            const response = await fetch(`${CONFIG.API_BASE}/analyses/history`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            
            if (response.ok) {
                const data = await response.json();
                const analyses = data.analyses || data || [];
                HistoryManager.setData(analyses);
            }
        } catch (error) {
            console.error('❌ [Dashboard] Erro ao carregar histórico:', error);
        }
    }

    // ==============================================
    // 🔥 MÉTRICAS
    // ==============================================

    function updateMetrics() {
        const state = getAppState();
        const total = State.activeAnalyses.length || 0;
        const today = State.activeAnalyses.filter(a => {
            const date = new Date(a.created_at || a.timestamp);
            const now = new Date();
            return date.toDateString() === now.toDateString();
        }).length || 0;
        
        const creditsDisplay = getCreditsDisplay();
        
        const totalEl = document.getElementById('totalAnalises');
        const todayEl = document.getElementById('analisesHoje');
        const creditsEl = document.getElementById('creditsDisplay');
        
        if (totalEl) {
            Animator.countUp(totalEl, total, {
                duration: 600,
                format: (v) => v
            });
        }
        if (todayEl) {
            Animator.countUp(todayEl, today, {
                duration: 600,
                format: (v) => v
            });
        }
        if (creditsEl) {
            creditsEl.textContent = creditsDisplay;
        }
    }

    // ==============================================
    // 🔥 UI HELPERS
    // ==============================================

    function showNotification(message, type = 'info') {
        if (window.toastr && window.toastr[type]) {
            window.toastr[type](message);
            return;
        }
        console.log(`[${type}] ${message}`);
    }

    function showLoading(message, submessage) {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            const text = document.getElementById('loadingTitle');
            const subtext = document.getElementById('loadingSubtext');
            if (text) text.textContent = message || 'Processando...';
            if (subtext) subtext.textContent = submessage || 'Aguarde...';
            overlay.classList.add('show');
        }
    }

    function hideLoading() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) overlay.classList.remove('show');
    }

    function updateLoadingProgress(percent) {
        const progress = document.getElementById('loadingProgressBar');
        const percentText = document.getElementById('loadingPercent');
        if (progress) progress.style.width = `${Math.min(100, percent)}%`;
        if (percentText) percentText.textContent = `${Math.round(percent)}%`;
    }

    function showCreditsModal() {
        const modal = document.getElementById('creditsModal');
        if (modal) {
            const bsModal = bootstrap.Modal.getInstance(modal) || new bootstrap.Modal(modal);
            bsModal.show();
        }
    }

    // ==============================================
    // 🔥 DRAG & DROP
    // ==============================================

    function setupDragAndDrop() {
        const dropZone = document.getElementById('dropArea');
        if (!dropZone) return;
        
        dropZone.addEventListener('dragenter', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });
        
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });
        
        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('dragover');
        });
        
        dropZone.addEventListener('drop', async (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            const files = Array.from(e.dataTransfer.files);
            await processUpload(files);
        });
        
        dropZone.addEventListener('click', () => {
            const fileInput = document.getElementById('fileInput');
            if (fileInput) fileInput.click();
        });
    }

    function setupUploadForm() {
        const uploadForm = document.getElementById('uploadForm');
        if (uploadForm) {
            uploadForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const fileInput = document.getElementById('fileInput');
                if (fileInput && fileInput.files.length > 0) {
                    await processUpload(Array.from(fileInput.files));
                } else {
                    showNotification('Selecione pelo menos um arquivo', 'warning');
                }
            });
        }
        
        const fileInput = document.getElementById('fileInput');
        if (fileInput) {
            fileInput.setAttribute('multiple', 'multiple');
            fileInput.addEventListener('change', (e) => {
                if (e.target.files && e.target.files.length > 0) {
                    showFilePreview(Array.from(e.target.files));
                }
            });
        }
    }

    function showFilePreview(files) {
        const container = document.getElementById('filePreviewContainer');
        if (!container) return;
        
        let html = `
            <div class="p-3 rounded-3" style="background: rgba(0,0,0,0.15);">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <strong style="color: white; font-size: 0.85rem;"><i class="fas fa-files me-2"></i>${files.length} arquivo(s):</strong>
                    <button type="button" class="btn btn-sm btn-clear-files" style="background: rgba(220,53,69,0.1); border: none; color: #dc3545; border-radius: 50px; padding: 0.15rem 0.6rem; font-size: 0.65rem; transition: all 0.3s;">
                        <i class="fas fa-times me-1"></i> Limpar
                    </button>
                </div>
                <div style="max-height: 150px; overflow-y: auto;">
        `;
        
        for (const file of files) {
            const fileSizeKB = (file.size / 1024).toFixed(1);
            html += `
                <div class="d-flex justify-content-between align-items-center py-1 px-2 file-preview-item" 
                     style="border-bottom: 1px solid rgba(255,255,255,0.03); transition: all 0.3s;">
                    <span style="color: rgba(255,255,255,0.75); font-size: 0.75rem;">
                        <i class="fas fa-file-excel text-success me-2"></i> ${Utils.escapeHtml(file.name)}
                    </span>
                    <span class="badge" style="background: rgba(255,255,255,0.03); color: rgba(255,255,255,0.3); font-size: 0.55rem;">${fileSizeKB}KB</span>
                </div>
            `;
        }
        
        html += `</div></div>`;
        container.innerHTML = html;
        
        const items = container.querySelectorAll('.file-preview-item');
        Animator.staggerIn(items, { y: -10, stagger: 0.05, duration: 0.3 });
        
        const clearBtn = container.querySelector('.btn-clear-files');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                const fileInput = document.getElementById('fileInput');
                if (fileInput) fileInput.value = '';
                container.innerHTML = '';
            });
        }
        
        const uploadBtn = document.getElementById('uploadButton');
        if (uploadBtn) {
            uploadBtn.disabled = false;
            uploadBtn.innerHTML = `<i class="fas fa-play-circle me-2"></i> Iniciar Análise <span class="badge ms-2" style="background: rgba(255,255,255,0.15); color: white; font-size: 0.55rem;">${files.length} crédito${files.length > 1 ? 's' : ''}</span>`;
        }
    }

    // ==============================================
    // 🔥 GPSA (DETALHES)
    // ==============================================

    window.showGPSAForAnalysis = function(processId) {
        const analysis = State.activeAnalyses.find(a => a.processId === processId);
        if (!analysis || !analysis.result) {
            showNotification('Aguardando conclusão da análise...', 'warning');
            return;
        }
        
        const data = analysis.result;
        const stats = data.stats || {};
        const predictions = data.predictions_summary || {};
        
        const totalRegistros = stats.rows || predictions.total || 0;
        const scoreMedio = predictions.mean || 0.65;
        const confianca = Math.round(scoreMedio * 100);
        const scoreColor = Utils.getScoreColor(scoreMedio);
        
        const modalBody = document.getElementById('gpsaModalBody');
        if (modalBody) {
            modalBody.innerHTML = `
                <div style="color: white; padding: 0.5rem;">
                    <div class="row g-3">
                        <div class="col-12">
                            <h6 style="color: #ff6b35; font-size: 0.85rem;">
                                <i class="fas fa-info-circle me-2"></i> Informações da Análise
                            </h6>
                            <div class="p-3 rounded-4" style="background: rgba(0,0,0,0.15); border: 1px solid rgba(255,255,255,0.03);">
                                <div class="row">
                                    <div class="col-6">
                                        <div style="color: rgba(255,255,255,0.3); font-size: 0.55rem;">Arquivo</div>
                                        <div style="color: white; font-weight: 500; font-size: 0.85rem;">${Utils.escapeHtml(analysis.filename || 'Desconhecido')}</div>
                                    </div>
                                    <div class="col-6">
                                        <div style="color: rgba(255,255,255,0.3); font-size: 0.55rem;">Registros</div>
                                        <div style="color: white; font-weight: 500; font-size: 0.85rem;">${totalRegistros.toLocaleString()}</div>
                                    </div>
                                    <div class="col-6 mt-2">
                                        <div style="color: rgba(255,255,255,0.3); font-size: 0.55rem;">Score Médio</div>
                                        <div style="color: ${scoreColor}; font-weight: 500; font-size: 0.85rem;">${confianca}%</div>
                                    </div>
                                    <div class="col-6 mt-2">
                                        <div style="color: rgba(255,255,255,0.3); font-size: 0.55rem;">Confiança</div>
                                        <div style="color: white; font-weight: 500; font-size: 0.85rem;">${confianca}%</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        ${renderInsightsModal(data)}
                        
                        <div class="text-center mt-3">
                            <button class="btn btn-outline-light btn-sm" onclick="window.closeGPSA()" 
                                    style="border-radius: 50px; padding: 0.3rem 1.5rem; font-size: 0.75rem; border-color: rgba(255,255,255,0.1);">
                                <i class="fas fa-times me-2"></i> Fechar
                            </button>
                        </div>
                    </div>
                </div>
            `;
        }
        
        const modal = document.getElementById('gpsaModal');
        if (modal) {
            const bsModal = bootstrap.Modal.getInstance(modal) || new bootstrap.Modal(modal);
            bsModal.show();
        }
    };

    function renderInsightsModal(data) {
        const insights = data.insights || {};
        const recommendations = insights.recomendacoes || insights.recommendations || [];
        
        if (recommendations.length === 0) return '';
        
        return `
            <div class="col-12">
                <h6 style="color: #ff6b35; font-size: 0.85rem;">
                    <i class="fas fa-lightbulb me-2"></i> Insights da IA
                </h6>
                <div class="p-3 rounded-4" style="background: rgba(0,0,0,0.15); border: 1px solid rgba(255,255,255,0.03);">
                    ${recommendations.slice(0, 3).map(r => `
                        <div class="mb-2 p-2 rounded-3" style="background: rgba(0,0,0,0.1); border-left: 3px solid #ff6b35; color: rgba(255,255,255,0.75); font-size: 0.8rem;">
                            ${Utils.escapeHtml(r)}
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }

    window.closeGPSA = function() {
        const modal = document.getElementById('gpsaModal');
        if (modal) {
            const bsModal = bootstrap.Modal.getInstance(modal);
            if (bsModal) bsModal.hide();
        }
    };

    // ==============================================
    // 🔥 PDF
    // ==============================================

    window.generatePDFReport = async function(processId) {
        const analysis = State.activeAnalyses.find(a => a.processId === processId);
        if (!analysis || !analysis.result) {
            showNotification('Aguardando conclusão da análise...', 'warning');
            return;
        }
        
        showNotification('📄 Gerando relatório PDF...', 'info');
        
        window.dispatchEvent(new CustomEvent('pdf:generate', {
            detail: {
                processId,
                analysis: analysis.result
            }
        }));
    };

    // ==============================================
    // 🔥 INICIALIZAÇÃO
    // ==============================================

    async function initialize() {
        if (State._initialized) {
            console.log('ℹ️ [Dashboard] Já inicializado');
            return;
        }

        console.log('🚀 [Dashboard v7.1] Inicializando...');

        const appReady = await waitForApp(40);
        
        if (!appReady) {
            console.error('❌ [Dashboard] app.js não respondeu');
            const token = localStorage.getItem('access_token');
            if (!token || token.length < 10) {
                console.warn('🔒 [Dashboard] Usuário não autenticado');
                window.location.replace('/login');
                return;
            }
            console.warn('⚠️ [Dashboard] Token presente, prosseguindo com cautela...');
        }

        Animator.init();
        setupDragAndDrop();
        setupUploadForm();

        // 🔥 CORRIGIDO: Inicializa gráfico com retry
        ChartManager.init('analysisChart');

        HistoryManager.init('recentAnalyses');
        await loadHistory();
        syncWithApp();
        updateMetrics();

        setInterval(() => {
            syncWithApp();
            updateMetrics();
        }, CONFIG.CREDITS_CHECK_INTERVAL);

        State._initialized = true;
        
        console.log('✅ [Dashboard v7.1] Inicializado com sucesso!');
        console.log(`   📦 App.js integrado: ${appReady}`);
        console.log(`   📊 Créditos: ${getCreditsDisplay()}`);
        console.log(`   📈 Gráfico: ${ChartManager.isReady() ? 'OK' : 'N/A'}`);
        console.log(`   📋 Histórico: ${HistoryManager._data.length} itens`);
    }

    function syncWithApp() {
        const state = getAppState();
        const app = window.App || {};
        
        State.credits = state.credits || 0;
        State.isPremium = state.isPremium || false;
        State.isAdmin = state.isAdmin || false;
        State.userName = state.user?.name || state.displayName || 'Usuário';
        
        updateCreditsDisplay();
        updateUserUI();
        updatePremiumStatusUI();
    }

    function updateCreditsDisplay() {
        const display = getCreditsDisplay();
        document.querySelectorAll('#creditsCount, #creditsDisplay, #uploadCredits, #modalCreditsCount')
            .forEach(el => {
                if (el) el.textContent = display;
            });
    }

    function updateUserUI() {
        document.querySelectorAll('#userName, .user-name').forEach(el => {
            if (el) el.textContent = State.userName;
        });
    }

    function updatePremiumStatusUI() {
        const container = document.getElementById('premiumStatusContainer');
        if (!container) return;
        
        let html = '';
        
        if (State.isAdmin) {
            html = `
                <div class="text-center py-2">
                    <span class="badge" style="background: linear-gradient(135deg, #667eea, #764ba2); color: white; padding: 0.4rem 1.5rem; font-size: 0.75rem;">
                        <i class="fas fa-user-shield me-2"></i> Administrador
                    </span>
                    <p class="mt-1 small" style="color: rgba(255,255,255,0.4); font-size: 0.65rem;">
                        <i class="fas fa-infinity me-1"></i> Créditos ilimitados
                    </p>
                </div>
            `;
        } else if (State.isPremium) {
            html = `
                <div class="text-center py-2">
                    <span class="badge" style="background: linear-gradient(135deg, #f5a623, #cd7f32); color: white; padding: 0.4rem 1.5rem; font-size: 0.75rem;">
                        <i class="fas fa-crown me-2"></i> Premium
                    </span>
                    <p class="mt-1 small" style="color: rgba(255,255,255,0.4); font-size: 0.65rem;">
                        <i class="fas fa-coins me-1"></i> ${State.credits || 0} créditos
                    </p>
                </div>
            `;
        } else {
            html = `
                <div class="text-center py-2">
                    <span class="badge" style="background: rgba(255,255,255,0.05); color: rgba(255,255,255,0.3); padding: 0.4rem 1.5rem; font-size: 0.75rem;">
                        <i class="fas fa-user me-2"></i> Grátis
                    </span>
                    <p class="mt-1 small" style="color: rgba(255,255,255,0.4); font-size: 0.65rem;">
                        <i class="fas fa-coins me-1"></i> ${State.credits || 0} créditos
                        <a href="planos.html" class="text-warning text-decoration-none ms-1" style="font-size: 0.6rem;">Fazer upgrade</a>
                    </p>
                </div>
            `;
        }
        
        container.innerHTML = html;
        Animator.fadeIn(container, { y: 10, duration: 0.4 });
    }

    // ==============================================
    // 🔥 EVENTOS
    // ==============================================

    document.addEventListener('app:ready', function(event) {
        console.log('📢 [Dashboard] app:ready recebido');
        State._appReady = true;
        initialize();
    });

    document.addEventListener('DOMContentLoaded', function() {
        const token = localStorage.getItem('access_token');
        const isAuth = token && token !== 'undefined' && token !== 'null' && token.length > 10;
        
        if (!isAuth) {
            console.log('🔒 [Dashboard] Usuário não autenticado');
            return;
        }

        if (State._initialized) return;

        if (window._appReadyFired || window.__APP_STATE?.isAppReady) {
            console.log('✅ [Dashboard] App já pronto, inicializando...');
            initialize();
            return;
        }

        console.log('⏳ [Dashboard] Aguardando app:ready (fallback em 3s)...');
        setTimeout(function() {
            if (!State._initialized) {
                console.log('🔄 [Dashboard] Fallback: tentando inicializar...');
                initialize();
            }
        }, 3000);
    });

    document.addEventListener('creditsUpdated', function(e) {
        const data = e.detail || {};
        updateCreditsDisplay();
        updatePremiumStatusUI();
        updateMetrics();
    });

    document.addEventListener('premiumStatusUpdated', function(e) {
        const data = e.detail || {};
        State.isPremium = data.isPremium || false;
        State.credits = data.creditsBalance || 0;
        updateCreditsDisplay();
        updatePremiumStatusUI();
        updateMetrics();
    });

    document.addEventListener('analysis:success', function(e) {
        const detail = e.detail || {};
        const analysisData = {
            processId: detail.processId,
            filename: detail.filename,
            status: 'completed',
            result: detail.result,
            created_at: new Date().toISOString()
        };
        
        if (!State.activeAnalyses.find(a => a.processId === detail.processId)) {
            State.activeAnalyses.push(analysisData);
        }
        
        renderAnalysisCard(analysisData);
        HistoryManager.addItem(analysisData);
        ChartManager.addPoint(
            new Date().toLocaleDateString('pt-BR', { month: 'short' }),
            State.activeAnalyses.length
        );
        updateMetrics();
        
        if (detail.result?.user_credits !== undefined) {
            State.credits = detail.result.user_credits;
            updateCreditsDisplay();
        }
    });

    document.addEventListener('auth:unauthorized', function() {
        console.log('🧹 [Dashboard] Limpando recursos...');
        State.pollingIntervals.forEach(clearInterval);
        State.pollingIntervals = [];
        State.activeAnalyses = [];
        State._initialized = false;
        ChartManager.destroy();
    });

    // ==============================================
    // 🔥 INJETA ESTILOS ADICIONAIS
    // ==============================================

    (function injectStyles() {
        if (document.getElementById('dashboardV71Styles')) return;
        
        const style = document.createElement('style');
        style.id = 'dashboardV71Styles';
        style.textContent = `
            .analysis-card {
                animation: fadeInUp 0.5s ease-out;
            }
            @keyframes fadeInUp {
                from { opacity: 0; transform: translateY(20px); }
                to { opacity: 1; transform: translateY(0); }
            }
            @keyframes slideIn {
                from { opacity: 0; transform: translateY(-10px); }
                to { opacity: 1; transform: translateY(0); }
            }
            @keyframes pulse {
                0%, 100% { transform: scale(1); }
                50% { transform: scale(1.05); }
            }
            
            .metric-box {
                transition: all 0.3s ease;
                cursor: default;
            }
            .metric-box:hover {
                transform: translateY(-2px);
                background: rgba(255,255,255,0.06) !important;
                border-color: rgba(255,255,255,0.1) !important;
            }
            
            .risk-bar {
                transition: all 0.3s ease;
                cursor: default;
            }
            .risk-bar:hover {
                transform: translateY(-2px) scale(1.02);
            }
            
            .insight-item {
                transition: all 0.3s ease;
                cursor: default;
            }
            .insight-item:hover {
                background: rgba(255,107,53,0.05) !important;
                padding-left: 1rem !important;
            }
            
            .btn-pdf:hover {
                background: #dc3545 !important;
                color: white !important;
                transform: translateY(-2px);
                box-shadow: 0 4px 15px rgba(220, 53, 69, 0.3);
            }
            .btn-gpsa:hover {
                background: #ff6b35 !important;
                color: white !important;
                transform: translateY(-2px);
                box-shadow: 0 4px 15px rgba(255, 107, 53, 0.3);
            }
            
            .dragover {
                border-color: #48bb78 !important;
                background: rgba(72, 187, 120, 0.1) !important;
                transform: scale(1.02);
                box-shadow: 0 0 40px rgba(72, 187, 120, 0.05);
            }
            
            .file-preview-item {
                transition: all 0.3s ease;
            }
            .file-preview-item:hover {
                background: rgba(255,255,255,0.03);
            }
            
            .timeline::-webkit-scrollbar,
            .history-scroll::-webkit-scrollbar {
                width: 4px;
            }
            .timeline::-webkit-scrollbar-track,
            .history-scroll::-webkit-scrollbar-track {
                background: rgba(255,255,255,0.03);
                border-radius: 4px;
            }
            .timeline::-webkit-scrollbar-thumb,
            .history-scroll::-webkit-scrollbar-thumb {
                background: rgba(255,107,53,0.2);
                border-radius: 4px; 
            }
            .timeline::-webkit-scrollbar-thumb:hover,
            .history-scroll::-webkit-scrollbar-thumb:hover {
                background: rgba(255,107,53,0.4);
            }
        `;
        document.head.appendChild(style);
    })();

    console.log('✅ [Dashboard v7.1] Módulo carregado com sucesso!');
    console.log('   🔥 CORRIGIDO: ChartManager com retry inteligente');
    console.log('   🔥 MELHORADO: Detecção de container com MutationObserver');
    console.log('   🔥 ADICIONADO: Fallback com timeout');
    console.log('   🎬 Animações GSAP + CSS');
    console.log('   📊 Gráficos leves (Chart.js otimizado)');
    console.log('   📋 Virtual scroll para histórico');

})();