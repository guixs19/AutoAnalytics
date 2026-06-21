// payment.js - VERSÃO ATUALIZADA v2.1
// ==============================================
// SINCRONIZADO COM:
// - payment_routes.py (preço fundador vitalício, webhook)
// - crud.py (MAX_CREDITS_PREMIUM = 3, INITIAL_FREE_CREDITS = 3)
// - daily_credits_service.py (crédito diário premium)
// - credits_consumer.py (consumo de créditos)
// - auth.js (window.appAuth)
// - app.js (estado global, eventos)
// ==============================================

// ==============================================
// 🔒 CONFIGURAÇÕES GLOBAIS (SINCRONIZADAS COM BACKEND)
// ==============================================

// 🔥 Constantes sincronizadas com backend/crud.py
const MAX_CREDITS_BALANCE = 3;
const INITIAL_FREE_CREDITS = 3;
const PIX_EXPIRY_MINUTES = 30;
const PROMOTIONAL_PRICE = 97.00;
const REGULAR_PRICE = 149.90;
const TOTAL_PROMOTIONAL_SLOTS = 100;
const DAYS_PREMIUM = 30;

// 🔥 API_URL dinâmica (funciona em localhost e produção)
const API_URL = (() => {
    const isLocalhost = window.location.hostname === 'localhost' || 
                        window.location.hostname === '127.0.0.1';
    
    if (isLocalhost) {
        return 'http://localhost:8000/api';
    }
    
    return '/api';
})();

console.log(`🌐 Payment.js API_URL: ${API_URL}`);
console.log(`📊 MAX_CREDITS_BALANCE: ${MAX_CREDITS_BALANCE}`);
console.log(`💰 Preço Fundador: R$ ${PROMOTIONAL_PRICE}`);
console.log(`💰 Preço Cheio: R$ ${REGULAR_PRICE}`);

// 🔥 Flag para indicar que payment.js carregou
window.paymentLoaded = true;

// ==============================================
// 🔒 FUNÇÕES DE SEGURANÇA CONTRA XSS (CAMADA MÚLTIPLA)
// ==============================================

/**
 * Sanitização de HTML - Remove tags e scripts maliciosos
 * Usa múltiplas camadas de proteção
 */
