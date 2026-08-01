// frontend/js/app.js - ORQUESTRADOR CENTRAL - v7.5 (COM INATIVIDADE)
/**
 * AutoAnalytics - Módulo Principal da Aplicação
 * 
 * 🏗️ ARQUITETURA V7.5:
 * 1. 🔥 CORRIGIDO: URLs absolutas com /api/
 * 2. 🔥 ADICIONADO: Helper buildApiUrl global
 * 3. 🔥 MELHORADO: Estrutura modular do Pow
 * 4. 🔥 OTIMIZADO: Cache e performance
 * 5. 🔥 ADICIONADO: Logging estruturado
 * 6. 🔥 CORRIGIDO: Tratamento de erros avançado
 * 7. 🔥 NOVO: Sistema de inatividade e limpeza automática
 * 
 * 🔥 CORREÇÕES V7.5:
 * - URLs absolutas em todas as chamadas fetch
 * - buildApiUrl para evitar duplicação
 * - Pow manager com fallback robusto
 * - Melhor tratamento de rate limit
 * - Cache com invalidação automática
 * - Sistema de inatividade com limpeza automática após 15 minutos
 */

(function() {
    'use strict';

    // ==============================================
    // 🔥 CONFIGURAÇÕES GLOBAIS
    // ==============================================

    const CONFIG = Object.freeze({
        // App
        VERSION: '7.5.0',
        
        // Upload
        MAX_FILES: 3,
        MAX_FILE_SIZE_KB: 200,
        
        // Créditos
        MAX_CREDITS_BALANCE: 3,
        INITIAL_FREE_CREDITS: 3,
        
        // Preços
        PROMOTIONAL_PRICE: 97.00,
        REGULAR_PRICE: 149.90,
        TOTAL_PROMOTIONAL_SLOTS: 100,
        DAYS_PREMIUM: 30,
        
        // Token
        TOKEN_EXPIRY_MINUTES: 15,
        SESSION_TIMEOUT: 15 * 60 * 1000,
        
        // 🔥 INATIVIDADE
        INACTIVITY_TIMEOUT: 15 * 60 * 1000, // 15 minutos
        INACTIVITY_CHECK_INTERVAL: 30000, // 30 segundos
        INACTIVITY_WARNING_TIME: 60, // 60 segundos antes de expirar
        
        // Rate Limit
        RATE_LIMIT_LOGIN_MAX: 5,
        RATE_LIMIT_LOGIN_WINDOW: 900,
        RATE_LIMIT_REGISTER_MAX: 5,
        RATE_LIMIT_REGISTER_WINDOW: 3600,
        
        // PoW
        POW_STOCK_SIZE: 2,
        API_BASE: '/api',
        
        // Rotas
        ROUTES: {
            PROTECTED: ['/', '/dashboard', '/planos', '/checkout'],
            PUBLIC: ['/login', '/register'],
            HOME: '/dashboard',
            LOGIN: '/login'
        },
        
        // UI
        UI_CACHE_TTL: 5000,
        DEBOUNCE_DELAY: 50,
        
        // Reload
        RELOAD_COOLDOWN: 3000,
        MAX_RELOADS: 3,
        RELOAD_STORAGE_KEY: '_aa_reload_count',
        AUTH_BLOCK_KEY: '_aa_auth_block',
        
        // 🔥 Novas configurações
        API_RETRY_ATTEMPTS: 3,
        API_RETRY_DELAY: 1000,
        MAX_API_RETRY_DELAY: 10000,
    });

    // ==============================================
    // 🔥 HELPER GLOBAL DE API (NOVO)
    // ==============================================

    /**
     * 🔥 Constrói URL absoluta para API
     * Garante que todas as chamadas usem /api/ corretamente
     * 
     * @param {string} path - Caminho da API (ex: 'upload-auto', '/pow/challenge')
     * @returns {string} - URL absoluta (ex: '/api/upload-auto', '/api/pow/challenge')
     */
    function buildApiUrl(path) {
        if (!path) return '/api';
        
        // Garante que o path sempre comece com /
        const cleanPath = path.startsWith('/') ? path : '/' + path;
        
        // Evita duplicar /api/api/
        if (cleanPath.startsWith('/api/')) {
            return cleanPath;
        }
        
        return '/api' + cleanPath;
    }

    // ==============================================
    // 🔥 LOGGER ESTRUTURADO (NOVO)
    // ==============================================

    const Logger = {
        levels: { debug: 0, info: 1, warn: 2, error: 3 },
        level: 'info',
        prefix: '[App]',
        enabled: true,
        history: [],
        maxHistory: 100,

        _shouldLog(level) {
            return this.enabled && this.levels[level] >= this.levels[this.level];
        },

        _format(level, message, args) {
            const timestamp = new Date().toISOString().substring(11, 19);
            const logMessage = `${timestamp} ${this.prefix} ${message}`;
            
            this.history.push({ timestamp: Date.now(), level, message, args });
            if (this.history.length > this.maxHistory) this.history.shift();
            
            return logMessage;
        },

        debug(message, ...args) {
            if (!this._shouldLog('debug')) return;
            console.debug(this._format('debug', message, args), ...args);
        },

        info(message, ...args) {
            if (!this._shouldLog('info')) return;
            console.log(this._format('info', message, args), ...args);
        },

        warn(message, ...args) {
            if (!this._shouldLog('warn')) return;
            console.warn(this._format('warn', message, args), ...args);
        },

        error(message, ...args) {
            if (!this._shouldLog('error')) return;
            console.error(this._format('error', message, args), ...args);
        },

        setLevel(level) {
            if (this.levels[level] !== undefined) {
                this.level = level;
            }
        },

        getHistory() {
            return this.history;
        }
    };

    // ==============================================
    // 🔥 GERENCIADOR DE RELOAD (ANTI-LOOP)
    // ==============================================

    const ReloadManager = {
        _lastReload: 0,
        _reloadCount: 0,
        
        canReload: function() {
            const now = Date.now();
            
            if (now - this._lastReload < CONFIG.RELOAD_COOLDOWN) {
                Logger.warn('⛔ Cooldown ativo, evitando reload');
                return false;
            }
            
            let storedCount = parseInt(sessionStorage.getItem(CONFIG.RELOAD_STORAGE_KEY) || '0');
            if (storedCount >= CONFIG.MAX_RELOADS) {
                Logger.error('❌ Número máximo de reloads atingido. Redirecionando para login.');
                sessionStorage.removeItem(CONFIG.RELOAD_STORAGE_KEY);
                window.location.replace('/login');
                return false;
            }
            
            storedCount++;
            sessionStorage.setItem(CONFIG.RELOAD_STORAGE_KEY, String(storedCount));
            this._reloadCount = storedCount;
            this._lastReload = now;
            
            return true;
        },
        
        reset: function() {
            sessionStorage.removeItem(CONFIG.RELOAD_STORAGE_KEY);
            this._reloadCount = 0;
            this._lastReload = 0;
        },
        
        getCount: function() {
            return parseInt(sessionStorage.getItem(CONFIG.RELOAD_STORAGE_KEY) || '0');
        }
    };

    // ==============================================
    // 🔥 EVENT BUS UNIFICADO (OTIMIZADO)
    // ==============================================

    const EventBus = {
        _handlers: new Map(),
        _queue: [],
        _processing: false,
        _maxQueueSize: 1000,
        _eventHistory: [],
        _maxHistory: 100,

        on: function(event, handler, options = {}) {
            if (!this._handlers.has(event)) {
                this._handlers.set(event, []);
            }
            this._handlers.get(event).push({
                handler,
                once: options.once || false,
                priority: options.priority || 0,
                id: options.id || null
            });
            
            this._handlers.get(event).sort((a, b) => b.priority - a.priority);
            
            return () => this.off(event, handler);
        },

        once: function(event, handler) {
            return this.on(event, handler, { once: true });
        },

        off: function(event, handler) {
            if (!this._handlers.has(event)) return;
            
            const handlers = this._handlers.get(event);
            const index = handlers.findIndex(h => h.handler === handler);
            if (index !== -1) {
                handlers.splice(index, 1);
            }
            
            if (handlers.length === 0) {
                this._handlers.delete(event);
            }
        },

        offById: function(event, id) {
            if (!this._handlers.has(event)) return;
            
            const handlers = this._handlers.get(event);
            const filtered = handlers.filter(h => h.id !== id);
            
            if (filtered.length === 0) {
                this._handlers.delete(event);
            } else {
                this._handlers.set(event, filtered);
            }
        },

        emit: function(event, data = {}) {
            this._eventHistory.push({ event, data, timestamp: Date.now() });
            if (this._eventHistory.length > this._maxHistory) {
                this._eventHistory.shift();
            }
            
            this._queue.push({ event, data, timestamp: Date.now() });
            
            if (this._queue.length > this._maxQueueSize) {
                this._queue.shift();
            }
            
            if (!this._processing) {
                this._processQueue();
            }
            
            try {
                window.dispatchEvent(new CustomEvent(event, { detail: data, bubbles: true }));
                document.dispatchEvent(new CustomEvent(event, { detail: data, bubbles: true }));
            } catch (e) {
                // Ignora
            }
        },

        _processQueue: function() {
            if (this._processing) return;
            if (this._queue.length === 0) return;
            
            this._processing = true;
            
            const batch = this._queue.splice(0, 10);
            
            for (const item of batch) {
                this._dispatch(item.event, item.data);
            }
            
            this._processing = false;
            
            if (this._queue.length > 0) {
                setTimeout(() => this._processQueue(), 0);
            }
        },

        _dispatch: function(event, data) {
            if (!this._handlers.has(event)) return;
            
            const handlers = this._handlers.get(event);
            const toRemove = [];
            
            for (let i = 0; i < handlers.length; i++) {
                const { handler, once } = handlers[i];
                try {
                    handler(data);
                } catch (e) {
                    Logger.error(`❌ Erro no handler do evento ${event}:`, e);
                }
                if (once) {
                    toRemove.push(i);
                }
            }
            
            if (toRemove.length > 0) {
                const remaining = handlers.filter((_, index) => !toRemove.includes(index));
                if (remaining.length === 0) {
                    this._handlers.delete(event);
                } else {
                    this._handlers.set(event, remaining);
                }
            }
        },

        clear: function() {
            this._handlers.clear();
            this._queue = [];
            this._eventHistory = [];
        },

        getQueueSize: function() {
            return this._queue.length;
        },
        
        getHistory: function() {
            return this._eventHistory;
        }
    };

    // ==============================================
    // 🔥 GERENCIADOR DE INATIVIDADE (NOVO)
    // ==============================================

    const InactivityManager = {
        _timeoutId: null,
        _checkInterval: null,
        _inactivityLimit: CONFIG.INACTIVITY_TIMEOUT,
        _lastActivity: Date.now(),
        _isExpired: false,
        _cleanupCallbacks: [],
        _isInitialized: false,
        _warningShown: false,
        
        // 🔥 Registrar callback para limpeza
        registerCleanup: function(callback) {
            if (typeof callback === 'function') {
                this._cleanupCallbacks.push(callback);
            }
            return this;
        },
        
        // 🔥 Resetar timer de inatividade
        resetTimer: function() {
            this._lastActivity = Date.now();
            this._warningShown = false;
            this._isExpired = false;
            this._clearTimeout();
            this._startTimer();
            this._hideWarning();
        },
        
        _startTimer: function() {
            this._clearTimeout();
            
            this._timeoutId = setTimeout(() => {
                Logger.info('⏰ Inatividade detectada - limpando dados...');
                this._performCleanup();
            }, this._inactivityLimit);
            
            // 🔥 Check interval para aviso prévio
            if (this._checkInterval) {
                clearInterval(this._checkInterval);
            }
            
            this._checkInterval = setInterval(() => {
                const elapsed = Date.now() - this._lastActivity;
                const remaining = this._inactivityLimit - elapsed;
                
                // 🔥 Aviso 60 segundos antes
                if (remaining < CONFIG.INACTIVITY_WARNING_TIME * 1000 && 
                    remaining > 0 && 
                    !this._warningShown && 
                    !this._isExpired) {
                    this._warningShown = true;
                    this._showWarning(Math.ceil(remaining / 1000));
                }
                
                // 🔥 Se já expirou e não foi limpo
                if (remaining <= 0 && !this._isExpired) {
                    this._isExpired = true;
                    this._performCleanup();
                }
            }, 10000);
        },
        
        _clearTimeout: function() {
            if (this._timeoutId) {
                clearTimeout(this._timeoutId);
                this._timeoutId = null;
            }
            if (this._checkInterval) {
                clearInterval(this._checkInterval);
                this._checkInterval = null;
            }
        },
        
        _showWarning: function(seconds) {
            // 🔥 Mostrar toast de aviso
            if (window.toastr) {
                window.toastr.warning(
                    `⏰ Sua sessão expirará em ${seconds} segundos por inatividade.`,
                    '⚠️ Atenção',
                    {
                        timeOut: 10000,
                        closeButton: true,
                        progressBar: true,
                        positionClass: 'toast-top-center'
                    }
                );
            }
            
            // 🔥 Mostrar notificação na UI
            const container = document.getElementById('messageContainer');
            if (container) {
                const existing = container.querySelector('.inactivity-warning');
                if (existing) existing.remove();
                
                const warning = document.createElement('div');
                warning.className = 'message-banner message-warning message-visible inactivity-warning';
                warning.style.cssText = `
                    background: linear-gradient(145deg, rgba(40, 40, 60, 0.98), rgba(30, 30, 50, 0.98));
                    border-left-color: #f5a623;
                    padding: 10px 14px;
                    margin-bottom: 6px;
                    border-radius: 10px;
                    backdrop-filter: blur(20px);
                    border: 1px solid rgba(255, 193, 7, 0.2);
                `;
                warning.innerHTML = `
                    <div class="message-content">
                        <div class="message-icon" style="color: #f5a623; font-size: 18px;">
                            <i class="fas fa-clock"></i>
                        </div>
                        <div class="message-text">
                            <div class="message-title" style="color: #f5a623; font-size: 0.8rem; font-weight: 700;">
                                ⏰ Sessão expirando
                            </div>
                            <div class="message-body" style="font-size: 0.7rem; color: rgba(255,255,255,0.7);">
                                Sua sessão expirará em <strong id="inactivityCountdown">${seconds}</strong> segundos por inatividade.
                                <br><small style="color: rgba(255,255,255,0.4);">Clique em qualquer lugar para continuar</small>
                            </div>
                        </div>
                        <button class="message-dismiss" onclick="window.InactivityManager?.resetTimer()" style="background:transparent; border:none; color:rgba(255,255,255,0.3); font-size:0.8rem; padding:2px;">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                `;
                container.appendChild(warning);
                container.style.display = 'block';
                
                // 🔥 Atualizar contador
                let remaining = seconds;
                const countdownEl = warning.querySelector('#inactivityCountdown');
                if (countdownEl) {
                    const interval = setInterval(() => {
                        remaining--;
                        if (remaining <= 0 || this._isExpired) {
                            clearInterval(interval);
                            if (warning.parentNode) warning.remove();
                            return;
                        }
                        countdownEl.textContent = remaining;
                    }, 1000);
                }
            }
            
            Logger.info(`⚠️ Aviso de inatividade: ${seconds}s restantes`);
        },
        
        _hideWarning: function() {
            const container = document.getElementById('messageContainer');
            if (container) {
                const warnings = container.querySelectorAll('.inactivity-warning');
                warnings.forEach(el => el.remove());
            }
        },
        
        _performCleanup: function() {
            if (this._isExpired) return;
            this._isExpired = true;
            
            Logger.info('🧹 Executando limpeza por inatividade...');
            
            // 🔥 Executar todos os callbacks de limpeza
            this._cleanupCallbacks.forEach(cb => {
                try { 
                    cb(); 
                } catch (e) { 
                    Logger.warn('⚠️ Erro no callback de limpeza:', e); 
                }
            });
            
            // 🔥 Limpar dados do dashboard
            this._clearDashboardData();
            
            // 🔥 Limpar upload
            this._clearUploadData();
            
            // 🔥 Limpar gráficos
            this._clearCharts();
            
            // 🔥 Mostrar notificação
            const message = '⏰ Sessão expirada por inatividade. Recarregue a página para continuar.';
            
            if (window.toastr) {
                window.toastr.warning(message, 'Sessão expirada', {
                    timeOut: 5000,
                    closeButton: true,
                    progressBar: true,
                    positionClass: 'toast-top-center'
                });
            }
            
            // 🔥 Recarregar a página após 3 segundos
            setTimeout(() => {
                window.location.reload();
            }, 3000);
            
            Logger.info('✅ Limpeza por inatividade concluída');
        },
        
        _clearDashboardData: function() {
            try {
                // 🔥 Limpar cache do dashboard
                if (window.__dashboard) {
                    const dashboard = window.__dashboard;
                    if (dashboard.cache) {
                        dashboard.cache.clear().catch(() => {});
                    }
                    if (dashboard.tabManager) {
                        dashboard.tabManager.destroy();
                        // 🔥 Limpar abas
                        const tabList = document.getElementById('gpsaTabs');
                        if (tabList) tabList.innerHTML = '';
                        const tabContent = document.getElementById('gpsaTabContent');
                        if (tabContent) tabContent.innerHTML = '';
                    }
                    if (dashboard.state) {
                        dashboard.state.reset();
                    }
                }
                
                // 🔥 Limpar métricas
                const metricsContainer = document.getElementById('metricsContainer');
                if (metricsContainer) metricsContainer.innerHTML = '';
                
                // 🔥 Limpar relatório da IA
                const aiReport = document.getElementById('aiReportContent');
                if (aiReport) {
                    aiReport.innerHTML = `
                        <div style="color: rgba(255,255,255,0.3); font-size: 0.8rem; text-align: center; padding: 1rem;">
                            ⏰ Sessão expirada. Faça um novo upload para gerar o relatório.
                        </div>
                    `;
                }
                
                // 🔥 Limpar health indicator
                const healthIndicator = document.getElementById('gpsaHealthIndicator');
                if (healthIndicator) {
                    healthIndicator.style.cssText = `
                        display: inline-flex;
                        align-items: center;
                        gap: 0.5rem;
                        background: rgba(255,255,255,0.03);
                        color: rgba(255,255,255,0.3);
                        border: 1px solid rgba(255,255,255,0.05);
                        border-radius: 20px;
                        padding: 0.3rem 1rem;
                        font-size: 0.7rem;
                    `;
                    healthIndicator.innerHTML = '⏳ Sessão expirada';
                }
                
                // 🔥 Esconder resultado
                const resultContainer = document.getElementById('resultContainer');
                if (resultContainer) {
                    resultContainer.classList.remove('show');
                    resultContainer.style.display = 'none';
                }
                const resultPlaceholder = document.getElementById('resultPlaceholder');
                if (resultPlaceholder) resultPlaceholder.style.display = 'block';
                
                // 🔥 Limpar status
                const statusEl = document.getElementById('analysisStatus');
                if (statusEl) statusEl.classList.remove('show');
                
                Logger.info('🧹 Dados do dashboard limpos');
            } catch (e) {
                Logger.warn('⚠️ Erro ao limpar dashboard:', e);
            }
        },
        
        _clearUploadData: function() {
            try {
                // 🔥 Limpar preview de arquivos
                const previewContainer = document.getElementById('filePreviewContainer');
                if (previewContainer) previewContainer.innerHTML = '';
                
                // 🔥 Limpar input
                const fileInput = document.getElementById('fileInput');
                if (fileInput) fileInput.value = '';
                
                // 🔥 Limpar área de upload
                const dropArea = document.getElementById('dropArea');
                if (dropArea) {
                    dropArea.classList.remove('success', 'error', 'uploading');
                }
                
                // 🔥 Resetar estado do upload via window.UploadSystem
                if (window.UploadSystem && typeof window.UploadSystem.clearFiles === 'function') {
                    window.UploadSystem.clearFiles();
                }
                
                Logger.info('🧹 Dados de upload limpos');
            } catch (e) {
                Logger.warn('⚠️ Erro ao limpar upload:', e);
            }
        },
        
        _clearCharts: function() {
            try {
                // 🔥 Limpar gráficos do Chart.js
                if (window._chartInstances) {
                    Object.keys(window._chartInstances).forEach(key => {
                        try {
                            window._chartInstances[key].destroy();
                            delete window._chartInstances[key];
                        } catch (e) {}
                    });
                    window._chartInstances = {};
                }
                
                // 🔥 Limpar gráficos do dashboard
                if (window.__dashboard && window.__dashboard.tabManager) {
                    const chartRenderer = window.__dashboard.tabManager._chartRenderer;
                    if (chartRenderer && typeof chartRenderer.destroyAll === 'function') {
                        chartRenderer.destroyAll();
                    }
                }
                
                Logger.info('🧹 Gráficos limpos');
            } catch (e) {
                Logger.warn('⚠️ Erro ao limpar gráficos:', e);
            }
        },
        
        // 🔥 Iniciar monitoramento
        init: function() {
            if (this._isInitialized) return;
            this._isInitialized = true;
            
            // 🔥 Resetar timer em eventos de atividade
            const events = ['click', 'mousemove', 'keydown', 'scroll', 'touchstart', 'wheel'];
            const resetHandler = () => {
                if (!this._isExpired) {
                    this.resetTimer();
                }
            };
            
            events.forEach(event => {
                document.addEventListener(event, resetHandler);
            });
            
            // 🔥 Iniciar timer
            this._startTimer();
            
            // 🔥 Registrar limpeza do dashboard
            this.registerCleanup(() => {
                if (window.__dashboard && window.__dashboard.state) {
                    window.__dashboard.state.reset();
                }
            });
            
            Logger.info(`✅ InactivityManager inicializado (timeout: ${this._inactivityLimit/60000} minutos)`);
            
            // 🔥 Expor globalmente
            window.InactivityManager = this;
        },
        
        // 🔥 Método para estender o tempo
        extend: function(extraMinutes = 5) {
            if (this._isExpired) return false;
            
            const extraMs = extraMinutes * 60 * 1000;
            const newLimit = this._inactivityLimit + extraMs;
            this._inactivityLimit = newLimit;
            this.resetTimer();
            
            Logger.info(`⏰ Tempo de inatividade estendido em ${extraMinutes} minutos`);
            return true;
        },
        
        // 🔥 Obter status
        getStatus: function() {
            const elapsed = Date.now() - this._lastActivity;
            const remaining = Math.max(0, this._inactivityLimit - elapsed);
            return {
                isActive: !this._isExpired,
                secondsRemaining: Math.ceil(remaining / 1000),
                minutesRemaining: Math.ceil(remaining / 60000),
                isExpired: this._isExpired,
                lastActivity: new Date(this._lastActivity).toISOString()
            };
        }
    };

    // ==============================================
    // 🔥 ESTADO GLOBAL (COM PROXY + PERSISTÊNCIA)
    // ==============================================

    const initialState = {
        user: null,
        credits: 0,
        isPremium: false,
        isAdmin: false,
        creditsDisplay: '0',
        
        initialized: false,
        userInitialized: false,
        isAppReady: false,
        tokenValid: false,
        tokenExpiresAt: null,
        lastActivity: Date.now(),
        loadAttempts: 0,
        
        premiumStatus: null,
        hasPromotionalPrice: false,
        promotionalPrice: null,
        isVitalicio: false,
        daysLeftPremium: 0,
        canReceiveDailyCredit: false,
        receivedDailyCreditToday: false,
        
        powReady: false,
        powSolutionsReady: 0,
        powAutoRefillActive: false,
        
        rateLimitBlocked: false,
        rateLimitBlockedUntil: 0,
        rateLimitRemainingAttempts: CONFIG.RATE_LIMIT_LOGIN_MAX,
        rateLimitBlockedFor: 'login',
        
        activeAnalyses: [],
        recentAnalyses: [],
        totalAnalyses: 0,
        analysesToday: 0,
        
        userSegment: null,
        currentMessage: null,
        lastMessageId: null,
        uiContext: null,
        
        _listeners: [],
        _intervals: [],
        _updateQueue: [],
        _isUpdating: false
    };

    // 🔥 Carregar estado salvo
    try {
        const savedState = localStorage.getItem('__APP_STATE_PERSIST');
        if (savedState) {
            const parsed = JSON.parse(savedState);
            const persistKeys = ['user', 'credits', 'isPremium', 'isAdmin', 'creditsDisplay'];
            persistKeys.forEach(key => {
                if (parsed[key] !== undefined) {
                    initialState[key] = parsed[key];
                }
            });
        }
    } catch (e) {
        // Ignora erro
    }

    const State = new Proxy(initialState, {
        set(target, key, value) {
            const oldValue = target[key];
            const changed = oldValue !== value;
            
            target[key] = value;
            
            if (changed) {
                if (key === 'credits' || key === 'isPremium' || key === 'isAdmin') {
                    const isAdmin = target.isAdmin;
                    const isPremium = target.isPremium;
                    const credits = target.credits || 0;
                    target.creditsDisplay = isAdmin ? '∞' : (isPremium ? `${credits}/${CONFIG.MAX_CREDITS_BALANCE}` : String(credits));
                }
                
                const eventData = {
                    state: target,
                    key,
                    oldValue,
                    newValue: value,
                    timestamp: Date.now()
                };
                
                EventBus.emit('app:state_changed', eventData);
                window.dispatchEvent(new CustomEvent('app:state_changed', { detail: eventData }));
                
                // 🔥 Persistir estado (apenas chaves selecionadas)
                try {
                    const persistKeys = ['user', 'credits', 'isPremium', 'isAdmin', 'creditsDisplay'];
                    const toSave = {};
                    persistKeys.forEach(k => {
                        if (target[k] !== undefined) {
                            toSave[k] = target[k];
                        }
                    });
                    localStorage.setItem('__APP_STATE_PERSIST', JSON.stringify(toSave));
                } catch (e) {
                    // Ignora
                }
            }
            
            return true;
        },
        
        get(target, key) {
            return target[key];
        }
    });

    window.__APP_STATE = State;

    // ==============================================
    // 🔥 GERENCIADOR DE ESTADO
    // ==============================================

    const StateManager = {
        updateState: function(newState) {
            for (const [key, value] of Object.entries(newState)) {
                if (value !== undefined) {
                    State[key] = value;
                }
            }
            return State;
        },
        
        updateCredits: function(credits, isPremium = null) {
            if (credits !== undefined) State.credits = credits;
            if (isPremium !== null) State.isPremium = isPremium;
            return State;
        },
        
        updatePremiumStatus: function(status) {
            State.isPremium = status.is_premium || false;
            State.daysLeftPremium = status.days_left || 0;
            State.hasPromotionalPrice = status.promotional_price_locked || false;
            State.promotionalPrice = status.promotional_price || null;
            State.canReceiveDailyCredit = status.can_receive_today || false;
            State.receivedDailyCreditToday = status.received_today || false;
            State.credits = status.credits_balance || State.credits;
            return State;
        },
        
        getState: function() {
            return { ...State };
        },
        
        reset: function() {
            const newState = { ...initialState };
            for (const [key, value] of Object.entries(newState)) {
                State[key] = value;
            }
            try {
                localStorage.removeItem('__APP_STATE_PERSIST');
            } catch (e) {
                // Ignora
            }
            return State;
        }
    };

    window.__APP_STATE_MANAGER = StateManager;

    // ==============================================
    // 🔥 UTILITÁRIOS
    // ==============================================

    const Utils = {
        formatDate: (date) => {
            const d = new Date(date);
            return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR');
        },

        escapeHtml: (text) => {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        },

        sanitizeNumber: (value, defaultValue = 0) => {
            if (value === undefined || value === null) return defaultValue;
            const num = parseFloat(String(value).replace(/[^0-9.,-]/g, '').replace(',', '.'));
            return isNaN(num) ? defaultValue : num;
        },

        formatCreditsDisplay: (credits, isPremium = false) => {
            if (State.isAdmin) return '∞';
            const safeCredits = Utils.sanitizeNumber(credits, 0);
            if (isPremium || State.isPremium) {
                return `${safeCredits}/${CONFIG.MAX_CREDITS_BALANCE}`;
            }
            return safeCredits.toString();
        },

        showNotification: (message, type = 'info') => {
            if (window.toastr && window.toastr[type]) {
                try {
                    window.toastr[type](message);
                    return true;
                } catch (e) {
                    Logger.warn('⚠️ Toastr falhou:', e);
                }
            }
            
            if (type === 'error' || type === 'warning') {
                Logger.warn(`[${type}] ${message}`);
                alert(`⚠️ ${message}`);
                return true;
            }
            
            Logger.info(`[${type}] ${message}`);
            return true;
        },

        getCurrentPath: () => window.location.pathname,
        getQueryParam: (param) => new URLSearchParams(window.location.search).get(param),
        
        redirectTo: (url) => {
            if (window.location.pathname !== url) {
                window.location.href = url;
            }
        },
        
        goBack: () => window.history.back(),
        goForward: () => window.history.forward(),
        
        reload: () => {
            if (ReloadManager.canReload()) {
                window.location.reload();
            }
        },

        isAuthenticated: () => {
            try {
                const token = localStorage.getItem('access_token');
                return token && token !== '' && token !== 'undefined' && token !== 'null' && token.length > 10;
            } catch (e) {
                return false;
            }
        },

        isRateLimitBlocked: () => {
            if (State.rateLimitBlocked && Date.now() < State.rateLimitBlockedUntil) {
                return true;
            }
            if (State.rateLimitBlocked && Date.now() >= State.rateLimitBlockedUntil) {
                State.rateLimitBlocked = false;
                State.rateLimitBlockedUntil = 0;
                State.rateLimitRemainingAttempts = CONFIG.RATE_LIMIT_LOGIN_MAX;
                State.rateLimitBlockedFor = 'login';
                return false;
            }
            return false;
        },

        getRateLimitTimeRemaining: () => {
            if (!State.rateLimitBlocked) return 0;
            return Math.max(0, Math.ceil((State.rateLimitBlockedUntil - Date.now()) / 1000));
        },

        getRateLimitRemainingAttempts: () => State.rateLimitRemainingAttempts,

        waitFor: (condition, timeout = 10000, interval = 200) => {
            return new Promise((resolve) => {
                const startTime = Date.now();
                const check = () => {
                    try {
                        if (condition()) {
                            resolve(true);
                            return;
                        }
                    } catch (e) {
                        // Ignora
                    }
                    
                    if (Date.now() - startTime > timeout) {
                        resolve(false);
                        return;
                    }
                    setTimeout(check, interval);
                };
                check();
            });
        },

        validateCPF: function(cpf) {
            const clean = String(cpf).replace(/\D/g, '');
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
        
        debounce: function(func, delay = CONFIG.DEBOUNCE_DELAY) {
            let timeoutId;
            return function(...args) {
                clearTimeout(timeoutId);
                timeoutId = setTimeout(() => func.apply(this, args), delay);
            };
        },
        
        throttle: function(func, limit = 100) {
            let inThrottle;
            return function(...args) {
                if (!inThrottle) {
                    func.apply(this, args);
                    inThrottle = true;
                    setTimeout(() => inThrottle = false, limit);
                }
            };
        },
        
        // 🔥 NOVO: Retry com backoff
        retry: async function(fn, attempts = CONFIG.API_RETRY_ATTEMPTS, delay = CONFIG.API_RETRY_DELAY) {
            let lastError;
            for (let i = 0; i < attempts; i++) {
                try {
                    return await fn();
                } catch (error) {
                    lastError = error;
                    if (i < attempts - 1) {
                        const backoff = Math.min(delay * Math.pow(2, i), CONFIG.MAX_API_RETRY_DELAY);
                        await Utils.sleep(backoff);
                    }
                }
            }
            throw lastError;
        },
        
        sleep: (ms) => new Promise(resolve => setTimeout(resolve, ms))
    };

    window.AppUtils = {
        buildApiUrl: buildApiUrl,
        sanitizeNumber: Utils.sanitizeNumber,
        formatCreditsDisplay: Utils.formatCreditsDisplay,
        escapeHtml: Utils.escapeHtml,
        formatDate: Utils.formatDate,
        showNotification: Utils.showNotification,
        isAuthenticated: Utils.isAuthenticated,
        validateCPF: Utils.validateCPF,
        getMaxCredits: () => CONFIG.MAX_CREDITS_BALANCE,
        getConfig: () => CONFIG,
        debounce: Utils.debounce,
        throttle: Utils.throttle,
        retry: Utils.retry,
        sleep: Utils.sleep,
    };

    // 🔥 Expor buildApiUrl globalmente
    window.buildApiUrl = buildApiUrl;

    // ==============================================
    // 🔥 FETCH UNIFICADO (COM REFRESH AUTOMÁTICO)
    // ==============================================

    let _isRefreshing = false;
    let _refreshPromise = null;

    async function refreshTokenSafely() {
        if (_isRefreshing) {
            return _refreshPromise || false;
        }
        
        _isRefreshing = true;
        _refreshPromise = (async () => {
            try {
                const refreshToken = localStorage.getItem('refresh_token');
                if (!refreshToken) {
                    Logger.warn('⚠️ Sem refresh token disponível');
                    return false;
                }
                
                const url = buildApiUrl('/auth/refresh');
                const response = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ refresh_token: refreshToken })
                });
                
                if (response.ok) {
                    const data = await response.json();
                    if (data.access_token) {
                        localStorage.setItem('access_token', data.access_token);
                        document.cookie = `access_token=${data.access_token}; path=/; max-age=900; SameSite=Strict; Secure`;
                        
                        if (data.refresh_token) {
                            localStorage.setItem('refresh_token', data.refresh_token);
                        }
                        if (data.user) {
                            localStorage.setItem('user_data', JSON.stringify(data.user));
                            localStorage.setItem('user_email', data.user.email || '');
                        }
                        
                        Logger.info('✅ Token renovado com sucesso!');
                        EventBus.emit('auth:token_refreshed', { message: 'Token renovado automaticamente' });
                        return true;
                    }
                }
                
                Logger.warn('⚠️ Falha ao renovar token');
                return false;
            } catch (error) {
                Logger.error('❌ Erro ao renovar token:', error);
                return false;
            } finally {
                _isRefreshing = false;
                _refreshPromise = null;
            }
        })();
        
        return _refreshPromise;
    }

    async function fetchWithAuth(url, options = {}) {
        // 🔥 Garantir URL absoluta
        const finalUrl = buildApiUrl(url);
        
        try {
            const token = localStorage.getItem('access_token');
            if (!token) {
                Logger.warn('⚠️ fetchWithAuth: sem token');
                EventBus.emit('auth:unauthorized', { message: 'Token não encontrado' });
                return null;
            }
            
            const headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': `Bearer ${token}`,
                ...options.headers
            };
            
            if (options.body instanceof FormData) {
                delete headers['Content-Type'];
            }
            
            let response = await fetch(finalUrl, { ...options, headers });
            
            if (response.status === 401) {
                Logger.warn('⚠️ Token expirado, tentando refresh...');
                
                const refreshed = await refreshTokenSafely();
                if (refreshed) {
                    const newToken = localStorage.getItem('access_token');
                    if (newToken) {
                        headers['Authorization'] = `Bearer ${newToken}`;
                        response = await fetch(finalUrl, { ...options, headers });
                        if (response.ok) {
                            return response;
                        }
                    }
                }
                
                Logger.error('❌ Falha ao renovar token, redirecionando para login');
                EventBus.emit('auth:unauthorized', { message: 'Sessão expirada', redirect: true });
                handleUnauthorized();
                return null;
            }
            
            if (response.status === 429) {
                const data = await response.json().catch(() => ({}));
                const retryAfter = data.retry_after || 60;
                const remaining = data.remaining_attempts || 0;
                
                EventBus.emit('rate_limit:blocked', {
                    retryAfter: retryAfter,
                    remaining: remaining,
                    message: data.detail || data.message || 'Muitas requisições. Aguarde um momento.',
                    for: url
                });
                
                Utils.showNotification(`⏳ Aguarde ${retryAfter} segundos antes de tentar novamente.`, 'warning');
                return response;
            }
            
            if (response.status === 402) {
                const data = await response.json().catch(() => ({}));
                Logger.warn('⚠️ Créditos insuficientes:', data);
                EventBus.emit('credits:insufficient', {
                    message: data.message || 'Créditos insuficientes',
                    credits_available: data.credits_available || 0,
                    credits_needed: data.credits_needed || 1
                });
                return response;
            }
            
            return response;
        } catch (error) {
            Logger.error('❌ fetchWithAuth error:', error);
            EventBus.emit('fetch:error', { url: finalUrl, error: error.message, options });
            return null;
        }
    }

    // ==============================================
    // 🔥 HANDLE UNAUTHORIZED
    // ==============================================

    function handleUnauthorized() {
        Logger.error('❌ [Orquestrador] Sessão inválida ou expirada.');
        
        sessionStorage.setItem(CONFIG.AUTH_BLOCK_KEY, String(Date.now()));
        
        localStorage.clear();
        document.cookie.split(';').forEach(function(c) {
            document.cookie = c.replace(/^ +/, '').replace(/=.*/, '=;expires=' + new Date().toUTCString() + ';path=/');
        });
        
        StateManager.updateState({
            user: null,
            credits: 0,
            isPremium: false,
            isAdmin: false,
            tokenValid: false,
            isAppReady: false,
            userInitialized: false
        });
        
        EventBus.emit('auth:unauthorized', { message: 'Sessão inválida ou expirada', redirect: true });
        
        setTimeout(() => {
            window.location.replace('/login');
        }, 300);
    }

    // ==============================================
    // 🔥 ROTEADOR
    // ==============================================

    const Router = {
        isProtected: function() {
            const path = Utils.getCurrentPath();
            return CONFIG.ROUTES.PROTECTED.some(route => 
                path === route || path.startsWith(route + '/') || path.startsWith(route + '?')
            );
        },

        isPublic: function() {
            const path = Utils.getCurrentPath();
            return CONFIG.ROUTES.PUBLIC.some(route => 
                path === route || path.startsWith(route + '/') || path.startsWith(route + '?')
            );
        },

        protect: function() {
            const isAuth = Utils.isAuthenticated();
            
            if (this.isProtected() && !isAuth) {
                Logger.info('🔒 Rota protegida - redirecionando para login');
                Utils.redirectTo(CONFIG.ROUTES.LOGIN);
                return false;
            }

            if (this.isPublic() && isAuth) {
                Logger.info('✅ Usuário já logado - redirecionando para dashboard');
                Utils.redirectTo(CONFIG.ROUTES.HOME);
                return false;
            }

            return true;
        },

        navigate: function(url) {
            const isProtected = CONFIG.ROUTES.PROTECTED.some(route => 
                url === route || url.startsWith(route + '/') || url.startsWith(route + '?')
            );
            
            if (isProtected && !Utils.isAuthenticated()) {
                Utils.showNotification('Faça login para acessar esta página.', 'warning');
                Utils.redirectTo(CONFIG.ROUTES.LOGIN);
                return;
            }

            Utils.redirectTo(url);
        },

        setupNavigation: function() {
            document.querySelectorAll('[data-nav]').forEach(el => {
                el.addEventListener('click', (e) => {
                    e.preventDefault();
                    const target = el.getAttribute('data-nav');
                    if (target) Router.navigate(target);
                });
            });

            document.querySelectorAll('a[href^="/"]').forEach(el => {
                if (el.hasAttribute('data-nav') || 
                    el.getAttribute('target') === '_blank' || 
                    el.id === 'logoutBtn') return;
                
                el.addEventListener('click', (e) => {
                    const href = el.getAttribute('href');
                    if (href && !href.startsWith('http') && !href.startsWith('#')) {
                        e.preventDefault();
                        Router.navigate(href);
                    }
                });
            });
        }
    };

    // ==============================================
    // 🔥 UI MANAGER (OTIMIZADO)
    // ==============================================

    const UI = {
        _elements: new Map(),
        _elementCache: new Map(),
        _cacheTimestamps: new Map(),
        _updateTimeout: null,
        _isUpdating: false,
        _lastUpdate: 0,

        _getElement: function(selector, forceRefresh = false) {
            const now = Date.now();
            const cached = this._elementCache.get(selector);
            const timestamp = this._cacheTimestamps.get(selector) || 0;
            
            if (!forceRefresh && cached && (now - timestamp) < CONFIG.UI_CACHE_TTL) {
                return cached;
            }
            
            const el = document.querySelector(selector);
            this._elementCache.set(selector, el);
            this._cacheTimestamps.set(selector, now);
            return el;
        },

        invalidateCache: function() {
            this._elementCache.clear();
            this._cacheTimestamps.clear();
            Logger.debug('🧹 Cache de UI invalidado');
        },

        scheduleUpdate: function() {
            if (this._updateTimeout) {
                clearTimeout(this._updateTimeout);
            }
            this._updateTimeout = setTimeout(() => {
                this.updateNavbar();
                this._updateTimeout = null;
            }, CONFIG.DEBOUNCE_DELAY);
        },

        updateNavbar: function() {
            const now = Date.now();
            if (this._isUpdating) return;
            if (now - this._lastUpdate < 50) return;
            
            this._isUpdating = true;
            
            try {
                const isAuth = Utils.isAuthenticated();
                
                document.querySelectorAll('.auth-required').forEach(el => {
                    el.style.display = isAuth ? 'block' : 'none';
                });
                document.querySelectorAll('.guest-only').forEach(el => {
                    el.style.display = isAuth ? 'none' : 'block';
                });

                if (isAuth) {
                    try {
                        const name = State.user?.name || 'Usuário';
                        document.querySelectorAll('.user-name').forEach(el => {
                            el.textContent = name;
                        });
                        document.querySelectorAll('.workshop-name').forEach(el => {
                            el.textContent = State.user?.workshop_name || 'Oficina';
                        });

                        UI.updateCredits();
                        UI.updateAdminBadge();
                        UI.updatePremiumBadge();
                        UI.updateVitalicioBadge();
                        UI.updatePowStatus();
                        UI.updateRateLimitStatus();
                    } catch (e) {
                        Logger.warn('Erro ao atualizar navbar:', e);
                    }
                }
                
                this._lastUpdate = now;
            } finally {
                this._isUpdating = false;
            }
        },

        updateCredits: function() {
            try {
                const credits = State.credits || 0;
                const isPremium = State.isPremium || false;
                const isAdmin = State.isAdmin || false;
                
                const formattedDisplay = isAdmin ? '∞' : (isPremium ? `${credits}/${CONFIG.MAX_CREDITS_BALANCE}` : String(credits));
                State.creditsDisplay = formattedDisplay;
                
                const selectors = [
                    '.credits-display', '.user-credits', 
                    '#creditsDisplay', '#creditsCount', '#uploadCredits',
                    '.credits-badge span', '.credits-value'
                ];
                
                document.querySelectorAll(selectors.join(',')).forEach(el => {
                    if (el) el.textContent = formattedDisplay;
                });

                EventBus.emit('credits:updated', {
                    credits,
                    display: formattedDisplay,
                    maxCredits: CONFIG.MAX_CREDITS_BALANCE,
                    isPremium
                });

            } catch (e) {
                Logger.warn('Erro ao atualizar créditos:', e);
            }
        },

        updateAdminBadge: function() {
            const isAdmin = State.isAdmin || false;
            document.querySelectorAll('.admin-badge, .admin-only').forEach(el => {
                el.style.display = isAdmin ? 'inline-block' : 'none';
            });
            document.body.classList.toggle('is-admin', isAdmin);
        },

        updatePremiumBadge: function() {
            const isPremium = State.isPremium || false;
            document.querySelectorAll('.premium-badge, .premium-only').forEach(el => {
                el.style.display = isPremium ? 'inline-block' : 'none';
            });

            if (isPremium && State.daysLeftPremium > 0) {
                document.querySelectorAll('.premium-days-badge').forEach(el => {
                    el.textContent = `${State.daysLeftPremium} dias`;
                    el.style.display = 'inline-block';
                });
            } else {
                document.querySelectorAll('.premium-days-badge').forEach(el => {
                    el.style.display = 'none';
                });
            }

            document.body.classList.toggle('is-premium', isPremium);
        },

        updateVitalicioBadge: function() {
            const hasVitalicio = State.hasPromotionalPrice && State.promotionalPrice !== null;
            
            document.querySelectorAll('.vitalicio-badge, .vitalicio-only').forEach(el => {
                el.style.display = hasVitalicio ? 'inline-block' : 'none';
            });

            if (hasVitalicio) {
                document.querySelectorAll('.vitalicio-price').forEach(el => {
                    el.textContent = `R$ ${State.promotionalPrice.toFixed(2).replace('.', ',')}`;
                });
                document.body.classList.add('has-vitalicio');
            } else {
                document.body.classList.remove('has-vitalicio');
            }
        },

        updatePowStatus: function() {
            try {
                if (window.powClient && typeof window.powClient.getStats === 'function') {
                    const stats = window.powClient.getStats();
                    State.powSolutionsReady = stats.solutionsReady || 0;
                    State.powAutoRefillActive = stats.autoRefill || false;
                    
                    const powBadge = document.getElementById('powStatus');
                    if (powBadge) {
                        if (stats.solutionsReady > 0) {
                            powBadge.textContent = `⚡ ${stats.solutionsReady}`;
                            powBadge.className = 'badge bg-success';
                            powBadge.style.display = 'inline-block';
                        } else {
                            powBadge.textContent = '⚡ 0';
                            powBadge.className = 'badge bg-warning';
                            powBadge.style.display = 'inline-block';
                        }
                    }
                }
            } catch (e) {
                Logger.warn('Erro ao atualizar status PoW:', e);
            }
        },

        updateRateLimitStatus: function() {
            const isBlocked = Utils.isRateLimitBlocked();
            const timeRemaining = Utils.getRateLimitTimeRemaining();
            
            const rateLimitBadge = document.getElementById('rateLimitStatus');
            if (rateLimitBadge) {
                if (isBlocked) {
                    const minutes = Math.floor(timeRemaining / 60);
                    const seconds = timeRemaining % 60;
                    rateLimitBadge.textContent = `⛔ ${minutes}m${seconds}s`;
                    rateLimitBadge.className = 'badge bg-danger';
                    rateLimitBadge.style.display = 'inline-block';
                } else {
                    rateLimitBadge.style.display = 'none';
                }
            }

            const loginBtn = document.getElementById('loginBtn');
            if (loginBtn && isBlocked) {
                const minutes = Math.floor(timeRemaining / 60);
                const seconds = timeRemaining % 60;
                let timeMsg = '';
                if (minutes > 0) {
                    timeMsg = `${minutes}m`;
                    if (seconds > 0) timeMsg += ` ${seconds}s`;
                } else {
                    timeMsg = `${seconds}s`;
                }
                loginBtn.disabled = true;
                loginBtn.innerHTML = `<i class="fas fa-hourglass-half me-2"></i> Aguarde ${timeMsg}`;
                
                clearTimeout(window._rateLimitLoginTimer);
                window._rateLimitLoginTimer = setTimeout(() => {
                    loginBtn.disabled = false;
                    loginBtn.innerHTML = '<i class="fas fa-sign-in-alt me-2"></i> Entrar';
                    State.rateLimitBlocked = false;
                    State.rateLimitBlockedUntil = 0;
                    UI.updateRateLimitStatus();
                }, timeRemaining * 1000);
            }
        },

        showLoading: function(message = 'Processando...', submessage = '') {
            const overlay = document.getElementById('loadingOverlay');
            if (overlay) {
                const text = document.getElementById('loadingText');
                const subtext = document.getElementById('loadingSubtext');
                const progress = document.getElementById('loadingProgressBar');
                
                if (text) text.textContent = message;
                if (subtext) subtext.textContent = submessage || 'Aguarde...';
                if (progress) progress.style.width = '0%';
                
                overlay.classList.add('show');
            } else {
                Logger.info('⏳ Loading:', message);
            }
        },

        hideLoading: function() {
            const overlay = document.getElementById('loadingOverlay');
            if (overlay) {
                overlay.classList.remove('show');
            }
        },

        updateLoadingProgress: function(percent, message = null) {
            const progress = document.getElementById('loadingProgressBar');
            const text = document.getElementById('loadingText');
            
            if (progress) progress.style.width = `${Math.min(100, percent)}%`;
            if (message && text) text.textContent = message;
        },

        setupModals: function() {
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') {
                    document.querySelectorAll('.modal.show').forEach(modal => {
                        try {
                            const instance = bootstrap.Modal.getInstance(modal);
                            if (instance) instance.hide();
                        } catch (e) {}
                    });
                }
            });

            document.querySelectorAll('.modal').forEach(modal => {
                modal.addEventListener('click', (e) => {
                    if (e.target === modal) {
                        try {
                            const instance = bootstrap.Modal.getInstance(modal);
                            if (instance) instance.hide();
                        } catch (e) {}
                    }
                });
            });
        },

        clearElementCache: function() {
            this._elements.clear();
            this._elementCache.clear();
            this._cacheTimestamps.clear();
        }
    };

    // ==============================================
    // 🔥 AUTH (OTIMIZADO)
    // ==============================================

    const Auth = {
        _sessionTimeout: null,

        startSessionTimer: function() {
            if (this._sessionTimeout) {
                clearTimeout(this._sessionTimeout);
                this._sessionTimeout = null;
            }

            if (!Utils.isAuthenticated()) return;

            Logger.info(`⏰ Timer de sessão: ${CONFIG.SESSION_TIMEOUT/60000} minutos`);

            this._sessionTimeout = setTimeout(() => {
                Logger.warn('⏰ Sessão expirada por inatividade');
                Utils.showNotification('⏰ Sessão expirada por inatividade. Faça login novamente.', 'warning');
                handleUnauthorized();
            }, CONFIG.SESSION_TIMEOUT);
        },

        resetSessionTimer: function() {
            if (!Utils.isAuthenticated()) return;
            this.startSessionTimer();
        },

        stop: function() {
            if (this._sessionTimeout) {
                clearTimeout(this._sessionTimeout);
                this._sessionTimeout = null;
            }
        }
    };

    // ==============================================
    // 🔥 INTERFACE DE AUTENTICAÇÃO
    // ==============================================

    window.appAuth = {
        isAuthenticated: () => Utils.isAuthenticated(),
        isAdmin: () => State.isAdmin,
        isPremium: () => State.isPremium,
        getCredits: () => State.credits,
        getCurrentUser: () => State.user,
        getState: () => StateManager.getState(),
        
        fetchWithAuth: fetchWithAuth,
        refreshTokenSafely: refreshTokenSafely,
        
        showNotification: Utils.showNotification,
        
        updateState: StateManager.updateState,
        updateCredits: StateManager.updateCredits,
        updatePremiumStatus: StateManager.updatePremiumStatus,
        
        loadUserCredits: async function() {
            try {
                const url = buildApiUrl('/auth/me');
                const response = await fetchWithAuth(url);
                if (response?.ok) {
                    const data = await response.json();
                    
                    StateManager.updateState({
                        user: data.user || null,
                        credits: data.credits || 0,
                        isPremium: data.is_premium || false,
                        isAdmin: data.is_admin || false,
                        tokenValid: true,
                        userInitialized: true,
                        isAppReady: true
                    });
                    
                    if (data.user) {
                        try {
                            localStorage.setItem('user_data', JSON.stringify(data.user));
                            localStorage.setItem('user_email', data.user.email || '');
                        } catch (e) {}
                    }
                    
                    Logger.info(`✅ Créditos carregados: ${data.credits || 0}`);
                    
                    if (window.App && typeof window.App.updateNavbar === 'function') {
                        window.App.updateNavbar();
                    }
                    
                    return data;
                }
            } catch (e) {
                Logger.warn('Erro ao carregar créditos:', e);
            }
            return null;
        },
        
        getRateLimitStatus: () => ({
            blocked: State.rateLimitBlocked,
            blockedUntil: State.rateLimitBlockedUntil,
            remainingAttempts: State.rateLimitRemainingAttempts,
            for: State.rateLimitBlockedFor,
            timeRemaining: Utils.getRateLimitTimeRemaining()
        }),
        
        refreshMessageContext: async function() {
            try {
                const token = localStorage.getItem('access_token');
                if (!token) return null;
                
                const url = buildApiUrl('/auth/session-status');
                const response = await fetch(url, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                
                if (response.ok) {
                    const data = await response.json();
                    
                    StateManager.updateState({
                        userSegment: data.segment || 'regular',
                        currentMessage: data.message_config || null,
                        lastMessageId: data.message_config?.message_id || null,
                        uiContext: data.ui_context || null
                    });
                    
                    window.dispatchEvent(new CustomEvent('message:context_updated', {
                        detail: {
                            segment: data.segment,
                            message: data.message_config,
                            ui_context: data.ui_context
                        }
                    }));
                    
                    return data;
                }
            } catch (e) {
                Logger.warn('Erro ao atualizar mensagem:', e);
            }
            return null;
        },
        
        logout: handleUnauthorized
    };

    // ==============================================
    // 🔥 GERENCIADOR DE EVENTOS
    // ==============================================

    const EventManager = {
        setup: function() {
            Logger.info('📡 Configurando gerenciador de eventos...');
            
            document.addEventListener('creditsUpdated', function(e) {
                const data = e.detail || {};
                StateManager.updateCredits(data.credits || 0, data.isPremium || false);
                if (window.App && typeof window.App.updateCredits === 'function') {
                    window.App.updateCredits();
                }
                setTimeout(() => {
                    if (window.appAuth?.refreshMessageContext) {
                        window.appAuth.refreshMessageContext();
                    }
                }, 300);
            });
            
            document.addEventListener('premiumStatusUpdated', function(e) {
                const data = e.detail || {};
                StateManager.updatePremiumStatus({
                    is_premium: data.isPremium || false,
                    days_left: data.daysLeft || 0,
                    promotional_price_locked: data.hasPromotionalPrice || false,
                    promotional_price: data.promotionalPrice || null,
                    can_receive_today: data.canReceiveDailyCredit || false,
                    received_today: data.receivedDailyCreditToday || false,
                    credits_balance: data.creditsBalance || State.credits
                });
                if (window.App && typeof window.App.updateNavbar === 'function') {
                    window.App.updateNavbar();
                }
                setTimeout(() => {
                    if (window.appAuth?.refreshMessageContext) {
                        window.appAuth.refreshMessageContext();
                    }
                }, 400);
            });
            
            document.addEventListener('paymentReady', function(e) {
                window._paymentReady = true;
                setTimeout(() => {
                    if (window.loadPremiumStatus) {
                        window.loadPremiumStatus();
                    }
                    if (window.appAuth?.loadUserCredits) {
                        window.appAuth.loadUserCredits();
                    }
                    if (window.App && typeof window.App.updateNavbar === 'function') {
                        window.App.updateNavbar();
                    }
                    setTimeout(() => {
                        if (window.appAuth?.refreshMessageContext) {
                            window.appAuth.refreshMessageContext();
                        }
                    }, 500);
                }, 300);
            });
            
            document.addEventListener('analysis:success', function(e) {
                const detail = e.detail || {};
                if (detail.result?.user_credits !== undefined) {
                    StateManager.updateCredits(detail.result.user_credits);
                }
                if (detail.result?.credits_balance !== undefined) {
                    StateManager.updateCredits(detail.result.credits_balance);
                }
                if (window.App && typeof window.App.updateCredits === 'function') {
                    window.App.updateCredits();
                }
                setTimeout(() => {
                    if (window.appAuth?.refreshMessageContext) {
                        window.appAuth.refreshMessageContext();
                    }
                }, 300);
            });
            
            document.addEventListener('upload:completed', function(e) {
                const detail = e.detail || {};
                if (detail.credits_remaining !== undefined) {
                    StateManager.updateCredits(detail.credits_remaining);
                }
                if (window.App && typeof window.App.updateCredits === 'function') {
                    window.App.updateCredits();
                }
                setTimeout(() => {
                    if (window.appAuth?.refreshMessageContext) {
                        window.appAuth.refreshMessageContext();
                    }
                }, 300);
            });

            document.addEventListener('credits:insufficient', function(e) {
                const detail = e.detail || {};
                Utils.showNotification(detail.message || 'Créditos insuficientes!', 'warning');
                window.dispatchEvent(new CustomEvent('payment:show_upgrade_modal', {
                    detail: {
                        message: detail.message,
                        credits_available: detail.credits_available,
                        credits_needed: detail.credits_needed
                    }
                }));
            });
            
            document.addEventListener('rate_limit:blocked', function(e) {
                const detail = e.detail || {};
                State.rateLimitBlocked = true;
                State.rateLimitBlockedUntil = Date.now() + (detail.retryAfter || 60) * 1000;
                State.rateLimitRemainingAttempts = detail.remaining || 0;
                if (window.App && typeof window.App.updateRateLimitStatus === 'function') {
                    window.App.updateRateLimitStatus();
                }
                Utils.showNotification(detail.message || 'Muitas tentativas. Aguarde um momento.', 'warning');
            });
            
            document.addEventListener('authReady', function(e) {
                const detail = e.detail || {};
                if (detail.isAuthenticated) {
                    StateManager.updateState({
                        tokenValid: true,
                        userInitialized: true,
                        isAppReady: true
                    });
                    setTimeout(() => {
                        if (window.appAuth?.loadUserCredits) {
                            window.appAuth.loadUserCredits();
                        }
                        if (window.App && typeof window.App.updateNavbar === 'function') {
                            window.App.updateNavbar();
                        }
                        if (window.appAuth?.refreshMessageContext) {
                            setTimeout(() => {
                                window.appAuth.refreshMessageContext();
                            }, 500);
                        }
                    }, 500);
                }
            });

            document.addEventListener('authLogout', handleUnauthorized);
            
            Logger.info('✅ Event listeners configurados');
        }
    };

    // ==============================================
    // 🔥🔥🔥 GERENCIADOR DE PoW - REFATORADO
    // ==============================================

    const Pow = {
        _client: null,
        
        isAvailable: function() {
            return window.powClient !== undefined && window.powClient !== null;
        },

        getClient: function() {
            if (!this._client) {
                this._client = window.powClient;
            }
            return this._client;
        },

        getStats: function() {
            const client = this.getClient();
            if (!client) {
                return { available: false, solutionsReady: 0 };
            }
            try {
                if (typeof client.getStats === 'function') {
                    const stats = client.getStats();
                    return {
                        available: true,
                        solutionsReady: stats.solutionsReady || 0,
                        maxStock: stats.maxStock || CONFIG.POW_STOCK_SIZE,
                        autoRefill: stats.autoRefill || false,
                        isSolving: stats.isSolving || false,
                        isAuthenticated: stats.isAuthenticated || false,
                        lastSolutionAge: stats.lastSolutionAge || null
                    };
                }
            } catch (e) {
                Logger.warn('Erro ao obter stats PoW:', e);
            }
            return { available: false, solutionsReady: 0 };
        },

        prepareForUpload: async function() {
            const client = this.getClient();
            if (!client) {
                Logger.info('⏳ PoW não disponível para preparar upload');
                return false;
            }
            try {
                if (typeof client.prepareForUpload === 'function') {
                    const result = await client.prepareForUpload();
                    if (typeof client.getStats === 'function') {
                        const stats = client.getStats();
                        State.powSolutionsReady = stats.solutionsReady || 0;
                        if (window.App && typeof window.App.updatePowStatus === 'function') {
                            window.App.updatePowStatus();
                        }
                    }
                    return result;
                }
            } catch (e) {
                Logger.warn('Erro ao preparar PoW para upload:', e);
            }
            return false;
        },

        // 🔥 CORRIGIDO: uploadWithPow com URLs absolutas
        uploadWithPow: async function(files, endpoint = '/api/upload-auto') {
            const client = this.getClient();
            
            // 🔥 Garantir URL absoluta
            const finalEndpoint = buildApiUrl(endpoint);
            
            // Se não tiver cliente, fazer upload normal
            if (!client) {
                Logger.info('⏳ PoW não disponível, usando upload normal');
                const formData = new FormData();
                if (Array.isArray(files)) {
                    for (const file of files) {
                        formData.append('files', file);
                    }
                } else {
                    formData.append('files', files);
                }
                
                const token = localStorage.getItem('access_token');
                const response = await fetch(finalEndpoint, {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` },
                    body: formData
                });
                return response;
            }

            try {
                if (typeof client.uploadWithPow === 'function') {
                    if (Array.isArray(files) && files.length > 1) {
                        const solution = await client.getSolutionForUpload();
                        const formData = new FormData();
                        for (const file of files) {
                            formData.append('files', file);
                        }
                        
                        const token = localStorage.getItem('access_token');
                        const headers = { 'Authorization': `Bearer ${token}` };
                        if (solution && solution.prefix && solution.nonce) {
                            headers['X-PoW-Challenge'] = solution.prefix;
                            headers['X-PoW-Nonce'] = solution.nonce;
                        }
                        
                        const response = await fetch(finalEndpoint, {
                            method: 'POST',
                            headers: headers,
                            body: formData
                        });
                        return response;
                    }
                    
                    const file = Array.isArray(files) ? files[0] : files;
                    return await client.uploadWithPow(file, finalEndpoint);
                }
            } catch (e) {
                Logger.error('Erro no upload com PoW:', e);
                throw e;
            }
            throw new Error('Método uploadWithPow não disponível');
        }
    };

    // ==============================================
    // 🔥 GERENCIADOR DE ANÁLISES
    // ==============================================

    const Analysis = {
        startAnalysis: function(data) {
            const analysis = {
                id: Date.now(),
                timestamp: new Date().toISOString(),
                status: 'processing',
                progress: 0,
                files: data.files || [],
                ...data
            };
            
            State.activeAnalyses.push(analysis);
            EventBus.emit('analysis:started', {
                analysis,
                activeCount: State.activeAnalyses.length
            });
            
            return analysis;
        },

        updateProgress: function(analysisId, progress, status = 'processing') {
            const analysis = State.activeAnalyses.find(a => a.id === analysisId);
            if (analysis) {
                analysis.progress = progress;
                analysis.status = status;
                analysis.lastUpdate = new Date().toISOString();
                EventBus.emit('analysis:progress', { analysis, progress, status });
            }
        },

        completeAnalysis: function(analysisId, result) {
            const index = State.activeAnalyses.findIndex(a => a.id === analysisId);
            if (index !== -1) {
                const analysis = State.activeAnalyses[index];
                analysis.status = 'completed';
                analysis.result = result;
                analysis.completedAt = new Date().toISOString();
                
                State.activeAnalyses.splice(index, 1);
                State.recentAnalyses.unshift(analysis);
                State.totalAnalyses++;
                
                if (State.recentAnalyses.length > 50) {
                    State.recentAnalyses = State.recentAnalyses.slice(0, 50);
                }

                if (result && result.user_credits !== undefined) {
                    StateManager.updateCredits(result.user_credits);
                    if (window.App && typeof window.App.updateCredits === 'function') {
                        window.App.updateCredits();
                    }
                }
                
                EventBus.emit('analysis:success', {
                    analysis,
                    result,
                    total: State.totalAnalyses,
                    today: State.analysesToday,
                    creditsUpdated: result?.credits || 0
                });
            }
        },

        failAnalysis: function(analysisId, error) {
            const index = State.activeAnalyses.findIndex(a => a.id === analysisId);
            if (index !== -1) {
                const analysis = State.activeAnalyses[index];
                analysis.status = 'failed';
                analysis.error = error;
                analysis.failedAt = new Date().toISOString();
                
                State.activeAnalyses.splice(index, 1);
                
                EventBus.emit('analysis:error', {
                    analysis,
                    error,
                    message: error.message || 'Erro na análise'
                });
            }
        },

        getActiveAnalyses: () => State.activeAnalyses,
        getRecentAnalyses: () => State.recentAnalyses.slice(0, 10),
        getTotalAnalyses: () => State.totalAnalyses,
        getAnalysesToday: () => State.analysesToday,
        
        clearHistory: function() {
            State.recentAnalyses = [];
            State.totalAnalyses = 0;
            State.analysesToday = 0;
            EventBus.emit('analysis:history_cleared', {});
        }
    };

    // ==============================================
    // 🔥 SINCRONIZAÇÃO (OTIMIZADA)
    // ==============================================

    const Sync = {
        syncAuth: async function() {
            if (!window.appAuth) {
                Logger.warn('⚠️ Auth não inicializado.');
                return false;
            }

            try {
                const isAuth = Utils.isAuthenticated();
                
                if (isAuth) {
                    await window.appAuth.loadUserCredits();
                    
                    StateManager.updateState({
                        tokenValid: true,
                        userInitialized: true
                    });
                    
                    if (window.App && typeof window.App.updateNavbar === 'function') {
                        window.App.updateNavbar();
                    }
                    Auth.startSessionTimer();
                    
                    setTimeout(() => {
                        if (window.appAuth?.refreshMessageContext) {
                            window.appAuth.refreshMessageContext();
                        }
                    }, 500);
                } else {
                    StateManager.updateState({
                        tokenValid: false,
                        userInitialized: false
                    });
                }

                return isAuth;
            } catch (e) {
                Logger.error('Erro ao sincronizar auth:', e);
                StateManager.updateState({ userInitialized: false });
                return false;
            }
        },

        syncPayment: async function() {
            if (!window.appAuth) return;
            
            try {
                await Utils.waitFor(() => {
                    return typeof window.loadPremiumStatus === 'function';
                }, 5000, 200);
                
                if (typeof window.loadPremiumStatus === 'function') {
                    await window.loadPremiumStatus();
                    Logger.info('✅ Payment sincronizado com sucesso!');
                }
            } catch (e) {
                Logger.warn('⚠️ Payment não carregou. Será sincronizado quando disponível.');
            }
        },

        // 🔥 CORRIGIDO: URL absoluta
        syncPromotion: async function() {
            try {
                const token = localStorage.getItem('access_token');
                if (!token) return;
                
                const url = buildApiUrl('/payments/promotion-status');
                const response = await fetchWithAuth(url);
                if (response?.ok) {
                    const data = await response.json();
                    
                    StateManager.updateState({
                        hasPromotionalPrice: data.user_locked_price !== null && data.user_locked_price !== undefined,
                        promotionalPrice: data.user_locked_price || null,
                        remainingSlots: data.remaining_slots,
                        totalSlots: data.total_slots
                    });
                    
                    EventBus.emit('premium:promotion_updated', {
                        hasPromotionalPrice: State.hasPromotionalPrice,
                        promotionalPrice: State.promotionalPrice,
                        remainingSlots: data.remaining_slots,
                        totalSlots: data.total_slots
                    });
                    
                    if (window.App && typeof window.App.updateVitalicioBadge === 'function') {
                        window.App.updateVitalicioBadge();
                    }
                }
            } catch (e) {
                Logger.warn('Erro ao sincronizar promoção:', e);
            }
        },

        syncRateLimit: function() {
            if (window.appAuth?.getRateLimitStatus) {
                const status = window.appAuth.getRateLimitStatus();
                if (status) {
                    StateManager.updateState({
                        rateLimitBlocked: status.blocked || false,
                        rateLimitBlockedUntil: status.blockedUntil || 0,
                        rateLimitRemainingAttempts: status.remainingAttempts || CONFIG.RATE_LIMIT_LOGIN_MAX,
                        rateLimitBlockedFor: status.for || 'login'
                    });
                    if (window.App && typeof window.App.updateRateLimitStatus === 'function') {
                        window.App.updateRateLimitStatus();
                    }
                }
            }
        }
    };

    // ==============================================
    // 🔥 INICIALIZAÇÃO DA APLICAÇÃO
    // ==============================================

    async function initApp() {
        Logger.info('🚀 Inicializando App (Orquestrador) v7.5...');

        try {
            ReloadManager.reset();

            Logger.info('⏳ Aguardando auth.js carregar...');
            await Utils.waitFor(() => window.appAuth !== undefined, 5000, 200);

            const isAuth = Utils.isAuthenticated();
            const currentPath = Utils.getCurrentPath();

            if (!Router.protect()) {
                return;
            }

            Logger.info('✅ Rota verificada, continuando inicialização...');

            EventManager.setup();

            if (window.appAuth) {
                await Sync.syncAuth();
            } else {
                if (isAuth) {
                    StateManager.updateState({
                        tokenValid: true,
                        userInitialized: true
                    });
                    Logger.info('✅ Autenticação via token (fallback)');
                }
            }
            
            Sync.syncRateLimit();

            if (isAuth) {
                Logger.info('🔐 Usuário autenticado, sincronizando serviços...');
                
                await Sync.syncPayment();
                await Sync.syncPromotion();
                
                setTimeout(() => {
                    if (window.appAuth?.refreshMessageContext) {
                        window.appAuth.refreshMessageContext();
                    }
                }, 800);
            }

            UI.setupModals();
            
            if (window.App && typeof window.App.updateNavbar === 'function') {
                window.App.updateNavbar();
            } else {
                UI.updateNavbar();
            }
            
            if (window.App && typeof window.App.updateRateLimitStatus === 'function') {
                window.App.updateRateLimitStatus();
            } else {
                UI.updateRateLimitStatus();
            }

            Router.setupNavigation();

            StateManager.updateState({
                initialized: true,
                isAppReady: true,
                userInitialized: true
            });

            window._appReadyFired = true;
            window._appInitialized = true;

            const appReadyData = {
                isAuthenticated: isAuth,
                user: State.user,
                credits: State.credits,
                creditsDisplay: State.creditsDisplay,
                isAdmin: State.isAdmin,
                isPremium: State.isPremium,
                maxCredits: CONFIG.MAX_CREDITS_BALANCE,
                hasVitalicio: State.hasPromotionalPrice,
                promotionalPrice: State.promotionalPrice,
                tokenValid: State.tokenValid,
                powReady: State.powReady,
                rateLimitBlocked: State.rateLimitBlocked,
                rateLimitTimeRemaining: Utils.getRateLimitTimeRemaining(),
                displayName: State.user?.name || 'Usuário',
                workshopName: State.user?.workshop_name || 'Oficina',
                userInitialized: State.userInitialized,
                userSegment: State.userSegment || 'regular',
                isReady: true,
                version: CONFIG.VERSION
            };

            // 🔥 INICIAR GERENCIADOR DE INATIVIDADE
            InactivityManager.init();
            
            // 🔥 Registrar callbacks de limpeza
            InactivityManager.registerCleanup(() => {
                if (window.__dashboard && window.__dashboard.state) {
                    window.__dashboard.state.reset();
                }
            });

            EventBus.emit('app:ready', appReadyData);
            window.dispatchEvent(new CustomEvent('app:ready', { detail: appReadyData }));
            document.dispatchEvent(new CustomEvent('app:ready', { detail: appReadyData }));
            
            window.dispatchEvent(new CustomEvent('appReady', { 
                detail: { isReady: true, version: CONFIG.VERSION }
            }));

            Logger.info('✅ App (Orquestrador) v7.5 inicializado com sucesso!');
            Logger.info(`📌 Autenticado: ${isAuth}`);
            Logger.info(`📌 Página: ${currentPath}`);
            Logger.info(`📌 Admin: ${State.isAdmin}`);
            Logger.info(`📌 Premium: ${State.isPremium}`);
            Logger.info(`📌 Créditos: ${State.creditsDisplay}`);
            Logger.info(`📌 Segmento: ${State.userSegment || 'Não definido'}`);
            Logger.info(`📌 Mensagem: ${State.currentMessage?.message_id || 'Nenhuma'}`);
            Logger.info(`⏰ Inatividade: ${CONFIG.INACTIVITY_TIMEOUT/60000} minutos`);
            Logger.info('🌉 window.appAuth centralizado');
            Logger.info('📦 AppUtils disponível');
            Logger.info('⚡ fetchWithAuth com refresh automático');
            Logger.info('🔄 Estado reativo via Proxy');
            Logger.info('📡 EventBus com fila de eventos');
            Logger.info('📢 Sistema de mensagens inteligentes ativo');
            Logger.info('🔗 Integrado com auth.js, payment.js, dashboard.js');
            Logger.info('🔧 CORREÇÃO V7.5: Sistema de inatividade implementado');
            Logger.info('🔧 CORREÇÃO V7.5: Limpeza automática após 15 minutos');

        } catch (error) {
            Logger.error('❌ Erro na inicialização do App:', error);
            Utils.showNotification('Erro ao inicializar aplicação. Recarregue a página.', 'error');
            
            EventBus.emit('app:error', { error: error.message || 'Erro na inicialização' });
            
            StateManager.updateState({
                initialized: false,
                isAppReady: false,
                userInitialized: false
            });
            window._appReadyFired = false;
        }
    }

    // ==============================================
    // 🔥🔥🔥 EXPORTAÇÕES GLOBAIS
    // ==============================================

    const App = {
        CONFIG,
        State,
        StateManager,
        Utils,
        EventBus,
        Logger,
        
        Router,
        UI,
        Auth,
        Pow,
        Analysis,
        Sync,
        
        // 🔥 NOVO: InactivityManager
        InactivityManager,
        
        init: initApp,
        isInitialized: function() {
            return !!(window._appInitialized && State.isAppReady);
        },
        isReady: function() {
            return State.isAppReady === true;
        },
        
        buildApiUrl: buildApiUrl,
        
        isAvailable: function() {
            return Pow.isAvailable();
        },
        
        showNotification: Utils.showNotification,
        isAuthenticated: Utils.isAuthenticated,
        getCurrentUser: () => State.user,
        getCredits: () => State.credits,
        isAdmin: () => State.isAdmin,
        isPremium: () => State.isPremium,
        hasVitalicio: () => State.hasPromotionalPrice,
        getPromotionalPrice: () => State.promotionalPrice,
        canReceiveDailyCredit: () => State.canReceiveDailyCredit,
        getDaysLeftPremium: () => State.daysLeftPremium,
        isTokenValid: () => State.tokenValid,
        
        getMessageContext: () => ({
            segment: State.userSegment,
            message: State.currentMessage,
            uiContext: State.uiContext
        }),
        getUserSegment: () => State.userSegment,
        hasActiveMessage: () => State.currentMessage !== null,
        dismissMessage: (messageId) => {
            if (messageId) {
                State.lastMessageId = messageId;
                const container = document.getElementById('messageContainer');
                if (container) {
                    container.style.display = 'none';
                    container.innerHTML = '';
                }
                window.dispatchEvent(new CustomEvent('message:dismissed', {
                    detail: { messageId }
                }));
            }
        },
        refreshMessage: async () => {
            if (window.appAuth && typeof window.appAuth.refreshMessageContext === 'function') {
                return await window.appAuth.refreshMessageContext();
            }
            return null;
        },
        
        // MÉTODOS UI COM BIND EXPLÍCITO
        updateNavbar: UI.updateNavbar.bind(UI),
        updateCredits: UI.updateCredits.bind(UI),
        updateAdminBadge: UI.updateAdminBadge.bind(UI),
        updatePremiumBadge: UI.updatePremiumBadge.bind(UI),
        updateVitalicioBadge: UI.updateVitalicioBadge.bind(UI),
        updatePowStatus: UI.updatePowStatus.bind(UI),
        updateRateLimitStatus: UI.updateRateLimitStatus.bind(UI),
        updateLoadingProgress: UI.updateLoadingProgress.bind(UI),
        showLoading: UI.showLoading.bind(UI),
        hideLoading: UI.hideLoading.bind(UI),
        setupModals: UI.setupModals.bind(UI),
        clearElementCache: UI.clearElementCache.bind(UI),
        invalidateCache: UI.invalidateCache.bind(UI),
        scheduleUpdate: UI.scheduleUpdate.bind(UI),
        
        fetchWithAuth: fetchWithAuth,
        refreshTokenSafely: refreshTokenSafely,
        
        uploadWithPow: Pow.uploadWithPow,
        preparePowForUpload: Pow.prepareForUpload,
        getPowStats: Pow.getStats,
        isPowAvailable: Pow.isAvailable,
        
        startAnalysis: Analysis.startAnalysis,
        updateAnalysisProgress: Analysis.updateProgress,
        completeAnalysis: Analysis.completeAnalysis,
        failAnalysis: Analysis.failAnalysis,
        getActiveAnalyses: Analysis.getActiveAnalyses,
        getRecentAnalyses: Analysis.getRecentAnalyses,
        getTotalAnalyses: Analysis.getTotalAnalyses,
        getAnalysesToday: Analysis.getAnalysesToday,
        clearAnalysisHistory: Analysis.clearHistory,
        
        isRateLimitBlocked: Utils.isRateLimitBlocked,
        getRateLimitTimeRemaining: Utils.getRateLimitTimeRemaining,
        getRateLimitRemainingAttempts: Utils.getRateLimitRemainingAttempts,
        getRateLimitStatus: function() {
            return {
                blocked: State.rateLimitBlocked,
                blockedUntil: State.rateLimitBlockedUntil,
                remainingAttempts: State.rateLimitRemainingAttempts,
                for: State.rateLimitBlockedFor,
                timeRemaining: Utils.getRateLimitTimeRemaining()
            };
        },
        
        navigate: Router.navigate,
        goBack: Utils.goBack,
        getQueryParam: Utils.getQueryParam,
        
        escapeHtml: Utils.escapeHtml,
        formatDate: Utils.formatDate,
        sanitizeNumber: Utils.sanitizeNumber,
        formatCreditsDisplay: Utils.formatCreditsDisplay,
        validateCPF: Utils.validateCPF,
        debounce: Utils.debounce,
        throttle: Utils.throttle,
        retry: Utils.retry,
        sleep: Utils.sleep,
        
        loadCredits: window.appAuth?.loadUserCredits || (() => {}),
        loadPremiumStatus: window.loadPremiumStatus || (() => {}),
        receiveDailyCredit: window.receiveDailyCredit || (() => {}),
        getMaxCredits: () => CONFIG.MAX_CREDITS_BALANCE,
        getCreditsBalance: () => State.credits,
        
        logout: handleUnauthorized
    };

    // EXPORTAÇÕES GLOBAIS
    window.App = App;
    window.app = App;
    window.autoAnalytics = App;
    window.EventBus = EventBus;
    window.__APP_STATE = State;
    window.__APP_STATE_MANAGER = StateManager;
    window.__APP_CONFIG = CONFIG;
    window.AppUtils = AppUtils;
    window.InactivityManager = InactivityManager;
    
    window.showNotification = Utils.showNotification;
    window.isAuthenticated = Utils.isAuthenticated;
    window.fetchWithAuth = fetchWithAuth;
    window.refreshTokenSafely = refreshTokenSafely;
    window.logout = handleUnauthorized;
    window.getCurrentUser = () => State.user;
    
    window.updateCreditsDisplay = UI.updateCredits.bind(UI);
    window.updateNavbar = UI.updateNavbar.bind(UI);
    window.updateRateLimitStatus = UI.updateRateLimitStatus.bind(UI);
    window.receiveDailyCredit = window.receiveDailyCredit || (() => {});
    window.loadPremiumStatus = window.loadPremiumStatus || (() => {});

    // INICIAR
    if (window._appInitialized) {
        Logger.warn('⚠️ App já inicializado, ignorando...');
    } else {
        window._appInitialized = true;
        
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initApp);
        } else {
            setTimeout(initApp, 150);
        }
    }

    Logger.info('✅ app.js (Orquestrador) v7.5 carregado!');
    Logger.info('   🔥 CORRIGIDO: URLs absolutas com /api/');
    Logger.info('   🔥 ADICIONADO: Helper buildApiUrl global');
    Logger.info('   🔥 MELHORADO: Estrutura modular do Pow');
    Logger.info('   🔥 OTIMIZADO: Cache e performance');
    Logger.info('   🔥 ADICIONADO: Logging estruturado');
    Logger.info('   🔥 CORRIGIDO: Tratamento de erros avançado');
    Logger.info('   🔥 NOVO: Sistema de inatividade (15 min)');
    Logger.info('   📢 Sistema de mensagens inteligentes integrado');
    Logger.info('   🔗 Integrado com auth.js, payment.js, dashboard.js');
    Logger.info('   ⏰ Use window.InactivityManager.getStatus() para ver status');

})();