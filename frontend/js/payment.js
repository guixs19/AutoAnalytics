// payment.js - VERSÃO COMPLETA SINCRONIZADA COM BACKEND PREMIUM
// ==============================================
// CONFIGURAÇÕES GLOBAIS
// ==============================================

const API_URL = window.API_URL || 'http://localhost:8000/api';

// ==============================================
// FUNÇÕES DE SEGURANÇA
// ==============================================

function sanitizeHTML(str) {
    if (!str) return '';
    return str.replace(/[&<>]/g, function(m) {
        if (m === '&') return '&amp;';
        if (m === '<') return '&lt;';
        if (m === '>') return '&gt;';
        return m;
    });
}

// ==============================================
// FUNÇÕES DE AUTENTICAÇÃO E USUÁRIO
// ==============================================

function isAdmin() {
    return window.appAuth ? window.appAuth.isAdmin() : false;
}

function getCreditsDisplay() {
    return window.appAuth ? window.appAuth.getCreditsDisplay() : '0';
}

function isPremium() {
    return window.appAuth ? window.appAuth.isPremium() : false;
}

// Formatar exibição de créditos (suporte premium com limite de 3)
function formatCreditsDisplay(credits, isPremiumUser = false, maxCredits = 3) {
    if (isAdmin()) return '∞';
    if (isPremiumUser) {
        return `${credits}/${maxCredits}`;
    }
    return credits.toString();
}

// Atualizar display de créditos no header/navbar
async function updateCreditsDisplay() {
    try {
        const response = await fetchWithAuth(`${API_URL}/users/me/credits`);
        if (response && response.ok) {
            const data = await response.json();
            const creditsElement = document.getElementById('creditsDisplay');
            if (creditsElement) {
                const displayText = formatCreditsDisplay(
                    data.current_credits || 0,
                    data.is_premium || false,
                    data.max_credits || 3
                );
                creditsElement.innerHTML = `<i class="fas fa-coins me-1"></i> ${displayText}`;
                
                // Atualizar também no appAuth
                if (window.appAuth && window.appAuth.updateCredits) {
                    window.appAuth.updateCredits(data.current_credits, data.is_premium);
                }
            }
        }
    } catch (error) {
        console.error('Erro ao atualizar créditos:', error);
    }
}

// ==============================================
// CARREGAMENTO DE PLANOS
// ==============================================

async function loadPlans() {
    try {
        const response = await fetch(`${API_URL}/payments/plans`);
        if (response.ok) {
            const data = await response.json();
            renderPlans(data.plans, data.premium_info);
        } else {
            console.error('Erro ao carregar planos:', response.status);
            showNotification('Erro ao carregar planos. Tente novamente.', 'error');
        }
    } catch (error) {
        console.error('Erro ao carregar planos:', error);
        showNotification('Erro de conexão. Tente novamente.', 'error');
    }
}

