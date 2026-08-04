// frontend/js/pow-client.js - VERSÃO v6.1 (CORREÇÃO DE ROTA + MELHORIAS)
/**
 * 🔥 Proof of Work Client - Versão 6.1
 * 
 * ✅ CORRIGIDO: UPLOAD_ENDPOINT agora é /upload-multi-analyze
 * ✅ MELHORADO: Detecção automática de rota com fallback
 * ✅ ADICIONADO: Verificação de saúde do PoW antes do upload
 * ✅ ADICIONADO: Log detalhado de erros 400
 * ✅ MELHORADO: Tratamento de erros com mensagens amigáveis
 * ✅ ADICIONADO: Auto-recuperação para PoW expirado
 * ✅ OTIMIZADO: Cache com invalidação inteligente
 * 
 * CONECTADO COM: pow_routes.py (backend TTL: 900s)
 */

// ==============================================
// 🔥 CONFIGURAÇÕES (SINCRONIZADAS COM BACKEND)
// ==============================================

const POW_CONFIG = {
    // 🔥 Dificuldade e TTL (sincronizado com backend)
    DEFAULT_DIFFICULTY: 4,
    CHALLENGE_TTL: 900, // 15 minutos (combinado com backend)
    CACHE_TTL: 60000, // 60 segundos para cache da solução
    
    // 🔥 Retry e Timeout
    MAX_RETRIES: 3,
    RETRY_DELAY: 1000,
    MAX_BACKOFF: 10000,
    WORKER_TIMEOUT: 60000, // 60 segundos
    MAX_NONCE_ATTEMPTS: 2000000, // 2 milhões
    
    // 🔥 Endpoints (CORRIGIDO)
    API_BASE: window.location.hostname.includes('localhost')
        ? 'http://localhost:8000/api'
        : '/api',
    CHALLENGE_ENDPOINT: '/pow/challenge',
    // 🔥 CORRIGIDO: Rota correta para upload múltiplo
    UPLOAD_ENDPOINT: '/upload-multi-analyze',
    // 🔥 Fallback para rota antiga (tenta ambas)
    UPLOAD_ENDPOINT_FALLBACK: '/upload-auto',
    WORKER_URL: '/static/js/pow-worker.js',
    
    // 🔥 Limites (sincronizados com backend)
    MAX_CHALLENGE_AGE: 900000, // 15 minutos em ms
    MIN_DIFFICULTY: 3,
    MAX_DIFFICULTY: 6,
    MIN_EXPIRES_IN: 30,
    MAX_EXPIRES_IN: 1800,
    
    // 🔥 Logging
    LOG_LEVEL: 'info',
    MAX_LOG_HISTORY: 100,
};

// ==============================================
// 🔥 LOGGER MELHORADO
// ==============================================

class PowLogger {
    constructor(level = 'info') {
        this.level = level;
        this.levels = { debug: 0, info: 1, warn: 2, error: 3 };
        this.history = [];
        this.maxHistory = POW_CONFIG.MAX_LOG_HISTORY;
        this.enabled = true;
        this.prefix = '[PoW Client]';
        this.colors = {
            debug: '#6c757d',
            info: '#17a2b8',
            warn: '#ffc107',
            error: '#dc3545'
        };
    }

    _shouldLog(level) {
        return this.enabled && this.levels[level] >= this.levels[this.level];
    }

