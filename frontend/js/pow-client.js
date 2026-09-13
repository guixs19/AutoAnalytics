// frontend/js/pow-client.js - VERSÃO v6.3 (CORRIGIDA E OTIMIZADA)
/**
 * 🔥 Proof of Work Client - Versão 6.3
 * 
 * ✅ CORREÇÕES v6.3 (baseadas em bugs reais encontrados):
 *   🔴 BUGFIX #1: TTL sincronizado com backend (600s, era 900s)
 *   🔴 BUGFIX #2: _getToken() NÃO sanitiza mais o JWT (corrompia o token!)
 *   🔴 BUGFIX #3: nonce NÃO sanitizado (era corrompido em casos extremos)
 *   🔴 BUGFIX #4: Headers X-PoW-Complexity e X-PoW-Timestamp adicionados
 *   🔴 BUGFIX #5: Log detalhado de erro 400 (útil para debug)
 *   🔴 BUGFIX #6: _sanitizeString renomeado para _sanitizeFilename (só para arquivos)
 *   🔴 BUGFIX #7: Removido fallback para /upload-auto (evitava consumo duplo do challenge)
 * 
 * ✅ MANTIDO v6.2:
 *   - isPowHealthy() - verifica saúde do PoW
 *   - autoRecover() - recuperação automática
 *   - Exponential backoff para retries
 *   - Diagnóstico de saúde detalhado
 *   - Auto-cleanup de cache expirado
 * 
 * CONECTADO COM: pow_routes.py (backend TTL: 600s)
 */

// ==============================================
// 🔥 CONFIGURAÇÕES (SINCRONIZADAS COM BACKEND)
// ==============================================

