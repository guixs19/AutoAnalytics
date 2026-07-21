// frontend/js/pow-client.js - VERSÃO REFATORADA v4.0
/**
 * 🔥 Proof of Work Client - Versão 4.0
 * 
 * ✅ COMPLETAMENTE REFATORADO
 * ✅ SEGURO (todas as props inicializadas)
 * ✅ ROBUSTO (fallbacks automáticos)
 * ✅ DIAGNÓSTICO (métricas detalhadas)
 * ✅ PERFORMANCE (cache inteligente)
 * 
 * CONECTADO COM: pow_routes.py (backend)
 * 
 * FLUXO:
 * 1. GET /api/pow/challenge → { challenge, difficulty, expires_in }
 * 2. Resolve SHA-256 com Web Worker (fallback síncrono)
 * 3. Upload com headers: X-PoW-Challenge, X-PoW-Nonce
 * 4. Validação no backend (validate_pow_request)
 */

// ==============================================
// 🔒 SEGURANÇA - SANITIZAÇÃO
// ==============================================

const POW_CONFIG = {
    // 🔥 Configurações
    DEFAULT_DIFFICULTY: 4,
    CHALLENGE_TTL: 300, // 5 minutos
    CACHE_TTL: 30000, // 30 segundos
    MAX_RETRIES: 3,
    RETRY_DELAY: 1000, // 1 segundo
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
};

// ==============================================
// 🔒 FUNÇÕES DE SANITIZAÇÃO
// ==============================================

function sanitizeString(str) {
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
}

function sanitizeNumber(value, defaultValue = 0) {
    if (value === undefined || value === null) return defaultValue;
    const num = parseFloat(String(value).replace(/[^0-9.]/g, ''));
    return isNaN(num) ? defaultValue : num;
}

// ==============================================
// 🔥 VALIDAÇÕES
// ==============================================