function sanitizeHTML(str) {
    if (!str) return '';
    if (typeof str !== 'string') str = String(str);
    
    // 1ª camada: Remover tags HTML
    let clean = str.replace(/<[^>]*>/g, '');
    
    // 2ª camada: Escapar caracteres especiais
    const escapeMap = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
        '`': '&#96;',
        '/': '&#47;',
        '=': '&#61;',
        '(': '&#40;',
        ')': '&#41;',
        ';': '&#59;'
    };
    
    clean = clean.replace(/[&<>"'`/=();]/g, function(match) {
        return escapeMap[match] || match;
    });
    
    // 3ª camada: Remover padrões de script
    clean = clean.replace(/javascript:/gi, '');
    clean = clean.replace(/on\w+\s*=/gi, '');
    clean = clean.replace(/eval\s*\(/gi, '');
    clean = clean.replace(/alert\s*\(/gi, '');
    clean = clean.replace(/confirm\s*\(/gi, '');
    clean = clean.replace(/prompt\s*\(/gi, '');
    
    // 4ª camada: Limitar tamanho (evita DoS)
    clean = clean.slice(0, 5000);
    
    return clean;
}

/**
 * Sanitização de números - Garante que é um número válido
 */
function sanitizeNumber(value, defaultValue = 0) {
    if (value === undefined || value === null) return defaultValue;
    const num = parseFloat(String(value).replace(/[^0-9.,-]/g, '').replace(',', '.'));
    return isNaN(num) ? defaultValue : num;
}

/**
 * Sanitização de CPF - Remove caracteres não numéricos
 */
function sanitizeCPF(cpf) {
    if (!cpf) return '';
    return String(cpf).replace(/\D/g, '');
}

/**
 * Validação de CPF (completa)
 */
function validateCPF(cpf) {
    const clean = sanitizeCPF(cpf);
    
    if (clean.length !== 11) return false;
    
    // Eliminar CPFs inválidos conhecidos
    const invalidCPFs = [
        '00000000000', '11111111111', '22222222222',
        '33333333333', '44444444444', '55555555555',
        '66666666666', '77777777777', '88888888888',
        '99999999999'
    ];
    if (invalidCPFs.includes(clean)) return false;
    
    // Validação do dígito verificador
    let sum = 0;
    let remainder;
    
    for (let i = 1; i <= 9; i++) {
        sum += parseInt(clean.substring(i - 1, i)) * (11 - i);
    }
    remainder = (sum * 10) % 11;
    if (remainder === 10 || remainder === 11) remainder = 0;
    if (remainder !== parseInt(clean.substring(9, 10))) return false;
    
    sum = 0;
    for (let i = 1; i <= 10; i++) {
        sum += parseInt(clean.substring(i - 1, i)) * (12 - i);
    }
    remainder = (sum * 10) % 11;
    if (remainder === 10 || remainder === 11) remainder = 0;
    if (remainder !== parseInt(clean.substring(10, 11))) return false;
    
    return true;
}

/**
 * Sanitização de objeto completo (recursivo)
 */
function sanitizeObject(obj) {
    if (obj === null || obj === undefined) return obj;
    if (typeof obj === 'string') return sanitizeHTML(obj);
    if (typeof obj === 'number') return sanitizeNumber(obj);
    if (Array.isArray(obj)) {
        return obj.map(item => sanitizeObject(item));
    }
    if (typeof obj === 'object') {
        const result = {};
        for (const [key, value] of Object.entries(obj)) {
            const safeKey = sanitizeHTML(key);
            result[safeKey] = sanitizeObject(value);
        }
        return result;
    }
    return obj;
}

/**
 * Sanitização de resposta da API (antes de exibir)
 */
function sanitizeResponse(data) {
    return sanitizeObject(data);
}

// ==============================================
// 🔒 FUNÇÕES DE AUTENTICAÇÃO (usando window.appAuth)
// ==============================================

function isAdmin() {
    try {
        return window.appAuth ? window.appAuth.isAdmin() : false;
    } catch {
        return false;
    }
}

function getCredits() {
    try {
        return window.appAuth ? window.appAuth.getCredits() : 0;
    } catch {
        return 0;
    }
}

function getCreditsDisplay() {
    try {
        return window.appAuth ? window.appAuth.getCreditsDisplay() : '0';
    } catch {
        return '0';
    }
}

function isPremium() {
    try {
        return window.appAuth ? window.appAuth.isPremium() : false;
    } catch {
        return false;
    }
}

function formatCreditsDisplay(credits, isPremiumUser = false) {
    const safeCredits = sanitizeNumber(credits, 0);
    
    if (isAdmin()) return '∞';
    if (isPremiumUser) {
        return `${safeCredits}/${MAX_CREDITS_BALANCE}`;
    }
    return safeCredits.toString();
}

// ==============================================
// 🔥 REQUISIÇÕES AUTENTICADAS (USANDO appAuth)
// ==============================================

/**
 * 🔥 CORRIGIDO: Usa window.appAuth.fetchWithAuth como fonte única
 */
async function fetchWithAuth(url, options = {}) {
    // ✅ Usar window.appAuth se disponível (fonte única)
    if (window.appAuth && window.appAuth.fetchWithAuth) {
        return window.appAuth.fetchWithAuth(url, options);
    }
    
    // 🔥 Fallback: Usar token do localStorage (apenas para compatibilidade)
    console.warn('⚠️ appAuth não disponível, usando fallback fetchWithAuth');
    
    const token = localStorage.getItem('access_token');
    
    const headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        ...options.headers
    };
    
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    
    try {
        const response = await fetch(url, { ...options, headers });
        
        // Tratar token expirado
        if (response.status === 401) {
            const refreshToken = localStorage.getItem('refresh_token');
            if (refreshToken) {
                try {
                    const refreshResponse = await fetch(`${API_URL}/auth/refresh`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ refresh_token: refreshToken })
                    });
                    
                    if (refreshResponse.ok) {
                        const refreshData = await refreshResponse.json();
                        localStorage.setItem('access_token', refreshData.access_token);
                        if (refreshData.refresh_token) {
                            localStorage.setItem('refresh_token', refreshData.refresh_token);
                        }
                        headers['Authorization'] = `Bearer ${refreshData.access_token}`;
                        return fetch(url, { ...options, headers });
                    }
                } catch (refreshError) {
                    console.error('Erro ao renovar token:', refreshError);
                }
            }
            
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
// 🔥 NOTIFICAÇÕES SEGURAS
// ==============================================

function showNotification(message, type = 'info') {
    const safeMessage = sanitizeHTML(message);
    
    // ✅ Usar appAuth se disponível
    if (window.appAuth && window.appAuth.showNotification) {
        return window.appAuth.showNotification(safeMessage, type);
    }
    
    if (window.toastr) {
        const options = {
            closeButton: true,
            progressBar: true,
            positionClass: 'toast-top-right',
            timeOut: 5000,
            escapeHtml: true
        };
        
        switch (type) {
            case 'success':
                toastr.success(safeMessage, '✅ Sucesso!', options);
                break;
            case 'error':
                toastr.error(safeMessage, '❌ Erro', options);
                break;
            case 'warning':
                toastr.warning(safeMessage, '⚠️ Atenção', options);
                break;
            default:
                toastr.info(safeMessage, 'ℹ️ Informação', options);
        }
    } else {
        console.log(`[${type}] ${safeMessage}`);
    }
}

// ==============================================
// 🔥 ATUALIZAR CRÉDITOS (COM EVENTO)
// ==============================================

/**
 * 🔥 CORRIGIDO: Atualiza créditos e dispara evento para app.js
 */
async function updateCreditsDisplay() {
    try {
        let credits = getCredits();
        let isPremiumUser = isPremium();
        
        // Se appAuth tem loadUserCredits, usar para dados atualizados
        if (window.appAuth && window.appAuth.loadUserCredits) {
            await window.appAuth.loadUserCredits();
            credits = window.appAuth.getCredits ? window.appAuth.getCredits() : 0;
            isPremiumUser = window.appAuth.isPremium ? window.appAuth.isPremium() : false;
        }
        
        const displayText = formatCreditsDisplay(credits, isPremiumUser);
        
        // Atualizar elementos DOM
        const selectors = [
            '.credits-display', '.user-credits', 
            '#creditsDisplay', '#creditsCount', '#uploadCredits',
            '.credits-badge span', '.credits-value'
        ];
        
        document.querySelectorAll(selectors.join(',')).forEach(el => {
            if (el) el.textContent = displayText;
        });
        
        // 🔥 DISPARAR EVENTO PARA APP.JS
        window.dispatchEvent(new CustomEvent('creditsUpdated', {
            detail: {
                credits: credits,
                display: displayText,
                maxCredits: MAX_CREDITS_BALANCE,
                isPremium: isPremiumUser
            }
        }));
        
        return true;
    } catch (error) {
        console.error('Erro ao atualizar créditos:', error);
        return false;
    }
}

// ==============================================
// 🔥 CARREGAMENTO DE PLANOS (COM PREÇO FUNDADOR VITALÍCIO)
// ==============================================

async function loadPlans() {
    try {
        const response = await fetch(`${API_URL}/payments/plans`);
        if (response.ok) {
            const data = await response.json();
            const safeData = sanitizeResponse(data);
            renderBronzePlan(safeData.plans, safeData);
        } else {
            console.error('Erro ao carregar planos:', response.status);
            showNotification('Erro ao carregar planos. Tente novamente.', 'error');
        }
    } catch (error) {
        console.error('Erro ao carregar planos:', error);
        showNotification('Erro de conexão. Tente novamente.', 'error');
    }
}

/**
 * 🔥 RENDERIZAÇÃO DO PLANO BRONZE COM SISTEMA FUNDADOR VITALÍCIO
 */
async function renderBronzePlan(plans, fullData = null) {
    const container = document.getElementById('plansContainer');
    if (!container) return;
    
    if (isAdmin()) {
        container.innerHTML = `
            <div class="col-lg-8 mx-auto">
                <div class="admin-message">
                    <i class="fas fa-crown"></i>
                    <h2 class="h3 mb-3">👑 Você é Administrador</h2>
                    <p class="lead mb-4">Como admin, você tem acesso ilimitado a todas as funcionalidades.</p>
                    <a href="/dashboard" class="btn btn-light btn-lg mt-3">
                        <i class="fas fa-arrow-left me-2"></i> Voltar ao Dashboard
                    </a>
                </div>
            </div>
        `;
        return;
    }
    
    const plan = plans?.['premium_mensal'];
    if (!plan) {
        container.innerHTML = '<div class="text-center text-danger">Erro ao carregar plano. Tente novamente.</div>';
        return;
    }
    
    // 🔥 BUSCAR STATUS REAL DA PROMOÇÃO NO BACKEND
    let promoData = {
        remaining_slots: TOTAL_PROMOTIONAL_SLOTS,
        total_slots: TOTAL_PROMOTIONAL_SLOTS,
        promotional_price: PROMOTIONAL_PRICE,
        regular_price: REGULAR_PRICE,
        current_price: PROMOTIONAL_PRICE,
        is_active: true,
        user_locked_price: null,
        is_vitalicio: true
    };
    
    try {
        const promoResponse = await fetchWithAuth(`${API_URL}/payments/promotion-status`);
        if (promoResponse && promoResponse.ok) {
            const rawData = await promoResponse.json();
            promoData = sanitizeResponse(rawData);
        }
    } catch (error) {
        console.warn('Erro ao buscar status da promoção:', error);
    }
    
    const vagasRestantes = sanitizeNumber(promoData.remaining_slots, TOTAL_PROMOTIONAL_SLOTS);
    const totalVagas = sanitizeNumber(promoData.total_slots, TOTAL_PROMOTIONAL_SLOTS);
    const precoPromocional = sanitizeNumber(promoData.promotional_price, PROMOTIONAL_PRICE);
    const precoRegular = sanitizeNumber(promoData.regular_price, REGULAR_PRICE);
    const isUserLocked = promoData.user_locked_price !== null && promoData.user_locked_price !== undefined;
    const isSoldOut = vagasRestantes <= 0;
    const precoAtual = isSoldOut ? precoRegular : precoPromocional;
    const economia = precoRegular - precoPromocional;
    const vagasUsadas = totalVagas - vagasRestantes;
    const percentual = (vagasUsadas / totalVagas) * 100;
    const isUrgent = vagasRestantes <= 20 && vagasRestantes > 0;
    
    // 🔥 MENSAGEM PERSONALIZADA PARA QUEM JÁ TEM PREÇO VITALÍCIO
    let precoMessage = '';
    if (isUserLocked) {
        precoMessage = `
            <div class="vitalicio-badge">
                <i class="fas fa-gem me-2"></i>
                PREÇO VITALÍCIO GARANTIDO!
                <small>R$ ${precoAtual.toFixed(2).replace('.', ',')} para sempre</small>
            </div>
        `;
    }
    
    const html = `
        <div class="col-lg-8 mx-auto">
            <div class="bronze-card" data-aos="fade-up" data-aos-duration="800">
                <div class="bronze-badge">
                    <i class="fas fa-fire"></i> 
                    ${isSoldOut ? 'PROMOÇÃO ENCERRADA' : (isUserLocked ? '🔥 SEU PREÇO VITALÍCIO' : '🔥 PROMOÇÃO FUNDADOR')}
                </div>
                
                ${precoMessage}
                
                <div class="bronze-title">
                    <h2>
                        <i class="fas fa-crown me-2"></i>
                        Plano Bronze
                    </h2>
                    <p><i class="fas fa-check-circle me-1"></i> A escolha dos profissionais</p>
                </div>
                
                <div class="price-container">
                    ${!isSoldOut && !isUserLocked ? `
                        <span class="old-price">De R$ ${precoRegular.toFixed(2).replace('.', ',')}</span>
                    ` : ''}
                    <div class="price-tag" id="planoPreco">
                        R$ ${precoAtual.toFixed(2).replace('.', ',')}<small>/mês</small>
                    </div>
                    ${!isSoldOut && !isUserLocked ? `
                        <span class="economy-badge">🔥 ECONOMIZE R$ ${economia.toFixed(2).replace('.', ',')} 🔥</span>
                    ` : ''}
                    ${isUserLocked ? `
                        <span class="economy-badge" style="background: linear-gradient(135deg, #28a745, #20c997);">
                            <i class="fas fa-lock me-1"></i> PREÇO BLOQUEADO - VITALÍCIO
                        </span>
                    ` : ''}
                    ${isSoldOut && !isUserLocked ? `
                        <span class="economy-badge" style="background: linear-gradient(135deg, #dc3545, #c0392b);">
                            <i class="fas fa-exclamation-triangle me-1"></i> PROMOÇÃO ESGOTADA
                        </span>
                    ` : ''}
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
                    <div class="vagas-progress">
                        <div class="vagas-progress-bar" style="width: ${Math.min(100, percentual)}%"></div>
                    </div>
                    ${isUrgent ? `
                        <div class="mt-2 text-center">
                            <strong style="color: #f5a623;">🔥 URGENTE! ÚLTIMAS ${vagasRestantes} VAGAS! 🔥</strong>
                            <br><small>Garanta o preço de fundador R$ ${precoPromocional.toFixed(2).replace('.', ',')} (vitalício)</small>
                        </div>
                    ` : `
                        <div class="mt-2 text-center small text-muted">
                            Apenas as primeiras ${totalVagas} pessoas pagam R$ ${precoPromocional.toFixed(2).replace('.', ',')} (vitalício)
                        </div>
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
                    <div class="mt-2 text-center small text-success">
                        <i class="fas fa-check-circle me-1"></i> Você comprou na promoção e teve o preço bloqueado!
                    </div>
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
                    <div class="mt-2 text-center small text-danger">
                        As ${totalVagas} vagas promocionais já foram preenchidas. Valor: R$ ${precoRegular.toFixed(2).replace('.', ',')}
                    </div>
                </div>
                ` : ''}
                
                <div class="my-3">
                    <div class="highlight-title">
                        <i class="fas fa-star me-2"></i> O que você recebe:
                    </div>
                    
                    <div class="bronze-feature">
                        <i class="fas fa-brain"></i>
                        <span><strong>IA Avançada (Gemini + Scikit-Learn)</strong> - Análises preditivas</span>
                    </div>
                    <div class="bronze-feature">
                        <i class="fas fa-file-alt"></i>
                        <span><strong>Relatórios Completos em PDF</strong> - Exporte análises</span>
                    </div>
                    <div class="bronze-feature">
                        <i class="fas fa-chart-line"></i>
                        <span><strong>Dashboard Interativo</strong> - Métricas em tempo real</span>
                    </div>
                    <div class="bronze-feature">
                        <i class="fas fa-calendar-day"></i>
                        <span><strong>1 crédito novo por dia</strong> - Para novas análises</span>
                    </div>
                    <div class="bronze-feature">
                        <i class="fas fa-layer-group"></i>
                        <span><strong>Até ${MAX_CREDITS_BALANCE} créditos acumulados</strong> - Máximo de ${MAX_CREDITS_BALANCE}</span>
                    </div>
                    <div class="bronze-feature">
                        <i class="fas fa-chart-pie"></i>
                        <span><strong>Gráficos automáticos</strong> - Visualização inteligente</span>
                    </div>
                    <div class="bronze-feature">
                        <i class="fas fa-download"></i>
                        <span><strong>Exportação CSV/Excel</strong> - Seus dados sempre disponíveis</span>
                    </div>
                    <div class="bronze-feature">
                        <i class="fas fa-headset"></i>
                        <span><strong>Suporte Prioritário 24/7</strong> - Atendimento exclusivo</span>
                    </div>
                </div>
                
                <div class="plan-info">
                    <div class="row text-center">
                        <div class="col-4">
                            <i class="fas fa-coins fa-lg"></i>
                            <div class="small fw-bold mt-1">${DAYS_PREMIUM} Créditos</div>
                            <div class="small text-muted">Total do plano</div>
                        </div>
                        <div class="col-4">
                            <i class="fas fa-clock fa-lg"></i>
                            <div class="small fw-bold mt-1">${DAYS_PREMIUM} Dias</div>
                            <div class="small text-muted">Duração</div>
                        </div>
                        <div class="col-4">
                            <i class="fas fa-tachometer-alt fa-lg"></i>
                            <div class="small fw-bold mt-1">${MAX_CREDITS_BALANCE} Máx.</div>
                            <div class="small text-muted">Créditos acumulados</div>
                        </div>
                    </div>
                </div>
                
                <div class="limit-warning">
                    <i class="fas fa-info-circle"></i>
                    <small>⚠️ Limite máximo de <strong>${MAX_CREDITS_BALANCE} créditos acumulados</strong>. Use-os para continuar recebendo novos créditos diários!</small>
                </div>
                
                <div class="d-grid gap-3 mt-4">
                    <button class="btn btn-bronze btn-lg" id="buyButton" onclick="window.openCpfModal('premium_mensal')">
                        <i class="fas fa-bolt me-2"></i>
                        ${isUserLocked ? 'RENOVAR MEU PLANO' : (isSoldOut ? `COMPRAR POR R$ ${precoAtual.toFixed(2).replace('.', ',')}` : `🔥 GARANTIR PREÇO FUNDADOR R$ ${precoAtual.toFixed(2).replace('.', ',')}`)}
                        <small class="d-block fs-10">${isUserLocked ? 'Pagamento vitalício garantido' : 'Pagamento seguro via PIX'}</small>
                    </button>
                </div>
                
                <div class="security-seals">
                    <span class="badge me-2">
                        <i class="fas fa-lock"></i> Pagamento 100% Seguro
                    </span>
                    <span class="badge me-2">
                        <i class="fas fa-undo-alt"></i> 7 Dias de Garantia
                    </span>
                    <span class="badge">
                        <i class="fas fa-clock"></i> Ativação Imediata
                    </span>
                </div>
                
                <p class="text-center small mt-4 mb-0" style="color: rgba(255,255,255,0.6);">
                    <i class="fas fa-check-circle text-warning me-1"></i>
                    Após o pagamento, você receberá 1 crédito por dia durante ${DAYS_PREMIUM} dias
                </p>
            </div>
        </div>
    `;
    
    container.innerHTML = html;
}

// ==============================================
// 🔥 MODAL DE CPF (ANTIFRAUDE - SEGURO)
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
        cpfModal.innerHTML = `
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content" style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border: 1px solid #f5a623;">
                    <div class="modal-header border-0">
                        <h5 class="modal-title" style="color: #f5a623;">
                            <i class="fas fa-id-card me-2"></i>Confirme seu CPF
                        </h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Fechar"></button>
                    </div>
                    <div class="modal-body">
                        <p class="text-white-50 mb-3">
                            <i class="fas fa-shield-alt me-2"></i>
                            O CPF é obrigatório para geração do PIX e protege sua compra contra fraudes.
                        </p>
                        <div class="mb-3">
                            <label class="form-label text-white">CPF</label>
                            <input type="text" 
                                   class="form-control form-control-lg" 
                                   id="cpfInput" 
                                   placeholder="000.000.000-00"
                                   maxlength="14"
                                   autocomplete="off"
                                   style="background: rgba(255,255,255,0.1); border-color: #f5a623; color: white;">
                            <div class="form-text text-white-50">Apenas números (11 dígitos)</div>
                        </div>
                        <div id="cpfError" class="alert alert-danger d-none" role="alert"></div>
                    </div>
                    <div class="modal-footer border-0">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
                        <button type="button" class="btn btn-bronze" id="confirmCpfBtn" onclick="window.proceedWithCpf('${sanitizeHTML(planId)}')">
                            <i class="fas fa-arrow-right me-2"></i>Continuar para PIX
                        </button>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(cpfModal);
        
        // 🔥 MÁSCARA DE CPF SEGURA
        const cpfInput = document.getElementById('cpfInput');
        if (cpfInput) {
            cpfInput.addEventListener('input', function(e) {
                let value = e.target.value.replace(/\D/g, '');
                if (value.length > 11) value = value.slice(0, 11);
                
                // Aplicar máscara
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
    }
    
    const modal = new bootstrap.Modal(cpfModal);
    modal.show();
}

/**
 * 🔥 PROCESSAR CPF COM VALIDAÇÃO COMPLETA
 */
async function proceedWithCpf(planId) {
    const cpfInput = document.getElementById('cpfInput');
    const cpfError = document.getElementById('cpfError');
    
    if (!cpfInput) return;
    
    const cpfLimpo = sanitizeCPF(cpfInput.value);
    
    // 🔥 VALIDAÇÃO COMPLETA DO CPF
    if (!validateCPF(cpfLimpo)) {
        if (cpfError) {
            cpfError.textContent = '❌ CPF inválido. Digite um CPF válido com 11 dígitos.';
            cpfError.classList.remove('d-none');
        }
        return;
    }
    
    // Fechar modal
    const cpfModal = bootstrap.Modal.getInstance(document.getElementById('cpfModal'));
    if (cpfModal) cpfModal.hide();
    
    // 🔥 Prosseguir com pagamento
    await selectPlan(planId, 'pix', cpfLimpo);
}

// ==============================================
// 🔥 SELEÇÃO E PAGAMENTO (COM PREÇO FUNDADOR VITALÍCIO)
// ==============================================

async function selectPlan(planId, method, cpf = null) {
    if (isAdmin()) {
        showNotification('👑 Como administrador, você tem acesso ilimitado.', 'info');
        return;
    }
    
    const btn = document.getElementById('buyButton');
    let originalText = '';
    
    if (btn) {
        originalText = sanitizeHTML(btn.innerHTML);
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i> Processando...';
        
        // Timeout de segurança
        setTimeout(() => {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        }, 30000);
    }
    
    // 🔥 CONSTRUIR CORPO DA REQUISIÇÃO (SEGURO)
    const requestBody = { plan_id: sanitizeHTML(planId) };
    
    if (cpf) {
        const cpfLimpo = sanitizeCPF(cpf);
        if (validateCPF(cpfLimpo)) {
            requestBody.cpf = cpfLimpo;
        } else {
            showNotification('❌ CPF inválido. Por favor, informe um CPF válido.', 'error');
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
            return;
        }
    }
    
    try {
        const response = await fetchWithAuth(`${API_URL}/payments/create-${method}`, {
            method: 'POST',
            body: JSON.stringify(requestBody)
        });
        
        if (response && response.ok) {
            const data = await response.json();
            const safeData = sanitizeResponse(data);
            
            if (safeData.requires_cpf) {
                showNotification(sanitizeHTML(safeData.error || 'CPF é obrigatório para gerar o pagamento.'), 'warning');
                openCpfModal(planId);
                return;
            }
            
            if (method === 'pix') {
                if (safeData.payment_id) {
                    showPixModalSecure(safeData.payment_id, safeData);
                } else if (safeData.checkout_url) {
                    // URL segura (sanitizada)
                    const safeUrl = sanitizeHTML(safeData.checkout_url);
                    window.location.href = safeUrl;
                } else {
                    showNotification('Pagamento iniciado. Verifique o status no dashboard.', 'info');
                    setTimeout(() => {
                        window.location.href = '/dashboard';
                    }, 2000);
                }
            }
        } else if (response) {
            const error = await response.json();
            const safeError = sanitizeResponse(error);
            const errorMsg = safeError.detail || safeError.message || 'Erro ao criar pagamento';
            
            if (errorMsg.toLowerCase().includes('cpf')) {
                showNotification('⚠️ CPF obrigatório. Por favor, informe seu CPF.', 'warning');
                openCpfModal(planId);
            } else if (errorMsg.toLowerCase().includes('token') || errorMsg.toLowerCase().includes('mercadopago')) {
                showNotification('⚠️ Erro no gateway de pagamento. Tente novamente em instantes.', 'error');
            } else {
                showNotification(`❌ ${sanitizeHTML(errorMsg)}`, 'error');
            }
        } else {
            showNotification('❌ Erro de conexão. Tente novamente.', 'error');
        }
    } catch (error) {
        console.error('Erro ao criar pagamento:', error);
        showNotification(`❌ Erro ao processar pagamento: ${sanitizeHTML(error.message || 'Tente novamente')}`, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    }
}

// ==============================================
// 🔥 MODAL PIX SEGURO (COM SANITIZAÇÃO)
// ==============================================

async function showPixModalSecure(paymentId, paymentData) {
    const modalContent = document.getElementById('pixContent');
    if (!modalContent) return;
    
    // Sanitizar dados
    const safePaymentData = sanitizeResponse(paymentData);
    const safePaymentId = sanitizeNumber(paymentId);
    
    modalContent.innerHTML = `
        <div class="text-center py-4">
            <div class="spinner-border text-primary mb-3" role="status">
                <span class="visually-hidden">Carregando...</span>
            </div>
            <p>Carregando informações de pagamento...</p>
        </div>
    `;
    
    const modalElement = document.getElementById('pixModal');
    const modal = new bootstrap.Modal(modalElement);
    modal.show();
    
    try {
        const response = await fetchWithAuth(`${API_URL}/payments/pix-qrcode/${safePaymentId}`);
        
        if (response && response.ok) {
            const qrData = await response.json();
            const safeQrData = sanitizeResponse(qrData);
            
            if (safeQrData.success && safeQrData.qr_code_base64) {
                const maxCredits = sanitizeNumber(safeQrData.max_credits_balance, MAX_CREDITS_BALANCE);
                const wasPromotional = safePaymentData.price_type === 'promotional' || safePaymentData.was_promotional;
                const expiresInSeconds = sanitizeNumber(safeQrData.expires_in, PIX_EXPIRY_MINUTES * 60);
                const expiresMinutes = Math.floor(expiresInSeconds / 60);
                const amount = sanitizeNumber(safePaymentData.amount, PROMOTIONAL_PRICE);
                
                modalContent.innerHTML = `
                    ${wasPromotional ? `
                        <div class="alert alert-success mb-3 text-center">
                            <i class="fas fa-gem me-2"></i>
                            <strong>🎉 VOCÊ GARANTIU O PREÇO FUNDADOR!</strong><br>
                            <small>R$ ${amount.toFixed(2).replace('.', ',')} - Preço bloqueado VITALÍCIO!</small>
                        </div>
                    ` : ''}
                    
                    <h6 class="mb-3 text-center">Escaneie o QR Code com seu banco</h6>
                    
                    <div class="text-center mb-3">
                        <img src="data:image/png;base64,${sanitizeHTML(safeQrData.qr_code_base64)}" 
                             alt="QR Code PIX"
                             class="img-fluid" style="max-width: 200px; border-radius: 12px;">
                    </div>
                    
                    <div class="bg-light p-3 rounded-3 mb-3" style="word-break: break-all; background: rgba(255,255,255,0.1) !important;">
                        <code id="pixCodeText" class="small" style="color: #f5a623;">${sanitizeHTML(safeQrData.qr_code || 'Código disponível no app do banco')}</code>
                    </div>
                    
                    <button class="btn btn-outline-primary w-100 mb-3" onclick="window.copyPixCodeSecure()">
                        <i class="fas fa-copy me-2"></i>
                        Copiar código PIX
                    </button>
                    
                    <div class="alert alert-info small">
                        <i class="fas fa-info-circle me-2"></i>
                        <strong>Informações do pagamento:</strong><br>
                        Valor: R$ ${amount.toFixed(2).replace('.', ',')}<br>
                        ${wasPromotional ? '<span class="text-success">✅ Você está comprando na promoção! Preço R$ 97,00 garantido para sempre.</span><br>' : ''}
                        Créditos: ${sanitizeNumber(safePaymentData.credits, DAYS_PREMIUM)}
                        ${safePaymentData.plan_type === 'daily_credits' ? `<br>⚠️ <strong>Plano Premium:</strong> máximo de ${maxCredits} créditos acumulados por vez.` : ''}
                        <br><br>
                        ⏰ Este QR Code expira em <strong id="countdownTimer">${expiresMinutes}:00</strong> minutos.<br>
                        Após o pagamento, os créditos são adicionados automaticamente.
                    </div>
                    
                    <div id="paymentStatus"></div>
                `;
                
                startCountdown(expiresInSeconds);
            } else {
                modalContent.innerHTML = `
                    <div class="alert alert-info text-center">
                        <i class="fas fa-info-circle fa-2x mb-2 d-block"></i>
                        <p>Pagamento registrado! O QR Code será exibido em breve.</p>
                        <p class="small text-muted">Status: ${sanitizeHTML(safeQrData.status || 'pendente')}</p>
                        <button class="btn btn-outline-primary mt-3" onclick="location.reload()">
                            <i class="fas fa-sync-alt me-2"></i>
                            Atualizar
                        </button>
                    </div>
                `;
            }
            
            startPaymentPollingSecure(safePaymentId);
        } else {
            modalContent.innerHTML = `
                <div class="alert alert-danger text-center">
                    <i class="fas fa-exclamation-triangle fa-2x mb-2 d-block"></i>
                    <p>Erro ao carregar informações de pagamento.</p>
                    <p class="small text-muted">Tente novamente ou verifique no dashboard.</p>
                    <button class="btn btn-outline-danger mt-2" onclick="location.reload()">
                        <i class="fas fa-redo me-2"></i>
                        Tentar novamente
                    </button>
                </div>
            `;
        }
    } catch (error) {
        console.error('Erro ao buscar QR Code:', error);
        modalContent.innerHTML = `
            <div class="alert alert-danger text-center">
                <i class="fas fa-wifi fa-2x mb-2 d-block"></i>
                <p>Erro de conexão. Tente novamente mais tarde.</p>
                <p class="small text-muted">${sanitizeHTML(error.message || 'Erro desconhecido')}</p>
            </div>
        `;
    }
}

// ==============================================
// 🔥 COUNTDOWN E POLLING SEGUROS
// ==============================================

let countdownInterval = null;

function startCountdown(seconds) {
    if (countdownInterval) clearInterval(countdownInterval);
    
    let remaining = sanitizeNumber(seconds, PIX_EXPIRY_MINUTES * 60);
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

/**
 * 🔥 COPIA CÓDIGO PIX COM SEGURANÇA
 */
function copyPixCodeSecure() {
    const codeElement = document.getElementById('pixCodeText');
    if (codeElement && codeElement.textContent) {
        const code = sanitizeHTML(codeElement.textContent.trim());
        navigator.clipboard.writeText(code)
            .then(() => showNotification('✅ Código PIX copiado!', 'success'))
            .catch(() => {
                const textarea = document.createElement('textarea');
                textarea.value = code;
                textarea.style.position = 'fixed';
                textarea.style.opacity = '0';
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand('copy');
                document.body.removeChild(textarea);
                showNotification('✅ Código PIX copiado!', 'success');
            });
    }
}

let paymentPollingInterval = null;

function startPaymentPollingSecure(paymentId) {
    if (paymentPollingInterval) clearInterval(paymentPollingInterval);
    
    let attempts = 0;
    const maxAttempts = 60;
    const safePaymentId = sanitizeNumber(paymentId);
    
    paymentPollingInterval = setInterval(async () => {
        attempts++;
        
        const modalElement = document.getElementById('pixModal');
        const isModalOpen = modalElement && modalElement.classList.contains('show');
        
        if (!isModalOpen && attempts > 10) {
            clearInterval(paymentPollingInterval);
            paymentPollingInterval = null;
            return;
        }
        
        if (attempts > maxAttempts) {
            clearInterval(paymentPollingInterval);
            paymentPollingInterval = null;
            
            const statusDiv = document.getElementById('paymentStatus');
            if (statusDiv) {
                statusDiv.innerHTML = `
                    <div class="alert alert-warning text-center">
                        <i class="fas fa-clock me-2"></i>
                        <strong>Pagamento em processamento</strong><br>
                        O pagamento está sendo processado. Você receberá os créditos em breve.
                        <hr>
                        <a href="/dashboard" class="alert-link">Ir para o Dashboard</a>
                        <button class="btn btn-sm btn-outline-warning ms-2" onclick="location.reload()">
                            <i class="fas fa-sync-alt"></i> Verificar agora
                        </button>
                    </div>
                `;
            }
            return;
        }
        
        try {
            const response = await fetchWithAuth(`${API_URL}/payments/status/${safePaymentId}`);
            if (response && response.ok) {
                const data = await response.json();
                const safeData = sanitizeResponse(data);
                
                if (safeData.payment && safeData.payment.status === 'approved') {
                    clearInterval(paymentPollingInterval);
                    paymentPollingInterval = null;
                    
                    if (countdownInterval) {
                        clearInterval(countdownInterval);
                        countdownInterval = null;
                    }
                    
                    const statusDiv = document.getElementById('paymentStatus');
                    if (statusDiv) {
                        statusDiv.innerHTML = `
                            <div class="alert alert-success text-center">
                                <i class="fas fa-check-circle fa-2x mb-2 d-block"></i>
                                <strong>✅ Pagamento aprovado!</strong><br>
                                ${sanitizeNumber(safeData.payment.credits, DAYS_PREMIUM)} créditos foram adicionados à sua conta.
                                ${safeData.payment.plan_type === 'daily_credits' ? '<br><span class="small">⭐ Plano Premium ativado! Você receberá 1 crédito por dia.</span>' : ''}
                                <div class="mt-3">
                                    <div class="spinner-border spinner-border-sm text-success me-2" role="status"></div>
                                    Redirecionando...
                                </div>
                            </div>
                        `;
                    }
                    
                    await updateCreditsDisplay();
                    
                    // 🔥 Disparar eventos para app.js
                    if (window.loadSubscriptionStatus) {
                        setTimeout(() => {
                            window.loadSubscriptionStatus();
                        }, 500);
                    }
                    
                    if (window.loadPremiumStatus) {
                        setTimeout(() => {
                            window.loadPremiumStatus();
                        }, 500);
                    }
                    
                    setTimeout(() => {
                        const modal = bootstrap.Modal.getInstance(document.getElementById('pixModal'));
                        if (modal) modal.hide();
                        window.location.href = '/dashboard?payment=success';
                    }, 2000);
                }
            }
        } catch (error) {
            console.error('Erro no polling:', error);
        }
    }, 3000);
}

// ==============================================
// 🔥 STATUS DO PLANO PREMIUM (COM CRÉDITOS DIÁRIOS)
// ==============================================

async function loadSubscriptionStatus() {
    try {
        const response = await fetchWithAuth(`${API_URL}/payments/subscription-status`);
        
        if (response && response.ok) {
            const data = await response.json();
            const safeData = sanitizeResponse(data);
            updatePlanStatusCard(safeData);
            return safeData;
        }
    } catch (error) {
        console.error('Erro ao carregar status da assinatura:', error);
    }
    return null;
}

function updatePlanStatusCard(subscriptionData) {
    const safeData = sanitizeResponse(subscriptionData);
    const statusContainer = document.getElementById('subscriptionStatusContainer');
    if (!statusContainer) return;
    
    if (!safeData.has_subscription && !safeData.is_admin) {
        statusContainer.innerHTML = `
            <div class="col-lg-8 mx-auto">
                <div class="alert alert-info text-center mb-0">
                    <i class="fas fa-info-circle me-2"></i>
                    Você ainda não possui um plano premium ativo.
                    <a href="#plansContainer" class="alert-link">Adquira agora!</a>
                </div>
            </div>
        `;
        return;
    }
    
    if (safeData.is_admin) {
        statusContainer.innerHTML = `
            <div class="col-lg-8 mx-auto">
                <div class="alert alert-warning text-center mb-0" style="background: linear-gradient(135deg, #fff3e0, #ffe0b3);">
                    <i class="fas fa-crown me-2 text-warning"></i>
                    <strong>👑 Administrador</strong> - Você tem acesso ilimitado a todas as funcionalidades!
                </div>
            </div>
        `;
        return;
    }
    
    const daysLeft = sanitizeNumber(safeData.days_left, 0);
    const expiresAt = safeData.expires_at ? new Date(safeData.expires_at) : null;
    const activatedAt = safeData.activated_at ? new Date(safeData.activated_at) : null;
    const isVitalicio = safeData.is_vitalicio || false;
    const lockedPrice = safeData.promotional_price || null;
    
    const formattedActivation = activatedAt ? activatedAt.toLocaleDateString('pt-BR') : '—';
    const formattedExpiration = expiresAt ? expiresAt.toLocaleDateString('pt-BR') : '—';
    
    let statusColor = '#28a745';
    let statusIcon = '✅';
    let statusText = 'Ativo';
    
    if (daysLeft <= 5 && daysLeft > 0) {
        statusColor = '#f5a623';
        statusIcon = '⚠️';
        statusText = 'Próximo do vencimento';
    } else if (daysLeft <= 0) {
        statusColor = '#dc3545';
        statusIcon = '❌';
        statusText = 'Expirado';
    }
    
    let progressPercent = 0;
    if (activatedAt && expiresAt) {
        const totalDays = DAYS_PREMIUM;
        const daysPassed = Math.max(0, Math.min(totalDays, totalDays - daysLeft));
        progressPercent = (daysPassed / totalDays) * 100;
    }
    
    const vitalicioBadge = isVitalicio ? `
        <span class="badge" style="background: #28a745; padding: 0.25rem 0.75rem; margin-left: 8px;">
            <i class="fas fa-gem me-1"></i> VITALÍCIO
        </span>
    ` : '';
    
    const priceBadge = lockedPrice ? `
        <div class="mt-2 small" style="color: #48bb78;">
            <i class="fas fa-lock me-1"></i>
            Preço garantido: R$ ${lockedPrice.toFixed(2).replace('.', ',')} (vitalício)
        </div>
    ` : '';
    
    statusContainer.innerHTML = `
        <div class="col-lg-8 mx-auto">
            <div class="premium-status-card" style="background: linear-gradient(135deg, #2c1a0a 0%, #3d2614 100%); border-radius: 20px; padding: 1.5rem; border: 1px solid #cd7f32;">
                <div class="d-flex justify-content-between align-items-start flex-wrap mb-3">
                    <div>
                        <h4 class="mb-1" style="color: #f5a623;">
                            <i class="fas fa-crown me-2"></i>
                            Plano Bronze Ativo ${vitalicioBadge}
                        </h4>
                        <p class="small mb-0" style="color: rgba(255,255,255,0.7);">
                            <i class="fas fa-check-circle me-1" style="color: #28a745;"></i>
                            Você tem acesso a todos os benefícios premium
                        </p>
                        ${priceBadge}
                    </div>
                    <div class="text-end">
                        <span class="badge" style="background: ${statusColor}; padding: 0.5rem 1rem;">
                            ${statusIcon} ${statusText}
                        </span>
                    </div>
                </div>
                
                <div class="row g-3 mb-3">
                    <div class="col-md-6">
                        <div class="p-3 rounded-3" style="background: rgba(0,0,0,0.3);">
                            <small style="color: rgba(255,255,255,0.6);">
                                <i class="fas fa-calendar-plus me-1"></i> DATA DA COMPRA
                            </small>
                            <div class="fw-bold" style="color: #f5a623; font-size: 1.1rem;">
                                ${sanitizeHTML(formattedActivation)}
                            </div>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="p-3 rounded-3" style="background: rgba(0,0,0,0.3);">
                            <small style="color: rgba(255,255,255,0.6);">
                                <i class="fas fa-calendar-times me-1"></i> DATA DE EXPIRAÇÃO
                            </small>
                            <div class="fw-bold" style="color: ${daysLeft <= 5 ? '#f5a623' : '#28a745'}; font-size: 1.1rem;">
                                ${sanitizeHTML(formattedExpiration)}
                                ${daysLeft > 0 ? `<small class="ms-2" style="color: rgba(255,255,255,0.5);">(em ${daysLeft} dias)</small>` : ''}
                            </div>
                        </div>
                    </div>
                </div>
                
                ${progressPercent > 0 ? `
                <div class="mb-3">
                    <div class="d-flex justify-content-between small mb-1" style="color: rgba(255,255,255,0.7);">
                        <span><i class="fas fa-hourglass-half me-1"></i> Progresso do plano</span>
                        <span>${Math.round(progressPercent)}%</span>
                    </div>
                    <div class="progress" style="height: 8px; background: rgba(255,255,255,0.2);">
                        <div class="progress-bar" role="progressbar" style="width: ${progressPercent}%; background: linear-gradient(90deg, #f5a623, #cd7f32);"></div>
                    </div>
                </div>
                ` : ''}
                
                <div class="alert alert-info small mb-0" style="background: rgba(245, 166, 35, 0.15); border-color: #f5a623; color: #f5a623;">
                    <i class="fas fa-info-circle me-2"></i>
                    <strong>Benefícios ativos:</strong> Você recebe <strong>1 crédito novo por dia</strong> (máximo de ${MAX_CREDITS_BALANCE} acumulados) e tem acesso a todas as análises da IA.
                    ${daysLeft <= 5 && daysLeft > 0 ? '<br><i class="fas fa-clock me-1"></i> <strong>Não esqueça de renovar para não perder os benefícios!</strong>' : ''}
                </div>
            </div>
        </div>
    `;
}

// ==============================================
// 🔥 STATUS PREMIUM COMPLETO (COM CRÉDITO DIÁRIO)
// ==============================================

/**
 * 🔥 CORRIGIDO: Carrega status premium e dispara evento para app.js
 */
async function loadPremiumStatus() {
    try {
        const response = await fetchWithAuth(`${API_URL}/payments/premium-status`);
        if (response && response.ok) {
            const data = await response.json();
            const safeData = sanitizeResponse(data);
            updatePremiumStatusUI(safeData);
            
            // 🔥 DISPARAR EVENTO PARA APP.JS
            window.dispatchEvent(new CustomEvent('premiumStatusUpdated', {
                detail: {
                    isPremium: safeData.is_premium || false,
                    daysLeft: safeData.days_left || 0,
                    hasPromotionalPrice: safeData.promotional_price_locked || false,
                    promotionalPrice: safeData.promotional_price || null,
                    canReceiveDailyCredit: safeData.can_receive_today || false,
                    receivedDailyCreditToday: safeData.received_today || false,
                    creditsBalance: safeData.credits_balance || 0,
                    maxCredits: safeData.max_credits_balance || MAX_CREDITS_BALANCE
                }
            }));
            
            return safeData;
        }
    } catch (error) {
        console.error('Erro ao carregar status premium:', error);
    }
    return null;
}

function updatePremiumStatusUI(data) {
    const safeData = sanitizeResponse(data);
    const container = document.getElementById('premiumStatusContainer');
    if (!container) return;
    
    if (!safeData.is_premium) {
        container.innerHTML = `
            <div class="premium-card premium-inactive">
                <div class="premium-status-header">
                    <i class="fas fa-crown" style="color: #f5a623;"></i>
                    <span>Plano Bronze</span>
                </div>
                <div class="premium-status-body">
                    <p class="text-center" style="color: rgba(255,255,255,0.7);">
                        <i class="fas fa-rocket me-2" style="color: #f5a623;"></i>
                        Ative o plano premium e ganhe <strong style="color: #f5a623;">1 crédito novo por dia</strong>!
                    </p>
                    <div class="premium-benefits-preview">
                        <div class="benefit-item">
                            <i class="fas fa-check-circle" style="color: #48bb78;"></i>
                            <span>1 crédito por dia durante ${DAYS_PREMIUM} dias</span>
                        </div>
                        <div class="benefit-item">
                            <i class="fas fa-check-circle" style="color: #48bb78;"></i>
                            <span>Limite máximo de ${MAX_CREDITS_BALANCE} créditos acumulados</span>
                        </div>
                        <div class="benefit-item">
                            <i class="fas fa-check-circle" style="color: #48bb78;"></i>
                            <span>Use seus créditos para análises com IA</span>
                        </div>
                    </div>
                    <a href="/planos" class="btn btn-premium w-100">
                        <i class="fas fa-gem me-2"></i>
                        Adquirir Plano Bronze
                    </a>
                </div>
            </div>
        `;
        return;
    }
    
    // ==========================================
    // USUÁRIO PREMIUM - STATUS DETALHADO
    // ==========================================
    
    const daysLeft = sanitizeNumber(safeData.days_left, 0);
    const creditsBalance = sanitizeNumber(safeData.credits_balance, 0);
    const maxCredits = sanitizeNumber(safeData.max_credits_balance, MAX_CREDITS_BALANCE);
    const receivedToday = safeData.received_today || false;
    const nextCreditDate = safeData.next_credit_date ? new Date(safeData.next_credit_date) : null;
    const activatedAt = safeData.activated_at ? new Date(safeData.activated_at) : null;
    const expiresAt = safeData.expires_at ? new Date(safeData.expires_at) : null;
    const canReceiveToday = safeData.can_receive_today || false;
    const isAtMaxCredits = creditsBalance >= maxCredits;
    const daysUsed = safeData.days_used || 0;
    const totalDays = DAYS_PREMIUM;
    const isVitalicio = safeData.is_vitalicio || false;
    const lockedPrice = safeData.promotional_price || null;
    
    const formattedActivation = activatedAt ? activatedAt.toLocaleDateString('pt-BR') : '—';
    const formattedExpiration = expiresAt ? expiresAt.toLocaleDateString('pt-BR') : '—';
    const progressPercent = Math.min(100, Math.round((daysUsed / totalDays) * 100));
    
    const isExpiringSoon = daysLeft <= 5 && daysLeft > 0;
    const isExpired = daysLeft <= 0;
    
    let nextStatusText = '';
    let nextStatusColor = '#f5a623';
    let nextStatusIcon = 'fa-hourglass-half';
    
    if (isAtMaxCredits) {
        nextStatusText = 'Gaste 1 para receber';
        nextStatusColor = '#f56565';
        nextStatusIcon = 'fa-exclamation-triangle';
    } else if (receivedToday) {
        nextStatusText = 'Amanhã';
        nextStatusColor = '#48bb78';
        nextStatusIcon = 'fa-check-circle';
    } else if (canReceiveToday) {
        nextStatusText = 'Disponível HOJE! 🎯';
        nextStatusColor = '#48bb78';
        nextStatusIcon = 'fa-gift';
    } else {
        nextStatusText = 'Em breve...';
        nextStatusColor = '#f5a623';
        nextStatusIcon = 'fa-clock';
    }
    
    const vitalicioBadge = isVitalicio ? `
        <span class="badge" style="background: #28a745; padding: 0.25rem 0.75rem; margin-left: 8px;">
            <i class="fas fa-gem me-1"></i> VITALÍCIO
        </span>
    ` : '';
    
    const priceBadge = lockedPrice ? `
        <div class="mt-1 small" style="color: #48bb78;">
            <i class="fas fa-lock me-1"></i>
            Preço garantido: R$ ${lockedPrice.toFixed(2).replace('.', ',')} (vitalício)
        </div>
    ` : '';
    
    container.innerHTML = `
        <div class="premium-card premium-active">
            <!-- HEADER -->
            <div class="premium-status-header">
                <div class="d-flex align-items-center">
                    <i class="fas fa-crown" style="color: #f5a623; font-size: 1.5rem;"></i>
                    <div class="ms-3">
                        <h5 class="mb-0" style="color: white;">
                            Plano Bronze Premium ${vitalicioBadge}
                        </h5>
                        ${priceBadge}
                        <small style="color: rgba(255,255,255,0.6);">
                            <i class="fas fa-calendar-check me-1"></i>
                            Ativo desde ${sanitizeHTML(formattedActivation)}
                        </small>
                    </div>
                </div>
                <span class="badge premium-badge ${isExpiringSoon ? 'badge-warning' : ''} ${isExpired ? 'badge-danger' : ''}">
                    <i class="fas fa-clock me-1"></i>
                    ${isExpired ? 'Expirado ⚠️' : `${daysLeft} dias restantes`}
                </span>
            </div>
            
            <!-- PROGRESSO DO PLANO -->
            <div class="premium-progress">
                <div class="d-flex justify-content-between small mb-1">
                    <span style="color: rgba(255,255,255,0.6);">Progresso do plano (${totalDays} dias)</span>
                    <span style="color: #f5a623;">${progressPercent}%</span>
                </div>
                <div class="progress" style="height: 6px; background: rgba(255,255,255,0.15);">
                    <div class="progress-bar" style="width: ${progressPercent}%; background: linear-gradient(90deg, #f5a623, #cd7f32);"></div>
                </div>
                <div class="d-flex justify-content-between small mt-1">
                    <span style="color: rgba(255,255,255,0.4);">Dia ${Math.min(daysUsed + 1, totalDays)}</span>
                    <span style="color: rgba(255,255,255,0.4);">Dia ${totalDays}</span>
                </div>
            </div>
            
            <!-- CARDS DE CRÉDITOS -->
            <div class="row g-3 mb-3">
                <div class="col-4">
                    <div class="credit-status-card text-center p-3 rounded-3">
                        <div style="font-size: 2rem; color: #f5a623; font-weight: 700;">${creditsBalance}</div>
                        <div style="font-size: 0.7rem; color: rgba(255,255,255,0.6);">
                            <i class="fas fa-coins me-1"></i>Créditos Atuais
                        </div>
                        <div style="font-size: 0.6rem; color: rgba(255,255,255,0.4);">máx. ${maxCredits}</div>
                    </div>
                </div>
                <div class="col-4">
                    <div class="credit-status-card text-center p-3 rounded-3">
                        <div style="font-size: 2rem; color: ${receivedToday ? '#48bb78' : (canReceiveToday ? '#f5a623' : '#f56565')};">
                            ${receivedToday ? '✅' : (canReceiveToday ? '🎯' : '⏳')}
                        </div>
                        <div style="font-size: 0.7rem; color: rgba(255,255,255,0.6);">
                            <i class="fas fa-calendar-day me-1"></i>Crédito Hoje
                        </div>
                        <div style="font-size: 0.6rem; color: ${receivedToday ? '#48bb78' : (canReceiveToday ? '#f5a623' : '#f56565')};">
                            ${receivedToday ? 'Recebido ✅' : (canReceiveToday ? 'Disponível 🎯' : 'Aguardando ⏳')}
                        </div>
                    </div>
                </div>
                <div class="col-4">
                    <div class="credit-status-card text-center p-3 rounded-3">
                        <div style="font-size: 1.8rem; color: ${isAtMaxCredits ? '#f56565' : '#f5a623'};">
                            <i class="fas ${isAtMaxCredits ? 'fa-exclamation-triangle' : 'fa-arrow-right'}"></i>
                        </div>
                        <div style="font-size: 0.7rem; color: rgba(255,255,255,0.6);">
                            <i class="fas fa-clock me-1"></i>Próximo Crédito
                        </div>
                        <div style="font-size: 0.6rem; color: ${nextStatusColor};">
                            ${sanitizeHTML(nextStatusText)}
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- MENSAGEM DE AÇÃO -->
            <div class="premium-message ${isAtMaxCredits ? 'premium-message-warning' : (canReceiveToday ? 'premium-message-success' : 'premium-message-info')}">
                <i class="fas ${isAtMaxCredits ? 'fa-exclamation-triangle' : (canReceiveToday ? 'fa-gift' : 'fa-info-circle')} me-2"></i>
                <span>
                    ${isAtMaxCredits 
                        ? `⚠️ <strong>Limite de ${maxCredits} créditos atingido!</strong> Use um crédito para continuar recebendo 1 por dia.`
                        : (canReceiveToday)
                            ? `🎯 <strong>Você tem um crédito disponível HOJE!</strong> Clique no botão abaixo para receber.`
                            : (receivedToday)
                                ? `✅ Crédito de hoje já recebido! Volte amanhã para mais 1 crédito.`
                                : `📅 Você está em dia com seus créditos. Continue usando para otimizar seu negócio!`
                    }
                </span>
            </div>
            
            <!-- BOTÃO DE AÇÃO -->
            ${canReceiveToday ? `
                <div class="d-grid gap-2 mt-3">
                    <button class="btn btn-premium-receive" onclick="window.receiveDailyCredit()">
                        <i class="fas fa-gift me-2"></i>
                        Receber meu crédito de hoje! 🎁
                    </button>
                </div>
            ` : ''}
            
            ${isAtMaxCredits ? `
                <div class="premium-action-cta text-center mt-2">
                    <small style="color: rgba(255,255,255,0.7);">
                        💡 <strong style="color: #f5a623;">Dica:</strong> Você está com ${creditsBalance}/${maxCredits} créditos. 
                        <span style="color: #48bb78;">Use um crédito para receber outro amanhã!</span>
                    </small>
                    <br>
                    <a href="/dashboard" class="btn btn-sm btn-outline-warning mt-2">
                        <i class="fas fa-upload me-1"></i>
                        Ir para Dashboard e usar créditos
                    </a>
                </div>
            ` : ''}
            
            ${isExpiringSoon ? `
                <div class="premium-expiring-warning mt-2">
                    <i class="fas fa-clock me-1"></i>
                    <span>⚠️ Seu plano expira em ${daysLeft} dias. Renove para não perder os benefícios!</span>
                    <a href="/planos" class="btn btn-sm btn-warning ms-2">Renovar Agora</a>
                </div>
            ` : ''}
            
            <!-- FOOTER -->
            <div class="premium-footer">
                <div class="row text-center small">
                    <div class="col-6">
                        <i class="fas fa-calendar-plus" style="color: #f5a623;"></i>
                        <span style="color: rgba(255,255,255,0.6);"> Início: ${sanitizeHTML(formattedActivation)}</span>
                    </div>
                    <div class="col-6">
                        <i class="fas fa-calendar-times" style="color: ${isExpiringSoon ? '#f56565' : '#f5a623'};"></i>
                        <span style="color: rgba(255,255,255,0.6);"> Expira: ${sanitizeHTML(formattedExpiration)}</span>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Notificações
    if (isAtMaxCredits) {
        showNotification(
            `⚠️ Você atingiu o limite de ${maxCredits} créditos! Use um crédito para continuar recebendo 1 por dia.`,
            'warning'
        );
    }
    
    if (canReceiveToday) {
        showNotification(
            '🎯 Você tem um crédito premium disponível HOJE! Clique no botão para receber.',
            'success'
        );
    }
}

/**
 * 🔥 RECEBE CRÉDITO DIÁRIO (COM SEGURANÇA E EVENTO)
 */
async function receiveDailyCredit() {
    try {
        const response = await fetchWithAuth(`${API_URL}/payments/daily-credit`, {
            method: 'POST'
        });
        
        if (response && response.ok) {
            const data = await response.json();
            const safeData = sanitizeResponse(data);
            
            if (safeData.success) {
                showNotification(`✅ ${safeData.message || 'Crédito recebido com sucesso!'}`, 'success');
                
                // 🔥 DISPARAR EVENTO PARA APP.JS
                window.dispatchEvent(new CustomEvent('dailyCreditReceived', {
                    detail: {
                        success: true,
                        credits: safeData.current_credits || 0,
                        message: safeData.message
                    }
                }));
                
                setTimeout(() => loadPremiumStatus(), 500);
                setTimeout(() => updateCreditsDisplay(), 1000);
                
                return safeData;
            } else {
                showNotification(safeData.message || 'Erro ao receber crédito', 'warning');
                return safeData;
            }
        } else {
            showNotification('Erro ao receber crédito. Tente novamente.', 'error');
            return null;
        }
    } catch (error) {
        console.error('Erro ao receber crédito:', error);
        showNotification('Erro de conexão. Tente novamente.', 'error');
        return null;
    }
}

// ==============================================
// 🔥 POLLING PARA STATUS PREMIUM
// ==============================================

let premiumStatusInterval = null;

function startPremiumStatusPolling(interval = 60000) {
    if (premiumStatusInterval) clearInterval(premiumStatusInterval);
    
    loadPremiumStatus();
    
    premiumStatusInterval = setInterval(() => {
        loadPremiumStatus();
    }, interval);
}

function stopPremiumStatusPolling() {
    if (premiumStatusInterval) {
        clearInterval(premiumStatusInterval);
        premiumStatusInterval = null;
    }
}

// ==============================================
// 🔥 INICIALIZAÇÃO
// ==============================================

function isPlansPage() {
    return window.location.pathname.includes('planos.html') || 
           window.location.pathname === '/planos' ||
           document.getElementById('plansContainer') !== null;
}

function isDashboardPage() {
    return window.location.pathname.includes('index.html') || 
           window.location.pathname === '/dashboard' ||
           window.location.pathname === '/' ||
           document.getElementById('premiumStatusContainer') !== null;
}

document.addEventListener('DOMContentLoaded', function() {
    // Inicializar na página de planos
    if (isPlansPage()) {
        setTimeout(() => {
            loadPlans();
            console.log('✅ payment.js - PÁGINA DE PLANOS');
            console.log(`📊 MAX_CREDITS_BALANCE: ${MAX_CREDITS_BALANCE}`);
            console.log(`💰 Preço Fundador: R$ ${PROMOTIONAL_PRICE}`);
            console.log(`💰 Preço Cheio: R$ ${REGULAR_PRICE}`);
            console.log(`🎯 Total de vagas: ${TOTAL_PROMOTIONAL_SLOTS}`);
        }, 200);
    }
    
    // Inicializar STATUS PREMIUM no dashboard
    if (isDashboardPage()) {
        setTimeout(() => {
            loadPremiumStatus();
            startPremiumStatusPolling(60000);
            console.log('✅ payment.js - Status Premium ativo no Dashboard');
        }, 500);
    }
    
    // Atualizar créditos periodicamente
    const creditsElement = document.getElementById('creditsDisplay');
    if (creditsElement) {
        updateCreditsDisplay();
        setInterval(updateCreditsDisplay, 30000);
    }
    
    // Limpar polling ao fechar modal PIX
    const pixModal = document.getElementById('pixModal');
    if (pixModal) {
        pixModal.addEventListener('hidden.bs.modal', function() {
            if (paymentPollingInterval) {
                clearInterval(paymentPollingInterval);
                paymentPollingInterval = null;
            }
            if (countdownInterval) {
                clearInterval(countdownInterval);
                countdownInterval = null;
            }
        });
    }
    
    // Verificar parâmetro de sucesso no pagamento
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('payment') === 'success') {
        showNotification('✅ Pagamento aprovado! Créditos adicionados à sua conta.', 'success');
        window.history.replaceState({}, document.title, window.location.pathname);
        
        setTimeout(() => {
            if (window.loadSubscriptionStatus) {
                window.loadSubscriptionStatus();
            }
            if (window.loadPremiumStatus) {
                window.loadPremiumStatus();
            }
            if (window.updateCreditsDisplay) {
                window.updateCreditsDisplay();
            }
        }, 1000);
    }
    
    // 🔥 Disparar evento de payment carregado
    window.dispatchEvent(new CustomEvent('paymentReady', {
        detail: {
            loaded: true,
            version: '2.1'
        }
    }));
});

