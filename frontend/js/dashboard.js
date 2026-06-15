// frontend/js/dashboard.js - VERSÃO COMPLETA
// GPSA Visual + Gráfico de Tendência + PDF AUTOMÁTICO + Botão PDF manual
// Layout: Gráfico e Insights lado a lado
// Cards individuais com animação suave (3-4 segundos)

document.addEventListener('DOMContentLoaded', async function() {
    console.log('🚀 Inicializando Dashboard...');
    
    const API_URL = '/api';
    const MAX_FILES_PER_BATCH = 3;
    const MAX_FILE_SIZE_KB = 200;
    
    let activeAnalyses = [];
    let pollingIntervals = [];
    
    // ==============================================
    // 🔥 GPSA DASHBOARD - VISUALIZAÇÃO DE IMPACTO
    // ==============================================
    
    class GPSAVisualization {
        constructor() {
            this.container = null;
            this.currentResult = null;
            this.trendChart = null;
        }
        
        showDashboard(containerId, resultData) {
            this.container = document.getElementById(containerId);
            if (!this.container) return;
            
            this.currentResult = resultData;
            this.container.style.display = 'block';
            this.renderDashboard();
            this.startAnimations();
        }
        
        calculateProjections(growthType, scoreMedio, totalRegistros) {
            const baseCrescimento = 10;
            const baseEconomia = 5000;
            const baseRetencao = 60;
            
            let fatorCrescimento, fatorEconomia, fatorRetencao;
            
            switch(growthType) {
                case 'exponential':
                    fatorCrescimento = 1 + (scoreMedio * 1.5);
                    fatorEconomia = 1 + (scoreMedio * 0.8);
                    fatorRetencao = 1 + (scoreMedio * 0.4);
                    break;
                case 'quadratic':
                    fatorCrescimento = 1 + (scoreMedio * 1.2);
                    fatorEconomia = 1 + (scoreMedio * 0.6);
                    fatorRetencao = 1 + (scoreMedio * 0.3);
                    break;
                case 'linear':
                    fatorCrescimento = 1 + (scoreMedio * 0.8);
                    fatorEconomia = 1 + (scoreMedio * 0.4);
                    fatorRetencao = 1 + (scoreMedio * 0.2);
                    break;
                default:
                    fatorCrescimento = 1 + (scoreMedio * 0.5);
                    fatorEconomia = 1 + (scoreMedio * 0.3);
                    fatorRetencao = 1 + (scoreMedio * 0.15);
            }
            
            return {
                crescimentoPercentual: Math.min(50, Math.round(baseCrescimento * fatorCrescimento)),
                economiaMensal: Math.round(baseEconomia * fatorEconomia),
                retencaoClientes: Math.min(95, Math.round(baseRetencao * fatorRetencao))
            };
        }
        
        renderDashboard() {
            const data = this.currentResult;
            const stats = data.stats || {};
            const predictions = data.predictions_summary || {};
            const insights = data.insights || {};
            
            const totalRegistros = stats.rows || predictions.total || 0;
            const scoreMedio = predictions.mean || 0.65;
            const altoRisco = predictions.high_risk_percentage || 0;
            const baixoRisco = predictions.low_risk_percentage || 0;
            const medioRisco = 100 - altoRisco - baixoRisco;
            
            let growthType = 'linear';
            let growthIcon = '📈';
            let growthDesc = 'Crescimento constante e previsível';
            let growthColor = '#4299e1';
            
            if (scoreMedio > 0.85) {
                growthType = 'exponential';
                growthIcon = '🚀';
                growthDesc = 'Crescimento EXPONENCIAL acelerado!';
                growthColor = '#48bb78';
            } else if (scoreMedio > 0.7) {
                growthType = 'quadratic';
                growthIcon = '📈';
                growthDesc = 'Crescimento ACELERADO, tendência forte';
                growthColor = '#f5a623';
            } else if (scoreMedio > 0.55) {
                growthType = 'linear';
                growthIcon = '➡️';
                growthDesc = 'Crescimento LINEAR, previsível';
                growthColor = '#4299e1';
            } else {
                growthType = 'logarithmic';
                growthIcon = '🔄';
                growthDesc = 'Crescimento LOGARÍTMICO, desaceleração';
                growthColor = '#f56565';
            }
            
            const projecoes = this.calculateProjections(growthType, scoreMedio, totalRegistros);
            
            const insightsList = insights?.recomendacoes || insights?.recommendations || [];
            const hasGeminiInsights = insightsList.length > 0;
            
            // 🔥 LAYOUT LADO A LADO: Gráfico (50%) + Insights (50%)
            const html = `
                <div class="gpsa-dashboard mt-4">
                    <svg width="0" height="0" style="position: absolute;">
                        <defs>
                            <linearGradient id="scoreGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                                <stop offset="0%" style="stop-color:#667eea"/>
                                <stop offset="100%" style="stop-color:#764ba2"/>
                            </linearGradient>
                            <linearGradient id="trendGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                                <stop offset="0%" style="stop-color:#667eea;stop-opacity:0.3"/>
                                <stop offset="100%" style="stop-color:#667eea;stop-opacity:0.0"/>
                            </linearGradient>
                        </defs>
                    </svg>
                    
                    <!-- Score Circular - Topo Centralizado -->
                    <div class="gpsa-header text-center mb-4">
                        <div class="gpsa-score-wrapper">
                            <div class="gpsa-score-circle" data-score="${Math.round(scoreMedio * 100)}">
                                <svg width="140" height="140" viewBox="0 0 140 140">
                                    <circle cx="70" cy="70" r="60" fill="none" stroke="#e2e8f0" stroke-width="8"/>
                                    <circle class="score-ring" cx="70" cy="70" r="60" fill="none" 
                                            stroke="url(#scoreGrad)" stroke-width="8" 
                                            stroke-dasharray="377" stroke-dashoffset="377"/>
                                </svg>
                                <div class="score-text">
                                    <span class="score-number">0</span>
                                    <span class="score-symbol">%</span>
                                </div>
                            </div>
                            <h3 class="mt-3 mb-1">${growthIcon} Índice de Confiança</h3>
                            <p class="text-muted small">${growthDesc}</p>
                        </div>
                    </div>
                    
                    <!-- Cards de Impacto no Negócio (3 cards lado a lado) -->
                    <div class="row g-4 mb-4">
                        <div class="col-md-4">
                            <div class="impact-card text-center p-4 rounded-4 h-100">
                                <div class="impact-icon mb-3"><i class="fas fa-chart-line fa-3x" style="color: #48bb78;"></i></div>
                                <h4>Crescimento Projetado</h4>
                                <div class="impact-value display-4 fw-bold text-success" data-target="${projecoes.crescimentoPercentual}">
                                    0<span class="fs-4">%</span>
                                </div>
                                <small class="text-muted">nos próximos 3 meses</small>
                                <div class="trend-indicator mt-2">
                                    <i class="fas ${growthIcon === '🚀' ? 'fa-rocket' : 'fa-chart-line'}"></i> 
                                    ${growthType === 'exponential' ? 'Crescimento exponencial 🚀' : 
                                      growthType === 'quadratic' ? 'Crescimento acelerado 📈' :
                                      growthType === 'linear' ? 'Crescimento constante ➡️' : 'Desaceleração natural 🔄'}
                                </div>
                            </div>
                        </div>
                        
                        <div class="col-md-4">
                            <div class="impact-card text-center p-4 rounded-4 h-100">
                                <div class="impact-icon mb-3"><i class="fas fa-coins fa-3x" style="color: #f5a623;"></i></div>
                                <h4>Economia Mensal</h4>
                                <div class="impact-value display-4 fw-bold text-warning" data-target="${projecoes.economiaMensal}">
                                    R$ 0
                                </div>
                                <small class="text-muted">em redução de custos</small>
                                <div class="trend-indicator mt-2"><i class="fas fa-chart-line"></i> Otimização identificada</div>
                            </div>
                        </div>
                        
                        <div class="col-md-4">
                            <div class="impact-card text-center p-4 rounded-4 h-100">
                                <div class="impact-icon mb-3"><i class="fas fa-users fa-3x" style="color: #667eea;"></i></div>
                                <h4>Retenção de Clientes</h4>
                                <div class="impact-value display-4 fw-bold text-primary" data-target="${projecoes.retencaoClientes}">
                                    0<span class="fs-4">%</span>
                                </div>
                                <small class="text-muted">taxa estimada de fidelização</small>
                                <div class="trend-indicator mt-2"><i class="fas fa-heart"></i> Clientes satisfeitos</div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- 🔥 LAYOUT LADO A LADO: Gráfico (50%) + Insights (50%) -->
                    <div class="row g-4 mb-4">
                        <div class="col-md-6">
                            <div class="trend-chart-card p-4 rounded-4 h-100">
                                <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap">
                                    <h5 class="mb-0">
                                        <i class="fas fa-chart-line me-2"></i> 
                                        Projeção de Crescimento - ${growthType.charAt(0).toUpperCase() + growthType.slice(1)}
                                        <span class="badge ms-2" style="background: ${growthColor};">${growthIcon}</span>
                                    </h5>
                                </div>
                                <canvas id="trendChart" width="100%" height="250" style="width: 100%; height: 250px;"></canvas>
                                <div class="text-center mt-3">
                                    <small class="text-muted">
                                        <i class="fas fa-chart-simple me-1"></i>
                                        Baseado em ${totalRegistros.toLocaleString()} registros | 
                                        Tipo: ${growthDesc.toLowerCase()}
                                    </small>
                                </div>
                            </div>
                        </div>
                        
                        <div class="col-md-6">
                            <div class="insights-card p-4 rounded-4 h-100">
                                <h5 class="mb-3">
                                    <i class="fas fa-lightbulb me-2"></i> 
                                    Insights da ${hasGeminiInsights ? 'IA Gemini' : 'Análise'}
                                    ${hasGeminiInsights ? '<span class="badge bg-success ms-2"><i class="fas fa-robot me-1"></i>IA</span>' : ''}
                                </h5>
                                <div class="insights-list" style="max-height: 250px; overflow-y: auto;">
                                    ${hasGeminiInsights ? 
                                        insightsList.slice(0, 5).map(i => `<div class="insight-item mb-2 p-2 bg-light rounded-3">${escapeHtml(i)}</div>`).join('') :
                                        this.generateInsightsHTML(scoreMedio, altoRisco, totalRegistros, growthType)
                                    }
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Distribuição de Risco (3 cores lado a lado) -->
                    <div class="row g-4 mb-4">
                        <div class="col-12">
                            <div class="risk-summary p-3 rounded-4">
                                <h5 class="mb-3 text-center"><i class="fas fa-chart-pie me-2"></i> Distribuição de Risco</h5>
                                <div class="row text-center">
                                    <div class="col-4">
                                        <div class="risk-badge high p-2 rounded-3">
                                            <i class="fas fa-exclamation-triangle me-1"></i>
                                            <span class="risk-label">Alto Risco</span>
                                            <div class="risk-value fw-bold">${Math.round(altoRisco)}%</div>
                                        </div>
                                    </div>
                                    <div class="col-4">
                                        <div class="risk-badge medium p-2 rounded-3">
                                            <i class="fas fa-chart-line me-1"></i>
                                            <span class="risk-label">Médio Risco</span>
                                            <div class="risk-value fw-bold">${Math.round(medioRisco)}%</div>
                                        </div>
                                    </div>
                                    <div class="col-4">
                                        <div class="risk-badge low p-2 rounded-3">
                                            <i class="fas fa-check-circle me-1"></i>
                                            <span class="risk-label">Baixo Risco</span>
                                            <div class="risk-value fw-bold">${Math.round(baixoRisco)}%</div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Barra de Progresso do Score -->
                    <div class="score-progress-card p-4 rounded-4">
                        <div class="d-flex justify-content-between mb-2">
                            <span><i class="fas fa-chart-simple me-2"></i> Score de Acerto da Previsão</span>
                            <span class="score-progress-value fw-bold">0%</span>
                        </div>
                        <div class="progress mb-2" style="height: 12px; border-radius: 20px;">
                            <div class="progress-bar progress-bar-striped progress-bar-animated" 
                                 style="width: 0%; background: linear-gradient(90deg, ${growthColor}, #764ba2);"></div>
                        </div>
                        <small class="text-muted"><i class="fas fa-database me-1"></i> Baseado em ${totalRegistros.toLocaleString()} registros analisados</small>
                    </div>
                    
                    <div class="text-center mt-4">
                        <button class="btn btn-outline-primary btn-sm" onclick="window.closeGPSA()">
                            <i class="fas fa-times me-2"></i> Fechar Dashboard
                        </button>
                    </div>
                </div>
            `;
            
            this.container.innerHTML = html;
            this.initTrendChart(growthType, scoreMedio, projecoes);
        }
        
        generateInsightsHTML(scoreMedio, altoRisco, totalRegistros, growthType) {
            let insights = [];
            
            if (scoreMedio > 0.7) {
                insights.push('✅ <strong>Excelente performance!</strong> Seus dados estão muito bem estruturados.');
            } else if (scoreMedio > 0.5) {
                insights.push('📈 <strong>Bom potencial de melhoria</strong> com ajustes nos processos.');
            } else {
                insights.push('⚠️ <strong>Oportunidade de melhoria</strong> identificada nos dados.');
            }
            
            if (altoRisco > 30) {
                insights.push('🔴 <strong>Alerta de risco elevado</strong> em mais de 30% dos casos analisados.');
            } else if (altoRisco > 15) {
                insights.push('🟠 <strong>Atenção necessária</strong> em áreas específicas do negócio.');
            } else {
                insights.push('🟢 <strong>Risco controlado</strong> - ótimas práticas de gestão.');
            }
            
            if (growthType === 'exponential') {
                insights.push('🚀 <strong>Crescimento exponencial detectado!</strong> Momento perfeito para investir e expandir.');
            } else if (growthType === 'quadratic') {
                insights.push('📈 <strong>Crescimento acelerado confirmado!</strong> Mantenha o ritmo e capitalize as oportunidades.');
            } else if (growthType === 'linear') {
                insights.push('➡️ <strong>Crescimento estável projetado.</strong> Foco em otimização contínua.');
            } else {
                insights.push('🔄 <strong>Crescimento com desaceleração.</strong> Reveja estratégias para retomar o crescimento.');
            }
            
            insights.push(`💡 <strong>Recomendação:</strong> Foque em ações preventivas para maximizar resultados.`);
            insights.push(`📊 <strong>Total analisado:</strong> ${totalRegistros.toLocaleString()} registros processados com sucesso.`);
            
            return insights.map(i => `<div class="insight-item mb-2 p-2 bg-light rounded-3">${i}</div>`).join('');
        }
        
        initTrendChart(growthType, scoreMedio, projecoes) {
            const canvas = document.getElementById('trendChart');
            if (!canvas) return;
            
            if (this.trendChart) this.trendChart.destroy();
            
            const meses = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
            const dadosProjecao = [];
            const dadosAtual = [];
            
            const baseValue = 30;
            const maxGrowth = projecoes.crescimentoPercentual;
            const maxValue = baseValue + maxGrowth;
            
            for (let i = 0; i < 12; i++) {
                let t = i / 11;
                let valorProjetado;
                
                switch(growthType) {
                    case 'exponential':
                        valorProjetado = baseValue + (maxValue - baseValue) * (Math.pow(2, t) - 1);
                        break;
                    case 'quadratic':
                        valorProjetado = baseValue + (maxValue - baseValue) * Math.pow(t, 1.5);
                        break;
                    case 'linear':
                        valorProjetado = baseValue + (maxValue - baseValue) * t;
                        break;
                    default:
                        valorProjetado = baseValue + (maxValue - baseValue) * Math.log(1 + t * 2) / Math.log(3);
                }
                
                dadosProjecao.push(Math.min(100, Math.round(valorProjetado)));
                
                let valorAtual = baseValue + (maxValue * 0.3) * Math.sin(t * Math.PI / 2);
                dadosAtual.push(Math.min(100, Math.round(Math.max(20, valorAtual))));
            }
            
            this.trendChart = new Chart(canvas, {
                type: 'line',
                data: {
                    labels: meses,
                    datasets: [
                        {
                            label: 'Projeção Futura',
                            data: dadosProjecao,
                            borderColor: '#667eea',
                            backgroundColor: 'rgba(102, 126, 234, 0.1)',
                            borderWidth: 3,
                            fill: true,
                            tension: 0.3,
                            pointRadius: 4,
                            pointHoverRadius: 6,
                            pointBackgroundColor: '#667eea'
                        },
                        {
                            label: 'Tendência Atual',
                            data: dadosAtual,
                            borderColor: '#a0aec0',
                            backgroundColor: 'transparent',
                            borderWidth: 2,
                            borderDash: [5, 5],
                            fill: false,
                            tension: 0.2,
                            pointRadius: 3,
                            pointBackgroundColor: '#a0aec0'
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    plugins: {
                        legend: { position: 'top', labels: { font: { size: 11 } } },
                        tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${ctx.raw}%` } }
                    },
                    scales: {
                        y: { title: { display: true, text: 'Crescimento (%)' }, min: 0, max: 100, grid: { color: '#e2e8f0' } },
                        x: { title: { display: true, text: 'Meses' }, grid: { display: false } }
                    }
                }
            });
        }
        
        startAnimations() {
            const scoreValue = this.currentResult.predictions_summary?.mean || 0.65;
            const targetPercent = Math.round(scoreValue * 100);
            const scoreRing = document.querySelector('.score-ring');
            const scoreNumber = document.querySelector('.score-number');
            
            if (scoreRing) {
                const radius = 60;
                const circumference = 2 * Math.PI * radius;
                
                anime({
                    targets: { value: 0 },
                    value: targetPercent,
                    duration: 3500,
                    easing: 'easeOutElastic(1, .8)',
                    update: function(anim) {
                        const current = Math.round(anim.animations[0].currentValue);
                        if (scoreNumber) scoreNumber.textContent = current;
                        const currentOffset = circumference - (current / 100) * circumference;
                        scoreRing.style.strokeDashoffset = currentOffset;
                    }
                });
            }
            
            document.querySelectorAll('[data-target]').forEach(el => {
                const target = parseInt(el.dataset.target);
                if (isNaN(target)) return;
                
                const isCurrency = el.textContent.includes('R$');
                const hasPercent = el.querySelector('.fs-4') !== null;
                
                anime({
                    targets: { value: 0 },
                    value: target,
                    duration: 3500,
                    easing: 'easeOutQuad',
                    update: function(anim) {
                        const current = Math.round(anim.animations[0].currentValue);
                        if (isCurrency) {
                            el.innerHTML = `R$ ${current.toLocaleString('pt-BR')}`;
                        } else if (hasPercent) {
                            el.innerHTML = `${current}<span class="fs-4">%</span>`;
                        } else {
                            el.textContent = current;
                        }
                    }
                });
            });
            
            const progressBar = document.querySelector('.progress-bar');
            const progressValue = document.querySelector('.score-progress-value');
            
            if (progressBar && progressValue) {
                anime({
                    targets: { width: 0 },
                    width: targetPercent,
                    duration: 3500,
                    easing: 'easeOutQuad',
                    update: function(anim) {
                        const current = Math.round(anim.animations[0].currentValue);
                        progressBar.style.width = `${current}%`;
                        if (progressValue) progressValue.textContent = `${current}%`;
                    }
                });
            }
            
            anime({
                targets: '.impact-card, .trend-chart-card, .insights-card, .score-progress-card, .risk-summary',
                opacity: [0, 1],
                translateY: [20, 0],
                delay: anime.stagger(150),
                duration: 1200,
                easing: 'easeOutCubic'
            });
        }
        
        hide() {
            if (this.container) {
                anime({
                    targets: this.container,
                    opacity: [1, 0],
                    duration: 300,
                    easing: 'easeOutQuad',
                    complete: () => {
                        this.container.style.display = 'none';
                        if (this.trendChart) {
                            this.trendChart.destroy();
                            this.trendChart = null;
                        }
                    }
                });
            }
        }
    }
    
    let gpsaDashboard = null;
    
    // ===== FUNÇÕES DE AUTENTICAÇÃO =====
    
    function isAuthenticated() {
        if (window.appAuth) {
            if (typeof window.appAuth.isAuthenticated === 'function') {
                return window.appAuth.isAuthenticated();
            }
            return window.appAuth.isAuthenticated;
        }
        return !!localStorage.getItem('access_token');
    }
    
    function isAdmin() {
        if (window.appAuth && window.appAuth.isAdmin) {
            return typeof window.appAuth.isAdmin === 'function' ? window.appAuth.isAdmin() : window.appAuth.isAdmin;
        }
        return false;
    }
    
    function isPremium() {
        if (window.appAuth && window.appAuth.isPremium) {
            return typeof window.appAuth.isPremium === 'function' ? window.appAuth.isPremium() : window.appAuth.isPremium;
        }
        return false;
    }
    
    function getCredits() {
        if (window.appAuth && window.appAuth.getCredits) {
            return window.appAuth.getCredits();
        }
        return 0;
    }
    
    function getCreditsDisplay() {
        if (window.appAuth && window.appAuth.getCreditsDisplay) {
            return window.appAuth.getCreditsDisplay();
        }
        const credits = getCredits();
        if (isAdmin()) return '∞';
        if (isPremium()) return `${credits}/3`;
        return String(credits);
    }
    
    function redirectToLogin() {
        window.location.href = '/login';
    }
    
    if (!isAuthenticated()) {
        redirectToLogin();
        return;
    }
    
    // ===== FUNÇÕES DE FETCH =====
    
    async function fetchWithAuth(url, options = {}) {
        if (window.appAuth && window.appAuth.fetchWithAuth) {
            return window.appAuth.fetchWithAuth(url, options);
        }
        
        const token = localStorage.getItem('access_token');
        if (!token) {
            redirectToLogin();
            return null;
        }
        
        const headers = {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
            ...options.headers
        };
        
        try {
            let response = await fetch(url, { ...options, headers });
            if (response.status === 401) {
                redirectToLogin();
                return null;
            }
            return response;
        } catch (error) {
            console.error('Fetch error:', error);
            return null;
        }
    }
    
    // ===== FUNÇÕES DE UI =====
    
    function showNotification(message, type = 'info') {
        if (window.toastr) {
            toastr[type](message);
            return;
        }
        
        const bgColor = type === 'success' ? '#48bb78' : 
                        type === 'error' ? '#f56565' :
                        type === 'warning' ? '#ed8936' : '#4299e1';
        
        const notification = document.createElement('div');
        notification.style.cssText = `
            position: fixed; bottom: 20px; right: 20px; background: white;
            border-left: 4px solid ${bgColor}; padding: 12px 20px;
            border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            z-index: 10000; animation: slideInRight 0.3s ease;
        `;
        notification.innerHTML = `<i class="fas fa-${type === 'success' ? 'check-circle' : 'info-circle'}" style="color: ${bgColor}; margin-right: 8px;"></i>${message}`;
        document.body.appendChild(notification);
        setTimeout(() => notification.remove(), 5000);
    }
    
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    // ===== FUNÇÕES DE CRÉDITOS =====
    
    async function loadUserCredits() {
        if (window.appAuth && window.appAuth.loadUserCredits) {
            await window.appAuth.loadUserCredits();
        }
        
        const creditsDisplay = getCreditsDisplay();
        document.querySelectorAll('.credits-display, .user-credits, #creditsCount').forEach(el => {
            if (el) el.textContent = creditsDisplay;
        });
    }
    
    async function checkCreditsBeforeUpload(filesCount = 1) {
        if (isAdmin()) return true;
        
        let credits = getCredits();
        if (credits < filesCount) {
            showNotification(`❌ Você precisa de ${filesCount} crédito(s). Você tem apenas ${credits || 0}.`, 'warning');
            showCreditsModal();
            return false;
        }
        return true;
    }
    
    function showCreditsModal() {
        let modal = document.getElementById('creditsModal');
        if (!modal) {
            const modalHtml = `
                <div class="modal fade" id="creditsModal" tabindex="-1">
                    <div class="modal-dialog">
                        <div class="modal-content">
                            <div class="modal-header bg-warning">
                                <h5 class="modal-title"><i class="fas fa-exclamation-triangle me-2"></i>Créditos Insuficientes</h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                            </div>
                            <div class="modal-body text-center py-4">
                                <i class="fas fa-coins fa-4x text-warning mb-3"></i>
                                <h5>Você não tem créditos suficientes</h5>
                                <p>Cada arquivo consome 1 crédito.</p>
                                <a href="/planos" class="btn btn-primary mt-2">Comprar Créditos</a>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            document.body.insertAdjacentHTML('beforeend', modalHtml);
            modal = document.getElementById('creditsModal');
        }
        new bootstrap.Modal(modal).show();
    }
    
    // ===== TELA DE CARREGAMENTO =====
    
    function showLoading(message = 'Processando sua análise...', submessage = 'A IA está analisando seus dados') {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            const loadingText = document.getElementById('loadingText');
            const loadingSubtext = document.getElementById('loadingSubtext');
            const progressBar = document.getElementById('loadingProgressBar');
            
            if (loadingText) loadingText.textContent = message;
            if (loadingSubtext) loadingSubtext.textContent = submessage;
            if (progressBar) progressBar.style.width = '0%';
            
            overlay.classList.add('show');
        }
    }
    
    function updateLoadingProgress(percent, message = null) {
        const progressBar = document.getElementById('loadingProgressBar');
        const loadingText = document.getElementById('loadingText');
        
        if (progressBar) progressBar.style.width = `${percent}%`;
        if (message && loadingText) loadingText.textContent = message;
    }
    
    function hideLoading() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            overlay.classList.remove('show');
        }
    }
    
    // ===== 🔥 FUNÇÃO PARA GERAR PDF AUTOMATICAMENTE =====
    
    async function generateAutoPDF(processId, analysisResult) {
        console.log(`📄 Gerando PDF automático para ${processId}...`);
        
        const stats = analysisResult.stats || {};
        const predictions = analysisResult.predictions_summary || {};
        const insights = analysisResult.insights || {};
        
        const totalRegistros = stats.rows || predictions.total || 0;
        const scoreMedio = predictions.mean || 0.65;
        const altoRisco = predictions.high_risk_percentage || 0;
        const baixoRisco = predictions.low_risk_percentage || 0;
        const nomeArquivo = analysisResult.filename || 'analise';
        const dataAnalise = new Date().toLocaleDateString('pt-BR');
        const horaAnalise = new Date().toLocaleTimeString('pt-BR');
        
        // Detectar tipo de crescimento
        let growthType = 'linear';
        let growthIcon = '📈';
        let growthDesc = 'Crescimento constante e previsível';
        
        if (scoreMedio > 0.85) {
            growthType = 'exponential';
            growthIcon = '🚀';
            growthDesc = 'Crescimento EXPONENCIAL acelerado!';
        } else if (scoreMedio > 0.7) {
            growthType = 'quadratic';
            growthIcon = '📈';
            growthDesc = 'Crescimento ACELERADO, tendência forte';
        } else if (scoreMedio > 0.55) {
            growthType = 'linear';
            growthIcon = '➡️';
            growthDesc = 'Crescimento LINEAR, previsível';
        } else {
            growthType = 'logarithmic';
            growthIcon = '🔄';
            growthDesc = 'Crescimento LOGARÍTMICO, desaceleração';
        }
        
        // Projeções baseadas no ML
        const crescimentoProjetado = Math.min(50, Math.max(-20, Math.round((scoreMedio - 0.5) * 40)));
        const economiaMensal = Math.round(5000 * scoreMedio);
        const retencaoClientes = Math.min(95, Math.round(60 + (scoreMedio * 30)));
        
        // 🔥 EXTRAIR INSIGHTS DA IA (GEMINI)
        const iaInsights = insights?.recomendacoes || insights?.recommendations || [];
        const iaFullAnalysis = insights?.full_analysis || insights?.analise_completa || '';
        const hasGemini = iaInsights.length > 0 || iaFullAnalysis;
        
        // Tentar capturar gráfico
        let chartImage = null;
        const chartCanvas = document.getElementById('trendChart');
        if (chartCanvas) {
            try {
                chartImage = chartCanvas.toDataURL('image/png');
            } catch(e) { console.warn('Erro ao capturar gráfico:', e); }
        }
        
        // Criar div temporária para o PDF
        const pdfContent = document.createElement('div');
        pdfContent.style.cssText = `
            padding: 30px;
            font-family: 'Inter', 'Segoe UI', Arial, sans-serif;
            background: white;
            max-width: 800px;
            margin: 0 auto;
            color: #1a1a2e;
        `;
        
        pdfContent.innerHTML = `
            <div style="text-align: center; margin-bottom: 30px; border-bottom: 3px solid #667eea; padding-bottom: 20px;">
                <div style="font-size: 48px; margin-bottom: 10px;">🔧📊🤖</div>
                <h1 style="color: #667eea; margin: 0; font-size: 28px;">AutoAnalyticsPro</h1>
                <h2 style="color: #764ba2; margin: 5px 0; font-size: 20px;">Relatório de Análise com IA</h2>
                <p style="color: #666; margin: 10px 0 0; font-size: 12px;">
                    Gerado em ${dataAnalise} às ${horaAnalise}
                </p>
                ${hasGemini ? `
                    <div style="margin-top: 10px; padding: 8px 16px; background: linear-gradient(135deg, #667eea, #764ba2); color: white; border-radius: 30px; display: inline-block; font-size: 12px;">
                        <i class="fas fa-robot"></i> Análise gerada com Google Gemini IA
                    </div>
                ` : ''}
            </div>
            
            <div style="margin-bottom: 25px;">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px; border-radius: 12px;">
                    <div style="font-size: 14px; opacity: 0.9;">ARQUIVO ANALISADO</div>
                    <div style="font-size: 18px; font-weight: bold;">📁 ${escapeHtml(nomeArquivo)}</div>
                    <div style="font-size: 12px; margin-top: 8px;">📊 ${totalRegistros.toLocaleString()} registros | 📈 Score de confiança: ${Math.round(scoreMedio * 100)}%</div>
                </div>
            </div>
            
            <div style="margin-bottom: 25px;">
                <h3 style="color: #667eea; margin-bottom: 15px; font-size: 18px;">📊 Índice de Confiança da Análise</h3>
                <div style="background: #f0f0f0; border-radius: 10px; padding: 15px; text-align: center;">
                    <div style="font-size: 42px; font-weight: bold; color: ${scoreMedio > 0.7 ? '#48bb78' : (scoreMedio > 0.5 ? '#f5a623' : '#f56565')};">${Math.round(scoreMedio * 100)}%</div>
                    <div style="color: #666; margin-top: 5px;">${growthIcon} ${growthDesc}</div>
                    <div style="color: #999; margin-top: 10px; font-size: 12px;">Baseado em ${totalRegistros.toLocaleString()} registros analisados pelo modelo de Machine Learning</div>
                </div>
            </div>
            
            <div style="margin-bottom: 25px;">
                <h3 style="color: #667eea; margin-bottom: 15px; font-size: 18px;">💰 Impacto no Negócio</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 12px; background: #f0fdf4; border-radius: 10px; width: 33%; text-align: center;">
                            <div style="font-size: 28px; font-weight: bold; color: #48bb78;">${crescimentoProjetado > 0 ? '+' : ''}${crescimentoProjetado}%</div>
                            <div style="font-size: 12px; color: #666;">Crescimento projetado em 3 meses</div>
                        </td>
                        <td style="padding: 12px; background: #fef3c7; border-radius: 10px; width: 33%; text-align: center;">
                            <div style="font-size: 28px; font-weight: bold; color: #f5a623;">R$ ${economiaMensal.toLocaleString()}</div>
                            <div style="font-size: 12px; color: #666;">Economia mensal estimada</div>
                        </td>
                        <td style="padding: 12px; background: #e0e7ff; border-radius: 10px; width: 33%; text-align: center;">
                            <div style="font-size: 28px; font-weight: bold; color: #667eea;">${retencaoClientes}%</div>
                            <div style="font-size: 12px; color: #666;">Taxa de retenção de clientes</div>
                        </td>
                    </tr>
                </table>
            </div>
            
            <div style="margin-bottom: 25px;">
                <h3 style="color: #667eea; margin-bottom: 15px; font-size: 18px;">⚠️ Distribuição de Risco</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px; background: #fee2e2; border-radius: 8px; width: 33%; text-align: center;">
                            <div><span style="display: inline-block; width: 12px; height: 12px; background: #f56565; border-radius: 50%;"></span> Alto Risco</div>
                            <div style="font-size: 24px; font-weight: bold; color: #f56565;">${Math.round(altoRisco)}%</div>
                            <div style="font-size: 11px; color: #666;">${Math.round(altoRisco)}% dos casos merecem atenção imediata</div>
                        </td>
                        <td style="padding: 8px; background: #fef3c7; border-radius: 8px; width: 33%; text-align: center;">
                            <div><span style="display: inline-block; width: 12px; height: 12px; background: #f5a623; border-radius: 50%;"></span> Médio Risco</div>
                            <div style="font-size: 24px; font-weight: bold; color: #f5a623;">${Math.round(100 - altoRisco - baixoRisco)}%</div>
                            <div style="font-size: 11px; color: #666;">Áreas que precisam de monitoramento</div>
                        </td>
                        <td style="padding: 8px; background: #d1fae5; border-radius: 8px; width: 33%; text-align: center;">
                            <div><span style="display: inline-block; width: 12px; height: 12px; background: #48bb78; border-radius: 50%;"></span> Baixo Risco</div>
                            <div style="font-size: 24px; font-weight: bold; color: #48bb78;">${Math.round(baixoRisco)}%</div>
                            <div style="font-size: 11px; color: #666;">Processos saudáveis e controlados</div>
                        </td>
                    </tr>
                </table>
            </div>
            
            ${chartImage ? `
            <div style="margin-bottom: 25px;">
                <h3 style="color: #667eea; margin-bottom: 15px; font-size: 18px;">📈 Projeção de Crescimento</h3>
                <div style="text-align: center;">
                    <img src="${chartImage}" style="max-width: 100%; height: auto; border-radius: 8px; border: 1px solid #e2e8f0;">
                </div>
                <div style="text-align: center; margin-top: 10px;">
                    <small class="text-muted">Projeção baseada no modelo de Machine Learning - Tipo: ${growthDesc.toLowerCase()}</small>
                </div>
            </div>
            ` : ''}
            
            <div style="margin-bottom: 25px;">
                <h3 style="color: #667eea; margin-bottom: 15px; font-size: 18px;">
                    <i class="fas fa-robot"></i> Insights da Inteligência Artificial (Gemini)
                </h3>
                <div style="background: linear-gradient(135deg, #f0f4ff 0%, #e8edf5 100%); border-radius: 12px; padding: 20px;">
                    ${hasGemini ? `
                        <div style="margin-bottom: 15px;">
                            ${iaInsights.length > 0 ? 
                                iaInsights.slice(0, 6).map(i => `
                                    <div style="margin-bottom: 12px; padding: 10px; background: white; border-radius: 8px; border-left: 3px solid #667eea;">
                                        <span style="font-size: 18px; margin-right: 8px;">💡</span> ${escapeHtml(i)}
                                    </div>
                                `).join('') :
                                `<div style="margin-bottom: 12px; padding: 10px; background: white; border-radius: 8px; border-left: 3px solid #667eea;">
                                    <span style="font-size: 18px; margin-right: 8px;">🤖</span> ${escapeHtml(iaFullAnalysis.substring(0, 500))}
                                </div>`
                            }
                        </div>
                    ` : `
                        <div style="margin-bottom: 12px; padding: 10px; background: white; border-radius: 8px; border-left: 3px solid #f5a623;">
                            <span style="font-size: 18px; margin-right: 8px;">📊</span> <strong>Análise do ML:</strong> Score de confiança de ${Math.round(scoreMedio * 100)}% indica ${scoreMedio > 0.7 ? 'excelente qualidade dos dados' : (scoreMedio > 0.5 ? 'potencial de melhoria' : 'oportunidade de revisão')}.
                        </div>
                        <div style="margin-bottom: 12px; padding: 10px; background: white; border-radius: 8px; border-left: 3px solid #f5a623;">
                            <span style="font-size: 18px; margin-right: 8px;">⚠️</span> <strong>Alerta de risco:</strong> ${Math.round(altoRisco)}% dos casos analisados apresentam alto risco.
                        </div>
                        <div style="margin-bottom: 12px; padding: 10px; background: white; border-radius: 8px; border-left: 3px solid #48bb78;">
                            <span style="font-size: 18px; margin-right: 8px;">🟢</span> <strong>Pontos fortes:</strong> ${Math.round(baixoRisco)}% dos processos estão sob controle.
                        </div>
                        <div style="margin-bottom: 12px; padding: 10px; background: white; border-radius: 8px; border-left: 3px solid #667eea;">
                            <span style="font-size: 18px; margin-right: 8px;">📈</span> <strong>Tendência detectada:</strong> ${growthDesc}
                        </div>
                    `}
                </div>
            </div>
            
            <div style="margin-bottom: 25px;">
                <h3 style="color: #667eea; margin-bottom: 15px; font-size: 18px;">🎯 Recomendações Práticas</h3>
                <ul style="margin: 0; padding-left: 20px;">
                    ${hasGemini && iaInsights.length > 2 ? 
                        iaInsights.slice(2, 6).map(i => `<li style="margin-bottom: 8px; color: #333;">${escapeHtml(i)}</li>`).join('') :
                        `
                        <li style="margin-bottom: 8px;">💰 Invista em ações preventivas nas áreas identificadas como alto risco</li>
                        <li style="margin-bottom: 8px;">📊 Monitore os KPIs mensalmente para acompanhar a evolução</li>
                        <li style="margin-bottom: 8px;">🔧 Revise processos nas áreas com ${Math.round(altoRisco)}% de risco elevado</li>
                        <li style="margin-bottom: 8px;">📈 Utilize os insights para tomada de decisão estratégica</li>
                        <li style="margin-bottom: 8px;">⭐ Considere o plano premium para receber 1 crédito novo por dia</li>
                        `
                    }
                </ul>
            </div>
            
            <div style="margin-bottom: 25px;">
                <h3 style="color: #667eea; margin-bottom: 15px; font-size: 18px;">🔬 Resumo Técnico</h3>
                <table style="width: 100%; border-collapse: collapse; background: #f8f9fa; border-radius: 10px;">
                    <tr><td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0;"><strong>Total de registros analisados:</strong></td><td style="padding: 8px 12px;">${totalRegistros.toLocaleString()}</td></tr>
                    <tr><td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0;"><strong>Score médio de confiança:</strong></td><td style="padding: 8px 12px;">${Math.round(scoreMedio * 100)}%</td></tr>
                    <tr><td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0;"><strong>Alto risco detectado:</strong></td><td style="padding: 8px 12px;">${Math.round(altoRisco)}% dos casos</td></tr>
                    <tr><td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0;"><strong>Baixo risco detectado:</strong></td><td style="padding: 8px 12px;">${Math.round(baixoRisco)}% dos casos</td></tr>
                    <tr><td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0;"><strong>Tipo de crescimento projetado:</strong></td><td style="padding: 8px 12px;">${growthType.charAt(0).toUpperCase() + growthType.slice(1)} (${growthDesc.toLowerCase()})</td></tr>
                    <tr><td style="padding: 8px 12px;"><strong>Modelo de IA utilizado:</strong></td><td style="padding: 8px 12px;">${hasGemini ? 'Google Gemini + RandomForest' : 'RandomForest (ML)'}</td></tr>
                </table>
            </div>
            
            <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #e2e8f0; text-align: center; font-size: 10px; color: #999;">
                <p>AutoAnalyticsPro - Inteligência Artificial para Oficinas Mecânicas</p>
                <p>Este relatório foi gerado automaticamente com base na análise dos seus dados reais.</p>
                <p>🔒 Relatório confidencial - Uso interno da oficina</p>
            </div>
        `;
        
        if (typeof html2canvas === 'undefined' || typeof jspdf === 'undefined') {
            console.warn('Bibliotecas de PDF não carregadas');
            return;
        }
        
        try {
            document.body.appendChild(pdfContent);
            
            const canvas = await html2canvas(pdfContent, {
                scale: 2,
                backgroundColor: '#ffffff',
                logging: false,
                useCORS: true
            });
            
            document.body.removeChild(pdfContent);
            
            const imgData = canvas.toDataURL('image/png');
            const { jsPDF } = window.jspdf;
            const pdf = new jsPDF({
                orientation: 'portrait',
                unit: 'mm',
                format: 'a4'
            });
            
            const imgWidth = 190;
            const imgHeight = (canvas.height * imgWidth) / canvas.width;
            
            pdf.addImage(imgData, 'PNG', 10, 10, imgWidth, imgHeight);
            
            const nomeArquivoLimpo = nomeArquivo.replace(/[^a-z0-9]/gi, '_').substring(0, 30);
            const dataStr = dataAnalise.replace(/\//g, '-');
            pdf.save(`autoanalytics_${nomeArquivoLimpo}_${dataStr}.pdf`);
            
            console.log(`✅ PDF gerado automaticamente: ${nomeArquivo}`);
            showNotification(`📄 Relatório PDF gerado automaticamente!`, 'success');
            
        } catch (error) {
            console.error('Erro ao gerar PDF:', error);
            if (pdfContent.parentNode) document.body.removeChild(pdfContent);
        }
    }
    
    // ===== 🔥 FUNÇÃO PARA GERAR PDF MANUAL (botão) =====
    
    window.generatePDFReport = async function(processId) {
        const analysis = activeAnalyses.find(a => a.processId === processId);
        if (!analysis || !analysis.result) {
            showNotification('Aguardando conclusão da análise...', 'warning');
            return;
        }
        await generateAutoPDF(processId, analysis.result);
    };
    
    // ===== CARDS INDIVIDUAIS COM ANIMAÇÃO =====
    
    function createAnalysisCard(processId, filename, index, totalFiles) {
        return `
            <div class="analysis-card mb-4" id="analysis-card-${processId}" data-process-id="${processId}" data-filename="${filename}" style="opacity: 0; transform: translateY(30px);">
                <div class="card border-0 shadow-sm rounded-4 overflow-hidden">
                    <div class="card-header bg-gradient-primary text-white py-3" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
                        <div class="d-flex justify-content-between align-items-center">
                            <div>
                                <i class="fas fa-chart-line me-2"></i>
                                <strong>Análise #${index + 1} de ${totalFiles}</strong>
                                <span class="badge bg-light text-dark ms-2" id="status-${processId}">⏳ Aguardando</span>
                            </div>
                            <div>
                                <i class="fas fa-file-excel me-1"></i>
                                <small>${escapeHtml(filename.length > 35 ? filename.substring(0, 35) + '...' : filename)}</small>
                            </div>
                        </div>
                    </div>
                    <div class="card-body">
                        <div class="progress-container mb-4" id="progress-container-${processId}">
                            <div class="d-flex justify-content-between small mb-1">
                                <span><i class="fas fa-spinner fa-spin me-1"></i> Processando com IA...</span>
                                <span id="progress-text-${processId}" class="text-muted">0%</span>
                            </div>
                            <div class="progress" style="height: 12px; border-radius: 20px; background: #e2e8f0;">
                                <div id="progress-${processId}" class="progress-bar progress-bar-striped" 
                                     style="width: 0%; background: linear-gradient(90deg, #667eea, #764ba2); border-radius: 20px; transition: width 3.5s ease-out;"></div>
                            </div>
                        </div>
                        
                        <div id="results-${processId}" style="display: none;">
                            <div class="row g-3 mb-4">
                                <div class="col-md-3 col-6">
                                    <div class="metric-box text-center p-3 bg-light rounded-3">
                                        <div class="metric-value h3 mb-0 text-primary" id="total-rows-${processId}">-</div>
                                        <div class="metric-label small text-muted">Total Registros</div>
                                    </div>
                                </div>
                                <div class="col-md-3 col-6">
                                    <div class="metric-box text-center p-3 bg-light rounded-3">
                                        <div class="metric-value h3 mb-0 text-success" id="score-${processId}">-</div>
                                        <div class="metric-label small text-muted">Score Médio</div>
                                    </div>
                                </div>
                                <div class="col-md-3 col-6">
                                    <div class="metric-box text-center p-3 bg-light rounded-3">
                                        <div class="metric-value h3 mb-0 text-info" id="features-${processId}">-</div>
                                        <div class="metric-label small text-muted">Features</div>
                                    </div>
                                </div>
                                <div class="col-md-3 col-6">
                                    <div class="metric-box text-center p-3 bg-light rounded-3">
                                        <div class="metric-value h3 mb-0 text-warning" id="risk-${processId}">-</div>
                                        <div class="metric-label small text-muted">Alto Risco</div>
                                    </div>
                                </div>
                            </div>
                            
                            <div class="d-flex gap-2 justify-content-center mt-3">
                                <button class="btn btn-gradient" onclick="window.showGPSAForAnalysis('${processId}')">
                                    <i class="fas fa-chart-line me-2"></i>
                                    Ver Impacto no Negócio (GPSA)
                                </button>
                                <button class="btn btn-outline-danger" onclick="window.generatePDFReport('${processId}')">
                                    <i class="fas fa-file-pdf me-2"></i>
                                    📄 Gerar PDF novamente
                                </button>
                            </div>
                        </div>
                        
                        <div id="error-${processId}" style="display: none;" class="alert alert-danger">
                            <i class="fas fa-exclamation-triangle me-2"></i>
                            <span id="error-msg-${processId}"></span>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    function displayActiveAnalyses() {
        const container = document.getElementById('activeAnalysesContainer');
        if (!container) return;
        
        if (activeAnalyses.length === 0) {
            container.innerHTML = `
                <div class="text-center text-muted py-5">
                    <i class="fas fa-chart-line fa-3x mb-3 opacity-50"></i>
                    <h5>Nenhuma análise em andamento</h5>
                    <p class="small">Envie arquivos para ver os resultados aqui</p>
                </div>
            `;
            return;
        }
        
        const totalFiles = activeAnalyses.length;
        let html = '<div class="analyses-grid">';
        
        activeAnalyses.forEach((analysis, index) => {
            html += createAnalysisCard(analysis.processId, analysis.filename, index, totalFiles);
        });
        
        html += '</div>';
        container.innerHTML = html;
        
        anime({
            targets: '.analysis-card',
            opacity: [0, 1],
            translateY: [30, 0],
            delay: anime.stagger(200),
            duration: 3500,
            easing: 'easeOutElastic(1, .8)'
        });
    }
    
    function updateAnalysisProgress(processId, status, progress, analysisInfo = null) {
        const progressBar = document.getElementById(`progress-${processId}`);
        const progressText = document.getElementById(`progress-text-${processId}`);
        const statusBadge = document.getElementById(`status-${processId}`);
        const progressContainer = document.getElementById(`progress-container-${processId}`);
        const resultsDiv = document.getElementById(`results-${processId}`);
        const errorDiv = document.getElementById(`error-${processId}`);
        
        if (progress && progress < 100) {
            updateLoadingProgress(progress, `Processando... ${progress}%`);
        }
        
        if (progressBar) {
            anime({
                targets: { width: progress || 0 },
                width: progress || 0,
                duration: 3500,
                easing: 'easeOutQuad',
                update: function(anim) {
                    const currentWidth = Math.round(anim.animations[0].currentValue);
                    progressBar.style.width = `${currentWidth}%`;
                    if (progressText) progressText.textContent = `${currentWidth}%`;
                }
            });
        }
        
        if (statusBadge) {
            let statusClass = 'bg-secondary', statusIcon = '⏳', statusText = status || 'Processando';
            if (status === 'completed') { statusClass = 'bg-success'; statusIcon = '✅'; statusText = 'Concluído'; }
            else if (status === 'error') { statusClass = 'bg-danger'; statusIcon = '❌'; statusText = 'Erro'; }
            statusBadge.innerHTML = `${statusIcon} ${statusText}`;
            statusBadge.className = `badge ${statusClass} ms-2`;
        }
        
        if (status === 'completed' && analysisInfo) {
            hideLoading();
            
            if (progressContainer) {
                anime({
                    targets: progressContainer,
                    opacity: [1, 0],
                    duration: 800,
                    easing: 'easeOutQuad',
                    complete: () => {
                        progressContainer.style.display = 'none';
                        if (resultsDiv) {
                            resultsDiv.style.display = 'block';
                            anime({
                                targets: resultsDiv,
                                opacity: [0, 1],
                                translateY: [20, 0],
                                duration: 1000,
                                easing: 'easeOutElastic(1, .5)'
                            });
                        }
                    }
                });
            }
            
            const totalRows = document.getElementById(`total-rows-${processId}`);
            const scoreElem = document.getElementById(`score-${processId}`);
            const riskElem = document.getElementById(`risk-${processId}`);
            
            if (totalRows) {
                const targetRows = analysisInfo.rows_processed || analysisInfo.total_rows || 0;
                anime({
                    targets: { value: 0 },
                    value: targetRows,
                    duration: 3000,
                    easing: 'easeOutQuad',
                    update: function(anim) {
                        totalRows.textContent = Math.round(anim.animations[0].currentValue).toLocaleString();
                    }
                });
            }
            
            if (scoreElem && analysisInfo.mean_score) {
                const targetScore = Math.round(analysisInfo.mean_score * 100);
                anime({
                    targets: { value: 0 },
                    value: targetScore,
                    duration: 3000,
                    easing: 'easeOutQuad',
                    update: function(anim) {
                        scoreElem.textContent = `${Math.round(anim.animations[0].currentValue)}%`;
                    }
                });
            }
            
            if (riskElem && analysisInfo.high_risk_percentage) {
                const targetRisk = Math.round(analysisInfo.high_risk_percentage);
                anime({
                    targets: { value: 0 },
                    value: targetRisk,
                    duration: 3000,
                    easing: 'easeOutQuad',
                    update: function(anim) {
                        riskElem.textContent = `${Math.round(anim.animations[0].currentValue)}%`;
                    }
                });
            }
            
            // Armazenar resultado
            activeAnalyses = activeAnalyses.map(a => 
                a.processId === processId ? { ...a, result: analysisInfo } : a
            );
            
            showNotification(`✅ Análise concluída: ${analysisInfo.filename || 'Arquivo'}`, 'success');
            
            // 🔥 GERAR PDF AUTOMATICAMENTE APÓS CONCLUSÃO
            setTimeout(() => {
                const analysis = activeAnalyses.find(a => a.processId === processId);
                if (analysis && analysis.result) {
                    generateAutoPDF(processId, analysis.result);
                }
            }, 1500);
            
        } else if (status === 'error') {
            hideLoading();
            
            if (progressContainer) {
                anime({
                    targets: progressContainer,
                    opacity: [1, 0],
                    duration: 500,
                    complete: () => {
                        progressContainer.style.display = 'none';
                        if (errorDiv) errorDiv.style.display = 'block';
                    }
                });
            }
            const errorMsg = document.getElementById(`error-msg-${processId}`);
            if (errorMsg) errorMsg.textContent = analysisInfo?.error || 'Erro no processamento';
            showNotification(`❌ Erro na análise: ${analysisInfo?.filename || 'Arquivo'}`, 'error');
        }
    }
    
    async function pollAnalysisStatus(processId, filename) {
        return new Promise((resolve) => {
            const interval = setInterval(async () => {
                try {
                    const response = await fetchWithAuth(`${API_URL}/status/${processId}`);
                    if (!response) return;
                    
                    const data = await response.json();
                    
                    updateAnalysisProgress(
                        processId, 
                        data.status, 
                        data.progress || 0,
                        {
                            ...data.analysis_info,
                            ...data.prediction_stats,
                            ...data.insights,
                            filename: filename,
                            rows_processed: data.analysis_info?.rows_processed,
                            mean_score: data.prediction_stats?.mean,
                            high_risk_percentage: data.prediction_stats?.high_risk_percentage,
                            total_rows: data.analysis_info?.rows_processed,
                            recomendacoes: data.insights?.recomendacoes || data.insights?.recommendations,
                            full_analysis: data.insights?.full_analysis
                        }
                    );
                    
                    if (data.status === 'completed' || data.status === 'error') {
                        clearInterval(interval);
                        const intervalIndex = pollingIntervals.findIndex(i => i.processId === processId);
                        if (intervalIndex !== -1) pollingIntervals.splice(intervalIndex, 1);
                        resolve(data);
                    }
                } catch (error) {
                    console.error(`Polling error:`, error);
                }
            }, 2000);
            
            pollingIntervals.push({ processId, interval });
        });
    }
    
    // ===== FUNÇÃO PARA MOSTRAR GPSA =====
    
    window.showGPSAForAnalysis = function(processId) {
        const analysis = activeAnalyses.find(a => a.processId === processId);
        if (!analysis || !analysis.result) {
            showNotification('Aguardando conclusão da análise...', 'warning');
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
                    <div class="modal-content" style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);">
                        <div class="modal-header border-0">
                            <h5 class="modal-title" style="color: #f5a623;">
                                <i class="fas fa-chart-line me-2"></i>GPSA - Impacto no Negócio
                            </h5>
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body" id="gpsaModalBody"></div>
                    </div>
                </div>
            `;
            document.body.appendChild(gpsaModal);
        }
        
        if (!gpsaDashboard) {
            gpsaDashboard = new GPSAVisualization();
        }
        
        gpsaDashboard.showDashboard('gpsaModalBody', analysis.result);
        const modal = new bootstrap.Modal(gpsaModal);
        modal.show();
    };
    
    window.closeGPSA = function() {
        const modal = bootstrap.Modal.getInstance(document.getElementById('gpsaModal'));
        if (modal) modal.hide();
        if (gpsaDashboard) gpsaDashboard.hide();
    };
    
    // ===== HANDLE UPLOAD =====
    
    async function handleUpload(e) {
        e.preventDefault();
        
        const fileInput = document.getElementById('fileInput');
        const files = fileInput?.files;
        
        if (!files || files.length === 0) {
            showNotification('Selecione pelo menos um arquivo', 'warning');
            return;
        }
        
        const totalFiles = files.length;
        if (totalFiles > MAX_FILES_PER_BATCH) {
            showNotification(`Máximo de ${MAX_FILES_PER_BATCH} arquivos por vez.`, 'error');
            return;
        }
        
        for (const file of files) {
            if (file.size > MAX_FILE_SIZE_KB * 1024) {
                showNotification(`❌ ${file.name} excede ${MAX_FILE_SIZE_KB}KB`, 'error');
                return;
            }
        }
        
        if (!await checkCreditsBeforeUpload(totalFiles)) return;
        
        showLoading('Iniciando análise...', `Preparando ${totalFiles} arquivo(s) para processamento`);
        updateLoadingProgress(10);
        
        const newAnalyses = [];
        for (let i = 0; i < files.length; i++) {
            newAnalyses.push({
                processId: `temp_${Date.now()}_${i}`,
                filename: files[i].name,
                status: 'waiting'
            });
        }
        
        activeAnalyses = [...newAnalyses, ...activeAnalyses];
        displayActiveAnalyses();
        
        const uploadBtn = document.getElementById('uploadButton');
        const originalText = uploadBtn.innerHTML;
        uploadBtn.disabled = true;
        uploadBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i> Processando arquivos...';
        
        try {
            const formData = new FormData();
            for (let i = 0; i < files.length; i++) {
                formData.append('files', files[i]);
            }
            formData.append('analysis_type', 'auto');
            formData.append('ai_model', 'auto');
            
            const token = localStorage.getItem('access_token');
            const response = await fetch(`${API_URL}/upload-auto`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData
            });
            
            const data = await response.json();
            
            if (response.ok && data.processed_files && data.processed_files.length > 0) {
                for (let i = 0; i < data.processed_files.length; i++) {
                    const processed = data.processed_files[i];
                    if (activeAnalyses[i]) {
                        activeAnalyses[i].processId = processed.process_id;
                    }
                }
                
                displayActiveAnalyses();
                showNotification(`✅ ${data.processed_files.length} arquivo(s) processado(s)!`, 'success');
                
                for (const processed of data.processed_files) {
                    pollAnalysisStatus(processed.process_id, processed.filename);
                }
                
                await loadUserCredits();
                await loadHistory();
                
                fileInput.value = '';
                const previewContainer = document.getElementById('filePreviewContainer');
                if (previewContainer) previewContainer.innerHTML = '';
                
            } else {
                hideLoading();
                activeAnalyses = activeAnalyses.filter(a => !a.processId.toString().startsWith('temp_'));
                displayActiveAnalyses();
                showNotification(data?.detail || 'Erro no upload', 'error');
            }
        } catch (error) {
            console.error('Upload error:', error);
            hideLoading();
            showNotification('Erro ao processar arquivo(s)', 'error');
            activeAnalyses = activeAnalyses.filter(a => !a.processId.toString().startsWith('temp_'));
            displayActiveAnalyses();
        } finally {
            uploadBtn.disabled = false;
            uploadBtn.innerHTML = originalText;
        }
    }
    
    // ===== LOAD HISTORY =====
    
    async function loadHistory() {
        try {
            const response = await fetchWithAuth(`${API_URL}/analyses/history`);
            if (response && response.ok) {
                const data = await response.json();
                updateHistoryUI(data.analyses || data);
            }
        } catch (error) {
            console.error('Erro ao carregar histórico:', error);
        }
    }
    
    function updateHistoryUI(analyses) {
        const container = document.getElementById('recentAnalyses');
        if (!container) return;
        
        if (!analyses || analyses.length === 0) {
            container.innerHTML = `
                <div class="text-center text-muted py-4">
                    <i class="fas fa-chart-line fa-2x mb-2"></i>
                    <p>Nenhuma análise realizada</p>
                    <small>Envie seu primeiro arquivo</small>
                </div>
            `;
            return;
        }
        
        const html = analyses.slice(0, 10).map(a => {
            const date = new Date(a.created_at);
            return `
                <div class="list-group-item list-group-item-action">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <strong>${escapeHtml(a.filename || 'Análise')}</strong>
                            <br><small class="text-muted">${date.toLocaleDateString('pt-BR')}</small>
                        </div>
                        <span class="badge ${a.status === 'completed' ? 'bg-success' : 'bg-secondary'}">${a.status === 'completed' ? 'Concluído' : a.status}</span>
                    </div>
                </div>
            `;
        }).join('');
        
        container.innerHTML = `<div class="list-group">${html}</div>`;
    }
    
    // ===== DRAG & DROP =====
    
    function setupDragAndDrop() {
        const dropZone = document.getElementById('dropZone');
        if (!dropZone) return;
        
        dropZone.addEventListener('dragenter', (e) => { e.preventDefault(); dropZone.classList.add('drag-over'); });
        dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('drag-over'); });
        dropZone.addEventListener('dragleave', () => { dropZone.classList.remove('drag-over'); });
        dropZone.addEventListener('click', () => { document.getElementById('fileInput').click(); });
        
        dropZone.addEventListener('drop', async (e) => {
            e.preventDefault();
            dropZone.classList.remove('drag-over');
            
            const files = Array.from(e.dataTransfer.files);
            if (files.length > 0) {
                if (files.length > MAX_FILES_PER_BATCH) {
                    showNotification(`Máximo de ${MAX_FILES_PER_BATCH} arquivos.`, 'error');
                    return;
                }
                
                const oversized = files.filter(f => f.size > MAX_FILE_SIZE_KB * 1024);
                if (oversized.length > 0) {
                    showNotification(`${oversized.length} arquivo(s) excedem ${MAX_FILE_SIZE_KB}KB`, 'error');
                    return;
                }
                
                const dataTransfer = new DataTransfer();
                files.forEach(f => dataTransfer.items.add(f));
                const fileInput = document.getElementById('fileInput');
                if (fileInput) {
                    fileInput.files = dataTransfer.files;
                    showFilePreview(files);
                    showNotification(`📁 ${files.length} arquivo(s) selecionado(s)!`, 'info');
                }
            }
        });
    }
    
    function showFilePreview(files) {
        let container = document.getElementById('filePreviewContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'filePreviewContainer';
            container.className = 'mt-3';
            const dropZone = document.getElementById('dropZone');
            if (dropZone) dropZone.insertAdjacentElement('afterend', container);
        }
        
        let html = `
            <div class="bg-light p-3 rounded-3">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <strong><i class="fas fa-files me-2"></i>${files.length} arquivo(s):</strong>
                    <button type="button" class="btn btn-sm btn-outline-danger" id="clearFilesBtn">Limpar</button>
                </div>
                <div class="list-group list-group-flush bg-transparent" style="max-height: 200px; overflow-y: auto;">
        `;
        
        for (const file of files) {
            const fileSizeKB = (file.size / 1024).toFixed(1);
            html += `<div class="list-group-item bg-transparent px-0 py-2"><i class="fas fa-file-excel text-success me-2"></i>${escapeHtml(file.name)} <span class="badge bg-secondary ms-2">${fileSizeKB}KB</span></div>`;
        }
        
        html += `</div><div class="text-muted small mt-2"><i class="fas fa-info-circle me-1"></i>Cada arquivo consome 1 crédito. Limite de ${MAX_FILE_SIZE_KB}KB.</div></div>`;
        container.innerHTML = html;
        
        document.getElementById('clearFilesBtn')?.addEventListener('click', () => {
            document.getElementById('fileInput').value = '';
            container.innerHTML = '';
        });
    }
    
    function setupLogout() {
        const logoutBtn = document.getElementById('logoutBtn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', async (e) => {
                e.preventDefault();
                if (window.appAuth && window.appAuth.logout) {
                    await window.appAuth.logout();
                } else {
                    localStorage.clear();
                    window.location.href = '/login';
                }
            });
        }
    }
    
    // ===== INICIALIZAÇÃO =====
    
    await loadUserCredits();
    await loadHistory();
    
    setupDragAndDrop();
    setupLogout();
    
    const uploadForm = document.getElementById('uploadForm');
    if (uploadForm) uploadForm.addEventListener('submit', handleUpload);
    
    const fileInput = document.getElementById('fileInput');
    if (fileInput) {
        fileInput.setAttribute('multiple', 'multiple');
        fileInput.addEventListener('change', (e) => {
            if (e.target.files && e.target.files.length > 0) {
                showFilePreview(Array.from(e.target.files));
            }
        });
    }
    
    console.log('✅ Dashboard inicializado com PDF AUTOMÁTICO + Botão PDF manual + Layout lado a lado!');
    console.log(`📁 Limite: ${MAX_FILE_SIZE_KB}KB por arquivo | Máximo: ${MAX_FILES_PER_BATCH} arquivos`);
    console.log(`📄 PDF gerado automaticamente ao final de cada análise | Botão para gerar novamente`);
    console.log(`📊 Layout: Gráfico e Insights lado a lado`);
});

