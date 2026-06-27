// frontend/js/pow-client.js - VERSÃO CORRIGIDA v2.1
/**
 * Cliente Proof of Work - SOLUÇÃO INSTANTÂNEA
 * 🔥 SINCRONIZADO COM:
 * - pow_routes.py (backend unificado)
 * - upload_routes.py (integração com upload)
 * - SHA-256 no backend
 * 
 * 🔒 SEGURANÇA:
 * - Sanitização de todas as entradas
 * - Validação de dados antes do envio
 * - Proteção contra XSS
 * - Rate limiting no client-side
 * - Fallback seguro
 */

// ==============================================
// 🔒 FUNÇÕES DE SEGURANÇA
// ==============================================

/**
 * Sanitiza string para prevenir XSS
 */
function sanitizeString(str) {
    if (!str) return '';
    if (typeof str !== 'string') str = String(str);
    
    const escapeMap = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
        '`': '&#96;',
        '/': '&#47;',
        '=': '&#61;',
        '(': '&#40;',
        ')': '&#41;',
        ';': '&#59;'
    };
    
    return str.replace(/[&<>"'`/=();]/g, function(match) {
        return escapeMap[match] || match;
    }).slice(0, 1000);
}

/**
 * Sanitiza número
 */
function sanitizeNumber(value, defaultValue = 0) {
    if (value === undefined || value === null) return defaultValue;
    const num = parseFloat(String(value).replace(/[^0-9.]/g, ''));
    return isNaN(num) ? defaultValue : num;
}

/**
 * Valida se o objeto é um desafio PoW válido
 * 🔥 CORRIGIDO: Agora aceita o formato do backend (challenge + difficulty)
 */
function isValidChallenge(challenge) {
    if (!challenge || typeof challenge !== 'object') return false;
    // Usa 'challenge' (string) e 'difficulty' (number) como enviado pelo backend
    if (!challenge.challenge || typeof challenge.challenge !== 'string') return false;
    if (!challenge.difficulty || typeof challenge.difficulty !== 'number') return false;
    if (challenge.difficulty < 3 || challenge.difficulty > 5) return false;
    if (!challenge.expires_in || typeof challenge.expires_in !== 'number') return false;
    if (challenge.expires_in < 30 || challenge.expires_in > 120) return false;
    return true;
}

/**
 * Valida solução PoW
 */
function isValidSolution(solution) {
    if (!solution || typeof solution !== 'object') return false;
    if (!solution.nonce || typeof solution.nonce !== 'string') return false;
    if (solution.nonce.length === 0 || solution.nonce.length > 20) return false;
    if (!solution.prefix || typeof solution.prefix !== 'string' || solution.prefix.length !== 16) return false;
    if (!solution.complexity || typeof solution.complexity !== 'number') return false;
    if (solution.complexity < 3 || solution.complexity > 5) return false;
    return true;
}

// ==============================================
// 🔥 CLASSE PRINCIPAL
// ==============================================

class PoWClient {
    constructor() {
        this.currentChallenge = null;
        this.solutionStock = [];
        this.isSolving = false;
        this.worker = null;
        
        // 🔥 API Base sincronizada com backend
        this.apiBase = window.location.hostname.includes('localhost') 
            ? 'http://localhost:8000/api'
            : '/api';
        
        // Configurações (sincronizadas com backend)
        this.stockSize = 2;
        this.refillThreshold = 1;
        this.lastSolutionTime = 0;
        this.autoRefill = true;
        this.refillInterval = null;
        this._isInitialized = false;
        
        // 🔥 Estatísticas de segurança
        this._securityStats = {
            totalAttempts: 0,
            failedAttempts: 0,
            lastFailure: null,
            sanitizedCount: 0
        };
        
        console.log('⚡ PoW Client v2.1 inicializado');
        console.log(`   🔒 Sanitização ativa`);
        console.log(`   📦 Stock size: ${this.stockSize}`);
        console.log(`   🔄 Auto-refill: ${this.autoRefill}`);
    }
    