// ==============================================
// 🔥 EXPOSIÇÃO DE FUNÇÕES GLOBAIS
// ==============================================

// Pagamento
window.selectPlan = selectPlan;
window.openCpfModal = openCpfModal;
window.proceedWithCpf = proceedWithCpf;
window.copyPixCodeSecure = copyPixCodeSecure;

// Créditos
window.updateCreditsDisplay = updateCreditsDisplay;
window.formatCreditsDisplay = formatCreditsDisplay;
window.showNotification = showNotification;
window.getCredits = getCredits;
window.isPremium = isPremium;

// Status do plano
window.loadSubscriptionStatus = loadSubscriptionStatus;

// 🔥 Status Premium (crédito diário)
window.loadPremiumStatus = loadPremiumStatus;
window.updatePremiumStatusUI = updatePremiumStatusUI;
window.receiveDailyCredit = receiveDailyCredit;
window.startPremiumStatusPolling = startPremiumStatusPolling;
window.stopPremiumStatusPolling = stopPremiumStatusPolling;

// Segurança
window.sanitizeHTML = sanitizeHTML;
window.sanitizeCPF = sanitizeCPF;
window.validateCPF = validateCPF;
window.sanitizeResponse = sanitizeResponse;

console.log('✅ payment.js carregado - v2.1');
console.log('🔒 Proteção antifraude: CPF obrigatório e validado');
console.log(`📊 Limite máximo de créditos: ${MAX_CREDITS_BALANCE}`);
console.log(`💰 Preço Fundador: R$ ${PROMOTIONAL_PRICE} (vitalício)`);
console.log(`💰 Preço Cheio: R$ ${REGULAR_PRICE}`);
console.log(`🎯 Total de vagas: ${TOTAL_PROMOTIONAL_SLOTS}`);
console.log('🕐 Fuso horário: America/Sao_Paulo (UTC-3)');
console.log('📡 Eventos: paymentReady, creditsUpdated, premiumStatusUpdated, dailyCreditReceived');