// payment.js - VERSÃO 8.0 (DEFINITIVA - FRONT BLINDADO)
// ==============================================
// 🔥 SINCRONIZADO COM:
//    - payment_service.py V4.0 (QrCodeNormalizer + pix_code)
//    - payment_routes.py V4.0 (JSONResponse sem sanitize no QR Code)
//
// 🔥 CORREÇÕES V8.0:
//  1. ✅ SEPARAÇÃO ESTRITA: qr_code_base64 (imagem) ≠ pix_code (copia-e-cola)
//  2. ✅ NUNCA trata copia-e-cola como imagem (elimina 404)
//  3. ✅ PixPayloadNormalizer: extrai campos de qualquer estrutura (compatível MP aninhado)
//  4. ✅ Trava final: só renderiza <img> se for data:image válido
//  5. ✅ Fallback textual robusto quando não há imagem
//  6. ✅ Timeout do QR NÃO entra em loop (só recarrega UMA vez)
//  7. ✅ generateFromText só gera se for copia-e-cola válido
//  8. ✅ showPixModal consome campos já normalizados (sem duplicação)
//  9. ✅ payment:completed só dispara APÓS confirmação de aprovação
// 10. ✅ handlePaymentApproved NÃO faz reload agressivo (atualiza UI)
// 11. ✅ Compatível com payload antigo (qr_code com prefixo, pix_code, etc)
// 12. ✅ Logs coloridos para debug rápido
// ==============================================