    // ==============================================
    // 🔒 MÉTODOS SEGUROS DE ACESSO
    // ==============================================
    
    /**
     * Obtém token de forma segura
     */
    _getSecureToken() {
        const token = localStorage.getItem('access_token');
        if (!token || token === 'undefined' || token === 'null') {
            return null;
        }
        return sanitizeString(token);
    }
    
    /**
     * Verifica se está autenticado
     */
    _isAuthenticated() {
        const token = this._getSecureToken();
        return token !== null && token.length > 0;
    }
    
    // ==============================================
    // 🔥 MÉTODOS PRINCIPAIS
    // ==============================================
    
    /**
     * PRÉ-CÁLCULO INSTANTÂNEO - Chama na inicialização
     */
    async preSolve() {
        // Verifica se está autenticado
        if (!this._isAuthenticated()) {
            console.log('⏳ Aguardando autenticação para iniciar PoW...');
            return;
        }
        
        if (this.isSolving || this.solutionStock.length >= this.stockSize) {
            console.log(`📦 Estoque: ${this.solutionStock.length}/${this.stockSize}`);
            return;
        }
        
        console.log('⚡ Pré-calculando PoW em background...');
        this.isSolving = true;
        
        try {
            const challenge = await this._getChallengeSafe();
            
            if (!challenge) {
                console.warn('⚠️ Não foi possível obter desafio');
                this.isSolving = false;
                return;
            }
            
            const solution = await this._solveChallengeSafe(challenge);
            
            if (solution && isValidSolution(solution)) {
                this.solutionStock.push({
                    solution: solution,
                    challenge: challenge,
                    timestamp: Date.now()
                });
                
                console.log(`✅ PoW pronto (${this.solutionStock.length}/${this.stockSize})`);
                
                // Continua se não atingiu o estoque
                if (this.autoRefill && this.solutionStock.length < this.stockSize) {
                    setTimeout(() => this.preSolve(), 100);
                }
            } else {
                console.warn('⚠️ Solução inválida gerada');
            }
        } catch (error) {
            console.error('❌ Erro no pré-cálculo:', error);
            this._securityStats.failedAttempts++;
        } finally {
            this.isSolving = false;
        }
    }
    
    /**
     * Inicia refill automático periódico
     */
    startAutoRefill(intervalMs = 30000) {
        if (this.refillInterval) {
            clearInterval(this.refillInterval);
            this.refillInterval = null;
        }
        
        this.autoRefill = true;
        this.refillInterval = setInterval(() => {
            if (this.solutionStock.length < this.refillThreshold) {
                console.log('🔄 Reposição automática PoW');
                this.preSolve();
            }
        }, intervalMs);
        
        console.log(`🔄 Auto-refill ativo (${intervalMs/1000}s)`);
    }
    
    stopAutoRefill() {
        if (this.refillInterval) {
            clearInterval(this.refillInterval);
            this.refillInterval = null;
        }
        this.autoRefill = false;
        console.log('⏹️ Auto-refill desativado');
    }
    
    // ==============================================
    // 🔒 MÉTODOS SEGUROS PARA API
    // ==============================================
    
