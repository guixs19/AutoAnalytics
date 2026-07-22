// frontend/js/pow-client.js - VERSÃO COMPLETA v5.0
/**
 * 🔥 Proof of Work Client - Versão 5.0
 * 
 * ✅ ARQUITETURA MODULAR
 * ✅ INICIALIZAÇÃO AUTOMÁTICA
 * ✅ GESTÃO DE ESTADO ROBUSTA
 * ✅ CACHE INTELIGENTE COM TTL
 * ✅ RETRY AUTOMÁTICO COM BACKOFF
 * ✅ FALLBACK SÍNCRONO
 * ✅ DIAGNÓSTICO COMPLETO
 * ✅ TRATAMENTO DE ERROS AVANÇADO
 * 
 * CONECTADO COM: pow_routes.py (backend)
 * 
 * FLUXO:
 * 1. Inicialização automática → window.powClient disponível
 * 2. GET /api/pow/challenge → { challenge, difficulty, expires_in }
 * 3. Resolve SHA-256 com Web Worker (fallback síncrono)
 * 4. Upload com headers: X-PoW-Challenge, X-PoW-Nonce
 * 5. Validação no backend (validate_pow_request)
 */

// ==============================================
// 🔥 CONFIGURAÇÕES
// ==============================================

const POW_CONFIG = {
    // 🔥 Dificuldade e TTL
    DEFAULT_DIFFICULTY: 4,
    CHALLENGE_TTL: 300, // 5 minutos
    CACHE_TTL: 30000, // 30 segundos
    
    // 🔥 Retry e Timeout
    MAX_RETRIES: 3,
    RETRY_DELAY: 1000, // 1 segundo
    MAX_BACKOFF: 10000, // 10 segundos
    WORKER_TIMEOUT: 30000, // 30 segundos
    MAX_NONCE_ATTEMPTS: 1000000,
    
    // 🔥 Endpoints
    API_BASE: window.location.hostname.includes('localhost')
        ? 'http://localhost:8000/api'
        : '/api',
    CHALLENGE_ENDPOINT: '/pow/challenge',
    UPLOAD_ENDPOINT: '/upload-auto',
    
    // 🔥 Limites
    MAX_CHALLENGE_AGE: 300000, // 5 minutos
    MIN_DIFFICULTY: 3,
    MAX_DIFFICULTY: 6,
    
    // 🔥 Logging
    LOG_LEVEL: 'info', // debug, info, warn, error
    MAX_LOG_HISTORY: 100,
};

// ==============================================
// 🔥 UTILITÁRIOS
// ==============================================