(function() {
    'use strict';

    console.log('%c🚀 [payment.js v8.0] Carregando...', 'color:#0ff;font-weight:bold');

    // ==============================================
    // 🔥 CONFIGURAÇÕES
    // ==============================================

    const CONFIG = {
        MAX_CREDITS_BALANCE: 3,
        INITIAL_FREE_CREDITS: 3,
        PIX_EXPIRY_MINUTES: 2,
        PROMOTIONAL_PRICE: 97.00,
        REGULAR_PRICE: 149.90,
        TOTAL_PROMOTIONAL_SLOTS: 100,
        DAYS_PREMIUM: 30,

        VAGAS_UPDATE_INTERVAL_NORMAL: 30000,
        VAGAS_UPDATE_INTERVAL_URGENT: 5000,
        VAGAS_URGENT_THRESHOLD: 20,
        VAGAS_CACHE_TTL: 35000,

        STATUS_POLLING_INTERVAL: 5000,
        STATUS_MAX_ATTEMPTS: 60,
        STATUS_PIX_INTERVAL: 3000,

        WAIT_FOR_APP_TIMEOUT: 10000,
        WAIT_FOR_APP_INTERVAL: 200,
        MAX_WAIT_ATTEMPTS: 50,

        MAX_RETRY_ATTEMPTS: 2,
        RETRY_BASE_DELAY: 2000,
        RETRY_MAX_DELAY: 5000,
        REQUEST_TIMEOUT: 30000,
        DEBOUNCE_DELAY: 800,
        STATUS_CACHE_TTL: 3000,
        QR_CODE_TIMEOUT: 5000,
        QR_CODE_CACHE_TTL: 60000
    };

    // ==============================================
    // 🔥 LOGGER
    // ==============================================

    const Logger = {
        _levels: { DEBUG: 0, INFO: 1, WARN: 2, ERROR: 3 },
        _level: 0,
        setLevel: function(level) {
            if (this._levels[level] !== undefined) this._level = this._levels[level];
        },
        _log: function(level, module, message, data) {
            if (this._levels[level] < this._level) return;
            const timestamp = new Date().toISOString();
            const prefix = `[${timestamp}] [${level}] [${module}]`;
            if (data) console.log(`${prefix} ${message}`, data);
            else console.log(`${prefix} ${message}`);
        },
        debug: function(m, msg, d) { this._log('DEBUG', m, msg, d); },
        info:  function(m, msg, d) { this._log('INFO',  m, msg, d); },
        warn:  function(m, msg, d) { this._log('WARN',  m, msg, d); },
        error: function(m, msg, d) { this._log('ERROR', m, msg, d); }
    };

    // ==============================================
    // 🔥 V8.0: NORMALIZADOR DE PAYLOAD (blindagem total)
    // ==============================================
    // Recebe QUALQUER estrutura que o backend possa mandar e devolve
    // { qrCodeBase64, pixCode } com separação estrita.
    // --------------------------------------------------------------

    const PixPayloadNormalizer = {
        /**
         * Detecta se a string é uma imagem Base64 plausível.
         */
        isBase64Image: function(str) {
            if (!str || typeof str !== 'string') return false;
            if (str.startsWith('data:image/')) return true;
            if (str.startsWith('iVBOR')) return true;   // PNG
            if (str.startsWith('/9j/')) return true;    // JPEG
            if (str.startsWith('R0lGOD')) return true;  // GIF
            return false;
        },

        /**
         * Detecta código PIX copia-e-cola (EMV).
         */
        isPixCopyPaste: function(str) {
            if (!str || typeof str !== 'string') return false;
            return str.startsWith('000201') ||
                   str.includes('br.gov.bcb.pix') ||
                   str.includes('BR.GOV.BCB.PIX');
        },

        /**
         * 🔥 Extrai qr_code_base64 e pix_code de qualquer estrutura.
         * Trata também estruturas aninhadas do Mercado Pago.
         */
        extract: function(data) {
            if (!data || typeof data !== 'object') {
                return { qrCodeBase64: '', pixCode: '' };
            }

            // Estruturas aninhadas do MP (compatibilidade retroativa)
            const poi = data.point_of_interaction
                     || data.pointOfInteraction
                     || (data.payment && data.payment.point_of_interaction);
            const txData = poi && (poi.transaction_data || poi.transactionData);

            // Candidatos a imagem
            const base64Candidates = [
                data.qr_code_base64,
                data.qrcode_base64,
                data.qrCodeBase64,
                txData && txData.qr_code_base64,
                txData && txData.qrcode_base64,
                data.payment && data.payment.qr_code_base64,
            ].filter(Boolean);

            // Candidatos a copia-e-cola
            const textCandidates = [
                data.pix_code,
                data.pixCode,
                data.qr_code,
                data.qrcode,
                txData && txData.qr_code,
                txData && txData.qrcode,
                data.payment && data.payment.pix_code,
                data.payment && data.payment.qr_code,
            ].filter(Boolean);

            // 1. Escolhe a melhor imagem (só aceita Base64 válido)
            let qrCodeBase64 = '';
            for (const cand of base64Candidates) {
                if (this.isBase64Image(cand)) {
                    qrCodeBase64 = cand;
                    break;
                }
                // Fallback: string longa com só chars base64 e sem ser copia-e-cola
                if (typeof cand === 'string' &&
                    cand.length > 200 &&
                    !this.isPixCopyPaste(cand) &&
                    /^[A-Za-z0-9+/=]+$/.test(cand.substring(0, 100))) {
                    qrCodeBase64 = cand;
                    break;
                }
            }

            // 2. Escolhe o melhor copia-e-cola
            let pixCode = '';
            for (const cand of textCandidates) {
                if (this.isPixCopyPaste(cand)) {
                    pixCode = cand;
                    break;
                }
            }

            // 3. Trava: se a "imagem" for copia-e-cola, move para pixCode
            if (qrCodeBase64 && this.isPixCopyPaste(qrCodeBase64)) {
                Logger.warn('PixPayloadNormalizer',
                    '⛔ Copia-e-cola detectado em qr_code_base64 — movendo');
                if (!pixCode) pixCode = qrCodeBase64;
                qrCodeBase64 = '';
            }

            return { qrCodeBase64, pixCode };
        },

        /**
         * 🔥 Normaliza e retorna o payload pronto para o modal.
         * Aplica prefixo correto apenas em Base64 válido.
         */
        normalize: function(data) {
            const { qrCodeBase64: rawBase64, pixCode } = this.extract(data);

            let qrCodeBase64 = '';
            if (rawBase64) {
                if (rawBase64.startsWith('data:image/')) {
                    qrCodeBase64 = rawBase64;
                } else if (this.isBase64Image(rawBase64)) {
                    qrCodeBase64 = `data:image/png;base64,${rawBase64}`;
                }
            }

            return {
                qrCodeBase64,     // "" ou "data:image/png;base64,..."
                pixCode,          // "" ou "000201..."
                hasImage: !!qrCodeBase64,
                hasPixCode: !!pixCode
            };
        }
    };

    // ==============================================
    // 🔥 SISTEMA DE QR CODE LOCAL (blindado)
    // ==============================================

    const QrCodeSystem = {
        _cache: {},

        /**
         * 🔥 V8.0: Só gera se realmente for copia-e-cola.
         * Nunca gera lixo a partir de string aleatória.
         */
        generateFromText: function(pixCode) {
            if (!pixCode || !PixPayloadNormalizer.isPixCopyPaste(pixCode)) {
                Logger.warn('QrCodeSystem',
                    '⛔ generateFromText: texto não é copia-e-cola válido');
                return null;
            }

            try {
                const cacheKey = pixCode.substring(0, 50);
                if (this._cache[cacheKey]) {
                    Logger.debug('QrCodeSystem', '📦 Cache hit');
                    return this._cache[cacheKey];
                }

                // Estratégia 1: QRCode.js (davidshimjs)
                if (typeof QRCode !== 'undefined') {
                    const container = document.createElement('div');
                    new QRCode(container, {
                        text: pixCode,
                        width: 200,
                        height: 200,
                        colorDark: '#000000',
                        colorLight: '#ffffff',
                        correctLevel: QRCode.CorrectLevel.H
                    });

                    const canvas = container.querySelector('canvas');
                    const img = container.querySelector('img');

                    let dataUrl = null;
                    if (canvas) dataUrl = canvas.toDataURL('image/png');
                    else if (img && img.src) dataUrl = img.src;

                    if (dataUrl && dataUrl.startsWith('data:image')) {
                        this._cache[cacheKey] = dataUrl;
                        Logger.info('QrCodeSystem', '✅ QR gerado (QRCode lib)');
                        return dataUrl;
                    }
                }

                // Estratégia 2: qrcode-generator
                if (typeof QRCodeGenerator !== 'undefined') {
                    const qr = QRCodeGenerator(0, 'M');
                    qr.addData(pixCode);
                    qr.make();

                    const size = qr.getModuleCount();
                    const scale = Math.max(1, Math.floor(200 / size));
                    const dim = size * scale;

                    const canvas = document.createElement('canvas');
                    canvas.width = dim;
                    canvas.height = dim;
                    const ctx = canvas.getContext('2d');

                    ctx.fillStyle = '#ffffff';
                    ctx.fillRect(0, 0, dim, dim);

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
                        Logger.info('QrCodeSystem', '✅ QR gerado (QRCodeGenerator)');
                        return dataUrl;
                    }
                }

                Logger.warn('QrCodeSystem', '⚠️ Nenhuma lib de QR Code disponível');
                return null;
            } catch (error) {
                Logger.error('QrCodeSystem', '❌ Erro ao gerar QR:', error);
                return null;
            }
        },

        clearCache: function() {
            this._cache = {};
        }
    };

    // ==============================================
    // 🔥 VALIDADOR DE CPF
    // ==============================================

    const CpfValidator = {
        validate: function(cpf) {
            const cleaned = cpf.replace(/\D/g, '');
            if (cleaned.length !== 11) return { valid: false, message: 'CPF deve conter 11 dígitos' };
            if (/^(\d)\1{10}$/.test(cleaned)) return { valid: false, message: 'CPF inválido (dígitos repetidos)' };

            let sum = 0;
            for (let i = 0; i < 9; i++) sum += parseInt(cleaned.charAt(i)) * (10 - i);
            let remainder = 11 - (sum % 11);
            let firstDigit = remainder >= 10 ? 0 : remainder;
            if (parseInt(cleaned.charAt(9)) !== firstDigit)
                return { valid: false, message: 'CPF inválido (primeiro dígito)' };

            sum = 0;
            for (let i = 0; i < 10; i++) sum += parseInt(cleaned.charAt(i)) * (11 - i);
            remainder = 11 - (sum % 11);
            let secondDigit = remainder >= 10 ? 0 : remainder;
            if (parseInt(cleaned.charAt(10)) !== secondDigit)
                return { valid: false, message: 'CPF inválido (segundo dígito)' };

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
            if (cleaned.length > 9) return cleaned.replace(/^(\d{3})(\d{3})(\d{3})(\d{2})$/, '$1.$2.$3-$4');
            else if (cleaned.length > 6) return cleaned.replace(/^(\d{3})(\d{3})(\d{0,3})$/, '$1.$2.$3');
            else if (cleaned.length > 3) return cleaned.replace(/^(\d{3})(\d{0,3})$/, '$1.$2');
            return cleaned;
        }
    };

    // ==============================================
    // 🔥 RETRY SYSTEM
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
                    if (attempt > 1) Logger.info(context, `Sucesso na tentativa ${attempt}`);
                    return result;
                } catch (error) {
                    lastError = error;

                    if (error.message && (error.message.includes('429') || error.message.includes('rate'))) {
                        Logger.warn(context, `Rate limit — não retentando`);
                        throw error;
                    }

                    if (attempt < maxAttempts) {
                        const delay = Math.min(
                            baseDelay * Math.pow(2, attempt - 1) + Math.random() * 200,
                            maxDelay
                        );
                        Logger.warn(context, `Falha ${attempt}: ${error.message}`);
                        if (onRetry) await onRetry(attempt, error, delay);
                        await new Promise(r => setTimeout(r, delay));
                    } else {
                        if (onError) await onError(error);
                        Logger.error(context, `Todas as ${maxAttempts} tentativas falharam`);
                    }
                }
            }
            throw lastError || new Error('Todas as tentativas falharam');
        }
    };

    // ==============================================
    // 🔥 DEBOUNCE
    // ==============================================

    const DebounceSystem = {
        _timeouts: {},
        debounce: function(key, fn, delay = CONFIG.DEBOUNCE_DELAY) {
            if (this._timeouts[key]) clearTimeout(this._timeouts[key]);
            this._timeouts[key] = setTimeout(() => {
                delete this._timeouts[key];
                fn();
            }, delay);
        },
        isPending: function(key) { return !!this._timeouts[key]; },
        cancel: function(key) {
            if (this._timeouts[key]) {
                clearTimeout(this._timeouts[key]);
                delete this._timeouts[key];
            }
        }
    };

    // ==============================================
    // 🔥 WAITER
    // ==============================================

    const Waiter = {
        _interval: CONFIG.WAIT_FOR_APP_INTERVAL,
        waitForApp: function() {
            return new Promise((resolve) => {
                if (this._isAppReady()) { resolve(true); return; }
                const startTime = Date.now();
                const check = () => {
                    if (this._isAppReady()) { resolve(true); return; }
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
                try { if (window.App.isReady()) return true; } catch (e) {}
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
                StateManager: window.__APP_STATE_MANAGER || null
            };
        },
        validateDependencies: function(deps) {
            const required = ['EventBus', 'AppUtils', 'fetchWithAuth'];
            const missing = required.filter(key => !deps[key]);
            if (missing.length > 0) {
                Logger.warn('Waiter', `Deps faltando: ${missing.join(', ')}`);
                return false;
            }
            return true;
        }
    };

    // ==============================================
    // 🔥 RESET UPGRADE BUTTON
    // ==============================================

    window.resetUpgradeButton = function() {
        const btn = document.getElementById('btnUpgrade');
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `
                <i class="fas fa-bolt me-2"></i>
                🔥 GARANTIR PREÇO FUNDADOR R$ 97,00
                <small class="d-block fs-10">Pagamento seguro via PIX</small>
            `;
            btn.classList.remove('loading');
        }
        window._upgradeInProgress = false;
        window._cpfModalOpen = false;
        _isCreatingPayment = false;
    };

    // ==============================================
    // 🔥 SISTEMA DE VAGAS
    // ==============================================

    const VagasSystem = {
        _lastUpdate: 0, _updateInterval: null, _currentData: null,
        _isUpdating: false, _isUrgent: false, _deps: null,
        _initialized: false, _updatePromise: null,

        init: function(deps) {
            if (this._initialized) return;
            this._deps = deps;
            this._initialized = true;
            Logger.info('VagasSystem', 'Inicializando...');
            this.updateVagas();
            this._startPolling();
            ['payment:completed', 'premiumStatusUpdated', 'app:state_changed'].forEach(eventName => {
                document.addEventListener(eventName, () => {
                    DebounceSystem.debounce('vagas_update', () => this.updateVagas(true), 1000);
                });
            });
        },
        _startPolling: function() {
            if (this._updateInterval) clearInterval(this._updateInterval);
            const interval = this._isUrgent ?
                CONFIG.VAGAS_UPDATE_INTERVAL_URGENT : CONFIG.VAGAS_UPDATE_INTERVAL_NORMAL;
            this._updateInterval = setInterval(() => this.updateVagas(), interval);
        },
        _adjustPolling: function(remaining) {
            const wasUrgent = this._isUrgent;
            this._isUrgent = remaining <= CONFIG.VAGAS_URGENT_THRESHOLD && remaining > 0;
            if (wasUrgent !== this._isUrgent) this._startPolling();
        },
        updateVagas: async function(force = false) {
            if (this._isUpdating) return this._updatePromise || null;
            const now = Date.now();
            if (!force && (now - this._lastUpdate) < CONFIG.VAGAS_CACHE_TTL) return this._currentData;
            this._isUpdating = true;
            this._updatePromise = this._doUpdate(force);
            try { return await this._updatePromise; }
            finally { this._isUpdating = false; this._updatePromise = null; }
        },
        _doUpdate: async function() {
            try {
                const response = await this._deps.fetchWithAuth('/api/payments/promotion-status');
                if (!response || !response.ok) return null;
                const data = await response.json();
                this._currentData = data;
                this._lastUpdate = Date.now();
                this._adjustPolling(data.remaining_slots || 0);
                this._updateUI(data);
                if (this._deps.EventBus) this._deps.EventBus.emit('vagas:updated', data);
                window.dispatchEvent(new CustomEvent('vagas:updated', { detail: data }));
                return data;
            } catch (error) {
                Logger.error('VagasSystem', 'Erro:', error);
                return null;
            }
        },
        _updateUI: function(data) {
            const remaining = data.remaining_slots || 0;
            const total = data.total_slots || CONFIG.TOTAL_PROMOTIONAL_SLOTS;
            const isSoldOut = remaining <= 0;
            const isUrgent = remaining <= CONFIG.VAGAS_URGENT_THRESHOLD && remaining > 0;
            const percent = total > 0 ? ((total - remaining) / total) * 100 : 0;

            const el = {
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

            if (el.vagasRestantes) {
                const oldValue = parseInt(el.vagasRestantes.textContent) || 0;
                el.vagasRestantes.textContent = remaining;
                if (oldValue !== remaining && oldValue > 0) {
                    el.vagasRestantes.style.transition = 'transform 0.3s ease';
                    el.vagasRestantes.style.transform = 'scale(1.4)';
                    setTimeout(() => { el.vagasRestantes.style.transform = 'scale(1)'; }, 300);
                }
            }
            if (el.vagasTotal) el.vagasTotal.textContent = total;
            if (el.vagasPercentText) el.vagasPercentText.textContent = Math.round(percent) + '% preenchidas';
            if (el.vagasHeaderText) el.vagasHeaderText.textContent = remaining;
            if (el.vagasProgress) {
                el.vagasProgress.style.width = Math.min(100, percent) + '%';
                el.vagasProgress.classList.remove('urgent', 'sold-out');
                if (isSoldOut) el.vagasProgress.classList.add('sold-out');
                else if (isUrgent) el.vagasProgress.classList.add('urgent');
            }
            if (el.vagasContainer) {
                el.vagasContainer.classList.remove('urgent', 'sold-out');
                if (isSoldOut) el.vagasContainer.classList.add('sold-out');
                else if (isUrgent) el.vagasContainer.classList.add('urgent');
            }
            if (el.vagasUrgentAlert && el.vagasUrgentCount) {
                if (isUrgent) { el.vagasUrgentAlert.classList.add('show'); el.vagasUrgentCount.textContent = remaining; }
                else el.vagasUrgentAlert.classList.remove('show');
            }
            if (el.vagasSoldOutAlert) {
                if (isSoldOut) el.vagasSoldOutAlert.classList.add('show');
                else el.vagasSoldOutAlert.classList.remove('show');
            }
            if (el.planBadgeText) {
                if (isSoldOut) {
                    el.planBadgeText.textContent = '❌ PROMOÇÃO ESGOTADA';
                    el.planBadgeText.style.color = '#dc3545';
                } else if (isUrgent) {
                    el.planBadgeText.textContent = '🔥 ÚLTIMAS ' + remaining + ' VAGAS!';
                    el.planBadgeText.style.color = '#f5a623';
                    el.planBadgeText.style.animation = 'badgePulse 0.8s ease-in-out infinite';
                } else {
                    el.planBadgeText.textContent = '🔥 ' + remaining + ' VAGAS DISPONÍVEIS';
                    el.planBadgeText.style.color = '#ffffff';
                    el.planBadgeText.style.animation = 'badgePulse 2s ease-in-out infinite';
                }
            }
            if (isSoldOut) {
                if (el.currentPrice) el.currentPrice.textContent = '149.90';
                if (el.oldPrice) el.oldPrice.style.display = 'none';
                if (el.economyBadge) {
                    el.economyBadge.textContent = '❌ PROMOÇÃO ESGOTADA';
                    el.economyBadge.style.background = 'linear-gradient(135deg, #dc3545, #c0392b)';
                }
                if (el.btnUpgrade) {
                    el.btnUpgrade.innerHTML = `<i class="fas fa-exclamation-triangle me-2"></i>COMPRAR POR R$ 149,90<small class="d-block fs-10">Promoção encerrada</small>`;
                    el.btnUpgrade.classList.add('sold-out');
                }
            } else {
                if (el.btnUpgrade) {
                    el.btnUpgrade.classList.remove('sold-out');
                    const price = data.user_locked_price || CONFIG.PROMOTIONAL_PRICE;
                    el.btnUpgrade.innerHTML = `
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
            if (this._updateInterval) { clearInterval(this._updateInterval); this._updateInterval = null; }
        }
    };

    // ==============================================
    // 🔥 ESTADO GLOBAL
    // ==============================================

    let deps = null;
    let _statusCache = {};
    let _isCreatingPayment = false;
    let _pixModalInstance = null;
    window._upgradeInProgress = false;
    window._cpfModalOpen = false;

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
        return { isAdmin: false, isPremium: false, credits: 0, user: null, tokenValid: false };
    }

    async function loadPremiumStatus() {
        if (!deps || !deps.fetchWithAuth) return null;
        try {
            const response = await deps.fetchWithAuth('/api/payments/subscription-status');
            if (response?.ok) {
                const data = await response.json();
                if (window.__APP_STATE_MANAGER) window.__APP_STATE_MANAGER.updatePremiumStatus(data);
                if (deps.EventBus) {
                    deps.EventBus.emit('payment:premium_status_updated', {
                        isPremium: data.is_premium || false,
                        daysLeft: data.days_left || 0,
                        hasPromotionalPrice: data.promotional_price_locked || false,
                        promotionalPrice: data.promotional_price || null,
                        canReceiveDailyCredit: data.can_receive_today || false,
                        receivedDailyCreditToday: data.received_today || false,
                        creditsBalance: data.credits_balance || 0,
                        maxCredits: data.max_credits || CONFIG.MAX_CREDITS_BALANCE
                    });
                }
                return data;
            }
        } catch (error) {
            Logger.error('payment.js', 'Erro premium status:', error);
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
            Logger.error('payment.js', 'Erro crédito diário:', error);
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
            .forEach(el => { if (el) el.textContent = display; });
        window.dispatchEvent(new CustomEvent('creditsUpdated', {
            detail: { credits: _credits, display, maxCredits: CONFIG.MAX_CREDITS_BALANCE, isPremium: _isPremium }
        }));
    }

    // ==============================================
    // 🔥 MODAL CPF
    // ==============================================

    function openCpfModal(planId) {
        if (!deps) { window.resetUpgradeButton(); return; }
        if (window._cpfModalOpen) {
            deps.AppUtils.showNotification('⏳ Aguarde o processamento atual...', 'warning');
            return;
        }
        const authStatus = getAuthStatus();
        if (authStatus.isAdmin) {
            deps.AppUtils.showNotification('👑 Administrador tem acesso ilimitado.', 'info');
            window.resetUpgradeButton(); return;
        }
        if (authStatus.isPremium) {
            deps.AppUtils.showNotification('✅ Você já possui um plano ativo!', 'success');
            window.location.href = '/dashboard';
            window.resetUpgradeButton(); return;
        }
        if (_isCreatingPayment) {
            deps.AppUtils.showNotification('⏳ Aguarde o processamento atual...', 'warning');
            window.resetUpgradeButton(); return;
        }

        window._cpfModalOpen = true;

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
        cpfModal.addEventListener('hidden.bs.modal', function() {
            window._cpfModalOpen = false;
            window.resetUpgradeButton();
        });
        cpfModal.addEventListener('hide.bs.modal', function() {
            window._cpfModalOpen = false;
            window.resetUpgradeButton();
        });
        try {
            new bootstrap.Modal(cpfModal).show();
        } catch (e) {
            cpfModal.style.display = 'block';
            cpfModal.classList.add('show');
            setTimeout(() => { window._cpfModalOpen = false; window.resetUpgradeButton(); }, 5000);
        }
    }

    function getCpfModalHTML(planId) {
        return `
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content" style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border: 1px solid #f5a623;">
                    <div class="modal-header border-0">
                        <h5 class="modal-title" style="color: #f5a623;"><i class="fas fa-id-card me-2"></i>Confirme seu CPF</h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <p class="text-white-50 mb-3"><i class="fas fa-shield-alt me-2"></i> CPF obrigatório para gerar PIX e proteger sua compra.</p>
                        <div class="mb-3">
                            <label class="form-label text-white">CPF</label>
                            <input type="text" class="form-control form-control-lg" id="cpfInput" placeholder="000.000.000-00" maxlength="14" style="background: rgba(255,255,255,0.1); border-color: #f5a623; color: white; border-radius:12px;" autocomplete="off">
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
                e.target.value = CpfValidator.mask(e.target.value);
                if (cpfError) cpfError.classList.add('d-none');
                const cleaned = e.target.value.replace(/\D/g, '');
                if (cleaned.length === 11) {
                    const result = CpfValidator.validate(cleaned);
                    if (!result.valid && cpfError) {
                        cpfError.textContent = `❌ ${result.message}`;
                        cpfError.classList.remove('d-none');
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
                    if (!result.valid && cpfError) {
                        cpfError.textContent = `❌ ${result.message}`;
                        cpfError.classList.remove('d-none');
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
                }, 500);
            });
        }
        if (cpfInput) {
            cpfInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' && confirmBtn) { e.preventDefault(); confirmBtn.click(); }
            });
        }
    }

    // ==============================================
    // 🔥 CRIAR PAGAMENTO (V8.0)
    // ==============================================

    async function createPaymentWithPix(cpf, planId = 'premium_mensal') {
        if (_isCreatingPayment) {
            deps?.AppUtils?.showNotification('⏳ Aguarde o processamento atual...', 'warning');
            window.resetUpgradeButton(); return;
        }
        if (!deps) {
            deps?.AppUtils?.showNotification('Erro interno. Recarregue a página.', 'error');
            window.resetUpgradeButton(); return;
        }

        _isCreatingPayment = true;
        const btn = document.getElementById('btnUpgrade');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i> Gerando PIX...';
            btn.classList.add('loading');
        }

        const validPlanId = planId || 'premium_mensal';
        Logger.info('payment.js', `Criando PIX para CPF ${cpf.substring(0, 3)}***${cpf.substring(cpf.length - 3)}`);
        deps.AppUtils.showNotification('🔄 Gerando QR Code PIX...', 'info');

        try {
            const response = await RetrySystem.execute(async (attempt) => {
                const resp = await deps.fetchWithAuth('/api/payments/create-pix', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ cpf: cpf, plan_id: validPlanId })
                });

                if (!resp) throw new Error('Falha na conexão com o servidor');

                if (resp.status === 429) {
                    let errorData = {};
                    try { errorData = await resp.json(); } catch (e) {}
                    throw new Error(errorData.detail || errorData.message || 'Muitas tentativas. Aguarde.');
                }

                if (!resp.ok) {
                    let errorData = {};
                    try { errorData = await resp.json(); }
                    catch (e) {
                        try { const text = await resp.text(); errorData = { detail: text || `Erro ${resp.status}` }; }
                        catch (e2) { errorData = { detail: `Erro ${resp.status}` }; }
                    }
                    throw new Error(errorData.detail || errorData.message || `Erro ${resp.status}`);
                }
                return resp;
            }, {
                maxAttempts: CONFIG.MAX_RETRY_ATTEMPTS,
                baseDelay: CONFIG.RETRY_BASE_DELAY,
                maxDelay: CONFIG.RETRY_MAX_DELAY,
                onRetry: (attempt, error) => {
                    if (error.message.includes('429') || error.message.includes('rate')) throw error;
                    deps.AppUtils.showNotification(`⏳ Tentando novamente (${attempt}/${CONFIG.MAX_RETRY_ATTEMPTS})...`, 'warning');
                },
                context: 'createPaymentWithPix'
            });

            const data = await response.json();

            // 🔥 V8.0: LOG CRU
            console.log('%c📦 BACKEND PAYLOAD', 'background:#222;color:#0f0;padding:4px', data);

            // 🔥 V8.0: Normalização estrita
            const normalized = PixPayloadNormalizer.normalize(data);

            let qrCodeBase64 = normalized.qrCodeBase64;
            let pixCode = normalized.pixCode;

            Logger.info('payment.js', '🔍 Normalizado:', {
                hasImage: normalized.hasImage,
                hasPixCode: normalized.hasPixCode,
                imagePreview: qrCodeBase64 ? qrCodeBase64.substring(0, 50) : 'VAZIO',
                pixPreview: pixCode ? pixCode.substring(0, 50) : 'VAZIO'
            });

            // 🔥 V8.0: Se não veio imagem mas temos copia-e-cola → gera local
            if (!qrCodeBase64 && pixCode) {
                Logger.info('payment.js', '📱 Sem imagem do backend — gerando QR Code localmente...');
                const generated = QrCodeSystem.generateFromText(pixCode);
                if (generated) {
                    qrCodeBase64 = generated;
                    Logger.info('payment.js', '✅ QR Code gerado localmente!');
                }
            }

            // 🔥 V8.0: Só renderiza se for data URL válida
            const shouldRenderImage = qrCodeBase64 &&
                                      qrCodeBase64.startsWith('data:image') &&
                                      qrCodeBase64.length > 200;

            console.log('%c🎯 QR CHECK FINAL', 'background:#024;color:#0ff;padding:4px', {
                shouldRenderImage,
                hasPixCode: !!pixCode,
                imageLen: qrCodeBase64 ? qrCodeBase64.length : 0,
                pixLen: pixCode ? pixCode.length : 0
            });

            if (!shouldRenderImage && !pixCode) {
                throw new Error('Mercado Pago não retornou QR Code válido. Tente novamente.');
            }

            // Atualiza data com campos normalizados
            data.qr_code_base64 = shouldRenderImage ? qrCodeBase64 : '';
            data.pix_code = pixCode;
            data.qr_code = pixCode;

            // Eventos (apenas créditos/status — NÃO o payment:completed aqui)
            if (deps.EventBus) {
                if (data.credits_balance !== undefined) {
                    deps.EventBus.emit('creditsUpdated', {
                        credits: data.credits_balance,
                        isPremium: data.is_premium || false,
                        maxCredits: CONFIG.MAX_CREDITS_BALANCE
                    });
                }
            }

            // 🔥 V8.0: payment:completed NÃO é emitido aqui (só após aprovação real)

            showPixModal(data);
            _isCreatingPayment = false;
            window.resetUpgradeButton();

        } catch (error) {
            Logger.error('payment.js', 'Erro ao criar pagamento:', error);

            let userMessage = error.message || 'Erro ao gerar pagamento. Tente novamente.';
            if (userMessage.includes('422')) userMessage = 'Dados inválidos. Verifique seu CPF.';
            else if (userMessage.includes('429') || userMessage.includes('rate')) userMessage = 'Muitas tentativas. Aguarde alguns minutos.';
            else if (userMessage.includes('CPF')) userMessage = 'CPF inválido. Verifique e tente novamente.';
            else if (userMessage.includes('conexão') || userMessage.includes('connection')) userMessage = 'Erro de conexão. Verifique sua internet.';
            else if (userMessage.includes('QR Code')) userMessage = 'Serviço indisponível. Tente novamente em instantes.';

            deps.AppUtils.showNotification(`❌ ${userMessage}`, 'error');
            _isCreatingPayment = false;
            window.resetUpgradeButton();
        }
    }

    // ==============================================
    // 🔥 MODAL PIX (V8.0 - consome dados normalizados)
    // ==============================================

    let countdownInterval = null;
    let statusPollingInterval = null;

    function showPixModal(data) {
        Logger.info('payment.js', 'Mostrando modal PIX...');

        if (_pixModalInstance) {
            try { _pixModalInstance.hide(); } catch (e) {}
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

        // 🔥 V8.0: Dados JÁ normalizados por createPaymentWithPix
        let qrCodeBase64 = data.qr_code_base64 || '';
        let pixCode = data.pix_code || data.qr_code || '';

        // 🔥 Trava final
        const shouldRenderImage = qrCodeBase64 &&
                                  qrCodeBase64.startsWith('data:image') &&
                                  qrCodeBase64.length > 200;

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

            if (qrImg && shouldRenderImage) {
                Logger.info('payment.js', '🖼️ Renderizando imagem do QR Code...');
                qrImg.src = qrCodeBase64;
                qrImg.style.display = 'block';
                if (placeholder) placeholder.style.display = 'none';

                qrImg.onload = function() {
                    Logger.info('payment.js', '✅ QR Code carregado!');
                    if (placeholder) placeholder.style.display = 'none';
                    qrImg.style.display = 'block';
                };
                qrImg.onerror = function() {
                    Logger.warn('payment.js', '⚠️ Imagem falhou — fallback textual');
                    qrImg.style.display = 'none';
                    if (placeholder) {
                        placeholder.style.display = 'flex';
                        placeholder.innerHTML = renderFallback(pixCode);
                    }
                };
            } else if (placeholder) {
                Logger.info('payment.js', '📱 Sem imagem — fallback textual');
                if (qrImg) qrImg.style.display = 'none';
                placeholder.style.display = 'flex';
                placeholder.innerHTML = renderFallback(pixCode);
            }

            const codeText = pixModal.querySelector('#pixCodeText');
            if (codeText && pixCode) codeText.textContent = pixCode;

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
            pixModal.innerHTML = getPixModalHTML(
                data, shouldRenderImage ? qrCodeBase64 : '', pixCode, amount, planName
            );
        }

        startCountdown(CONFIG.PIX_EXPIRY_MINUTES * 60);
        startStatusPolling(paymentId);

        try {
            _pixModalInstance = new bootstrap.Modal(pixModal);
            _pixModalInstance.show();
        } catch (e) {
            pixModal.style.display = 'block';
            pixModal.classList.add('show');
        }
    }

    function renderFallback(pixCode) {
        if (pixCode) {
            return `
                <div style="text-align:center;">
                    <i class="fas fa-file-invoice" style="font-size:2.5rem;color:#48bb78;margin-bottom:0.5rem;"></i>
                    <div style="font-size:0.7rem;color:#999;word-break:break-all;max-width:180px;">
                        ${pixCode.substring(0, 60)}...
                    </div>
                    <div style="font-size:0.6rem;color:#666;margin-top:0.3rem;">
                        Clique em "Copiar Chave PIX" abaixo
                    </div>
                </div>
            `;
        }
        return `
            <div style="text-align:center;">
                <i class="fas fa-exclamation-circle" style="font-size:2.5rem;color:#f5a623;margin-bottom:0.5rem;"></i>
                <div style="font-size:0.8rem;color:#999;">QR Code indisponível</div>
                <div style="font-size:0.6rem;color:#666;margin-top:0.3rem;">Tente novamente</div>
            </div>
        `;
    }

    function getPixModalHTML(data, qrCode, pixCode, amount, planName) {
        // 🔥 V8.0: Só monta <img> se realmente for data URL
        const hasValidImage = qrCode &&
                              qrCode.startsWith('data:image') &&
                              qrCode.length > 200;

        const qrCodeHtml = hasValidImage
            ? `<img src="${qrCode}" alt="QR Code PIX" style="max-width:200px;border-radius:8px;" id="pixQrCode">`
            : `<div id="pixQrPlaceholder" style="width:200px;height:200px;background:rgba(255,255,255,0.05);display:flex;align-items:center;justify-content:center;border-radius:8px;color:#999;font-size:13px;padding:12px;text-align:center;">
                   ${renderFallback(pixCode)}
               </div>`;

        return `
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content" style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border: 1px solid rgba(205,127,50,0.3);">
                    <div class="modal-header border-0" style="border-bottom:1px solid rgba(255,255,255,0.1);">
                        <h5 class="modal-title" style="color:#f5a623;"><i class="fas fa-qrcode me-2"></i> Pagamento via PIX</h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body text-center py-4">
                        <div class="alert alert-success mb-3 text-center" style="background:rgba(40,167,69,0.15);border-color:#28a745;color:#48bb78;">
                            <i class="fas fa-gem me-2"></i>
                            <strong>${data.was_promotional ? '🎉 VOCÊ GARANTIU O PREÇO FUNDADOR!' : '💰 PAGAMENTO GERADO'}</strong><br>
                            <small>R$ ${amount.toFixed(2).replace('.', ',')} ${data.was_promotional ? '- Preço bloqueado VITALÍCIO!' : ''}</small>
                        </div>
                        <h6 class="mb-3" style="color:rgba(255,255,255,0.7);">${hasValidImage ? 'Escaneie o QR Code com seu banco' : 'Copie o código PIX abaixo'}</h6>
                        <div class="text-center mb-3">
                            <div class="p-3 d-inline-block" style="background:${hasValidImage ? 'white' : 'transparent'};border-radius:16px;">
                                ${qrCodeHtml}
                            </div>
                        </div>
                        <div class="p-3 rounded-3 mb-3" style="background:rgba(255,255,255,0.05);word-break:break-all;">
                            <code id="pixCodeText" class="small" style="color:#f5a623;">${pixCode || 'Chave PIX indisponível'}</code>
                        </div>
                        <button class="btn w-100 mb-3" onclick="window.copyPixCode()" style="background:rgba(255,255,255,0.06);color:#f5a623;border:1px solid rgba(205,127,50,0.3);border-radius:12px;padding:0.75rem;">
                            <i class="fas fa-copy me-2"></i> Copiar Chave PIX
                        </button>
                        <div class="alert alert-info small" style="background:rgba(245,166,35,0.08);border-color:rgba(205,127,50,0.2);color:rgba(255,255,255,0.7);">
                            <i class="fas fa-info-circle me-2"></i>
                            <strong>Informações:</strong><br>
                            <strong id="pixPlanText">${planName}</strong> - Valor: R$ ${amount.toFixed(2).replace('.', ',')}<br>
                            <span class="text-success" id="pixPromoBadge">${data.was_promotional ? '✅ Preço de fundador garantido!' : '💰 Preço regular'}</span><br>
                            <span style="color:rgba(255,255,255,0.5);">⏰ Expira em <strong id="countdownTimer">${CONFIG.PIX_EXPIRY_MINUTES}:00</strong> minutos.</span>
                        </div>
                        <div id="paymentStatus" class="mt-2"></div>
                    </div>
                    <div class="modal-footer border-0 justify-content-center" style="border-top:1px solid rgba(255,255,255,0.06);">
                        <button type="button" class="btn w-100" id="pixVerifyBtn" data-payment-id="${data.payment_id || ''}" style="background:rgba(255,255,255,0.06);color:rgba(255,255,255,0.6);border:none;border-radius:50px;padding:0.75rem;">
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
        if (statusPollingInterval) { clearInterval(statusPollingInterval); statusPollingInterval = null; }
        if (!paymentId || !deps) return;

        let attempts = 0;
        const maxAttempts = CONFIG.STATUS_MAX_ATTEMPTS;

        statusPollingInterval = setInterval(async () => {
            attempts++;
            const cacheKey = `status_${paymentId}`;
            const cached = _statusCache[cacheKey];
            if (cached && (Date.now() - cached.timestamp) < CONFIG.STATUS_CACHE_TTL) {
                if (cached.status === 'approved') {
                    clearInterval(statusPollingInterval); statusPollingInterval = null;
                    handlePaymentApproved(paymentId);
                }
                return;
            }
            try {
                const response = await deps.fetchWithAuth(`/api/payments/status/${paymentId}`);
                if (response?.ok) {
                    const data = await response.json();
                    const payment = data.payment || data;
                    _statusCache[cacheKey] = { status: payment.status, timestamp: Date.now() };

                    if (payment.status === 'approved') {
                        clearInterval(statusPollingInterval); statusPollingInterval = null;
                        handlePaymentApproved(paymentId);
                    } else if (payment.status === 'rejected' || payment.status === 'cancelled') {
                        clearInterval(statusPollingInterval); statusPollingInterval = null;
                        deps.AppUtils.showNotification(`❌ Pagamento ${payment.status}. Tente novamente.`, 'error');
                    }
                }
            } catch (error) {
                Logger.warn('payment.js', 'Erro status polling:', error);
            }
            if (attempts >= maxAttempts) {
                clearInterval(statusPollingInterval); statusPollingInterval = null;
            }
        }, CONFIG.STATUS_POLLING_INTERVAL);
    }

    function handlePaymentApproved(paymentId) {
        deps.AppUtils.showNotification('✅ Pagamento confirmado! Seu plano foi ativado.', 'success');

        // 🔥 V8.0: atualiza estado sem reload
        if (window.__APP_STATE) {
            window.__APP_STATE.isPremium = true;
            window.__APP_STATE.credits = 30;
        }
        if (window.__APP_STATE_MANAGER) {
            window.__APP_STATE_MANAGER.updatePremiumStatus({ is_premium: true, days_left: 30 });
            window.__APP_STATE_MANAGER.updateCredits(30);
        }
        updateCreditsDisplay(30, true);

        // 🔥 V8.0: AQUI sim dispara payment:completed (após aprovação real)
        window.dispatchEvent(new CustomEvent('premiumStatusUpdated', {
            detail: { isPremium: true, daysLeft: 30, creditsBalance: 30 }
        }));
        window.dispatchEvent(new CustomEvent('payment:completed', {
            detail: { payment_id: paymentId, status: 'approved' }
        }));

        if (_pixModalInstance) _pixModalInstance.hide();

        // 🔥 V8.0: soft-reload só se o app não reagir aos eventos
        setTimeout(() => {
            if (!window.__APP_STATE || !window.__APP_STATE.isPremium) {
                window.location.reload();
            }
        }, 2500);
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
                clearInterval(countdownInterval); countdownInterval = null;
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
        if (!code || code === 'Chave PIX indisponível') {
            deps?.AppUtils?.showNotification('❌ Chave PIX não disponível', 'error');
            return;
        }
        if (navigator.clipboard?.writeText) {
            navigator.clipboard.writeText(code)
                .then(() => deps?.AppUtils?.showNotification('✅ Chave PIX copiada!', 'success'))
                .catch(() => fallbackCopy(code));
        } else fallbackCopy(code);
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
        if (!deps) return;
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
                deps.AppUtils.showNotification('⏳ Ainda não confirmado. Aguarde alguns minutos.', 'warning');
            } else {
                deps.AppUtils.showNotification(`⏳ Status: ${payment.status}`, 'info');
            }
        } catch (error) {
            Logger.error('payment.js', 'Erro verify:', error);
            deps.AppUtils.showNotification('Erro ao verificar pagamento.', 'error');
        }
    };

    // ==============================================
    // 🔥 INIT
    // ==============================================

    async function init() {
        Logger.info('payment.js', 'v8.0 Iniciando...');
        const appReady = await Waiter.waitForApp();
        deps = appReady ? Waiter.getDependencies() : {
            EventBus: window.EventBus || null,
            AppUtils: window.AppUtils || null,
            fetchWithAuth: window.fetchWithAuth || null,
            State: window.__APP_STATE || null,
            StateManager: window.__APP_STATE_MANAGER || null
        };
        Waiter.validateDependencies(deps);
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
        window.PixPayloadNormalizer = PixPayloadNormalizer; // 🔥 debug

        window.paymentReady = true;
        window.paymentVersion = '8.0';
        window._paymentInitialized = true;

        window.dispatchEvent(new CustomEvent('paymentReady', {
            detail: { version: '8.0', integrated: true, appReady }
        }));

        Logger.info('payment.js', 'v8.0 Carregado com sucesso!');
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() { setTimeout(init, 300); });
    } else {
        setTimeout(init, 300);
    }
    document.addEventListener('app:ready', function() { init(); });

})();