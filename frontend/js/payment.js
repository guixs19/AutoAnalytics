

// Função para sanitizar saída HTML
function sanitizeHTML(str) {
    if (!str) return '';
    return str.replace(/[&<>]/g, function(m) {
        if (m === '&') return '&amp;';
        if (m === '<') return '&lt;';
        if (m === '>') return '&gt;';
        return m;
    });
}

// Função para verificar se é admin (segura)
function isAdmin() {
    return window.appAuth ? window.appAuth.isAdmin() : false;
}

// Função para obter display de créditos
function getCreditsDisplay() {
    return window.appAuth ? window.appAuth.getCreditsDisplay() : '0';
}

// Carregar planos na página planos.html
async function loadPlans() {
    try {
        const response = await fetch(`${API_URL}/payments/plans`);
        if (response.ok) {
            const data = await response.json();
            renderPlans(data.plans);
        }
    } catch (error) {
        console.error('Erro ao carregar planos:', error);
    }
}

// Renderizar planos (seguro - sem innerHTML perigoso)
function renderPlans(plans) {
    const container = document.getElementById('plansContainer');
    if (!container) return;
    
    if (isAdmin()) {
        container.innerHTML = `
            <div class="col-12">
                <div class="alert alert-warning text-center p-5 rounded-4">
                    <i class="fas fa-crown fa-4x mb-3 text-warning"></i>
                    <h3>👑 Você é Administrador</h3>
                    <p class="lead">Como admin, você tem acesso ilimitado a todas as funcionalidades.</p>
                </div>
            </div>
        `;
        return;
    }
    
    let html = '';
    
    for (const [key, plan] of Object.entries(plans)) {
        // Sanitizar nome do plano
        const planName = sanitizeHTML(plan.name);
        
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
                    </div>
                    
                    <div class="my-4">
                        <div class="feature-item">
                            <i class="fas fa-check-circle"></i>
                            <span><strong>${plan.credits_per_day} crédito novo</strong> por dia</span>
                        </div>
                        <div class="feature-item">
                            <i class="fas fa-check-circle"></i>
                            <span><strong>${plan.total_credits} créditos</strong> no total</span>
                        </div>
                        <div class="feature-item">
                            <i class="fas fa-check-circle"></i>
                            <span>Modelos <strong>Scikit-Learn</strong></span>
                        </div>
                    </div>
                    
                    <div id="avisoVagas_${key}"></div>
                    
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

// Selecionar plano (seguro)
async function selectPlan(planId, method) {
    if (isAdmin()) {
        alert('👑 Como administrador, você tem acesso ilimitado.');
        return;
    }
    
    try {
        const response = await fetchWithAuth(`${API_URL}/payments/create-${method}`, {
            method: 'POST',
            body: JSON.stringify({ plan_id: planId })
        });
        
        if (response.ok) {
            const data = await response.json();
            
            if (method === 'pix') {
                // 🔥 NÃO RECEBE MAIS QR CODE DIRETO
                // Agora precisa buscar separadamente
                if (data.payment_id) {
                    showPixModalSecure(data.payment_id, data);
                } else {
                    showNotification('Pagamento iniciado. Verifique o status no dashboard.', 'info');
                    setTimeout(() => {
                        window.location.href = '/dashboard';
                    }, 2000);
                }
            }
        } else {
            const error = await response.json();
            const errorMsg = error.detail || error.message || 'Erro ao criar pagamento';
            showNotification(sanitizeHTML(errorMsg), 'error');
        }
    } catch (error) {
        console.error('Erro:', error);
        showNotification('Erro de conexão. Tente novamente.', 'error');
    }
}

// 🔥 MODAL SEGURO - Buscar QR Code apenas quando necessário
async function showPixModalSecure(paymentId, paymentData) {
    const modalContent = document.getElementById('pixContent');
    
    modalContent.innerHTML = `
        <div class="text-center py-4">
            <div class="spinner-border text-primary mb-3" role="status">
                <span class="visually-hidden">Carregando...</span>
            </div>
            <p>Carregando informações de pagamento...</p>
        </div>
    `;
    
    const modal = new bootstrap.Modal(document.getElementById('pixModal'));
    modal.show();
    
    try {
        // Buscar QR Code de forma segura (após autenticação)
        const response = await fetchWithAuth(`${API_URL}/payments/pix-qrcode/${paymentId}`);
        
        if (response.ok) {
            const qrData = await response.json();
            
            if (qrData.success && qrData.qr_code_base64) {
                modalContent.innerHTML = `
                    ${paymentData.promotional_message ? `
                        <div class="alert alert-warning mb-3 text-center">
                            ${sanitizeHTML(paymentData.promotional_message)}
                        </div>
                    ` : ''}
                    
                    <h6 class="mb-3 text-center">Escaneie o QR Code com seu banco</h6>
                    
                    <div class="text-center mb-3">
                        <img src="data:image/png;base64,${qrData.qr_code_base64}" 
                             class="img-fluid" style="max-width: 200px; border-radius: 12px;">
                    </div>
                    
                    <div class="bg-light p-3 rounded-3 mb-3" style="word-break: break-all;">
                        <code id="pixCodeText" class="small">${sanitizeHTML(qrData.qr_code || 'Código disponível no app do banco')}</code>
                    </div>
                    
                    <button class="btn btn-outline-primary w-100 mb-3" onclick="copyPixCodeSecure()">
                        <i class="fas fa-copy me-2"></i>
                        Copiar código PIX
                    </button>
                    
                    <div class="alert alert-info small">
                        <i class="fas fa-info-circle me-2"></i>
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
                    </div>
                `;
            }
            
            startPaymentPollingSecure(paymentId);
        } else {
            modalContent.innerHTML = `
                <div class="alert alert-danger text-center">
                    <i class="fas fa-exclamation-triangle fa-2x mb-2 d-block"></i>
                    <p>Erro ao carregar informações de pagamento.</p>
                    <button class="btn btn-outline-danger mt-2" onclick="location.reload()">
                        Tentar novamente
                    </button>
                </div>
            `;
        }
    } catch (error) {
        console.error('Erro ao buscar QR Code:', error);
        modalContent.innerHTML = `
            <div class="alert alert-danger text-center">
                <p>Erro de conexão. Tente novamente mais tarde.</p>
            </div>
        `;
    }
}

function copyPixCodeSecure() {
    const codeElement = document.getElementById('pixCodeText');
    if (codeElement) {
        navigator.clipboard.writeText(codeElement.textContent.trim())
            .then(() => showNotification('✅ Código PIX copiado!', 'success'))
            .catch(() => showNotification('❌ Não foi possível copiar', 'error'));
    }
}

let paymentPollingInterval = null;

function startPaymentPollingSecure(paymentId) {
    if (paymentPollingInterval) clearInterval(paymentPollingInterval);
    
    let attempts = 0;
    const maxAttempts = 40; // ~2 minutos
    
    paymentPollingInterval = setInterval(async () => {
        attempts++;
        
        if (attempts > maxAttempts) {
            clearInterval(paymentPollingInterval);
            const statusDiv = document.getElementById('paymentStatus');
            if (statusDiv) {
                statusDiv.innerHTML = `
                    <div class="alert alert-warning">
                        <i class="fas fa-clock me-2"></i>
                        O pagamento está sendo processado. Você receberá os créditos em breve.
                        <a href="/dashboard" class="alert-link">Ir para o Dashboard</a>
                    </div>
                `;
            }
            return;
        }
        
        const response = await fetchWithAuth(`${API_URL}/payments/status/${paymentId}`);
        if (response && response.ok) {
            const data = await response.json();
            
            if (data.payment && data.payment.status === 'approved') {
                clearInterval(paymentPollingInterval);
                const statusDiv = document.getElementById('paymentStatus');
                if (statusDiv) {
                    statusDiv.innerHTML = `
                        <div class="alert alert-success">
                            <i class="fas fa-check-circle me-2"></i>
                            ✅ Pagamento aprovado! Redirecionando...
                        </div>
                    `;
                }
                
                setTimeout(() => {
                    const modal = bootstrap.Modal.getInstance(document.getElementById('pixModal'));
                    if (modal) modal.hide();
                    window.location.href = '/dashboard?payment=success';
                }, 2000);
            }
        }
    }, 3000);
}

// Função segura para mostrar notificações
function showNotification(message, type = 'info') {
    if (window.toastr) {
        toastr[type](sanitizeHTML(message));
    } else {
        alert(sanitizeHTML(message));
    }
}

// Função para fazer requisições com token (segura)
async function fetchWithAuth(url, options = {}) {
    const token = localStorage.getItem('access_token');
    
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };
    
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    
    try {
        const response = await fetch(url, { ...options, headers });
        
        if (response.status === 401) {
            window.location.href = 'login.html';
            return null;
        }
        
        return response;
    } catch (error) {
        console.error('Fetch error:', error);
        return null;
    }
}

// Inicializar
document.addEventListener('DOMContentLoaded', function() {
    if (window.location.pathname.includes('planos.html')) {
        setTimeout(() => {
            loadPlans();
            console.log('✅ payment.js inicializado (versão segura)');
        }, 200);
    }
});

// Funções globais (sem expor dados sensíveis)
window.selectPlan = selectPlan;
window.copyPixCodeSecure = copyPixCodeSecure;