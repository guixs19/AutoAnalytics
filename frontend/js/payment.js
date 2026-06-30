// payment.js - VERSÃO OTIMIZADA v2.5 (CÓDIGO LIMPO E COMPLETO)
// ==============================================
// 🔥 OTIMIZAÇÕES V2.5:
// 1. Código mais limpo e organizado
// 2. Remoção de duplicações
// 3. Fallback para renderização estática do plano
// 4. Modais criados dinamicamente e corretamente
// 5. Todas as funções expostas globalmente
// ==============================================

(function() {
    'use strict';

    console.log('🚀 Inicializando payment.js v2.5 (otimizado)...');

    // ==============================================
    // 🔒 CONFIGURAÇÕES GLOBAIS
    // ==============================================

    const CONFIG = {
        MAX_CREDITS_BALANCE: 3,
        INITIAL_FREE_CREDITS: 3,
        PIX_EXPIRY_MINUTES: 30,
        PROMOTIONAL_PRICE: 97.00,
        REGULAR_PRICE: 149.90,
        TOTAL_PROMOTIONAL_SLOTS: 100,
        DAYS_PREMIUM: 30
    };

    // API_URL dinâmica
    const API_URL = (() => {
        const isLocalhost = window.location.hostname === 'localhost' || 
                            window.location.hostname === '127.0.0.1';
        return isLocalhost ? 'http://localhost:8000/api' : '/api';
    })();

    console.log(`🌐 API_URL: ${API_URL}`);
    console.log(`💰 Preço Fundador: R$ ${CONFIG.PROMOTIONAL_PRICE}`);

    // ==============================================
    // 🔒 SEGURANÇA (XSS PROTECTION)
    // ==============================================

    function sanitizeHTML(str) {
        if (!str) return '';
        if (typeof str !== 'string') str = String(str);
        
        const escapeMap = {
            '&': '&amp;', '<': '&lt;', '>': '&gt;',
            '"': '&quot;', "'": '&#39;', '`': '&#96;',
            '/': '&#47;', '=': '&#61;', '(': '&#40;',
            ')': '&#41;', ';': '&#59;'
        };
        
        return str.replace(/[&<>"'`/=();]/g, m => escapeMap[m] || m)
                  .replace(/javascript:/gi, '')
                  .replace(/on\w+\s*=/gi, '')
                  .replace(/eval\s*\(/gi, '')
                  .slice(0, 5000);
    }

    function sanitizeNumber(value, defaultValue = 0) {
        if (value === undefined || value === null) return defaultValue;
        const num = parseFloat(String(value).replace(/[^0-9.,-]/g, '').replace(',', '.'));
        return isNaN(num) ? defaultValue : num;
    }

    function sanitizeCPF(cpf) {
        if (!cpf) return '';
        return String(cpf).replace(/\D/g, '');
    }

    function validateCPF(cpf) {
        const clean = sanitizeCPF(cpf);
        if (clean.length !== 11) return false;
        
        const invalid = ['00000000000', '11111111111', '22222222222', '33333333333',
                        '44444444444', '55555555555', '66666666666', '77777777777',
                        '88888888888', '99999999999'];
        if (invalid.includes(clean)) return false;
        
        let sum = 0, remainder;
        for (let i = 1; i <= 9; i++) {
            sum += parseInt(clean[i - 1]) * (11 - i);
        }
        remainder = (sum * 10) % 11;
        if (remainder === 10 || remainder === 11) remainder = 0;
        if (remainder !== parseInt(clean[9])) return false;
        
        sum = 0;
        for (let i = 1; i <= 10; i++) {
            sum += parseInt(clean[i - 1]) * (12 - i);
        }
        remainder = (sum * 10) % 11;
        if (remainder === 10 || remainder === 11) remainder = 0;
        if (remainder !== parseInt(clean[10])) return false;
        
        return true;
    }

    function sanitizeObject(obj) {
        if (obj === null || obj === undefined) return obj;
        if (typeof obj === 'string') return sanitizeHTML(obj);
        if (typeof obj === 'number') return sanitizeNumber(obj);
        if (Array.isArray(obj)) return obj.map(sanitizeObject);
        if (typeof obj === 'object') {
            const result = {};
            for (const [key, value] of Object.entries(obj)) {
                result[sanitizeHTML(key)] = sanitizeObject(value);
            }
            return result;
        }
        return obj;
    }

    function sanitizeResponse(data) {
        return sanitizeObject(data);
    }

    // ==============================================
    // 🔒 AUTENTICAÇÃO (via appAuth)
    // ==============================================

    function isAdmin() {
        try { return window.appAuth ? window.appAuth.isAdmin() : false; } catch { return false; }
    }

    function getCredits() {
        try { return window.appAuth ? window.appAuth.getCredits() : 0; } catch { return 0; }
    }

    function isPremium() {
        try { return window.appAuth ? window.appAuth.isPremium() : false; } catch { return false; }
    }

    function formatCreditsDisplay(credits, isPremiumUser = false) {
        const safeCredits = sanitizeNumber(credits, 0);
        if (isAdmin()) return '∞';
        if (isPremiumUser) return `${safeCredits}/${CONFIG.MAX_CREDITS_BALANCE}`;
        return safeCredits.toString();
    }

    // ==============================================
    // 🔥 REQUISIÇÕES AUTENTICADAS
    // ==============================================

    async function fetchWithAuth(url, options = {}) {
        if (window.appAuth?.fetchWithAuth) {
            return window.appAuth.fetchWithAuth(url, options);
        }
        
        const token = localStorage.getItem('access_token');
        const headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            ...options.headers
        };
        if (token) headers['Authorization'] = `Bearer ${token}`;
        
        try {
            const response = await fetch(url, { ...options, headers });
            if (response.status === 401) {
                localStorage.removeItem('access_token');
                localStorage.removeItem('refresh_token');
                window.location.href = '/login?session=expired';
                return null;
            }
            return response;
        } catch (error) {
            console.error('Fetch error:', error);
            return null;
        }
    }

    // ==============================================
    // 🔥 NOTIFICAÇÕES
    // ==============================================

    function showNotification(message, type = 'info') {
        const safeMessage = sanitizeHTML(message);
        
        if (window.appAuth?.showNotification) {
            return window.appAuth.showNotification(safeMessage, type);
        }
        
        if (window.toastr) {
            const opts = { closeButton: true, progressBar: true, positionClass: 'toast-top-right', timeOut: 5000, escapeHtml: true };
            const map = { success: 'success', error: 'error', warning: 'warning', info: 'info' };
            toastr[map[type] || 'info'](safeMessage, '', opts);
        } else {
            console.log(`[${type}] ${safeMessage}`);
        }
    }

    // ==============================================
    // 🔥 ATUALIZAR CRÉDITOS
    // ==============================================

    async function updateCreditsDisplay() {
        try {
            let credits = getCredits();
            let isPremiumUser = isPremium();
            
            if (window.appAuth?.loadUserCredits) {
                await window.appAuth.loadUserCredits();
                credits = window.appAuth.getCredits?.() || 0;
                isPremiumUser = window.appAuth.isPremium?.() || false;
            }
            
            const displayText = formatCreditsDisplay(credits, isPremiumUser);
            
            document.querySelectorAll('#creditsCount, #creditsDisplay, #uploadCredits, .credits-badge span').forEach(el => {
                if (el) el.textContent = displayText;
            });
            
            window.dispatchEvent(new CustomEvent('creditsUpdated', {
                detail: { credits, display: displayText, maxCredits: CONFIG.MAX_CREDITS_BALANCE, isPremium: isPremiumUser }
            }));
            
            return true;
        } catch (error) {
            console.error('Erro ao atualizar créditos:', error);
            return false;
        }
    }

    // ==============================================
    // 🔥 RENDERIZAÇÃO DO PLANO (FALLBACK ESTÁTICO)
    // ==============================================

    function renderBronzePlanStatic() {
        const container = document.getElementById('plansContainer');
        if (!container) return;

        if (isAdmin()) {
            container.innerHTML = `
                <div class="col-lg-8 mx-auto">
                    <div class="admin-message" style="background: linear-gradient(135deg, #2c1a0a 0%, #3d2614 100%); border-radius: 40px; padding: 3rem; border: 1px solid #cd7f32; text-align: center;">
                        <i class="fas fa-crown" style="font-size: 4rem; color: #f5a623; margin-bottom: 1rem;"></i>
                        <h2 class="h3 mb-3" style="color: #f5a623;">👑 Você é Administrador</h2>
                        <p class="lead mb-4" style="color: rgba(255,255,255,0.7);">Como admin, você tem acesso ilimitado a todas as funcionalidades.</p>
                        <a href="/dashboard" class="btn btn-light btn-lg mt-3"><i class="fas fa-arrow-left me-2"></i> Voltar ao Dashboard</a>
                    </div>
                </div>
            `;
            return;
        }

        const html = `
            <div class="col-lg-8 mx-auto">
                <div class="bronze-card" data-aos="fade-up" data-aos-duration="800">
                    <div class="bronze-badge"><i class="fas fa-fire"></i> 🔥 PROMOÇÃO FUNDADOR</div>
                    
                    <div class="bronze-title">
                        <span class="icon-big"><i class="fas fa-crown"></i></span>
                        <h2>Plano Bronze</h2>
                        <p class="subtitle">O plano ideal para sua oficina crescer com IA</p>
                    </div>
                    
                    <div class="price-container">
                        <span class="old-price">De R$ 149,90</span>
                        <div class="price-tag" id="planoPreco">R$ 97<span class="cents">,00</span> <small>à vista</small></div>
                        <span class="economy-badge"><i class="fas fa-tag"></i> Economia de 35%</span>
                    </div>
                    
                    <div class="plan-info">
                        <div class="row">
                            <div class="col-4"><span class="number">30</span><span class="label">Créditos</span></div>
                            <div class="col-4"><span class="number">3</span><span class="label">Arquivos/vez</span></div>
                            <div class="col-4"><span class="number">∞</span><span class="label">Vitalício</span></div>
                        </div>
                    </div>
                    
                    <div class="vagas-counter">
                        <div><span class="vagas-label">🎯 Apenas</span> <span class="vagas-number">73</span> <span class="vagas-label">vagas restantes</span></div>
                        <div class="vagas-progress"><div class="vagas-progress-bar" style="width: 27%;"></div></div>
                        <small style="color:rgba(255,255,255,0.3); font-size:0.7rem;"><i class="fas fa-clock"></i> Oferta por tempo limitado</small>
                    </div>
                    
                    <div class="bronze-features">
                        <div class="bronze-feature"><i class="fas fa-check-circle check"></i> <span><strong>30 créditos</strong> para análises completas</span></div>
                        <div class="bronze-feature"><i class="fas fa-check-circle check"></i> <span><strong>Análise com IA</strong> (Google Gemini)</span></div>
                        <div class="bronze-feature"><i class="fas fa-check-circle check"></i> <span><strong>Até 3 arquivos</strong> por análise (CSV/Excel)</span></div>
                        <div class="bronze-feature"><i class="fas fa-check-circle check"></i> <span>📊 <strong>Dashboard completo</strong> com métricas</span></div>
                        <div class="bronze-feature"><i class="fas fa-check-circle check"></i> <span>📄 <strong>Relatórios em PDF</strong> automáticos</span></div>
                        <div class="bronze-feature"><i class="fas fa-check-circle check"></i> <span><strong>Suporte prioritário</strong> por email</span></div>
                    </div>
                    
                    <div class="d-grid gap-3 mt-4">
                        <button class="btn btn-bronze btn-lg" onclick="window.openCpfModal('premium_mensal')">
                            <i class="fas fa-bolt me-2"></i> 🔥 GARANTIR PREÇO FUNDADOR R$ 97,00
                            <small class="d-block fs-10">Pagamento seguro via PIX</small>
                        </button>
                    </div>
                    
                    <div class="limit-warning">
                        <i class="fas fa-info-circle"></i>
                        <span>Este é um <strong>plano vitalício</strong> com preço especial para os primeiros <strong>100 clientes</strong>. Após esgotar, o preço volta para R$ 149,90.</span>
                    </div>
                    
                    <div class="credits-explanation">
                        <div class="step"><i class="fas fa-coins"></i> <span><strong>Como funcionam os créditos:</strong></span></div>
                        <div class="step"><i class="fas fa-plus-circle"></i> <span>Você começa com <strong>3 créditos grátis</strong></span></div>
                        <div class="step"><i class="fas fa-gem"></i> <span>Com o <strong>Plano Bronze</strong>, você ganha <strong>30 créditos</strong> para usar quando quiser</span></div>
                        <div class="step"><i class="fas fa-chart-line"></i> <span>Cada análise consome <strong>1 crédito</strong> por arquivo</span></div>
                        <div class="highlight-box"><span><i class="fas fa-bolt" style="color:#f5a623;"></i> <strong>Dica:</strong> Use seus créditos estrategicamente para análises mais importantes e maximize o ROI da sua oficina!</span></div>
                    </div>
                    
                    <div class="security-seals">
                        <span class="seal"><i class="fas fa-lock"></i> Pagamento Seguro</span>
                        <span class="seal"><i class="fas fa-shield-alt"></i> PoW Protegido</span>
                        <span class="seal"><i class="fas fa-credit-card"></i> PIX</span>
                    </div>
                </div>
            </div>
        `;
        
        container.innerHTML = html;
    }

    async function loadPlans() {
        try {
            const response = await fetch(`${API_URL}/payments/plans`);
            if (response.ok) {
                const data = await response.json();
                const safeData = sanitizeResponse(data);
                // Tenta renderizar com dados da API
                renderBronzePlan(safeData.plans, safeData);
            } else {
                console.warn('⚠️ Falha ao carregar planos da API, usando fallback estático');
                renderBronzePlanStatic();
            }
        } catch (error) {
            console.warn('⚠️ Erro ao carregar planos, usando fallback estático:', error);
            renderBronzePlanStatic();
        }
    }

    async function renderBronzePlan(plans, fullData = null) {
        const container = document.getElementById('plansContainer');
        if (!container) return;
        
        if (isAdmin()) {
            renderBronzePlanStatic();
            return;
        }
        
        // Se não tiver dados da API, usa fallback
        if (!plans || !plans['premium_mensal']) {
            renderBronzePlanStatic();
            return;
        }
        
        // Tenta buscar status da promoção
        let promoData = {
            remaining_slots: CONFIG.TOTAL_PROMOTIONAL_SLOTS,
            total_slots: CONFIG.TOTAL_PROMOTIONAL_SLOTS,
            promotional_price: CONFIG.PROMOTIONAL_PRICE,
            regular_price: CONFIG.REGULAR_PRICE,
            user_locked_price: null
        };
        
        try {
            const promoResponse = await fetchWithAuth(`${API_URL}/payments/promotion-status`);
            if (promoResponse?.ok) {
                const rawData = await promoResponse.json();
                promoData = sanitizeResponse(rawData);
            }
        } catch (error) {
            console.warn('Erro ao buscar status da promoção:', error);
        }
        
        // Se não conseguiu dados da promoção, usa fallback
        if (!promoData.remaining_slots) {
            renderBronzePlanStatic();
            return;
        }
        
        const vagasRestantes = sanitizeNumber(promoData.remaining_slots, CONFIG.TOTAL_PROMOTIONAL_SLOTS);
        const totalVagas = sanitizeNumber(promoData.total_slots, CONFIG.TOTAL_PROMOTIONAL_SLOTS);
        const precoPromocional = sanitizeNumber(promoData.promotional_price, CONFIG.PROMOTIONAL_PRICE);
        const precoRegular = sanitizeNumber(promoData.regular_price, CONFIG.REGULAR_PRICE);
        const isUserLocked = promoData.user_locked_price !== null && promoData.user_locked_price !== undefined;
        const isSoldOut = vagasRestantes <= 0;
        const precoAtual = isSoldOut ? precoRegular : precoPromocional;
        const percentual = ((totalVagas - vagasRestantes) / totalVagas) * 100;
        const isUrgent = vagasRestantes <= 20 && vagasRestantes > 0;
        
        let precoMessage = isUserLocked ? `
            <div class="vitalicio-badge">
                <i class="fas fa-gem me-2"></i>
                PREÇO VITALÍCIO GARANTIDO!
                <small>R$ ${precoAtual.toFixed(2).replace('.', ',')} para sempre</small>
            </div>
        ` : '';
        
        const html = `
            <div class="col-lg-8 mx-auto">
                <div class="bronze-card" data-aos="fade-up" data-aos-duration="800">
                    <div class="bronze-badge">
                        <i class="fas fa-fire"></i> 
                        ${isSoldOut ? 'PROMOÇÃO ENCERRADA' : (isUserLocked ? '🔥 SEU PREÇO VITALÍCIO' : '🔥 PROMOÇÃO FUNDADOR')}
                    </div>
                    
                    ${precoMessage}
                    
                    <div class="bronze-title">
                        <h2><i class="fas fa-crown me-2"></i> Plano Bronze</h2>
                        <p><i class="fas fa-check-circle me-1"></i> A escolha dos profissionais</p>
                    </div>
                    
                    <div class="price-container">
                        ${!isSoldOut && !isUserLocked ? `<span class="old-price">De R$ ${precoRegular.toFixed(2).replace('.', ',')}</span>` : ''}
                        <div class="price-tag" id="planoPreco">R$ ${precoAtual.toFixed(2).replace('.', ',')}<small>/mês</small></div>
                        ${!isSoldOut && !isUserLocked ? `<span class="economy-badge">🔥 ECONOMIZE R$ ${(precoRegular - precoPromocional).toFixed(2).replace('.', ',')} 🔥</span>` : ''}
                        ${isUserLocked ? `<span class="economy-badge" style="background: linear-gradient(135deg, #28a745, #20c997);"><i class="fas fa-lock me-1"></i> PREÇO BLOQUEADO - VITALÍCIO</span>` : ''}
                        ${isSoldOut && !isUserLocked ? `<span class="economy-badge" style="background: linear-gradient(135deg, #dc3545, #c0392b);"><i class="fas fa-exclamation-triangle me-1"></i> PROMOÇÃO ESGOTADA</span>` : ''}
                    </div>
                    
                    ${!isSoldOut && !isUserLocked ? `
                    <div class="vagas-counter ${isUrgent ? 'vagas-urgent' : ''}">
                        <div class="d-flex align-items-center justify-content-center flex-wrap">
                            <i class="fas fa-ticket-alt fa-2x me-3" style="color: #f5a623;"></i>
                            <div>
                                <span class="vagas-label">VAGAS PROMOCIONAIS</span>
                                <div>
                                    <span class="vagas-number">${vagasRestantes}</span>
                                    <span class="vagas-label">restantes de ${totalVagas}</span>
                                </div>
                            </div>
                        </div>
                        <div class="vagas-progress"><div class="vagas-progress-bar" style="width: ${Math.min(100, percentual)}%"></div></div>
                        ${isUrgent ? `
                            <div class="mt-2 text-center">
                                <strong style="color: #f5a623;">🔥 URGENTE! ÚLTIMAS ${vagasRestantes} VAGAS! 🔥</strong>
                                <br><small>Garanta o preço de fundador R$ ${precoPromocional.toFixed(2).replace('.', ',')} (vitalício)</small>
                            </div>
                        ` : `
                            <div class="mt-2 text-center small text-muted">Apenas as primeiras ${totalVagas} pessoas pagam R$ ${precoPromocional.toFixed(2).replace('.', ',')} (vitalício)</div>
                        `}
                    </div>
                    ` : ''}
                    
                    ${isUserLocked ? `
                    <div class="vagas-counter" style="background: rgba(40, 167, 69, 0.2); border-color: #28a745;">
                        <div class="d-flex align-items-center justify-content-center flex-wrap">
                            <i class="fas fa-lock fa-2x me-3" style="color: #28a745;"></i>
                            <div>
                                <span class="vagas-label">PREÇO GARANTIDO</span>
                                <div>
                                    <span class="vagas-number" style="color: #28a745;">R$ ${precoAtual.toFixed(2).replace('.', ',')}</span>
                                    <span class="vagas-label">para sempre!</span>
                                </div>
                            </div>
                        </div>
                        <div class="mt-2 text-center small text-success"><i class="fas fa-check-circle me-1"></i> Você comprou na promoção e teve o preço bloqueado!</div>
                    </div>
                    ` : ''}
                    
                    ${isSoldOut && !isUserLocked ? `
                    <div class="vagas-counter" style="background: rgba(220, 53, 69, 0.2); border-color: #dc3545;">
                        <div class="d-flex align-items-center justify-content-center flex-wrap">
                            <i class="fas fa-exclamation-triangle fa-2x me-3" style="color: #dc3545;"></i>
                            <div>
                                <span class="vagas-label">PROMOÇÃO ESGOTADA</span>
                                <div>
                                    <span class="vagas-number" style="color: #dc3545;">0</span>
                                    <span class="vagas-label">vagas restantes</span>
                                </div>
                            </div>
                        </div>
                        <div class="mt-2 text-center small text-danger">As ${totalVagas} vagas promocionais já foram preenchidas. Valor: R$ ${precoRegular.toFixed(2).replace('.', ',')}</div>
                    </div>
                    ` : ''}
                    
                    <div class="my-3">
                        <div class="highlight-title"><i class="fas fa-star me-2"></i> O que você recebe:</div>
                        <div class="bronze-feature"><i class="fas fa-brain"></i> <span><strong>IA Avançada (Gemini + Scikit-Learn)</strong> - Análises preditivas</span></div>
                        <div class="bronze-feature"><i class="fas fa-file-alt"></i> <span><strong>Relatórios Completos em PDF</strong> - Exporte análises</span></div>
                        <div class="bronze-feature"><i class="fas fa-chart-line"></i> <span><strong>Dashboard Interativo</strong> - Métricas em tempo real</span></div>
                        <div class="bronze-feature"><i class="fas fa-calendar-day"></i> <span><strong>1 crédito novo por dia</strong> - Para novas análises</span></div>
                        <div class="bronze-feature"><i class="fas fa-layer-group"></i> <span><strong>Até ${CONFIG.MAX_CREDITS_BALANCE} créditos acumulados</strong> - Máximo de ${CONFIG.MAX_CREDITS_BALANCE}</span></div>
                        <div class="bronze-feature"><i class="fas fa-chart-pie"></i> <span><strong>Gráficos automáticos</strong> - Visualização inteligente</span></div>
                        <div class="bronze-feature"><i class="fas fa-download"></i> <span><strong>Exportação CSV/Excel</strong> - Seus dados sempre disponíveis</span></div>
                        <div class="bronze-feature"><i class="fas fa-headset"></i> <span><strong>Suporte Prioritário 24/7</strong> - Atendimento exclusivo</span></div>
                    </div>
                    
                    <div class="plan-info">
                        <div class="row text-center">
                            <div class="col-4"><i class="fas fa-coins fa-lg"></i><div class="small fw-bold mt-1">${CONFIG.DAYS_PREMIUM} Créditos</div><div class="small text-muted">Total do plano</div></div>
                            <div class="col-4"><i class="fas fa-clock fa-lg"></i><div class="small fw-bold mt-1">${CONFIG.DAYS_PREMIUM} Dias</div><div class="small text-muted">Duração</div></div>
                            <div class="col-4"><i class="fas fa-tachometer-alt fa-lg"></i><div class="small fw-bold mt-1">${CONFIG.MAX_CREDITS_BALANCE} Máx.</div><div class="small text-muted">Créditos acumulados</div></div>
                        </div>
                    </div>
                    
                    <div class="limit-warning">
                        <i class="fas fa-info-circle"></i>
                        <small>⚠️ Limite máximo de <strong>${CONFIG.MAX_CREDITS_BALANCE} créditos acumulados</strong>. Use-os para continuar recebendo novos créditos diários!</small>
                    </div>
                    
                    <div class="d-grid gap-3 mt-4">
                        <button class="btn btn-bronze btn-lg" onclick="window.openCpfModal('premium_mensal')">
                            <i class="fas fa-bolt me-2"></i>
                            ${isUserLocked ? 'RENOVAR MEU PLANO' : (isSoldOut ? `COMPRAR POR R$ ${precoAtual.toFixed(2).replace('.', ',')}` : `🔥 GARANTIR PREÇO FUNDADOR R$ ${precoAtual.toFixed(2).replace('.', ',')}`)}
                            <small class="d-block fs-10">${isUserLocked ? 'Pagamento vitalício garantido' : 'Pagamento seguro via PIX'}</small>
                        </button>
                    </div>
                    
                    <div class="security-seals">
                        <span class="badge me-2"><i class="fas fa-lock"></i> Pagamento 100% Seguro</span>
                        <span class="badge me-2"><i class="fas fa-undo-alt"></i> 7 Dias de Garantia</span>
                        <span class="badge"><i class="fas fa-clock"></i> Ativação Imediata</span>
                    </div>
                    
                    <p class="text-center small mt-4 mb-0" style="color: rgba(255,255,255,0.6);">
                        <i class="fas fa-check-circle text-warning me-1"></i>
                        Após o pagamento, você receberá 1 crédito por dia durante ${CONFIG.DAYS_PREMIUM} dias
                    </p>
                </div>
            </div>
        `;
        
        container.innerHTML = html;
    }

    // ==============================================
    // 🔥 MODAL DE CPF (DINÂMICO)
    // ==============================================

    function openCpfModal(planId) {
        if (isAdmin()) {
            showNotification('👑 Como administrador, você tem acesso ilimitado.', 'info');
            return;
        }
        
        let cpfModal = document.getElementById('cpfModal');
        
        if (!cpfModal) {
            cpfModal = document.createElement('div');
            cpfModal.id = 'cpfModal';
            cpfModal.className = 'modal fade';
            cpfModal.setAttribute('tabindex', '-1');
            cpfModal.setAttribute('aria-hidden', 'true');
            document.body.appendChild(cpfModal);
        }

        cpfModal.innerHTML = `
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content" style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border: 1px solid #f5a623;">
                    <div class="modal-header border-0">
                        <h5 class="modal-title" style="color: #f5a623;"><i class="fas fa-id-card me-2"></i>Confirme seu CPF</h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <p class="text-white-50 mb-3"><i class="fas fa-shield-alt me-2"></i> O CPF é obrigatório para geração do PIX e protege sua compra contra fraudes.</p>
                        <div class="mb-3">
                            <label class="form-label text-white">CPF</label>
                            <input type="text" class="form-control form-control-lg" id="cpfInput" placeholder="000.000.000-00" maxlength="14" autocomplete="off" style="background: rgba(255,255,255,0.1); border-color: #f5a623; color: white; border-radius:12px;">
                            <div class="form-text text-white-50">Apenas números (11 dígitos)</div>
                        </div>
                        <div id="cpfError" class="alert alert-danger d-none" role="alert"></div>
                    </div>
                    <div class="modal-footer border-0">
                        <button type="button" class="btn" style="background:rgba(255,255,255,0.06); color:rgba(255,255,255,0.6); border:none; border-radius:50px; padding:0.5rem 1.5rem;" data-bs-dismiss="modal">Cancelar</button>
                        <button type="button" class="btn btn-bronze" onclick="window.proceedWithCpf('${sanitizeHTML(planId)}')"><i class="fas fa-arrow-right me-2"></i>Continuar para PIX</button>
                    </div>
                </div>
            </div>
        `;

        // Máscara de CPF
        const cpfInput = document.getElementById('cpfInput');
        if (cpfInput) {
            cpfInput.addEventListener('input', function(e) {
                let value = e.target.value.replace(/\D/g, '');
                if (value.length > 11) value = value.slice(0, 11);
                if (value.length > 9) {
                    value = value.replace(/^(\d{3})(\d{3})(\d{3})(\d{2})$/, '$1.$2.$3-$4');
                } else if (value.length > 6) {
                    value = value.replace(/^(\d{3})(\d{3})(\d{0,3})$/, '$1.$2.$3');
                } else if (value.length > 3) {
                    value = value.replace(/^(\d{3})(\d{0,3})$/, '$1.$2');
                }
                e.target.value = value;
            });
        }

        new bootstrap.Modal(cpfModal).show();
    }

    function proceedWithCpf(planId) {
        const cpfInput = document.getElementById('cpfInput');
        const cpfError = document.getElementById('cpfError');
        
        if (!cpfInput) {
            showNotification('Erro ao processar CPF. Tente novamente.', 'error');
            return;
        }
        
        const cpfLimpo = sanitizeCPF(cpfInput.value);
        
        if (!validateCPF(cpfLimpo)) {
            if (cpfError) {
                cpfError.textContent = '❌ CPF inválido. Digite um CPF válido com 11 dígitos.';
                cpfError.classList.remove('d-none');
            }
            return;
        }
        
        if (cpfError) cpfError.classList.add('d-none');
        
        // Fecha modal CPF
        const cpfModal = bootstrap.Modal.getInstance(document.getElementById('cpfModal'));
        if (cpfModal) cpfModal.hide();
        
        // Abre modal PIX
        showPixModalSecure(planId, cpfLimpo);
    }

    // ==============================================
    // 🔥 MODAL PIX (DINÂMICO)
    // ==============================================

    let countdownInterval = null;

    function showPixModalSecure(planId, cpf) {
        console.log(`💳 Abrindo modal PIX - Plano: ${planId}, CPF: ${cpf}`);
        
        let pixModal = document.getElementById('pixModal');
        
        if (!pixModal) {
            pixModal = document.createElement('div');
            pixModal.id = 'pixModal';
            pixModal.className = 'modal fade';
            pixModal.setAttribute('tabindex', '-1');
            pixModal.setAttribute('aria-hidden', 'true');
            document.body.appendChild(pixModal);
        }

        const valorPlano = "R$ 97,00";
        const planName = "Plano Bronze";

        pixModal.innerHTML = `
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content" style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border: 1px solid rgba(205,127,50,0.3);">
                    <div class="modal-header border-0" style="border-bottom: 1px solid rgba(255,255,255,0.1);">
                        <h5 class="modal-title" style="color: #f5a623;"><i class="fas fa-qrcode me-2"></i> Pagamento via PIX</h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body text-center py-4">
                        <div class="alert alert-success mb-3 text-center" style="background: rgba(40, 167, 69, 0.15); border-color: #28a745; color: #48bb78;">
                            <i class="fas fa-gem me-2"></i>
                            <strong>🎉 VOCÊ GARANTIU O PREÇO FUNDADOR!</strong><br>
                            <small>${valorPlano} - Preço bloqueado VITALÍCIO!</small>
                        </div>
                        
                        <h6 class="mb-3" style="color: rgba(255,255,255,0.7);">Escaneie o QR Code com seu banco</h6>
                        
                        <div class="text-center mb-3">
                            <div class="p-3 d-inline-block" style="background: white; border-radius: 16px;">
                                <img src="https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=pix%3A%2F%2Fautonalytics%40gmail.com%3Famount%3D97.00%26cpf%3D${cpf}" 
                                     alt="QR Code PIX" style="max-width: 200px; border-radius: 8px;">
                            </div>
                        </div>
                        
                        <div class="p-3 rounded-3 mb-3" style="background: rgba(255,255,255,0.05); word-break: break-all;">
                            <code id="pixCodeText" class="small" style="color: #f5a623;">autonalytics@gmail.com</code>
                        </div>
                        
                        <button class="btn w-100 mb-3" onclick="window.copyPixCodeSecure()" 
                                style="background: rgba(255,255,255,0.06); color: #f5a623; border: 1px solid rgba(205,127,50,0.3); border-radius: 12px; padding: 0.75rem;">
                            <i class="fas fa-copy me-2"></i> Copiar Chave PIX
                        </button>
                        
                        <div class="alert alert-info small" style="background: rgba(245, 166, 35, 0.08); border-color: rgba(205,127,50,0.2); color: rgba(255,255,255,0.7);">
                            <i class="fas fa-info-circle me-2"></i>
                            <strong>Informações do pagamento:</strong><br>
                            <strong>${planName}</strong> - Valor: ${valorPlano}<br>
                            <span class="text-success">✅ Você está comprando na promoção! Preço R$ 97,00 garantido para sempre.</span><br>
                            <span style="color: rgba(255,255,255,0.5);">⏰ Este QR Code expira em <strong id="countdownTimer">30:00</strong> minutos.</span>
                        </div>
                        
                        <div id="paymentStatus"></div>
                    </div>
                    <div class="modal-footer border-0 justify-content-center" style="border-top: 1px solid rgba(255,255,255,0.06);">
                        <button type="button" class="btn w-100" onclick="location.reload()" 
                                style="background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.6); border: none; border-radius: 50px; padding: 0.75rem;">
                            <i class="fas fa-sync-alt me-2"></i> Já realizei o pagamento / Atualizar
                        </button>
                    </div>
                </div>
            </div>
        `;

        startCountdown(30 * 60);
        new bootstrap.Modal(pixModal).show();
    }

    function startCountdown(seconds) {
        if (countdownInterval) clearInterval(countdownInterval);
        
        let remaining = sanitizeNumber(seconds, 30 * 60);
        const timerElement = document.getElementById('countdownTimer');
        
        countdownInterval = setInterval(() => {
            if (remaining <= 0) {
                clearInterval(countdownInterval);
                if (timerElement) {
                    timerElement.textContent = 'Expirado!';
                    timerElement.style.color = '#dc3545';
                }
                showNotification('⏰ QR Code expirado. Por favor, gere um novo pagamento.', 'warning');
            } else {
                const minutes = Math.floor(remaining / 60);
                const secs = remaining % 60;
                if (timerElement) {
                    timerElement.textContent = `${minutes}:${secs.toString().padStart(2, '0')}`;
                }
                remaining--;
            }
        }, 1000);
    }

    function copyPixCodeSecure() {
        const codeElement = document.getElementById('pixCodeText');
        if (codeElement?.textContent) {
            const code = sanitizeHTML(codeElement.textContent.trim());
            navigator.clipboard.writeText(code)
                .then(() => showNotification('✅ Chave PIX copiada!', 'success'))
                .catch(() => {
                    const textarea = document.createElement('textarea');
                    textarea.value = code;
                    textarea.style.position = 'fixed';
                    textarea.style.opacity = '0';
                    document.body.appendChild(textarea);
                    textarea.select();
                    document.execCommand('copy');
                    document.body.removeChild(textarea);
                    showNotification('✅ Chave PIX copiada!', 'success');
                });
        }
    }

    // ==============================================
    // 🔥 STATUS PREMIUM (SIMPLIFICADO)
    // ==============================================

    async function loadPremiumStatus() {
        try {
            const response = await fetchWithAuth(`${API_URL}/payments/premium-status`);
            if (response?.ok) {
                const data = await response.json();
                const safeData = sanitizeResponse(data);
                
                window.dispatchEvent(new CustomEvent('premiumStatusUpdated', {
                    detail: {
                        isPremium: safeData.is_premium || false,
                        daysLeft: safeData.days_left || 0,
                        hasPromotionalPrice: safeData.promotional_price_locked || false,
                        promotionalPrice: safeData.promotional_price || null,
                        canReceiveDailyCredit: safeData.can_receive_today || false,
                        receivedDailyCreditToday: safeData.received_today || false,
                        creditsBalance: safeData.credits_balance || 0,
                        maxCredits: safeData.max_credits_balance || CONFIG.MAX_CREDITS_BALANCE
                    }
                }));
                
                return safeData;
            }
        } catch (error) {
            console.error('Erro ao carregar status premium:', error);
        }
        return null;
    }

    async function loadSubscriptionStatus() {
        try {
            const response = await fetchWithAuth(`${API_URL}/payments/subscription-status`);
            if (response?.ok) {
                const data = await response.json();
                return sanitizeResponse(data);
            }
        } catch (error) {
            console.error('Erro ao carregar status da assinatura:', error);
        }
        return null;
    }

    async function updatePromotionStatus() {
        try {
            const response = await fetchWithAuth(`${API_URL}/payments/promotion-status`);
            if (response?.ok) {
                const data = await response.json();
                console.log(`📊 Promoção: ${data.remaining_slots}/${data.total_slots} vagas`);
                return data;
            }
        } catch (error) {
            console.warn('Erro ao atualizar status da promoção:', error);
        }
        return null;
    }

    async function receiveDailyCredit() {
        try {
            const response = await fetchWithAuth(`${API_URL}/payments/daily-credit`, { method: 'POST' });
            if (response?.ok) {
                const data = await response.json();
                const safeData = sanitizeResponse(data);
                
                if (safeData.success) {
                    showNotification(`✅ ${safeData.message || 'Crédito recebido com sucesso!'}`, 'success');
                    setTimeout(() => loadPremiumStatus(), 500);
                    setTimeout(() => updateCreditsDisplay(), 1000);
                    return safeData;
                } else {
                    showNotification(safeData.message || 'Erro ao receber crédito', 'warning');
                    return safeData;
                }
            }
        } catch (error) {
            console.error('Erro ao receber crédito:', error);
            showNotification('Erro de conexão. Tente novamente.', 'error');
        }
        return null;
    }

    // ==============================================
    // 🔥 INICIALIZAÇÃO
    // ==============================================

    function isPlansPage() {
        return document.getElementById('plansContainer') !== null;
    }

    function isDashboardPage() {
        return document.getElementById('premiumStatusContainer') !== null;
    }

    document.addEventListener('DOMContentLoaded', function() {
        console.log('📄 DOMContentLoaded - Inicializando payment.js v2.5');
        
        if (isPlansPage()) {
            setTimeout(() => {
                loadPlans();
                console.log('✅ payment.js - PÁGINA DE PLANOS');
                console.log(`💰 Preço Fundador: R$ ${CONFIG.PROMOTIONAL_PRICE}`);
                console.log(`🎯 Total de vagas: ${CONFIG.TOTAL_PROMOTIONAL_SLOTS}`);
            }, 200);
        }
        
        if (isDashboardPage()) {
            setTimeout(() => {
                loadPremiumStatus();
                console.log('✅ payment.js - Status Premium no Dashboard');
            }, 500);
        }
        
        // Atualiza créditos periodicamente
        updateCreditsDisplay();
        setInterval(updateCreditsDisplay, 30000);
        
        // Dispara evento de carregamento
        window.dispatchEvent(new CustomEvent('paymentReady', {
            detail: { loaded: true, version: '2.5' }
        }));
    });

    // ==============================================
    // 🔥 EXPOSIÇÃO DE FUNÇÕES GLOBAIS
    // ==============================================

    window.loadPlans = loadPlans;
    window.openCpfModal = openCpfModal;
    window.proceedWithCpf = proceedWithCpf;
    window.showPixModalSecure = showPixModalSecure;
    window.copyPixCodeSecure = copyPixCodeSecure;
    window.updateCreditsDisplay = updateCreditsDisplay;
    window.formatCreditsDisplay = formatCreditsDisplay;
    window.showNotification = showNotification;
    window.getCredits = getCredits;
    window.isPremium = isPremium;
    window.loadSubscriptionStatus = loadSubscriptionStatus;
    window.loadPremiumStatus = loadPremiumStatus;
    window.updatePromotionStatus = updatePromotionStatus;
    window.receiveDailyCredit = receiveDailyCredit;
    window.sanitizeHTML = sanitizeHTML;
    window.sanitizeCPF = sanitizeCPF;
    window.validateCPF = validateCPF;

    console.log('✅ payment.js v2.5 carregado com sucesso!');
    console.log('🔒 Proteção antifraude: CPF obrigatório e validado');
    console.log(`💰 Preço Fundador: R$ ${CONFIG.PROMOTIONAL_PRICE} (vitalício)`);
    console.log(`🎯 Total de vagas: ${CONFIG.TOTAL_PROMOTIONAL_SLOTS}`);
    console.log('📡 Eventos: paymentReady, creditsUpdated, premiumStatusUpdated');

})(); // <-- FECHA A IIFE