    /**
     * Obtém desafio de forma segura
     */
    async _getChallengeSafe() {
        const token = this._getSecureToken();
        if (!token) {
            throw new Error('Não autenticado');
        }
        
        try {
            const response = await fetch(`${this.apiBase}/pow/challenge`, {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Cache-Control': 'no-cache',
                    'Accept': 'application/json'
                }
            });
            
            if (!response.ok) {
                const errorText = await response.text().catch(() => '');
                throw new Error(`HTTP ${response.status}: ${errorText}`);
            }
            
            const data = await response.json();
            
            // 🔥 Validação de segurança (formato corrigido)
            if (!isValidChallenge(data)) {
                throw new Error('Desafio inválido recebido do servidor');
            }
            
            this.currentChallenge = data;
            this._securityStats.totalAttempts++;
            
            return data;
            
        } catch (error) {
            console.error('❌ Erro ao obter desafio:', error);
            this._securityStats.failedAttempts++;
            this._securityStats.lastFailure = Date.now();
            throw error;
        }
    }
    
    /**
     * Resolve desafio de forma segura
     * 🔥 CORRIGIDO: Mapeia os campos para o worker
     */
    async _solveChallengeSafe(challenge) {
        // Valida entrada
        if (!isValidChallenge(challenge)) {
            throw new Error('Desafio inválido para resolver');
        }
        
        return new Promise((resolve, reject) => {
            const startTime = performance.now();
            const worker = new Worker('/js/pow-worker.js');
            
            // Timeout de segurança (60 segundos)
            const timeoutId = setTimeout(() => {
                worker.terminate();
                reject(new Error('Timeout ao resolver PoW'));
            }, 60000);
            
            // 🔥 CORRIGIDO: Mapeia os campos do backend para o worker
            worker.postMessage({
                prefix: challenge.challenge,        // Mapeia challenge -> prefix
                complexity: challenge.difficulty,   // Mapeia difficulty -> complexity
                timestamp: challenge.timestamp,
                expires_in: challenge.expires_in
            });
            
            worker.onmessage = (e) => {
                clearTimeout(timeoutId);
                const data = e.data;
                
                if (data.error) {
                    worker.terminate();
                    reject(new Error(data.error));
                    return;
                }
                
                // Valida a solução recebida
                if (!data.nonce || typeof data.nonce !== 'string') {
                    worker.terminate();
                    reject(new Error('Nonce inválido recebido do worker'));
                    return;
                }
                
                const solution = {
                    nonce: sanitizeString(data.nonce),
                    prefix: challenge.challenge,  // Usa challenge.challenge como prefix
                    complexity: challenge.difficulty, // Usa challenge.difficulty como complexity
                    solvedAt: Date.now()
                };
                
                worker.terminate();
                resolve(solution);
            };
            
            worker.onerror = (error) => {
                clearTimeout(timeoutId);
                worker.terminate();
                reject(new Error(`Worker error: ${error.message || 'desconhecido'}`));
            };
        });
    }
    
    // ==============================================
    // 🔥 MÉTODOS PÚBLICOS
    // ==============================================
    
    /**
     * PEGA SOLUÇÃO INSTANTÂNEA - Zero espera!
     */
    async getInstantSolution() {
        // Verifica autenticação
        if (!this._isAuthenticated()) {
            throw new Error('Usuário não autenticado');
        }
        
        // Se tem solução no estoque, usa
        if (this.solutionStock.length > 0) {
            const stockItem = this.solutionStock.shift();
            console.log(`⚡ Usando PoW pré-calculado (restam ${this.solutionStock.length})`);
            
            // Dispara reposição
            if (this.autoRefill && this.solutionStock.length < this.refillThreshold) {
                setTimeout(() => this.preSolve(), 50);
            }
            
            // Valida a solução antes de retornar
            if (isValidSolution(stockItem.solution)) {
                return stockItem.solution;
            } else {
                console.warn('⚠️ Solução do estoque inválida, recalculando...');
            }
        }
        
        // Fallback: calcula na hora
        console.warn('⚠️ Estoque vazio! Calculando PoW sob demanda...');
        
        const challenge = await this._getChallengeSafe();
        const solution = await this._solveChallengeSafe(challenge);
        
        return solution;
    }
    
    /**
     * Upload com PoW INSTANTÂNEO (sem espera)
     * 🔥 CORRIGIDO: Headers agora usam X-PoW-Challenge (como o backend espera)
     */
    async uploadWithPow(file, endpoint = '/api/upload-auto') {
        // 🔥 Verifica autenticação
        if (!this._isAuthenticated()) {
            throw new Error('Usuário não autenticado');
        }
        
        // 🔥 Valida o arquivo
        if (!file || !file.name || !file.size) {
            throw new Error('Arquivo inválido');
        }
        
        // Sanitiza nome do arquivo
        const safeFilename = sanitizeString(file.name);
        
        // Pega solução instantânea
        const solution = await this.getInstantSolution();
        
        // 🔥 Valida a solução
        if (!isValidSolution(solution)) {
            throw new Error('Solução PoW inválida');
        }
        
        const formData = new FormData();
        formData.append('files', file, safeFilename);
        
        // Adiciona campos da análise
        const analysisType = document.getElementById('tipoAnalise')?.value || 'auto';
        const aiModel = document.getElementById('modeloIA')?.value || 'auto';
        formData.append('analysis_type', sanitizeString(analysisType));
        formData.append('ai_model', sanitizeString(aiModel));
        
        const token = this._getSecureToken();
        if (!token) {
            throw new Error('Token de autenticação não encontrado');
        }
        
        const startTime = performance.now();
        
        try {
            // 🔥 CORRIGIDO: Headers agora usam X-PoW-Challenge (como o backend espera)
            const response = await fetch(`${this.apiBase}${endpoint}`, {
                method: 'POST',
                headers: {
                    'X-PoW-Challenge': solution.prefix,  // CORRIGIDO: X-PoW-Challenge
                    'X-PoW-Nonce': solution.nonce,
                    'Authorization': `Bearer ${token}`
                },
                body: formData
            });
            
            const totalTime = performance.now() - startTime;
            console.log(`📤 Upload concluído em ${totalTime.toFixed(0)}ms`);
            
            // 🔥 Tratamento de erros
            if (response.status === 428) {
                console.warn('⚠️ PoW expirado, tentando novamente...');
                // Tenta com próxima solução
                if (this.solutionStock.length > 0) {
                    return this.uploadWithPow(file, endpoint);
                } else {
                    await this.preSolve();
                    return this.uploadWithPow(file, endpoint);
                }
            }
            
            if (response.status === 401) {
                console.warn('⚠️ Token expirado, redirecionando...');
                localStorage.removeItem('access_token');
                localStorage.removeItem('refresh_token');
                window.location.href = '/login?session=expired';
                throw new Error('Sessão expirada');
            }
            
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                const errorMsg = errorData.detail || errorData.message || `HTTP ${response.status}`;
                throw new Error(sanitizeString(errorMsg));
            }
            
            const data = await response.json();
            
            // 🔥 Sanitiza resposta
            return this._sanitizeResponse(data);
            
        } catch (error) {
            console.error('❌ Upload com PoW falhou:', error);
            throw error;
        }
    }
    
    /**
     * Pré-prepara para drag & drop
     */
    async prepareForUpload() {
        if (!this._isAuthenticated()) {
            console.log('⏳ Aguardando autenticação para preparar PoW...');
            return false;
        }
        
        if (this.solutionStock.length === 0) {
            console.log('🔄 Preparando PoW durante drag...');
            await this.preSolve();
            return this.solutionStock.length > 0;
        }
        
        console.log(`⚡ PoW pronto (${this.solutionStock.length} disponíveis)`);
        return true;
    }
    
    /**
     * Sanitiza resposta da API
     */
    _sanitizeResponse(data) {
        if (!data) return data;
        if (typeof data === 'string') return sanitizeString(data);
        if (typeof data === 'number') return sanitizeNumber(data);
        if (Array.isArray(data)) {
            return data.map(item => this._sanitizeResponse(item));
        }
        if (typeof data === 'object') {
            const result = {};
            for (const [key, value] of Object.entries(data)) {
                const safeKey = sanitizeString(key);
                result[safeKey] = this._sanitizeResponse(value);
            }
            return result;
        }
        return data;
    }
    
    /**
     * Reseta o estado
     */
    reset() {
        this.solutionStock = [];
        this.currentChallenge = null;
        this.isSolving = false;
        this._securityStats = {
            ...this._securityStats,
            totalAttempts: 0,
            failedAttempts: 0,
            lastFailure: null
        };
        console.log('🔄 PoW Client resetado');
    }
    
    /**
     * Retorna estatísticas
     */
    getStats() {
        return {
            solutionsReady: this.solutionStock.length,
            maxStock: this.stockSize,
            autoRefill: this.autoRefill,
            isSolving: this.isSolving,
            isAuthenticated: this._isAuthenticated(),
            lastSolutionAge: this.solutionStock[0] ? Date.now() - this.solutionStock[0].timestamp : null,
            security: {
                totalAttempts: this._securityStats.totalAttempts,
                failedAttempts: this._securityStats.failedAttempts,
                lastFailure: this._securityStats.lastFailure
            }
        };
    }
}