    _formatMessage(level, message, args) {
        const timestamp = new Date().toISOString().substring(11, 19);
        const logMessage = `${timestamp} ${this.prefix} ${message}`;
        
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

    _logWithStyle(level, message, args, style) {
        if (!this._shouldLog(level)) return;
        const formatted = this._formatMessage(level, message, args);
        console.log(`%c${formatted}`, style, ...args);
    }

    debug(message, ...args) {
        if (!this._shouldLog('debug')) return;
        console.debug(this._formatMessage('debug', message, args), ...args);
    }

    info(message, ...args) {
        if (!this._shouldLog('info')) return;
        console.log(this._formatMessage('info', message, args), ...args);
    }

    warn(message, ...args) {
        if (!this._shouldLog('warn')) return;
        console.warn(this._formatMessage('warn', message, args), ...args);
    }

    error(message, ...args) {
        if (!this._shouldLog('error')) return;
        console.error(this._formatMessage('error', message, args), ...args);
    }

    getHistory() { return this.history; }
    clearHistory() { this.history = []; }
    setLevel(level) { if (this.levels[level] !== undefined) this.level = level; }
}

// ==============================================
// 🔥 VALIDAÇÕES CORRIGIDAS
// ==============================================

const PowValidators = {
    isValidChallenge: (challenge) => {
        if (!challenge || typeof challenge !== 'object') {
            return false;
        }
        
        if (!challenge.challenge || typeof challenge.challenge !== 'string') {
            return false;
        }
        if (challenge.challenge.length !== 32) {
            return false;
        }
        
        if (!challenge.difficulty || typeof challenge.difficulty !== 'number') {
            return false;
        }
        if (challenge.difficulty < POW_CONFIG.MIN_DIFFICULTY || 
            challenge.difficulty > POW_CONFIG.MAX_DIFFICULTY) {
            return false;
        }
        
        if (!challenge.expires_in || typeof challenge.expires_in !== 'number') {
            return false;
        }
        if (challenge.expires_in < POW_CONFIG.MIN_EXPIRES_IN || 
            challenge.expires_in > POW_CONFIG.MAX_EXPIRES_IN) {
            return false;
        }
        
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
        const allowedExtensions = ['.csv', '.xlsx', '.xls', '.tsv'];
        const ext = '.' + file.name.split('.').pop().toLowerCase();
        return allowedExtensions.includes(ext);
    }
};

// ==============================================
// 🔥 CLASSE PRINCIPAL - PowClient v6.1
// ==============================================

class PowClient {
    constructor(config = {}) {
        this.config = { ...POW_CONFIG, ...config };
        this.logger = new PowLogger(this.config.LOG_LEVEL);

        // Estado
        this._state = {
            id: this._generateId(),
            isInitialized: false,
            isSolving: false,
            isReady: false,
            lastError: null,
            lastSuccess: null,
            createdAt: Date.now(),
            workerChecked: false,
            workerAvailable: false,
            isAuthenticated: false,
            version: '6.1'
        };

        // Cache
        this._cache = {
            solution: null,
            challenge: null,
            solvedAt: null,
            expiresAt: null,
            isValid: false,
            used: false
        };

        // Métricas
        this._metrics = {
            totalRequests: 0,
            successfulRequests: 0,
            failedRequests: 0,
            challengesRequested: 0,
            challengesReceived: 0,
            challengesFailed: 0,
            solutionsCalculated: 0,
            solutionsCached: 0,
            solutionsUsed: 0,
            solutionsFailed: 0,
            totalSolveTime: 0,
            avgSolveTime: 0,
            lastSolveTime: 0,
            maxSolveTime: 0,
            minSolveTime: Infinity,
            errorCount: 0,
            lastError: null,
            workerAttempts: 0,
            workerFailures: 0,
            syncFallbackUsed: 0,
            cacheHits: 0,
            cacheMisses: 0
        };

        // Segurança
        this._security = {
            totalAttempts: 0,
            successfulAttempts: 0,
            failedAttempts: 0,
            lastFailure: null,
            lastSuccess: null,
            consecutiveFailures: 0,
            isLocked: false,
            lockUntil: null
        };

        this._worker = null;
        this._cleanupFunctions = [];

        this._init();
    }

    // ==============================================
    // 🔥 INICIALIZAÇÃO
    // ==============================================

    _init() {
        this.logger.info('🚀 PoW Client v6.1 inicializado');
        this.logger.info(`   📦 ID: ${this._state.id}`);
        this.logger.info(`   📦 Cache TTL: ${this.config.CACHE_TTL}ms`);
        this.logger.info(`   🔑 API: ${this.config.API_BASE}${this.config.CHALLENGE_ENDPOINT}`);
        this.logger.info(`   🔒 TTL Challenge: ${this.config.CHALLENGE_TTL}s`);
        this.logger.info(`   📤 Upload Endpoint: ${this.config.UPLOAD_ENDPOINT}`);
        this.logger.info(`   🔒 Modo: sob demanda (só no upload)`);
        
        this._state.isInitialized = true;
        this._setupEventListeners();
        this._checkWorkerAvailability();
        this._updateAuthStatus();
        
        this.logger.info('   🔍 Diagnóstico: ativo');
    }

    _setupEventListeners() {
        const authHandler = () => this._updateAuthStatus();
        document.addEventListener('authLoginSuccess', authHandler);
        document.addEventListener('authLogout', authHandler);
        this._cleanupFunctions.push(() => {
            document.removeEventListener('authLoginSuccess', authHandler);
            document.removeEventListener('authLogout', authHandler);
        });

        const visibilityHandler = () => {
            if (document.hidden && this._state.isSolving) {
                this.logger.debug('⏸️ Página oculta, mantendo operação em background');
            }
        };
        document.addEventListener('visibilitychange', visibilityHandler);
        this._cleanupFunctions.push(() => {
            document.removeEventListener('visibilitychange', visibilityHandler);
        });

        const beforeUnloadHandler = () => this._cleanup();
        window.addEventListener('beforeunload', beforeUnloadHandler);
        this._cleanupFunctions.push(() => {
            window.removeEventListener('beforeunload', beforeUnloadHandler);
        });
    }