const PowUtils = {
    sanitizeString: (str) => {
        if (!str) return '';
        if (typeof str !== 'string') str = String(str);
        
        const escapeMap = {
            '&': '&amp;', '<': '&lt;', '>': '&gt;',
            '"': '&quot;', "'": '&#39;', '`': '&#96;',
            '/': '&#47;', '=': '&#61;', '(': '&#40;',
            ')': '&#41;', ';': '&#59;', '\n': '\\n',
            '\r': '\\r', '\t': '\\t'
        };
        
        return str
            .replace(/[&<>"'`/=();\n\r\t]/g, m => escapeMap[m] || m)
            .slice(0, 1000);
    },

    sanitizeNumber: (value, defaultValue = 0) => {
        if (value === undefined || value === null) return defaultValue;
        const num = parseFloat(String(value).replace(/[^0-9.]/g, ''));
        return isNaN(num) ? defaultValue : num;
    },

    sleep: (ms) => new Promise(resolve => setTimeout(resolve, ms)),
    
    getToken: () => {
        try {
            const token = localStorage.getItem('access_token');
            if (!token || token === 'undefined' || token === 'null') return null;
            return PowUtils.sanitizeString(token);
        } catch (e) {
            return null;
        }
    },

    getRefreshToken: () => {
        try {
            const token = localStorage.getItem('refresh_token');
            if (!token || token === 'undefined' || token === 'null') return null;
            return PowUtils.sanitizeString(token);
        } catch (e) {
            return null;
        }
    },

    isAuthenticated: () => {
        const token = PowUtils.getToken();
        return token !== null && token.length > 10;
    },

    parseJson: async (response) => {
        try {
            const text = await response.text();
            return JSON.parse(text);
        } catch (e) {
            return null;
        }
    },

    // 🔥 Calcula tempo de backoff exponencial
    calculateBackoff: (attempt, baseDelay = 1000) => {
        return Math.min(baseDelay * Math.pow(2, attempt - 1), POW_CONFIG.MAX_BACKOFF);
    },

    // 🔥 Verifica se a resposta é JSON
    isJsonResponse: (response) => {
        const contentType = response.headers.get('content-type') || '';
        return contentType.includes('application/json');
    },

    // 🔥 Verifica se é uma página HTML (erro de proxy)
    isHtmlResponse: (text) => {
        return text.trim().startsWith('<');
    },

    // 🔥 Gera ID único
    generateId: () => {
        return Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
    }
};

// ==============================================
// 🔥 VALIDAÇÕES
// ==============================================

const PowValidators = {
    isValidChallenge: (challenge) => {
        if (!challenge || typeof challenge !== 'object') return false;
        
        // Campos obrigatórios
        if (!challenge.challenge || typeof challenge.challenge !== 'string') return false;
        if (challenge.challenge.length !== 32) return false;
        
        if (!challenge.difficulty || typeof challenge.difficulty !== 'number') return false;
        if (challenge.difficulty < POW_CONFIG.MIN_DIFFICULTY || 
            challenge.difficulty > POW_CONFIG.MAX_DIFFICULTY) return false;
        
        if (!challenge.expires_in || typeof challenge.expires_in !== 'number') return false;
        if (challenge.expires_in < 30 || challenge.expires_in > 600) return false;
        
        return true;
    },

    isValidSolution: (solution) => {
        if (!solution || typeof solution !== 'object') return false;
        
        if (!solution.nonce || typeof solution.nonce !== 'string') return false;
        if (solution.nonce.length === 0 || solution.nonce.length > 64) return false;
        
        if (!solution.prefix || typeof solution.prefix !== 'string') return false;
        if (solution.prefix.length !== 32) return false;
        
        if (!solution.complexity || typeof solution.complexity !== 'number') return false;
        if (solution.complexity < POW_CONFIG.MIN_DIFFICULTY || 
            solution.complexity > POW_CONFIG.MAX_DIFFICULTY) return false;
        
        return true;
    },

    isNonceValid: (nonce) => {
        return nonce && typeof nonce === 'string' && nonce.length > 0 && nonce.length <= 64;
    },

    isFileValid: (file) => {
        if (!file) return false;
        if (!file.name || typeof file.name !== 'string') return false;
        if (!file.size || typeof file.size !== 'number') return false;
        if (file.size <= 0) return false;
        return true;
    }
};

// ==============================================
// 🔥 LOGGER
// ==============================================

class PowLogger {
    constructor(level = 'info') {
        this.level = level;
        this.levels = { debug: 0, info: 1, warn: 2, error: 3 };
        this.history = [];
        this.maxHistory = POW_CONFIG.MAX_LOG_HISTORY;
        this.enabled = true;
        this.prefix = '[PoW Client]';
    }

    _shouldLog(level) {
        return this.enabled && this.levels[level] >= this.levels[this.level];
    }

    _formatMessage(level, message, args) {
        const timestamp = new Date().toISOString().substring(11, 19);
        let logMessage = `${timestamp} ${this.prefix} ${message}`;
        
        // Mantém histórico
        this.history.push({
            timestamp: Date.now(),
            level,
            message,
            args: args.length > 0 ? args : undefined
        });
        
        if (this.history.length > this.maxHistory) {
            this.history.shift();
        }
        
        return logMessage;
    }

    debug(message, ...args) {
        if (!this._shouldLog('debug')) return;
        const msg = this._formatMessage('debug', message, args);
        console.debug(msg, ...args);
    }

    info(message, ...args) {
        if (!this._shouldLog('info')) return;
        const msg = this._formatMessage('info', message, args);
        console.log(msg, ...args);
    }

    warn(message, ...args) {
        if (!this._shouldLog('warn')) return;
        const msg = this._formatMessage('warn', message, args);
        console.warn(msg, ...args);
    }

    error(message, ...args) {
        if (!this._shouldLog('error')) return;
        const msg = this._formatMessage('error', message, args);
        console.error(msg, ...args);
    }

    getHistory() {
        return this.history;
    }

    clearHistory() {
        this.history = [];
    }

    setLevel(level) {
        if (this.levels[level] !== undefined) {
            this.level = level;
        }
    }
}

// ==============================================
// 🔥 CLASSE PRINCIPAL - PowClient
// ==============================================

class PowClient {
    constructor(config = {}) {
        // ==========================================
        // 1. CONFIGURAÇÕES
        // ==========================================
        this.config = {
            ...POW_CONFIG,
            ...config,
        };

        // ==========================================
        // 2. LOGGER
        // ==========================================
        this.logger = new PowLogger(this.config.LOG_LEVEL);

        // ==========================================
        // 3. ESTADO
        // ==========================================
        this._state = {
            id: PowUtils.generateId(),
            isInitialized: false,
            isSolving: false,
            isReady: false,
            lastError: null,
            lastSuccess: null,
            createdAt: Date.now(),
        };

        // ==========================================
        // 4. CACHE
        // ==========================================
        this._cache = {
            solution: null,
            challenge: null,
            solvedAt: null,
            expiresAt: null,
            isValid: false,
        };

        // ==========================================
        // 5. MÉTRICAS
        // ==========================================
        this._metrics = {
            // Requisições
            totalRequests: 0,
            successfulRequests: 0,
            failedRequests: 0,
            
            // Desafios
            challengesRequested: 0,
            challengesReceived: 0,
            challengesFailed: 0,
            
            // Soluções
            solutionsCalculated: 0,
            solutionsCached: 0,
            solutionsUsed: 0,
            solutionsFailed: 0,
            
            // Tempos
            totalSolveTime: 0,
            avgSolveTime: 0,
            lastSolveTime: 0,
            maxSolveTime: 0,
            minSolveTime: Infinity,
            
            // Última resposta
            lastResponse: {
                status: null,
                contentType: null,
                preview: null,
                timestamp: null,
                duration: 0,
            },
            
            // Erros
            errorCount: 0,
            lastError: null,
            errorHistory: [],
        };

        // ==========================================
        // 6. SEGURANÇA
        // ==========================================
        this._security = {
            totalAttempts: 0,
            successfulAttempts: 0,
            failedAttempts: 0,
            lastFailure: null,
            lastSuccess: null,
            consecutiveFailures: 0,
            isLocked: false,
            lockUntil: null,
        };

        // ==========================================
        // 7. CONTROLE DE RETRY
        // ==========================================
        this._retry = {
            count: 0,
            maxRetries: this.config.MAX_RETRIES,
            baseDelay: this.config.RETRY_DELAY,
            backoff: 1,
        };

        // ==========================================
        // 8. WORKER
        // ==========================================
        this._worker = null;
        this._workerPromise = null;

        // ==========================================
        // 9. EVENT LISTENERS
        // ==========================================
        this._listeners = [];
        this._cleanupFunctions = [];

        // ==========================================
        // 10. INICIALIZAÇÃO
        // ==========================================
        this._init();
    }

    // ==============================================
    // 🔥 INICIALIZAÇÃO
    // ==============================================

    _init() {
        this.logger.info('🚀 PoW Client v5.0 inicializado');
        this.logger.info(`   📦 ID: ${this._state.id}`);
        this.logger.info(`   📦 Cache TTL: ${this.config.CACHE_TTL}ms`);
        this.logger.info(`   🔑 API: ${this.config.API_BASE}${this.config.CHALLENGE_ENDPOINT}`);
        this.logger.info(`   🔒 Modo: sob demanda (só no upload)`);
        
        this._state.isInitialized = true;
        this._setupEventListeners();
        
        this.logger.info('   🔍 Diagnóstico: ativo');
    }

    _setupEventListeners() {
        // 🔥 Escuta mudanças de autenticação
        const authHandler = () => {
            this._updateAuthStatus();
        };
        
        document.addEventListener('authLoginSuccess', authHandler);
        document.addEventListener('authLogout', authHandler);
        this._cleanupFunctions.push(() => {
            document.removeEventListener('authLoginSuccess', authHandler);
            document.removeEventListener('authLogout', authHandler);
        });

        // 🔥 Escuta eventos de visibilidade (pausar quando em background)
        const visibilityHandler = () => {
            if (document.hidden && this._state.isSolving) {
                this.logger.debug('⏸️ Página oculta, mantendo operação em background');
            }
        };
        
        document.addEventListener('visibilitychange', visibilityHandler);
        this._cleanupFunctions.push(() => {
            document.removeEventListener('visibilitychange', visibilityHandler);
        });

        // 🔥 Escuta antes de fechar a página
        const beforeUnloadHandler = () => {
            this._cleanup();
        };
        
        window.addEventListener('beforeunload', beforeUnloadHandler);
        this._cleanupFunctions.push(() => {
            window.removeEventListener('beforeunload', beforeUnloadHandler);
        });
    }

    // ==============================================
    // 🔥 MÉTODOS PÚBLICOS
    // ==============================================

    /**
     * Prepara uma solução PoW em background
     * Chamado quando o usuário arrasta ou seleciona um arquivo
     * 
     * @returns {Promise<boolean>} - True se preparado com sucesso
     */
    async prepareForUpload() {
        this.logger.debug('🔄 Preparando PoW para upload...');
        
        // 1. Verificar autenticação
        if (!this._isAuthenticated()) {
            this.logger.warn('⏳ PoW: aguardando autenticação...');
            this._state.lastError = 'Usuário não autenticado';
            return false;
        }

        // 2. Verificar se está bloqueado
        if (this._isLocked()) {
            this.logger.warn('⛔ PoW bloqueado temporariamente');
            return false;
        }

        // 3. Verificar cache válido
        if (this._hasValidCache()) {
            this.logger.info('⚡ PoW em cache (válido)');
            this._metrics.solutionsCached++;
            return true;
        }

        // 4. Se já está calculando, aguarda
        if (this._state.isSolving) {
            this.logger.debug('⏳ PoW já está sendo calculado...');
            return await this._waitForSolving();
        }

        // 5. Calcular nova solução
        return await this._calculateSolution();
    }

    /**
     * Obtém a solução PoW para o upload
     * Se não tiver em cache, calcula na hora
     * 
     * @returns {Promise<Object>} - Solução PoW
     * @throws {Error} - Se não for possível obter solução
     */
    async getSolutionForUpload() {
        this.logger.debug('🔑 Obtendo solução PoW para upload...');
        
        // 1. Verificar autenticação
        if (!this._isAuthenticated()) {
            throw new Error('Usuário não autenticado');
        }

        // 2. Verificar bloqueio
        if (this._isLocked()) {
            throw new Error('PoW bloqueado temporariamente. Tente novamente em alguns segundos.');
        }

        // 3. Usar cache se disponível e válido
        if (this._hasValidCache() && this._cache.solution) {
            const solution = { ...this._cache.solution };
            this._cache.solution = null;
            this._cache.isValid = false;
            this._metrics.solutionsUsed++;
            this.logger.info(`⚡ Usando PoW em cache (difficulty: ${solution.complexity})`);
            return solution;
        }

        // 4. Se está calculando, aguarda
        if (this._state.isSolving) {
            this.logger.debug('⏳ Aguardando cálculo do PoW...');
            const result = await this._waitForSolving();
            if (result && this._cache.solution) {
                const solution = { ...this._cache.solution };
                this._cache.solution = null;
                this._cache.isValid = false;
                this._metrics.solutionsUsed++;
                return solution;
            }
        }

        // 5. Calcular sob demanda
        return await this._calculateSolution(true);
    }

    /**
     * Upload com PoW - ALINHADO COM pow_routes.py
     * 
     * @param {File|File[]} files - Arquivo(s) para upload
     * @param {string} endpoint - Endpoint de upload
     * @param {Object} options - Opções adicionais
     * @returns {Promise<Object>} - Resposta do servidor
     */
    async uploadWithPow(files, endpoint = this.config.UPLOAD_ENDPOINT, options = {}) {
        const fileArray = Array.isArray(files) ? files : [files];
        
        this.logger.info(`📤 Iniciando upload com PoW: ${fileArray.length} arquivo(s)`);

        // 1. Validar arquivos
        for (const file of fileArray) {
            if (!PowValidators.isFileValid(file)) {
                throw new Error(`Arquivo inválido: ${file?.name || 'desconhecido'}`);
            }
        }

        // 2. Verificar autenticação
        if (!this._isAuthenticated()) {
            throw new Error('Usuário não autenticado');
        }

        // 3. Obter solução PoW
        let solution;
        try {
            solution = await this.getSolutionForUpload();
        } catch (error) {
            this.logger.error('❌ Falha ao obter solução PoW:', error);
            throw new Error(`PoW falhou: ${error.message}`);
        }

        if (!PowValidators.isValidSolution(solution)) {
            throw new Error('Solução PoW inválida');
        }

        // 4. Preparar FormData
        const formData = new FormData();
        for (const file of fileArray) {
            const safeFilename = PowUtils.sanitizeString(file.name);
            formData.append('files', file, safeFilename);
        }
        formData.append('analysis_type', options.analysis_type || 'auto');
        formData.append('ai_model', options.ai_model || 'auto');

        // 5. Obter token
        const token = PowUtils.getToken();
        if (!token) {
            throw new Error('Token de autenticação não encontrado');
        }

        // 6. Fazer upload com retry
        return await this._uploadWithRetry(formData, token, solution, endpoint);
    }

    /**
     * Reseta o estado do cliente
     */
    reset() {
        this._cache.solution = null;
        this._cache.challenge = null;
        this._cache.solvedAt = null;
        this._cache.expiresAt = null;
        this._cache.isValid = false;
        
        this._state.isSolving = false;
        this._state.lastError = null;
        this._state.isReady = false;
        
        this._retry.count = 0;
        this._retry.backoff = 1;
        
        this._cleanupWorker();
        
        this.logger.info('🔄 PoW resetado');
    }

    /**
     * Obtém estatísticas do cliente
     * 
     * @returns {Object} - Estatísticas
     */
    getStats() {
        return {
            state: {
                id: this._state.id,
                isInitialized: this._state.isInitialized,
                isSolving: this._state.isSolving,
                isReady: this._state.isReady,
                isAuthenticated: this._state.isAuthenticated,
                lastError: this._state.lastError,
                lastSuccess: this._state.lastSuccess,
                age: Date.now() - this._state.createdAt,
            },
            cache: {
                hasSolution: this._cache.solution !== null,
                hasChallenge: this._cache.challenge !== null,
                age: this._cache.solvedAt ? Date.now() - this._cache.solvedAt : null,
                isValid: this._cache.isValid,
            },
            metrics: this._metrics,
            security: this._security,
            config: {
                cacheTTL: this.config.CACHE_TTL,
                maxRetries: this.config.MAX_RETRIES,
                workerTimeout: this.config.WORKER_TIMEOUT,
                defaultDifficulty: this.config.DEFAULT_DIFFICULTY,
            }
        };
    }

    /**
     * Obtém diagnóstico detalhado
     * 
     * @returns {Object} - Diagnóstico
     */
    getDiagnostics() {
        return {
            ...this.getStats(),
            config: this.config,
            apiBase: this.config.API_BASE,
            challengeEndpoint: this.config.CHALLENGE_ENDPOINT,
            uploadEndpoint: this.config.UPLOAD_ENDPOINT,
            workerAvailable: this._isWorkerAvailable(),
            logHistory: this.logger.getHistory().slice(-10),
            timestamp: new Date().toISOString(),
            uptime: this._state.isInitialized ? Date.now() - this._state.createdAt : null,
        };
    }

    // ==============================================
    // 🔥 MÉTODOS INTERNOS
    // ==============================================

    /**
     * Verifica autenticação
     */
    _isAuthenticated() {
        this._updateAuthStatus();
        return this._state.isAuthenticated;
    }

    /**
     * Atualiza status de autenticação
     */
    _updateAuthStatus() {
        this._state.isAuthenticated = PowUtils.isAuthenticated();
        return this._state.isAuthenticated;
    }

    /**
     * Verifica se está bloqueado
     */
    _isLocked() {
        if (!this._security.isLocked) return false;
        if (this._security.lockUntil && Date.now() > this._security.lockUntil) {
            this._security.isLocked = false;
            this._security.lockUntil = null;
            return false;
        }
        return true;
    }

    /**
     * Bloqueia temporariamente
     */
    _lock(duration = 5000) {
        this._security.isLocked = true;
        this._security.lockUntil = Date.now() + duration;
        this.logger.warn(`🔒 PoW bloqueado por ${duration}ms`);
    }

    /**
     * Verifica se o cache é válido
     */
    _hasValidCache() {
        if (!this._cache.solution) return false;
        if (!this._cache.solvedAt) return false;
        if (!this._cache.isValid) return false;
        
        const age = Date.now() - this._cache.solvedAt;
        const isValid = age < this.config.CACHE_TTL;
        
        if (!isValid) {
            this.logger.debug(`⏳ Cache expirado (${age}ms > ${this.config.CACHE_TTL}ms)`);
            this._cache.solution = null;
            this._cache.challenge = null;
            this._cache.solvedAt = null;
            this._cache.isValid = false;
        }
        
        return isValid;
    }

    /**
     * Aguarda o fim do cálculo
     */
    async _waitForSolving(timeout = 30000) {
        const start = Date.now();
        while (this._state.isSolving && (Date.now() - start) < timeout) {
            await PowUtils.sleep(100);
        }
        
        if (this._state.isSolving) {
            this.logger.warn('⏰ Timeout aguardando cálculo do PoW');
            this._state.isSolving = false;
            return false;
        }
        
        return this._cache.solution !== null && this._cache.isValid;
    }

    /**
     * Calcula uma solução PoW
     */
    async _calculateSolution(force = false) {
        if (this._state.isSolving && !force) {
            return await this._waitForSolving();
        }

        this._state.isSolving = true;
        this.logger.info('🔄 Calculando PoW...');

        try {
            // 1. Obter desafio
            const challenge = await this._getChallenge();
            if (!challenge) {
                this._state.isSolving = false;
                return false;
            }

            // 2. Resolver desafio
            const solution = await this._solveChallenge(challenge);
            
            // 3. Validar e armazenar solução
            if (solution && PowValidators.isValidSolution(solution)) {
                this._cache.solution = {
                    ...solution,
                    solvedAt: Date.now(),
                    expiresAt: Date.now() + this.config.CACHE_TTL,
                };
                this._cache.challenge = challenge;
                this._cache.solvedAt = Date.now();
                this._cache.isValid = true;
                
                this._metrics.solutionsCalculated++;
                this._state.lastSuccess = Date.now();
                this._state.isReady = true;
                
                this.logger.info(`✅ PoW pronto (difficulty: ${solution.complexity}, time: ${solution.timeMs || '?'}ms)`);
                this._state.isSolving = false;
                return true;
            }

            this._state.isSolving = false;
            this._state.lastError = 'Solução inválida';
            this.logger.warn('⚠️ Solução inválida');
            return false;

        } catch (error) {
            this._handleError(error, '_calculateSolution');
            this._state.isSolving = false;
            return false;
        }
    }

    /**
     * Obtém desafio do backend
     */
    async _getChallenge() {
        this.logger.debug('📡 Solicitando desafio PoW ao backend...');
        this._metrics.totalRequests++;
        this._metrics.challengesRequested++;

        const token = PowUtils.getToken();
        if (!token) {
            throw new Error('Não autenticado');
        }

        const startTime = Date.now();

        try {
            const response = await fetch(
                `${this.config.API_BASE}${this.config.CHALLENGE_ENDPOINT}`,
                {
                    method: 'GET',
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Cache-Control': 'no-cache',
                        'Accept': 'application/json',
                    },
                    credentials: 'include',
                }
            );

            // 🔥 Registrar resposta
            const duration = Date.now() - startTime;
            const contentType = response.headers.get('content-type') || '';
            this._metrics.lastResponse.status = response.status;
            this._metrics.lastResponse.contentType = contentType;
            this._metrics.lastResponse.timestamp = Date.now();
            this._metrics.lastResponse.duration = duration;

            this.logger.debug(`📡 Resposta: status=${response.status}, contentType=${contentType}, duration=${duration}ms`);

            // 🔥 Tratar erros HTTP
            if (response.status === 401) {
                this._handleAuthError();
                throw new Error('Sessão expirada. Faça login novamente.');
            }

            if (response.status === 429) {
                const data = await PowUtils.parseJson(response);
                const retryAfter = data?.retry_after || 60;
                this._lock(retryAfter * 1000);
                throw new Error(`Rate limit: ${data?.detail || 'Muitas requisições'}`);
            }

            if (response.status === 404) {
                throw new Error('Serviço PoW indisponível. Verifique o backend.');
            }

            if (!response.ok) {
                const data = await PowUtils.parseJson(response);
                throw new Error(data?.detail || `HTTP ${response.status}`);
            }

            // 🔥 Verificar se é JSON
            if (!PowUtils.isJsonResponse(response)) {
                const text = await response.text();
                const preview = text.substring(0, 200);
                this._metrics.lastResponse.preview = preview;
                
                if (PowUtils.isHtmlResponse(text)) {
                    throw new Error('Servidor retornou HTML. Verifique o proxy/reverse proxy.');
                }
                throw new Error(`Resposta não é JSON: ${preview}...`);
            }

            // 🔥 Parsear JSON
            const data = await PowUtils.parseJson(response);
            if (!data) {
                throw new Error('JSON inválido recebido');
            }

            // 🔥 Validar desafio
            if (!PowValidators.isValidChallenge(data)) {
                this.logger.error('❌ Desafio inválido:', data);
                throw new Error('Desafio inválido recebido do servidor');
            }

            // ✅ Sucesso
            this._metrics.successfulRequests++;
            this._metrics.challengesReceived++;
            this._security.successfulAttempts++;
            this._security.consecutiveFailures = 0;

            this.logger.info(`✅ Desafio recebido (difficulty: ${data.difficulty}, expires: ${data.expires_in}s)`);
            return data;

        } catch (error) {
            this._metrics.failedRequests++;
            this._metrics.challengesFailed++;
            this._security.failedAttempts++;
            this._security.consecutiveFailures++;
            this._security.lastFailure = Date.now();

            this.logger.error('❌ Erro ao obter desafio:', error.message);
            throw error;
        }
    }

    /**
     * Resolve o desafio usando Web Worker
     */
    async _solveChallenge(challenge) {
        this.logger.info(`🔐 Resolvendo PoW (difficulty: ${challenge.difficulty})...`);
        const startTime = Date.now();

        try {
            // 1. Tentar com Web Worker
            if (this._isWorkerAvailable()) {
                const result = await this._solveWithWorker(challenge);
                if (result) {
                    this._updateSolveMetrics(startTime);
                    this.logger.info(`✅ PoW resolvido com Worker em ${Date.now() - startTime}ms`);
                    return result;
                }
            }

            // 2. Fallback: Síncrono
            this.logger.warn('⚠️ Worker não disponível, usando fallback síncrono...');
            const result = await this._solveSync(challenge);
            this._updateSolveMetrics(startTime);
            this.logger.info(`✅ PoW resolvido (sync) em ${Date.now() - startTime}ms`);
            return result;

        } catch (error) {
            this.logger.error('❌ Erro ao resolver PoW:', error);
            throw error;
        }
    }

    /**
     * Resolve com Web Worker
     */
    _solveWithWorker(challenge) {
        return new Promise((resolve, reject) => {
            try {
                // Criar worker
                const worker = new Worker('/js/pow-worker.js');
                this._worker = worker;

                // Timeout
                const timeoutId = setTimeout(() => {
                    worker.terminate();
                    this._worker = null;
                    reject(new Error(`Timeout ao resolver PoW (${this.config.WORKER_TIMEOUT}ms)`));
                }, this.config.WORKER_TIMEOUT);

                // Postar mensagem
                worker.postMessage({
                    prefix: challenge.challenge,
                    complexity: challenge.difficulty,
                    timestamp: challenge.timestamp || Date.now(),
                    expires_in: challenge.expires_in || this.config.CHALLENGE_TTL,
                });

                // Receber resposta
                worker.onmessage = (e) => {
                    clearTimeout(timeoutId);
                    const data = e.data;

                    if (data.error) {
                        worker.terminate();
                        this._worker = null;
                        reject(new Error(data.error));
                        return;
                    }

                    if (!PowValidators.isNonceValid(data.nonce)) {
                        worker.terminate();
                        this._worker = null;
                        reject(new Error('Nonce inválido recebido do worker'));
                        return;
                    }

                    const solution = {
                        nonce: PowUtils.sanitizeString(data.nonce),
                        prefix: challenge.challenge,
                        complexity: challenge.difficulty,
                        solvedAt: Date.now(),
                        timeMs: data.timeMs || 0,
                        worker: true,
                    };

                    // Verificar se a solução é válida
                    if (!PowValidators.isValidSolution(solution)) {
                        worker.terminate();
                        this._worker = null;
                        reject(new Error('Solução não atende à dificuldade exigida'));
                        return;
                    }

                    worker.terminate();
                    this._worker = null;
                    resolve(solution);
                };

                worker.onerror = (error) => {
                    clearTimeout(timeoutId);
                    worker.terminate();
                    this._worker = null;
                    reject(new Error(`Worker error: ${error.message || 'desconhecido'}`));
                };

            } catch (error) {
                this._worker = null;
                reject(new Error(`Erro ao criar worker: ${error.message}`));
            }
        });
    }

    /**
     * Fallback síncrono para resolver PoW
     */
    async _solveSync(challenge) {
        // 🔥 Verificar se temos crypto.subtle disponível
        if (!crypto.subtle) {
            throw new Error('Web Crypto API não disponível. Use um navegador moderno.');
        }

        const prefix = challenge.challenge;
        const complexity = challenge.difficulty;
        const target = '0'.repeat(complexity);
        const maxAttempts = this.config.MAX_NONCE_ATTEMPTS;

        const encoder = new TextEncoder();
        let nonce = 0;

        this.logger.debug(`🔐 Tentando encontrar nonce (max: ${maxAttempts})...`);

        while (nonce < maxAttempts) {
            // Verificar se foi cancelado
            if (this._state.isSolving === false) {
                throw new Error('Cálculo cancelado');
            }

            const data = `${prefix}:${nonce}`;
            const encoded = encoder.encode(data);

            try {
                const hashBuffer = await crypto.subtle.digest('SHA-256', encoded);
                const hashArray = Array.from(new Uint8Array(hashBuffer));
                const hashHex = hashArray
                    .map(b => b.toString(16).padStart(2, '0'))
                    .join('');

                if (hashHex.startsWith(target)) {
                    this.logger.debug(`✅ Nonce encontrado: ${nonce}`);
                    return {
                        nonce: String(nonce),
                        prefix: prefix,
                        complexity: complexity,
                        solvedAt: Date.now(),
                        timeMs: 0,
                        sync: true,
                    };
                }
            } catch (e) {
                // Ignorar erro e continuar
            }

            nonce++;

            // Progresso a cada 1000 tentativas
            if (nonce % 1000 === 0) {
                this.logger.debug(`🔐 Tentativas: ${nonce}/${maxAttempts}`);
            }
        }

        throw new Error(`Não foi possível encontrar nonce após ${maxAttempts} tentativas`);
    }

    /**
     * Atualiza métricas de solução
     */
    _updateSolveMetrics(startTime) {
        const timeMs = Date.now() - startTime;
        this._metrics.lastSolveTime = timeMs;
        this._metrics.totalSolveTime += timeMs;
        
        if (this._metrics.solutionsCalculated > 0) {
            this._metrics.avgSolveTime = this._metrics.totalSolveTime / 
                (this._metrics.solutionsCalculated + 1);
        }
        
        if (timeMs > this._metrics.maxSolveTime) {
            this._metrics.maxSolveTime = timeMs;
        }
        if (timeMs < this._metrics.minSolveTime) {
            this._metrics.minSolveTime = timeMs;
        }
    }

    /**
     * Upload com retry automático
     */
    async _uploadWithRetry(formData, token, solution, endpoint) {
        const maxRetries = this.config.MAX_RETRIES;
        let lastError = null;
        let attempt = 0;

        while (attempt < maxRetries) {
            attempt++;
            const backoff = PowUtils.calculateBackoff(attempt);
            
            try {
                this.logger.debug(`📤 Tentativa ${attempt}/${maxRetries}`);

                const response = await fetch(
                    `${this.config.API_BASE}${endpoint}`,
                    {
                        method: 'POST',
                        headers: {
                            'X-PoW-Challenge': solution.prefix,
                            'X-PoW-Nonce': solution.nonce,
                            'Authorization': `Bearer ${token}`,
                            'Accept': 'application/json',
                        },
                        body: formData,
                        credentials: 'include',
                    }
                );

                // 🔥 PoW expirado (428)
                if (response.status === 428) {
                    this.logger.warn('⚠️ PoW expirado (428), recalculando...');
                    this.reset();
                    
                    const newSolution = await this.getSolutionForUpload();
                    if (!newSolution) {
                        throw new Error('Não foi possível obter nova solução PoW');
                    }

                    // Tentar novamente com nova solução
                    const retryResponse = await fetch(
                        `${this.config.API_BASE}${endpoint}`,
                        {
                            method: 'POST',
                            headers: {
                                'X-PoW-Challenge': newSolution.prefix,
                                'X-PoW-Nonce': newSolution.nonce,
                                'Authorization': `Bearer ${token}`,
                                'Accept': 'application/json',
                            },
                            body: formData,
                            credentials: 'include',
                        }
                    );

                    if (retryResponse.status === 428) {
                        throw new Error('PoW expirado novamente. Tente novamente.');
                    }

                    if (!retryResponse.ok) {
                        const errorData = await PowUtils.parseJson(retryResponse);
                        throw new Error(errorData?.detail || `HTTP ${retryResponse.status}`);
                    }

                    const data = await retryResponse.json();
                    this.logger.info('✅ Upload com PoW (retry) concluído');
                    return data;
                }

                // 🔥 Token expirado (401)
                if (response.status === 401) {
                    this.logger.warn('⚠️ Token expirado, tentando refresh...');
                    const refreshed = await this._refreshToken();

                    if (refreshed) {
                        const newToken = PowUtils.getToken();
                        const retryResponse = await fetch(
                            `${this.config.API_BASE}${endpoint}`,
                            {
                                method: 'POST',
                                headers: {
                                    'X-PoW-Challenge': solution.prefix,
                                    'X-PoW-Nonce': solution.nonce,
                                    'Authorization': `Bearer ${newToken}`,
                                    'Accept': 'application/json',
                                },
                                body: formData,
                                credentials: 'include',
                            }
                        );

                        if (retryResponse.ok) {
                            const data = await retryResponse.json();
                            this.logger.info('✅ Upload com novo token concluído');
                            return data;
                        }
                    }

                    throw new Error('Sessão expirada. Faça login novamente.');
                }

                // 🔥 Rate limit (429)
                if (response.status === 429) {
                    const data = await PowUtils.parseJson(response);
                    const retryAfter = data?.retry_after || 60;
                    this.logger.warn(`⚠️ Rate limit, aguardando ${retryAfter}s...`);
                    await PowUtils.sleep(retryAfter * 1000);
                    continue;
                }

                // 🔥 Sucesso (2xx)
                if (response.ok) {
                    const data = await response.json();
                    this.logger.info('✅ Upload com PoW concluído');
                    return data;
                }

                // 🔥 Outros erros
                const errorData = await PowUtils.parseJson(response);
                throw new Error(errorData?.detail || `HTTP ${response.status}: ${response.statusText}`);

            } catch (error) {
                lastError = error;
                this.logger.error(`❌ Tentativa ${attempt} falhou:`, error.message);

                if (attempt < maxRetries) {
                    this.logger.debug(`⏳ Aguardando ${backoff}ms antes de tentar novamente...`);
                    await PowUtils.sleep(backoff);
                }
            }
        }

        throw new Error(`Upload falhou após ${maxRetries} tentativas: ${lastError?.message || 'Erro desconhecido'}`);
    }

    /**
     * Tenta refresh do token
     */
    async _refreshToken() {
        try {
            const refreshToken = PowUtils.getRefreshToken();
            if (!refreshToken) return false;

            const response = await fetch('/api/auth/refresh', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: refreshToken }),
                credentials: 'include',
            });

            if (!response.ok) return false;

            const data = await response.json();
            if (data.access_token) {
                localStorage.setItem('access_token', data.access_token);
                if (data.refresh_token) {
                    localStorage.setItem('refresh_token', data.refresh_token);
                }
                return true;
            }

            return false;
        } catch (e) {
            return false;
        }
    }

    /**
     * Verifica se o Worker está disponível
     */
    _isWorkerAvailable() {
        try {
            return typeof Worker !== 'undefined';
        } catch (e) {
            return false;
        }
    }

    /**
     * Limpa o worker
     */
    _cleanupWorker() {
        if (this._worker) {
            try {
                this._worker.terminate();
            } catch (e) {
                // Ignorar
            }
            this._worker = null;
            this._workerPromise = null;
        }
    }

    /**
     * Trata erro de autenticação
     */
    _handleAuthError() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        
        this._state.isAuthenticated = false;
        this._state.lastError = 'Token expirado';
        
        window.dispatchEvent(new CustomEvent('auth:expired', {
            detail: { message: 'Sessão expirada' }
        }));
    }

    /**
     * Trata erros de forma consistente
     */
    _handleError(error, context) {
        const errorMsg = error.message || String(error);
        this._state.lastError = errorMsg;
        this._metrics.errorCount++;
        this._metrics.lastError = {
            message: errorMsg,
            context: context,
            timestamp: Date.now(),
        };

        this._metrics.errorHistory.push({
            message: errorMsg,
            context: context,
            timestamp: Date.now(),
        });

        if (this._metrics.errorHistory.length > 10) {
            this._metrics.errorHistory.shift();
        }

        this.logger.error(`❌ [${context}] ${errorMsg}`);
    }

    /**
     * Limpeza geral
     */
    _cleanup() {
        this._cleanupWorker();
        this._cleanupFunctions.forEach(fn => {
            try {
                fn();
            } catch (e) {
                // Ignorar
            }
        });
        this._cleanupFunctions = [];
    }

    /**
     * Destroi o cliente
     */
    destroy() {
        this._cleanup();
        this._state.isInitialized = false;
        this.logger.info('🗑️ PoW Client destruído');
    }
}

