// payment.js - VERSÃO CORRIGIDA COM PROMOÇÃO "DE R$149 POR R$97"
// ==============================================
// CONFIGURAÇÕES GLOBAIS
// ==============================================

const API_URL = window.API_URL || 'http://localhost:8000/api';

// ==============================================
// 🔒 FUNÇÕES DE SEGURANÇA CONTRA XSS
// ==============================================

function sanitizeHTML(str) {
    if (!str) return '';
    if (typeof str !== 'string') str = String(str);
    
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;')
        .replace(/`/g, '&#96;')
        .replace(/\//g, '&#47;');
}

function sanitizeNumber(value, defaultValue = 0) {
    const num = parseFloat(value);
    return isNaN(num) ? defaultValue : num;
}

// ==============================================
// FUNÇÕES DE AUTENTICAÇÃO E USUÁRIO
// ==============================================

function isAdmin() {
    try {
        return window.appAuth ? window.appAuth.isAdmin() : false;
    } catch {
        return false;
    }
}

function getCreditsDisplay() {
    try {
        return window.appAuth ? window.appAuth.getCreditsDisplay() : '0';
    } catch {
        return '0';
    }
}

function formatCreditsDisplay(credits, isPremiumUser = false, maxCredits = 3) {
    const safeCredits = sanitizeNumber(credits, 0);
    const safeMaxCredits = sanitizeNumber(maxCredits, 3);
    
    if (isAdmin()) return '∞';
    if (isPremiumUser) {
        return `${safeCredits}/${safeMaxCredits}`;
    }
    return safeCredits.toString();
}

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
                creditsElement.textContent = displayText;
            }
        }
    } catch (error) {
        console.error('Erro ao atualizar créditos:', error);
    }
}

// ==============================================
// 🔥 CARREGAMENTO DE PLANOS (LAYOUT BRONZE COM PROMOÇÃO)
// ==============================================

async function loadPlans() {
    try {
        const response = await fetch(`${API_URL}/payments/plans`);
        if (response.ok) {
            const data = await response.json();
            renderBronzePlan(data.plans, data);
        } else {
            console.error('Erro ao carregar planos:', response.status);
            showNotification('Erro ao carregar planos. Tente novamente.', 'error');
        }
    } catch (error) {
        console.error('Erro ao carregar planos:', error);
        showNotification('Erro de conexão. Tente novamente.', 'error');
    }
}

// 🔥 RENDERIZAÇÃO EXCLUSIVA DO PLANO BRONZE COM PROMOÇÃO
async function renderBronzePlan(plans, fullData = null) {
    const container = document.getElementById('plansContainer');
    if (!container) return;
    
    // Admin tem acesso ilimitado
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
    
    // Buscar o plano premium_mensal
    const plan = plans['premium_mensal'];
    if (!plan) {
        container.innerHTML = '<div class="text-center text-danger">Erro ao carregar plano. Tente novamente.</div>';
        return;
    }
    
    // Buscar status da promoção
    let vagasRestantes = 100;
    let totalVagas = 100;
    let precoPromocional = 97.00;
    let precoRegular = 149.90;
    let isUserLocked = false;
    let currentPrice = precoPromocional;
    
    try {
        const promoResponse = await fetchWithAuth(`${API_URL}/payments/promotion-status`);
        if (promoResponse && promoResponse.ok) {
            const promoData = await promoResponse.json();
            vagasRestantes = promoData.remaining_slots;
            totalVagas = promoData.total_slots;
            precoPromocional = promoData.promotional_price;
            precoRegular = promoData.regular_price;
            isUserLocked = promoData.user_locked_price !== null;
            currentPrice = promoData.current_price;
        }
    } catch (error) {
        console.warn('Erro ao buscar status da promoção:', error);
    }
    
    const isSoldOut = vagasRestantes <= 0;
    const precoAtual = isSoldOut ? precoRegular : precoPromocional;
    const economia = precoRegular - precoPromocional;
    const vagasUsadas = totalVagas - vagasRestantes;
    const percentual = (vagasUsadas / totalVagas) * 100;
    const isUrgent = vagasRestantes <= 20 && vagasRestantes > 0;
    
    // Se o usuário já tem preço travado, mostrar mensagem especial
    const userHasLockedPrice = isUserLocked;
    
    // 🔥 HTML DO PLANO BRONZE COM LAYOUT DE PROMOÇÃO
    const html = `
        <div class="col-lg-8 mx-auto">
            <div class="bronze-card" data-aos="fade-up" data-aos-duration="800">
                <div class="bronze-badge">
                    <i class="fas fa-fire"></i> ${isSoldOut ? 'PROMOÇÃO ENCERRADA' : (userHasLockedPrice ? 'SEU PREÇO PROMOCIONAL' : 'PROMOÇÃO POR TEMPO LIMITADO')}
                </div>
                
                <div class="bronze-title">
                    <h2>
                        <i class="fas fa-crown me-2"></i>
                        Plano Bronze
                    </h2>
                    <p><i class="fas fa-check-circle me-1"></i> A escolha dos profissionais</p>
                </div>
                
                <div class="price-container">
                    ${!isSoldOut && !userHasLockedPrice ? `
                        <span class="old-price">De R$ ${precoRegular.toFixed(2).replace('.', ',')}</span>
                    ` : ''}
                    <div class="price-tag" id="planoPreco">
                        R$ ${precoAtual.toFixed(2).replace('.', ',')}<small>/mês</small>
                    </div>
                    ${!isSoldOut && !userHasLockedPrice ? `
                        <span class="economy-badge">🔥 ECONOMIZE R$ ${economia.toFixed(2).replace('.', ',')} 🔥</span>
                    ` : ''}
                    ${userHasLockedPrice ? `
                        <span class="economy-badge" style="background: linear-gradient(135deg, #28a745, #20c997);">
                            <i class="fas fa-gem me-1"></i> PREÇO BLOQUEADO - R$ ${precoAtual.toFixed(2).replace('.', ',')}
                        </span>
                    ` : ''}
                </div>
                
                <!-- DIV DE VAGAS - SÓ MOSTRA SE NÃO ESGOTOU E USUÁRIO NÃO TEM PREÇO TRAVADO -->
                ${!isSoldOut && !userHasLockedPrice ? `
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
                        <div class="vagas-progress-bar" style="width: ${percentual}%"></div>
                    </div>
                    ${isUrgent ? `
                        <div class="mt-2 text-center">
                            <strong style="color: #f5a623;">🔥 URGENTE! ÚLTIMAS ${vagasRestantes} VAGAS! 🔥</strong>
                            <br><small>Garanta o preço promocional de R$ ${precoPromocional.toFixed(2).replace('.', ',')}</small>
                        </div>
                    ` : `
                        <div class="mt-2 text-center small text-muted">
                            ${isSoldOut ? 'Promoção esgotada!' : `Apenas as primeiras ${totalVagas} pessoas pagam R$ ${precoPromocional.toFixed(2).replace('.', ',')}`}
                        </div>
                    `}
                </div>
                ` : ''}
                
                ${userHasLockedPrice ? `
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
                
                ${isSoldOut && !userHasLockedPrice ? `
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
                        As 100 vagas promocionais já foram preenchidas. Valor volta para R$ ${precoRegular.toFixed(2).replace('.', ',')}
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
                        <span><strong>Até 3 arquivos por vez</strong> - Processamento em lote</span>
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
                            <div class="small fw-bold mt-1">30 Créditos</div>
                            <div class="small text-muted">Total do plano</div>
                        </div>
                        <div class="col-4">
                            <i class="fas fa-clock fa-lg"></i>
                            <div class="small fw-bold mt-1">30 Dias</div>
                            <div class="small text-muted">Duração</div>
                        </div>
                        <div class="col-4">
                            <i class="fas fa-tachometer-alt fa-lg"></i>
                            <div class="small fw-bold mt-1">3 Máx.</div>
                            <div class="small text-muted">Créditos acumulados</div>
                        </div>
                    </div>
                </div>
                
                <div class="limit-warning">
                    <i class="fas fa-info-circle"></i>
                    <small>⚠️ Limite máximo de <strong>3 créditos acumulados</strong>. Use-os para continuar recebendo novos créditos diários!</small>
                </div>
                
                <div class="d-grid gap-3 mt-4">
                    <button class="btn btn-bronze btn-lg" id="buyButton" onclick="window.selectPlan('premium_mensal', 'pix')">
                        <i class="fas fa-bolt me-2"></i>
                        ${userHasLockedPrice ? 'RENOVAR MEU PLANO' : (isSoldOut ? `COMPRAR POR R$ ${precoAtual.toFixed(2).replace('.', ',')}` : `GARANTIR PREÇO PROMOCIONAL POR R$ ${precoAtual.toFixed(2).replace('.', ',')}`)}
                        <small class="d-block fs-10">Pagamento seguro via PIX</small>
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
                    Após o pagamento, você receberá 1 crédito por dia durante 30 dias
                </p>
            </div>
        </div>
    `;
    
    container.innerHTML = html;
}

// ==============================================
// SELEÇÃO E PAGAMENTO
// ==============================================

async function selectPlan(planId, method) {
    if (isAdmin()) {
        showNotification('👑 Como administrador, você tem acesso ilimitado.', 'info');
        return;
    }
    
    const btn = document.getElementById('buyButton');
    let originalText = '';
    
    if (btn) {
        originalText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i> Processando...';
        
        setTimeout(() => {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        }, 30000);
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
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
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
                
                // Mostrar se foi promoção
                const wasPromotional = paymentData.price_type === 'promotional';
                
                modalContent.innerHTML = `
                    ${wasPromotional ? `
                        <div class="alert alert-success mb-3 text-center">
                            <i class="fas fa-gift me-2"></i>
                            <strong>🎉 VOCÊ GARANTIU O PREÇO PROMOCIONAL!</strong><br>
                            <small>R$ 97,00 - Preço bloqueado para futuras renovações!</small>
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
                        ${wasPromotional ? '<span class="text-success">✅ Você está comprando na promoção! Preço R$ 97,00 garantido para sempre.</span><br>' : ''}
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
                <p class="small text-muted">${sanitizeHTML(error.message || 'Erro desconhecido')}</p>
            </div>
        `;
    }
}

function copyPixCodeSecure() {
    const codeElement = document.getElementById('pixCodeText');
    if (codeElement && codeElement.textContent) {
        const code = codeElement.textContent.trim();
        navigator.clipboard.writeText(code)
            .then(() => showNotification('✅ Código PIX copiado!', 'success'))
            .catch(() => {
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
    const maxAttempts = 60;
    
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
                    
                    await updateCreditsDisplay();
                    
                    // 🔥 Recarregar status da assinatura após pagamento aprovado
                    if (window.loadSubscriptionStatus) {
                        setTimeout(() => {
                            window.loadSubscriptionStatus();
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
// NOTIFICAÇÕES SEGURAS
// ==============================================

function showNotification(message, type = 'info') {
    const safeMessage = sanitizeHTML(message);
    
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
        alert(safeMessage);
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
// 🔥 FUNÇÕES DE STATUS DO PLANO (DATA COMPRA/EXPIRAÇÃO)
// ==============================================

async function loadSubscriptionStatus() {
    /**
     * Carrega o status da assinatura do usuário
     * Mostra data de compra e expiração se for premium
     */
    try {
        const response = await fetchWithAuth(`${API_URL}/payments/subscription-status`);
        
        if (response && response.ok) {
            const data = await response.json();
            
            // Atualizar o card de status do plano
            updatePlanStatusCard(data);
            
            return data;
        }
    } catch (error) {
        console.error('Erro ao carregar status da assinatura:', error);
    }
    return null;
}

function updatePlanStatusCard(subscriptionData) {
    /**
     * Atualiza o card de status do plano na página
     * Mostra se é premium, datas, dias restantes
     */
    const statusContainer = document.getElementById('subscriptionStatusContainer');
    if (!statusContainer) return;
    
    // Se não tem plano premium ativo, esconde o card ou mostra mensagem
    if (!subscriptionData.has_subscription && !subscriptionData.is_admin) {
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
    
    // Admin tem acesso ilimitado
    if (subscriptionData.is_admin) {
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
    
    // Usuário premium - mostrar card com datas
    const daysLeft = subscriptionData.days_left;
    const expiresAt = subscriptionData.expires_at ? new Date(subscriptionData.expires_at) : null;
    const activatedAt = subscriptionData.activated_at ? new Date(subscriptionData.activated_at) : null;
    
    // Formatar datas para exibição
    const formattedActivation = activatedAt ? activatedAt.toLocaleDateString('pt-BR') : '—';
    const formattedExpiration = expiresAt ? expiresAt.toLocaleDateString('pt-BR') : '—';
    
    // Definir cor baseada nos dias restantes
    let statusColor = '#28a745'; // verde
    let statusIcon = '✅';
    let statusText = 'Ativo';
    
    if (daysLeft <= 5 && daysLeft > 0) {
        statusColor = '#f5a623'; // laranja
        statusIcon = '⚠️';
        statusText = 'Próximo do vencimento';
    } else if (daysLeft <= 0) {
        statusColor = '#dc3545'; // vermelho
        statusIcon = '❌';
        statusText = 'Expirado';
    }
    
    // Calcular progresso (dias passados / total de 30 dias)
    let progressPercent = 0;
    if (activatedAt && expiresAt) {
        const totalDays = 30;
        const daysPassed = Math.max(0, Math.min(totalDays, totalDays - daysLeft));
        progressPercent = (daysPassed / totalDays) * 100;
    }
    
    statusContainer.innerHTML = `
        <div class="col-lg-8 mx-auto">
            <div class="premium-status-card" style="background: linear-gradient(135deg, #2c1a0a 0%, #3d2614 100%); border-radius: 20px; padding: 1.5rem; border: 1px solid #cd7f32;">
                <div class="d-flex justify-content-between align-items-start flex-wrap mb-3">
                    <div>
                        <h4 class="mb-1" style="color: #f5a623;">
                            <i class="fas fa-crown me-2"></i>
                            Plano Bronze Ativo
                        </h4>
                        <p class="small mb-0" style="color: rgba(255,255,255,0.7);">
                            <i class="fas fa-check-circle me-1" style="color: #28a745;"></i>
                            Você tem acesso a todos os benefícios premium
                        </p>
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
                                ${formattedActivation}
                            </div>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="p-3 rounded-3" style="background: rgba(0,0,0,0.3);">
                            <small style="color: rgba(255,255,255,0.6);">
                                <i class="fas fa-calendar-times me-1"></i> DATA DE EXPIRAÇÃO
                            </small>
                            <div class="fw-bold" style="color: ${daysLeft <= 5 ? '#f5a623' : '#28a745'}; font-size: 1.1rem;">
                                ${formattedExpiration}
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
                    <strong>Benefícios ativos:</strong> Você recebe <strong>1 crédito novo por dia</strong> (máximo de 3 acumulados) e tem acesso a todas as análises da IA.
                    ${daysLeft <= 5 && daysLeft > 0 ? '<br><i class="fas fa-clock me-1"></i> <strong>Não esqueça de renovar para não perder os benefícios!</strong>' : ''}
                </div>
            </div>
        </div>
    `;
    
    // Se estiver expirado, mostrar botão de renovação destacado
    if (daysLeft <= 0 && !subscriptionData.is_expired_fallback) {
        const buyButton = document.getElementById('buyButton');
        if (buyButton) {
            buyButton.style.animation = 'urgent-pulse 1s ease-in-out infinite';
            buyButton.innerHTML = '<i class="fas fa-exclamation-triangle me-2"></i> RENOVAR PLANO AGORA <small class="d-block fs-10">Seu plano expirou! Clique aqui para renovar</small>';
        }
    }
}

// Função para mostrar notificação de renovação
async function checkAndNotifyRenewal() {
    try {
        const status = await loadSubscriptionStatus();
        
        if (status && status.needs_renewal && !status.is_expired) {
            showNotification(
                `⚠️ Seu plano premium expira em ${status.days_left} dias! Renove agora para não perder o acesso.`,
                'warning'
            );
        }
        
        if (status && status.is_expired) {
            showNotification(
                '❌ Seu plano premium expirou! Renove agora para voltar a ter todos os benefícios.',
                'error'
            );
        }
        
        return status;
    } catch (error) {
        console.error('Erro ao verificar renovação:', error);
    }
}

// ==============================================
// INICIALIZAÇÃO
// ==============================================

function isPlansPage() {
    return window.location.pathname.includes('planos.html') || 
           window.location.pathname === '/planos' ||
           document.getElementById('plansContainer') !== null;
}

document.addEventListener('DOMContentLoaded', function() {
    if (isPlansPage()) {
        setTimeout(() => {
            loadPlans();
            console.log('✅ payment.js inicializado - Layout Bronze com promoção de R$149 por R$97');
        }, 200);
    }
    
    const creditsElement = document.getElementById('creditsDisplay');
    if (creditsElement) {
        updateCreditsDisplay();
        setInterval(updateCreditsDisplay, 30000);
    }
    
    const pixModal = document.getElementById('pixModal');
    if (pixModal) {
        pixModal.addEventListener('hidden.bs.modal', function() {
            if (paymentPollingInterval) {
                clearInterval(paymentPollingInterval);
                paymentPollingInterval = null;
            }
        });
    }
    
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('payment') === 'success') {
        showNotification('Pagamento aprovado! Créditos adicionados à sua conta.', 'success');
        window.history.replaceState({}, document.title, window.location.pathname);
        
        // 🔥 Recarregar status da assinatura após sucesso
        setTimeout(() => {
            if (window.loadSubscriptionStatus) {
                window.loadSubscriptionStatus();
            }
        }, 1000);
    }
});

// ==============================================
// EXPOSIÇÃO DE FUNÇÕES GLOBAIS
// ==============================================

window.selectPlan = selectPlan;
window.copyPixCodeSecure = copyPixCodeSecure;
window.updateCreditsDisplay = updateCreditsDisplay;
window.formatCreditsDisplay = formatCreditsDisplay;
window.showNotification = showNotification;
window.loadSubscriptionStatus = loadSubscriptionStatus;
window.checkAndNotifyRenewal = checkAndNotifyRenewal;

console.log('✅ payment.js carregado - Promoção: R$149 por R$97 (primeiras 100 pessoas)');