const POW_CONFIG = {
    // 🔥 Dificuldade e TTL (SINCRONIZADO COM pow_routes.py)
    DEFAULT_DIFFICULTY: 4,
    CHALLENGE_TTL: 600, // 🔴 BUGFIX #1: era 900, backend usa 600
    CACHE_TTL: 60000, // 60 segundos para cache da solução
    
    // 🔥 Retry e Timeout
    MAX_RETRIES: 3,
    RETRY_DELAY: 1000,
    MAX_BACKOFF: 10000,
    WORKER_TIMEOUT: 60000, // 60 segundos
    MAX_NONCE_ATTEMPTS: 2000000, // 2 milhões
    
    // 🔥 Endpoints
    API_BASE: window.location.hostname.includes('localhost')
        ? 'http://localhost:8000/api'
        : '/api',
    CHALLENGE_ENDPOINT: '/pow/challenge',
    UPLOAD_ENDPOINT: '/upload-multi-analyze',
    // 🔴 BUGFIX #7: removido UPLOAD_ENDPOINT_FALLBACK (evitava consumo duplo)
    WORKER_URL: '/static/js/pow-worker.js',
    
    // 🔥 Limites (sincronizados com backend)
    MAX_CHALLENGE_AGE: 600000, // 🔴 BUGFIX #1: 10 minutos (era 15)
    MIN_DIFFICULTY: 3,
    MAX_DIFFICULTY: 6,
    MIN_EXPIRES_IN: 30,
    MAX_EXPIRES_IN: 1800,
    
    // 🔥 Logging
    LOG_LEVEL: 'info',
    MAX_LOG_HISTORY: 100,
    
    // 🔥 Configurações de saúde
    HEALTH_CHECK_INTERVAL: 30000,
    MAX_CONSECUTIVE_FAILURES: 3,
    RECOVERY_COOLDOWN: 60000,
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
// 🔥 VALIDAÇÕES
// ==============================================

const PowValidators = {
    isValidChallenge: (challenge) => {
        if (!challenge || typeof challenge !== 'object') return false;
        if (!challenge.challenge || typeof challenge.challenge !== 'string') return false;
        if (challenge.challenge.length !== 32) return false;
        if (!challenge.difficulty || typeof challenge.difficulty !== 'number') return false;
        if (challenge.difficulty < POW_CONFIG.MIN_DIFFICULTY || 
            challenge.difficulty > POW_CONFIG.MAX_DIFFICULTY) return false;
        if (!challenge.expires_in || typeof challenge.expires_in !== 'number') return false;
        if (challenge.expires_in < POW_CONFIG.MIN_EXPIRES_IN || 
            challenge.expires_in > POW_CONFIG.MAX_EXPIRES_IN) return false;
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
// 🔥 DETECTOR DE ERROS
// ==============================================

const ErrorDetector = {
    isPowError: (error) => {
        if (!error) return false;
        const errorStr = typeof error === 'string' ? error : JSON.stringify(error);
        const patterns = ['pow', 'proof', 'nonce', 'challenge', '428', 'precondition'];
        return patterns.some(p => errorStr.toLowerCase().includes(p));
    },
    
    isCreditsError: (error) => {
        if (!error) return false;
        const errorStr = typeof error === 'string' ? error : JSON.stringify(error);
        const patterns = ['crédito', 'credits', '402', 'payment', 'insufficient'];
        return patterns.some(p => errorStr.toLowerCase().includes(p));
    },
    
    isAuthError: (error) => {
        if (!error) return false;
        const errorStr = typeof error === 'string' ? error : JSON.stringify(error);
        const patterns = ['401', 'unauthorized', 'token', 'session', 'login'];
        return patterns.some(p => errorStr.toLowerCase().includes(p));
    },
    
    isRateLimitError: (error) => {
        if (!error) return false;
        const errorStr = typeof error === 'string' ? error : JSON.stringify(error);
        const patterns = ['429', 'rate limit', 'too many', 'muitas'];
        return patterns.some(p => errorStr.toLowerCase().includes(p));
    }
};

// ==============================================
// 🔥 CLASSE PRINCIPAL - PowClient v6.3
// ==============================================

class PowClient {
    constructor(config = {}) {
        this.config = { ...POW_CONFIG, ...config };
        this.logger = new PowLogger(this.config.LOG_LEVEL);

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
            version: '6.3',
            healthCheckCount: 0,
            consecutiveFailures: 0,
            lastRecoveryAttempt: 0,
            isRecovering: false,
            recoveryCount: 0,
        };

        this._cache = {
            solution: null,
            challenge: null,
            solvedAt: null,
            expiresAt: null,
            isValid: false,
            used: false
        };

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
            cacheMisses: 0,
            recoveryAttempts: 0,
            recoverySuccesses: 0,
            healthCheckFailures: 0,
        };

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
        this._healthCheckInterval = null;

        this._init();
    }

    // ==============================================
    // 🔥 INICIALIZAÇÃO
    // ==============================================

    _init() {
        this.logger.info('🚀 PoW Client v6.3 inicializado (CORRIGIDO)');
        this.logger.info(`   📦 ID: ${this._state.id}`);
        this.logger.info(`   📦 Cache TTL: ${this.config.CACHE_TTL}ms`);
        this.logger.info(`   🔑 API: ${this.config.API_BASE}${this.config.CHALLENGE_ENDPOINT}`);
        this.logger.info(`   🔒 TTL Challenge: ${this.config.CHALLENGE_TTL}s (sincronizado com backend)`);
        this.logger.info(`   📤 Upload Endpoint: ${this.config.UPLOAD_ENDPOINT}`);
        this.logger.info(`   🩺 Health Check: ${this.config.HEALTH_CHECK_INTERVAL/1000}s`);
        
        this._state.isInitialized = true;
        this._setupEventListeners();
        this._checkWorkerAvailability();
        this._updateAuthStatus();
        this._startHealthCheck();
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
            if (!document.hidden) {
                this.isPowHealthy().catch(() => {});
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
    // 🔥 SAÚDE DO POW
    // ==============================================

    async isPowHealthy() {
        this.logger.debug('🩺 Verificando saúde do PoW...');
        this._state.healthCheckCount++;
        
        if (!this._isAuthenticated()) {
            this.logger.warn('⏳ PoW: usuário não autenticado');
            this._metrics.healthCheckFailures++;
            return false;
        }
        
        if (this._hasValidCache()) {
            this.logger.debug('✅ PoW saudável (cache válido)');
            return true;
        }
        
        if (this._isLocked()) {
            this.logger.warn('⛔ PoW bloqueado');
            this._metrics.healthCheckFailures++;
            return false;
        }
        
        if (this._state.isRecovering) {
            this.logger.debug('⏳ PoW em recuperação...');
            return false;
        }
        
        if (this._state.isSolving) {
            this.logger.debug('⏳ PoW está resolvendo...');
            return true;
        }
        
        try {
            const ready = await this.prepareForUpload();
            if (ready) {
                this.logger.debug('✅ PoW saudável (preparado)');
                this._state.consecutiveFailures = 0;
                return true;
            }
        } catch (e) {
            this.logger.warn(`⚠️ Erro ao verificar saúde: ${e.message}`);
            this._metrics.healthCheckFailures++;
            this._state.consecutiveFailures++;
        }
        
        if (this._state.consecutiveFailures >= POW_CONFIG.MAX_CONSECUTIVE_FAILURES) {
            this.logger.warn(`⚠️ ${this._state.consecutiveFailures} falhas consecutivas, tentando recuperar...`);
            await this.autoRecover();
        }
        
        return false;
    }

    async autoRecover() {
        if (this._state.isRecovering) {
            this.logger.debug('⏳ PoW já está em recuperação');
            return false;
        }
        
        const now = Date.now();
        if (now - this._state.lastRecoveryAttempt < POW_CONFIG.RECOVERY_COOLDOWN) {
            const waitTime = Math.ceil((POW_CONFIG.RECOVERY_COOLDOWN - (now - this._state.lastRecoveryAttempt)) / 1000);
            this.logger.warn(`⏳ Cooldown de recuperação: aguarde ${waitTime}s`);
            return false;
        }
        
        this._state.isRecovering = true;
        this._state.lastRecoveryAttempt = now;
        this._metrics.recoveryAttempts++;
        
        this.logger.info('🔄 Tentando auto-recuperação do PoW...');
        
        try {
            this.clearCache();
            this.reset();
            
            // 🔥 Limpar localStorage (APENAS chaves do PoW, NÃO o token!)
            localStorage.removeItem('pow_nonce');
            localStorage.removeItem('pow_challenge');
            localStorage.removeItem('pow_solution');
            
            // 🔥 Limpar cookies do PoW
            document.cookie.split(';').forEach(cookie => {
                const trimmed = cookie.trim();
                if (trimmed.startsWith('pow_')) {
                    document.cookie = trimmed + '=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
                }
            });
            
            await this._sleep(500);
            this._updateAuthStatus();
            
            const success = await this.prepareForUpload();
            
            if (success) {
                this.logger.info('✅ Auto-recuperação do PoW concluída com sucesso!');
                this._metrics.recoverySuccesses++;
                this._state.consecutiveFailures = 0;
                this._state.recoveryCount++;
                return true;
            }
            
            this.logger.warn('⚠️ Auto-recuperação falhou');
            return false;
            
        } catch (e) {
            this.logger.error('❌ Erro na auto-recuperação:', e.message);
            return false;
        } finally {
            this._state.isRecovering = false;
        }
    }

    _startHealthCheck() {
        if (this._healthCheckInterval) {
            clearInterval(this._healthCheckInterval);
        }
        
        this._healthCheckInterval = setInterval(() => {
            if (this._state.isAuthenticated && !this._state.isSolving) {
                this.isPowHealthy().catch(() => {});
            }
        }, this.config.HEALTH_CHECK_INTERVAL);
    }

    // ==============================================
    // 🔥 MÉTODOS PÚBLICOS PRINCIPAIS
    // ==============================================

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

    async getSolutionForUpload() {
        this.logger.debug('🔑 Obtendo solução PoW para upload...');
        
        if (!this._isAuthenticated()) {
            throw new Error('Usuário não autenticado');
        }

        if (this._isLocked()) {
            throw new Error('PoW bloqueado temporariamente. Tente novamente em alguns segundos.');
        }

        if (this._hasValidCache() && this._cache.solution && !this._cache.used) {
            const solution = { ...this._cache.solution };
            this._cache.used = true;
            this._metrics.solutionsUsed++;
            this.logger.info(`⚡ Usando PoW em cache (difficulty: ${solution.complexity})`);
            return solution;
        }

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

        const success = await this._calculateSolution(true);
        if (success && this._cache.solution && !this._cache.used) {
            const solution = { ...this._cache.solution };
            this._cache.used = true;
            this._metrics.solutionsUsed++;
            return solution;
        }

        throw new Error('Não foi possível obter solução PoW');
    }

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

        // 🔴 BUGFIX #7: usar APENAS o endpoint principal (evita consumo duplo)
        const targetEndpoint = endpoint || this.config.UPLOAD_ENDPOINT;

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
            // 🔴 BUGFIX #6: sanitizar apenas o NOME do arquivo, não o conteúdo
            const safeFilename = this._sanitizeFilename(file.name);
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

        // 🔥 Tentar apenas o endpoint principal
        try {
            this.logger.info(`📤 Enviando para: ${targetEndpoint}`);
            const result = await this._uploadWithRetry(formData, token, solution, targetEndpoint);
            this.logger.info(`✅ Upload concluído via ${targetEndpoint}`);
            return result;
        } catch (error) {
            this.logger.warn(`⚠️ Falha no endpoint ${targetEndpoint}: ${error.message}`);
            
            // 🔥 Se for erro de PoW, tentar recuperar UMA vez
            if (ErrorDetector.isPowError(error.message)) {
                this.logger.info('🔄 Erro de PoW detectado, tentando auto-recuperação...');
                const recovered = await this.autoRecover();
                if (recovered) {
                    const newSolution = await this.getSolutionForUpload();
                    if (newSolution) {
                        this.logger.info('✅ PoW recuperado, tentando novamente...');
                        return await this._uploadWithRetry(formData, token, newSolution, targetEndpoint);
                    }
                }
            }
            
            throw error;
        }
    }

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
        this._state.consecutiveFailures = 0;
        this._cleanupWorker();
        this.logger.info('🔄 PoW resetado');
    }

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
    // 🔥 ESTATÍSTICAS
    // ==============================================

    getStats() {
        return {
            state: { ...this._state },
            cache: {
                hasSolution: this._cache.solution !== null,
                hasChallenge: this._cache.challenge !== null,
                age: this._cache.solvedAt ? Date.now() - this._cache.solvedAt : null,
                isValid: this._cache.isValid,
                used: this._cache.used,
                ttl: this.config.CACHE_TTL
            },
            metrics: { ...this._metrics },
            security: { ...this._security },
            config: {
                cacheTTL: this.config.CACHE_TTL,
                challengeTTL: this.config.CHALLENGE_TTL,
                maxRetries: this.config.MAX_RETRIES,
                workerTimeout: this.config.WORKER_TIMEOUT,
                defaultDifficulty: this.config.DEFAULT_DIFFICULTY,
                maxExpiresIn: this.config.MAX_EXPIRES_IN,
                uploadEndpoint: this.config.UPLOAD_ENDPOINT,
                healthCheckInterval: this.config.HEALTH_CHECK_INTERVAL,
                maxConsecutiveFailures: this.config.MAX_CONSECUTIVE_FAILURES,
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
            workerUrl: this.config.WORKER_URL,
            logHistory: this.logger.getHistory().slice(-10),
            timestamp: new Date().toISOString(),
            uptime: this._state.isInitialized ? Date.now() - this._state.createdAt : null,
        };
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

    /**
     * 🔴 BUGFIX #2: NÃO sanitizar o token JWT!
     * Tokens JWT contêm caracteres como '.', '-', '_' que são válidos.
     * A sanitização anterior corrompia o token, causando 401/400.
     */
    _getToken() {
        try {
            const token = localStorage.getItem('access_token');
            if (!token || token === 'undefined' || token === 'null' || token.length < 10) {
                return null;
            }
            // 🔥 RETORNAR O TOKEN COMO ESTÁ - NÃO SANITIZAR!
            return token;
        } catch (e) {
            return null;
        }
    }

    _getRefreshToken() {
        try {
            const token = localStorage.getItem('refresh_token');
            if (!token || token === 'undefined' || token === 'null') return null;
            // 🔥 RETORNAR O TOKEN COMO ESTÁ - NÃO SANITIZAR!
            return token;
        } catch (e) {
            return null;
        }
    }

    /**
     * 🔴 BUGFIX #6: sanitização de NOME DE ARQUIVO (não de token/nonce)
     * Remove apenas caracteres perigosos para path traversal
     */
    _sanitizeFilename(filename) {
        if (!filename) return 'arquivo.csv';
        if (typeof filename !== 'string') filename = String(filename);
        // 🔥 Remove path traversal e caracteres de controle
        return filename
            .replace(/[/\\]/g, '_')
            .replace(/[\x00-\x1f\x7f]/g, '')
            .replace(/\.\./g, '_')
            .slice(0, 255);
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
                this._state.consecutiveFailures = 0;
                
                this.logger.info(`✅ PoW pronto (difficulty: ${solution.complexity}, time: ${solution.timeMs || '?'}ms)`);
                this._state.isSolving = false;
                return true;
            }

            this._state.isSolving = false;
            this._state.lastError = 'Solução inválida';
            this._state.consecutiveFailures++;
            return false;

        } catch (error) {
            this._handleError(error, '_calculateSolution');
            this._state.isSolving = false;
            this._state.consecutiveFailures++;
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

        try {
            const url = `${this.config.API_BASE}${this.config.CHALLENGE_ENDPOINT}`;
            
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Cache-Control': 'no-cache',
                    'Accept': 'application/json',
                },
                credentials: 'include',
            });

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
                throw new Error(`Desafio inválido: expires_in=${data.expires_in}`);
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
                        nonce: String(nonce),  // 🔴 BUGFIX #3: sem sanitize
                        prefix: prefix,
                        complexity: complexity,
                        solvedAt: Date.now(),
                        timeMs: 0,
                        sync: true,
                    };
                }
            } catch (e) {
                // Ignorar
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

                            if (data.type === 'progress' || data.type === 'ready') return;

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
                                nonce: String(data.nonce),  // 🔴 BUGFIX #3: sem sanitize
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
    // 🔥 UPLOAD COM RETRY
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
                this.logger.debug(`   🔑 Complexity: ${solution.complexity}`);

                const url = `${this.config.API_BASE}${endpoint}`;
                
                // 🔴 BUGFIX #4: enviar TODOS os headers que o backend espera
                const response = await fetch(url, {
                    method: 'POST',
                    headers: {
                        'X-PoW-Challenge': solution.prefix,
                        'X-PoW-Nonce': solution.nonce,
                        'X-PoW-Complexity': String(solution.complexity),  // 🔥 NOVO
                        'X-PoW-Timestamp': String(Date.now()),            // 🔥 NOVO
                        'X-Request-ID': this._generateId(),               // 🔥 NOVO
                        'Authorization': `Bearer ${token}`,
                        'Accept': 'application/json',
                    },
                    body: formData,
                    credentials: 'include',
                });

                this.logger.debug(`📡 Resposta: ${response.status} ${response.statusText}`);

                // Ler corpo da resposta (mesmo em erro)
                let responseData = null;
                let responseText = '';
                try {
                    responseText = await response.text();
                    if (responseText) {
                        try {
                            responseData = JSON.parse(responseText);
                        } catch (e) {
                            // Não é JSON
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

                // 🔴 BUGFIX #5: LOG COMPLETO de erro 400
                if (response.status === 400) {
                    console.group('❌ ERRO 400 - DIAGNÓSTICO COMPLETO');
                    console.log('📍 URL:', url);
                    console.log('📍 Endpoint:', endpoint);
                    console.log('📍 Attempt:', `${attempt}/${maxRetries}`);
                    console.log('📤 Headers enviados:', {
                        'X-PoW-Challenge': solution.prefix,
                        'X-PoW-Nonce': solution.nonce,
                        'X-PoW-Complexity': String(solution.complexity),
                        'X-PoW-Timestamp': 'presente',
                        'X-Request-ID': 'presente',
                        'Authorization': `Bearer ${token.substring(0, 20)}...`,
                    });
                    console.log('📄 Response text:', responseText);
                    console.log('📄 Response JSON:', responseData);
                    console.log('📄 FormData keys:', Array.from(formData.keys()));
                    console.groupEnd();

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
                    
                    const errorStr = typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg);
                    this.logger.error(`❌ Erro 400: ${errorStr}`);
                    
                    // Detectar tipo
                    if (ErrorDetector.isPowError(errorStr)) {
                        throw new Error(`PoW rejeitado: ${errorStr}`);
                    }
                    
                    if (ErrorDetector.isCreditsError(errorStr)) {
                        throw new Error(`Créditos insuficientes: ${errorStr}`);
                    }
                    
                    if (ErrorDetector.isAuthError(errorStr)) {
                        throw new Error(`Erro de autenticação: ${errorStr}`);
                    }
                    
                    throw new Error(errorStr);
                }

                if (response.ok) {
                    const data = responseData || JSON.parse(responseText);
                    this.logger.info('✅ Upload com PoW concluído');
                    return data;
                }

                const errorData = responseData || {};
                throw new Error(errorData?.detail || `HTTP ${response.status}: ${response.statusText}`);

            } catch (error) {
                lastError = error;
                this.logger.error(`❌ Tentativa ${attempt} falhou:`, error.message);
                
                if (ErrorDetector.isAuthError(error.message) || ErrorDetector.isCreditsError(error.message)) {
                    throw error;
                }
                
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
        if (this._healthCheckInterval) {
            clearInterval(this._healthCheckInterval);
            this._healthCheckInterval = null;
        }
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
        console.log('✅ PoW Client v6.3 inicializado');
        return powClientInstance;
    };
    
    window.getPowDiagnostics = function() {
        return powClientInstance.getDiagnostics();
    };
    
    window.getPowStats = function() {
        return powClientInstance.getStats();
    };
    
    console.log('✅ PoW Client v6.3 global disponível');
    console.log('   🔍 Use window.powClient.getDiagnostics() para debug');
    console.log('   📊 Use window.powClient.getStats() para estatísticas');
    console.log('   🩺 Use window.powClient.isPowHealthy() para verificar saúde');
}

// ==============================================
// 🔥 MENSAGEM DE INICIALIZAÇÃO
// ==============================================

console.log('='.repeat(60));
console.log('🔥 pow-client.js v6.3 carregado (CORRIGIDO)');
console.log('   🔴 BUGFIX #1: TTL sincronizado (600s)');
console.log('   🔴 BUGFIX #2: Token JWT NÃO é mais sanitizado');
console.log('   🔴 BUGFIX #3: Nonce NÃO é mais sanitizado');
console.log('   🔴 BUGFIX #4: Headers X-PoW-Complexity/Timestamp adicionados');
console.log('   🔴 BUGFIX #5: Log completo de erro 400');
console.log('   🔴 BUGFIX #6: _sanitizeFilename só para nomes de arquivo');
console.log('   🔴 BUGFIX #7: Removido fallback /upload-auto (evita consumo duplo)');
console.log('   📡 window.powClient disponível');
console.log('='.repeat(60));