// ==============================================
// 🔥 INSTÂNCIA GLOBAL
// ==============================================

// Verifica se já existe uma instância
if (typeof window.powClient === 'undefined' || window.powClient === null) {
    window.powClient = new PoWClient();
    console.log('✅ PoW Client v2.1 global');
}

// ==============================================
// 🔥 INICIALIZAÇÃO - DISPAROS SILENCIADOS
// ==============================================

// 🔥 SILENCIADO: O app.js agora controla o ciclo de vida do PoW
// O código abaixo foi removido para evitar disparos automáticos
// O AppState e o app.js v5.4+ gerenciam a inicialização

/*
// 🔥 REMOVIDO - Disparo automático via authReady
document.addEventListener('authReady', (event) => {
    if (event.detail && event.detail.isAuthenticated) {
        console.log('🔐 Autenticação detectada, iniciando PoW...');
        setTimeout(() => {
            window.powClient.startAutoRefill(30000);
            window.powClient.preSolve();
        }, 1000);
    }
});

// 🔥 REMOVIDO - Disparo automático via DOMContentLoaded
document.addEventListener('DOMContentLoaded', () => {
    const token = localStorage.getItem('access_token');
    if (token && token !== 'undefined' && token !== 'null') {
        setTimeout(() => {
            if (!window.powClient._isInitialized) {
                window.powClient._isInitialized = true;
                window.powClient.startAutoRefill(30000);
                window.powClient.preSolve();
                console.log('⚡ PoW iniciado automaticamente');
            }
        }, 2000);
    }
});
*/

