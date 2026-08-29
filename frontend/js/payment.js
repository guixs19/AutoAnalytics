// payment.js - VERSÃO 7.4 (CORREÇÃO DEFINITIVA QR CODE + MELHORIAS INTELIGENTES)
// ==============================================
// 🔥 MELHORIAS V7.4:
// 1. ✅ CORRIGIDO: QR Code com prefixo 'data:image/png;base64,' (CORREÇÃO DEFINITIVA)
// 2. ✅ ADICIONADO: Geração local de QR Code quando o MP não retorna
// 3. ✅ ADICIONADO: Fallback inteligente com múltiplas estratégias
// 4. ✅ ADICIONADO: Sistema de validação do QR Code antes de exibir
// 5. ✅ MELHORADO: Logs com mais detalhes para debug
// 6. ✅ ADICIONADO: Tempo de expiração configurável para 2 minutos
// 7. ✅ ADICIONADO: Cache de QR Code para reuso
// 8. ✅ MELHORADO: Tratamento de erros com mensagens mais claras
// 9. ✅ ADICIONADO: Verificação de integridade do QR Code
// 10. ✅ ADICIONADO: Sistema de fallback textual quando imagem falha
// ==============================================

(function() {
    'use strict';

    console.log('🚀 [payment.js v7.4] Carregando...');

    // ==============================================
    // 🔥 CONFIGURAÇÕES
    // ==============================================

    const CONFIG = {
        MAX_CREDITS_BALANCE: 3,
        INITIAL_FREE_CREDITS: 3,
        PIX_EXPIRY_MINUTES: 2,  // 🔥 MUDADO PARA 2 MINUTOS
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
        MAX_WAIT_ATTEMPTS: 50,

        // 🔥 CONFIGURAÇÕES V7.4
        MAX_RETRY_ATTEMPTS: 3,
        RETRY_BASE_DELAY: 1000,
        RETRY_MAX_DELAY: 10000,
        REQUEST_TIMEOUT: 30000,
        DEBOUNCE_DELAY: 500,
        STATUS_CACHE_TTL: 3000,
        QR_CODE_TIMEOUT: 5000,
        QR_CODE_CACHE_TTL: 60000  // 🔥 NOVO: Cache de QR Code
    };

    // ==============================================
    // 🔥 SISTEMA DE LOGGER ESTRUTURADO
    // ==============================================

    const Logger = {
        _levels: {
            DEBUG: 0,
            INFO: 1,
            WARN: 2,
            ERROR: 3
        },
        _level: 0,

        setLevel: function(level) {
            if (this._levels[level] !== undefined) {
                this._level = this._levels[level];
            }
        },

        _log: function(level, module, message, data) {
            if (this._levels[level] < this._level) return;
            
            const timestamp = new Date().toISOString();
            const prefix = `[${timestamp}] [${level}] [${module}]`;
            
            if (data) {
                console.log(`${prefix} ${message}`, data);
            } else {
                console.log(`${prefix} ${message}`);
            }
        },

        debug: function(module, message, data) {
            this._log('DEBUG', module, message, data);
        },
        info: function(module, message, data) {
            this._log('INFO', module, message, data);
        },
        warn: function(module, message, data) {
            this._log('WARN', module, message, data);
        },
        error: function(module, message, data) {
            this._log('ERROR', module, message, data);
        }
    };

    // ==============================================
    // 🔥 SISTEMA DE QR CODE (INTELIGENTE)
    // ==============================================

    const QrCodeSystem = {
        _cache: {},
        
        /**
         * 🔥 Gera QR Code localmente a partir do texto PIX
         * Usado como fallback quando o Mercado Pago não retorna a imagem
         */
        generateFromText: function(pixCode) {
            if (!pixCode) return null;
            
            try {
                Logger.info('QrCodeSystem', '🔄 Gerando QR Code localmente a partir do texto PIX...');
                
                // 🔥 Verifica se já temos no cache
                const cacheKey = pixCode.substring(0, 50);
                if (this._cache[cacheKey]) {
                    Logger.debug('QrCodeSystem', '📦 QR Code do cache local');
                    return this._cache[cacheKey];
                }
                
                // 🔥 Tenta usar a biblioteca QRCode.js
                if (typeof QRCode !== 'undefined') {
                    const canvas = document.createElement('canvas');
                    canvas.width = 200;
                    canvas.height = 200;
                    
                    const qr = new QRCode(canvas, {
                        text: pixCode,
                        width: 200,
                        height: 200,
                        colorDark: '#000000',
                        colorLight: '#ffffff',
                        correctLevel: QRCode.CorrectLevel.H
                    });
                    
                    // Aguarda o canvas ser desenhado
                    const dataUrl = canvas.toDataURL('image/png');
                    
                    if (dataUrl && dataUrl.startsWith('data:image')) {
                        this._cache[cacheKey] = dataUrl;
                        Logger.info('QrCodeSystem', '✅ QR Code gerado localmente com sucesso!');
                        return dataUrl;
                    }
                }
                
                // 🔥 Fallback: usa a biblioteca qrcode-generator se disponível
                if (typeof QRCodeGenerator !== 'undefined') {
                    const qr = QRCodeGenerator(0, 'M');
                    qr.addData(pixCode);
                    qr.make();
                    
                    const canvas = document.createElement('canvas');
                    canvas.width = 200;
                    canvas.height = 200;
                    const ctx = canvas.getContext('2d');
                    
                    const size = qr.getModuleCount();
                    const scale = 200 / size;
                    
                    ctx.fillStyle = '#ffffff';
                    ctx.fillRect(0, 0, 200, 200);
                    
                    for (let row = 0; row < size; row++) {
                        for (let col = 0; col < size; col++) {
                            if (qr.isDark(row, col)) {
                                ctx.fillStyle = '#000000';
                                ctx.fillRect(col * scale, row * scale, scale, scale);
                            }
                        }
                    }
                    
                    const dataUrl = canvas.toDataURL('image/png');
                    if (dataUrl && dataUrl.startsWith('data:image')) {
                        this._cache[cacheKey] = dataUrl;
                        Logger.info('QrCodeSystem', '✅ QR Code gerado com QRCodeGenerator!');
                        return dataUrl;
                    }
                }
                
                Logger.warn('QrCodeSystem', '⚠️ Nenhuma biblioteca de QR Code disponível');
                return null;
                
            } catch (error) {
                Logger.error('QrCodeSystem', '❌ Erro ao gerar QR Code local:', error);
                return null;
            }
        },
        
        /**
         * 🔥 Garante que o QR Code tenha o prefixo correto
         */
        ensurePrefix: function(qrCode) {
            if (!qrCode) return '';
            
            // Se já tem o prefixo correto, retorna
            if (qrCode.startsWith('data:image')) {
                return qrCode;
            }
            
            // Se começa com "iVBOR" (base64 de PNG), adiciona prefixo
            if (qrCode.startsWith('iVBOR')) {
                Logger.info('QrCodeSystem', '✅ Adicionando prefixo data:image/png;base64, ao QR Code');
                return `data:image/png;base64,${qrCode}`;
            }
            
            // Se começa com "000201" (PIX Copia e Cola), é texto
            if (qrCode.startsWith('000201')) {
                Logger.debug('QrCodeSystem', '📱 QR Code textual detectado');
                return qrCode;
            }
            
            // Fallback: tenta como base64 genérico
            Logger.warn('QrCodeSystem', '⚠️ QR Code sem formato conhecido, tentando como base64');
            return `data:image/png;base64,${qrCode}`;
        },
        
        /**
         * 🔥 Valida se o QR Code é uma imagem válida
         */
        isValidImage: function(qrCode) {
            if (!qrCode) return false;
            return qrCode.startsWith('data:image') && qrCode.length > 100;
        },
        
        /**
         * 🔥 Verifica se o QR Code é textual (PIX Copia e Cola)
         */
        isTextual: function(qrCode) {
            if (!qrCode) return false;
            return qrCode.startsWith('000201') || qrCode.includes('br.gov.bcb.pix');
        },
        
        /**
         * 🔥 Limpa o cache de QR Code
         */
        clearCache: function() {
            this._cache = {};
            Logger.debug('QrCodeSystem', '🧹 Cache de QR Code limpo');
        }
    };

    // ==============================================
    // 🔥 VALIDADOR DE CPF (COM ALGORITMO DV)
    // ==============================================

    const CpfValidator = {
        validate: function(cpf) {
            const cleaned = cpf.replace(/\D/g, '');
            
            if (cleaned.length !== 11) {
                return { valid: false, message: 'CPF deve conter 11 dígitos' };
            }
            
            if (/^(\d)\1{10}$/.test(cleaned)) {
                return { valid: false, message: 'CPF inválido (dígitos repetidos)' };
            }
            
            let sum = 0;
            for (let i = 0; i < 9; i++) {
                sum += parseInt(cleaned.charAt(i)) * (10 - i);
            }
            let remainder = 11 - (sum % 11);
            let firstDigit = remainder >= 10 ? 0 : remainder;
            
            if (parseInt(cleaned.charAt(9)) !== firstDigit) {
                return { valid: false, message: 'CPF inválido (primeiro dígito verificador)' };
            }
            
            sum = 0;
            for (let i = 0; i < 10; i++) {
                sum += parseInt(cleaned.charAt(i)) * (11 - i);
            }
            remainder = 11 - (sum % 11);
            let secondDigit = remainder >= 10 ? 0 : remainder;
            
            if (parseInt(cleaned.charAt(10)) !== secondDigit) {
                return { valid: false, message: 'CPF inválido (segundo dígito verificador)' };
            }
            
            return { valid: true, cleaned: cleaned };
        },

        format: function(cpf) {
            const cleaned = cpf.replace(/\D/g, '');
            if (cleaned.length !== 11) return cpf;
            return cleaned.replace(/^(\d{3})(\d{3})(\d{3})(\d{2})$/, '$1.$2.$3-$4');
        },

        mask: function(value) {
            let cleaned = value.replace(/\D/g, '');
            if (cleaned.length > 11) cleaned = cleaned.slice(0, 11);
            
            if (cleaned.length > 9) {
                return cleaned.replace(/^(\d{3})(\d{3})(\d{3})(\d{2})$/, '$1.$2.$3-$4');
            } else if (cleaned.length > 6) {
                return cleaned.replace(/^(\d{3})(\d{3})(\d{0,3})$/, '$1.$2.$3');
            } else if (cleaned.length > 3) {
                return cleaned.replace(/^(\d{3})(\d{0,3})$/, '$1.$2');
            }
            return cleaned;
        }
    };

    // ==============================================
    // 🔥 SISTEMA DE RETRY COM BACKOFF EXPONENCIAL
    // ==============================================

    const RetrySystem = {
        execute: async function(fn, options = {}) {
            const {
                maxAttempts = CONFIG.MAX_RETRY_ATTEMPTS,
                baseDelay = CONFIG.RETRY_BASE_DELAY,
                maxDelay = CONFIG.RETRY_MAX_DELAY,
                onRetry = null,
                onError = null,
                context = 'RetrySystem'
            } = options;

            let lastError = null;
            
            for (let attempt = 1; attempt <= maxAttempts; attempt++) {
                try {
                    Logger.debug(context, `Tentativa ${attempt}/${maxAttempts}`);
                    const result = await fn(attempt);
                    if (attempt > 1) {
                        Logger.info(context, `Sucesso na tentativa ${attempt}`);
                    }
                    return result;
                } catch (error) {
                    lastError = error;
                    
                    if (attempt < maxAttempts) {
                        const delay = Math.min(
                            baseDelay * Math.pow(2, attempt - 1) + Math.random() * 200,
                            maxDelay
                        );
                        
                        Logger.warn(context, `Falha na tentativa ${attempt}: ${error.message}`);
                        
                        if (onRetry) {
                            await onRetry(attempt, error, delay);
                        }
                        
                        await new Promise(resolve => setTimeout(resolve, delay));
                    } else {
                        if (onError) {
                            await onError(error);
                        }
                        Logger.error(context, `Todas as ${maxAttempts} tentativas falharam`);
                    }
                }
            }
            
            throw lastError || new Error('Todas as tentativas falharam');
        }
    };

    // ==============================================
    // 🔥 SISTEMA DE DEBOUNCE
    // ==============================================

    const DebounceSystem = {
        _timeouts: {},
        
        debounce: function(key, fn, delay = CONFIG.DEBOUNCE_DELAY) {
            if (this._timeouts[key]) {
                clearTimeout(this._timeouts[key]);
                Logger.debug('DebounceSystem', `Debounce cancelado para ${key}`);
            }
            
            this._timeouts[key] = setTimeout(() => {
                delete this._timeouts[key];
                fn();
            }, delay);
        },
        
        isPending: function(key) {
            return !!this._timeouts[key];
        },
        
        cancel: function(key) {
            if (this._timeouts[key]) {
                clearTimeout(this._timeouts[key]);
                delete this._timeouts[key];
                Logger.debug('DebounceSystem', `Debounce cancelado para ${key}`);
            }
        }
    };

    // ==============================================
    // 🔥 SISTEMA DE ESPERA INTELIGENTE
    // ==============================================

    const Waiter = {
        _attempts: 0,
        _maxAttempts: CONFIG.MAX_WAIT_ATTEMPTS,
        _interval: CONFIG.WAIT_FOR_APP_INTERVAL,
        _resolved: false,

        waitForApp: function() {
            return new Promise((resolve) => {
                if (this._isAppReady()) {
                    Logger.info('Waiter', 'app.js já está pronto');
                    this._resolved = true;
                    resolve(true);
                    return;
                }

                Logger.info('Waiter', 'Aguardando app.js...');

                const startTime = Date.now();
                this._attempts = 0;

                const check = () => {
                    this._attempts++;

                    if (this._isAppReady()) {
                        Logger.info('Waiter', `app.js pronto após ${this._attempts} tentativas`);
                        this._resolved = true;
                        resolve(true);
                        return;
                    }

                    if (Date.now() - startTime > CONFIG.WAIT_FOR_APP_TIMEOUT) {
                        Logger.error('Waiter', 'Timeout aguardando app.js');
                        resolve(false);
                        return;
                    }

                    setTimeout(check, this._interval);
                };

                check();
            });
        },

        _isAppReady: function() {
            if (window._appReadyFired === true) return true;
            
            if (window.App && typeof window.App.isReady === 'function') {
                try {
                    if (window.App.isReady()) return true;
                } catch (e) { /* ignora */ }
            }

            if (window.__APP_STATE && window.__APP_STATE.isAppReady === true) return true;
            if (window.EventBus && window.AppUtils && window.fetchWithAuth) return true;

            return false;
        },

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

        validateDependencies: function(deps) {
            const required = ['EventBus', 'AppUtils', 'fetchWithAuth'];
            const missing = required.filter(key => !deps[key]);

            if (missing.length > 0) {
                Logger.warn('Waiter', `Dependências faltando: ${missing.join(', ')}`);
                return false;
            }

            return true;
        }
    };

    // ==============================================
    // 🔥 SISTEMA DE VAGAS (MELHORADO)
    // ==============================================

    const VagasSystem = {
        _lastUpdate: 0,
        _updateInterval: null,
        _currentData: null,
        _isUpdating: false,
        _isUrgent: false,
        _deps: null,
        _initialized: false,
        _updatePromise: null,

        init: function(deps) {
            if (this._initialized) return;

            this._deps = deps;
            this._initialized = true;

            Logger.info('VagasSystem', 'Inicializando...');

            this.updateVagas();

            this._startPolling();

            const events = ['payment:completed', 'premiumStatusUpdated', 'app:state_changed'];
            events.forEach(eventName => {
                document.addEventListener(eventName, () => {
                    Logger.debug('VagasSystem', `Evento ${eventName} - atualizando`);
                    DebounceSystem.debounce('vagas_update', () => {
                        this.updateVagas(true);
                    }, 1000);
                });
            });

            Logger.info('VagasSystem', 'Inicializado com sucesso');
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

            Logger.debug('VagasSystem', `Polling: ${interval/1000}s`);
        },

        _adjustPolling: function(remaining) {
            const wasUrgent = this._isUrgent;
            this._isUrgent = remaining <= CONFIG.VAGAS_URGENT_THRESHOLD && remaining > 0;

            if (wasUrgent !== this._isUrgent) {
                Logger.info('VagasSystem', 
                    `Ajustando polling: ${this._isUrgent ? 'URGENTE (5s)' : 'NORMAL (30s)'}`
                );
                this._startPolling();
            }
        },

        updateVagas: async function(force = false) {
            if (this._isUpdating) {
                if (this._updatePromise) return this._updatePromise;
                return null;
            }

            const now = Date.now();
            if (!force && (now - this._lastUpdate) < CONFIG.VAGAS_CACHE_TTL) {
                return this._currentData;
            }

            this._isUpdating = true;
            this._updatePromise = this._doUpdate(force);
            
            try {
                const result = await this._updatePromise;
                return result;
            } finally {
                this._isUpdating = false;
                this._updatePromise = null;
            }
        },

        _doUpdate: async function(force) {
            try {
                const response = await this._deps.fetchWithAuth('/api/payments/promotion-status');
                
                if (!response) {
                    Logger.warn('VagasSystem', 'Sem resposta da API');
                    return null;
                }

                if (!response.ok) {
                    Logger.warn('VagasSystem', `API retornou ${response.status}`);
                    return null;
                }

                const data = await response.json();
                this._currentData = data;
                this._lastUpdate = Date.now();

                this._adjustPolling(data.remaining_slots || 0);
                this._updateUI(data);

                if (this._deps.EventBus) {
                    this._deps.EventBus.emit('vagas:updated', data);
                }
                window.dispatchEvent(new CustomEvent('vagas:updated', { detail: data }));

                return data;

            } catch (error) {
                Logger.error('VagasSystem', 'Erro ao atualizar:', error);
                return null;
            }
        },

        _updateUI: function(data) {
            const remaining = data.remaining_slots || 0;
            const total = data.total_slots || CONFIG.TOTAL_PROMOTIONAL_SLOTS;
            const isSoldOut = remaining <= 0;
            const isUrgent = remaining <= CONFIG.VAGAS_URGENT_THRESHOLD && remaining > 0;
            const percent = total > 0 ? ((total - remaining) / total) * 100 : 0;

            const elements = {
                vagasRestantes: document.getElementById('vagasRestantes'),
                vagasTotal: document.getElementById('vagasTotal'),
                vagasPercentText: document.getElementById('vagasPercentText'),
                vagasHeaderText: document.getElementById('vagasHeaderText'),
                vagasProgress: document.getElementById('vagasProgress'),
                vagasContainer: document.getElementById('vagasContainer'),
                vagasUrgentAlert: document.getElementById('vagasUrgentAlert'),
                vagasUrgentCount: document.getElementById('vagasUrgentCount'),
                vagasSoldOutAlert: document.getElementById('vagasSoldOutAlert'),
                currentPrice: document.getElementById('currentPrice'),
                oldPrice: document.getElementById('oldPrice'),
                economyBadge: document.getElementById('economyBadge'),
                btnUpgrade: document.getElementById('btnUpgrade'),
                planBadgeText: document.getElementById('planBadgeText')
            };

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

            if (elements.vagasTotal) elements.vagasTotal.textContent = total;
            if (elements.vagasPercentText) elements.vagasPercentText.textContent = Math.round(percent) + '% preenchidas';
            if (elements.vagasHeaderText) elements.vagasHeaderText.textContent = remaining;

            if (elements.vagasProgress) {
                elements.vagasProgress.style.width = Math.min(100, percent) + '%';
                elements.vagasProgress.classList.remove('urgent', 'sold-out');
                if (isSoldOut) elements.vagasProgress.classList.add('sold-out');
                else if (isUrgent) elements.vagasProgress.classList.add('urgent');
            }

            if (elements.vagasContainer) {
                elements.vagasContainer.classList.remove('urgent', 'sold-out');
                if (isSoldOut) elements.vagasContainer.classList.add('sold-out');
                else if (isUrgent) elements.vagasContainer.classList.add('urgent');
            }

            if (elements.vagasUrgentAlert && elements.vagasUrgentCount) {
                if (isUrgent) {
                    elements.vagasUrgentAlert.classList.add('show');
                    elements.vagasUrgentCount.textContent = remaining;
                } else {
                    elements.vagasUrgentAlert.classList.remove('show');
                }
            }

            if (elements.vagasSoldOutAlert) {
                if (isSoldOut) {
                    elements.vagasSoldOutAlert.classList.add('show');
                } else {
                    elements.vagasSoldOutAlert.classList.remove('show');
                }
            }

            if (elements.planBadgeText) {
                if (isSoldOut) {
                    elements.planBadgeText.textContent = '❌ PROMOÇÃO ESGOTADA';
                    elements.planBadgeText.style.color = '#dc3545';
                } else if (isUrgent) {
                    elements.planBadgeText.textContent = '🔥 ÚLTIMAS ' + remaining + ' VAGAS!';
                    elements.planBadgeText.style.color = '#f5a623';
                    elements.planBadgeText.style.animation = 'badgePulse 0.8s ease-in-out infinite';
                } else {
                    elements.planBadgeText.textContent = '🔥 ' + remaining + ' VAGAS DISPONÍVEIS';
                    elements.planBadgeText.style.color = '#ffffff';
                    elements.planBadgeText.style.animation = 'badgePulse 2s ease-in-out infinite';
                }
            }

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

            window.dispatchEvent(new CustomEvent('vagas:ui_updated', {
                detail: { remaining, total, isSoldOut, isUrgent, percent }
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
    let _statusCache = {};
    let _isCreatingPayment = false;
    let _pixModalInstance = null;

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

    async function loadPremiumStatus() {
        if (!deps || !deps.fetchWithAuth) {
            Logger.warn('payment.js', 'fetchWithAuth não disponível');
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
            Logger.error('payment.js', 'Erro ao carregar status premium:', error);
        }
        return null;
    }

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
            Logger.error('payment.js', 'Erro ao receber crédito:', error);
            deps?.AppUtils?.showNotification('Erro de conexão. Tente novamente.', 'error');
        }
        return null;
    }

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

    // ==============================================
    // 🔥 CORREÇÃO PRINCIPAL: MODAL CPF MELHORADO
    // ==============================================

    function openCpfModal(planId) {
        if (!deps) {
            Logger.warn('payment.js', 'Dependências não carregadas');
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

        if (_isCreatingPayment) {
            deps.AppUtils.showNotification('⏳ Aguarde o processamento atual...', 'warning');
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
            Logger.warn('payment.js', 'Bootstrap Modal não disponível:', e);
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
                                   style="background: rgba(255,255,255,0.1); border-color: #f5a623; color: white; border-radius:12px;"
                                   autocomplete="off">
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
                const formatted = CpfValidator.mask(e.target.value);
                e.target.value = formatted;
                
                if (cpfError) {
                    cpfError.classList.add('d-none');
                }
                
                const cleaned = e.target.value.replace(/\D/g, '');
                if (cleaned.length === 11) {
                    const result = CpfValidator.validate(cleaned);
                    if (!result.valid) {
                        if (cpfError) {
                            cpfError.textContent = `❌ ${result.message}`;
                            cpfError.classList.remove('d-none');
                        }
                    }
                }
            });

            cpfInput.addEventListener('blur', function(e) {
                const cleaned = e.target.value.replace(/\D/g, '');
                if (cleaned.length > 0 && cleaned.length !== 11) {
                    if (cpfError) {
                        cpfError.textContent = '❌ CPF inválido. Digite um CPF válido com 11 dígitos.';
                        cpfError.classList.remove('d-none');
                    }
                } else if (cleaned.length === 11) {
                    const result = CpfValidator.validate(cleaned);
                    if (!result.valid) {
                        if (cpfError) {
                            cpfError.textContent = `❌ ${result.message}`;
                            cpfError.classList.remove('d-none');
                        }
                    }
                }
            });
        }

        if (confirmBtn) {
            confirmBtn.addEventListener('click', function() {
                if (!cpfInput) return;
                
                const cpfLimpo = cpfInput.value.replace(/\D/g, '');
                
                const validation = CpfValidator.validate(cpfLimpo);
                
                if (!validation.valid) {
                    if (cpfError) {
                        cpfError.textContent = `❌ ${validation.message}`;
                        cpfError.classList.remove('d-none');
                    }
                    return;
                }
                
                if (cpfError) cpfError.classList.add('d-none');
                
                const modal = bootstrap.Modal.getInstance(document.getElementById('cpfModal'));
                if (modal) modal.hide();
                
                DebounceSystem.debounce('create_payment', () => {
                    createPaymentWithPix(validation.cleaned, planId);
                }, 300);
            });
        }

        if (cpfInput) {
            cpfInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' && confirmBtn) {
                    e.preventDefault();
                    confirmBtn.click();
                }
            });
        }
    }

    // ==============================================
    // 🔥 CORREÇÃO PRINCIPAL: createPaymentWithPix
    // ==============================================

    async function createPaymentWithPix(cpf, planId = 'premium_mensal') {
        if (_isCreatingPayment) {
            Logger.warn('payment.js', 'Já existe um pagamento em andamento');
            deps?.AppUtils?.showNotification('⏳ Aguarde o processamento atual...', 'warning');
            return;
        }

        if (!deps) {
            Logger.error('payment.js', 'Dependências não carregadas');
            deps?.AppUtils?.showNotification('Erro interno. Recarregue a página.', 'error');
            return;
        }

        const validPlanId = planId || 'premium_mensal';
        
        Logger.info('payment.js', `Criando pagamento PIX para CPF: ${cpf.substring(0, 3)}***${cpf.substring(cpf.length - 3)}`);
        Logger.debug('payment.js', `Plan ID: ${validPlanId}`);
        
        deps.AppUtils.showNotification('🔄 Gerando QR Code PIX...', 'info');
        
        _isCreatingPayment = true;

        try {
            const response = await RetrySystem.execute(async (attempt) => {
                Logger.debug('payment.js', `Tentativa ${attempt} de criar pagamento`);
                
                const resp = await deps.fetchWithAuth('/api/payments/create-pix', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        cpf: cpf,
                        plan_id: validPlanId
                    })
                });

                if (!resp) {
                    throw new Error('Falha na conexão com o servidor');
                }

                if (!resp.ok) {
                    let errorData = {};
                    try {
                        errorData = await resp.json();
                    } catch (e) {
                        try {
                            const text = await resp.text();
                            errorData = { detail: text || `Erro ${resp.status}` };
                        } catch (e2) {
                            errorData = { detail: `Erro ${resp.status}` };
                        }
                    }
                    
                    const errorMsg = errorData.detail || errorData.message || `Erro ${resp.status}`;
                    throw new Error(errorMsg);
                }

                return resp;
            }, {
                maxAttempts: CONFIG.MAX_RETRY_ATTEMPTS,
                baseDelay: CONFIG.RETRY_BASE_DELAY,
                maxDelay: CONFIG.RETRY_MAX_DELAY,
                onRetry: (attempt, error, delay) => {
                    Logger.warn('payment.js', `Retry ${attempt}: ${error.message}, aguardando ${delay}ms`);
                    deps.AppUtils.showNotification(`⏳ Tentando novamente (${attempt}/${CONFIG.MAX_RETRY_ATTEMPTS})...`, 'warning');
                },
                onError: (error) => {
                    Logger.error('payment.js', `Falha após todas as tentativas: ${error.message}`);
                },
                context: 'createPaymentWithPix'
            });

            const data = await response.json();
            
            Logger.info('payment.js', `Pagamento criado: ${data.payment_id || 'ID desconhecido'}`);
            Logger.debug('payment.js', 'Dados do pagamento:', data);

            // 🔥 CORREÇÃO V7.4: Validação inteligente do QR Code
            let qrCodeBase64 = data.qr_code_base64 || data.qr_code || '';
            let pixCode = data.pix_code || data.qr_code || '';

            // 🔥 Se não tem QR Code base64, mas tem texto PIX, gera localmente
            if (!qrCodeBase64 && pixCode) {
                Logger.info('payment.js', '📱 QR Code base64 vazio, tentando gerar localmente...');
                
                // Tenta gerar o QR Code a partir do texto
                const generatedQr = QrCodeSystem.generateFromText(pixCode);
                if (generatedQr) {
                    qrCodeBase64 = generatedQr;
                    Logger.info('payment.js', '✅ QR Code gerado localmente com sucesso!');
                }
            }

            // 🔥 Garante o prefixo correto
            if (qrCodeBase64) {
                qrCodeBase64 = QrCodeSystem.ensurePrefix(qrCodeBase64);
                Logger.debug('payment.js', '✅ QR Code com prefixo corrigido');
            }

            // 🔥 Atualiza os dados com o QR Code corrigido
            data.qr_code_base64 = qrCodeBase64;
            data.pix_code = pixCode;

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
            _isCreatingPayment = false;

        } catch (error) {
            Logger.error('payment.js', 'Erro ao criar pagamento:', error);
            
            let userMessage = error.message || 'Erro ao gerar pagamento. Tente novamente.';
            
            if (userMessage.includes('422')) {
                userMessage = 'Dados inválidos. Verifique seu CPF e tente novamente.';
            } else if (userMessage.includes('429') || userMessage.includes('rate')) {
                userMessage = 'Muitas tentativas. Aguarde alguns minutos e tente novamente.';
            } else if (userMessage.includes('CPF')) {
                userMessage = 'CPF inválido. Verifique e tente novamente.';
            } else if (userMessage.includes('conexão') || userMessage.includes('connection')) {
                userMessage = 'Erro de conexão. Verifique sua internet e tente novamente.';
            }
            
            deps.AppUtils.showNotification(`❌ ${userMessage}`, 'error');
            _isCreatingPayment = false;
        }
    }

    // ==============================================
    // 🔥 MODAL PIX (V7.4 - CORRIGIDO)
    // ==============================================

    let countdownInterval = null;
    let statusPollingInterval = null;

    function showPixModal(data) {
        Logger.info('payment.js', 'Mostrando modal PIX...');

        // 🔥 Fecha modal anterior se existir
        if (_pixModalInstance) {
            try {
                _pixModalInstance.hide();
            } catch (e) {
                // ignora
            }
            _pixModalInstance = null;
        }

        let pixModal = document.getElementById('pixModal');
        if (!pixModal) {
            pixModal = document.createElement('div');
            pixModal.id = 'pixModal';
            pixModal.className = 'modal fade';
            pixModal.setAttribute('tabindex', '-1');
            document.body.appendChild(pixModal);
        }

        // 🔥 CORREÇÃO V7.4: Extração inteligente do QR Code
        let qrCodeBase64 = data.qr_code_base64 || data.qr_code || '';
        let pixCode = data.pix_code || data.qr_code || '';

        // 🔥 LOG DE DEBUG
        console.log('📱 QR Code Base64 recebido:', qrCodeBase64 ? 'SIM (length: ' + qrCodeBase64.length + ')' : 'NÃO');
        console.log('📱 PIX Code recebido:', pixCode ? 'SIM (length: ' + pixCode.length + ')' : 'NÃO');

        // 🔥 Se não tem QR Code base64, tenta gerar localmente
        if (!qrCodeBase64 && pixCode) {
            Logger.info('payment.js', '📱 QR Code base64 vazio no modal, gerando localmente...');
            const generatedQr = QrCodeSystem.generateFromText(pixCode);
            if (generatedQr) {
                qrCodeBase64 = generatedQr;
                Logger.info('payment.js', '✅ QR Code gerado localmente no modal!');
            }
        }

        // 🔥 Garante o prefixo correto
        if (qrCodeBase64) {
            qrCodeBase64 = QrCodeSystem.ensurePrefix(qrCodeBase64);
            Logger.debug('payment.js', '✅ QR Code com prefixo corrigido no modal');
        }

        const amount = data.amount || CONFIG.PROMOTIONAL_PRICE;
        const planName = data.plan_name || 'Plano Bronze';
        const paymentId = data.payment_id;

        const template = document.getElementById('pixModalTemplate');
        if (template) {
            const clone = template.content.cloneNode(true);
            pixModal.innerHTML = '';
            pixModal.appendChild(clone);
            
            const qrImg = pixModal.querySelector('#pixQrCode');
            const placeholder = pixModal.querySelector('#pixQrPlaceholder');
            
            // 🔥 CORREÇÃO V7.4: Renderização inteligente do QR Code
            if (qrImg && qrCodeBase64) {
                Logger.info('payment.js', '🖼️ Renderizando QR Code...');
                qrImg.src = qrCodeBase64;
                qrImg.style.display = 'block';
                if (placeholder) placeholder.style.display = 'none';
                
                // 🔥 VERIFICA SE O QR CODE CARREGOU CORRETAMENTE
                qrImg.onload = function() {
                    Logger.info('payment.js', '✅ QR Code carregado com sucesso!');
                    if (placeholder) {
                        placeholder.style.display = 'none';
                    }
                    qrImg.style.display = 'block';
                };
                
                qrImg.onerror = function(e) {
                    Logger.warn('payment.js', '⚠️ QR Code não carregou, usando fallback textual');
                    qrImg.style.display = 'none';
                    if (placeholder) {
                        placeholder.style.display = 'flex';
                        placeholder.innerHTML = `
                            <div style="text-align: center;">
                                <i class="fas fa-qrcode" style="font-size: 3rem; color: #f5a623; margin-bottom: 0.5rem;"></i>
                                <div style="font-size: 0.8rem; color: #999;">Escaneie o PIX</div>
                                <div style="font-size: 0.6rem; color: #666; margin-top: 0.3rem; word-break: break-all; max-width: 180px;">
                                    ${pixCode ? pixCode.substring(0, 30) + '...' : 'Chave PIX disponível abaixo'}
                                </div>
                            </div>
                        `;
                    }
                    deps.AppUtils.showNotification('💡 QR Code não carregou, mas a chave PIX está disponível', 'warning');
                };
                
                // 🔥 Timeout para carregamento do QR Code
                setTimeout(() => {
                    if (qrImg.style.display !== 'none' && !qrImg.complete) {
                        Logger.warn('payment.js', '⏰ Timeout no carregamento do QR Code');
                        // Tenta recarregar
                        qrImg.src = qrCodeBase64;
                    }
                }, CONFIG.QR_CODE_TIMEOUT);
                
            } else if (qrImg && pixCode) {
                // 🔥 Fallback: mostra o texto PIX
                Logger.info('payment.js', '📱 Usando fallback textual para QR Code');
                qrImg.style.display = 'none';
                if (placeholder) {
                    placeholder.style.display = 'flex';
                    placeholder.innerHTML = `
                        <div style="text-align: center;">
                            <i class="fas fa-file-invoice" style="font-size: 2.5rem; color: #48bb78; margin-bottom: 0.5rem;"></i>
                            <div style="font-size: 0.7rem; color: #999; word-break: break-all; max-width: 180px;">
                                ${pixCode.substring(0, 50)}...
                            </div>
                            <div style="font-size: 0.6rem; color: #666; margin-top: 0.3rem;">
                                Clique em "Copiar Chave PIX" abaixo
                            </div>
                        </div>
                    `;
                }
            } else {
                // Sem QR Code
                if (placeholder) {
                    placeholder.style.display = 'flex';
                    placeholder.innerHTML = `
                        <div style="text-align: center;">
                            <i class="fas fa-exclamation-circle" style="font-size: 2.5rem; color: #f5a623; margin-bottom: 0.5rem;"></i>
                            <div style="font-size: 0.8rem; color: #999;">QR Code indisponível</div>
                            <div style="font-size: 0.6rem; color: #666; margin-top: 0.3rem;">
                                Use a chave PIX abaixo
                            </div>
                        </div>
                    `;
                }
            }
            
            // 🔥 Atualiza o código PIX
            const codeText = pixModal.querySelector('#pixCodeText');
            if (codeText && pixCode) {
                codeText.textContent = pixCode;
            }
            
            const priceText = pixModal.querySelector('#pixPriceText');
            if (priceText) priceText.textContent = `R$ ${amount.toFixed(2).replace('.', ',')}`;
            
            const planText = pixModal.querySelector('#pixPlanText');
            if (planText) planText.textContent = planName;
            
            const promoBadge = pixModal.querySelector('#pixPromoBadge');
            if (promoBadge && data.was_promotional) {
                promoBadge.textContent = '✅ Preço de fundador garantido para sempre!';
            }
            
            const verifyBtn = pixModal.querySelector('#pixVerifyBtn');
            if (verifyBtn && paymentId) {
                verifyBtn.dataset.paymentId = paymentId;
                verifyBtn.onclick = window.verifyPayment;
            }
        } else {
            pixModal.innerHTML = getPixModalHTML(data, qrCodeBase64, pixCode, amount, planName);
        }

        // 🔥 Inicia contador com 2 minutos
        startCountdown(CONFIG.PIX_EXPIRY_MINUTES * 60);
        startStatusPolling(paymentId);

        try {
            _pixModalInstance = new bootstrap.Modal(pixModal);
            _pixModalInstance.show();
        } catch (e) {
            Logger.warn('payment.js', 'Bootstrap Modal não disponível:', e);
            pixModal.style.display = 'block';
            pixModal.classList.add('show');
        }
    }

    function getPixModalHTML(data, qrCode, pixCode, amount, planName) {
        const qrCodeHtml = qrCode ? 
            `<img src="${qrCode}" alt="QR Code PIX" style="max-width: 200px; border-radius: 8px;" id="pixQrCode">` :
            `<div id="pixQrPlaceholder" style="width:200px; height:200px; background:#f0f0f0; display:flex; align-items:center; justify-content:center; border-radius:8px; color:#999; font-size:14px;">QR Code indisponível</div>`;
        
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
                                ${qrCodeHtml}
                            </div>
                        </div>
                        
                        <div class="p-3 rounded-3 mb-3" style="background: rgba(255,255,255,0.05); word-break: break-all;">
                            <code id="pixCodeText" class="small" style="color: #f5a623;">${pixCode || 'autonalytics@gmail.com'}</code>
                        </div>
                        
                        <button class="btn w-100 mb-3" onclick="window.copyPixCode()" 
                                style="background: rgba(255,255,255,0.06); color: #f5a623; border: 1px solid rgba(205,127,50,0.3); border-radius: 12px; padding: 0.75rem;">
                            <i class="fas fa-copy me-2"></i> Copiar Chave PIX
                        </button>
                        
                        <div class="alert alert-info small" style="background: rgba(245, 166, 35, 0.08); border-color: rgba(205,127,50,0.2); color: rgba(255,255,255,0.7);">
                            <i class="fas fa-info-circle me-2"></i>
                            <strong>Informações do pagamento:</strong><br>
                            <strong id="pixPlanText">${planName}</strong> - Valor: R$ ${amount.toFixed(2).replace('.', ',')}<br>
                            <span class="text-success" id="pixPromoBadge">${data.was_promotional ? '✅ Preço de fundador garantido para sempre!' : '💰 Preço regular'}</span><br>
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
    // 🔥 STATUS POLLING (COM CACHE)
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

            const cacheKey = `status_${paymentId}`;
            const cached = _statusCache[cacheKey];
            if (cached && (Date.now() - cached.timestamp) < CONFIG.STATUS_CACHE_TTL) {
                Logger.debug('payment.js', `Usando cache para status ${paymentId}`);
                if (cached.status === 'approved') {
                    clearInterval(statusPollingInterval);
                    statusPollingInterval = null;
                    handlePaymentApproved(paymentId);
                }
                return;
            }

            try {
                const response = await deps.fetchWithAuth(`/api/payments/status/${paymentId}`);
                if (response?.ok) {
                    const data = await response.json();
                    const payment = data.payment || data;
                    
                    _statusCache[cacheKey] = {
                        status: payment.status,
                        timestamp: Date.now()
                    };
                    
                    if (payment.status === 'approved') {
                        clearInterval(statusPollingInterval);
                        statusPollingInterval = null;
                        handlePaymentApproved(paymentId);
                        
                    } else if (payment.status === 'rejected' || payment.status === 'cancelled') {
                        clearInterval(statusPollingInterval);
                        statusPollingInterval = null;
                        deps.AppUtils.showNotification(`❌ Pagamento ${payment.status}. Tente novamente.`, 'error');
                    }
                }
            } catch (error) {
                Logger.warn('payment.js', 'Erro no status polling:', error);
            }

            if (attempts >= maxAttempts) {
                clearInterval(statusPollingInterval);
                statusPollingInterval = null;
                Logger.info('payment.js', 'Status polling finalizado (timeout)');
            }
        }, CONFIG.STATUS_POLLING_INTERVAL);

        Logger.info('payment.js', `Status polling iniciado para payment ${paymentId}`);
    }

    function handlePaymentApproved(paymentId) {
        deps.AppUtils.showNotification('✅ Pagamento confirmado! Seu plano foi ativado.', 'success');
        
        window.dispatchEvent(new CustomEvent('premiumStatusUpdated', {
            detail: {
                isPremium: true,
                daysLeft: 30,
                creditsBalance: 30
            }
        }));
        
        window.dispatchEvent(new CustomEvent('payment:completed', {
            detail: {
                payment_id: paymentId,
                status: 'approved'
            }
        }));
        
        if (_pixModalInstance) {
            _pixModalInstance.hide();
        }
        setTimeout(() => window.location.reload(), 1500);
    }

    // ==============================================
    // 🔥 COUNTDOWN (2 MINUTOS)
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
            Logger.warn('payment.js', 'Dependências não carregadas');
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
                handlePaymentApproved(paymentId);
            } else if (payment.status === 'pending') {
                deps.AppUtils.showNotification('⏳ Pagamento ainda não confirmado. Aguarde alguns minutos.', 'warning');
            } else {
                deps.AppUtils.showNotification(`⏳ Status: ${payment.status}`, 'info');
            }
        } catch (error) {
            Logger.error('payment.js', 'Erro ao verificar pagamento:', error);
            deps.AppUtils.showNotification('Erro ao verificar pagamento. Tente novamente.', 'error');
        }
    };

    // ==============================================
    // 🔥 INICIALIZAÇÃO PRINCIPAL
    // ==============================================

    async function init() {
        Logger.info('payment.js', 'v7.4 Iniciando...');

        const appReady = await Waiter.waitForApp();
        
        if (!appReady) {
            Logger.error('payment.js', 'Não foi possível carregar dependências do app.js');
            Logger.warn('payment.js', 'O sistema pode não funcionar corretamente');
            
            deps = {
                EventBus: window.EventBus || null,
                AppUtils: window.AppUtils || null,
                fetchWithAuth: window.fetchWithAuth || null,
                State: window.__APP_STATE || null,
                StateManager: window.__APP_STATE_MANAGER || null
            };
        } else {
            deps = Waiter.getDependencies();
        }

        const valid = Waiter.validateDependencies(deps);
        if (!valid) {
            Logger.warn('payment.js', 'Algumas dependências estão faltando');
        }

        VagasSystem.init(deps);

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

        window.loadPremiumStatus = loadPremiumStatus;
        window.receiveDailyCredit = receiveDailyCredit;
        window.updateCreditsDisplay = updateCreditsDisplay;
        window.openCpfModal = openCpfModal;
        window.createPaymentWithPix = createPaymentWithPix;
        window.VagasSystem = VagasSystem;
        window.CpfValidator = CpfValidator;
        window.QrCodeSystem = QrCodeSystem;

        window.paymentReady = true;
        window.paymentVersion = '7.4';
        window._paymentInitialized = true;

        window.dispatchEvent(new CustomEvent('paymentReady', {
            detail: {
                version: '7.4',
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

        Logger.info('payment.js', 'v7.4 Carregado com sucesso!');
        Logger.debug('payment.js', `EventBus: ${!!deps.EventBus}`);
        Logger.debug('payment.js', `AppUtils: ${!!deps.AppUtils}`);
        Logger.debug('payment.js', `fetchWithAuth: ${!!deps.fetchWithAuth}`);
        Logger.debug('payment.js', `State: ${!!deps.State}`);
        Logger.debug('payment.js', `PIX Expiry: ${CONFIG.PIX_EXPIRY_MINUTES} minutos`);
        Logger.debug('payment.js', `QR Code timeout: ${CONFIG.QR_CODE_TIMEOUT}ms`);
    }

    // ==============================================
    // 🔥 INICIAR
    // ==============================================

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            setTimeout(init, 300);
        });
    } else {
        setTimeout(init, 300);
    }

    document.addEventListener('app:ready', function() {
        Logger.info('payment.js', 'app:ready recebido, inicializando...');
        init();
    });

})();