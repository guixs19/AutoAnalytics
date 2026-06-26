// frontend/js/dashboard.js - VERSÃO REVOLUCIONÁRIA V5.5
/**
 * AutoAnalytics - Módulo de Visualização e Esteira de Análise
 * Fluxo: Drag & Drop (CSV/Excel) -> ML -> Gemini IA -> PDF -> 3 Gráficos Lado a Lado
 * 
 * 🏗️ ARQUITETURA V5.5:
 * 1. 🔥 Escopo Isolado (IIFE) - Proteção contra vazamentos
 * 2. 🔥 Gatilho por Evento 'app:ready' - Sincronização com app.js v5.1
 * 3. 🔥 Cleanup de Gráficos - Prevenção de memory leaks
 * 4. 🔥 Anti-Concorrência no PDF - Botão com lock e feedback visual
 * 5. 🔥 Autolimpeza em Desautenticação - Evento 'auth:unauthorized'
 * 6. 🔥 Sistema de Polling Inteligente com Rate Limiter
 * 7. 🔥 Cache de Elementos DOM para Performance
 * 8. 🔥 Animações com GSAP e AOS integradas
 */

(function() {
    'use strict';

    console.log('📦 [Dashboard] Módulo carregado na memória. Aguardando sinal "app:ready"...');

    // ============================================================================
    // 🔥 CONFIGURAÇÕES (SINCRONIZADAS COM APP.JS)
    // ============================================================================
    
    const CONFIG = {
        MAX_FILES_PER_BATCH: 3,
        MAX_FILE_SIZE_KB: 200,
        API_BASE: '/api',
        POLLING_INTERVAL: 2000,
        MAX_POLLING_ATTEMPTS: 60,
        CREDITS_CHECK_INTERVAL: 30000,
        CHART_COLORS: {
            primary: '#667eea',
            success: '#48bb78',
            warning: '#f5a623',
            danger: '#f56565',
            info: '#4299e1',
            dark: '#2d3748'
        }
    };

    // ============================================================================
    // 🔥 GERENCIAMENTO DE ESTADO ISOLADO
    // ============================================================================
    
    const State = {
        activeAnalyses: [],
        pollingIntervals: [],
        isProcessing: false,
        currentUser: null,
        credits: 0,
        isPremium: false,
        isAdmin: false,
        chartInstances: {
            trend: null,
            risk: null,
            perf: null,
            gpsa: null
        },
        domCache: new Map(),
        _initialized: false
    };

    // ============================================================================
    // 🔥 UTILITÁRIOS DE DOM (COM CACHE)
    // ============================================================================
    
    const DOM = {
        get: (selector) => {
            if (!State.domCache.has(selector)) {
                const el = document.querySelector(selector);
                State.domCache.set(selector, el);
                return el;
            }
            return State.domCache.get(selector);
        },
        
        getAll: (selector) => {
            return document.querySelectorAll(selector);
        },
        
        clearCache: () => {
            State.domCache.clear();
        },
        
        create: (tag, classes = '', attributes = {}) => {
            const el = document.createElement(tag);
            if (classes) el.className = classes;
            Object.entries(attributes).forEach(([key, value]) => {
                el.setAttribute(key, value);
            });
            return el;
        }
    };

    // ============================================================================
    // 🔥 GERENCIADOR DE NOTIFICAÇÕES
    // ============================================================================
    
    const Notify = {
        show: (message, type = 'info', duration = 5000) => {
            // Tenta usar toastr se disponível
            if (window.toastr && window.toastr[type]) {
                window.toastr[type](message);
                return;
            }
            
            // Fallback: notificação customizada
            const colors = {
                success: '#48bb78',
                error: '#f56565',
                warning: '#f5a623',
                info: '#667eea'
            };
            
            const bgColor = colors[type] || colors.info;
            const icon = type === 'success' ? 'check-circle' : 
                        type === 'error' ? 'times-circle' : 
                        type === 'warning' ? 'exclamation-triangle' : 'info-circle';
            
            const notification = DOM.create('div', 'custom-notification');
            notification.style.cssText = `
                position: fixed; bottom: 20px; right: 20px; 
                background: white; border-left: 4px solid ${bgColor}; 
                padding: 12px 20px; border-radius: 8px; 
                box-shadow: 0 4px 20px rgba(0,0,0,0.15); 
                z-index: 10000; 
                animation: slideInRight 0.3s ease;
                max-width: 350px;
                font-family: 'Inter', sans-serif;
            `;
            notification.innerHTML = `
                <i class="fas fa-${icon}" style="color: ${bgColor}; margin-right: 8px;"></i>
                <span style="color: #2d3748;">${message}</span>
            `;
            document.body.appendChild(notification);
            
            setTimeout(() => {
                notification.style.opacity = '0';
                notification.style.transform = 'translateX(20px)';
                notification.style.transition = 'all 0.3s ease';
                setTimeout(() => notification.remove(), 300);
            }, duration);
        },
        
        success: (msg) => Notify.show(msg, 'success'),
        error: (msg) => Notify.show(msg, 'error'),
        warning: (msg) => Notify.show(msg, 'warning'),
        info: (msg) => Notify.show(msg, 'info')
    };

    // ============================================================================
    // 🔥 GERENCIADOR DE LOADING (COM ANIMAÇÃO)
    // ============================================================================
    
    const Loading = {
        show: (message = 'Processando análise...', submessage = 'A IA está analisando seus dados') => {
            const overlay = DOM.get('#loadingOverlay');
            if (!overlay) return;
            
            const text = DOM.get('#loadingText');
            const subtext = DOM.get('#loadingSubtext');
            const progress = DOM.get('#loadingProgressBar');
            const percent = DOM.get('#loadingPercent');
            const steps = DOM.getAll('.loading-step');
            
            if (text) text.textContent = message;
            if (subtext) subtext.textContent = submessage;
            if (progress) progress.style.width = '0%';
            if (percent) percent.textContent = '0%';
            
            steps.forEach((step, index) => {
                step.classList.remove('active', 'done');
                if (index === 0) step.classList.add('active');
            });
            
            overlay.classList.add('show');
            
            // Anima entrada
            if (window.gsap) {
                window.gsap.from(overlay, {
                    opacity: 0,
                    duration: 0.4,
                    ease: 'power2.out'
                });
            }
        },
        
        update: (percent, message = null) => {
            const progress = DOM.get('#loadingProgressBar');
            const text = DOM.get('#loadingText');
            const percentText = DOM.get('#loadingPercent');
            const steps = DOM.getAll('.loading-step');
            
            const clampedPercent = Math.min(100, Math.max(0, percent));
            
            if (progress) progress.style.width = `${clampedPercent}%`;
            if (percentText) percentText.textContent = `${Math.round(clampedPercent)}%`;
            if (message && text) text.textContent = message;
            
            if (steps.length > 0) {
                const activeStep = Math.floor((clampedPercent / 100) * steps.length);
                steps.forEach((step, index) => {
                    step.classList.remove('active', 'done');
                    if (index < activeStep) {
                        step.classList.add('done');
                    } else if (index === activeStep) {
                        step.classList.add('active');
                    }
                });
            }
        },
        
        hide: () => {
            const overlay = DOM.get('#loadingOverlay');
            if (!overlay) return;
            
            if (window.gsap) {
                window.gsap.to(overlay, {
                    opacity: 0,
                    duration: 0.3,
                    ease: 'power2.in',
                    onComplete: () => overlay.classList.remove('show')
                });
            } else {
                overlay.classList.remove('show');
            }
        }
    };

    // ============================================================================
    // 🔥 CLASSE GPSA - GERENCIADOR DE VISUALIZAÇÃO (3 GRÁFICOS LADO A LADO)
    // ============================================================================
    
    class GPSAVisualization {
        constructor() {
            this.container = null;
            this.currentResult = null;
            this.chartInstances = {
                trend: null,
                risk: null,
                perf: null
            };
            this.animations = [];
        }
        
        /**
         * Inicializa e exibe o painel dinâmico na tela
         */
        showDashboard(containerId, resultData) {
            this.container = document.getElementById(containerId);
            if (!this.container) {
                console.error(`❌ [Dashboard] Contêiner #${containerId} não encontrado.`);
                return;
            }
            
            this.currentResult = resultData;
            this.container.style.display = 'block';
            
            // 🔥 Limpa gráficos antigos para liberar memória
            this.cleanupExistingCharts();
            
            this.renderDashboardLayout();
            this.initializeCharts();
            this.triggerVisualEffects();
        }

        /**
         * Destrói instâncias antigas para evitar memory leaks
         */
        cleanupExistingCharts() {
            console.log('🧹 [Dashboard] Limpando instâncias anteriores de gráficos...');
            
            Object.keys(this.chartInstances).forEach(key => {
                if (this.chartInstances[key]) {
                    try {
                        this.chartInstances[key].destroy();
                    } catch (e) {
                        // Ignora erro de destruição
                    }
                    this.chartInstances[key] = null;
                }
            });
            
            // Limpa também do State global
            Object.keys(State.chartInstances).forEach(key => {
                if (State.chartInstances[key]) {
                    try {
                        State.chartInstances[key].destroy();
                    } catch (e) {
                        // Ignora erro de destruição
                    }
                    State.chartInstances[key] = null;
                }
            });
        }

        /**
         * Injeta a estrutura HTML responsiva para os 3 gráficos lado a lado
         */
        renderDashboardLayout() {
            const data = this.currentResult || {};
            const stats = data.stats || {};
            const predictions = data.predictions_summary || {};
            
            const totalRegistros = stats.rows || predictions.total || 0;
            const scoreMedio = predictions.mean || 0.65;
            const altoRisco = predictions.high_risk_percentage || 0;
            const baixoRisco = predictions.low_risk_percentage || 0;
            const medioRisco = 100 - altoRisco - baixoRisco;
            
            const crescimento = Math.round(scoreMedio * 50);
            const economia = Math.round(5000 * scoreMedio);
            const retencao = Math.round(60 + scoreMedio * 30);
            
            // Detecta tipo de crescimento
            const growth = this.detectGrowthType(scoreMedio);
            
            this.container.innerHTML = `
                <div class="gpsa-dashboard" style="color: white;">
                    <!-- HEADER -->
                    <div class="text-center mb-4">
                        <h5 style="color: #f5a623;">
                            <i class="fas fa-chart-line me-2"></i>
                            GPSA - Impacto no Negócio
                        </h5>
                        <p style="color: rgba(255,255,255,0.5); font-size: 0.85rem;">
                            Análise baseada em ${totalRegistros.toLocaleString()} registros
                        </p>
                    </div>
                    
                    <!-- SCORE CIRCULAR -->
                    <div class="text-center mb-4">
                        <div style="position: relative; display: inline-block;">
                            <svg width="120" height="120" viewBox="0 0 120 120">
                                <circle cx="60" cy="60" r="50" fill="none" stroke="rgba(255,255,255,0.1)" stroke-width="8"/>
                                <circle class="gpsa-score-ring" cx="60" cy="60" r="50" fill="none" 
                                        stroke="url(#gpsaGrad)" stroke-width="8" 
                                        stroke-dasharray="314" stroke-dashoffset="314"
                                        style="transform: rotate(-90deg); transform-origin: 50% 50%;"/>
                                <defs>
                                    <linearGradient id="gpsaGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                                        <stop offset="0%" style="stop-color:#667eea;stop-opacity:1" />
                                        <stop offset="100%" style="stop-color:#f5a623;stop-opacity:1" />
                                    </linearGradient>
                                </defs>
                            </svg>
                            <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); text-align: center;">
                                <div class="gpsa-score-value" style="font-size: 28px; font-weight: bold; color: #f5a623;">0%</div>
                                <div style="font-size: 10px; color: rgba(255,255,255,0.4);">Confiança</div>
                            </div>
                        </div>
                        <div class="mt-2">
                            <span class="badge" style="background: ${growth.color}; color: white; padding: 0.4rem 1rem; font-size: 0.85rem;">
                                ${growth.icon} ${growth.label}
                            </span>
                        </div>
                        <p style="color: rgba(255,255,255,0.6); font-size: 0.8rem; margin-top: 0.3rem;">
                            ${growth.desc}
                        </p>
                    </div>
                    
                    <!-- 3 CARDS DE IMPACTO -->
                    <div class="row g-3 mb-4">
                        <div class="col-md-4">
                            <div class="impact-card text-center p-3 rounded-4" style="background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.05); transition: transform 0.3s;">
                                <i class="fas fa-chart-line fa-2x" style="color: #48bb78;"></i>
                                <h6 class="mt-2" style="color: white; font-size: 0.85rem;">Crescimento</h6>
                                <div class="impact-value" style="font-size: 28px; font-weight: bold; color: #48bb78;" data-target="${crescimento}">0%</div>
                                <small style="color: rgba(255,255,255,0.4); font-size: 0.7rem;">em 3 meses</small>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="impact-card text-center p-3 rounded-4" style="background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.05); transition: transform 0.3s;">
                                <i class="fas fa-coins fa-2x" style="color: #f5a623;"></i>
                                <h6 class="mt-2" style="color: white; font-size: 0.85rem;">Economia</h6>
                                <div class="impact-value" style="font-size: 28px; font-weight: bold; color: #f5a623;" data-target="${economia}">R$ 0</div>
                                <small style="color: rgba(255,255,255,0.4); font-size: 0.7rem;">por mês</small>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="impact-card text-center p-3 rounded-4" style="background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.05); transition: transform 0.3s;">
                                <i class="fas fa-users fa-2x" style="color: #667eea;"></i>
                                <h6 class="mt-2" style="color: white; font-size: 0.85rem;">Retenção</h6>
                                <div class="impact-value" style="font-size: 28px; font-weight: bold; color: #667eea;" data-target="${retencao}">0%</div>
                                <small style="color: rgba(255,255,255,0.4); font-size: 0.7rem;">clientes fiéis</small>
                            </div>
                        </div>
                    </div>
                    
                    <!-- GRÁFICO + INSIGHTS LADO A LADO -->
                    <div class="row g-3 mb-4">
                        <div class="col-md-6">
                            <div class="p-3 rounded-4" style="background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.05);">
                                <h6 style="color: white; font-size: 0.85rem;">
                                    <i class="fas fa-chart-line me-2" style="color: #f5a623;"></i>
                                    Projeção de Crescimento
                                </h6>
                                <div style="height: 180px;">
                                    <canvas id="gpsaTrendChart"></canvas>
                                </div>
                            </div>
                        </div>
                        <div class="col-md-6">
                            <div class="p-3 rounded-4" style="background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.05);">
                                <h6 style="color: white; font-size: 0.85rem;">
                                    <i class="fas fa-lightbulb me-2" style="color: #f5a623;"></i>
                                    Insights IA
                                </h6>
                                <div class="gpsa-insights" style="max-height: 180px; overflow-y: auto; font-size: 0.8rem;">
                                    ${this.renderInsights(data)}
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- RISCO -->
                    <div class="row g-3 mb-4">
                        <div class="col-12">
                            <div class="p-3 rounded-4" style="background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.05);">
                                <h6 style="color: white; font-size: 0.85rem;">
                                    <i class="fas fa-chart-pie me-2" style="color: #f5a623;"></i>
                                    Distribuição de Risco
                                </h6>
                                <div class="row text-center">
                                    <div class="col-4">
                                        <div style="background: rgba(245,101,101,0.12); border-radius: 10px; padding: 0.5rem; border: 1px solid rgba(245,101,101,0.2);">
                                            <div style="color: #f56565; font-size: 20px; font-weight: bold;">${Math.round(altoRisco)}%</div>
                                            <div style="color: rgba(255,255,255,0.4); font-size: 0.65rem;">🔴 Alto Risco</div>
                                        </div>
                                    </div>
                                    <div class="col-4">
                                        <div style="background: rgba(245,166,35,0.12); border-radius: 10px; padding: 0.5rem; border: 1px solid rgba(245,166,35,0.2);">
                                            <div style="color: #f5a623; font-size: 20px; font-weight: bold;">${Math.round(medioRisco)}%</div>
                                            <div style="color: rgba(255,255,255,0.4); font-size: 0.65rem;">🟡 Médio Risco</div>
                                        </div>
                                    </div>
                                    <div class="col-4">
                                        <div style="background: rgba(72,187,120,0.12); border-radius: 10px; padding: 0.5rem; border: 1px solid rgba(72,187,120,0.2);">
                                            <div style="color: #48bb78; font-size: 20px; font-weight: bold;">${Math.round(baixoRisco)}%</div>
                                            <div style="color: rgba(255,255,255,0.4); font-size: 0.65rem;">🟢 Baixo Risco</div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- FECHAR -->
                    <div class="text-center">
                        <button class="btn btn-outline-light btn-sm" onclick="window.closeGPSA()" style="border-radius: 50px; padding: 0.4rem 1.5rem; font-size: 0.8rem;">
                            <i class="fas fa-times me-2"></i> Fechar
                        </button>
                    </div>
                </div>
            `;
        }
        
        renderInsights(data) {
            const insights = data.insights || {};
            const recommendations = insights.recomendacoes || insights.recommendations || [];
            
            if (recommendations.length > 0) {
                return recommendations.slice(0, 4).map(r => `
                    <div class="mb-2 p-2 rounded-3" style="background: rgba(0,0,0,0.15); border-left: 3px solid #f5a623;">
                        💡 ${escapeHtml(r)}
                    </div>
                `).join('');
            }
            
            const scoreMedio = data.predictions_summary?.mean || 0.65;
            const crescimento = Math.round(scoreMedio * 50);
            const retencao = Math.round(60 + scoreMedio * 30);
            
            return `
                <div class="mb-2 p-2 rounded-3" style="background: rgba(0,0,0,0.15); border-left: 3px solid #48bb78;">
                    ✅ Score de confiança: ${Math.round(scoreMedio * 100)}%
                </div>
                <div class="mb-2 p-2 rounded-3" style="background: rgba(0,0,0,0.15); border-left: 3px solid #f5a623;">
                    📈 Crescimento projetado: ${crescimento}%
                </div>
                <div class="mb-2 p-2 rounded-3" style="background: rgba(0,0,0,0.15); border-left: 3px solid #667eea;">
                    👥 Retenção de clientes: ${retencao}%
                </div>
            `;
        }
        
        detectGrowthType(scoreMedio) {
            if (scoreMedio > 0.85) {
                return { type: 'exponential', icon: '🚀', label: 'Acelerado', desc: 'Crescimento rápido! Continue assim!', color: '#48bb78' };
            } else if (scoreMedio > 0.7) {
                return { type: 'quadratic', icon: '📈', label: 'Forte', desc: 'Tendência de aceleração!', color: '#f5a623' };
            } else if (scoreMedio > 0.55) {
                return { type: 'linear', icon: '➡️', label: 'Constante', desc: 'Crescimento estável e previsível.', color: '#667eea' };
            } else {
                return { type: 'logarithmic', icon: '🔄', label: 'Desacelerando', desc: 'Hora de inovar e reverter!', color: '#f56565' };
            }
        }

        /**
         * Renderiza os novos gráficos a partir das métricas calculadas pelo ML
         */
        initializeCharts() {
            console.log('📊 [Dashboard] Inicializando renderização gráfica...');
            const data = this.currentResult || {};
            const predictions = data.predictions_summary || {};
            const scoreMedio = predictions.mean || 0.65;
            const growth = this.detectGrowthType(scoreMedio);
            
            // GRÁFICO DE TENDÊNCIA
            const ctxTrend = document.getElementById('gpsaTrendChart')?.getContext('2d');
            if (ctxTrend) {
                const meses = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
                const dados = this.generateGrowthData(scoreMedio, growth.type);
                
                this.chartInstances.trend = new Chart(ctxTrend, {
                    type: 'line',
                    data: {
                        labels: meses,
                        datasets: [{
                            label: 'Crescimento',
                            data: dados,
                            borderColor: '#f5a623',
                            backgroundColor: 'rgba(245, 166, 35, 0.1)',
                            borderWidth: 2,
                            fill: true,
                            tension: 0.3,
                            pointRadius: 2,
                            pointBackgroundColor: '#f5a623'
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { display: false }
                        },
                        scales: {
                            y: { 
                                min: 0, 
                                max: 100, 
                                grid: { color: 'rgba(255,255,255,0.05)' },
                                ticks: { color: 'rgba(255,255,255,0.3)', font: { size: 8 } }
                            },
                            x: { 
                                grid: { display: false },
                                ticks: { color: 'rgba(255,255,255,0.3)', font: { size: 8 } }
                            }
                        }
                    }
                });
            }
            
            // Armazena no State global
            State.chartInstances.gpsa = this.chartInstances;
        }
        
        generateGrowthData(scoreMedio, growthType) {
            const baseValue = 20;
            const maxGrowth = Math.round(scoreMedio * 50);
            const dados = [];
            
            for (let i = 0; i < 12; i++) {
                let t = i / 11;
                let valor;
                switch(growthType) {
                    case 'exponential':
                        valor = baseValue + (maxGrowth) * (Math.pow(2, t) - 1);
                        break;
                    case 'quadratic':
                        valor = baseValue + (maxGrowth) * Math.pow(t, 1.5);
                        break;
                    case 'linear':
                        valor = baseValue + (maxGrowth) * t;
                        break;
                    default:
                        valor = baseValue + (maxGrowth) * Math.log(1 + t * 2) / Math.log(3);
                }
                dados.push(Math.min(100, Math.round(valor)));
            }
            return dados;
        }

        triggerVisualEffects() {
            // Anima score circular
            const scoreElement = this.container.querySelector('.gpsa-score-value');
            const ring = this.container.querySelector('.gpsa-score-ring');
            const impactValues = this.container.querySelectorAll('.impact-value');
            const cards = this.container.querySelectorAll('.impact-card');
            
            const targetScore = Math.round((this.currentResult?.predictions_summary?.mean || 0.65) * 100);
            const circumference = 314;
            
            // Anima score com GSAP ou Anime.js
            if (window.anime) {
                // Score
                if (scoreElement) {
                    window.anime({
                        targets: { value: 0 },
                        value: targetScore,
                        duration: 2500,
                        easing: 'easeOutElastic(1, .8)',
                        update: function(anim) {
                            scoreElement.textContent = Math.round(anim.animations[0].currentValue) + '%';
                        }
                    });
                }
                
                // Ring
                if (ring) {
                    window.anime({
                        targets: { value: 0 },
                        value: targetScore,
                        duration: 2500,
                        easing: 'easeOutElastic(1, .8)',
                        update: function(anim) {
                            const current = Math.round(anim.animations[0].currentValue);
                            const offset = circumference - (current / 100) * circumference;
                            ring.style.strokeDashoffset = offset;
                        }
                    });
                }
                
                // Impact values
                impactValues.forEach(el => {
                    const target = parseInt(el.dataset.target);
                    if (isNaN(target)) return;
                    const isCurrency = el.textContent.includes('R$');
                    
                    window.anime({
                        targets: { value: 0 },
                        value: target,
                        duration: 2500,
                        easing: 'easeOutQuad',
                        update: function(anim) {
                            const current = Math.round(anim.animations[0].currentValue);
                            if (isCurrency) {
                                el.textContent = `R$ ${current.toLocaleString('pt-BR')}`;
                            } else {
                                el.textContent = current + '%';
                            }
                        }
                    });
                });
                
                // Cards com stagger
                if (cards.length > 0 && window.gsap) {
                    window.gsap.from(cards, {
                        y: 20,
                        opacity: 0,
                        duration: 0.6,
                        stagger: 0.1,
                        ease: 'power3.out'
                    });
                }
            }
            
            // Refresh AOS
            if (typeof AOS !== 'undefined') {
                AOS.refresh();
            }
        }
        
        hide() {
            if (this.container) {
                if (window.gsap) {
                    window.gsap.to(this.container, {
                        opacity: 0,
                        duration: 0.3,
                        ease: 'power2.in',
                        onComplete: () => {
                            this.container.style.display = 'none';
                            this.cleanupExistingCharts();
                        }
                    });
                } else {
                    this.container.style.display = 'none';
                    this.cleanupExistingCharts();
                }
            }
        }
    }

    // ============================================================================
    // 🔥 INSTÂNCIA DO GPSA
    // ============================================================================
    
    const gpsaVisualizer = new GPSAVisualization();

    // ============================================================================
    // 🔥 FUNÇÕES DE FETCH COM AUTH E RATE LIMIT
    // ============================================================================
    
    async function fetchWithAuth(url, options = {}) {
        if (window.App && typeof window.App.fetchWithAuth === 'function') {
            return window.App.fetchWithAuth(url, options);
        }
        
        const token = localStorage.getItem('access_token');
        if (!token) {
            Notify.warning('Sessão expirada. Faça login novamente.');
            return null;
        }
        
        const headers = {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
            ...options.headers
        };
        
        try {
            const response = await fetch(url, { ...options, headers });
            
            if (response.status === 401) {
                // Dispara evento de não autorizado
                window.dispatchEvent(new CustomEvent('auth:unauthorized', {
                    detail: { message: 'Token expirado' }
                }));
                return null;
            }
            
            if (response.status === 429) {
                const data = await response.json().catch(() => ({}));
                Notify.warning(data.message || 'Muitas requisições. Aguarde um momento.');
                return response;
            }
            
            return response;
        } catch (error) {
            console.error('Fetch error:', error);
            Notify.error('Erro de conexão. Tente novamente.');
            return null;
        }
    }

    // ============================================================================
    // 🔥 GERENCIADOR DE CRÉDITOS (REATIVO)
    // ============================================================================
    
    function updateCreditsDisplay() {
        const credits = State.credits;
        const isPremium = State.isPremium;
        const isAdmin = State.isAdmin;
        
        let display = '0';
        if (isAdmin) {
            display = '∞';
        } else if (isPremium) {
            display = `${credits}/${CONFIG.MAX_CREDITS_BALANCE || 3}`;
        } else {
            display = String(credits || 0);
        }
        
        document.querySelectorAll('.credits-display, .user-credits, #creditsCount, #uploadCredits, #creditsDisplay').forEach(el => {
            if (el) el.textContent = display;
        });
    }

    // ============================================================================
    // 🔥 FUNÇÕES DE UPLOAD E PROCESSAMENTO
    // ============================================================================
    
    async function processUpload(files) {
        if (!files || files.length === 0) {
            Notify.warning('Selecione pelo menos um arquivo');
            return;
        }
        
        if (files.length > CONFIG.MAX_FILES_PER_BATCH) {
            Notify.error(`Máximo de ${CONFIG.MAX_FILES_PER_BATCH} arquivos por vez.`);
            return;
        }
        
        // Verifica tamanho dos arquivos
        for (const file of files) {
            if (file.size > CONFIG.MAX_FILE_SIZE_KB * 1024) {
                Notify.error(`❌ ${file.name} excede ${CONFIG.MAX_FILE_SIZE_KB}KB`);
                return;
            }
        }
        
        // Verifica créditos
        if (!await checkCreditsBeforeUpload(files.length)) {
            return;
        }
        
        // Inicia loading
        Loading.show('Iniciando análise...', `Preparando ${files.length} arquivo(s) para processamento`);
        Loading.update(5, 'Iniciando...');
        
        // 🔥 Prepara PoW se disponível
        try {
            if (window.App && typeof window.App.preparePowForUpload === 'function') {
                await window.App.preparePowForUpload();
            }
        } catch (e) {
            console.warn('Erro ao preparar PoW:', e);
        }
        
        const formData = new FormData();
        for (const file of files) {
            formData.append('files', file);
        }
        formData.append('analysis_type', 'auto');
        formData.append('ai_model', 'auto');
        
        const token = localStorage.getItem('access_token');
        
        // 🔥 Adiciona PoW ao upload
        const headers = {
            'Authorization': `Bearer ${token}`
        };
        
        try {
            // Tenta obter solução PoW
            if (window.App && typeof window.App.getPowStats === 'function') {
                const stats = window.App.getPowStats();
                if (stats && stats.solutionsReady > 0) {
                    if (window.powClient && typeof window.powClient.getInstantSolution === 'function') {
                        const solution = await window.powClient.getInstantSolution();
                        if (solution) {
                            headers['X-PoW-Prefix'] = solution.prefix;
                            headers['X-PoW-Nonce'] = solution.nonce;
                            headers['X-PoW-Complexity'] = String(solution.complexity);
                            console.log('⚡ PoW adicionado ao upload');
                        }
                    }
                }
            }
        } catch (e) {
            console.warn('Erro ao obter PoW:', e);
        }
        
        try {
            const response = await fetch(`${CONFIG.API_BASE}/upload-auto`, {
                method: 'POST',
                headers: headers,
                body: formData
            });
            
            // 🔥 Tratamento do PoW (428 = Precondition Required)
            if (response.status === 428) {
                Notify.info('Proteção anti-bot: recalculando...');
                
                if (window.App && typeof window.App.preparePowForUpload === 'function') {
                    await window.App.preparePowForUpload();
                }
                
                // Retry com novo PoW
                const retryResponse = await fetch(`${CONFIG.API_BASE}/upload-auto`, {
                    method: 'POST',
                    headers: headers,
                    body: formData
                });
                
                const retryData = await retryResponse.json();
                
                if (retryResponse.ok && retryData.processed_files?.length > 0) {
                    handleUploadResponse(retryData, files);
                } else {
                    Notify.error(retryData?.detail || 'Erro no upload com PoW');
                    Loading.hide();
                }
                return;
            }
            
            const data = await response.json();
            
            if (response.ok && data.processed_files?.length > 0) {
                handleUploadResponse(data, files);
            } else {
                Notify.error(data?.detail || 'Erro no upload');
                Loading.hide();
            }
        } catch (error) {
            console.error('Upload error:', error);
            Notify.error('Erro ao processar arquivo(s)');
            Loading.hide();
        }
    }
    
    function handleUploadResponse(data, files) {
        Notify.success(`✅ ${data.processed_files.length} arquivo(s) processado(s)!`);
        Loading.update(10, 'Analisando dados...');
        
        // Inicia polling para cada arquivo
        for (const processed of data.processed_files) {
            startPolling(processed.process_id, processed.filename);
        }
        
        // Atualiza créditos
        loadUserCredits();
        
        // Limpa input
        const fileInput = DOM.get('#fileInput');
        if (fileInput) fileInput.value = '';
        const previewContainer = DOM.get('#filePreviewContainer');
        if (previewContainer) previewContainer.innerHTML = '';
    }
    
    async function startPolling(processId, filename) {
        let attempts = 0;
        const maxAttempts = CONFIG.MAX_POLLING_ATTEMPTS;
        
        const interval = setInterval(async () => {
            attempts++;
            
            try {
                const response = await fetchWithAuth(`${CONFIG.API_BASE}/status/${processId}`);
                if (!response) return;
                
                const data = await response.json();
                
                // Atualiza progresso
                Loading.update(data.progress || 0, data.status === 'processing' ? 'Processando dados...' : 'Finalizando...');
                
                if (data.status === 'completed') {
                    clearInterval(interval);
                    
                    // 🔥 Notifica sucesso
                    Notify.success(`✅ Análise concluída: ${filename}`);
                    Loading.update(100, '✅ Análise concluída!');
                    
                    // 🔥 Dispara evento para o dashboard
                    window.dispatchEvent(new CustomEvent('analysis:success', {
                        detail: {
                            processId,
                            filename,
                            result: data
                        }
                    }));
                    
                    // Adiciona à lista de análises
                    const analysisData = {
                        processId,
                        filename,
                        status: 'completed',
                        result: data
                    };
                    
                    State.activeAnalyses.push(analysisData);
                    
                    // Renderiza na UI
                    renderAnalysisCard(analysisData);
                    
                    // Gera PDF automático
                    setTimeout(() => generatePDF(processId, data), 1500);
                    
                    // Esconde loading
                    setTimeout(Loading.hide, 800);
                    
                    // Atualiza histórico
                    loadHistory();
                    
                } else if (data.status === 'error') {
                    clearInterval(interval);
                    Notify.error(`❌ Erro na análise: ${filename}`);
                    Loading.hide();
                }
                
                if (attempts >= maxAttempts) {
                    clearInterval(interval);
                    Notify.warning(`⏳ Análise ${filename} está demorando mais que o esperado.`);
                    Loading.hide();
                }
            } catch (error) {
                console.error('Polling error:', error);
                if (attempts >= maxAttempts) {
                    clearInterval(interval);
                }
            }
        }, CONFIG.POLLING_INTERVAL);
        
        State.pollingIntervals.push(interval);
    }

    // ============================================================================
    // 🔥 RENDERIZAÇÃO DE ANÁLISE (3 GRÁFICOS LADO A LADO)
    // ============================================================================
    
    function renderAnalysisCard(analysis) {
        const container = DOM.get('#activeAnalysesContainer');
        if (!container) return;
        
        const data = analysis.result;
        const stats = data.stats || {};
        const predictions = data.predictions_summary || {};
        
        const totalRegistros = stats.rows || predictions.total || 0;
        const scoreMedio = predictions.mean || 0.65;
        const altoRisco = predictions.high_risk_percentage || 0;
        const baixoRisco = predictions.low_risk_percentage || 0;
        const medioRisco = 100 - altoRisco - baixoRisco;
        
        const growth = detectGrowthType(scoreMedio);
        const crescimento = Math.round(scoreMedio * 50);
        const economia = Math.round(5000 * scoreMedio);
        const retencao = Math.round(60 + scoreMedio * 30);
        
        const cardId = `analysis-card-${analysis.processId}`;
        
        const cardHTML = `
            <div class="analysis-card mb-4" id="${cardId}" data-process-id="${analysis.processId}">
                <div class="card border-0 shadow-lg rounded-4 overflow-hidden" style="background: rgba(255,255,255,0.06); backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.1);">
                    
                    <!-- HEADER -->
                    <div class="card-header py-3 px-4" style="background: linear-gradient(135deg, rgba(102,126,234,0.2), rgba(118,75,162,0.2)); border-bottom: 1px solid rgba(255,255,255,0.05);">
                        <div class="d-flex justify-content-between align-items-center flex-wrap">
                            <div>
                                <h5 class="mb-0 fw-bold" style="color: white;">
                                    <i class="fas fa-chart-line me-2" style="color: #f5a623;"></i>
                                    Análise #${State.activeAnalyses.length}
                                    <span class="badge ms-2" style="background: ${growth.color}; color: white;">${growth.icon} ${growth.label}</span>
                                </h5>
                                <small style="color: rgba(255,255,255,0.4);">
                                    <i class="fas fa-file me-1"></i> ${analysis.filename || 'Arquivo'}
                                </small>
                            </div>
                            <div>
                                <span class="badge" style="background: rgba(255,255,255,0.08); color: rgba(255,255,255,0.6); padding: 0.3rem 0.6rem;">
                                    <i class="fas fa-database me-1"></i> ${totalRegistros.toLocaleString()}
                                </span>
                            </div>
                        </div>
                    </div>
                    
                    <!-- CORPO - 3 GRÁFICOS -->
                    <div class="card-body p-4">
                        <div class="row g-3">
                            <!-- GRÁFICO 1: CRESCIMENTO -->
                            <div class="col-lg-4">
                                <div class="p-3 rounded-4 h-100" style="background: rgba(0,0,0,0.15); border: 1px solid rgba(255,255,255,0.03);">
                                    <h6 style="color: rgba(255,255,255,0.7); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px;">
                                        <i class="fas fa-chart-line me-1" style="color: ${growth.color};"></i> Crescimento
                                    </h6>
                                    <canvas id="growthChart_${analysis.processId}" height="120"></canvas>
                                    <div class="text-center mt-2">
                                        <span class="badge" style="background: ${growth.color}; color: white; font-size: 0.65rem;">
                                            📈 ${growth.label}
                                        </span>
                                        <span class="badge ms-1" style="background: rgba(255,255,255,0.05); color: rgba(255,255,255,0.6); font-size: 0.65rem;">
                                            +${crescimento}%
                                        </span>
                                    </div>
                                </div>
                            </div>
                            
                            <!-- GRÁFICO 2: RISCO -->
                            <div class="col-lg-4">
                                <div class="p-3 rounded-4 h-100" style="background: rgba(0,0,0,0.15); border: 1px solid rgba(255,255,255,0.03);">
                                    <h6 style="color: rgba(255,255,255,0.7); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px;">
                                        <i class="fas fa-chart-pie me-1" style="color: #f5a623;"></i> Risco
                                    </h6>
                                    <canvas id="riskChart_${analysis.processId}" height="120"></canvas>
                                    <div class="text-center mt-2">
                                        <span class="badge" style="background: #48bb78; color: white; font-size: 0.55rem;">🟢 ${Math.round(baixoRisco)}%</span>
                                        <span class="badge ms-1" style="background: #f5a623; color: white; font-size: 0.55rem;">🟡 ${Math.round(medioRisco)}%</span>
                                        <span class="badge ms-1" style="background: #f56565; color: white; font-size: 0.55rem;">🔴 ${Math.round(altoRisco)}%</span>
                                    </div>
                                </div>
                            </div>
                            
                            <!-- GRÁFICO 3: PERFORMANCE -->
                            <div class="col-lg-4">
                                <div class="p-3 rounded-4 h-100" style="background: rgba(0,0,0,0.15); border: 1px solid rgba(255,255,255,0.03);">
                                    <h6 style="color: rgba(255,255,255,0.7); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px;">
                                        <i class="fas fa-bullseye me-1" style="color: #f5a623;"></i> Performance
                                    </h6>
                                    <div class="mt-1">
                                        <div class="d-flex justify-content-between align-items-center mb-1">
                                            <span style="color: rgba(255,255,255,0.5); font-size: 0.7rem;">📈 Crescimento</span>
                                            <span style="color: #48bb78; font-size: 0.8rem; font-weight: bold;">+${crescimento}%</span>
                                        </div>
                                        <div class="progress mb-2" style="height: 3px; background: rgba(255,255,255,0.05);">
                                            <div class="progress-bar" style="width: ${crescimento}%; background: ${growth.color};"></div>
                                        </div>
                                        <div class="d-flex justify-content-between align-items-center mb-1">
                                            <span style="color: rgba(255,255,255,0.5); font-size: 0.7rem;">💰 Economia</span>
                                            <span style="color: #f5a623; font-size: 0.8rem; font-weight: bold;">R$ ${economia}</span>
                                        </div>
                                        <div class="progress mb-2" style="height: 3px; background: rgba(255,255,255,0.05);">
                                            <div class="progress-bar" style="width: ${Math.min(100, economia/100)}%; background: #f5a623;"></div>
                                        </div>
                                        <div class="d-flex justify-content-between align-items-center mb-1">
                                            <span style="color: rgba(255,255,255,0.5); font-size: 0.7rem;">👥 Retenção</span>
                                            <span style="color: #667eea; font-size: 0.8rem; font-weight: bold;">${retencao}%</span>
                                        </div>
                                        <div class="progress" style="height: 3px; background: rgba(255,255,255,0.05);">
                                            <div class="progress-bar" style="width: ${retencao}%; background: #667eea;"></div>
                                        </div>
                                    </div>
                                    <div class="text-center mt-2">
                                        <span class="badge" style="background: rgba(255,255,255,0.05); color: rgba(255,255,255,0.5); font-size: 0.6rem;">
                                            ✅ Confiança: ${Math.round(scoreMedio * 100)}%
                                        </span>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <!-- RELATÓRIO (ABAIXO) -->
                        <div class="mt-3 p-3 rounded-4" style="background: rgba(0,0,0,0.1); border: 1px solid rgba(255,255,255,0.03);">
                            <div class="row align-items-center">
                                <div class="col-md-8">
                                    <div class="d-flex flex-wrap gap-4">
                                        <div>
                                            <small style="color: rgba(255,255,255,0.3); font-size: 0.6rem;">📊 REGISTROS</small>
                                            <div style="color: white; font-weight: bold; font-size: 0.9rem;">${totalRegistros.toLocaleString()}</div>
                                        </div>
                                        <div>
                                            <small style="color: rgba(255,255,255,0.3); font-size: 0.6rem;">💰 ECONOMIA/MÊS</small>
                                            <div style="color: #f5a623; font-weight: bold; font-size: 0.9rem;">R$ ${economia}</div>
                                        </div>
                                        <div>
                                            <small style="color: rgba(255,255,255,0.3); font-size: 0.6rem;">👥 RETENÇÃO</small>
                                            <div style="color: #667eea; font-weight: bold; font-size: 0.9rem;">${retencao}%</div>
                                        </div>
                                        <div>
                                            <small style="color: rgba(255,255,255,0.3); font-size: 0.6rem;">✅ CONFIANÇA</small>
                                            <div style="color: #48bb78; font-weight: bold; font-size: 0.9rem;">${Math.round(scoreMedio * 100)}%</div>
                                        </div>
                                    </div>
                                </div>
                                <div class="col-md-4 text-end mt-2 mt-md-0">
                                    <button class="btn btn-sm btn-pdf" onclick="window.generatePDFReport('${analysis.processId}')" style="background: rgba(220,53,69,0.15); border: 1px solid #dc3545; color: #dc3545; border-radius: 50px; padding: 0.3rem 0.8rem; font-size: 0.7rem;">
                                        <i class="fas fa-file-pdf me-1"></i> PDF
                                    </button>
                                    <button class="btn btn-sm btn-gpsa ms-1" onclick="window.showGPSAForAnalysis('${analysis.processId}')" style="background: rgba(245,166,35,0.15); border: 1px solid #f5a623; color: #f5a623; border-radius: 50px; padding: 0.3rem 0.8rem; font-size: 0.7rem;">
                                        <i class="fas fa-chart-line me-1"></i> GPSA
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // Insere o card no container
        const existingCards = container.querySelectorAll('.analysis-card');
        if (existingCards.length > 0) {
            container.insertAdjacentHTML('afterbegin', cardHTML);
        } else {
            container.innerHTML = cardHTML;
        }
        
        // Inicializa os gráficos do card
        setTimeout(() => {
            initGrowthChart(`growthChart_${analysis.processId}`, growth.type, scoreMedio);
            initRiskChart(`riskChart_${analysis.processId}`, altoRisco, medioRisco, baixoRisco);
        }, 300);
    }

    // ============================================================================
    // 🔥 INICIALIZAÇÃO DE GRÁFICOS
    // ============================================================================
    
    function initGrowthChart(canvasId, growthType, scoreMedio) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;
        
        // 🔥 Limpa instância anterior se existir
        if (State.chartInstances.trend) {
            try { State.chartInstances.trend.destroy(); } catch(e) {}
            State.chartInstances.trend = null;
        }
        
        const ctx = canvas.getContext('2d');
        const meses = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
        const baseValue = 20;
        const maxGrowth = Math.round(scoreMedio * 50);
        const dados = [];
        
        for (let i = 0; i < 12; i++) {
            let t = i / 11;
            let valor;
            switch(growthType) {
                case 'exponential':
                    valor = baseValue + (maxGrowth) * (Math.pow(2, t) - 1);
                    break;
                case 'quadratic':
                    valor = baseValue + (maxGrowth) * Math.pow(t, 1.5);
                    break;
                case 'linear':
                    valor = baseValue + (maxGrowth) * t;
                    break;
                default:
                    valor = baseValue + (maxGrowth) * Math.log(1 + t * 2) / Math.log(3);
            }
            dados.push(Math.min(100, Math.round(valor)));
        }
        
        State.chartInstances.trend = new Chart(ctx, {
            type: 'line',
            data: {
                labels: meses,
                datasets: [{
                    label: 'Crescimento',
                    data: dados,
                    borderColor: '#f5a623',
                    backgroundColor: 'rgba(245, 166, 35, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.3,
                    pointRadius: 2,
                    pointBackgroundColor: '#f5a623'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    y: { 
                        min: 0, 
                        max: 100, 
                        grid: { color: 'rgba(255,255,255,0.03)' },
                        ticks: { color: 'rgba(255,255,255,0.2)', font: { size: 7 } }
                    },
                    x: { 
                        grid: { display: false },
                        ticks: { color: 'rgba(255,255,255,0.2)', font: { size: 7 } }
                    }
                }
            }
        });
    }
    
    function initRiskChart(canvasId, altoRisco, medioRisco, baixoRisco) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;
        
        // 🔥 Limpa instância anterior se existir
        if (State.chartInstances.risk) {
            try { State.chartInstances.risk.destroy(); } catch(e) {}
            State.chartInstances.risk = null;
        }
        
        const ctx = canvas.getContext('2d');
        
        State.chartInstances.risk = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Baixo', 'Médio', 'Alto'],
                datasets: [{
                    data: [baixoRisco, medioRisco, altoRisco],
                    backgroundColor: ['#48bb78', '#f5a623', '#f56565'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { 
                        position: 'bottom',
                        labels: { 
                            color: 'rgba(255,255,255,0.3)',
                            font: { size: 7 },
                            boxWidth: 8,
                            padding: 3
                        }
                    }
                },
                cutout: '70%'
            }
        });
    }

    // ============================================================================
    // 🔥 DETECTAR TIPO DE CRESCIMENTO
    // ============================================================================
    
    function detectGrowthType(scoreMedio) {
        if (scoreMedio > 0.85) {
            return { type: 'exponential', icon: '🚀', label: 'Acelerado', desc: 'Crescimento rápido! Continue assim!', color: '#48bb78' };
        } else if (scoreMedio > 0.7) {
            return { type: 'quadratic', icon: '📈', label: 'Forte', desc: 'Tendência de aceleração!', color: '#f5a623' };
        } else if (scoreMedio > 0.55) {
            return { type: 'linear', icon: '➡️', label: 'Constante', desc: 'Crescimento estável e previsível.', color: '#667eea' };
        } else {
            return { type: 'logarithmic', icon: '🔄', label: 'Desacelerando', desc: 'Hora de inovar e reverter!', color: '#f56565' };
        }
    }

    // ============================================================================
    // 🔥 FUNÇÕES DE CRÉDITOS
    // ============================================================================
    
    async function loadUserCredits() {
        try {
            if (window.App && typeof window.App.getCreditsBalance === 'function') {
                State.credits = window.App.getCreditsBalance() || 0;
                State.isPremium = window.App.isPremium() || false;
                State.isAdmin = window.App.state?.isAdmin || false;
                updateCreditsDisplay();
                return;
            }
            
            const token = localStorage.getItem('access_token');
            if (!token) return;
            
            const response = await fetch(`${CONFIG.API_BASE}/auth/me`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            
            if (response.ok) {
                const data = await response.json();
                State.credits = data.credits || 0;
                State.isPremium = data.is_premium || false;
                State.isAdmin = data.is_admin || false;
                updateCreditsDisplay();
            }
        } catch (e) {
            console.warn('Erro ao carregar créditos:', e);
        }
    }
    
    async function checkCreditsBeforeUpload(filesCount = 1) {
        if (State.isAdmin) return true;
        
        if (State.credits < filesCount) {
            Notify.warning(`❌ Você precisa de ${filesCount} crédito(s). Você tem apenas ${State.credits || 0}.`);
            showCreditsModal();
            return false;
        }
        return true;
    }
    
    function showCreditsModal() {
        const modal = document.getElementById('creditsModal');
        if (modal) {
            const bsModal = bootstrap.Modal.getInstance(modal) || new bootstrap.Modal(modal);
            bsModal.show();
        }
    }

    // ============================================================================
    // 🔥 GERENCIAMENTO DE PDF (COM ANTI-CONCORRÊNCIA)
    // ============================================================================
    
    let pdfGenerationLock = false;
    
    async function generatePDF(processId, analysisResult) {
        console.log(`📄 [PDF] Gerando relatório para ${processId}...`);
        Notify.info('📄 Gerando relatório PDF automático...');
        
        // 🔥 Dispara evento de PDF gerado
        window.dispatchEvent(new CustomEvent('pdf:generated', {
            detail: {
                processId,
                analysisResult
            }
        }));
    }
    
    window.generatePDFReport = async function(processId) {
        // 🔥 ANTI-CONCORRÊNCIA: Lock para evitar múltiplos cliques
        if (pdfGenerationLock) {
            Notify.warning('⏳ Aguarde, o PDF já está sendo gerado...');
            return;
        }
        
        const analysis = State.activeAnalyses.find(a => a.processId === processId);
        if (!analysis || !analysis.result) {
            Notify.warning('Aguardando conclusão da análise...');
            return;
        }
        
        pdfGenerationLock = true;
        
        // Feedback visual no botão
        const buttons = document.querySelectorAll(`[onclick*="generatePDFReport('${processId}')"]`);
        const originalTexts = [];
        
        buttons.forEach(btn => {
            originalTexts.push(btn.innerHTML);
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Gerando...';
            btn.style.opacity = '0.7';
        });
        
        try {
            await generatePDF(processId, analysis.result);
            Notify.success('✅ PDF gerado com sucesso!');
        } catch (error) {
            console.error('Erro ao gerar PDF:', error);
            Notify.error('❌ Erro ao gerar PDF');
        } finally {
            // Restaura botões
            buttons.forEach((btn, index) => {
                btn.disabled = false;
                btn.innerHTML = originalTexts[index] || '<i class="fas fa-file-pdf me-1"></i> PDF';
                btn.style.opacity = '1';
            });
            pdfGenerationLock = false;
        }
    };

    // ============================================================================
    // 🔥 LOAD HISTORY
    // ============================================================================
    
    async function loadHistory() {
        try {
            const response = await fetchWithAuth(`${CONFIG.API_BASE}/analyses/history`);
            if (response && response.ok) {
                const data = await response.json();
                updateHistoryUI(data.analyses || data);
            }
        } catch (error) {
            console.error('Erro ao carregar histórico:', error);
        }
    }
    
    function updateHistoryUI(analyses) {
        const container = DOM.get('#recentAnalyses');
        if (!container) return;
        
        if (!analyses || analyses.length === 0) {
            container.innerHTML = `
                <div class="text-center py-3" style="color: rgba(255,255,255,0.3);">
                    <i class="fas fa-history fa-2x mb-2"></i>
                    <p class="small">Nenhuma análise realizada</p>
                </div>
            `;
            return;
        }
        
        const html = analyses.slice(0, 10).map(a => {
            const date = new Date(a.created_at);
            return `
                <div class="timeline-item">
                    <div class="timeline-marker ${a.status === 'completed' ? 'bg-success' : ''}"></div>
                    <div class="timeline-content">
                        <strong>${escapeHtml(a.filename || 'Análise')}</strong>
                        <br><small style="color: rgba(255,255,255,0.3);">${date.toLocaleDateString('pt-BR')} ${date.toLocaleTimeString('pt-BR')}</small>
                        <br><span class="badge ${a.status === 'completed' ? 'bg-success' : 'bg-secondary'}" style="font-size: 0.55rem;">${a.status === 'completed' ? '✅ Concluído' : a.status}</span>
                        ${a.pow_verified ? `<span class="badge bg-info ms-1" style="font-size: 0.5rem;">🔒 PoW</span>` : ''}
                    </div>
                </div>
            `;
        }).join('');
        
        container.innerHTML = html;
    }

    // ============================================================================
    // 🔥 DRAG & DROP (COM POLLING DE PoW)
    // ============================================================================
    
    function setupDragAndDrop() {
        const dropZone = DOM.get('#dropArea');
        if (!dropZone) return;
        
        // Prepara PoW durante drag
        dropZone.addEventListener('dragenter', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover-active');
            
            // 🔥 Prepara PoW durante o drag
            if (window.App && typeof window.App.preparePowForUpload === 'function') {
                window.App.preparePowForUpload().catch(err => {
                    console.warn('Erro ao preparar PoW:', err);
                });
            }
        });
        
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover-active');
        });
        
        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('dragover-active');
        });
        
        dropZone.addEventListener('drop', async (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover-active');
            
            // Verifica PoW
            if (window.App && typeof window.App.isPowAvailable === 'function') {
                const available = window.App.isPowAvailable();
                if (!available) {
                    Notify.info('Preparando proteção anti-bot...');
                    if (typeof window.App.preparePowForUpload === 'function') {
                        await window.App.preparePowForUpload();
                    }
                }
            }
            
            const files = Array.from(e.dataTransfer.files);
            await processUpload(files);
        });
        
        // Click para abrir seletor
        dropZone.addEventListener('click', () => {
            if (window.App && typeof window.App.preparePowForUpload === 'function') {
                window.App.preparePowForUpload();
            }
            const fileInput = DOM.get('#fileInput');
            if (fileInput) fileInput.click();
        });
    }

    // ============================================================================
    // 🔥 SHOW GPSA (EXPOSTO GLOBALMENTE)
    // ============================================================================
    
    window.showGPSAForAnalysis = function(processId) {
        const analysis = State.activeAnalyses.find(a => a.processId === processId);
        if (!analysis || !analysis.result) {
            Notify.warning('Aguardando conclusão da análise...');
            return;
        }
        
        let gpsaModal = document.getElementById('gpsaModal');
        if (!gpsaModal) {
            gpsaModal = document.createElement('div');
            gpsaModal.id = 'gpsaModal';
            gpsaModal.className = 'modal fade modal-lg';
            gpsaModal.setAttribute('tabindex', '-1');
            gpsaModal.innerHTML = `
                <div class="modal-dialog modal-dialog-centered modal-xl">
                    <div class="modal-content" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border: 1px solid rgba(255,255,255,0.1);">
                        <div class="modal-header border-0" style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                            <h5 class="modal-title" style="color: white;">
                                <i class="fas fa-chart-line me-2" style="color: #f5a623;"></i>
                                GPSA - Impacto no Negócio
                            </h5>
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body" id="gpsaModalBody">
                            <div class="text-center py-5">
                                <div class="spinner-border text-warning" role="status" style="color: #f5a623;">
                                    <span class="visually-hidden">Carregando...</span>
                                </div>
                                <p class="mt-3" style="color: rgba(255,255,255,0.5);">Carregando análise...</p>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            document.body.appendChild(gpsaModal);
        }
        
        gpsaVisualizer.showDashboard('gpsaModalBody', analysis.result);
        const modal = new bootstrap.Modal(gpsaModal);
        modal.show();
    };
    
    window.closeGPSA = function() {
        const modal = document.getElementById('gpsaModal');
        if (modal) {
            const bsModal = bootstrap.Modal.getInstance(modal);
            if (bsModal) bsModal.hide();
        }
        gpsaVisualizer.hide();
    };

    // ============================================================================
    // 🔥 ESCUTA DE EVENTOS (CICLO DE VIDA)
    // ============================================================================
    
    // 🔥 1. GATILHO PRINCIPAL: 'app:ready'
    window.addEventListener('app:ready', function(event) {
        console.log('🚀 [Dashboard] Sessão validada! Ativando esteira analítica...');
        
        const detail = event.detail || {};
        State.currentUser = detail.user || null;
        State.isAdmin = detail.isAdmin || false;
        State.isPremium = detail.isPremium || false;
        State.credits = detail.credits || 0;
        
        // Atualiza UI
        updateCreditsDisplay();
        
        // Configura Drag & Drop
        setupDragAndDrop();
        
        // Configura form de upload
        const uploadForm = DOM.get('#uploadForm');
        if (uploadForm) {
            uploadForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const fileInput = DOM.get('#fileInput');
                if (fileInput && fileInput.files.length > 0) {
                    await processUpload(Array.from(fileInput.files));
                } else {
                    Notify.warning('Selecione pelo menos um arquivo');
                }
            });
        }
        
        // Configura file input
        const fileInput = DOM.get('#fileInput');
        if (fileInput) {
            fileInput.setAttribute('multiple', 'multiple');
            fileInput.addEventListener('change', (e) => {
                if (e.target.files && e.target.files.length > 0) {
                    showFilePreview(Array.from(e.target.files));
                }
            });
        }
        
        // Carrega dados iniciais
        loadUserCredits();
        loadHistory();
        
        State._initialized = true;
        console.log('✅ [Dashboard] Inicializado com sucesso!');
    });
    
    // 🔥 2. ESCUTA DE EMERGÊNCIA: 'auth:unauthorized'
    window.addEventListener('auth:unauthorized', function() {
        console.log('🧹 [Dashboard] Limpando recursos em desautenticação...');
        
        // Limpa gráficos
        Object.keys(State.chartInstances).forEach(key => {
            if (State.chartInstances[key]) {
                try { State.chartInstances[key].destroy(); } catch(e) {}
                State.chartInstances[key] = null;
            }
        });
        
        // Limpa polling intervals
        State.pollingIntervals.forEach(clearInterval);
        State.pollingIntervals = [];
        
        // Limpa estado
        State.activeAnalyses = [];
        State._initialized = false;
        
        // Limpa cache DOM
        DOM.clearCache();
        
        Notify.info('Sessão expirada. Faça login novamente.', 3000);
    });
    
    // 🔥 3. ESCUTA DE SUCESSO: 'analysis:success'
    window.addEventListener('analysis:success', function(event) {
        console.log('✅ [Dashboard] Análise concluída:', event.detail);
        
        const detail = event.detail || {};
        const analysisData = {
            processId: detail.processId,
            filename: detail.filename,
            status: 'completed',
            result: detail.result
        };
        
        // Adiciona se não existir
        if (!State.activeAnalyses.find(a => a.processId === detail.processId)) {
            State.activeAnalyses.push(analysisData);
        }
        
        // Atualiza UI
        renderAnalysisCard(analysisData);
        loadHistory();
        
        // Atualiza créditos
        if (detail.result?.user_credits !== undefined) {
            State.credits = detail.result.user_credits;
            updateCreditsDisplay();
        }
    });
    
    // 🔥 4. ESCUTA DE CRÉDITOS: 'credits:updated'
    window.addEventListener('credits:updated', function(event) {
        if (event.detail) {
            State.credits = event.detail.credits || 0;
            State.isPremium = event.detail.isPremium || false;
            updateCreditsDisplay();
        }
    });

    // ============================================================================
    // 🔥 FUNÇÕES AUXILIARES DE UI
    // ============================================================================
    
    function showFilePreview(files) {
        const container = DOM.get('#filePreviewContainer');
        if (!container) return;
        
        let html = `
            <div class="p-3 rounded-3" style="background: rgba(0,0,0,0.15);">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <strong style="color: white; font-size: 0.9rem;"><i class="fas fa-files me-2"></i>${files.length} arquivo(s):</strong>
                    <button type="button" class="btn btn-sm btn-clear-files" style="background: rgba(220,53,69,0.2); border: none; color: #dc3545; border-radius: 50px; padding: 0.2rem 0.6rem; font-size: 0.7rem;">
                        <i class="fas fa-times me-1"></i> Limpar
                    </button>
                </div>
                <div style="max-height: 150px; overflow-y: auto;">
        `;
        
        for (const file of files) {
            const fileSizeKB = (file.size / 1024).toFixed(1);
            html += `
                <div class="d-flex justify-content-between align-items-center py-1 px-2" style="border-bottom: 1px solid rgba(255,255,255,0.03);">
                    <span style="color: rgba(255,255,255,0.8); font-size: 0.8rem;">
                        <i class="fas fa-file-excel text-success me-2"></i> ${escapeHtml(file.name)}
                    </span>
                    <span class="badge" style="background: rgba(255,255,255,0.05); color: rgba(255,255,255,0.4); font-size: 0.6rem;">${fileSizeKB}KB</span>
                </div>
            `;
        }
        
        html += `</div></div>`;
        container.innerHTML = html;
        
        const clearBtn = container.querySelector('.btn-clear-files');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                const fileInput = DOM.get('#fileInput');
                if (fileInput) fileInput.value = '';
                container.innerHTML = '';
            });
        }
    }
    
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ============================================================================
    // 🔥 INJEÇÃO DE ESTILOS ADICIONAIS
    // ============================================================================
    
    (function injectStyles() {
        if (document.getElementById('dashboardV55Styles')) return;
        
        const style = document.createElement('style');
        style.id = 'dashboardV55Styles';
        style.textContent = `
            .analysis-card {
                animation: fadeInUp 0.6s ease-out;
            }
            
            @keyframes fadeInUp {
                from { opacity: 0; transform: translateY(30px); }
                to { opacity: 1; transform: translateY(0); }
            }
            
            .gpsa-dashboard {
                animation: fadeIn 0.5s ease-out;
            }
            
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            
            .impact-card {
                transition: all 0.3s ease;
            }
            
            .impact-card:hover {
                transform: translateY(-3px);
                background: rgba(0,0,0,0.3) !important;
            }
            
            .btn-pdf:hover {
                background: #dc3545 !important;
                color: white !important;
                transform: translateY(-2px);
            }
            
            .btn-gpsa:hover {
                background: #f5a623 !important;
                color: white !important;
                transform: translateY(-2px);
            }
            
            .progress {
                border-radius: 10px;
                overflow: hidden;
            }
            
            .progress-bar {
                transition: width 1s ease-out;
            }
            
            .modal-content {
                border-radius: 20px;
            }
            
            .gpsa-score-ring {
                transition: stroke-dashoffset 2.5s ease-out;
            }
            
            .dragover-active {
                border-color: #48bb78 !important;
                background: rgba(72, 187, 120, 0.15) !important;
                transform: scale(1.02);
            }
            
            .custom-notification {
                box-shadow: 0 4px 20px rgba(0,0,0,0.15);
            }
            
            @keyframes slideInRight {
                from { opacity: 0; transform: translateX(30px); }
                to { opacity: 1; transform: translateX(0); }
            }
        `;
        document.head.appendChild(style);
    })();

    console.log('📦 [Dashboard] Módulo V5.5 carregado e aguardando eventos.');

})();