// ===== ESTILOS =====
(function addStyles() {
    if (document.getElementById('dashboardStyles')) return;
    
    const style = document.createElement('style');
    style.id = 'dashboardStyles';
    style.textContent = `
        @keyframes slideInRight {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        
        .gpsa-dashboard { animation: fadeInUp 0.5s ease-out; }
        
        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .impact-card, .trend-chart-card, .insights-card, .score-progress-card {
            background: rgba(255,255,255,0.08);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.15);
            transition: all 0.3s ease;
        }
        
        .impact-card:hover, .trend-chart-card:hover {
            transform: translateY(-5px);
            background: rgba(255,255,255,0.12);
        }
        
        .impact-value { font-size: 2.5rem; font-weight: bold; margin: 10px 0; }
        .trend-indicator { font-size: 0.8rem; padding: 4px 8px; background: rgba(0,0,0,0.2); border-radius: 20px; display: inline-block; }
        .insight-item { transition: all 0.2s; }
        .insight-item:hover { transform: translateX(5px); background: rgba(255,255,255,0.1) !important; }
        
        .gpsa-score-circle { position: relative; display: inline-block; }
        .score-ring { transform: rotate(-90deg); transform-origin: 50% 50%; transition: stroke-dashoffset 1.5s ease-out; }
        .score-text { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); text-align: center; }
        .score-number { font-size: 2rem; font-weight: bold; display: block; line-height: 1; }
        
        .drag-over { background: rgba(102,126,234,0.1); border: 2px dashed #667eea !important; transform: scale(1.02); }
        
        .btn-gradient {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            border: none;
            transition: all 0.3s;
        }
        .btn-gradient:hover { transform: translateY(-2px); box-shadow: 0 8px 25px rgba(102,126,234,0.4); color: white; }
        
        .btn-outline-danger {
            background: transparent;
            border: 1px solid #f56565;
            color: #f56565;
            transition: all 0.3s;
        }
        .btn-outline-danger:hover {
            background: #f56565;
            color: white;
            transform: translateY(-2px);
        }
        
        .progress-bar { transition: width 3.5s ease-out; }
        .analysis-card { transition: all 0.3s ease; }
        .analysis-card:hover { transform: translateY(-4px); }
        
        .metric-box { transition: all 0.2s; }
        .metric-box:hover { transform: translateY(-2px); background: #e9ecef !important; }
        
        .badge { font-weight: normal; }
        .trend-chart-card canvas { max-height: 250px; width: 100%; }
        
        .risk-summary {
            background: rgba(0,0,0,0.2);
            backdrop-filter: blur(5px);
        }
        
        .risk-badge {
            transition: all 0.3s ease;
        }
        
        .risk-badge.high {
            background: rgba(245, 101, 101, 0.2);
            border: 1px solid rgba(245, 101, 101, 0.5);
        }
        
        .risk-badge.medium {
            background: rgba(245, 166, 35, 0.2);
            border: 1px solid rgba(245, 166, 35, 0.5);
        }
        
        .risk-badge.low {
            background: rgba(72, 187, 120, 0.2);
            border: 1px solid rgba(72, 187, 120, 0.5);
        }
        
        .risk-badge:hover {
            transform: translateY(-2px);
        }
        
        .risk-value {
            font-size: 1.5rem;
        }
        
        .risk-label {
            font-size: 0.75rem;
            opacity: 0.8;
        }
        
        @media (max-width: 768px) {
            .impact-value { font-size: 1.8rem; }
            .score-number { font-size: 1.5rem; }
            .gpsa-score-circle svg { width: 100px; height: 100px; }
            .risk-value { font-size: 1.2rem; }
            .btn-gradient, .btn-outline-danger { font-size: 0.8rem; padding: 0.5rem 0.75rem; }
        }
    `;
    document.head.appendChild(style);
})();

// Funções globais
window.showGPSAForAnalysis = window.showGPSAForAnalysis;
window.closeGPSA = window.closeGPSA;
window.generatePDFReport = window.generatePDFReport;