// ==============================================
// 🔥 INSTÂNCIA GLOBAL - INICIALIZAÇÃO AUTOMÁTICA
// ==============================================

// 🔥 Cria a instância imediatamente
const powClientInstance = new PowClient();
powClientInstance._state._initTime = Date.now();

// 🔥 Expor globalmente com todos os nomes esperados
if (typeof window !== 'undefined') {
    // Nome principal
    window.powClient = powClientInstance;
    
    // 🔥 Alias esperados pelo PowManager do dashboard
    window.Pow = powClientInstance;
    window.PowClient = powClientInstance;
    window.PowClientInstance = powClientInstance;
    
    // 🔥 Função de inicialização (garantida)
    window.initPowClient = function(options = {}) {
        if (options.logLevel) {
            powClientInstance.logger.setLevel(options.logLevel);
        }
        
        if (!powClientInstance._isAuthenticated()) {
            console.log('⏳ PoW: aguardando autenticação...');
            return powClientInstance;
        }
        
        console.log('✅ PoW Client inicializado (modo sob demanda)');
        console.log(`   🔍 Use window.powClient.getDiagnostics() para debug`);
        console.log(`   📊 Use window.powClient.getStats() para estatísticas`);
        
        return powClientInstance;
    };
    
    // 🔥 Função para parar
    window.stopPowClient = function() {
        powClientInstance.reset();
        powClientInstance._state.isInitialized = false;
        console.log('⏹️ PoW Client parado');
    };
    
    // 🔥 Funções de diagnóstico
    window.getPowDiagnostics = function() {
        return powClientInstance.getDiagnostics();
    };
    
    window.getPowStats = function() {
        return powClientInstance.getStats();
    };
    
    console.log('✅ PoW Client v5.0 global disponível');
    console.log('   🔍 Use window.powClient.getDiagnostics() para debug');
    console.log('   📊 Use window.powClient.getStats() para estatísticas');
    console.log('   📡 window.powClient, window.Pow e window.PowClient disponíveis');
}

console.log('=' .repeat(60));
console.log('🔥 pow-client.js v5.0 carregado');
console.log('   ✅ Inicialização automática (instância global)');
console.log('   ✅ Arquitetura modular e organizada');
console.log('   ✅ Cache inteligente com TTL');
console.log('   ✅ Retry automático com backoff exponencial');
console.log('   ✅ Fallback síncrono (quando worker falha)');
console.log('   ✅ Tratamento de erros robusto');
console.log('   ✅ Métricas e diagnóstico detalhados');
console.log('   ✅ Logging estruturado');
console.log('   📡 window.powClient disponível imediatamente');
console.log('   🔍 Use window.getPowDiagnostics() para debug');
console.log('=' .repeat(60));

// ==============================================
// 🔥 EXPORTAÇÕES
// ==============================================

export { 
    PowClient, 
    powClientInstance, 
    PowUtils, 
    PowValidators, 
    PowLogger,
    POW_CONFIG 
};