// Renderizar planos com informações completas (incluindo limite de 3 créditos)
function renderPlans(plans, premiumInfo = null) {
    const container = document.getElementById('plansContainer');
    if (!container) return;
    
    // Admin tem acesso ilimitado
    if (isAdmin()) {
        container.innerHTML = `
            <div class="col-12">
                <div class="alert alert-warning text-center p-5 rounded-4">
                    <i class="fas fa-crown fa-4x mb-3 text-warning"></i>
                    <h3>👑 Você é Administrador</h3>
                    <p class="lead">Como admin, você tem acesso ilimitado a todas as funcionalidades.</p>
                    <p class="small text-muted">Créditos: ∞ (ilimitado)</p>
                </div>
            </div>
        `;
        return;
    }
    
    let html = '';
    
    for (const [key, plan] of Object.entries(plans)) {
        const planName = sanitizeHTML(plan.name);
        const isDailyCredits = plan.type === 'daily_credits';
        
        html += `
            <div class="col-lg-4 mb-4">
                <div class="plan-card ${plan.popular ? 'popular' : ''}">
                    ${plan.popular ? '<div class="popular-badge">🔥 MAIS POPULAR 🔥</div>' : ''}
                    <div class="text-center">
                        <span class="guarantee-badge mb-3">
                            <i class="fas fa-shield-alt me-2"></i>
                            Garantia de 7 dias
                        </span>
                        <h3 class="h4 mb-3">${planName}</h3>
                        <div class="price-tag">
                            R$ ${plan.price.toFixed(2).replace('.', ',')}
                        </div>
                        ${plan.price_per_credit ? `
                            <div class="small text-muted mt-2">
                                ~ R$ ${plan.price_per_credit.toFixed(2)} por crédito
                            </div>
                        ` : ''}
                    </div>
                    
                    <div class="my-4">
                        ${isDailyCredits ? `
                            <div class="feature-item">
                                <i class="fas fa-calendar-day"></i>
                                <span><strong>${plan.credits_per_day || 1} crédito novo</strong> por dia</span>
                            </div>
                            <div class="feature-item">
                                <i class="fas fa-layer-group"></i>
                                <span><strong>${plan.total_credits || 30} créditos</strong> no total (30 dias)</span>
                            </div>
                            <div class="feature-item">
                                <i class="fas fa-chart-line"></i>
                                <span>Máximo de <strong>${plan.max_credits_balance || 3} créditos</strong> acumulados</span>
                            </div>
                            <div class="feature-item">
                                <i class="fas fa-clock"></i>
                                <span>Expira em <strong>${plan.duration_days || 30} dias</strong></span>
                            </div>
                        ` : `
                            <div class="feature-item">
                                <i class="fas fa-bolt"></i>
                                <span><strong>${plan.credits} créditos</strong> imediatos</span>
                            </div>
                        `}
                        <div class="feature-item">
                            <i class="fas fa-robot"></i>
                            <span>Modelos <strong>Scikit-Learn + IA</strong></span>
                        </div>
                        <div class="feature-item">
                            <i class="fas fa-headset"></i>
                            <span>Suporte <strong>24/7</strong></span>
                        </div>
                        ${isDailyCredits ? `
                            <div class="feature-item text-warning">
                                <i class="fas fa-info-circle"></i>
                                <span class="small">⚠️ Créditos não acumulam acima de ${plan.max_credits_balance || 3}</span>
                            </div>
                        ` : ''}
                    </div>
                    
                    <div class="d-grid gap-3 mt-4">
                        <button class="btn btn-gradient" onclick="selectPlan('${key}', 'pix')">
                            <i class="fas fa-qrcode me-2"></i>
                            Comprar com PIX
                        </button>
                    </div>
                </div>
            </div>
        `;
    }
    
    container.innerHTML = html;
}

// ==============================================
// SELEÇÃO E PAGAMENTO
// ==============================================

async function selectPlan(planId, method) {
    // Admin não precisa comprar
    if (isAdmin()) {
        showNotification('👑 Como administrador, você tem acesso ilimitado.', 'info');
        return;
    }
    
    // Mostrar loading
    const btn = event?.target?.closest('button');
    if (btn) {
        const originalText = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i> Processando...';
        btn.disabled = true;
        
        setTimeout(() => {
            if (btn) {
                btn.innerHTML = originalText;
                btn.disabled = false;
            }
        }, 5000);
    }
    
    try {
        const response = await fetchWithAuth(`${API_URL}/payments/create-${method}`, {
            method: 'POST',
            body: JSON.stringify({ plan_id: planId })
        });
        
        if (response && response.ok) {
            const data = await response.json();
            
            if (method === 'pix') {
                if (data.payment_id) {
                    showPixModalSecure(data.payment_id, data);
                } else if (data.checkout_url) {
                    // Redirecionar para checkout do Mercado Pago
                    window.location.href = data.checkout_url;
                } else {
                    showNotification('Pagamento iniciado. Verifique o status no dashboard.', 'info');
                    setTimeout(() => {
                        window.location.href = '/dashboard';
                    }, 2000);
                }
            }
        } else if (response) {
            const error = await response.json();
            const errorMsg = error.detail || error.message || 'Erro ao criar pagamento';
            showNotification(sanitizeHTML(errorMsg), 'error');
        } else {
            showNotification('Erro de conexão. Tente novamente.', 'error');
        }
    } catch (error) {
        console.error('Erro ao criar pagamento:', error);
        showNotification('Erro de conexão. Tente novamente.', 'error');
    }
}

