// frontend/js/payment.js - Versão com suporte a admin

// Função para verificar se é admin
function isAdmin() {
    const user = JSON.parse(localStorage.getItem('user') || '{}');
    return user.is_admin === true;
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

// Renderizar planos (MODIFICADA)
function renderPlans(plans) {
    const container = document.getElementById('plansContainer');
    if (!container) return;
    
    // Se for admin, mostrar mensagem especial
    if (isAdmin()) {
        container.innerHTML = `
            <div class="col-12">
                <div class="alert alert-warning text-center p-5 rounded-4">
                    <i class="fas fa-crown fa-4x mb-3 text-warning"></i>
                    <h3>👑 Você é Administrador</h3>
                    <p class="lead">Como admin, você tem acesso ilimitado a todas as funcionalidades.</p>
                    <p class="text-muted">Não é necessário comprar planos ou créditos.</p>
                </div>
            </div>
        `;
        return;
    }
    
    // Render normal para usuários comuns
    let html = '';
    
    for (const [key, plan] of Object.entries(plans)) {
        const popularClass = plan.popular ? 'popular' : '';
        
        html += `
            <div class="col-lg-4">
                <div class="card plan-card ${popularClass}">
                    ${plan.popular ? '<div class="popular-badge">MAIS POPULAR</div>' : ''}
                    <div class="plan-header ${key}">
                        <h3 class="h4 mb-3">${plan.name}</h3>
                        <div class="plan-price">
                            R$ ${plan.price.toFixed(2).replace('.', ',')}
                        </div>
                        <p class="mb-0">${plan.credits} créditos</p>
                    </div>
                    <div class="plan-features">
                        <div class="plan-feature">
                            <i class="fas fa-check-circle text-success"></i>
                            <strong>${plan.credits}</strong> análises
                        </div>
                        <div class="plan-feature">
                            <i class="fas fa-check-circle text-success"></i>
                            Relatórios com IA
                        </div>
                        <div class="plan-feature">
                            <i class="fas fa-check-circle text-success"></i>
                            Previsões Scikit-Learn
                        </div>
                        
                        <div class="d-grid gap-2 mt-4">
                            <button class="btn btn-primary" onclick="selectPlan('${key}', 'pix')">
                                <i class="fas fa-qrcode me-2"></i>
                                PIX
                            </button>
                            <button class="btn btn-outline-primary" onclick="selectPlan('${key}', 'checkout')">
                                <i class="fas fa-credit-card me-2"></i>
                                Outros métodos
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    container.innerHTML = html;
}

// Selecionar plano (MODIFICADA)
async function selectPlan(planId, method) {
    // Admin não precisa comprar
    if (isAdmin()) {
        alert('👑 Como administrador, você tem acesso ilimitado. Não é necessário comprar planos.');
        return;
    }
    
    try {
        if (method === 'pix') {
            const response = await fetchWithAuth(`${API_URL}/payments/create-pix`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ plan_id: planId })
            });
            
            if (response.ok) {
                const data = await response.json();
                showPixModal(data);
            } else {
                const error = await response.json();
                alert(error.detail || 'Erro ao criar pagamento');
            }
        } else {
            const response = await fetchWithAuth(`${API_URL}/payments/create-checkout`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ plan_id: planId })
            });
            
            if (response.ok) {
                const data = await response.json();
                window.location.href = `/checkout.html?url=${encodeURIComponent(data.checkout_url)}`;
            } else {
                const error = await response.json();
                alert(error.detail || 'Erro ao criar pagamento');
            }
        }
    } catch (error) {
        console.error('Erro:', error);
        alert('Erro de conexão com o servidor');
    }
}

// Mostrar modal PIX (mantida)
function showPixModal(data) {
    const modal = new bootstrap.Modal(document.getElementById('pixModal'));
    
    const content = document.getElementById('pixContent');
    content.innerHTML = `
        <h6 class="mb-3">Escaneie o QR Code com seu banco</h6>
        
        ${data.qr_code_base64 ? `
            <img src="data:image/png;base64,${data.qr_code_base64}" class="qr-code-img mb-3">
        ` : ''}
        
        <div class="pix-code" id="pixCode">
            ${data.qr_code || 'Código indisponível'}
        </div>
        
        <button class="btn btn-outline-primary w-100 mb-3" onclick="copyPixCode()">
            <i class="fas fa-copy me-2"></i>
            Copiar código
        </button>
        
        <div class="alert alert-info small">
            <i class="fas fa-info-circle me-2"></i>
            Após o pagamento, aguarde até 1 minuto.
        </div>
        
        <div id="paymentStatus"></div>
    `;
    
    modal.show();
    startPaymentPolling(data.payment_id);
}

// Copiar código PIX (mantida)
function copyPixCode() {
    const pixCode = document.getElementById('pixCode');
    if (pixCode) {
        navigator.clipboard.writeText(pixCode.textContent.trim());
        alert('Código copiado!');
    }
}

// Verificar status do pagamento (mantida)
let paymentPolling = null;

function startPaymentPolling(paymentId) {
    if (paymentPolling) clearInterval(paymentPolling);
    
    paymentPolling = setInterval(async () => {
        await checkPaymentStatus(paymentId);
    }, 3000);
}

async function checkPaymentStatus(paymentId) {
    try {
        const response = await fetchWithAuth(`${API_URL}/payments/status/${paymentId}`);
        
        if (response.ok) {
            const data = await response.json();
            
            if (data.payment.status === 'approved') {
                clearInterval(paymentPolling);
                
                document.getElementById('paymentStatus').innerHTML = `
                    <div class="alert alert-success">
                        <i class="fas fa-check-circle me-2"></i>
                        Pagamento aprovado!
                    </div>
                `;
                
                setTimeout(() => {
                    const modal = bootstrap.Modal.getInstance(document.getElementById('pixModal'));
                    if (modal) modal.hide();
                    window.location.href = '/dashboard?success=1';
                }, 3000);
            }
        }
    } catch (error) {
        console.error('Erro:', error);
    }
}

// Função para fazer requisições com token (adicionada)
async function fetchWithAuth(url, options = {}) {
    const token = localStorage.getItem('access_token');
    
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };
    
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    
    const response = await fetch(url, { ...options, headers });
    
    if (response.status === 401) {
        // Redirecionar para login
        window.location.href = 'login.html';
    }
    
    return response;
}

// Inicializar na página de planos
document.addEventListener('DOMContentLoaded', function() {
    if (window.location.pathname.includes('planos.html')) {
        loadPlans();
    }
});