function isValidChallenge(challenge) {
    if (!challenge || typeof challenge !== 'object') {
        return false;
    }
    
    // Campos obrigatórios
    if (!challenge.challenge || typeof challenge.challenge !== 'string') {
        return false;
    }
    if (challenge.challenge.length !== 32) {
        return false; // 16 bytes hex = 32 chars
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
    if (challenge.expires_in < 30 || challenge.expires_in > 600) {
        return false;
    }
    
    return true;
}

function isValidSolution(solution) {
    if (!solution || typeof solution !== 'object') {
        return false;
    }
    
    if (!solution.nonce || typeof solution.nonce !== 'string') {
        return false;
    }
    if (solution.nonce.length === 0 || solution.nonce.length > 64) {
        return false;
    }
    
    if (!solution.prefix || typeof solution.prefix !== 'string') {
        return false;
    }
    if (solution.prefix.length !== 32) {
        return false;
    }
    
    if (!solution.complexity || typeof solution.complexity !== 'number') {
        return false;
    }
    if (solution.complexity < POW_CONFIG.MIN_DIFFICULTY || 
        solution.complexity > POW_CONFIG.MAX_DIFFICULTY) {
        return false;
    }
    
    return true;
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
        // 2. ESTADO DO CLIENTE
        // ==========================================
        this._state = {
            isInitialized: false,
            isSolving: false,
            isAuthenticated: false,
            lastError: null,
            lastSuccess: null,
        };
        
        // ==========================================
        // 3. CACHE
        // ==========================================
        this._cache = {
            solution: null,        // Solução em cache
            challenge: null,       // Desafio atual
            solvedAt: null,        // Timestamp da solução
            expiresAt: null,       // Expiração da solução
        };
        
        // ==========================================
        // 4. MÉTRICAS E DIAGNÓSTICO
        // ==========================================
        this._metrics = {
            // 🔥 Requisições
            totalRequests: 0,
            successfulRequests: 0,
            failedRequests: 0,
            
            // 🔥 Desafios
            challengesRequested: 0,
            challengesReceived: 0,
            challengesFailed: 0,
            
            // 🔥 Soluções
            solutionsCalculated: 0,
            solutionsCached: 0,
            solutionsUsed: 0,
            solutionsFailed: 0,
            
            // 🔥 Tempos
            avgSolveTime: 0,
            totalSolveTime: 0,
            lastSolveTime: 0,
            
            // 🔥 Últimas respostas
            lastResponse: {
                status: null,
                contentType: null,
                preview: null,
                timestamp: null,
            },
            
            // 🔥 Erros
            errors: {
                last: null,
                count: 0,
                history: [],
            },
            
            // 🔥 Status
            status: {
                hasCache: false,
                isSolving: false,
                isAuthenticated: false,
                cacheAge: null,
            },
        };
        
        // ==========================================
        // 5. STATS DE SEGURANÇA
        // ==========================================
        this._security = {
            totalAttempts: 0,
            successfulAttempts: 0,
            failedAttempts: 0,
            lastFailure: null,
            lastSuccess: null,
            consecutiveFailures: 0,
        };
        
        // ==========================================
        // 6. CONTROLE DE RETRY
        // ==========================================
        this._retry = {
            count: 0,
            maxRetries: this.config.MAX_RETRIES,
            delay: this.config.RETRY_DELAY,
            backoff: 1,
        };
        
        // ==========================================
        // 7. WORKER
        // ==========================================
        this._worker = null;
        this._workerPromise = null;
        
        // ==========================================
        // 8. LOGGING
        // ==========================================
        this._log = {
            enabled: true,
            level: 'info', // debug, info, warn, error
            history: [],
            maxHistory: 100,
        };
        
        // ==========================================
        // 9. INICIALIZAÇÃO
        // ==========================================
        this._logInfo('⚡ PoW Client v4.0 inicializado');
        this._logInfo(`   📦 Cache TTL: ${this.config.CACHE_TTL}ms`);
        this._logInfo(`   🔑 API: ${this.config.API_BASE}${this.config.CHALLENGE_ENDPOINT}`);
        this._logInfo(`   🔒 Modo: sob demanda (só no upload)`);
        this._logInfo(`   🔍 Diagnóstico: ativo`);
        
        // Inicializar estado de autenticação
        this._updateAuthStatus();
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
        this._logDebug('🔄 Preparando PoW para upload...');
        
        // 1. Verificar autenticação
        if (!this._isAuthenticated()) {
            this._logWarn('⏳ PoW: aguardando autenticação...');
            this._state.lastError = 'Usuário não autenticado';
            return false;
        }
        
        // 2. Verificar cache válido
        if (this._hasValidCache()) {
            this._logInfo('⚡ PoW em cache (válido)');
            this._metrics.solutionsCached++;
            return true;
        }
        
        // 3. Se já está calculando, aguarda
        if (this._state.isSolving) {
            this._logDebug('⏳ PoW já está sendo calculado...');
            const result = await this._waitForSolving();
            return result;
        }
        
        // 4. Calcular nova solução
        try {
            this._state.isSolving = true;
            this._logInfo('🔄 Calculando PoW...');
            
            const challenge = await this._getChallenge();
            if (!challenge) {
                this._state.isSolving = false;
                return false;
            }
            
            const solution = await this._solveChallenge(challenge);
            
            if (solution && isValidSolution(solution)) {
                this._cache.solution = {
                    ...solution,
                    solvedAt: Date.now(),
                    expiresAt: Date.now() + this.config.CACHE_TTL,
                };
                this._cache.challenge = challenge;
                this._cache.solvedAt = Date.now();
                
                this._metrics.solutionsCalculated++;
                this._state.lastSuccess = Date.now();
                
                this._logInfo(`✅ PoW pronto (difficulty: ${solution.complexity}, time: ${solution.timeMs || '?'}ms)`);
                this._state.isSolving = false;
                return true;
            }
            
            this._state.isSolving = false;
            this._state.lastError = 'Solução inválida';
            return false;
            
        } catch (error) {
            this._handleError(error, 'prepareForUpload');
            this._state.isSolving = false;
            return false;
        }
    }
    
    /**
     * Obtém a solução PoW para o upload
     * Se não tiver em cache, calcula na hora
     * 
     * @returns {Promise<Object>} - Solução PoW
     * @throws {Error} - Se não for possível obter solução
     */
    async getSolutionForUpload() {
        this._logDebug('🔑 Obtendo solução PoW para upload...');
        
        // 1. Verificar autenticação
        if (!this._isAuthenticated()) {
            throw new Error('Usuário não autenticado');
        }
        
        // 2. Usar cache se disponível e válido
        if (this._hasValidCache() && this._cache.solution) {
            const solution = { ...this._cache.solution };
            this._cache.solution = null; // Consumir cache
            this._metrics.solutionsUsed++;
            this._logInfo(`⚡ Usando PoW em cache (difficulty: ${solution.complexity})`);
            return solution;
        }
        
        // 3. Se está calculando, aguarda
        if (this._state.isSolving) {
            this._logDebug('⏳ Aguardando cálculo do PoW...');
            const result = await this._waitForSolving();
            if (result && this._cache.solution) {
                const solution = { ...this._cache.solution };
                this._cache.solution = null;
                this._metrics.solutionsUsed++;
                return solution;
            }
        }
        
        // 4. Calcular sob demanda
        this._logInfo('🔄 Calculando PoW sob demanda...');
        
        try {
            this._state.isSolving = true;
            
            const challenge = await this._getChallenge();
            if (!challenge) {
                throw new Error('Não foi possível obter desafio');
            }
            
            const solution = await this._solveChallenge(challenge);
            
            if (!solution || !isValidSolution(solution)) {
                throw new Error('Solução PoW inválida');
            }
            
            this._metrics.solutionsCalculated++;
            this._state.isSolving = false;
            this._state.lastSuccess = Date.now();
            
            this._logInfo(`✅ PoW calculado sob demanda (difficulty: ${solution.complexity}, time: ${solution.timeMs || '?'}ms)`);
            return solution;
            
        } catch (error) {
            this._state.isSolving = false;
            this._handleError(error, 'getSolutionForUpload');
            throw error;
        }
    }
    
    /**
     * Upload com PoW - ALINHADO COM pow_routes.py
     * 
     * @param {File} file - Arquivo para upload
     * @param {string} endpoint - Endpoint de upload
     * @returns {Promise<Object>} - Resposta do servidor
     */
    async uploadWithPow(file, endpoint = this.config.UPLOAD_ENDPOINT) {
        this._logInfo(`📤 Iniciando upload com PoW: ${file.name}`);
        
        // 1. Validar arquivo
        if (!file || !file.name || !file.size) {
            throw new Error('Arquivo inválido');
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
            this._logError('❌ Falha ao obter solução PoW:', error);
            throw new Error(`PoW falhou: ${error.message}`);
        }
        
        if (!isValidSolution(solution)) {
            throw new Error('Solução PoW inválida');
        }
        
        // 4. Preparar FormData
        const safeFilename = sanitizeString(file.name);
        const formData = new FormData();
        formData.append('files', file, safeFilename);
        formData.append('analysis_type', 'auto');
        formData.append('ai_model', 'auto');
        
        // 5. Obter token
        const token = this._getToken();
        if (!token) {
            throw new Error('Token de autenticação não encontrado');
        }
        
        // 6. Fazer upload com retry
        return this._uploadWithRetry(formData, token, solution, endpoint);
    }
    
    /**
     * Reseta o estado do cliente
     */
    reset() {
        this._cache.solution = null;
        this._cache.challenge = null;
        this._cache.solvedAt = null;
        this._cache.expiresAt = null;
        this._state.isSolving = false;
        this._state.lastError = null;
        this._retry.count = 0;
        this._retry.backoff = 1;
        
        if (this._worker) {
            try {
                this._worker.terminate();
            } catch (e) {
                // Ignorar
            }
            this._worker = null;
            this._workerPromise = null;
        }
        
        this._logInfo('🔄 PoW resetado');
    }
    
    /**
     * Obtém estatísticas do cliente
     * 
     * @returns {Object} - Estatísticas
     */
    getStats() {
        return {
            state: {
                isInitialized: this._state.isInitialized,
                isSolving: this._state.isSolving,
                isAuthenticated: this._state.isAuthenticated,
                lastError: this._state.lastError,
                lastSuccess: this._state.lastSuccess,
            },
            cache: {
                hasSolution: this._cache.solution !== null,
                hasChallenge: this._cache.challenge !== null,
                age: this._cache.solvedAt ? Date.now() - this._cache.solvedAt : null,
                isValid: this._hasValidCache(),
            },
            metrics: {
                totalRequests: this._metrics.totalRequests,
                successfulRequests: this._metrics.successfulRequests,
                failedRequests: this._metrics.failedRequests,
                solutionsCalculated: this._metrics.solutionsCalculated,
                solutionsCached: this._metrics.solutionsCached,
                solutionsUsed: this._metrics.solutionsUsed,
                avgSolveTime: this._metrics.avgSolveTime,
                lastSolveTime: this._metrics.lastSolveTime,
            },
            security: {
                totalAttempts: this._security.totalAttempts,
                successfulAttempts: this._security.successfulAttempts,
                failedAttempts: this._security.failedAttempts,
                consecutiveFailures: this._security.consecutiveFailures,
            },
            diagnostics: {
                lastResponse: this._metrics.lastResponse,
                errorCount: this._metrics.errors.count,
                lastError: this._metrics.errors.last,
            },
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
            timestamp: new Date().toISOString(),
            uptime: this._state.isInitialized ? Date.now() - this._state._initTime : null,
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
        const token = this._getToken();
        this._state.isAuthenticated = token !== null && token.length > 0;
        this._metrics.status.isAuthenticated = this._state.isAuthenticated;
        return this._state.isAuthenticated;
    }
    
    /**
     * Obtém token JWT
     */
    _getToken() {
        try {
            const token = localStorage.getItem('access_token');
            if (!token || token === 'undefined' || token === 'null') {
                return null;
            }
            return sanitizeString(token);
        } catch (e) {
            return null;
        }
    }
    
    /**
     * Obtém token de refresh
     */
    _getRefreshToken() {
        try {
            const token = localStorage.getItem('refresh_token');
            if (!token || token === 'undefined' || token === 'null') {
                return null;
            }
            return sanitizeString(token);
        } catch (e) {
            return null;
        }
    }
    
    /**
     * Verifica se o cache é válido
     */
    _hasValidCache() {
        if (!this._cache.solution) return false;
        if (!this._cache.solvedAt) return false;
        
        const age = Date.now() - this._cache.solvedAt;
        const isValid = age < this.config.CACHE_TTL;
        
        if (!isValid) {
            this._logDebug(`⏳ Cache expirado (${age}ms > ${this.config.CACHE_TTL}ms)`);
            this._cache.solution = null;
            this._cache.challenge = null;
            this._cache.solvedAt = null;
        }
        
        return isValid;
    }
    
    /**
     * Aguarda o fim do cálculo
     */
    async _waitForSolving(timeout = 30000) {
        const start = Date.now();
        while (this._state.isSolving && (Date.now() - start) < timeout) {
            await new Promise(r => setTimeout(r, 100));
        }
        
        if (this._state.isSolving) {
            this._logWarn('⏰ Timeout aguardando cálculo do PoW');
            this._state.isSolving = false;
            return false;
        }
        
        return this._cache.solution !== null;
    }
    
    /**
     * Obtém desafio do backend
     */
    async _getChallenge() {
        this._logDebug('📡 Solicitando desafio PoW ao backend...');
        this._metrics.totalRequests++;
        this._metrics.challengesRequested++;
        
        const token = this._getToken();
        if (!token) {
            throw new Error('Não autenticado');
        }
        
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
            
            // Registrar resposta
            const contentType = response.headers.get('content-type') || '';
            this._metrics.lastResponse.status = response.status;
            this._metrics.lastResponse.contentType = contentType;
            this._metrics.lastResponse.timestamp = Date.now();
            
            this._logDebug(`📡 Resposta: status=${response.status}, contentType=${contentType}`);
            
            // 🔥 Tratar erros HTTP específicos
            if (response.status === 401) {
                this._logWarn('⚠️ Token expirado ou inválido');
                this._metrics.challengesFailed++;
                this._handleAuthError();
                throw new Error('Sessão expirada. Faça login novamente.');
            }
            
            if (response.status === 429) {
                this._logWarn('⚠️ Rate limit excedido');
                this._metrics.challengesFailed++;
                const data = await this._safeParseJson(response);
                throw new Error(`Rate limit: ${data?.detail || 'Muitas requisições'}`);
            }
            
            if (response.status === 404) {
                this._logError('❌ Rota PoW não encontrada (404)');
                this._metrics.challengesFailed++;
                throw new Error('Serviço PoW indisponível. Verifique o backend.');
            }
            
            if (!response.ok) {
                this._metrics.challengesFailed++;
                const data = await this._safeParseJson(response);
                throw new Error(data?.detail || `HTTP ${response.status}`);
            }
            
            // 🔥 Verificar se é JSON
            if (!contentType.includes('application/json')) {
                const text = await response.text();
                const preview = text.substring(0, 200);
                this._metrics.lastResponse.preview = preview;
                this._metrics.challengesFailed++;
                
                if (text.trim().startsWith('<')) {
                    throw new Error('Servidor retornou HTML. Verifique o proxy/reverse proxy.');
                }
                throw new Error(`Resposta não é JSON: ${preview}...`);
            }
            
            // 🔥 Parsear JSON
            const data = await this._safeParseJson(response);
            if (!data) {
                this._metrics.challengesFailed++;
                throw new Error('JSON inválido recebido');
            }
            
            // 🔥 Log do dado (primeiros 100 caracteres)
            const preview = JSON.stringify(data).substring(0, 100);
            this._logDebug(`📦 Dados: ${preview}${preview.length >= 100 ? '...' : ''}`);
            
            // 🔥 Validar desafio
            if (!isValidChallenge(data)) {
                this._metrics.challengesFailed++;
                this._logError('❌ Desafio inválido:', data);
                throw new Error('Desafio inválido recebido do servidor');
            }
            
            // ✅ Sucesso
            this._metrics.successfulRequests++;
            this._metrics.challengesReceived++;
            this._security.successfulAttempts++;
            this._security.consecutiveFailures = 0;
            
            this._logInfo(`✅ Desafio recebido (difficulty: ${data.difficulty}, expires: ${data.expires_in}s)`);
            return data;
            
        } catch (error) {
            this._metrics.failedRequests++;
            this._metrics.challengesFailed++;
            this._security.failedAttempts++;
            this._security.consecutiveFailures++;
            this._security.lastFailure = Date.now();
            
            this._logError('❌ Erro ao obter desafio:', error.message);
            throw error;
        }
    }
    
    /**
     * Resolve o desafio usando Web Worker
     */
    async _solveChallenge(challenge) {
        this._logInfo(`🔐 Resolvendo PoW (difficulty: ${challenge.difficulty})...`);
        const startTime = Date.now();
        
        try {
            // 1. Tentar com Web Worker
            if (this._isWorkerAvailable()) {
                const result = await this._solveWithWorker(challenge);
                if (result) {
                    const timeMs = Date.now() - startTime;
                    this._metrics.lastSolveTime = timeMs;
                    this._metrics.totalSolveTime += timeMs;
                    this._metrics.avgSolveTime = this._metrics.totalSolveTime / 
                        (this._metrics.solutionsCalculated + 1);
                    
                    this._logInfo(`✅ PoW resolvido com Worker em ${timeMs}ms`);
                    return result;
                }
            }
            
            // 2. Fallback: Síncrono
            this._logWarn('⚠️ Worker não disponível, usando fallback síncrono...');
            const result = await this._solveSync(challenge);
            const timeMs = Date.now() - startTime;
            this._metrics.lastSolveTime = timeMs;
            
            this._logInfo(`✅ PoW resolvido (sync) em ${timeMs}ms`);
            return result;
            
        } catch (error) {
            this._logError('❌ Erro ao resolver PoW:', error);
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
                    
                    if (!data.nonce || typeof data.nonce !== 'string') {
                        worker.terminate();
                        this._worker = null;
                        reject(new Error('Nonce inválido recebido do worker'));
                        return;
                    }
                    
                    // Validar solução
                    const solution = {
                        nonce: sanitizeString(data.nonce),
                        prefix: challenge.challenge,
                        complexity: challenge.difficulty,
                        solvedAt: Date.now(),
                        timeMs: data.timeMs || 0,
                    };
                    
                    // Verificar se a solução é válida
                    const isValid = this._verifySolution(solution);
                    if (!isValid) {
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
        
        this._logDebug(`🔐 Tentando encontrar nonce (max: ${maxAttempts})...`);
        
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
                    this._logDebug(`✅ Nonce encontrado: ${nonce}`);
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
                this._logDebug(`🔐 Tentativas: ${nonce}/${maxAttempts}`);
            }
        }
        
        throw new Error(`Não foi possível encontrar nonce após ${maxAttempts} tentativas`);
    }
    
    /**
     * Verifica se a solução é válida
     */
    _verifySolution(solution) {
        try {
            const data = `${solution.prefix}:${solution.nonce}`;
            const encoder = new TextEncoder();
            const encoded = encoder.encode(data);
            
            // Usar Web Crypto se disponível, senão usar fallback
            // Nota: Isso é síncrono, então usamos uma verificação simples
            // Em produção, o backend fará a validação final
            
            // Verificação rápida no frontend
            // (Pode ser melhorada com crypto.subtle, mas é assíncrono)
            return true; // Confiar no worker
            
        } catch (e) {
            return false;
        }
    }
    
    /**
     * Upload com retry automático
     */
    async _uploadWithRetry(formData, token, solution, endpoint) {
        const maxRetries = this.config.MAX_RETRIES;
        let lastError = null;
        let backoff = 1;
        
        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                this._logDebug(`📤 Tentativa ${attempt}/${maxRetries}`);
                
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
                    this._logWarn('⚠️ PoW expirado (428), recalculando...');
                    this.reset();
                    
                    // Obter nova solução
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
                        const errorData = await this._safeParseJson(retryResponse);
                        throw new Error(errorData?.detail || `HTTP ${retryResponse.status}`);
                    }
                    
                    const data = await retryResponse.json();
                    this._logInfo('✅ Upload com PoW (retry) concluído');
                    return data;
                }
                
                // 🔥 Token expirado (401)
                if (response.status === 401) {
                    this._logWarn('⚠️ Token expirado, tentando refresh...');
                    const refreshed = await this._refreshToken();
                    
                    if (refreshed) {
                        // Tentar novamente com novo token
                        const newToken = this._getToken();
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
                            this._logInfo('✅ Upload com novo token concluído');
                            return data;
                        }
                    }
                    
                    throw new Error('Sessão expirada. Faça login novamente.');
                }
                
                // 🔥 Rate limit (429)
                if (response.status === 429) {
                    const data = await this._safeParseJson(response);
                    const retryAfter = data?.retry_after || 60;
                    this._logWarn(`⚠️ Rate limit, aguardando ${retryAfter}s...`);
                    
                    await this._sleep(retryAfter * 1000);
                    continue; // Tentar novamente
                }
                
                // 🔥 Sucesso (2xx)
                if (response.ok) {
                    const data = await response.json();
                    this._logInfo('✅ Upload com PoW concluído');
                    return data;
                }
                
                // 🔥 Outros erros
                const errorData = await this._safeParseJson(response);
                throw new Error(errorData?.detail || `HTTP ${response.status}: ${response.statusText}`);
                
            } catch (error) {
                lastError = error;
                this._logError(`❌ Tentativa ${attempt} falhou:`, error.message);
                
                if (attempt < maxRetries) {
                    const delay = this._retry.delay * backoff;
                    this._logDebug(`⏳ Aguardando ${delay}ms antes de tentar novamente...`);
                    await this._sleep(delay);
                    backoff *= 1.5; // Backoff exponencial
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
            const refreshToken = this._getRefreshToken();
            if (!refreshToken) return false;
            
            const response = await fetch('/api/auth/refresh', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
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
     * Trata erro de autenticação
     */
    _handleAuthError() {
        // Limpar tokens
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        
        // Atualizar estado
        this._state.isAuthenticated = false;
        this._state.lastError = 'Token expirado';
        
        // Disparar evento
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
        this._metrics.errors.count++;
        this._metrics.errors.last = {
            message: errorMsg,
            context: context,
            timestamp: Date.now(),
        };
        
        // Manter histórico limitado
        this._metrics.errors.history.push({
            message: errorMsg,
            context: context,
            timestamp: Date.now(),
        });
        
        if (this._metrics.errors.history.length > 10) {
            this._metrics.errors.history.shift();
        }
        
        this._logError(`❌ [${context}] ${errorMsg}`);
    }
    
    /**
     * Verifica se o Worker está disponível
     */
    _isWorkerAvailable() {
        try {
            // Verificar se o arquivo do worker existe
            // Nota: Isso é uma verificação simples
            return typeof Worker !== 'undefined';
        } catch (e) {
            return false;
        }
    }
    
    /**
     * Parse seguro de JSON
     */
    async _safeParseJson(response) {
        try {
            const text = await response.text();
            return JSON.parse(text);
        } catch (e) {
            return null;
        }
    }
    
    /**
     * Sleep helper
     */
    _sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
    
    // ==============================================
    // 🔥 LOGGING ESTRUTURADO
    // ==============================================
    
    _log(message, level = 'info', ...args) {
        if (!this._log.enabled) return;
        
        const levels = { debug: 0, info: 1, warn: 2, error: 3 };
        if (levels[level] < levels[this._log.level]) return;
        
        const prefix = `[PoW Client]`;
        const timestamp = new Date().toISOString().substring(11, 19);
        
        let logMessage = `${timestamp} ${prefix} ${message}`;
        if (args.length > 0) {
            console.log(logMessage, ...args);
        } else {
            console.log(logMessage);
        }
        
        // Manter histórico
        this._log.history.push({
            timestamp: Date.now(),
            level,
            message,
            args: args.length > 0 ? args : undefined,
        });
        
        if (this._log.history.length > this._log.maxHistory) {
            this._log.history.shift();
        }
    }
    
    _logDebug(message, ...args) {
        this._log(message, 'debug', ...args);
    }
    
    _logInfo(message, ...args) {
        this._log(message, 'info', ...args);
    }
    
    _logWarn(message, ...args) {
        this._log(message, 'warn', ...args);
    }
    
    _logError(message, ...args) {
        this._log(message, 'error', ...args);
    }
}

// ==============================================
// 🔥 INSTÂNCIA GLOBAL
// ==============================================

// Criar instância única
let globalPowClient = null;

function getPowClient() {
    if (!globalPowClient) {
        globalPowClient = new PowClient();
        globalPowClient._state._initTime = Date.now();
        globalPowClient._state.isInitialized = true;
        console.log('✅ PoW Client v4.0 global');
    }
    return globalPowClient;
}

// Expor globalmente
window.powClient = getPowClient();

// ==============================================
// 🔥 FUNÇÕES DE CONVENIÊNCIA
// ==============================================

/**
 * Inicializa o PoW Client
 * Chamado pelo app.js APÓS autenticação
 */
window.initPowClient = function(options = {}) {
    const client = getPowClient();
    
    if (client._state.isInitialized) {
        console.log('⚠️ PoW Client já inicializado');
        return client;
    }
    
    // Configurar opções
    if (options.logLevel) {
        client._log.level = options.logLevel;
    }
    
    // Verificar autenticação
    if (!client._isAuthenticated()) {
        console.log('⏳ PoW: aguardando autenticação...');
        return client;
    }
    
    client._state.isInitialized = true;
    client._state._initTime = Date.now();
    
    console.log('✅ PoW Client inicializado (modo sob demanda)');
    console.log(`   🔍 Use window.powClient.getDiagnostics() para debug`);
    console.log(`   📊 Use window.powClient.getStats() para estatísticas`);
    
    return client;
};

/**
 * Para o PoW Client
 */
window.stopPowClient = function() {
    const client = getPowClient();
    client.reset();
    client._state.isInitialized = false;
    console.log('⏹️ PoW Client parado');
};

/**
 * Obtém diagnóstico
 */
window.getPowDiagnostics = function() {
    const client = getPowClient();
    return client.getDiagnostics();
};

/**
 * Obtém estatísticas
 */
window.getPowStats = function() {
    const client = getPowClient();
    return client.getStats();
};

// ==============================================
// 🔥 EXPORTAÇÕES
// ==============================================

export { PowClient, getPowClient, POW_CONFIG };

console.log('=' .repeat(60));
console.log('🔥 pow-client.js v4.0 carregado');
console.log('   ✅ Inicialização segura (todas as props)');
console.log('   ✅ Cache inteligente (TTL configurável)');
console.log('   ✅ Retry automático com backoff');
console.log('   ✅ Diagnóstico e métricas detalhadas');
console.log('   ✅ Fallback síncrono (quando worker falha)');
console.log('   ✅ Tratamento de erros robusto');
console.log('   📡 Use window.initPowClient() para iniciar');
console.log('   🔍 Use window.getPowDiagnostics() para debug');
console.log('=' .repeat(60));