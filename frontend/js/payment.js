// payment.js - VERSÃO 6.5 (APENAS FUNÇÕES DE PAGAMENTO)
// ==============================================
// 🔥 MELHORIAS V6.5:
// 1. ✅ REMOVIDA renderização de planos (card estático no HTML)
// 2. ✅ MANTÉM: openCpfModal, proceedWithCpf, createPaymentWithPix
// 3. ✅ MANTÉM: showPixModal, verifyPayment, copyPixCode
// 4. ✅ MANTÉM: loadPremiumStatus, receiveDailyCredit
// 5. ✅ INTEGRAÇÃO TOTAL com app.js
// 6. ✅ CONSUMO DE window.fetchWithAuth
// ==============================================

(function() {
    'use strict';

    console.log('🚀 Inicializando payment.js v6.5 (Apenas funções de pagamento)...');

    // ==============================================
    // 🔒 DETECTA AMBIENTE
    // ==============================================

    const HAS_APP = !!(window.App || window.app || window.EventBus || window.__APP_STATE || window.appAuth);
    console.log(`📡 Ambiente: ${HAS_APP ? 'APP.JS' : 'STANDALONE'}`);

    // ==============================================
    // 🔒 CONFIGURAÇÕES
    // ==============================================

    const CONFIG = {
        MAX_CREDITS_BALANCE: 3,
        INITIAL_FREE_CREDITS: 3,
        PIX_EXPIRY_MINUTES: 30,
        PROMOTIONAL_PRICE: 97.00,
        REGULAR_PRICE: 149.90,
        TOTAL_PROMOTIONAL_SLOTS: 100,
        DAYS_PREMIUM: 30,
        CACHE_TTL: 60000,
        RETRY_ATTEMPTS: 3,
        RETRY_DELAY: 1000
    };

    // ==============================================
    // 📡 EVENT BUS (usa app.js se disponível)
    // ==============================================

    const EventBus = (() => {
        if (HAS_APP && window.EventBus) {
            console.log('📡 Usando EventBus do app.js');
            return window.EventBus;
        }
        
        console.log('📡 Usando EventBus próprio (fallback)');
        const _handlers = new Map();
        
        return {
            on(event, handler) {
                if (!_handlers.has(event)) _handlers.set(event, []);
                _handlers.get(event).push(handler);
            },
            off(event, handler) {
                if (!_handlers.has(event)) return;
                const handlers = _handlers.get(event);
                const index = handlers.indexOf(handler);
                if (index !== -1) handlers.splice(index, 1);
                if (handlers.length === 0) _handlers.delete(event);
            },
            emit(event, data) {
                try {
                    window.dispatchEvent(new CustomEvent(event, { detail: data, bubbles: true }));
                    document.dispatchEvent(new CustomEvent(event, { detail: data, bubbles: true }));
                } catch (e) {}
                
                if (!_handlers.has(event)) return;
                for (const handler of _handlers.get(event)) {
                    try { handler(data); } catch (e) { console.error(e); }
                }
            },
            once(event, handler) {
                const wrapper = (data) => {
                    handler(data);
                    this.off(event, wrapper);
                };
                this.on(event, wrapper);
            }
        };
    })();

    // ==============================================
    // 📦 CACHE INTELLIGENTE
    // ==============================================

    const Cache = {
        _data: new Map(),
        _timestamps: new Map(),

        set(key, value, ttl = CONFIG.CACHE_TTL) {
            this._data.set(key, value);
            this._timestamps.set(key, Date.now() + ttl);
        },

        get(key) {
            const timestamp = this._timestamps.get(key);
            if (!timestamp || Date.now() > timestamp) {
                this._data.delete(key);
                this._timestamps.delete(key);
                return null;
            }
            return this._data.get(key);
        },

        clear() {
            this._data.clear();
            this._timestamps.clear();
        },

        isValid(key) {
            const timestamp = this._timestamps.get(key);
            return timestamp && Date.now() <= timestamp;
        }
    };

    // ==============================================
    // 🔐 SEGURANÇA
    // ==============================================

    const Security = {
        sanitizeHTML(str) {
            if (!str) return '';
            if (typeof str !== 'string') str = String(str);
            const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
            return str.replace(/[&<>"']/g, m => map[m] || m).slice(0, 5000);
        },

        sanitizeNumber(value, defaultValue = 0) {
            if (value === undefined || value === null) return defaultValue;
            const num = parseFloat(String(value).replace(/[^0-9.,-]/g, '').replace(',', '.'));
            return isNaN(num) ? defaultValue : num;
        },

        sanitizeCPF(cpf) {
            if (!cpf) return '';
            return String(cpf).replace(/\D/g, '');
        },

        validateCPF(cpf) {
            const clean = this.sanitizeCPF(cpf);
            if (clean.length !== 11) return false;
            const invalid = ['00000000000', '11111111111', '22222222222', '33333333333',
                            '44444444444', '55555555555', '66666666666', '77777777777',
                            '88888888888', '99999999999'];
            if (invalid.includes(clean)) return false;
            let sum = 0;
            for (let i = 0; i < 9; i++) sum += parseInt(clean[i]) * (10 - i);
            let remainder = (sum * 10) % 11;
            if (remainder === 10 || remainder === 11) remainder = 0;
            if (remainder !== parseInt(clean[9])) return false;
            sum = 0;
            for (let i = 0; i < 10; i++) sum += parseInt(clean[i]) * (11 - i);
            remainder = (sum * 10) % 11;
            if (remainder === 10 || remainder === 11) remainder = 0;
            return remainder === parseInt(clean[10]);
        },

        sanitizeObject(obj) {
            if (obj === null || obj === undefined) return obj;
            if (typeof obj === 'string') return this.sanitizeHTML(obj);
            if (typeof obj === 'number') return this.sanitizeNumber(obj);
            if (Array.isArray(obj)) return obj.map(item => this.sanitizeObject(item));
            if (typeof obj === 'object') {
                const result = {};
                for (const [key, value] of Object.entries(obj)) {
                    result[this.sanitizeHTML(key)] = this.sanitizeObject(value);
                }
                return result;
            }
            return obj;
        }
    };

    // ==============================================
    // 🔥 FETCH UNIFICADO
    // ==============================================

    async function fetchWithRetry(url, options = {}, retries = CONFIG.RETRY_ATTEMPTS) {
        // Tenta usar fetchWithAuth do app.js
        if (window.fetchWithAuth) {
            try {
                const response = await window.fetchWithAuth(url, options);
                if (response) return response;
            } catch (e) {
                console.warn('⚠️ window.fetchWithAuth falhou:', e);
            }
        }
        if (window.App?.fetchWithAuth) {
            try {
                const response = await window.App.fetchWithAuth(url, options);
                if (response) return response;
            } catch (e) {
                console.warn('⚠️ App.fetchWithAuth falhou:', e);
            }
        }
        if (window.appAuth?.fetchWithAuth) {
            try {
                const response = await window.appAuth.fetchWithAuth(url, options);
                if (response) return response;
            } catch (e) {
                console.warn('⚠️ appAuth.fetchWithAuth falhou:', e);
            }
        }

        // Fallback: fetch com retry
        const attempt = (attemptNumber) => {
            return new Promise(async (resolve, reject) => {
                try {
                    const token = localStorage.getItem('access_token');
                    const headers = {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                        ...options.headers
                    };
                    if (token) headers['Authorization'] = `Bearer ${token}`;
                    const response = await fetch(url, { ...options, headers });
                    if (!response.ok && attemptNumber < retries) {
                        const delay = CONFIG.RETRY_DELAY * attemptNumber;
                        console.log(`🔄 Tentativa ${attemptNumber + 1} falhou. Retentando em ${delay}ms...`);
                        setTimeout(() => resolve(attempt(attemptNumber + 1)), delay);
                        return;
                    }
                    resolve(response);
                } catch (error) {
                    if (attemptNumber < retries) {
                        const delay = CONFIG.RETRY_DELAY * attemptNumber;
                        console.log(`🔄 Erro na tentativa ${attemptNumber + 1}. Retentando em ${delay}ms...`);
                        setTimeout(() => resolve(attempt(attemptNumber + 1)), delay);
                    } else {
                        reject(error);
                    }
                }
            });
        };
        return attempt(0);
    }

    // ==============================================
    // 🔥 SISTEMA DE AUTENTICAÇÃO
    // ==============================================

    function getAuthStatus() {
        if (HAS_APP && window.__APP_STATE) {
            const state = window.__APP_STATE;
            return {
                isAdmin: state.isAdmin || false,
                isPremium: state.isPremium || false,
                credits: state.credits || 0,
                user: state.user || null,
                tokenValid: state.tokenValid || false
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
    // 🔥 LOAD PREMIUM STATUS (EXPORTADA PARA APP.JS)
    // ==============================================

    async function loadPremiumStatus() {
        try {
            const response = await fetchWithRetry('/api/payments/premium-status');
            if (response?.ok) {
                const data = await response.json();
                const safeData = Security.sanitizeObject(data);
                if (HAS_APP && window.__APP_STATE_MANAGER) {
                    window.__APP_STATE_MANAGER.updatePremiumStatus(safeData);
                }
                EventBus.emit('payment:premium_status_updated', {
                    isPremium: safeData.is_premium || false,
                    daysLeft: safeData.days_left || 0,
                    hasPromotionalPrice: safeData.promotional_price_locked || false,
                    promotionalPrice: safeData.promotional_price || null,
                    canReceiveDailyCredit: safeData.can_receive_today || false,
                    receivedDailyCreditToday: safeData.received_today || false,
                    creditsBalance: safeData.credits_balance || 0,
                    maxCredits: safeData.max_credits_balance || CONFIG.MAX_CREDITS_BALANCE
                });
                return safeData;
            }
        } catch (error) {
            console.error('Erro ao carregar status premium:', error);
        }
        return null;
    }

    // ==============================================
    // 🔥 RECEIVE DAILY CREDIT (EXPORTADA PARA APP.JS)
    // ==============================================

    async function receiveDailyCredit() {
        try {
            const response = await fetchWithRetry('/api/payments/daily-credit', { method: 'POST' });
            if (response?.ok) {
                const data = await response.json();
                const safeData = Security.sanitizeObject(data);
                if (safeData.success) {
                    showNotification(`✅ ${safeData.message || 'Crédito recebido com sucesso!'}`, 'success');
                    if (HAS_APP && window.__APP_STATE_MANAGER) {
                        window.__APP_STATE_MANAGER.updateCredits(safeData.balance || 0);
                    }
                    setTimeout(() => updateCreditsDisplay(), 500);
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
    // 🔥 UPDATE CREDITS DISPLAY
    // ==============================================

    function updateCreditsDisplay(credits, isPremium, isAdmin) {
        const AppUtils = window.AppUtils || window.app?.AppUtils;
        let displayText = '0';
        if (isAdmin) {
            displayText = '∞';
        } else if (AppUtils?.formatCreditsDisplay) {
            displayText = AppUtils.formatCreditsDisplay(credits, isPremium);
        } else {
            displayText = isPremium ? `${credits || 0}/${CONFIG.MAX_CREDITS_BALANCE}` : String(credits || 0);
        }
        document.querySelectorAll('#creditsCount, #creditsDisplay, #uploadCredits, .credits-badge span').forEach(el => {
            if (el) el.textContent = displayText;
        });
        window.dispatchEvent(new CustomEvent('creditsUpdated', {
            detail: { credits: credits || 0, display: displayText, maxCredits: CONFIG.MAX_CREDITS_BALANCE, isPremium: isPremium || false }
        }));
    }

    // ==============================================
    // 🔥 NOTIFICAÇÕES
    // ==============================================

    function showNotification(message, type = 'info') {
        const AppUtils = window.AppUtils || window.app?.AppUtils;
        if (AppUtils?.showNotification) {
            return AppUtils.showNotification(message, type);
        }
        if (window.toastr?.[type]) {
            window.toastr[type](message);
            return true;
        }
        console.log(`[${type}] ${message}`);
        if (type === 'error' || type === 'warning') {
            alert(`⚠️ ${message}`);
        }
        return true;
    }

    // ==============================================
    // 🔥 MODAL CPF
    // ==============================================

    function openCpfModal(planId) {
        const authStatus = getAuthStatus();
        
        if (authStatus.isAdmin) {
            showNotification('👑 Como administrador, você tem acesso ilimitado.', 'info');
            return;
        }

        if (authStatus.isPremium) {
            showNotification('✅ Você já possui um plano ativo!', 'success');
            window.location.href = '/dashboard';
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
                        <button type="button" class="btn btn-bronze" onclick="window.proceedWithCpf('${Security.sanitizeHTML(planId || 'premium_mensal')}')"><i class="fas fa-arrow-right me-2"></i>Continuar para PIX</button>
                    </div>
                </div>
            </div>
        `;

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

            cpfInput.addEventListener('blur', function(e) {
                const cpf = Security.sanitizeCPF(e.target.value);
                if (cpf.length > 0 && !Security.validateCPF(cpf)) {
                    const errorEl = document.getElementById('cpfError');
                    if (errorEl) {
                        errorEl.textContent = '❌ CPF inválido. Digite um CPF válido com 11 dígitos.';
                        errorEl.classList.remove('d-none');
                    }
                }
            });
        }

        try {
            new bootstrap.Modal(cpfModal).show();
        } catch (e) {
            console.warn('⚠️ Bootstrap Modal não disponível:', e);
            cpfModal.style.display = 'block';
            cpfModal.classList.add('show');
        }
    }

    function proceedWithCpf(planId) {
        const cpfInput = document.getElementById('cpfInput');
        const cpfError = document.getElementById('cpfError');
        
        if (!cpfInput) {
            showNotification('Erro ao processar CPF. Tente novamente.', 'error');
            return;
        }
        
        const cpfLimpo = Security.sanitizeCPF(cpfInput.value);
        
        if (!Security.validateCPF(cpfLimpo)) {
            if (cpfError) {
                cpfError.textContent = '❌ CPF inválido. Digite um CPF válido com 11 dígitos.';
                cpfError.classList.remove('d-none');
            }
            return;
        }
        
        if (cpfError) cpfError.classList.add('d-none');
        
        const cpfModal = bootstrap.Modal.getInstance(document.getElementById('cpfModal'));
        if (cpfModal) cpfModal.hide();
        
        createPaymentWithPix(cpfLimpo, planId);
    }

    // ==============================================
    // 🔥 CRIAÇÃO DE PAGAMENTO - USANDO fetchWithAuth GLOBAL
    // ==============================================

    async function createPaymentWithPix(cpf, planId = 'premium_mensal') {
        console.log('💳 Criando pagamento PIX para CPF:', cpf);
        showNotification('🔄 Gerando QR Code PIX...', 'info');

        try {
            const fetchFn = window.fetchWithAuth || window.App?.fetchWithAuth || fetch;
            
            const response = await fetchFn('/api/payments/create-pix', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
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
                throw new Error(errorData.message || 'Erro ao criar pagamento');
            }

            const data = await response.json();
            console.log('✅ Pagamento criado:', data);

            // 🔥 Dispara evento creditsUpdated (camelCase - esperado pelo app.js)
            if (data.credits_balance !== undefined) {
                window.dispatchEvent(new CustomEvent('creditsUpdated', {
                    detail: {
                        credits: data.credits_balance,
                        isPremium: data.is_premium || false,
                        maxCredits: CONFIG.MAX_CREDITS_BALANCE
                    }
                }));
            }

            // 🔥 Dispara evento premiumStatusUpdated (camelCase - esperado pelo app.js)
            if (data.is_premium !== undefined) {
                window.dispatchEvent(new CustomEvent('premiumStatusUpdated', {
                    detail: {
                        isPremium: data.is_premium,
                        daysLeft: data.days_left || 0,
                        hasPromotionalPrice: data.has_promotional_price || false,
                        promotionalPrice: data.promotional_price || null,
                        creditsBalance: data.credits_balance || 0
                    }
                }));
            }

            showPixModal(data);

        } catch (error) {
            console.error('❌ Erro ao criar pagamento:', error);
            showNotification(error.message || 'Erro ao gerar pagamento. Tente novamente.', 'error');
        }
    }

    // ==============================================
    // 🔥 MODAL PIX
    // ==============================================

    let countdownInterval = null;

    function showPixModal(data) {
        console.log('📱 Mostrando modal PIX...');

        let pixModal = document.getElementById('pixModal');
        
        if (!pixModal) {
            pixModal = document.createElement('div');
            pixModal.id = 'pixModal';
            pixModal.className = 'modal fade';
            pixModal.setAttribute('tabindex', '-1');
            pixModal.setAttribute('aria-hidden', 'true');
            document.body.appendChild(pixModal);
        }

        const qrCode = data.qr_code || data.qrCode || '';
        const pixCode = data.pix_code || data.pixCode || data.pix_code_text || 'autonalytics@gmail.com';
        const amount = data.amount || CONFIG.PROMOTIONAL_PRICE;
        const planName = data.plan_name || 'Plano Bronze';

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
                            <small>R$ ${amount.toFixed(2).replace('.', ',')} - Preço bloqueado VITALÍCIO!</small>
                        </div>
                        
                        <h6 class="mb-3" style="color: rgba(255,255,255,0.7);">Escaneie o QR Code com seu banco</h6>
                        
                        <div class="text-center mb-3">
                            <div class="p-3 d-inline-block" style="background: white; border-radius: 16px;">
                                ${qrCode ? 
                                    `<img src="${qrCode}" alt="QR Code PIX" style="max-width: 200px; border-radius: 8px;">` :
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
                            <strong>${planName}</strong> - Valor: R$ ${amount.toFixed(2).replace('.', ',')}<br>
                            <span class="text-success">✅ Você está comprando na promoção! Preço garantido para sempre.</span><br>
                            <span style="color: rgba(255,255,255,0.5);">⏰ Este QR Code expira em <strong id="countdownTimer">30:00</strong> minutos.</span>
                        </div>
                        
                        <div id="paymentStatus"></div>
                    </div>
                    <div class="modal-footer border-0 justify-content-center" style="border-top: 1px solid rgba(255,255,255,0.06);">
                        <button type="button" class="btn w-100" onclick="window.verifyPayment()" 
                                style="background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.6); border: none; border-radius: 50px; padding: 0.75rem;">
                            <i class="fas fa-check-circle me-2"></i> Já realizei o pagamento / Atualizar
                        </button>
                    </div>
                </div>
            </div>
        `;

        startCountdown(30 * 60);
        
        try {
            new bootstrap.Modal(pixModal).show();
        } catch (e) {
            console.warn('⚠️ Bootstrap Modal não disponível:', e);
            pixModal.style.display = 'block';
            pixModal.classList.add('show');
        }
    }

    function startCountdown(seconds) {
        if (countdownInterval) clearInterval(countdownInterval);
        
        let remaining = seconds || 30 * 60;
        const timerElement = document.getElementById('countdownTimer');
        
        countdownInterval = setInterval(() => {
            if (remaining <= 0) {
                clearInterval(countdownInterval);
                countdownInterval = null;
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

    window.copyPixCode = function() {
        const codeElement = document.getElementById('pixCodeText');
        if (codeElement?.textContent) {
            const code = codeElement.textContent.trim();
            
            if (navigator.clipboard?.writeText) {
                navigator.clipboard.writeText(code)
                    .then(() => showNotification('✅ Chave PIX copiada!', 'success'))
                    .catch(() => fallbackCopy(code));
            } else {
                fallbackCopy(code);
            }
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
            showNotification('✅ Chave PIX copiada!', 'success');
        } catch (err) {
            showNotification('❌ Erro ao copiar. Tente novamente.', 'error');
        }
        document.body.removeChild(textarea);
    }

    window.verifyPayment = async function() {
        showNotification('🔄 Verificando pagamento...', 'info');
        
        try {
            const fetchFn = window.fetchWithAuth || window.App?.fetchWithAuth || fetch;
            
            const response = await fetchFn('/api/payments/verify-payment', {
                method: 'POST'
            });

            if (!response) {
                throw new Error('Falha na conexão');
            }

            if (!response.ok) {
                throw new Error('Erro ao verificar pagamento');
            }

            const data = await response.json();
            
            if (data.success) {
                showNotification('✅ Pagamento confirmado! Seu plano foi ativado.', 'success');
                
                window.dispatchEvent(new CustomEvent('premiumStatusUpdated', {
                    detail: {
                        isPremium: true,
                        daysLeft: data.days_left || 30,
                        creditsBalance: data.credits_balance || 0
                    }
                }));

                if (data.credits_balance !== undefined) {
                    window.dispatchEvent(new CustomEvent('creditsUpdated', {
                        detail: {
                            credits: data.credits_balance,
                            isPremium: true,
                            maxCredits: CONFIG.MAX_CREDITS_BALANCE
                        }
                    }));
                }
                
                const modal = bootstrap.Modal.getInstance(document.getElementById('pixModal'));
                if (modal) modal.hide();
                setTimeout(() => window.location.reload(), 1500);
            } else {
                showNotification('⏳ Pagamento ainda não confirmado. Aguarde alguns minutos.', 'warning');
            }
        } catch (error) {
            console.error('Erro ao verificar pagamento:', error);
            showNotification('Erro ao verificar pagamento. Tente novamente.', 'error');
        }
    };

    // ==============================================
    // 🔥 EXPOSIÇÃO GLOBAL
    // ==============================================

    // Funções principais
    window.loadPremiumStatus = loadPremiumStatus;
    window.receiveDailyCredit = receiveDailyCredit;
    window.updateCreditsDisplay = updateCreditsDisplay;
    window.showNotification = showNotification;

    // Funções de pagamento
    window.openCpfModal = openCpfModal;
    window.proceedWithCpf = proceedWithCpf;
    window.copyPixCode = copyPixCode;
    window.verifyPayment = verifyPayment;
    window.createPaymentWithPix = createPaymentWithPix;

    window.paymentReady = false;
    window.paymentVersion = '6.5';

    console.log('✅ payment.js v6.5 carregado');
    console.log('   📦 Funções de pagamento prontas');
    console.log('   🔗 Integrado com app.js v6.2');

})();