// ==============================================
// MODAL PIX SEGURO
// ==============================================

async function showPixModalSecure(paymentId, paymentData) {
    const modalContent = document.getElementById('pixContent');
    if (!modalContent) return;
    
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
        const response = await fetchWithAuth(`${API_URL}/payments/pix-qrcode/${paymentId}`);
        
        if (response && response.ok) {
            const qrData = await response.json();
            
            if (qrData.success && qrData.qr_code_base64) {
                const maxCredits = qrData.max_credits_balance || 3;
                const isPremiumPlan = paymentData.plan_type === 'daily_credits';
                
                modalContent.innerHTML = `
                    ${paymentData.promotional_message ? `
                        <div class="alert alert-warning mb-3 text-center">
                            <i class="fas fa-gift me-2"></i>
                            ${sanitizeHTML(paymentData.promotional_message)}
                        </div>
                    ` : ''}
                    
                    <h6 class="mb-3 text-center">Escaneie o QR Code com seu banco</h6>
                    
                    <div class="text-center mb-3">
                        <img src="data:image/png;base64,${qrData.qr_code_base64}" 
                             alt="QR Code PIX"
                             class="img-fluid" style="max-width: 200px; border-radius: 12px;">
                    </div>
                    
                    <div class="bg-light p-3 rounded-3 mb-3" style="word-break: break-all;">
                        <code id="pixCodeText" class="small">${sanitizeHTML(qrData.qr_code || 'Código disponível no app do banco')}</code>
                    </div>
                    
                    <button class="btn btn-outline-primary w-100 mb-3" onclick="window.copyPixCodeSecure()">
                        <i class="fas fa-copy me-2"></i>
                        Copiar código PIX
                    </button>
                    
                    <div class="alert alert-info small">
                        <i class="fas fa-info-circle me-2"></i>
                        <strong>Informações do pagamento:</strong><br>
                        Valor: R$ ${paymentData.amount?.toFixed(2) || '0,00'}<br>
                        Créditos: ${paymentData.credits || 0}
                        ${isPremiumPlan ? `<br>⚠️ <strong>Plano Premium:</strong> máximo de ${maxCredits} créditos acumulados por vez.` : ''}
                        <br><br>
                        Após o pagamento, os créditos são adicionados automaticamente.
                    </div>
                    
                    <div id="paymentStatus"></div>
                `;
            } else {
                modalContent.innerHTML = `
                    <div class="alert alert-info text-center">
                        <i class="fas fa-info-circle fa-2x mb-2 d-block"></i>
                        <p>Pagamento registrado! O QR Code será exibido em breve.</p>
                        <p class="small text-muted">Status: ${qrData.status || 'pendente'}</p>
                        <button class="btn btn-outline-primary mt-3" onclick="location.reload()">
                            <i class="fas fa-sync-alt me-2"></i>
                            Atualizar
                        </button>
                    </div>
                `;
            }
            
            // Iniciar polling para verificar status do pagamento
            startPaymentPollingSecure(paymentId);
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
                <p class="small text-muted">${error.message || 'Erro desconhecido'}</p>
            </div>
        `;
    }
}

function copyPixCodeSecure() {
    const codeElement = document.getElementById('pixCodeText');
    if (codeElement) {
        const code = codeElement.textContent.trim();
        navigator.clipboard.writeText(code)
            .then(() => showNotification('✅ Código PIX copiado!', 'success'))
            .catch(() => {
                // Fallback para navegadores antigos
                const textarea = document.createElement('textarea');
                textarea.value = code;
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand('copy');
                document.body.removeChild(textarea);
                showNotification('✅ Código PIX copiado!', 'success');
            });
    }
}

// ==============================================
// POLLING DE PAGAMENTO
// ==============================================

let paymentPollingInterval = null;

function startPaymentPollingSecure(paymentId) {
    if (paymentPollingInterval) clearInterval(paymentPollingInterval);
    
    let attempts = 0;
    const maxAttempts = 60; // ~3 minutos (60 * 3s = 180s)
    
    paymentPollingInterval = setInterval(async () => {
        attempts++;
        
        // Verificar se o modal ainda está aberto
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
            const response = await fetchWithAuth(`${API_URL}/payments/status/${paymentId}`);
            if (response && response.ok) {
                const data = await response.json();
                
                if (data.payment && data.payment.status === 'approved') {
                    clearInterval(paymentPollingInterval);
                    paymentPollingInterval = null;
                    
                    const statusDiv = document.getElementById('paymentStatus');
                    if (statusDiv) {
                        statusDiv.innerHTML = `
                            <div class="alert alert-success text-center">
                                <i class="fas fa-check-circle fa-2x mb-2 d-block"></i>
                                <strong>✅ Pagamento aprovado!</strong><br>
                                ${data.payment.credits} créditos foram adicionados à sua conta.
                                ${data.payment.plan_type === 'daily_credits' ? '<br><span class="small">⭐ Plano Premium ativado! Você receberá 1 crédito por dia.</span>' : ''}
                                <div class="mt-3">
                                    <div class="spinner-border spinner-border-sm text-success me-2" role="status"></div>
                                    Redirecionando...
                                </div>
                            </div>
                        `;
                    }
                    
                    // Atualizar display de créditos
                    await updateCreditsDisplay();
                    
                    // Aguardar 2 segundos e redirecionar
                    setTimeout(() => {
                        const modal = bootstrap.Modal.getInstance(document.getElementById('pixModal'));
                        if (modal) modal.hide();
                        window.location.href = '/dashboard?payment=success';
                    }, 2000);
                } else if (data.payment && data.payment.status === 'rejected') {
                    clearInterval(paymentPollingInterval);
                    paymentPollingInterval = null;
                    
                    const statusDiv = document.getElementById('paymentStatus');
                    if (statusDiv) {
                        statusDiv.innerHTML = `
                            <div class="alert alert-danger text-center">
                                <i class="fas fa-times-circle fa-2x mb-2 d-block"></i>
                                <strong>❌ Pagamento recusado</strong><br>
                                O pagamento não foi aprovado. Tente novamente.
                                <div class="mt-3">
                                    <button class="btn btn-outline-danger" onclick="location.reload()">
                                        <i class="fas fa-redo me-2"></i>
                                        Tentar novamente
                                    </button>
                                </div>
                            </div>
                        `;
                    }
                } else if (data.payment && data.payment.status === 'pending' && attempts % 10 === 0) {
                    // Atualizar mensagem a cada 30 segundos (10 tentativas)
                    const statusDiv = document.getElementById('paymentStatus');
                    if (statusDiv && !statusDiv.innerHTML.includes('Aguardando')) {
                        statusDiv.innerHTML = `
                            <div class="alert alert-info text-center">
                                <i class="fas fa-hourglass-half me-2"></i>
                                Aguardando confirmação do pagamento...
                                <div class="progress mt-2" style="height: 4px;">
                                    <div class="progress-bar progress-bar-striped progress-bar-animated" 
                                         style="width: ${Math.min(100, (attempts / maxAttempts) * 100)}%"></div>
                                </div>
                            </div>
                        `;
                    }
                }
            }
        } catch (error) {
            console.error('Erro no polling:', error);
            if (attempts % 10 === 0) {
                const statusDiv = document.getElementById('paymentStatus');
                if (statusDiv) {
                    statusDiv.innerHTML = `
                        <div class="alert alert-warning text-center">
                            <i class="fas fa-sync-alt fa-spin me-2"></i>
                            Verificando status do pagamento...
                        </div>
                    `;
                }
            }
        }
    }, 3000); // Verificar a cada 3 segundos
}

// ==============================================
// NOTIFICAÇÕES
// ==============================================

function showNotification(message, type = 'info') {
    const sanitizedMessage = sanitizeHTML(message);
    
    if (window.toastr) {
        const options = {
            closeButton: true,
            progressBar: true,
            positionClass: 'toast-top-right',
            timeOut: 5000
        };
        
        switch (type) {
            case 'success':
                toastr.success(sanitizedMessage, '✅ Sucesso!', options);
                break;
            case 'error':
                toastr.error(sanitizedMessage, '❌ Erro', options);
                break;
            case 'warning':
                toastr.warning(sanitizedMessage, '⚠️ Atenção', options);
                break;
            default:
                toastr.info(sanitizedMessage, 'ℹ️ Informação', options);
        }
    } else {
        // Fallback para alert
        alert(sanitizedMessage);
    }
}

// ==============================================
// REQUISIÇÕES AUTENTICADAS
// ==============================================

async function fetchWithAuth(url, options = {}) {
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
        
        // Token expirado
        if (response.status === 401) {
            // Tentar renovar token
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
                        // Tentar novamente com o novo token
                        headers['Authorization'] = `Bearer ${refreshData.access_token}`;
                        return fetch(url, { ...options, headers });
                    }
                } catch (refreshError) {
                    console.error('Erro ao renovar token:', refreshError);
                }
            }
            
            // Se não conseguiu renovar, redirecionar para login
            localStorage.removeItem('access_token');
            localStorage.removeItem('refresh_token');
            window.location.href = '/login.html?session=expired';
            return null;
        }
        
        return response;
    } catch (error) {
        console.error('Fetch error:', error);
        return null;
    }
}

// ==============================================
// INICIALIZAÇÃO
// ==============================================

// Verificar se é página de planos
function isPlansPage() {
    return window.location.pathname.includes('planos.html') || 
           window.location.pathname === '/planos' ||
           document.getElementById('plansContainer') !== null;
}

// Inicializar quando o DOM estiver pronto
document.addEventListener('DOMContentLoaded', function() {
    // Carregar planos se estiver na página correta
    if (isPlansPage()) {
        setTimeout(() => {
            loadPlans();
            console.log('✅ payment.js inicializado (versão premium com limite de 3 créditos)');
        }, 200);
    }
    
    // Configurar atualização automática de créditos
    const creditsElement = document.getElementById('creditsDisplay');
    if (creditsElement) {
        updateCreditsDisplay();
        // Atualizar a cada 30 segundos
        setInterval(updateCreditsDisplay, 30000);
    }
    
    // Fechar modal ao clicar fora
    const pixModal = document.getElementById('pixModal');
    if (pixModal) {
        pixModal.addEventListener('hidden.bs.modal', function() {
            if (paymentPollingInterval) {
                clearInterval(paymentPollingInterval);
                paymentPollingInterval = null;
            }
        });
    }
    
    // Verificar parâmetro de sucesso na URL
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('payment') === 'success') {
        showNotification('Pagamento aprovado! Créditos adicionados à sua conta.', 'success');
        // Limpar parâmetro da URL
        window.history.replaceState({}, document.title, window.location.pathname);
    }
});

// ==============================================
// EXPOSIÇÃO DE FUNÇÕES GLOBAIS (SEGURA)
// ==============================================

// Expor apenas funções necessárias para o HTML
window.selectPlan = selectPlan;
window.copyPixCodeSecure = copyPixCodeSecure;
window.updateCreditsDisplay = updateCreditsDisplay;
window.formatCreditsDisplay = formatCreditsDisplay;
window.showNotification = showNotification;

console.log('✅ payment.js carregado - Modo Premium com limite de 3 créditos');