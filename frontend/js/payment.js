// payment.js - VERSÃO 6.3 (PROTOCOLO COMPLETO DO APP.JS)
// ==============================================
// 🔥 MELHORIAS V6.3:
// 1. ✅ NOMES DE EVENTOS CORRETOS (creditsUpdated, premiumStatusUpdated, paymentReady)
// 2. ✅ ELIMINAÇÃO TOTAL DE POLLING (sem setInterval interno)
// 3. ✅ CONSUMO DE window.fetchWithAuth (não cria fetch próprio)
// 4. ✅ CONSUMO DE window.AppUtils (não duplica utilitários)
// 5. ✅ INICIALIZAÇÃO VIA evento 'appReady'
// 6. ✅ ESCUTA 'app:state_changed' para atualizações reativas
// 7. ✅ SEGUE ESTRITAMENTE O PROTOCOLO DO ORQUESTRADOR
// ==============================================

(function() {
    'use strict';

    console.log('🚀 Inicializando payment.js v6.3 (Protocolo app.js)...');

    // ==============================================
    // 🔒 CONFIGURAÇÕES (MÍNIMAS, APENAS O ESSENCIAL)
    // ==============================================

    const CONFIG = {
        MAX_CREDITS_BALANCE: 3,
        PIX_EXPIRY_MINUTES: 30,
        PROMOTIONAL_PRICE: 97.00,
        REGULAR_PRICE: 149.90,
        TOTAL_PROMOTIONAL_SLOTS: 100,
        DAYS_PREMIUM: 30
    };

    // ==============================================
    // 🔥 ESTADO INTERNO (SINCRONIZADO COM APP.JS)
    // ==============================================

    let _isInitialized = false;
    let _currentState = null;
    let _countdownInterval = null;

    // ==============================================
    // 🔥 FUNÇÃO DE INICIALIZAÇÃO (CHAMADA PELO APP.JS)
    // ==============================================

    function initModule(appState) {
        if (_isInitialized) {
            console.log('⚠️ payment.js já inicializado, ignorando...');
            return;
        }

        console.log('💳 Inicializando Módulo de Pagamento...');
        console.log('📊 Estado recebido do app.js:', appState);

        _currentState = appState || window.__APP_STATE || {};
        _isInitialized = true;

        // 1. Renderiza os componentes de planos
        renderPlans();

        // 2. Configura listeners de eventos
        setupEventListeners();

        // 3. Dispara evento de pronto (padrão camelCase)
        window.dispatchEvent(new CustomEvent('paymentReady', {
            detail: {
                loaded: true,
                version: '6.3',
                timestamp: Date.now()
            }
        }));

        console.log('✅ payment.js v6.3 inicializado com sucesso!');
        console.log('📡 Disparado: paymentReady');
    }

    // ==============================================
    // 🔥 CONFIGURAÇÃO DE EVENT LISTENERS
    // ==============================================

    function setupEventListeners() {
        console.log('📡 Configurando event listeners (protocolo app.js)...');

        // 🔥 ESCUTA 'app:state_changed' para atualizações reativas (SEM POLLING)
        window.addEventListener('app:state_changed', function(e) {
            const detail = e.detail || {};
            const state = detail.state || detail || {};
            
            console.log('📡 app:state_changed recebido:', state);

            // Atualiza estado interno
            _currentState = state;

            // Atualiza créditos na UI
            updateCreditsDisplay(state.credits, state.isPremium, state.isAdmin);

            // Se o status premium mudou, recarrega planos
            if (state.isPremium !== undefined) {
                renderPlans();
            }
        });

        // 🔥 ESCUTA 'appReady' (fallback - caso o app.js dispare)
        window.addEventListener('appReady', function(e) {
            console.log('📡 appReady recebido (fallback)');
            if (!_isInitialized) {
                const state = window.__APP_STATE || e.detail || {};
                initModule(state);
            }
        });

        // 🔥 ESCUTA 'app:ready' (outro fallback)
        document.addEventListener('app:ready', function(e) {
            console.log('📡 app:ready recebido (fallback)');
            if (!_isInitialized) {
                const detail = e.detail || {};
                initModule(detail);
            }
        });

        console.log('✅ Event listeners configurados:');
        console.log('   📡 Escutando: app:state_changed (reativo)');
        console.log('   📡 Escutando: appReady (fallback)');
        console.log('   📡 Disparando: paymentReady (quando pronto)');
        console.log('   📡 Disparando: creditsUpdated (quando créditos mudam)');
        console.log('   📡 Disparando: premiumStatusUpdated (quando status muda)');
    }

    // ==============================================
    // 🔥 RENDERIZAÇÃO DE PLANOS (USANDO AppUtils)
    // ==============================================

    function renderPlans() {
        const container = document.getElementById('plans-container');
        if (!container) {
            console.warn('⚠️ #plans-container não encontrado - página de planos?');
            return;
        }

        // 🔥 Usa AppUtils para formatar créditos
        const AppUtils = window.AppUtils || window.app?.AppUtils;
        const isAdmin = _currentState?.isAdmin || false;
        const isPremium = _currentState?.isPremium || false;
        const credits = _currentState?.credits || 0;

        console.log('📦 Renderizando planos...', { isAdmin, isPremium, credits });

        if (isAdmin) {
            container.innerHTML = getAdminHTML();
            return;
        }

        if (isPremium) {
            container.innerHTML = getActivePlanHTML();
            // Dispara evento de status premium atualizado (camelCase)
            window.dispatchEvent(new CustomEvent('premiumStatusUpdated', {
                detail: {
                    isPremium: true,
                    daysLeft: _currentState?.daysLeftPremium || 0,
                    creditsBalance: credits
                }
            }));
            return;
        }

        // Usuário normal (não premium)
        container.innerHTML = getStaticPlanHTML();
        
        // Configura listeners de compra
        setupPurchaseListeners();
    }

    // ==============================================
    // 🔥 HTML DOS PLANOS
    // ==============================================

    function getAdminHTML() {
        return `
            <div class="col-lg-8 mx-auto">
                <div class="admin-message" style="background: linear-gradient(135deg, #2c1a0a 0%, #3d2614 100%); border-radius: 40px; padding: 3rem; border: 1px solid #cd7f32; text-align: center;">
                    <i class="fas fa-crown" style="font-size: 4rem; color: #f5a623; margin-bottom: 1rem;"></i>
                    <h2 class="h3 mb-3" style="color: #f5a623;">👑 Você é Administrador</h2>
                    <p class="lead mb-4" style="color: rgba(255,255,255,0.7);">Como admin, você tem acesso ilimitado a todas as funcionalidades.</p>
                    <a href="/dashboard" class="btn btn-light btn-lg mt-3"><i class="fas fa-arrow-left me-2"></i> Voltar ao Dashboard</a>
                </div>
            </div>
        `;
    }

    function getActivePlanHTML() {
        return `
            <div class="col-lg-8 mx-auto">
                <div class="bronze-card active-plan" style="background: linear-gradient(135deg, #1a472a 0%, #2d6a4f 100%); border: 2px solid #48bb78; border-radius: 40px; padding: 3rem;">
                    <div class="text-center">
                        <div class="bronze-badge" style="background: linear-gradient(135deg, #48bb78, #2d6a4f);">
                            <i class="fas fa-check-circle"></i> PLANO ATIVO
                        </div>
                        <h2 style="color: #48bb78; margin: 1.5rem 0;"><i class="fas fa-crown me-2"></i>Plano Bronze Ativo</h2>
                        <div class="alert alert-success" style="background: rgba(72, 187, 120, 0.2); border-color: #48bb78; color: #48bb78;">
                            <i class="fas fa-check-circle me-2"></i>
                            Você já possui acesso premium! Aproveite todos os benefícios.
                        </div>
                        <a href="/dashboard" class="btn btn-success btn-lg mt-3">
                            <i class="fas fa-arrow-right me-2"></i> Ir para o Dashboard
                        </a>
                    </div>
                </div>
            </div>
        `;
    }

    function getStaticPlanHTML() {
        return `
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
                        <button class="btn btn-bronze btn-lg" id="btnBuyPlan" onclick="window.handlePurchase()">
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
    }

    // ==============================================
    // 🔥 CONFIGURAÇÃO DE LISTENERS DE COMPRA
    // ==============================================

    function setupPurchaseListeners() {
        const btnBuy = document.getElementById('btnBuyPlan');
        if (btnBuy) {
            // Remove listeners antigos para evitar duplicação
            const newBtn = btnBuy.cloneNode(true);
            btnBuy.parentNode.replaceChild(newBtn, btnBuy);
            
            newBtn.addEventListener('click', function(e) {
                e.preventDefault();
                handlePurchase();
            });
        }
    }

    // ==============================================
    // 🔥 HANDLE PURCHASE - USANDO fetchWithAuth GLOBAL
    // ==============================================

    function handlePurchase() {
        console.log('🛒 Iniciando processo de compra...');

        // Verifica se já é premium
        if (_currentState?.isPremium) {
            showNotification('✅ Você já possui um plano ativo!', 'success');
            window.location.href = '/dashboard';
            return;
        }

        // Verifica se é admin
        if (_currentState?.isAdmin) {
            showNotification('👑 Admin tem acesso ilimitado!', 'info');
            return;
        }

        // Abre modal de CPF
        openCpfModal();
    }

    // ==============================================
    // 🔥 MODAL CPF
    // ==============================================

    function openCpfModal() {
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
                        <button type="button" class="btn btn-bronze" id="btnProceedCpf"><i class="fas fa-arrow-right me-2"></i>Continuar para PIX</button>
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
        }

        const btnProceed = document.getElementById('btnProceedCpf');
        if (btnProceed) {
            btnProceed.addEventListener('click', function() {
                proceedWithCpf();
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

    function proceedWithCpf() {
        const cpfInput = document.getElementById('cpfInput');
        const cpfError = document.getElementById('cpfError');
        
        if (!cpfInput) {
            showNotification('Erro ao processar CPF. Tente novamente.', 'error');
            return;
        }
        
        const cpfLimpo = cpfInput.value.replace(/\D/g, '');
        
        // 🔥 Usa AppUtils para validar CPF se disponível
        let isValid = false;
        if (window.AppUtils?.validateCPF) {
            isValid = window.AppUtils.validateCPF(cpfLimpo);
        } else {
            // Fallback: validação simples
            isValid = cpfLimpo.length === 11 && !/^(\d)\1{10}$/.test(cpfLimpo);
        }
        
        if (!isValid) {
            if (cpfError) {
                cpfError.textContent = '❌ CPF inválido. Digite um CPF válido com 11 dígitos.';
                cpfError.classList.remove('d-none');
            }
            return;
        }
        
        if (cpfError) cpfError.classList.add('d-none');
        
        const cpfModal = bootstrap.Modal.getInstance(document.getElementById('cpfModal'));
        if (cpfModal) cpfModal.hide();
        
        // 🔥 Usa fetchWithAuth global para criar pagamento
        createPaymentWithPix(cpfLimpo);
    }

    // ==============================================
    // 🔥 CRIAÇÃO DE PAGAMENTO - USANDO fetchWithAuth GLOBAL
    // ==============================================

    async function createPaymentWithPix(cpf) {
        console.log('💳 Criando pagamento PIX para CPF:', cpf);
        showNotification('🔄 Gerando QR Code PIX...', 'info');

        try {
            // 🔥 Usa window.fetchWithAuth (global, fornecido pelo app.js)
            const fetchFn = window.fetchWithAuth || window.App?.fetchWithAuth || fetch;
            
            const response = await fetchFn('/api/payments/create-pix', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    cpf: cpf,
                    plan: 'premium_mensal'
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

            // Mostra modal PIX com os dados
            showPixModal(data);

        } catch (error) {
            console.error('❌ Erro ao criar pagamento:', error);
            showNotification(error.message || 'Erro ao gerar pagamento. Tente novamente.', 'error');
        }
    }

    // ==============================================
    // 🔥 MODAL PIX
    // ==============================================

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

    // ==============================================
    // 🔥 FUNÇÕES AUXILIARES
    // ==============================================

    function startCountdown(seconds) {
        if (_countdownInterval) clearInterval(_countdownInterval);
        
        let remaining = seconds || 30 * 60;
        const timerElement = document.getElementById('countdownTimer');
        
        _countdownInterval = setInterval(() => {
            if (remaining <= 0) {
                clearInterval(_countdownInterval);
                _countdownInterval = null;
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
            // 🔥 Usa window.fetchWithAuth (global)
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
                
                // 🔥 Dispara evento premiumStatusUpdated (camelCase)
                window.dispatchEvent(new CustomEvent('premiumStatusUpdated', {
                    detail: {
                        isPremium: true,
                        daysLeft: data.days_left || 30,
                        creditsBalance: data.credits_balance || 0
                    }
                }));

                // 🔥 Dispara evento creditsUpdated (camelCase)
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
    // 🔥 ATUALIZAÇÃO DE CRÉDITOS (USANDO AppUtils)
    // ==============================================

    function updateCreditsDisplay(credits, isPremium, isAdmin) {
        const AppUtils = window.AppUtils || window.app?.AppUtils;
        
        let displayText = '0';
        
        if (isAdmin) {
            displayText = '∞';
        } else if (AppUtils?.formatCreditsDisplay) {
            displayText = AppUtils.formatCreditsDisplay(credits, isPremium);
        } else {
            // Fallback
            displayText = isPremium ? `${credits || 0}/${CONFIG.MAX_CREDITS_BALANCE}` : String(credits || 0);
        }
        
        // Atualiza elementos na UI
        document.querySelectorAll('#creditsCount, #creditsDisplay, #uploadCredits, .credits-badge span').forEach(el => {
            if (el) el.textContent = displayText;
        });

        // 🔥 Dispara evento creditsUpdated (camelCase - esperado pelo app.js)
        window.dispatchEvent(new CustomEvent('creditsUpdated', {
            detail: {
                credits: credits || 0,
                display: displayText,
                maxCredits: CONFIG.MAX_CREDITS_BALANCE,
                isPremium: isPremium || false
            }
        }));
    }

    // ==============================================
    // 🔥 NOTIFICAÇÕES (USANDO AppUtils)
    // ==============================================

    function showNotification(message, type = 'info') {
        const AppUtils = window.AppUtils || window.app?.AppUtils;
        
        if (AppUtils?.showNotification) {
            return AppUtils.showNotification(message, type);
        }
        
        // Fallback
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
    // 🧹 CLEANUP
    // ==============================================

    function cleanup() {
        if (_countdownInterval) {
            clearInterval(_countdownInterval);
            _countdownInterval = null;
        }
        console.log('🧹 payment.js - Recursos limpos');
    }

    // ==============================================
    // 🌍 EXPOSIÇÃO GLOBAL (MÍNIMA)
    // ==============================================

    // Funções que precisam ser acessíveis via onclick
    window.handlePurchase = handlePurchase;
    window.copyPixCode = copyPixCode;
    window.verifyPayment = verifyPayment;
    window.openCpfModal = openCpfModal;
    window.proceedWithCpf = proceedWithCpf;

    // Status
    window.paymentReady = false;
    window.paymentVersion = '6.3';

    console.log('✅ payment.js v6.3 carregado - aguardando app.js');

    // ==============================================
    // 🔥 INICIALIZAÇÃO - PROTOCOLO DO APP.JS
    // ==============================================

    /**
     * 🔥 PROTOCOLO DE INICIALIZAÇÃO:
     * 
     * 1. Se o app.js já está pronto, usa window.__APP_STATE
     * 2. Caso contrário, aguarda o evento 'appReady'
     * 3. NUNCA inicializa antes do app.js estar pronto
     */

    // 🔥 Verifica se o app.js já está pronto
    const isAppReady = window.App?.isReady?.() || window._appReadyFired || false;
    const appState = window.__APP_STATE || {};

    if (isAppReady && appState.userInitialized) {
        console.log('✅ app.js já está pronto - inicializando imediatamente');
        initModule(appState);
    } else {
        // 🔥 Aguarda o evento 'appReady' (disparado pelo app.js)
        console.log('⏳ Aguardando evento appReady do orquestrador...');
        window.addEventListener('appReady', function(e) {
            console.log('📡 appReady recebido!');
            const state = window.__APP_STATE || e.detail || {};
            if (!_isInitialized) {
                initModule(state);
            }
        });

        // 🔥 Fallback: se o evento não chegar em 5 segundos, tenta usar appAuth
        setTimeout(() => {
            if (!_isInitialized && window.appAuth) {
                console.log('🔄 Fallback: usando appAuth após timeout');
                const state = {
                    isAdmin: window.appAuth.isAdmin?.() || false,
                    isPremium: window.appAuth.isPremium?.() || false,
                    credits: window.appAuth.getCredits?.() || 0,
                    user: window.appAuth.getCurrentUser?.() || null,
                    userInitialized: true
                };
                initModule(state);
            }
        }, 5000);
    }

    console.log('✅ payment.js v6.3 carregado!');
    console.log('   📡 Protocolo:');
    console.log('   🔹 Dispara: paymentReady (camelCase)');
    console.log('   🔹 Dispara: creditsUpdated (camelCase)');
    console.log('   🔹 Dispara: premiumStatusUpdated (camelCase)');
    console.log('   🔹 Escuta: app:state_changed (reativo)');
    console.log('   🔹 Escuta: appReady (inicialização)');
    console.log('   🔹 Usa: window.fetchWithAuth (global)');
    console.log('   🔹 Usa: window.AppUtils (utilitários)');
    console.log('   🔹 SEM POLLING! (apenas eventos)');

})(); // <-- FECHA A IIFE