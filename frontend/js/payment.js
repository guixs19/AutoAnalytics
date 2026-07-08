// payment.js - VERSÃO 7.1 (INTEGRAÇÃO TOTAL COM APP.JS)
// ==============================================
// 🔥 MELHORIAS V7.1:
// 1. ✅ REMOVIDO: Fallback do EventBus (usa apenas window.EventBus)
// 2. ✅ REMOVIDO: Fallback do AppUtils (usa apenas window.AppUtils)
// 3. ✅ REMOVIDO: Fallback do fetchWithAuth (usa apenas window.fetchWithAuth)
// 4. ✅ ADICIONADO: Sistema de espera inteligente (aguarda app.js)
// 5. ✅ ADICIONADO: Validação de dependências no carregamento
// 6. ✅ MELHORADO: Logs com nível de severidade
// 7. ✅ CORRIGIDO: Inicialização só após app:ready
// 8. ✅ OTIMIZADO: Uso de window.__APP_STATE como fonte única
// ==============================================

(function() {
    'use strict';

    console.log('🚀 [payment.js v7.1] Carregando...');

    // ==============================================
    // 🔥 CONFIGURAÇÕES
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
        VAGAS_UPDATE_INTERVAL_NORMAL: 30000,
        VAGAS_UPDATE_INTERVAL_URGENT: 5000,
        VAGAS_URGENT_THRESHOLD: 20,
        VAGAS_CACHE_TTL: 35000,
        
        // 🔥 VERIFICAÇÃO DE STATUS
        STATUS_POLLING_INTERVAL: 5000,
        STATUS_MAX_ATTEMPTS: 60,
        STATUS_PIX_INTERVAL: 3000,

        // 🔥 TIMEOUTS
        WAIT_FOR_APP_TIMEOUT: 10000,
        WAIT_FOR_APP_INTERVAL: 200,
        MAX_WAIT_ATTEMPTS: 50
    };

    // ==============================================
    // 🔥 SISTEMA DE ESPERA INTELIGENTE
    // ==============================================

    const Waiter = {
        _attempts: 0,
        _maxAttempts: CONFIG.MAX_WAIT_ATTEMPTS,
        _interval: CONFIG.WAIT_FOR_APP_INTERVAL,
        _resolved: false,

        /**
         * Aguarda o app.js ficar pronto
         * @returns {Promise<boolean>} - true se app pronto, false se timeout
         */
        waitForApp: function() {
            return new Promise((resolve) => {
                // Verifica se já está pronto
                if (this._isAppReady()) {
                    console.log('✅ [payment.js] app.js já está pronto');
                    this._resolved = true;
                    resolve(true);
                    return;
                }

                console.log('⏳ [payment.js] Aguardando app.js...');

                const startTime = Date.now();
                this._attempts = 0;

                const check = () => {
                    this._attempts++;

                    if (this._isAppReady()) {
                        console.log(`✅ [payment.js] app.js pronto após ${this._attempts} tentativas`);
                        this._resolved = true;
                        resolve(true);
                        return;
                    }

                    // Timeout
                    if (Date.now() - startTime > CONFIG.WAIT_FOR_APP_TIMEOUT) {
                        console.error('❌ [payment.js] Timeout aguardando app.js');
                        resolve(false);
                        return;
                    }

                    // Próxima verificação
                    setTimeout(check, this._interval);
                };

                check();
            });
        },

        _isAppReady: function() {
            // 1. Verifica pelo flag do app.js
            if (window._appReadyFired === true) {
                return true;
            }

            // 2. Verifica pelo estado do App
            if (window.App && typeof window.App.isReady === 'function') {
                try {
                    if (window.App.isReady()) {
                        return true;
                    }
                } catch (e) { /* ignora */ }
            }

            // 3. Verifica pelo estado global
            if (window.__APP_STATE && window.__APP_STATE.isAppReady === true) {
                return true;
            }

            // 4. Verifica dependências essenciais
            if (window.EventBus && window.AppUtils && window.fetchWithAuth) {
                // Se tem as dependências, considera pronto
                return true;
            }

            return false;
        },

        /**
         * Obtém as dependências do app.js, com validação
         */
        getDependencies: function() {
            return {
                EventBus: window.EventBus,
                AppUtils: window.AppUtils,
                fetchWithAuth: window.fetchWithAuth,
                State: window.__APP_STATE || null,
                StateManager: window.__APP_STATE_MANAGER || null,
                isReady: this._isAppReady()
            };
        },

        /**
         * Valida se todas as dependências estão disponíveis
         */
        validateDependencies: function(deps) {
            const required = ['EventBus', 'AppUtils', 'fetchWithAuth'];
            const missing = required.filter(key => !deps[key]);

            if (missing.length > 0) {
                console.warn(`⚠️ [payment.js] Dependências faltando: ${missing.join(', ')}`);
                return false;
            }

            return true;
        }
    };

    // ==============================================
    // 🔥 SISTEMA DE VAGAS (REFATORADO)
    // ==============================================

    const VagasSystem = {
        _lastUpdate: 0,
        _updateInterval: null,
        _currentData: null,
        _isUpdating: false,
        _isUrgent: false,
        _deps: null,
        _initialized: false,

        /**
         * Inicializa o sistema de vagas
         */
        init: function(deps) {
            if (this._initialized) return;

            this._deps = deps;
            this._initialized = true;

            console.log('🎯 [VagasSystem] Inicializando...');

            // 🔥 Primeira atualização
            this.updateVagas();

            // 🔥 Inicia polling
            this._startPolling();

            // 🔥 Eventos que disparam atualização
            const events = ['payment:completed', 'premiumStatusUpdated', 'app:state_changed'];
            events.forEach(eventName => {
                document.addEventListener(eventName, () => {
                    console.log(`🔄 [VagasSystem] Evento ${eventName} - atualizando`);
                    setTimeout(() => this.updateVagas(true), 1000);
                });
            });

            console.log('✅ [VagasSystem] Inicializado com sucesso');
        },

        _startPolling: function() {
            if (this._updateInterval) {
                clearInterval(this._updateInterval);
            }

            const interval = this._isUrgent ?
                CONFIG.VAGAS_UPDATE_INTERVAL_URGENT :
                CONFIG.VAGAS_UPDATE_INTERVAL_NORMAL;

            this._updateInterval = setInterval(() => {
                this.updateVagas();
            }, interval);

            console.log(`⏰ [VagasSystem] Polling: ${interval/1000}s`);
        },

        _adjustPolling: function(remaining) {
            const wasUrgent = this._isUrgent;
            this._isUrgent = remaining <= CONFIG.VAGAS_URGENT_THRESHOLD && remaining > 0;

            if (wasUrgent !== this._isUrgent) {
                console.log(`🔄 [VagasSystem] Ajustando polling: ${this._isUrgent ? 'URGENTE (5s)' : 'NORMAL (30s)'}`);
                this._startPolling();
            }
        },

        /**
         * Atualiza dados das vagas
         */
        updateVagas: async function(force = false) {
            if (this._isUpdating) return;

            const now = Date.now();
            if (!force && (now - this._lastUpdate) < CONFIG.VAGAS_CACHE_TTL) {
                return this._currentData;
            }

            this._isUpdating = true;

            try {
                const response = await this._deps.fetchWithAuth('/api/payments/promotion-status');
                
                if (!response) {
                    console.warn('⚠️ [VagasSystem] Sem resposta da API');
                    return null;
                }

                if (!response.ok) {
                    console.warn(`⚠️ [VagasSystem] API retornou ${response.status}`);
                    return null;
                }

                const data = await response.json();
                this._currentData = data;
                this._lastUpdate = now;

                this._adjustPolling(data.remaining_slots || 0);
                this._updateUI(data);

                // 🔥 Dispara evento via EventBus do app.js
                if (this._deps.EventBus) {
                    this._deps.EventBus.emit('vagas:updated', data);
                }
                window.dispatchEvent(new CustomEvent('vagas:updated', { detail: data }));

                return data;

            } catch (error) {
                console.error('❌ [VagasSystem] Erro ao atualizar:', error);
                return null;
            } finally {
                this._isUpdating = false;
            }
        },

        /**
         * Atualiza a UI com os dados das vagas
         */
        _updateUI: function(data) {
            const remaining = data.remaining_slots || 0;
            const total = data.total_slots || CONFIG.TOTAL_PROMOTIONAL_SLOTS;
            const isSoldOut = remaining <= 0;
            const isUrgent = remaining <= CONFIG.VAGAS_URGENT_THRESHOLD && remaining > 0;

            // 🔥 Elementos da UI
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

            // 1. Número de vagas com animação
            if (elements.vagasRestantes) {
                const oldValue = parseInt(elements.vagasRestantes.textContent) || 0;
                elements.vagasRestantes.textContent = remaining;
                
                if (oldValue !== remaining && oldValue > 0) {
                    elements.vagasRestantes.style.transition = 'transform 0.3s ease';
                    elements.vagasRestantes.style.transform = 'scale(1.4)';
                    setTimeout(() => {
                        elements.vagasRestantes.style.transform = 'scale(1)';
                    }, 300);
                }
            }

            // 2. Total
            if (elements.vagasTotal) {
                elements.vagasTotal.textContent = total;
            }

            // 3. Barra de progresso
            if (elements.vagasProgress) {
                const percent = total > 0 ? ((total - remaining) / total) * 100 : 0;
                elements.vagasProgress.style.width = `${Math.min(100, percent)}%`;
                
                elements.vagasProgress.style.background = isSoldOut 
                    ? 'linear-gradient(90deg, #dc3545, #c0392b)'
                    : isUrgent 
                        ? 'linear-gradient(90deg, #f5a623, #e67e22)'
                        : 'linear-gradient(90deg, #cd7f32, #f5a623)';
                
                elements.vagasProgress.style.animation = isUrgent && !isSoldOut 
                    ? 'pulse 1.5s ease-in-out infinite' 
                    : 'none';
            }

            // 4. Alertas
            if (elements.vagasUrgentAlert && elements.vagasUrgentCount) {
                elements.vagasUrgentAlert.style.display = isUrgent ? 'block' : 'none';
                if (isUrgent) elements.vagasUrgentCount.textContent = remaining;
            }

            if (elements.vagasSoldOutAlert) {
                elements.vagasSoldOutAlert.style.display = isSoldOut ? 'block' : 'none';
            }

            // 5. Preço e botão
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
                    elements.btnUpgrade.classList.add('sold-out');
                }
            } else {
                if (elements.btnUpgrade) {
                    elements.btnUpgrade.classList.remove('sold-out');
                    const price = data.user_locked_price || CONFIG.PROMOTIONAL_PRICE;
                    elements.btnUpgrade.innerHTML = `
                        <i class="fas fa-bolt me-2"></i>
                        🔥 GARANTIR PREÇO FUNDADOR R$ ${price.toFixed(2).replace('.', ',')}
                        <small class="d-block fs-10">${remaining} vagas restantes</small>
                    `;
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

        getCurrentData: function() {
            return this._currentData || {
                remaining_slots: CONFIG.TOTAL_PROMOTIONAL_SLOTS,
                total_slots: CONFIG.TOTAL_PROMOTIONAL_SLOTS,
                promotional_price: CONFIG.PROMOTIONAL_PRICE,
                regular_price: CONFIG.REGULAR_PRICE,
                user_locked_price: null
            };
        },

        stop: function() {
            if (this._updateInterval) {
                clearInterval(this._updateInterval);
                this._updateInterval = null;
            }
        }
    };

    // ==============================================
    // 🔥 FUNÇÕES PRINCIPAIS
    // ==============================================

    let deps = null;

    /**
     * Obtém status de autenticação do app.js
     */
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
            isAdmin: false,
            isPremium: false,
            credits: 0,
            user: null,
            tokenValid: false
        };
    }

    /**
     * Carrega status premium
     */
    async function loadPremiumStatus() {
        if (!deps || !deps.fetchWithAuth) {
            console.warn('⚠️ [payment.js] fetchWithAuth não disponível');
            return null;
        }

        try {
            const response = await deps.fetchWithAuth('/api/payments/premium-status');
            if (response?.ok) {
                const data = await response.json();
                
                if (window.__APP_STATE_MANAGER) {
                    window.__APP_STATE_MANAGER.updatePremiumStatus(data);
                }

                if (deps.EventBus) {
                    deps.EventBus.emit('payment:premium_status_updated', {
                        isPremium: data.is_premium || false,
                        daysLeft: data.days_left || 0,
                        hasPromotionalPrice: data.promotional_price_locked || false,
                        promotionalPrice: data.promotional_price || null,
                        canReceiveDailyCredit: data.can_receive_today || false,
                        receivedDailyCreditToday: data.received_today || false,
                        creditsBalance: data.credits_balance || 0,
                        maxCredits: data.max_credits_balance || CONFIG.MAX_CREDITS_BALANCE
                    });
                }

                return data;
            }
        } catch (error) {
            console.error('❌ [payment.js] Erro ao carregar status premium:', error);
        }
        return null;
    }

    /**
     * Recebe crédito diário
     */
    async function receiveDailyCredit() {
        if (!deps) return null;

        try {
            const response = await deps.fetchWithAuth('/api/payments/premium/check-daily', { method: 'POST' });
            if (response?.ok) {
                const data = await response.json();
                
                if (data.success) {
                    deps.AppUtils.showNotification(`✅ ${data.message || 'Crédito recebido!'}`, 'success');
                    if (window.__APP_STATE_MANAGER) {
                        window.__APP_STATE_MANAGER.updateCredits(data.current_credits || 0);
                    }
                    updateCreditsDisplay();
                    return data;
                } else {
                    deps.AppUtils.showNotification(data.message || 'Erro ao receber crédito', 'warning');
                    return data;
                }
            }
        } catch (error) {
            console.error('❌ [payment.js] Erro ao receber crédito:', error);
            deps?.AppUtils?.showNotification('Erro de conexão. Tente novamente.', 'error');
        }
        return null;
    }

    /**
     * Atualiza exibição de créditos
     */
    function updateCreditsDisplay(credits, isPremium, isAdmin) {
        const appState = window.__APP_STATE || {};
        const _credits = credits !== undefined ? credits : appState.credits || 0;
        const _isPremium = isPremium !== undefined ? isPremium : appState.isPremium || false;
        const _isAdmin = isAdmin !== undefined ? isAdmin : appState.isAdmin || false;

        const display = _isAdmin ? '∞' : (_isPremium ? `${_credits}/${CONFIG.MAX_CREDITS_BALANCE}` : String(_credits));
        
        document.querySelectorAll('#creditsCount, #creditsDisplay, #uploadCredits, .credits-badge span')
            .forEach(el => {
                if (el) el.textContent = display;
            });

        window.dispatchEvent(new CustomEvent('creditsUpdated', {
            detail: {
                credits: _credits,
                display: display,
                maxCredits: CONFIG.MAX_CREDITS_BALANCE,
                isPremium: _isPremium
            }
        }));
    }

    /**
     * Abre modal CPF
     */
    function openCpfModal(planId) {
        if (!deps) {
            console.warn('⚠️ [payment.js] Dependências não carregadas');
            return;
        }

        const authStatus = getAuthStatus();

        if (authStatus.isAdmin) {
            deps.AppUtils.showNotification('👑 Administrador tem acesso ilimitado.', 'info');
            return;
        }

        if (authStatus.isPremium) {
            deps.AppUtils.showNotification('✅ Você já possui um plano ativo!', 'success');
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

        // 🔥 Usa template se disponível
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
            console.warn('⚠️ [payment.js] Bootstrap Modal não disponível:', e);
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
                        <button type="button" class="btn btn-bronze" id="cpfConfirmBtn" style="background: linear-gradient(135deg, #f5a623, #e67e22); color: white; border: none; border-radius:50px; padding:0.5rem 1.5rem; font-weight:700;">
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
                const cpf = e.target.value.replace(/\D/g, '');
                if (cpf.length > 0 && cpf.length !== 11) {
                    if (cpfError) {
                        cpfError.textContent = '❌ CPF inválido. Digite um CPF válido com 11 dígitos.';
                        cpfError.classList.remove('d-none');
                    }
                }
            });
        }

        if (confirmBtn) {
            confirmBtn.addEventListener('click', function() {
                if (!cpfInput) return;
                
                const cpfLimpo = cpfInput.value.replace(/\D/g, '');
                
                if (cpfLimpo.length !== 11) {
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

        if (cpfInput) {
            cpfInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' && confirmBtn) {
                    confirmBtn.click();
                }
            });
        }
    }

    /**
     * Cria pagamento PIX
     */
    async function createPaymentWithPix(cpf, planId = 'premium_mensal') {
        if (!deps) {
            console.error('❌ [payment.js] Dependências não carregadas');
            return;
        }

        console.log('💳 [payment.js] Criando pagamento PIX para CPF:', cpf.substring(0, 3) + '***' + cpf.substring(cpf.length - 3));
        deps.AppUtils.showNotification('🔄 Gerando QR Code PIX...', 'info');

        try {
            const response = await deps.fetchWithAuth('/api/payments/create-pix', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    cpf: cpf,
                    plan: planId || 'premium_mensal'
                })
            });

            if (!response) {
                throw new Error('Falha na conexão com o servidor');
            }

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || errorData.message || 'Erro ao criar pagamento');
            }

            const data = await response.json();
            console.log('✅ [payment.js] Pagamento criado:', data.payment_id || 'ID desconhecido');

            // 🔥 Dispara eventos via EventBus do app.js
            if (deps.EventBus) {
                if (data.credits_balance !== undefined) {
                    deps.EventBus.emit('creditsUpdated', {
                        credits: data.credits_balance,
                        isPremium: data.is_premium || false,
                        maxCredits: CONFIG.MAX_CREDITS_BALANCE
                    });
                }

                if (data.is_premium !== undefined) {
                    deps.EventBus.emit('premiumStatusUpdated', {
                        isPremium: data.is_premium,
                        daysLeft: data.days_left || 0,
                        hasPromotionalPrice: data.was_promotional || false,
                        promotionalPrice: data.amount || null,
                        creditsBalance: data.credits_balance || 0
                    });
                }

                deps.EventBus.emit('payment:completed', {
                    user_id: data.user_id,
                    plan: data.plan,
                    amount: data.amount,
                    was_promotional: data.was_promotional || false
                });
            }

            showPixModal(data);

        } catch (error) {
            console.error('❌ [payment.js] Erro ao criar pagamento:', error);
            deps.AppUtils.showNotification(error.message || 'Erro ao gerar pagamento. Tente novamente.', 'error');
        }
    }

    // ==============================================
    // 🔥 MODAL PIX
    // ==============================================

    let countdownInterval = null;
    let statusPollingInterval = null;

    function showPixModal(data) {
        console.log('📱 [payment.js] Mostrando modal PIX...');

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

        // 🔥 Usa template se disponível
        const template = document.getElementById('pixModalTemplate');
        if (template) {
            const clone = template.content.cloneNode(true);
            pixModal.innerHTML = '';
            pixModal.appendChild(clone);
            
            // Preenche dados
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
            console.warn('⚠️ [payment.js] Bootstrap Modal não disponível:', e);
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
    // 🔥 STATUS POLLING
    // ==============================================

    function startStatusPolling(paymentId) {
        if (statusPollingInterval) {
            clearInterval(statusPollingInterval);
            statusPollingInterval = null;
        }

        if (!paymentId || !deps) return;

        let attempts = 0;
        const maxAttempts = CONFIG.STATUS_MAX_ATTEMPTS;

        statusPollingInterval = setInterval(async () => {
            attempts++;

            try {
                const response = await deps.fetchWithAuth(`/api/payments/status/${paymentId}`);
                if (response?.ok) {
                    const data = await response.json();
                    const payment = data.payment || data;
                    
                    if (payment.status === 'approved') {
                        clearInterval(statusPollingInterval);
                        statusPollingInterval = null;
                        
                        deps.AppUtils.showNotification('✅ Pagamento confirmado! Seu plano foi ativado.', 'success');
                        
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
                        deps.AppUtils.showNotification(`❌ Pagamento ${payment.status}. Tente novamente.`, 'error');
                    }
                }
            } catch (error) {
                console.warn('⚠️ [payment.js] Erro no status polling:', error);
            }

            if (attempts >= maxAttempts) {
                clearInterval(statusPollingInterval);
                statusPollingInterval = null;
                console.log('⏰ [payment.js] Status polling finalizado (timeout)');
            }
        }, CONFIG.STATUS_POLLING_INTERVAL);

        console.log(`⏰ [payment.js] Status polling iniciado para payment ${paymentId}`);
    }

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
                deps?.AppUtils?.showNotification('⏰ QR Code expirado. Gere um novo pagamento.', 'warning');
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
                .then(() => deps?.AppUtils?.showNotification('✅ Chave PIX copiada!', 'success'))
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
            deps?.AppUtils?.showNotification('✅ Chave PIX copiada!', 'success');
        } catch (err) {
            deps?.AppUtils?.showNotification('❌ Erro ao copiar. Tente novamente.', 'error');
        }
        document.body.removeChild(textarea);
    }

    // ==============================================
    // 🔥 VERIFY PAYMENT
    // ==============================================

    window.verifyPayment = async function() {
        if (!deps) {
            console.warn('⚠️ [payment.js] Dependências não carregadas');
            return;
        }

        deps.AppUtils.showNotification('🔄 Verificando pagamento...', 'info');

        const modal = document.getElementById('pixModal');
        const verifyBtn = modal?.querySelector('#pixVerifyBtn');
        const paymentId = verifyBtn?.dataset.paymentId;

        if (!paymentId) {
            deps.AppUtils.showNotification('ID do pagamento não encontrado.', 'error');
            return;
        }

        try {
            const response = await deps.fetchWithAuth(`/api/payments/status/${paymentId}`);
            if (!response) throw new Error('Falha na conexão');

            const data = await response.json();
            const payment = data.payment || data;

            if (payment.status === 'approved') {
                deps.AppUtils.showNotification('✅ Pagamento confirmado!', 'success');
                
                window.dispatchEvent(new CustomEvent('premiumStatusUpdated', {
                    detail: {
                        isPremium: true,
                        daysLeft: 30,
                        creditsBalance: data.credits_balance || 0
                    }
                }));
                
                const modal = bootstrap.Modal.getInstance(document.getElementById('pixModal'));
                if (modal) modal.hide();
                setTimeout(() => window.location.reload(), 1500);
                
            } else if (payment.status === 'pending') {
                deps.AppUtils.showNotification('⏳ Pagamento ainda não confirmado. Aguarde alguns minutos.', 'warning');
            } else {
                deps.AppUtils.showNotification(`⏳ Status: ${payment.status}`, 'info');
            }
        } catch (error) {
            console.error('❌ [payment.js] Erro ao verificar pagamento:', error);
            deps.AppUtils.showNotification('Erro ao verificar pagamento. Tente novamente.', 'error');
        }
    };

    // ==============================================
    // 🔥 INICIALIZAÇÃO PRINCIPAL
    // ==============================================

    async function init() {
        console.log('🚀 [payment.js v7.1] Iniciando...');

        // 🔥 1. Aguarda app.js
        const appReady = await Waiter.waitForApp();
        
        if (!appReady) {
            console.error('❌ [payment.js] Não foi possível carregar dependências do app.js');
            console.warn('⚠️ [payment.js] O sistema pode não funcionar corretamente');
            
            // Tenta usar fallback mínimo
            deps = {
                EventBus: window.EventBus || null,
                AppUtils: window.AppUtils || null,
                fetchWithAuth: window.fetchWithAuth || null,
                State: window.__APP_STATE || null,
                StateManager: window.__APP_STATE_MANAGER || null
            };
        } else {
            // 🔥 2. Obtém dependências
            deps = Waiter.getDependencies();
        }

        // 🔥 3. Valida dependências
        const valid = Waiter.validateDependencies(deps);
        if (!valid) {
            console.warn('⚠️ [payment.js] Algumas dependências estão faltando');
        }

        // 🔥 4. Inicializa VagasSystem
        VagasSystem.init(deps);

        // 🔥 5. Configura listeners de eventos
        document.addEventListener('app:state_changed', function(e) {
            const detail = e.detail || {};
            if (detail.key === 'credits' || detail.key === 'isPremium' || detail.key === 'isAdmin') {
                updateCreditsDisplay();
            }
        });

        document.addEventListener('creditsUpdated', function(e) {
            const data = e.detail || {};
            updateCreditsDisplay(data.credits, data.isPremium);
        });

        // 🔥 6. Expõe funções globais
        window.loadPremiumStatus = loadPremiumStatus;
        window.receiveDailyCredit = receiveDailyCredit;
        window.updateCreditsDisplay = updateCreditsDisplay;
        window.openCpfModal = openCpfModal;
        window.createPaymentWithPix = createPaymentWithPix;
        window.VagasSystem = VagasSystem;

        // 🔥 7. Marca como pronto
        window.paymentReady = true;
        window.paymentVersion = '7.1';
        window._paymentInitialized = true;

        // 🔥 8. Dispara evento
        window.dispatchEvent(new CustomEvent('paymentReady', {
            detail: {
                version: '7.1',
                integrated: true,
                appReady: appReady,
                dependencies: {
                    EventBus: !!deps.EventBus,
                    AppUtils: !!deps.AppUtils,
                    fetchWithAuth: !!deps.fetchWithAuth,
                    State: !!deps.State
                }
            }
        }));

        console.log('✅ [payment.js v7.1] Carregado com sucesso!');
        console.log(`   📦 EventBus: ${!!deps.EventBus}`);
        console.log(`   📦 AppUtils: ${!!deps.AppUtils}`);
        console.log(`   📦 fetchWithAuth: ${!!deps.fetchWithAuth}`);
        console.log(`   📦 State: ${!!deps.State}`);
        console.log(`   🎯 Polling adaptativo: ${CONFIG.VAGAS_UPDATE_INTERVAL_NORMAL/1000}s / ${CONFIG.VAGAS_UPDATE_INTERVAL_URGENT/1000}s`);
        console.log(`   ⏰ Status polling: ${CONFIG.STATUS_POLLING_INTERVAL/1000}s`);
    }

    // ==============================================
    // 🔥 INICIAR
    // ==============================================

    // Aguarda DOM e bibliotecas
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            // Pequeno delay para garantir que o app.js tenha tempo de carregar
            setTimeout(init, 300);
        });
    } else {
        setTimeout(init, 300);
    }

    // Fallback: se o app:ready chegar, inicia imediatamente
    document.addEventListener('app:ready', function() {
        console.log('📢 [payment.js] app:ready recebido, inicializando...');
        init();
    });

})();