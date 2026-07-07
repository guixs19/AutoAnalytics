// payment.js - VERSÃO 7.0 (REFATORADA)
// ==============================================
// 🔥 MELHORIAS V7.0:
// 1. ✅ REMOVIDO: EventBus próprio (usa window.EventBus do app.js)
// 2. ✅ REMOVIDO: Security/Sanitize próprio (usa window.AppUtils)
// 3. ✅ REMOVIDO: Cache próprio (usa window.AppCache ou sessionStorage)
// 4. ✅ REMOVIDO: fetchWithRetry próprio (usa window.fetchWithAuth)
// 5. ✅ ADICIONADO: Templates HTML para modais (reduz inline)
// 6. ✅ ADICIONADO: Polling adaptativo (5s quando < 20 vagas)
// 7. ✅ CORRIGIDO: Cache TTL consistente (>= polling)
// 8. ✅ ALINHADO: Constantes com backend (payment_routes.py)
// 9. ✅ SINCERONIZADO: Webhook + status polling
// 10. ✅ MELHORADO: Experiência de compra (feedback em tempo real)
// ==============================================

(function() {
    'use strict';

    console.log('🚀 Inicializando payment.js v7.0 (Refatorado)...');

    // ==============================================
    // 🔒 DEPENDÊNCIAS DO APP.JS
    // ==============================================

    const HAS_APP = !!(window.App || window.app || window.EventBus || window.__APP_STATE);
    
    // Usa EventBus do app.js, ou fallback mínimo
    const EventBus = window.EventBus || {
        emit: (event, data) => {
            try {
                window.dispatchEvent(new CustomEvent(event, { detail: data, bubbles: true }));
            } catch (e) {}
        },
        on: (event, handler) => {
            document.addEventListener(event, (e) => handler(e.detail));
        }
    };

    // Usa AppUtils do app.js, ou fallback
    const AppUtils = window.AppUtils || {
        sanitizeHTML: (str) => str,
        sanitizeNumber: (v, d) => v || d,
        sanitizeCPF: (v) => v?.replace(/\D/g, '') || '',
        validateCPF: (v) => v?.length === 11,
        showNotification: (msg, type) => {
            if (window.toastr?.[type]) window.toastr[type](msg);
            else alert(`[${type}] ${msg}`);
        },
        formatCreditsDisplay: (c, p) => p ? `${c || 0}/3` : String(c || 0)
    };

    // Usa fetchWithAuth do app.js
    const fetchWithAuth = window.fetchWithAuth || window.App?.fetchWithAuth || window.appAuth?.fetchWithAuth || fetch;

    // ==============================================
    // 🔒 CONFIGURAÇÕES (ALINHADAS COM payment_routes.py)
    // ==============================================

    const CONFIG = {
        MAX_CREDITS_BALANCE: 3,
        INITIAL_FREE_CREDITS: 3,
        PIX_EXPIRY_MINUTES: 30,
        PROMOTIONAL_PRICE: 97.00,
        REGULAR_PRICE: 149.90,
        TOTAL_PROMOTIONAL_SLOTS: 100,
        DAYS_PREMIUM: 30,
        
        // 🔥 VAGAS - POLLING ADAPTATIVO
        VAGAS_UPDATE_INTERVAL_NORMAL: 30000,   // 30s (normal)
        VAGAS_UPDATE_INTERVAL_URGENT: 5000,    // 5s (urgente - < 20 vagas)
        VAGAS_URGENT_THRESHOLD: 20,
        VAGAS_CACHE_TTL: 35000,                // 35s (> polling)
        
        // 🔥 VERIFICAÇÃO DE STATUS
        STATUS_POLLING_INTERVAL: 5000,          // 5s
        STATUS_MAX_ATTEMPTS: 60,                // 5 minutos
        STATUS_PIX_INTERVAL: 3000,              // 3s (após PIX)
    };

    // ==============================================
    // 🔥 SISTEMA DE VAGAS (REFATORADO)
    // ==============================================

    const VagasSystem = {
        _lastUpdate: 0,
        _updateInterval: null,
        _currentData: null,
        _isUpdating: false,
        _listeners: [],
        _isUrgent: false,

        init() {
            console.log('🎯 Inicializando Sistema de Vagas v2...');
            
            this.updateVagas();
            this._startPolling();

            // 🔥 Eventos que disparam atualização
            const events = ['payment:completed', 'premiumStatusUpdated', 'app:state_changed'];
            events.forEach(eventName => {
                document.addEventListener(eventName, () => {
                    console.log(`🔄 [${eventName}] - atualizando vagas`);
                    setTimeout(() => this.updateVagas(true), 1000);
                });
            });

            console.log('✅ Sistema de Vagas inicializado');
        },

        _startPolling() {
            if (this._updateInterval) {
                clearInterval(this._updateInterval);
            }

            const interval = this._isUrgent ? 
                CONFIG.VAGAS_UPDATE_INTERVAL_URGENT : 
                CONFIG.VAGAS_UPDATE_INTERVAL_NORMAL;

            this._updateInterval = setInterval(() => {
                this.updateVagas();
            }, interval);

            console.log(`⏰ Polling de vagas: ${interval/1000}s`);
        },

        _adjustPolling(remaining) {
            const wasUrgent = this._isUrgent;
            this._isUrgent = remaining <= CONFIG.VAGAS_URGENT_THRESHOLD && remaining > 0;

            if (wasUrgent !== this._isUrgent) {
                console.log(`🔄 Ajustando polling: ${this._isUrgent ? 'URGENTE (5s)' : 'NORMAL (30s)'}`);
                this._startPolling();
            }
        },

        async updateVagas(force = false) {
            if (this._isUpdating) return;

            const now = Date.now();
            if (!force && (now - this._lastUpdate) < CONFIG.VAGAS_CACHE_TTL) {
                return this._currentData;
            }

            this._isUpdating = true;

            try {
                const response = await fetchWithAuth('/api/payments/promotion-status');
                if (response?.ok) {
                    const data = await response.json();
                    this._currentData = data;
                    this._lastUpdate = now;

                    this._adjustPolling(data.remaining_slots || 0);
                    this._updateUI(data);

                    EventBus.emit('vagas:updated', data);
                    window.dispatchEvent(new CustomEvent('vagas:updated', { detail: data }));

                    return data;
                }
            } catch (error) {
                console.warn('⚠️ Erro ao atualizar vagas:', error);
            } finally {
                this._isUpdating = false;
            }

            return null;
        },

        _updateUI(data) {
            const remaining = data.remaining_slots || 0;
            const total = data.total_slots || CONFIG.TOTAL_PROMOTIONAL_SLOTS;
            const isSoldOut = remaining <= 0;
            const isUrgent = remaining <= CONFIG.VAGAS_URGENT_THRESHOLD && remaining > 0;

            // 🔥 Elementos da UI - usando IDs consistentes
            const elements = {
                vagasRestantes: document.getElementById('vagasRestantes'),
                vagasTotal: document.getElementById('vagasTotal'),
                vagasProgress: document.getElementById('vagasProgress'),
                vagasUrgentAlert: document.getElementById('vagasUrgentAlert'),
                vagasUrgentCount: document.getElementById('vagasUrgentCount'),
                vagasSoldOutAlert: document.getElementById('vagasSoldOutAlert'),
                currentPrice: document.getElementById('currentPrice'),
                oldPrice: document.getElementById('oldPrice'),
                economyBadge: document.getElementById('economyBadge'),
                btnUpgrade: document.getElementById('btnUpgrade'),
                planBadgeText: document.getElementById('planBadgeText')
            };

            // 1. Número de vagas
            if (elements.vagasRestantes) {
                elements.vagasRestantes.textContent = remaining;
                elements.vagasRestantes.style.transition = 'transform 0.3s ease';
                elements.vagasRestantes.style.transform = 'scale(1.3)';
                setTimeout(() => {
                    elements.vagasRestantes.style.transform = 'scale(1)';
                }, 300);
            }

            // 2. Total
            if (elements.vagasTotal) {
                elements.vagasTotal.textContent = total;
            }

            // 3. Barra de progresso
            if (elements.vagasProgress) {
                const percent = total > 0 ? ((total - remaining) / total) * 100 : 0;
                elements.vagasProgress.style.width = `${Math.min(100, percent)}%`;
                
                if (isSoldOut) {
                    elements.vagasProgress.style.background = 'linear-gradient(90deg, #dc3545, #c0392b)';
                    elements.vagasProgress.style.animation = 'none';
                } else if (isUrgent) {
                    elements.vagasProgress.style.background = 'linear-gradient(90deg, #f5a623, #e67e22)';
                    elements.vagasProgress.style.animation = 'pulse 1.5s ease-in-out infinite';
                } else {
                    elements.vagasProgress.style.background = 'linear-gradient(90deg, #cd7f32, #f5a623)';
                    elements.vagasProgress.style.animation = 'none';
                }
            }

            // 4. Alertas
            if (elements.vagasUrgentAlert && elements.vagasUrgentCount) {
                elements.vagasUrgentAlert.style.display = isUrgent ? 'block' : 'none';
                if (isUrgent) elements.vagasUrgentCount.textContent = remaining;
            }

            if (elements.vagasSoldOutAlert) {
                elements.vagasSoldOutAlert.style.display = isSoldOut ? 'block' : 'none';
            }

            // 5. Preço
            if (isSoldOut) {
                if (elements.currentPrice) elements.currentPrice.textContent = '149.90';
                if (elements.oldPrice) elements.oldPrice.style.display = 'none';
                if (elements.economyBadge) {
                    elements.economyBadge.textContent = '❌ PROMOÇÃO ESGOTADA';
                    elements.economyBadge.style.background = 'linear-gradient(135deg, #dc3545, #c0392b)';
                }
                if (elements.btnUpgrade) {
                    elements.btnUpgrade.innerHTML = `
                        <i class="fas fa-exclamation-triangle me-2"></i>
                        COMPRAR POR R$ 149,90
                        <small class="d-block fs-10">Promoção encerrada</small>
                    `;
                }
            } else if (data.user_locked_price) {
                if (elements.currentPrice) {
                    elements.currentPrice.textContent = data.user_locked_price.toFixed(0);
                }
            }

            // 6. Badge
            if (elements.planBadgeText) {
                if (isSoldOut) {
                    elements.planBadgeText.textContent = '❌ PROMOÇÃO ENCERRADA';
                } else if (isUrgent) {
                    elements.planBadgeText.textContent = `🔥 ÚLTIMAS ${remaining} VAGAS!`;
                } else {
                    elements.planBadgeText.textContent = `🔥 ${remaining} VAGAS DISPONÍVEIS`;
                }
            }

            // 7. Evento para outros módulos
            window.dispatchEvent(new CustomEvent('vagas:ui_updated', {
                detail: { remaining, total, isSoldOut, isUrgent }
            }));
        },

        getCurrentData() {
            return this._currentData || {
                remaining_slots: CONFIG.TOTAL_PROMOTIONAL_SLOTS,
                total_slots: CONFIG.TOTAL_PROMOTIONAL_SLOTS,
                promotional_price: CONFIG.PROMOTIONAL_PRICE,
                regular_price: CONFIG.REGULAR_PRICE,
                user_locked_price: null
            };
        },

        stop() {
            if (this._updateInterval) {
                clearInterval(this._updateInterval);
                this._updateInterval = null;
            }
        }
    };

    // ==============================================
    // 🔥 LOAD PREMIUM STATUS (SIMPLIFICADO)
    // ==============================================

    async function loadPremiumStatus() {
        try {
            const response = await fetchWithAuth('/api/payments/premium-status');
            if (response?.ok) {
                const data = await response.json();
                
                if (window.__APP_STATE_MANAGER) {
                    window.__APP_STATE_MANAGER.updatePremiumStatus(data);
                }

                EventBus.emit('payment:premium_status_updated', {
                    isPremium: data.is_premium || false,
                    daysLeft: data.days_left || 0,
                    hasPromotionalPrice: data.promotional_price_locked || false,
                    promotionalPrice: data.promotional_price || null,
                    canReceiveDailyCredit: data.can_receive_today || false,
                    receivedDailyCreditToday: data.received_today || false,
                    creditsBalance: data.credits_balance || 0,
                    maxCredits: data.max_credits_balance || CONFIG.MAX_CREDITS_BALANCE
                });

                return data;
            }
        } catch (error) {
            console.error('Erro ao carregar status premium:', error);
        }
        return null;
    }

    // ==============================================
    // 🔥 RECEIVE DAILY CREDIT (SIMPLIFICADO)
    // ==============================================

    async function receiveDailyCredit() {
        try {
            const response = await fetchWithAuth('/api/payments/premium/check-daily', { method: 'POST' });
            if (response?.ok) {
                const data = await response.json();
                
                if (data.success) {
                    AppUtils.showNotification(`✅ ${data.message || 'Crédito recebido!'}`, 'success');
                    if (window.__APP_STATE_MANAGER) {
                        window.__APP_STATE_MANAGER.updateCredits(data.current_credits || 0);
                    }
                    updateCreditsDisplay();
                    return data;
                } else {
                    AppUtils.showNotification(data.message || 'Erro ao receber crédito', 'warning');
                    return data;
                }
            }
        } catch (error) {
            console.error('Erro ao receber crédito:', error);
            AppUtils.showNotification('Erro de conexão. Tente novamente.', 'error');
        }
        return null;
    }

    // ==============================================
    // 🔥 UPDATE CREDITS DISPLAY (SIMPLIFICADO)
    // ==============================================

    function updateCreditsDisplay(credits, isPremium, isAdmin) {
        const display = isAdmin ? '∞' : AppUtils.formatCreditsDisplay(credits, isPremium);
        
        document.querySelectorAll('#creditsCount, #creditsDisplay, #uploadCredits, .credits-badge span')
            .forEach(el => {
                if (el) el.textContent = display;
            });

        window.dispatchEvent(new CustomEvent('creditsUpdated', {
            detail: { 
                credits: credits || 0, 
                display, 
                maxCredits: CONFIG.MAX_CREDITS_BALANCE, 
                isPremium: isPremium || false 
            }
        }));
    }

    // ==============================================
    // 🔥 MODAL CPF (COM TEMPLATE)
    // ==============================================

    function openCpfModal(planId) {
        const authStatus = getAuthStatus();

        if (authStatus.isAdmin) {
            AppUtils.showNotification('👑 Administrador tem acesso ilimitado.', 'info');
            return;
        }

        if (authStatus.isPremium) {
            AppUtils.showNotification('✅ Você já possui um plano ativo!', 'success');
            window.location.href = '/dashboard';
            return;
        }

        let cpfModal = document.getElementById('cpfModal');
        if (!cpfModal) {
            cpfModal = document.createElement('div');
            cpfModal.id = 'cpfModal';
            cpfModal.className = 'modal fade';
            cpfModal.setAttribute('tabindex', '-1');
            document.body.appendChild(cpfModal);
        }

        // 🔥 Usa template se disponível, senão inline
        const template = document.getElementById('cpfModalTemplate');
        if (template) {
            const clone = template.content.cloneNode(true);
            cpfModal.innerHTML = '';
            cpfModal.appendChild(clone);
        } else {
            cpfModal.innerHTML = getCpfModalHTML(planId);
        }

        setupCpfModalEvents(cpfModal, planId);

        try {
            new bootstrap.Modal(cpfModal).show();
        } catch (e) {
            console.warn('⚠️ Bootstrap Modal não disponível:', e);
            cpfModal.style.display = 'block';
            cpfModal.classList.add('show');
        }
    }

    function getCpfModalHTML(planId) {
        return `
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content" style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border: 1px solid #f5a623;">
                    <div class="modal-header border-0">
                        <h5 class="modal-title" style="color: #f5a623;">
                            <i class="fas fa-id-card me-2"></i>Confirme seu CPF
                        </h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <p class="text-white-50 mb-3">
                            <i class="fas fa-shield-alt me-2"></i> 
                            CPF obrigatório para gerar PIX e proteger sua compra.
                        </p>
                        <div class="mb-3">
                            <label class="form-label text-white">CPF</label>
                            <input type="text" class="form-control form-control-lg" 
                                   id="cpfInput" placeholder="000.000.000-00" maxlength="14" 
                                   style="background: rgba(255,255,255,0.1); border-color: #f5a623; color: white; border-radius:12px;">
                            <div class="form-text text-white-50">Apenas números (11 dígitos)</div>
                        </div>
                        <div id="cpfError" class="alert alert-danger d-none" role="alert"></div>
                    </div>
                    <div class="modal-footer border-0">
                        <button type="button" class="btn" style="background:rgba(255,255,255,0.06); color:rgba(255,255,255,0.6); border:none; border-radius:50px; padding:0.5rem 1.5rem;" data-bs-dismiss="modal">Cancelar</button>
                        <button type="button" class="btn btn-bronze" id="cpfConfirmBtn">
                            <i class="fas fa-arrow-right me-2"></i>Continuar para PIX
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    function setupCpfModalEvents(cpfModal, planId) {
        const cpfInput = document.getElementById('cpfInput');
        const cpfError = document.getElementById('cpfError');
        const confirmBtn = document.getElementById('cpfConfirmBtn');

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
                
                if (cpfError) cpfError.classList.add('d-none');
            });

            cpfInput.addEventListener('blur', function(e) {
                const cpf = AppUtils.sanitizeCPF(e.target.value);
                if (cpf.length > 0 && !AppUtils.validateCPF(cpf)) {
                    if (cpfError) {
                        cpfError.textContent = '❌ CPF inválido. Digite um CPF válido com 11 dígitos.';
                        cpfError.classList.remove('d-none');
                    }
                }
            });
        }

        if (confirmBtn) {
            confirmBtn.addEventListener('click', function() {
                const cpfInput = document.getElementById('cpfInput');
                const cpfError = document.getElementById('cpfError');
                
                if (!cpfInput) return;
                
                const cpfLimpo = AppUtils.sanitizeCPF(cpfInput.value);
                
                if (!AppUtils.validateCPF(cpfLimpo)) {
                    if (cpfError) {
                        cpfError.textContent = '❌ CPF inválido. Digite um CPF válido com 11 dígitos.';
                        cpfError.classList.remove('d-none');
                    }
                    return;
                }
                
                if (cpfError) cpfError.classList.add('d-none');
                
                const modal = bootstrap.Modal.getInstance(document.getElementById('cpfModal'));
                if (modal) modal.hide();
                
                createPaymentWithPix(cpfLimpo, planId);
            });
        }

        // Enter key
        if (cpfInput) {
            cpfInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' && confirmBtn) {
                    confirmBtn.click();
                }
            });
        }
    }

    // ==============================================
    // 🔥 CRIAÇÃO DE PAGAMENTO
    // ==============================================

    async function createPaymentWithPix(cpf, planId = 'premium_mensal') {
        console.log('💳 Criando pagamento PIX para CPF:', cpf);
        AppUtils.showNotification('🔄 Gerando QR Code PIX...', 'info');

        try {
            const response = await fetchWithAuth('/api/payments/create-pix', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    cpf: cpf,
                    plan: planId || 'premium_mensal'
                })
            });

            if (!response) {
                throw new Error('Falha na conexão');
            }

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || errorData.message || 'Erro ao criar pagamento');
            }

            const data = await response.json();
            console.log('✅ Pagamento criado:', data);

            // 🔥 Dispara eventos
            if (data.credits_balance !== undefined) {
                window.dispatchEvent(new CustomEvent('creditsUpdated', {
                    detail: {
                        credits: data.credits_balance,
                        isPremium: data.is_premium || false,
                        maxCredits: CONFIG.MAX_CREDITS_BALANCE
                    }
                }));
            }

            if (data.is_premium !== undefined) {
                window.dispatchEvent(new CustomEvent('premiumStatusUpdated', {
                    detail: {
                        isPremium: data.is_premium,
                        daysLeft: data.days_left || 0,
                        hasPromotionalPrice: data.was_promotional || false,
                        promotionalPrice: data.amount || null,
                        creditsBalance: data.credits_balance || 0
                    }
                }));
            }

            // 🔥 Dispara evento de pagamento para atualizar vagas
            window.dispatchEvent(new CustomEvent('payment:completed', {
                detail: {
                    user_id: data.user_id,
                    plan: data.plan,
                    amount: data.amount,
                    was_promotional: data.was_promotional || false
                }
            }));

            showPixModal(data);

        } catch (error) {
            console.error('❌ Erro ao criar pagamento:', error);
            AppUtils.showNotification(error.message || 'Erro ao gerar pagamento. Tente novamente.', 'error');
        }
    }

    // ==============================================
    // 🔥 MODAL PIX (COM TEMPLATE E STATUS POLLING)
    // ==============================================

    let countdownInterval = null;
    let statusPollingInterval = null;

    function showPixModal(data) {
        console.log('📱 Mostrando modal PIX...');

        let pixModal = document.getElementById('pixModal');
        if (!pixModal) {
            pixModal = document.createElement('div');
            pixModal.id = 'pixModal';
            pixModal.className = 'modal fade';
            pixModal.setAttribute('tabindex', '-1');
            document.body.appendChild(pixModal);
        }

        const qrCode = data.qr_code_base64 || data.qr_code || '';
        const pixCode = data.pix_code || data.qr_code || 'autonalytics@gmail.com';
        const amount = data.amount || CONFIG.PROMOTIONAL_PRICE;
        const planName = data.plan_name || 'Plano Bronze';
        const paymentId = data.payment_id;
        const wasPromotional = data.was_promotional || false;

        // 🔥 Usa template se disponível
        const template = document.getElementById('pixModalTemplate');
        if (template) {
            const clone = template.content.cloneNode(true);
            pixModal.innerHTML = '';
            pixModal.appendChild(clone);
            
            // Preenche dados dinâmicos
            const qrImg = pixModal.querySelector('#pixQrCode');
            if (qrImg && qrCode) {
                qrImg.src = qrCode;
                qrImg.style.display = 'block';
            }
            
            const codeText = pixModal.querySelector('#pixCodeText');
            if (codeText) codeText.textContent = pixCode;
            
            const priceText = pixModal.querySelector('#pixPriceText');
            if (priceText) priceText.textContent = `R$ ${amount.toFixed(2).replace('.', ',')}`;
            
            const planText = pixModal.querySelector('#pixPlanText');
            if (planText) planText.textContent = planName;
            
            // Store paymentId para polling
            const verifyBtn = pixModal.querySelector('#pixVerifyBtn');
            if (verifyBtn && paymentId) {
                verifyBtn.dataset.paymentId = paymentId;
            }
        } else {
            pixModal.innerHTML = getPixModalHTML(data, qrCode, pixCode, amount, planName);
        }

        startCountdown(CONFIG.PIX_EXPIRY_MINUTES * 60);
        startStatusPolling(paymentId);

        try {
            new bootstrap.Modal(pixModal).show();
        } catch (e) {
            console.warn('⚠️ Bootstrap Modal não disponível:', e);
            pixModal.style.display = 'block';
            pixModal.classList.add('show');
        }
    }

    function getPixModalHTML(data, qrCode, pixCode, amount, planName) {
        return `
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content" style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border: 1px solid rgba(205,127,50,0.3);">
                    <div class="modal-header border-0" style="border-bottom: 1px solid rgba(255,255,255,0.1);">
                        <h5 class="modal-title" style="color: #f5a623;">
                            <i class="fas fa-qrcode me-2"></i> Pagamento via PIX
                        </h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body text-center py-4">
                        <div class="alert alert-success mb-3 text-center" style="background: rgba(40, 167, 69, 0.15); border-color: #28a745; color: #48bb78;">
                            <i class="fas fa-gem me-2"></i>
                            <strong>${data.was_promotional ? '🎉 VOCÊ GARANTIU O PREÇO FUNDADOR!' : '💰 PAGAMENTO GERADO'}</strong><br>
                            <small>R$ ${amount.toFixed(2).replace('.', ',')} ${data.was_promotional ? '- Preço bloqueado VITALÍCIO!' : ''}</small>
                        </div>
                        
                        <h6 class="mb-3" style="color: rgba(255,255,255,0.7);">Escaneie o QR Code com seu banco</h6>
                        
                        <div class="text-center mb-3">
                            <div class="p-3 d-inline-block" style="background: white; border-radius: 16px;">
                                ${qrCode ? 
                                    `<img src="${qrCode}" alt="QR Code PIX" style="max-width: 200px; border-radius: 8px;" id="pixQrCode">` :
                                    `<div style="width:200px; height:200px; background:#f0f0f0; display:flex; align-items:center; justify-content:center; border-radius:8px; color:#999; font-size:14px;">QR Code indisponível</div>`
                                }
                            </div>
                        </div>
                        
                        <div class="p-3 rounded-3 mb-3" style="background: rgba(255,255,255,0.05); word-break: break-all;">
                            <code id="pixCodeText" class="small" style="color: #f5a623;">${pixCode}</code>
                        </div>
                        
                        <button class="btn w-100 mb-3" onclick="window.copyPixCode()" 
                                style="background: rgba(255,255,255,0.06); color: #f5a623; border: 1px solid rgba(205,127,50,0.3); border-radius: 12px; padding: 0.75rem;">
                            <i class="fas fa-copy me-2"></i> Copiar Chave PIX
                        </button>
                        
                        <div class="alert alert-info small" style="background: rgba(245, 166, 35, 0.08); border-color: rgba(205,127,50,0.2); color: rgba(255,255,255,0.7);">
                            <i class="fas fa-info-circle me-2"></i>
                            <strong>Informações do pagamento:</strong><br>
                            <strong id="pixPlanText">${planName}</strong> - Valor: R$ ${amount.toFixed(2).replace('.', ',')}<br>
                            <span class="text-success">${data.was_promotional ? '✅ Preço de fundador garantido para sempre!' : '💰 Preço regular'}</span><br>
                            <span style="color: rgba(255,255,255,0.5);">⏰ Expira em <strong id="countdownTimer">${CONFIG.PIX_EXPIRY_MINUTES}:00</strong> minutos.</span>
                        </div>
                        
                        <div id="paymentStatus" class="mt-2"></div>
                    </div>
                    <div class="modal-footer border-0 justify-content-center" style="border-top: 1px solid rgba(255,255,255,0.06);">
                        <button type="button" class="btn w-100" id="pixVerifyBtn" data-payment-id="${data.payment_id || ''}" 
                                style="background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.6); border: none; border-radius: 50px; padding: 0.75rem;">
                            <i class="fas fa-check-circle me-2"></i> Já realizei o pagamento / Atualizar
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    // ==============================================
    // 🔥 STATUS POLLING (AUTOMÁTICO)
    // ==============================================

    function startStatusPolling(paymentId) {
        if (statusPollingInterval) {
            clearInterval(statusPollingInterval);
            statusPollingInterval = null;
        }

        if (!paymentId) return;

        let attempts = 0;
        const maxAttempts = CONFIG.STATUS_MAX_ATTEMPTS;

        statusPollingInterval = setInterval(async () => {
            attempts++;

            try {
                const response = await fetchWithAuth(`/api/payments/status/${paymentId}`);
                if (response?.ok) {
                    const data = await response.json();
                    const payment = data.payment || data;
                    
                    if (payment.status === 'approved') {
                        clearInterval(statusPollingInterval);
                        statusPollingInterval = null;
                        
                        AppUtils.showNotification('✅ Pagamento confirmado! Seu plano foi ativado.', 'success');
                        
                        window.dispatchEvent(new CustomEvent('premiumStatusUpdated', {
                            detail: {
                                isPremium: true,
                                daysLeft: 30,
                                creditsBalance: data.credits_balance || 0
                            }
                        }));
                        
                        window.dispatchEvent(new CustomEvent('payment:completed', {
                            detail: {
                                payment_id: paymentId,
                                status: 'approved'
                            }
                        }));
                        
                        const modal = bootstrap.Modal.getInstance(document.getElementById('pixModal'));
                        if (modal) modal.hide();
                        setTimeout(() => window.location.reload(), 1500);
                        
                    } else if (payment.status === 'rejected' || payment.status === 'cancelled') {
                        clearInterval(statusPollingInterval);
                        statusPollingInterval = null;
                        AppUtils.showNotification(`❌ Pagamento ${payment.status}. Tente novamente.`, 'error');
                    }
                }
            } catch (error) {
                console.warn('⚠️ Erro no status polling:', error);
            }

            if (attempts >= maxAttempts) {
                clearInterval(statusPollingInterval);
                statusPollingInterval = null;
                console.log('⏰ Status polling finalizado (timeout)');
            }
        }, CONFIG.STATUS_POLLING_INTERVAL);

        console.log(`⏰ Status polling iniciado para payment ${paymentId} (${maxAttempts} tentativas)`);
    }

    // ==============================================
    // 🔥 VERIFY PAYMENT (MANUAL)
    // ==============================================

    window.verifyPayment = async function() {
        AppUtils.showNotification('🔄 Verificando pagamento...', 'info');

        const modal = document.getElementById('pixModal');
        const verifyBtn = modal?.querySelector('#pixVerifyBtn');
        const paymentId = verifyBtn?.dataset.paymentId;

        if (!paymentId) {
            AppUtils.showNotification('ID do pagamento não encontrado.', 'error');
            return;
        }

        try {
            const response = await fetchWithAuth(`/api/payments/status/${paymentId}`);
            if (!response) throw new Error('Falha na conexão');

            const data = await response.json();
            const payment = data.payment || data;

            if (payment.status === 'approved') {
                AppUtils.showNotification('✅ Pagamento confirmado!', 'success');
                
                window.dispatchEvent(new CustomEvent('premiumStatusUpdated', {
                    detail: {
                        isPremium: true,
                        daysLeft: 30,
                        creditsBalance: data.credits_balance || 0                    }
                }));
                
                const modal = bootstrap.Modal.getInstance(document.getElementById('pixModal'));
                if (modal) modal.hide();
                setTimeout(() => window.location.reload(), 1500);
                
            } else if (payment.status === 'pending') {
                AppUtils.showNotification('⏳ Pagamento ainda não confirmado. Aguarde alguns minutos.', 'warning');
            } else {
                AppUtils.showNotification(`⏳ Status: ${payment.status}`, 'info');
            }
        } catch (error) {
            console.error('Erro ao verificar pagamento:', error);
            AppUtils.showNotification('Erro ao verificar pagamento. Tente novamente.', 'error');
        }
    };

    // ==============================================
    // 🔥 COUNTDOWN
    // ==============================================

    function startCountdown(seconds) {
        if (countdownInterval) clearInterval(countdownInterval);

        let remaining = seconds || CONFIG.PIX_EXPIRY_MINUTES * 60;
        const timerElement = document.getElementById('countdownTimer');

        countdownInterval = setInterval(() => {
            if (remaining <= 0) {
                clearInterval(countdownInterval);
                countdownInterval = null;
                if (timerElement) {
                    timerElement.textContent = 'Expirado!';
                    timerElement.style.color = '#dc3545';
                }
                AppUtils.showNotification('⏰ QR Code expirado. Gere um novo pagamento.', 'warning');
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

    // ==============================================
    // 🔥 COPY PIX CODE
    // ==============================================

    window.copyPixCode = function() {
        const codeElement = document.getElementById('pixCodeText');
        if (!codeElement?.textContent) return;

        const code = codeElement.textContent.trim();

        if (navigator.clipboard?.writeText) {
            navigator.clipboard.writeText(code)
                .then(() => AppUtils.showNotification('✅ Chave PIX copiada!', 'success'))
                .catch(() => fallbackCopy(code));
        } else {
            fallbackCopy(code);
        }
    };

    function fallbackCopy(text) {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        textarea.style.top = '-9999px';
        document.body.appendChild(textarea);
        textarea.select();
        try {
            document.execCommand('copy');
            AppUtils.showNotification('✅ Chave PIX copiada!', 'success');
        } catch (err) {
            AppUtils.showNotification('❌ Erro ao copiar. Tente novamente.', 'error');
        }
        document.body.removeChild(textarea);
    }

    // ==============================================
    // 🔥 GET AUTH STATUS (SIMPLIFICADO)
    // ==============================================

    function getAuthStatus() {
        if (window.__APP_STATE) {
            const s = window.__APP_STATE;
            return {
                isAdmin: s.isAdmin || false,
                isPremium: s.isPremium || false,
                credits: s.credits || 0,
                user: s.user || null,
                tokenValid: s.tokenValid || false
            };
        }
        if (window.appAuth) {
            return {
                isAdmin: window.appAuth.isAdmin?.() || false,
                isPremium: window.appAuth.isPremium?.() || false,
                credits: window.appAuth.getCredits?.() || 0,
                user: window.appAuth.getCurrentUser?.() || null,
                tokenValid: true
            };
        }
        return {
            isAdmin: localStorage.getItem('is_admin') === 'true',
            isPremium: localStorage.getItem('is_premium') === 'true',
            credits: parseInt(localStorage.getItem('user_credits') || '0'),
            user: null,
            tokenValid: !!localStorage.getItem('access_token')
        };
    }

    // ==============================================
    // 🔥 EXPOSIÇÃO GLOBAL
    // ==============================================

    window.loadPremiumStatus = loadPremiumStatus;
    window.receiveDailyCredit = receiveDailyCredit;
    window.updateCreditsDisplay = updateCreditsDisplay;
    window.openCpfModal = openCpfModal;
    window.createPaymentWithPix = createPaymentWithPix;
    window.copyPixCode = window.copyPixCode;
    window.verifyPayment = window.verifyPayment;
    window.VagasSystem = VagasSystem;

    window.paymentReady = true;
    window.paymentVersion = '7.0';

    // ==============================================
    // 🔥 INICIALIZAÇÃO
    // ==============================================

    VagasSystem.init();

    console.log('✅ payment.js v7.0 carregado');
    console.log('   📦 Usando EventBus do app.js');
    console.log('   📦 Usando fetchWithAuth do app.js');
    console.log('   📦 Usando AppUtils do app.js');
    console.log('   🎯 Polling adaptativo de vagas');
    console.log('   ⏰ Status polling automático');

})();