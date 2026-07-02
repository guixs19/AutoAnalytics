// payment.js - VERSÃO ESTÁVEL v3.0.2
// ==============================================
// 🔥 CORREÇÕES:
// 1. REMOÇÃO DA DUPLA RENDERIZAÇÃO (só app:ready)
// 2. FLAG isRendered para evitar renderizações múltiplas
// 3. TRY/CATCH em todas as funções críticas
// 4. VERIFICAÇÃO se o container ainda existe antes de renderizar
// 5. MELHOR MANEJO DE ERROS (fallback amigável)
// 6. PRESERVAÇÃO DA ESTÉTICA E ROTAS
// ==============================================

(function() {
    'use strict';

    console.log('🚀 Inicializando payment.js v3.0.2 (Estável - Sem bugs)...');

    // ==============================================
    // 🔥 FLAG DE CONTROLE (EVITA DUPLA RENDERIZAÇÃO)
    // ==============================================

    let isRendered = false;
    let isInitializing = false;
    let renderTimeout = null;

    // ==============================================
    // 🔥 CONFIGURAÇÕES (USA APP.JS)
    // ==============================================

    const APP_CONFIG = window.__APP_CONFIG || null;
    const AppUtils = window.AppUtils || null;

    const CONFIG = APP_CONFIG || {
        MAX_CREDITS_BALANCE: 3,
        INITIAL_FREE_CREDITS: 3,
        PROMOTIONAL_PRICE: 97.00,
        REGULAR_PRICE: 149.90,
        TOTAL_PROMOTIONAL_SLOTS: 100,
        DAYS_PREMIUM: 30,
        API_BASE: '/api'
    };

    const Utils = AppUtils || {
        sanitizeNumber: (value, defaultValue = 0) => {
            const num = parseFloat(String(value).replace(/[^0-9.,-]/g, '').replace(',', '.'));
            return isNaN(num) ? defaultValue : num;
        },
        showNotification: (message, type = 'info') => {
            if (window.toastr?.[type]) {
                try {
                    window.toastr[type](message);
                    return true;
                } catch (e) {
                    console.warn('Toastr falhou:', e);
                }
            }
            console.log(`[${type}] ${message}`);
            if (type === 'error' || type === 'warning') {
                alert(`⚠️ ${message}`);
            }
            return true;
        },
        formatCreditsDisplay: (credits, isPremium = false) => {
            const safeCredits = Utils.sanitizeNumber(credits, 0);
            if (window.__APP_STATE?.isAdmin) return '∞';
            if (isPremium) return `${safeCredits}/${CONFIG.MAX_CREDITS_BALANCE}`;
            return safeCredits.toString();
        },
        escapeHtml: (str) => {
            if (!str) return '';
            const div = document.createElement('div');
            div.textContent = str;
            return div.innerHTML;
        }
    };

    const API_URL = CONFIG.API_BASE || (() => {
        const isLocalhost = window.location.hostname === 'localhost' || 
                            window.location.hostname === '127.0.0.1';
        return isLocalhost ? 'http://localhost:8000/api' : '/api';
    })();

    console.log(`🌐 API_URL: ${API_URL}`);
    console.log(`💰 Preço Fundador: R$ ${CONFIG.PROMOTIONAL_PRICE}`);

    // ==============================================
    // 🔥 FUNÇÕES DE AUTENTICAÇÃO (SEGURAS)
    // ==============================================

    function isAdmin() {
        try {
            if (window.appAuth?.isAdmin) return window.appAuth.isAdmin();
            if (window.App?.isAdmin) return window.App.isAdmin();
            if (window.__APP_STATE?.isAdmin) return window.__APP_STATE.isAdmin;
            return false;
        } catch { return false; }
    }

    function getCredits() {
        try {
            if (window.appAuth?.getCredits) return window.appAuth.getCredits();
            if (window.App?.getCredits) return window.App.getCredits();
            if (window.__APP_STATE?.credits !== undefined) return window.__APP_STATE.credits;
            return 0;
        } catch { return 0; }
    }

    function isPremium() {
        try {
            if (window.appAuth?.isPremium) return window.appAuth.isPremium();
            if (window.App?.isPremium) return window.App.isPremium();
            if (window.__APP_STATE?.isPremium) return window.__APP_STATE.isPremium;
            return false;
        } catch { return false; }
    }

    // ==============================================
    // 🔥 FETCH COM AUTH (SEGURO)
    // ==============================================

    async function fetchWithAuth(url, options = {}) {
        // ✅ PRIORIDADE: Usar fetchWithAuth do app.js
        if (window.appAuth?.fetchWithAuth) {
            try {
                return await window.appAuth.fetchWithAuth(url, options);
            } catch (e) {
                console.warn('appAuth.fetchWithAuth falhou:', e);
            }
        }

        // Fallback mínimo
        const token = localStorage.getItem('access_token');
        if (!token) {
            console.warn('⚠️ Sem token para fetchWithAuth');
            return null;
        }

        const headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': `Bearer ${token}`,
            ...options.headers
        };

        try {
            const response = await fetch(url, { ...options, headers });
            
            if (response.status === 401) {
                // Tenta renovar via app.js
                if (window.appAuth?.refreshTokenSafely) {
                    const refreshed = await window.appAuth.refreshTokenSafely();
                    if (refreshed) {
                        const newToken = localStorage.getItem('access_token');
                        if (newToken) {
                            headers['Authorization'] = `Bearer ${newToken}`;
                            return await fetch(url, { ...options, headers });
                        }
                    }
                }
                // Se falhou, redireciona
                Utils.showNotification('Sessão expirada. Faça login novamente.', 'warning');
                if (window.App?.logout) {
                    window.App.logout();
                } else {
                    localStorage.clear();
                    window.location.replace('/login');
                }
                return null;
            }
            
            return response;
        } catch (error) {
            console.error('fetchWithAuth error:', error);
            return null;
        }
    }

    // ==============================================
    // 🔥 ATUALIZAR CRÉDITOS (SEGURO)
    // ==============================================

    async function updateCreditsDisplay() {
        try {
            let credits = getCredits();
            let isPremiumUser = isPremium();
            
            // Tenta carregar do app.js
            if (window.appAuth?.loadUserCredits) {
                await window.appAuth.loadUserCredits();
                credits = window.appAuth.getCredits?.() || 0;
                isPremiumUser = window.appAuth.isPremium?.() || false;
            } else if (window.App?.loadCredits) {
                await window.App.loadCredits();
                credits = window.App.getCredits?.() || 0;
                isPremiumUser = window.App.isPremium?.() || false;
            }
            
            const formattedDisplay = Utils.formatCreditsDisplay(credits, isPremiumUser);
            
            // Atualiza UI
            document.querySelectorAll('#creditsCount, #creditsDisplay, #uploadCredits, .credits-badge span, .credits-value').forEach(el => {
                if (el) el.textContent = formattedDisplay;
            });
            
            // Dispara evento padronizado
            window.dispatchEvent(new CustomEvent('credits:updated', {
                detail: { 
                    credits, 
                    display: formattedDisplay, 
                    maxCredits: CONFIG.MAX_CREDITS_BALANCE, 
                    isPremium: isPremiumUser 
                },
                bubbles: true
            }));
            
            return true;
        } catch (error) {
            console.error('Erro ao atualizar créditos:', error);
            return false;
        }
    }

    // ==============================================
    // 🔥 RENDERIZAÇÃO DO PLANO (CORRIGIDA - SEM DUPLICAÇÃO)
    // ==============================================

    function isPlansPage() {
        return document.getElementById('plans-container') !== null;
    }

    function getContainer() {
        return document.getElementById('plans-container');
    }

    async function renderPlan() {
        // ✅ VERIFICA SE JÁ FOI RENDERIZADO OU ESTÁ INICIALIZANDO
        if (isRendered) {
            console.log('⚠️ Plano já renderizado, ignorando...');
            return;
        }

        if (isInitializing) {
            console.log('⚠️ Renderização em andamento, aguarde...');
            return;
        }

        // ✅ VERIFICA SE É PÁGINA DE PLANOS
        if (!isPlansPage()) {
            console.log('ℹ️ Não é página de planos, ignorando renderização.');
            return;
        }

        const container = getContainer();
        if (!container) {
            console.warn('⚠️ Container #plans-container não encontrado');
            return;
        }

        // ✅ MARCA COMO INICIALIZANDO
        isInitializing = true;
        console.log('📦 Renderizando plano...');

        try {
            // 🔥 LIMPA TIMEOUT ANTERIOR
            if (renderTimeout) {
                clearTimeout(renderTimeout);
                renderTimeout = null;
            }

            // 🔥 VERIFICA SE O CONTAINER AINDA EXISTE (PODE TER SIDO REMOVIDO)
            if (!document.body.contains(container)) {
                console.warn('⚠️ Container foi removido do DOM, abortando renderização.');
                isInitializing = false;
                return;
            }

            // 🔥 VERIFICA SE É ADMIN
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
                isRendered = true;
                isInitializing = false;
                return;
            }

            // 🔥 BUSCA DADOS DA API
            let promoData = null;
            let plansData = null;

            try {
                // Busca status da promoção
                const promoResponse = await fetchWithAuth(`${API_URL}/payments/promotion-status`);
                if (promoResponse?.ok) {
                    promoData = await promoResponse.json();
                }

                // Busca planos
                const plansResponse = await fetchWithAuth(`${API_URL}/payments/plans`);
                if (plansResponse?.ok) {
                    plansData = await plansResponse.json();
                }
            } catch (error) {
                console.warn('Erro ao buscar dados da API:', error);
            }

            // 🔥 DADOS PADRÃO (FALLBACK)
            const defaultData = {
                remaining_slots: CONFIG.TOTAL_PROMOTIONAL_SLOTS,
                total_slots: CONFIG.TOTAL_PROMOTIONAL_SLOTS,
                promotional_price: CONFIG.PROMOTIONAL_PRICE,
                regular_price: CONFIG.REGULAR_PRICE,
                user_locked_price: null
            };

            const finalData = promoData || defaultData;

            // 🔥 CALCULA DADOS
            const vagasRestantes = Utils.sanitizeNumber(finalData.remaining_slots, CONFIG.TOTAL_PROMOTIONAL_SLOTS);
            const totalVagas = Utils.sanitizeNumber(finalData.total_slots, CONFIG.TOTAL_PROMOTIONAL_SLOTS);
            const precoPromocional = Utils.sanitizeNumber(finalData.promotional_price, CONFIG.PROMOTIONAL_PRICE);
            const precoRegular = Utils.sanitizeNumber(finalData.regular_price, CONFIG.REGULAR_PRICE);
            const isUserLocked = finalData.user_locked_price !== null && finalData.user_locked_price !== undefined;
            const isSoldOut = vagasRestantes <= 0;
            const precoAtual = isSoldOut ? precoRegular : precoPromocional;
            const percentual = totalVagas > 0 ? ((totalVagas - vagasRestantes) / totalVagas) * 100 : 0;
            const isUrgent = vagasRestantes <= 20 && vagasRestantes > 0;

            // 🔥 CONSTRÓI HTML DO PLANO
            const html = `
                <div class="col-lg-8 mx-auto">
                    <div class="bronze-card" data-aos="fade-up" data-aos-duration="800">
                        <div class="bronze-badge">
                            <i class="fas fa-fire"></i> 
                            ${isSoldOut ? 'PROMOÇÃO ENCERRADA' : (isUserLocked ? '🔥 SEU PREÇO VITALÍCIO' : '🔥 PROMOÇÃO FUNDADOR')}
                        </div>
                        
                        ${isUserLocked ? `
                            <div class="vitalicio-badge" style="background: linear-gradient(135deg, #28a745, #20c997); color: white; padding: 0.5rem 1.2rem; border-radius: 50px; text-align: center; margin: 0.5rem auto 1rem; font-weight: 700; display: inline-block; width: 100%;">
                                <i class="fas fa-gem me-2"></i>
                                PREÇO VITALÍCIO GARANTIDO!
                                <small>R$ ${precoAtual.toFixed(2).replace('.', ',')} para sempre</small>
                            </div>
                        ` : ''}
                        
                        <div class="bronze-title">
                            <span class="icon-big"><i class="fas fa-crown"></i></span>
                            <h2>Plano Bronze</h2>
                            <p class="subtitle">O plano ideal para sua oficina crescer com IA</p>
                        </div>
                        
                        <div class="price-container">
                            ${!isSoldOut && !isUserLocked ? `<span class="old-price">De R$ ${precoRegular.toFixed(2).replace('.', ',')}</span>` : ''}
                            <div class="price-tag">R$ ${precoAtual.toFixed(2).replace('.', ',')} <small>à vista</small></div>
                            ${!isSoldOut && !isUserLocked ? `<span class="economy-badge"><i class="fas fa-tag"></i> Economia de ${Math.round(((precoRegular - precoPromocional) / precoRegular) * 100)}%</span>` : ''}
                            ${isUserLocked ? `<span class="economy-badge" style="background: linear-gradient(135deg, #28a745, #20c997);"><i class="fas fa-lock me-1"></i> PREÇO BLOQUEADO - VITALÍCIO</span>` : ''}
                            ${isSoldOut && !isUserLocked ? `<span class="economy-badge" style="background: linear-gradient(135deg, #dc3545, #c0392b);"><i class="fas fa-exclamation-triangle me-1"></i> PROMOÇÃO ESGOTADA</span>` : ''}
                        </div>
                        
                        ${!isSoldOut && !isUserLocked ? `
                            <div class="vagas-counter ${isUrgent ? 'vagas-urgent' : ''}">
                                <div>
                                    <span class="vagas-label">🎯 Apenas</span>
                                    <span class="vagas-number">${vagasRestantes}</span>
                                    <span class="vagas-label">vagas restantes de ${totalVagas}</span>
                                </div>
                                <div class="vagas-progress">
                                    <div class="vagas-progress-bar" style="width: ${Math.min(100, percentual)}%;"></div>
                                </div>
                                ${isUrgent ? `
                                    <div class="mt-2 text-center">
                                        <strong style="color: #f5a623;">🔥 URGENTE! ÚLTIMAS ${vagasRestantes} VAGAS! 🔥</strong>
                                    </div>
                                ` : ''}
                            </div>
                        ` : ''}
                        
                        ${isUserLocked ? `
                            <div class="vagas-counter" style="background: rgba(40, 167, 69, 0.2); border-color: #28a745;">
                                <div>
                                    <span class="vagas-label">✅ PREÇO GARANTIDO</span>
                                    <div>
                                        <span class="vagas-number" style="color: #28a745;">R$ ${precoAtual.toFixed(2).replace('.', ',')}</span>
                                        <span class="vagas-label">para sempre!</span>
                                    </div>
                                </div>
                            </div>
                        ` : ''}
                        
                        ${isSoldOut && !isUserLocked ? `
                            <div class="vagas-counter" style="background: rgba(220, 53, 69, 0.2); border-color: #dc3545;">
                                <div>
                                    <span class="vagas-label">❌ PROMOÇÃO ESGOTADA</span>
                                    <div>
                                        <span class="vagas-number" style="color: #dc3545;">0</span>
                                        <span class="vagas-label">vagas restantes</span>
                                    </div>
                                </div>
                            </div>
                        ` : ''}
                        
                        <div class="bronze-features">
                            <div class="bronze-feature"><i class="fas fa-check-circle check"></i> <span><strong>30 créditos</strong> para análises completas</span></div>
                            <div class="bronze-feature"><i class="fas fa-check-circle check"></i> <span><strong>Análise com IA</strong> (Google Gemini)</span></div>
                            <div class="bronze-feature"><i class="fas fa-check-circle check"></i> <span><strong>Até 3 arquivos</strong> por análise (CSV/Excel)</span></div>
                            <div class="bronze-feature"><i class="fas fa-check-circle check"></i> <span>📊 <strong>Dashboard completo</strong> com métricas</span></div>
                            <div class="bronze-feature"><i class="fas fa-check-circle check"></i> <span>📄 <strong>Relatórios em PDF</strong> automáticos</span></div>
                            <div class="bronze-feature"><i class="fas fa-check-circle check"></i> <span><strong>Suporte prioritário</strong> por email</span></div>
                            <div class="bronze-feature"><i class="fas fa-check-circle check"></i> <span>💎 <strong>Preço vitalício garantido</strong> (nunca aumenta)</span></div>
                        </div>
                        
                        <div class="plan-info">
                            <div class="row text-center">
                                <div class="col-4"><i class="fas fa-coins fa-lg"></i><div class="small fw-bold mt-1">30</div><div class="small text-muted">Créditos</div></div>
                                <div class="col-4"><i class="fas fa-file-alt fa-lg"></i><div class="small fw-bold mt-1">3</div><div class="small text-muted">Arquivos/vez</div></div>
                                <div class="col-4"><i class="fas fa-infinity fa-lg"></i><div class="small fw-bold mt-1">∞</div><div class="small text-muted">Vitalício</div></div>
                            </div>
                        </div>
                        
                        <div class="d-grid gap-3 mt-4">
                            <button class="btn btn-bronze btn-lg" onclick="window.openCpfModal('premium_mensal')" id="planPurchaseBtn">
                                <i class="fas fa-bolt me-2"></i>
                                ${isUserLocked ? 'RENOVAR MEU PLANO' : (isSoldOut ? `COMPRAR POR R$ ${precoAtual.toFixed(2).replace('.', ',')}` : `🔥 GARANTIR PREÇO FUNDADOR R$ ${precoAtual.toFixed(2).replace('.', ',')}`)}
                                <small class="d-block fs-10">${isUserLocked ? 'Pagamento vitalício garantido' : 'Pagamento seguro via PIX'}</small>
                            </button>
                        </div>
                        
                        <div class="limit-warning">
                            <i class="fas fa-info-circle"></i>
                            <span>Este é um <strong>plano vitalício</strong> com preço especial para os primeiros <strong>100 clientes</strong>.</span>
                        </div>
                        
                        <div class="security-seals">
                            <span class="seal"><i class="fas fa-lock"></i> Pagamento Seguro</span>
                            <span class="seal"><i class="fas fa-shield-alt"></i> PoW Protegido</span>
                            <span class="seal"><i class="fas fa-credit-card"></i> PIX</span>
                            <span class="seal"><i class="fas fa-undo-alt"></i> 7 Dias de Garantia</span>
                        </div>
                    </div>
                </div>
            `;

            // 🔥 VERIFICA SE O CONTAINER AINDA EXISTE ANTES DE INSERIR
            if (!document.body.contains(container)) {
                console.warn('⚠️ Container foi removido do DOM antes de inserir o HTML.');
                isInitializing = false;
                return;
            }

            // 🔥 INSERE O HTML
            container.innerHTML = html;

            // 🔥 REINICIA ANIMAÇÕES AOS (SE DISPONÍVEL)
            if (typeof AOS !== 'undefined' && AOS.refresh) {
                setTimeout(() => {
                    try {
                        AOS.refresh();
                    } catch (e) {
                        // Ignora erro no AOS
                    }
                }, 100);
            }

            // 🔥 MARCA COMO RENDERIZADO
            isRendered = true;
            isInitializing = false;

            console.log('✅ Plano renderizado com sucesso!');
            console.log(`   📊 Vagas: ${vagasRestantes}/${totalVagas}`);
            console.log(`   💰 Preço: R$ ${precoAtual.toFixed(2)}`);
            console.log(`   🔒 Usuário bloqueou preço? ${isUserLocked}`);

        } catch (error) {
            console.error('❌ Erro ao renderizar plano:', error);
            isInitializing = false;

            // 🔥 FALLBACK: MENSAGEM DE ERRO AMIGÁVEL
            try {
                if (document.body.contains(container)) {
                    container.innerHTML = `
                        <div class="col-lg-8 mx-auto">
                            <div class="alert alert-warning text-center p-5" style="background: rgba(245, 166, 35, 0.1); border: 1px solid #f5a623; border-radius: 20px;">
                                <i class="fas fa-exclamation-triangle fa-3x mb-3" style="color: #f5a623;"></i>
                                <h4 style="color: #f5a623;">Ops! Não foi possível carregar o plano</h4>
                                <p style="color: rgba(255,255,255,0.6);">Tente recarregar a página ou entre em contato com o suporte.</p>
                                <button class="btn btn-outline-warning mt-2" onclick="location.reload()" style="border-color: #f5a623; color: #f5a623;">
                                    <i class="fas fa-sync-alt me-2"></i> Recarregar
                                </button>
                            </div>
                        </div>
                    `;
                }
            } catch (e) {
                console.error('Erro ao mostrar fallback:', e);
            }
        }
    }

    // ==============================================
    // 🔥 FUNÇÕES DE CPF E PIX (ESPECÍFICAS DO PAYMENT)
    // ==============================================

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

    window.openCpfModal = function(planId) {
        if (isAdmin()) {
            Utils.showNotification('👑 Como administrador, você tem acesso ilimitado.', 'info');
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
                        <button type="button" class="btn btn-bronze" onclick="window.proceedWithCpf('${planId}')"><i class="fas fa-arrow-right me-2"></i>Continuar para PIX</button>
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

        new bootstrap.Modal(cpfModal).show();
    };

    window.proceedWithCpf = function(planId) {
        const cpfInput = document.getElementById('cpfInput');
        const cpfError = document.getElementById('cpfError');
        
        if (!cpfInput) {
            Utils.showNotification('Erro ao processar CPF. Tente novamente.', 'error');
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
        
        const cpfModal = bootstrap.Modal.getInstance(document.getElementById('cpfModal'));
        if (cpfModal) cpfModal.hide();
        
        showPixModal(planId, cpfLimpo);
    };

    let countdownInterval = null;

    function showPixModal(planId, cpf) {
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
                            <small>R$ 97,00 - Preço bloqueado VITALÍCIO!</small>
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
                        
                        <button class="btn w-100 mb-3" onclick="window.copyPixCode()" 
                                style="background: rgba(255,255,255,0.06); color: #f5a623; border: 1px solid rgba(205,127,50,0.3); border-radius: 12px; padding: 0.75rem;">
                            <i class="fas fa-copy me-2"></i> Copiar Chave PIX
                        </button>
                        
                        <div class="alert alert-info small" style="background: rgba(245, 166, 35, 0.08); border-color: rgba(205,127,50,0.2); color: rgba(255,255,255,0.7);">
                            <i class="fas fa-info-circle me-2"></i>
                            <strong>Informações do pagamento:</strong><br>
                            <strong>Plano Bronze</strong> - Valor: R$ 97,00<br>
                            <span class="text-success">✅ Você está comprando na promoção! Preço R$ 97,00 garantido para sempre.</span><br>
                            <span style="color: rgba(255,255,255,0.5);">⏰ Este QR Code expira em <strong id="countdownTimer">30:00</strong> minutos.</span>
                        </div>
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
        
        let remaining = seconds;
        const timerElement = document.getElementById('countdownTimer');
        
        countdownInterval = setInterval(() => {
            if (remaining <= 0) {
                clearInterval(countdownInterval);
                if (timerElement) {
                    timerElement.textContent = 'Expirado!';
                    timerElement.style.color = '#dc3545';
                }
                Utils.showNotification('⏰ QR Code expirado. Por favor, gere um novo pagamento.', 'warning');
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
            navigator.clipboard.writeText(code)
                .then(() => Utils.showNotification('✅ Chave PIX copiada!', 'success'))
                .catch(() => {
                    const textarea = document.createElement('textarea');
                    textarea.value = code;
                    textarea.style.position = 'fixed';
                    textarea.style.opacity = '0';
                    document.body.appendChild(textarea);
                    textarea.select();
                    document.execCommand('copy');
                    document.body.removeChild(textarea);
                    Utils.showNotification('✅ Chave PIX copiada!', 'success');
                });
        }
    };

    // ==============================================
    // 🔥 STATUS PREMIUM E CRÉDITOS (AUXILIARES)
    // ==============================================

    async function loadPremiumStatus() {
        try {
            if (window.App?.loadPremiumStatus) {
                return await window.App.loadPremiumStatus();
            }
            
            const response = await fetchWithAuth(`${API_URL}/payments/premium-status`);
            if (response?.ok) {
                const data = await response.json();
                window.dispatchEvent(new CustomEvent('premium:status_updated', {
                    detail: {
                        isPremium: data.is_premium || false,
                        daysLeft: data.days_left || 0,
                        hasPromotionalPrice: data.promotional_price_locked || false,
                        promotionalPrice: data.promotional_price || null,
                        canReceiveDailyCredit: data.can_receive_today || false,
                        receivedDailyCreditToday: data.received_today || false,
                        creditsBalance: data.credits_balance || 0,
                        maxCredits: data.max_credits_balance || CONFIG.MAX_CREDITS_BALANCE
                    },
                    bubbles: true
                }));
                return data;
            }
        } catch (error) {
            console.error('Erro ao carregar status premium:', error);
        }
        return null;
    }

    async function receiveDailyCredit() {
        try {
            if (window.App?.receiveDailyCredit) {
                return await window.App.receiveDailyCredit();
            }
            
            const response = await fetchWithAuth(`${API_URL}/payments/daily-credit`, { method: 'POST' });
            if (response?.ok) {
                const data = await response.json();
                if (data.success) {
                    Utils.showNotification(`✅ ${data.message || 'Crédito recebido com sucesso!'}`, 'success');
                    setTimeout(() => loadPremiumStatus(), 500);
                    setTimeout(() => updateCreditsDisplay(), 1000);
                    return data;
                } else {
                    Utils.showNotification(data.message || 'Erro ao receber crédito', 'warning');
                    return data;
                }
            }
        } catch (error) {
            console.error('Erro ao receber crédito:', error);
            Utils.showNotification('Erro de conexão. Tente novamente.', 'error');
        }
        return null;
    }

    // ==============================================
    // 🔥 INICIALIZAÇÃO (ÚNICA, ESTÁVEL)
    // ==============================================

    let isInitialized = false;

    function initializePayment() {
        if (isInitialized) {
            console.log('⚠️ payment.js já inicializado, ignorando...');
            return;
        }

        console.log('📄 Inicializando payment.js v3.0.2...');

        // ✅ MARCA COMO INICIALIZADO
        isInitialized = true;

        // ✅ ATUALIZA CRÉDITOS
        updateCreditsDisplay();

        // ✅ RENDERIZA PLANO (SE FOR PÁGINA DE PLANOS)
        if (isPlansPage()) {
            // Pequeno delay para garantir que o DOM está pronto
            setTimeout(() => {
                renderPlan();
            }, 200);
        }

        // ✅ INICIA POLLING DE CRÉDITOS (30s)
        setInterval(updateCreditsDisplay, 30000);

        // ✅ DISPARA EVENTO DE PRONTO
        window.dispatchEvent(new CustomEvent('payment:ready', {
            detail: { 
                loaded: true, 
                version: '3.0.2',
                consumer: 'app.js'
            },
            bubbles: true
        }));

        console.log('✅ payment.js v3.0.2 inicializado com sucesso!');
        console.log('   🔧 Renderização única (evita duplicação)');
        console.log('   📡 Aguarda app:ready antes de renderizar');
        console.log('   🔗 Eventos padronizados: credits:updated, premium:status_updated');
    }

    // ✅ PRIORIDADE 1: Aguardar evento app:ready
    document.addEventListener('app:ready', function(e) {
        console.log('📢 payment.js: app:ready recebido!');
        if (!isInitialized) {
            setTimeout(initializePayment, 100);
        }
    });

    // ✅ PRIORIDADE 2: Verificar se app já está pronto
    if (window._appReadyFired || window.App?.isReady?.() === true) {
        console.log('📢 payment.js: app já estava pronto!');
        if (!isInitialized) {
            setTimeout(initializePayment, 100);
        }
    }

    // ✅ PRIORIDADE 3: Fallback seguro (se app.js não carregar)
    setTimeout(function() {
        if (!isInitialized) {
            console.warn('⚠️ payment.js: app.js não detectado. Inicializando com fallback...');
            initializePayment();
        }
    }, 5000);

    // ==============================================
    // 🔥 EXPOSIÇÃO DE FUNÇÕES GLOBAIS
    // ==============================================

    window.renderPlan = renderPlan;
    window.updateCreditsDisplay = updateCreditsDisplay;
    window.loadPremiumStatus = loadPremiumStatus;
    window.receiveDailyCredit = receiveDailyCredit;
    window.sanitizeCPF = sanitizeCPF;
    window.validateCPF = validateCPF;
    window.isPlansPage = isPlansPage;
    window.getContainer = getContainer;

    console.log('✅ payment.js v3.0.2 carregado!');
    console.log('   🔧 Renderização única (flag isRendered)');
    console.log('   🔒 Try/Catch em todas as funções críticas');
    console.log('   🛡️ Verificação de existência do container');
    console.log('   💰 Preço Fundador: R$ ' + CONFIG.PROMOTIONAL_PRICE);

})();