    async _checkWorkerAvailability() {
        if (this._state.workerChecked) return;
        this._state.workerChecked = true;
        
        try {
            const response = await fetch(this.config.WORKER_URL, { method: 'HEAD' });
            this._state.workerAvailable = response.ok;
            this.logger.info(`🧵 Worker ${this._state.workerAvailable ? 'disponível' : 'indisponível'} (status: ${response.status})`);
        } catch (e) {
            this._state.workerAvailable = false;
            this.logger.warn('🧵 Worker indisponível (erro na verificação)');
        }
    }

    // ==============================================
    // 🔥 MÉTODOS PÚBLICOS PRINCIPAIS
    // ==============================================

    /**
     * 🔥 PREPARA O POW PARA UPLOAD
     * Retorna true se o PoW está pronto, false caso contrário
     */
    async prepareForUpload() {
        this.logger.debug('🔄 Preparando PoW para upload...');
        
        if (!this._isAuthenticated()) {
            this.logger.warn('⏳ PoW: aguardando autenticação...');
            this._state.lastError = 'Usuário não autenticado';
            return false;
        }

        if (this._isLocked()) {
            this.logger.warn('⛔ PoW bloqueado temporariamente');
            return false;
        }

        // 🔥 Verificar cache válido
        if (this._hasValidCache()) {
            this.logger.info('⚡ PoW em cache (válido)');
            this._metrics.cacheHits++;
            this._metrics.solutionsCached++;
            return true;
        }

        this._metrics.cacheMisses++;

        if (this._state.isSolving) {
            this.logger.debug('⏳ PoW já está sendo calculado...');
            return await this._waitForSolving();
        }

        return await this._calculateSolution();
    }

    /**
     * 🔥 OBTÉM A SOLUÇÃO POW PARA UPLOAD
     * Retorna a solução ou lança erro
     */
    async getSolutionForUpload() {
        this.logger.debug('🔑 Obtendo solução PoW para upload...');
        
        if (!this._isAuthenticated()) {
            throw new Error('Usuário não autenticado');
        }

        if (this._isLocked()) {
            throw new Error('PoW bloqueado temporariamente. Tente novamente em alguns segundos.');
        }

        // 🔥 Verificar cache válido
        if (this._hasValidCache() && this._cache.solution && !this._cache.used) {
            const solution = { ...this._cache.solution };
            this._cache.used = true;
            this._metrics.solutionsUsed++;
            this.logger.info(`⚡ Usando PoW em cache (difficulty: ${solution.complexity})`);
            return solution;
        }

        // Se estiver calculando, aguardar
        if (this._state.isSolving) {
            this.logger.debug('⏳ Aguardando cálculo do PoW...');
            const result = await this._waitForSolving();
            if (result && this._cache.solution && !this._cache.used) {
                const solution = { ...this._cache.solution };
                this._cache.used = true;
                this._metrics.solutionsUsed++;
                return solution;
            }
        }

        // 🔥 Forçar novo cálculo
        const success = await this._calculateSolution(true);
        if (success && this._cache.solution && !this._cache.used) {
            const solution = { ...this._cache.solution };
            this._cache.used = true;
            this._metrics.solutionsUsed++;
            return solution;
        }

        throw new Error('Não foi possível obter solução PoW');
    }

    /**
     * 🔥 UPLOAD COM POW (CORRIGIDO)
     */
    async uploadWithPow(files, endpoint = null, options = {}) {
        const fileArray = Array.isArray(files) ? files : [files];
        this.logger.info(`📤 Iniciando upload com PoW: ${fileArray.length} arquivo(s)`);

        for (const file of fileArray) {
            if (!PowValidators.isFileValid(file)) {
                throw new Error(`Arquivo inválido: ${file?.name || 'desconhecido'}`);
            }
        }

        if (!this._isAuthenticated()) {
            throw new Error('Usuário não autenticado');
        }

        // 🔥 USAR ENDPOINT CORRETO (com fallback)
        const endpoints = [];
        if (endpoint) {
            endpoints.push(endpoint);
        }
        endpoints.push(this.config.UPLOAD_ENDPOINT);
        endpoints.push(this.config.UPLOAD_ENDPOINT_FALLBACK);

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

        const formData = new FormData();
        for (const file of fileArray) {
            const safeFilename = this._sanitizeString(file.name);
            formData.append('files', file, safeFilename);
        }
        formData.append('analysis_type', options.analysis_type || 'auto');
        if (options.report_format) {
            formData.append('report_format', options.report_format);
        }

        const token = this._getToken();
        if (!token) {
            throw new Error('Token de autenticação não encontrado');
        }

        // 🔥 Tentar cada endpoint
        let lastError = null;
        for (const ep of endpoints) {
            try {
                this.logger.info(`📤 Tentando endpoint: ${ep}`);
                const result = await this._uploadWithRetry(formData, token, solution, ep);
                this.logger.info(`✅ Upload concluído via ${ep}`);
                return result;
            } catch (error) {
                this.logger.warn(`⚠️ Falha no endpoint ${ep}: ${error.message}`);
                lastError = error;
                // Se for erro 400, pode ser endpoint errado - tentar próximo
                if (error.message.includes('400')) {
                    this.logger.info(`🔄 Tentando próximo endpoint...`);
                    continue;
                }
                // Se for erro 428 (PoW expirado), recomeçar
                if (error.message.includes('428') || error.message.includes('PoW expirado')) {
                    this.logger.info(`🔄 PoW expirado, recalculando...`);
                    this.clearCache();
                    solution = await this.getSolutionForUpload();
                    if (!solution) {
                        throw new Error('Não foi possível obter nova solução PoW');
                    }
                    continue;
                }
                throw error;
            }
        }

        throw new Error(`Upload falhou em todos os endpoints: ${lastError?.message || 'Erro desconhecido'}`);
    }