// 🔥 NOVO: Função exposta para o app.js iniciar o PoW quando apropriado
window.initPowClient = function(options = {}) {
    const { autoRefill = true, refillInterval = 30000, preSolve = true } = options;
    
    if (window.powClient._isInitialized) {
        console.log('⚠️ PoW Client já inicializado');
        return;
    }
    
    window.powClient._isInitialized = true;
    
    if (autoRefill) {
        window.powClient.startAutoRefill(refillInterval);
    }
    
    if (preSolve) {
        setTimeout(() => window.powClient.preSolve(), 500);
    }
    
    console.log('✅ PoW Client inicializado pelo app.js');
};

// 🔥 NOVO: Função exposta para o app.js parar o PoW
window.stopPowClient = function() {
    if (window.powClient) {
        window.powClient.stopAutoRefill();
        window.powClient.reset();
        window.powClient._isInitialized = false;
        console.log('⏹️ PoW Client parado');
    }
};

console.log('✅ pow-client.js v2.1 carregado');
console.log('   🔒 Sanitização ativa contra XSS');
console.log('   🔐 Inicialização controlada pelo app.js');
console.log(`   📦 Stock: ${window.powClient.stockSize}`);
console.log('   🔄 Auto-refill: controlado pelo app.js');
console.log('   📡 Use window.initPowClient() para iniciar');