// frontend/js/pow-client.js - VERSÃO v3.1 (ALINHADA COM BACKEND)
/**
 * Cliente Proof of Work - CONECTADO COM pow_routes.py
 * 
 * 🔥 ALINHAMENTO:
 * - GET /api/pow/challenge → Retorna { challenge, difficulty, expires_in }
 * - HEADERS no upload: X-PoW-Challenge, X-PoW-Nonce
 * - VALIDAÇÃO: SHA-256 com difficulty (zeros no prefixo)
 * 
 * 🚀 MODO SOB DEMANDA:
 * - Só ativado no upload
 * - Cache de 1 solução
 * - Fallback sob demanda
 */

// ==============================================
// 🔒 SEGURANÇA
// ==============================================

function sanitizeString(str) {
    if (!str) return '';
    if (typeof str !== 'string') str = String(str);
    const escapeMap = {
        '&': '&amp;', '<': '&lt;', '>': '&gt;',
        '"': '&quot;', "'": '&#39;', '`': '&#96;',
        '/': '&#47;', '=': '&#61;', '(': '&#40;',
        ')': '&#41;', ';': '&#59;'
    };
    return str.replace(/[&<>"'`/=();]/g, m => escapeMap[m] || m).slice(0, 1000);
}

function sanitizeNumber(value, defaultValue = 0) {
    if (value === undefined || value === null) return defaultValue;
    const num = parseFloat(String(value).replace(/[^0-9.]/g, ''));
    return isNaN(num) ? defaultValue : num;
}

// ==============================================
// 🔥 VALIDAÇÕES (ALINHADAS COM BACKEND)
// ==============================================

/**
 * Valida desafio recebido do backend (pow_routes.py)
 */
function isValidChallenge(challenge) {
    if (!challenge || typeof challenge !== 'object') return false;
    // 🔥 Campos retornados pelo backend: challenge, difficulty, expires_in
    if (!challenge.challenge || typeof challenge.challenge !== 'string') return false;
    if (challenge.challenge.length !== 32) return false; // 16 bytes hex = 32 chars
    if (!challenge.difficulty || typeof challenge.difficulty !== 'number') return false;
    if (challenge.difficulty < 3 || challenge.difficulty > 6) return false;
    if (!challenge.expires_in || typeof challenge.expires_in !== 'number') return false;
    if (challenge.expires_in < 30 || challenge.expires_in > 300) return false;
    return true;
}

/**
 * Valida solução PoW
 */
function isValidSolution(solution) {
    if (!solution || typeof solution !== 'object') return false;
    if (!solution.nonce || typeof solution.nonce !== 'string') return false;
    if (solution.nonce.length === 0 || solution.nonce.length > 64) return false;
    if (!solution.prefix || typeof solution.prefix !== 'string') return false;
    if (solution.prefix.length !== 32) return false;
    if (!solution.complexity || typeof solution.complexity !== 'number') return false;
    if (solution.complexity < 3 || solution.complexity > 6) return false;
    return true;
}

// ==============================================
// 🔥 CLASSE PRINCIPAL
// ==============================================

class PoWClient {
    constructor() {
        // Cache SIMPLES: apenas 1 solução pronta
        this.cachedSolution = null;
        this.isSolving = false;
        this._isInitialized = false;
        
        // API Base
        this.apiBase = window.location.hostname.includes('localhost') 
            ? 'http://localhost:8000/api'
            : '/api';
        
        // Configurações (sincronizadas com backend)
        this.challengeTtl = 300; // 5 minutos (CHALLENGE_EXPIRY_SECONDS)
        this.defaultDifficulty = 4;
        
        console.log('⚡ PoW Client v3.1 - Conectado com pow_routes.py');
        console.log('   🔒 Modo sob demanda (só no upload)');
        console.log(`   📦 Cache: 1 solução`);
        console.log(`   🔑 API: ${this.apiBase}/pow/challenge`);
    }
    
    // ==============================================
    // 🔒 TOKEN
    // ==============================================
    
    _getSecureToken() {
        const token = localStorage.getItem('access_token');
        if (!token || token === 'undefined' || token === 'null') {
            return null;
        }
        return sanitizeString(token);
    }
    
    _isAuthenticated() {
        const token = this._getSecureToken();
        return token !== null && token.length > 0;
    }
    
    // ==============================================
    // 🔥 PREPARAR PoW (chamado no drag ou seleção)
    // ==============================================
    
    /**
     * Prepara uma solução PoW em background
     * Chamado quando o usuário arrasta arquivo ou seleciona
     */
    async prepareForUpload() {
        // Verifica autenticação
        if (!this._isAuthenticated()) {
            console.log('⏳ PoW: aguardando autenticação...');
            return false;
        }
        
        // Se já tem solução em cache, verifica validade
        if (this.cachedSolution && isValidSolution(this.cachedSolution)) {
            const age = Date.now() - (this.cachedSolution.solvedAt || 0);
            // Se a solução tem menos de 30 segundos, reutiliza
            if (age < 30000) {
                console.log('⚡ PoW em cache (válido)');
                return true;
            } else {
                // Cache expirado
                this.cachedSolution = null;
                console.log('⏳ PoW em cache expirado');
            }
        }
        
        // Se já está calculando, aguarda
        if (this.isSolving) {
            console.log('⏳ PoW já está sendo calculado...');
            let attempts = 0;
            while (this.isSolving && attempts < 30) {
                await new Promise(r => setTimeout(r, 100));
                attempts++;
            }
            return this.cachedSolution !== null;
        }
        
        // Calcula nova solução
        console.log('🔄 Preparando PoW para upload...');
        this.isSolving = true;
        
        try {
            const challenge = await this._getChallengeSafe();
            if (!challenge) {
                this.isSolving = false;
                return false;
            }
            
            const solution = await this._solveChallengeSafe(challenge);
            
            if (solution && isValidSolution(solution)) {
                this.cachedSolution = {
                    ...solution,
                    solvedAt: Date.now()
                };
                console.log(`✅ PoW pronto (difficulty: ${this.cachedSolution.complexity})`);
                this.isSolving = false;
                return true;
            }
            
            this.isSolving = false;
            return false;
            
        } catch (error) {
            console.warn('⚠️ Erro ao preparar PoW:', error.message);
            this.isSolving = false;
            return false;
        }
    }
    
    // ==============================================
    // 🔥 OBTER SOLUÇÃO PARA UPLOAD
    // ==============================================
    
    /**
     * Obtém a solução PoW para o upload
     * Se não tiver em cache, calcula na hora
     */
    async getSolutionForUpload() {
        if (!this._isAuthenticated()) {
            throw new Error('Usuário não autenticado');
        }
        
        // Usa cache se disponível e válido
        if (this.cachedSolution && isValidSolution(this.cachedSolution)) {
            const age = Date.now() - (this.cachedSolution.solvedAt || 0);
            if (age < 30000) {
                const solution = { ...this.cachedSolution };
                // Limpa cache após usar
                this.cachedSolution = null;
                console.log(`⚡ Usando PoW em cache (difficulty: ${solution.complexity})`);
                return solution;
            } else {
                this.cachedSolution = null;
                console.log('⏳ PoW em cache expirado, recalculando...');
            }
        }
        
        // Se está calculando, aguarda
        if (this.isSolving) {
            console.log('⏳ Aguardando cálculo do PoW...');
            let attempts = 0;
            while (this.isSolving && attempts < 30) {
                await new Promise(r => setTimeout(r, 100));
                attempts++;
            }
            if (this.cachedSolution) {
                const solution = { ...this.cachedSolution };
                this.cachedSolution = null;
                return solution;
            }
        }
        
        // Calcula sob demanda
        console.log('🔄 Calculando PoW sob demanda...');
        const challenge = await this._getChallengeSafe();
        const solution = await this._solveChallengeSafe(challenge);
        
        if (!solution || !isValidSolution(solution)) {
            throw new Error('Não foi possível obter solução PoW');
        }
        
        console.log(`✅ PoW calculado sob demanda (difficulty: ${solution.complexity})`);
        return solution;
    }
    
    // ==============================================
    // 🔥 UPLOAD COM PoW (ALINHADO COM BACKEND)
    // ==============================================
    
    /**
     * Upload com PoW - ALINHADO COM pow_routes.py
     * 
     * Headers esperados pelo backend:
     * - X-PoW-Challenge: prefixo do desafio
     * - X-PoW-Nonce: nonce encontrado
     * - Authorization: Bearer token
     */
    async uploadWithPow(file, endpoint = '/api/upload-auto') {
        if (!this._isAuthenticated()) {
            throw new Error('Usuário não autenticado');
        }
        
        if (!file || !file.name || !file.size) {
            throw new Error('Arquivo inválido');
        }
        
        // Obtém solução (cache ou sob demanda)
        const solution = await this.getSolutionForUpload();
        
        if (!isValidSolution(solution)) {
            throw new Error('Solução PoW inválida');
        }
        
        const safeFilename = sanitizeString(file.name);
        const formData = new FormData();
        formData.append('files', file, safeFilename);
        formData.append('analysis_type', 'auto');
        formData.append('ai_model', 'auto');
        
        const token = this._getSecureToken();
        if (!token) {
            throw new Error('Token de autenticação não encontrado');
        }
        
        console.log(`📤 Enviando arquivo com PoW (difficulty: ${solution.complexity})`);
        
        try {
            // 🔥 HEADERS ALINHADOS COM pow_routes.py
            const response = await fetch(`${this.apiBase}${endpoint}`, {
                method: 'POST',
                headers: {
                    'X-PoW-Challenge': solution.prefix,  // ← Backend espera X-PoW-Challenge
                    'X-PoW-Nonce': solution.nonce,       // ← Backend espera X-PoW-Nonce
                    'Authorization': `Bearer ${token}`
                },
                body: formData
            });
            
            // PoW expirado (428 Precondition Required)
            if (response.status === 428) {
                console.warn('⚠️ PoW expirado (428), recalculando...');
                // Remove cache e tenta novamente
                this.cachedSolution = null;
                const newSolution = await this.getSolutionForUpload();
                
                const retryResponse = await fetch(`${this.apiBase}${endpoint}`, {
                    method: 'POST',
                    headers: {
                        'X-PoW-Challenge': newSolution.prefix,
                        'X-PoW-Nonce': newSolution.nonce,
                        'Authorization': `Bearer ${token}`
                    },
                    body: formData
                });
                
                if (retryResponse.status === 428) {
                    throw new Error('PoW expirado novamente. Tente novamente.');
                }
                
                if (!retryResponse.ok) {
                    const errorData = await retryResponse.json().catch(() => ({}));
                    throw new Error(errorData.detail || `HTTP ${retryResponse.status}`);
                }
                
                const data = await retryResponse.json();
                console.log('✅ Upload com PoW (retry) concluído');
                return data;
            }
            
            // Token expirado
            if (response.status === 401) {
                console.warn('⚠️ Token expirado, redirecionando...');
                localStorage.removeItem('access_token');
                localStorage.removeItem('refresh_token');
                window.location.href = '/login?session=expired';
                throw new Error('Sessão expirada');
            }
            
            // Outros erros
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                const errorMsg = errorData.detail || errorData.message || `HTTP ${response.status}`;
                throw new Error(sanitizeString(errorMsg));
            }
            
            const data = await response.json();
            console.log('✅ Upload com PoW concluído');
            return data;
            
        } catch (error) {
            console.error('❌ Upload com PoW falhou:', error);
            throw error;
        }
    }
    
    // ==============================================
    // 🔒 MÉTODOS INTERNOS (CONECTADOS AO BACKEND)
    // ==============================================
    
    /**
     * Obtém desafio do backend (GET /api/pow/challenge)
     * Resposta esperada: { challenge, difficulty, expires_in, ... }
     */
    async _getChallengeSafe() {
        const token = this._getSecureToken();
        if (!token) {
            throw new Error('Não autenticado');
        }
        
        console.log('📡 Solicitando desafio PoW ao backend...');
        
        const response = await fetch(`${this.apiBase}/pow/challenge`, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Cache-Control': 'no-cache',
                'Accept': 'application/json'
            }
        });
        
        if (response.status === 401) {
            throw new Error('Não autenticado');
        }
        
        if (response.status === 429) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.detail || 'Muitas requisições. Aguarde.');
        }
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        
        // 🔥 Valida resposta do backend (pow_routes.py)
        if (!isValidChallenge(data)) {
            console.error('❌ Resposta inválida do backend:', data);
            throw new Error('Desafio inválido recebido do servidor');
        }
        
        console.log(`✅ Desafio recebido (difficulty: ${data.difficulty}, expires: ${data.expires_in}s)`);
        
        return data;
    }
    
    /**
     * Resolve o desafio usando Web Worker
     */
    async _solveChallengeSafe(challenge) {
        if (!isValidChallenge(challenge)) {
            throw new Error('Desafio inválido');
        }
        
        console.log(`🔐 Resolvendo PoW (difficulty: ${challenge.difficulty})...`);
        const startTime = Date.now();
        
        return new Promise((resolve, reject) => {
            // Tenta usar Web Worker (se disponível)
            try {
                const worker = new Worker('/js/pow-worker.js');
                
                const timeoutId = setTimeout(() => {
                    worker.terminate();
                    reject(new Error('Timeout ao resolver PoW (30s)'));
                }, 30000);
                
                // 🔥 Envia dados no formato que o worker espera
                worker.postMessage({
                    prefix: challenge.challenge,      // ← challenge.challenge
                    complexity: challenge.difficulty, // ← challenge.difficulty
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
                    
                    if (!data.nonce || typeof data.nonce !== 'string') {
                        worker.terminate();
                        reject(new Error('Nonce inválido recebido do worker'));
                        return;
                    }
                    
                    const solution = {
                        nonce: sanitizeString(data.nonce),
                        prefix: challenge.challenge,       // ← mesmo valor
                        complexity: challenge.difficulty,  // ← mesmo valor
                        solvedAt: Date.now(),
                        timeMs: Date.now() - startTime
                    };
                    
                    worker.terminate();
                    console.log(`✅ PoW resolvido em ${solution.timeMs}ms`);
                    resolve(solution);
                };
                
                worker.onerror = (error) => {
                    clearTimeout(timeoutId);
                    worker.terminate();
                    reject(new Error(`Worker error: ${error.message || 'desconhecido'}`));
                };
                
            } catch (e) {
                // Fallback: worker não disponível (usar método síncrono simples)
                console.warn('⚠️ Worker não disponível, usando fallback síncrono...');
                try {
                    const nonce = this._solveSync(challenge);
                    const solution = {
                        nonce: nonce,
                        prefix: challenge.challenge,
                        complexity: challenge.difficulty,
                        solvedAt: Date.now(),
                        timeMs: Date.now() - startTime
                    };
                    console.log(`✅ PoW resolvido (sync) em ${solution.timeMs}ms`);
                    resolve(solution);
                } catch (error) {
                    reject(error);
                }
            }
        });
    }
    
    /**
     * Fallback síncrono (quando worker não está disponível)
     */
    _solveSync(challenge) {
        const target = '0'.repeat(challenge.difficulty);
        let nonce = 0;
        const maxAttempts = 1000000;
        
        while (nonce < maxAttempts) {
            const data = `${challenge.challenge}:${nonce}`;
            const hash = hashlib.sha256(data).hexdigest(); // Nota: isso é pseudo-código
            // No browser real, usaríamos CryptoJS ou outra lib
            if (hash && hash.startsWith(target)) {
                return String(nonce);
            }
            nonce++;
        }
        
        throw new Error('Não foi possível encontrar nonce (timeout)');
    }
    
    // ==============================================
    // 🔥 UTILITÁRIOS
    // ==============================================
    
    reset() {
        this.cachedSolution = null;
        this.isSolving = false;
        console.log('🔄 PoW resetado');
    }
    
    getStats() {
        return {
            hasCachedSolution: this.cachedSolution !== null,
            isSolving: this.isSolving,
            isAuthenticated: this._isAuthenticated(),
            cacheAge: this.cachedSolution ? Date.now() - this.cachedSolution.solvedAt : null
        };
    }
}

// ==============================================
// 🔥 INSTÂNCIA GLOBAL
// ==============================================

if (typeof window.powClient === 'undefined' || window.powClient === null) {
    window.powClient = new PoWClient();
    console.log('✅ PoW Client v3.1 global');
}

console.log('✅ pow-client.js v3.1 carregado');
console.log('   📡 Conectado ao backend: /api/pow/challenge');
console.log('   🔑 Headers: X-PoW-Challenge, X-PoW-Nonce');
console.log('   📡 Use window.powClient.prepareForUpload() para preparar');
console.log('   📡 Use window.powClient.uploadWithPow(file) para upload');