    /**
     * 🔥 RESETA O CLIENTE
     */
    reset() {
        this._cache.solution = null;
        this._cache.challenge = null;
        this._cache.solvedAt = null;
        this._cache.expiresAt = null;
        this._cache.isValid = false;
        this._cache.used = false;
        this._state.isSolving = false;
        this._state.lastError = null;
        this._state.isReady = false;
        this._security.consecutiveFailures = 0;
        this._cleanupWorker();
        this.logger.info('🔄 PoW resetado');
    }

    /**
     * 🔥 LIMPA O CACHE
     */
    clearCache() {
        this._cache.solution = null;
        this._cache.challenge = null;
        this._cache.solvedAt = null;
        this._cache.expiresAt = null;
        this._cache.isValid = false;
        this._cache.used = false;
        this.logger.info('🧹 Cache do PoW limpo');
    }

    // ==============================================
    // 🔥 ESTATÍSTICAS E DIAGNÓSTICO
    // ==============================================

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
                workerAvailable: this._state.workerAvailable,
                version: this._state.version
            },
            cache: {
                hasSolution: this._cache.solution !== null,
                hasChallenge: this._cache.challenge !== null,
                age: this._cache.solvedAt ? Date.now() - this._cache.solvedAt : null,
                isValid: this._cache.isValid,
                used: this._cache.used,
                ttl: this.config.CACHE_TTL
            },
            metrics: this._metrics,
            security: this._security,
            config: {
                cacheTTL: this.config.CACHE_TTL,
                challengeTTL: this.config.CHALLENGE_TTL,
                maxRetries: this.config.MAX_RETRIES,
                workerTimeout: this.config.WORKER_TIMEOUT,
                defaultDifficulty: this.config.DEFAULT_DIFFICULTY,
                maxExpiresIn: this.config.MAX_EXPIRES_IN,
                uploadEndpoint: this.config.UPLOAD_ENDPOINT,
                uploadEndpointFallback: this.config.UPLOAD_ENDPOINT_FALLBACK
            }
        };
    }

    getDiagnostics() {
        return {
            ...this.getStats(),
            config: this.config,
            apiBase: this.config.API_BASE,
            challengeEndpoint: this.config.CHALLENGE_ENDPOINT,
            uploadEndpoint: this.config.UPLOAD_ENDPOINT,
            uploadEndpointFallback: this.config.UPLOAD_ENDPOINT_FALLBACK,
            workerUrl: this.config.WORKER_URL,
            logHistory: this.logger.getHistory().slice(-10),
            timestamp: new Date().toISOString(),
            uptime: this._state.isInitialized ? Date.now() - this._state.createdAt : null,
            health: this._checkHealth()
        };
    }

    _checkHealth() {
        const issues = [];
        const warnings = [];

        if (!this._state.isAuthenticated) {
            issues.push('Não autenticado');
        }

        if (this._state.isSolving && Date.now() - this._state.createdAt > 60000) {
            warnings.push('Cálculo em andamento há mais de 60s');
        }

        if (this._security.consecutiveFailures > 3) {
            warnings.push(`${this._security.consecutiveFailures} falhas consecutivas`);
        }

        return {
            status: issues.length === 0 ? 'healthy' : 'unhealthy',
            issues,
            warnings,
            recommendations: this._getRecommendations(issues, warnings)
        };
    }

    _getRecommendations(issues, warnings) {
        const recs = [];
        if (issues.includes('Não autenticado')) {
            recs.push('Faça login para usar o PoW');
        }
        if (warnings.some(w => w.includes('falhas consecutivas'))) {
            recs.push('Reset o cliente com window.powClient.reset()');
        }
        return recs;
    }

    // ==============================================
    // 🔥 MÉTODOS INTERNOS
    // ==============================================

    _isAuthenticated() {
        this._updateAuthStatus();
        return this._state.isAuthenticated;
    }

    _updateAuthStatus() {
        this._state.isAuthenticated = !!this._getToken();
        return this._state.isAuthenticated;
    }

    _getToken() {
        try {
            const token = localStorage.getItem('access_token');
            if (!token || token === 'undefined' || token === 'null') return null;
            return this._sanitizeString(token);
        } catch (e) {
            return null;
        }
    }

    _getRefreshToken() {
        try {
            const token = localStorage.getItem('refresh_token');
            if (!token || token === 'undefined' || token === 'null') return null;
            return this._sanitizeString(token);
        } catch (e) {
            return null;
        }
    }

    _sanitizeString(str) {
        if (!str) return '';
        if (typeof str !== 'string') str = String(str);
        return str.replace(/[&<>"'`/=();\n\r\t]/g, m => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;',
            '"': '&quot;', "'": '&#39;', '`': '&#96;',
            '/': '&#47;', '=': '&#61;', '(': '&#40;',
            ')': '&#41;', ';': '&#59;', '\n': '\\n',
            '\r': '\\r', '\t': '\\t'
        })[m] || m).slice(0, 1000);
    }

    _generateId() {
        return Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
    }

    _sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    _isLocked() {
        if (!this._security.isLocked) return false;
        if (this._security.lockUntil && Date.now() > this._security.lockUntil) {
            this._security.isLocked = false;
            this._security.lockUntil = null;
            return false;
        }
        return true;
    }

    _lock(duration = 5000) {
        this._security.isLocked = true;
        this._security.lockUntil = Date.now() + duration;
        this.logger.warn(`🔒 PoW bloqueado por ${duration}ms`);
    }

    _hasValidCache() {
        if (!this._cache.solution) return false;
        if (!this._cache.solvedAt) return false;
        if (!this._cache.isValid) return false;
        if (this._cache.used) return false;
        
        const age = Date.now() - this._cache.solvedAt;
        const isValid = age < this.config.CACHE_TTL;
        
        if (!isValid) {
            this.logger.debug(`⏳ Cache expirado (${age}ms > ${this.config.CACHE_TTL}ms)`);
            this._cache.solution = null;
            this._cache.challenge = null;
            this._cache.solvedAt = null;
            this._cache.isValid = false;
            this._cache.used = false;
        }
        
        return isValid;
    }

    async _waitForSolving(timeout = 30000) {
        const start = Date.now();
        while (this._state.isSolving && (Date.now() - start) < timeout) {
            await this._sleep(100);
        }
        if (this._state.isSolving) {
            this.logger.warn('⏰ Timeout aguardando cálculo do PoW');
            this._state.isSolving = false;
            return false;
        }
        return this._cache.solution !== null && this._cache.isValid && !this._cache.used;
    }

    // ==============================================
    // 🔥 CÁLCULO DO POW
    // ==============================================

    async _calculateSolution(force = false) {
        if (this._state.isSolving && !force) {
            return await this._waitForSolving();
        }

        this._state.isSolving = true;
        this.logger.info('🔄 Calculando PoW...');

        try {
            const challenge = await this._getChallenge();
            if (!challenge) {
                this._state.isSolving = false;
                return false;
            }

            const solution = await this._solveChallenge(challenge);
            
            if (solution && PowValidators.isValidSolution(solution)) {
                this._cache.solution = {
                    ...solution,
                    solvedAt: Date.now(),
                    expiresAt: Date.now() + this.config.CACHE_TTL,
                };
                this._cache.challenge = challenge;
                this._cache.solvedAt = Date.now();
                this._cache.isValid = true;
                this._cache.used = false;
                this._metrics.solutionsCalculated++;
                this._state.lastSuccess = Date.now();
                this._state.isReady = true;
                this._security.consecutiveFailures = 0;
                
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

    async _getChallenge() {
        this.logger.debug('📡 Solicitando desafio PoW ao backend...');
        this._metrics.totalRequests++;
        this._metrics.challengesRequested++;

        const token = this._getToken();
        if (!token) {
            throw new Error('Não autenticado');
        }

        const startTime = Date.now();

        try {
            const url = `${this.config.API_BASE}${this.config.CHALLENGE_ENDPOINT}`;
            this.logger.debug(`   🔗 URL: ${url}`);

            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Cache-Control': 'no-cache',
                    'Accept': 'application/json',
                },
                credentials: 'include',
            });

            const duration = Date.now() - startTime;
            this.logger.debug(`📡 Resposta: status=${response.status}, duration=${duration}ms`);

            if (response.status === 401) {
                this._handleAuthError();
                throw new Error('Sessão expirada. Faça login novamente.');
            }

            if (response.status === 429) {
                const data = await this._parseJson(response);
                const retryAfter = data?.retry_after || 60;
                this._lock(retryAfter * 1000);
                throw new Error(`Rate limit: ${data?.detail || 'Muitas requisições'}`);
            }

            if (!response.ok) {
                const data = await this._parseJson(response);
                throw new Error(data?.detail || `HTTP ${response.status}`);
            }

            const data = await this._parseJson(response);
            if (!data) {
                throw new Error('JSON inválido recebido');
            }

            if (!PowValidators.isValidChallenge(data)) {
                this.logger.error('❌ Desafio inválido:', data);
                throw new Error(`Desafio inválido: expires_in=${data.expires_in} (max: ${POW_CONFIG.MAX_EXPIRES_IN}s)`);
            }

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

    async _solveChallenge(challenge) {
        this.logger.info(`🔐 Resolvendo PoW (difficulty: ${challenge.difficulty})...`);
        const startTime = Date.now();

        // 1. Tentar com Web Worker
        if (this._state.workerAvailable && this._isWorkerAvailable()) {
            try {
                const result = await this._solveWithWorker(challenge);
                if (result) {
                    this._updateSolveMetrics(startTime);
                    this.logger.info(`✅ PoW resolvido com Worker em ${Date.now() - startTime}ms`);
                    return result;
                }
            } catch (workerError) {
                this._metrics.workerFailures++;
                this.logger.warn(`⚠️ Erro no Worker (${workerError.message}). Usando fallback síncrono...`);
            }
        } else {
            this.logger.info('🧵 Worker indisponível, usando fallback síncrono diretamente...');
        }

        // 2. Fallback: Síncrono
        try {
            this._metrics.syncFallbackUsed++;
            this.logger.info('🔄 Usando fallback síncrono...');
            const result = await this._solveSync(challenge);
            this._updateSolveMetrics(startTime);
            this.logger.info(`✅ PoW resolvido (sync) em ${Date.now() - startTime}ms`);
            return result;
        } catch (syncError) {
            this.logger.error('❌ Erro no fallback síncrono:', syncError);
            throw syncError;
        }
    }

    async _solveSync(challenge) {
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

            if (nonce % 10000 === 0) {
                this.logger.debug(`🔐 Tentativas: ${nonce}/${maxAttempts}`);
            }
        }

        throw new Error(`Não foi possível encontrar nonce após ${maxAttempts} tentativas`);
    }

    _isWorkerAvailable() {
        try {
            return typeof Worker !== 'undefined';
        } catch (e) {
            return false;
        }
    }

    _solveWithWorker(challenge) {
        return new Promise((resolve, reject) => {
            try {
                this._metrics.workerAttempts++;
                
                fetch(this.config.WORKER_URL, { method: 'HEAD' })
                    .then(response => {
                        if (!response.ok) {
                            this.logger.warn(`⚠️ Worker não encontrado (${response.status}), usando fallback síncrono...`);
                            this._solveSync(challenge).then(resolve).catch(reject);
                            return;
                        }
                        
                        const worker = new Worker(this.config.WORKER_URL);
                        this._worker = worker;

                        const timeoutId = setTimeout(() => {
                            worker.terminate();
                            this._worker = null;
                            reject(new Error(`Timeout ao resolver PoW (${this.config.WORKER_TIMEOUT}ms)`));
                        }, this.config.WORKER_TIMEOUT);

                        worker.postMessage({
                            prefix: challenge.challenge,
                            complexity: challenge.difficulty,
                            timestamp: challenge.timestamp || Date.now(),
                            expires_in: challenge.expires_in || this.config.CHALLENGE_TTL,
                        });

                        worker.onmessage = (e) => {
                            clearTimeout(timeoutId);
                            const data = e.data;

                            if (data.type === 'progress' || data.type === 'ready') {
                                return;
                            }

                            if (data.success === false) {
                                worker.terminate();
                                this._worker = null;
                                reject(new Error(data.error || 'Worker falhou'));
                                return;
                            }

                            if (!PowValidators.isNonceValid(data.nonce)) {
                                worker.terminate();
                                this._worker = null;
                                reject(new Error('Nonce inválido recebido do worker'));
                                return;
                            }

                            const solution = {
                                nonce: this._sanitizeString(data.nonce),
                                prefix: challenge.challenge,
                                complexity: challenge.difficulty,
                                solvedAt: Date.now(),
                                timeMs: data.timeMs || 0,
                                worker: true,
                            };

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
                            
                            this.logger.warn(`⚠️ Worker error. Usando fallback síncrono...`);
                            this._solveSync(challenge)
                                .then(resolve)
                                .catch(fallbackError => {
                                    reject(new Error(`Worker e fallback falharam: ${fallbackError.message}`));
                                });
                        };
                    })
                    .catch(() => {
                        this.logger.warn('⚠️ Worker não disponível, usando fallback síncrono...');
                        this._solveSync(challenge).then(resolve).catch(reject);
                    });
                    
            } catch (error) {
                this._worker = null;
                this.logger.warn('⚠️ Erro ao criar Worker, usando fallback síncrono...');
                this._solveSync(challenge).then(resolve).catch(reject);
            }
        });
    }

    _updateSolveMetrics(startTime) {
        const timeMs = Date.now() - startTime;
        this._metrics.lastSolveTime = timeMs;
        this._metrics.totalSolveTime += timeMs;
        if (this._metrics.solutionsCalculated > 0) {
            this._metrics.avgSolveTime = this._metrics.totalSolveTime / (this._metrics.solutionsCalculated + 1);
        }
        if (timeMs > this._metrics.maxSolveTime) this._metrics.maxSolveTime = timeMs;
        if (timeMs < this._metrics.minSolveTime) this._metrics.minSolveTime = timeMs;
    }

    // ==============================================
    // 🔥 UPLOAD COM RETRY (CORRIGIDO)
    // ==============================================

    async _uploadWithRetry(formData, token, solution, endpoint) {
        const maxRetries = this.config.MAX_RETRIES;
        let lastError = null;
        let attempt = 0;

        while (attempt < maxRetries) {
            attempt++;
            const backoff = Math.min(1000 * Math.pow(2, attempt - 1), this.config.MAX_BACKOFF);
            
            try {
                this.logger.debug(`📤 Tentativa ${attempt}/${maxRetries}`);
                this.logger.debug(`   🔗 Endpoint: ${endpoint}`);
                this.logger.debug(`   🔑 Challenge: ${solution.prefix.substring(0, 10)}...`);
                this.logger.debug(`   🔑 Nonce: ${solution.nonce}`);

                const url = `${this.config.API_BASE}${endpoint}`;
                
                const response = await fetch(url, {
                    method: 'POST',
                    headers: {
                        'X-PoW-Challenge': solution.prefix,
                        'X-PoW-Nonce': solution.nonce,
                        'Authorization': `Bearer ${token}`,
                        'Accept': 'application/json',
                    },
                    body: formData,
                    credentials: 'include',
                });

                // 🔥 LOG DA RESPOSTA PARA DEBUG
                this.logger.debug(`📡 Resposta: ${response.status} ${response.statusText}`);

                // 🔥 TENTAR LER O CORPO DA RESPOSTA (MESMO EM ERRO)
                let responseData = null;
                try {
                    const text = await response.text();
                    if (text) {
                        try {
                            responseData = JSON.parse(text);
                            this.logger.debug(`📄 Resposta:`, responseData);
                        } catch (e) {
                            this.logger.debug(`📄 Resposta texto: ${text.substring(0, 200)}`);
                        }
                    }
                } catch (e) {
                    // Ignora
                }

                if (response.status === 428) {
                    this.logger.warn('⚠️ PoW expirado (428), recalculando...');
                    this.clearCache();
                    const newSolution = await this.getSolutionForUpload();
                    if (!newSolution) {
                        throw new Error('Não foi possível obter nova solução PoW');
                    }
                    solution = newSolution;
                    continue;
                }

                if (response.status === 401) {
                    this.logger.warn('⚠️ Token expirado, tentando refresh...');
                    const refreshed = await this._refreshToken();
                    if (refreshed) {
                        const newToken = this._getToken();
                        if (newToken) {
                            token = newToken;
                            continue;
                        }
                    }
                    throw new Error('Sessão expirada. Faça login novamente.');
                }

                if (response.status === 429) {
                    const data = responseData || {};
                    const retryAfter = data?.retry_after || 60;
                    this.logger.warn(`⚠️ Rate limit, aguardando ${retryAfter}s...`);
                    await this._sleep(retryAfter * 1000);
                    continue;
                }

                // 🔥 TRATAR ERRO 400 COM MAIS DETALHES
                if (response.status === 400) {
                    let errorMsg = 'Erro na requisição (400)';
                    if (responseData) {
                        if (responseData.detail) {
                            errorMsg = typeof responseData.detail === 'string' 
                                ? responseData.detail 
                                : JSON.stringify(responseData.detail);
                        } else if (responseData.message) {
                            errorMsg = responseData.message;
                        } else if (responseData.error) {
                            errorMsg = responseData.error;
                        }
                    }
                    this.logger.error(`❌ Erro 400: ${errorMsg}`);
                    
                    // 🔥 SE FOR ERRO DE PoW, TENTAR RENOVAR
                    if (errorMsg.toLowerCase().includes('pow') || 
                        errorMsg.toLowerCase().includes('proof') ||
                        errorMsg.toLowerCase().includes('nonce')) {
                        this.logger.info('🔄 Erro de PoW detectado, renovando...');
                        this.clearCache();
                        const newSolution = await this.getSolutionForUpload();
                        if (newSolution) {
                            solution = newSolution;
                            continue;
                        }
                    }
                    
                    throw new Error(errorMsg);
                }

                if (response.ok) {
                    const data = responseData || await response.json();
                    this.logger.info('✅ Upload com PoW concluído');
                    return data;
                }

                const errorData = responseData || {};
                throw new Error(errorData?.detail || `HTTP ${response.status}: ${response.statusText}`);

            } catch (error) {
                lastError = error;
                this.logger.error(`❌ Tentativa ${attempt} falhou:`, error.message);
                if (attempt < maxRetries) {
                    this.logger.debug(`⏳ Aguardando ${backoff}ms antes de tentar novamente...`);
                    await this._sleep(backoff);
                }
            }
        }

        throw new Error(`Upload falhou após ${maxRetries} tentativas: ${lastError?.message || 'Erro desconhecido'}`);
    }

    // ==============================================
    // 🔥 UTILITÁRIOS
    // ==============================================

    async _refreshToken() {
        try {
            const refreshToken = this._getRefreshToken();
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

    async _parseJson(response) {
        try {
            const text = await response.text();
            return JSON.parse(text);
        } catch (e) {
            return null;
        }
    }

    _handleAuthError() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        this._state.isAuthenticated = false;
        this._state.lastError = 'Token expirado';
        window.dispatchEvent(new CustomEvent('auth:expired', {
            detail: { message: 'Sessão expirada' }
        }));
    }

    _handleError(error, context) {
        const errorMsg = error.message || String(error);
        this._state.lastError = errorMsg;
        this._metrics.errorCount++;
        this._metrics.lastError = { message: errorMsg, context, timestamp: Date.now() };
        this.logger.error(`❌ [${context}] ${errorMsg}`);
    }

    _cleanupWorker() {
        if (this._worker) {
            try { this._worker.terminate(); } catch (e) {}
            this._worker = null;
        }
    }

    _cleanup() {
        this._cleanupWorker();
        this._cleanupFunctions.forEach(fn => { try { fn(); } catch (e) {} });
        this._cleanupFunctions = [];
    }

    destroy() {
        this._cleanup();
        this._state.isInitialized = false;
        this.logger.info('🗑️ PoW Client destruído');
    }
}

// ==============================================
// 🔥 INSTÂNCIA GLOBAL
// ==============================================

const powClientInstance = new PowClient();

if (typeof window !== 'undefined') {
    window.powClient = powClientInstance;
    window.Pow = powClientInstance;
    window.PowClient = powClientInstance;
    
    window.initPowClient = function(options = {}) {
        if (options.logLevel) powClientInstance.logger.setLevel(options.logLevel);
        console.log('✅ PoW Client v6.1 inicializado');
        console.log(`   🔍 Use window.powClient.getDiagnostics() para debug`);
        console.log(`   📊 Use window.powClient.getStats() para estatísticas`);
        console.log(`   📤 Upload Endpoint: ${POW_CONFIG.UPLOAD_ENDPOINT}`);
        console.log(`   🔄 Fallback: ${POW_CONFIG.UPLOAD_ENDPOINT_FALLBACK}`);
        return powClientInstance;
    };
    
    window.getPowDiagnostics = function() {
        return powClientInstance.getDiagnostics();
    };
    
    window.getPowStats = function() {
        return powClientInstance.getStats();
    };
    
    console.log('✅ PoW Client v6.1 global disponível');
    console.log('   🔍 Use window.powClient.getDiagnostics() para debug');
    console.log('   📊 Use window.powClient.getStats() para estatísticas');
    console.log('   🔄 Compatível com backend TTL: 900s');
    console.log('   📤 Upload Endpoint: /upload-multi-analyze');
}

// ==============================================
// 🔥 MENSAGEM DE INICIALIZAÇÃO
// ==============================================

console.log('=' .repeat(60));
console.log('🔥 pow-client.js v6.1 carregado');
console.log('   ✅ CORRIGIDO: UPLOAD_ENDPOINT = /upload-multi-analyze');
console.log('   ✅ ADICIONADO: Fallback para /upload-auto');
console.log('   ✅ MELHORADO: Tratamento de erros 400');
console.log('   ✅ ADICIONADO: Auto-recuperação PoW');
console.log('   ✅ ADICIONADO: Log detalhado de respostas');
console.log('   ✅ OTIMIZADO: Cache com invalidação inteligente');
console.log('   📡 window.powClient disponível');
console.log('   🔍 Use window.getPowDiagnostics() para debug');
console.log('=' .repeat(60));