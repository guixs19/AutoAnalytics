// frontend/js/pow-client.js - VERSÃO CORRIGIDA v3.3 (COM DIAGNÓSTICO MELHORADO)
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
 * 
 * 🔍 DIAGNÓSTICO V3.3:
 * - Log detalhado das respostas do servidor
 * - Validação de contentType (JSON vs HTML)
 * - Tratamento de erro com fallback para texto
 * - Identificação de problemas de proxy/autenticação
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
        
        // 🔥 Estatísticas de diagnóstico
        this._diag = {
            lastResponseStatus: null,
            lastResponseContentType: null,
            lastResponsePreview: null,
            totalRequests: 0,
            failedRequests: 0,
            successfulRequests: 0
        };
        
        console.log('⚡ PoW Client v3.3 - Conectado com pow_routes.py');
        console.log('   🔒 Modo sob demanda (só no upload)');
        console.log(`   📦 Cache: 1 solução`);
        console.log(`   🔑 API: ${this.apiBase}/pow/challenge`);
        console.log('   🔍 Diagnóstico ativo');
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
            if (age < 30000) {
                console.log('⚡ PoW em cache (válido)');
                return true;
            } else {
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
            const response = await fetch(`${this.apiBase}${endpoint}`, {
                method: 'POST',
                headers: {
                    'X-PoW-Challenge': solution.prefix,
                    'X-PoW-Nonce': solution.nonce,
                    'Authorization': `Bearer ${token}`
                },
                body: formData
            });
            
            // PoW expirado (428 Precondition Required)
            if (response.status === 428) {
                console.warn('⚠️ PoW expirado (428), recalculando...');
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
            console.log('✅ Upload com PoW concluído');
            return data;
            
        } catch (error) {
            console.error('❌ Upload com PoW falhou:', error);
            throw error;
        }
    }
    
    // ==============================================
    // 🔒 MÉTODOS INTERNOS (CONECTADOS AO BACKEND) - CORRIGIDOS V3.3
    // ==============================================
    
    /**
     * Obtém desafio do backend (GET /api/pow/challenge)
     * 🔥 CORRIGIDO V3.3: Diagnóstico detalhado e tratamento de erros
     */
    async _getChallengeSafe() {
        const token = this._getSecureToken();
        if (!token) {
            throw new Error('Não autenticado');
        }

        this._diag.totalRequests++;

        try {
            console.log('📡 Solicitando desafio PoW ao backend...');
            
            const response = await fetch(`${this.apiBase}/pow/challenge`, {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Cache-Control': 'no-cache',
                    'Accept': 'application/json'
                }
            });

            // 🔥 LOG PARA DIAGNÓSTICO
            const contentType = response.headers.get('content-type') || '';
            this._diag.lastResponseStatus = response.status;
            this._diag.lastResponseContentType = contentType;
            
            console.log(`📡 Resposta PoW: status=${response.status}, contentType=${contentType}`);

            // 🔥 Verifica se é 401 (token inválido)
            if (response.status === 401) {
                console.warn('⚠️ Token expirado ou inválido no PoW');
                this._diag.failedRequests++;
                throw new Error('Não autenticado - token inválido');
            }

            // 🔥 Verifica se é 429 (rate limit)
            if (response.status === 429) {
                console.warn('⚠️ Rate limit excedido no PoW');
                this._diag.failedRequests++;
                let errorText = '';
                try {
                    const data = await response.json();
                    errorText = data.detail || data.message || 'Muitas requisições. Aguarde.';
                } catch (e) {
                    errorText = await response.text().catch(() => '');
                }
                throw new Error(`Rate limit: ${errorText}`);
            }

            // 🔥 Verifica se é 404 (rota não encontrada)
            if (response.status === 404) {
                console.error('❌ Rota PoW não encontrada (404) - Verifique se o backend está rodando e a rota está registrada');
                this._diag.failedRequests++;
                let errorText = '';
                try {
                    const data = await response.json();
                    errorText = data.detail || data.message || 'Rota não encontrada';
                } catch (e) {
                    errorText = await response.text().catch(() => '');
                }
                throw new Error(`Rota não encontrada: ${errorText.substring(0, 100)}`);
            }

            // 🔥 Verifica se a resposta é OK
            if (!response.ok) {
                this._diag.failedRequests++;
                let errorText = '';
                try {
                    const data = await response.json();
                    errorText = data.detail || data.message || JSON.stringify(data);
                } catch (e) {
                    errorText = await response.text().catch(() => '');
                }
                console.error(`❌ Erro PoW HTTP ${response.status}:`, errorText.substring(0, 200));
                throw new Error(`HTTP ${response.status}: ${errorText.substring(0, 100)}`);
            }

            // 🔥 Verifica se a resposta é JSON
            if (!contentType.includes('application/json')) {
                this._diag.failedRequests++;
                const text = await response.text().catch(() => '');
                const preview = text.substring(0, 200);
                this._diag.lastResponsePreview = preview;
                console.error('❌ Resposta não é JSON. Primeiros 200 caracteres:', preview);
                
                // Verifica se é uma página HTML (comum em proxies mal configurados)
                if (text.trim().startsWith('<')) {
                    throw new Error('Servidor retornou HTML em vez de JSON (verifique proxy/reverse)');
                }
                throw new Error(`Servidor retornou formato inválido: ${preview.substring(0, 50)}...`);
            }

            // 🔥 Tenta parsear o JSON
            let data;
            try {
                data = await response.json();
            } catch (e) {
                this._diag.failedRequests++;
                const text = await response.text().catch(() => '');
                console.error('❌ JSON inválido:', text.substring(0, 200));
                throw new Error(`JSON inválido recebido do servidor`);
            }

            // 🔥 Log do dado recebido (primeiros 100 caracteres)
            const dataPreview = JSON.stringify(data).substring(0, 100);
            console.log('📦 Dados recebidos do PoW:', dataPreview + (dataPreview.length >= 100 ? '...' : ''));

            // 🔥 Validação de segurança
            if (!isValidChallenge(data)) {
                this._diag.failedRequests++;
                console.error('❌ Desafio inválido - estrutura incorreta:', data);
                throw new Error('Desafio inválido recebido do servidor (formato incorreto)');
            }

            // Sucesso!
            this._diag.successfulRequests++;
            this.currentChallenge = data;
            this._securityStats.totalAttempts++;

            console.log(`✅ Desafio recebido (difficulty: ${data.difficulty}, expires: ${data.expires_in}s)`);
            return data;

        } catch (error) {
            console.error('❌ Erro ao obter desafio:', error.message);
            this._diag.failedRequests++;
            this._securityStats.failedAttempts++;
            this._securityStats.lastFailure = Date.now();
            
            // 🔥 Se for erro de autenticação, propaga com mensagem clara
            if (error.message.includes('autenticado') || error.message.includes('token')) {
                throw error;
            }
            
            // 🔥 Erro de infraestrutura - log detalhado
            console.error('📋 DIAGNÓSTICO:', {
                status: this._diag.lastResponseStatus,
                contentType: this._diag.lastResponseContentType,
                preview: this._diag.lastResponsePreview || 'n/a'
            });
            
            throw error;
        }
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
            try {
                const worker = new Worker('/js/pow-worker.js');
                
                const timeoutId = setTimeout(() => {
                    worker.terminate();
                    reject(new Error('Timeout ao resolver PoW (30s)'));
                }, 30000);
                
                worker.postMessage({
                    prefix: challenge.challenge,
                    complexity: challenge.difficulty,
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
                        prefix: challenge.challenge,
                        complexity: challenge.difficulty,
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
                // Fallback: worker não disponível
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
            // Fallback: não temos crypto no browser sem worker
            // Este é apenas um placeholder - na prática, o worker deve estar disponível
            throw new Error('Worker não disponível para resolver PoW');
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
            cacheAge: this.cachedSolution ? Date.now() - this.cachedSolution.solvedAt : null,
            // 🔥 Estatísticas de diagnóstico
            diagnostics: {
                totalRequests: this._diag.totalRequests,
                successfulRequests: this._diag.successfulRequests,
                failedRequests: this._diag.failedRequests,
                lastStatus: this._diag.lastResponseStatus,
                lastContentType: this._diag.lastResponseContentType
            }
        };
    }
    
    /**
     * 🔥 Obtém diagnóstico detalhado para debugging
     */
    getDiagnostics() {
        return {
            ...this._diag,
            apiBase: this.apiBase,
            isAuthenticated: this._isAuthenticated(),
            hasCache: this.cachedSolution !== null,
            cacheAge: this.cachedSolution ? Date.now() - this.cachedSolution.solvedAt : null,
            isSolving: this.isSolving
        };
    }
}

// ==============================================
// 🔥 INSTÂNCIA GLOBAL
// ==============================================

if (typeof window.powClient === 'undefined' || window.powClient === null) {
    window.powClient = new PoWClient();
    console.log('✅ PoW Client v3.3 global');
}

// 🔥 Função para inicializar (chamada pelo app.js APÓS autenticação)
window.initPowClient = function(options = {}) {
    const { autoRefill = false, preSolve = false } = options;
    
    if (!window.powClient) {
        console.warn('⚠️ PoW Client não disponível');
        return;
    }
    
    if (window.powClient._isInitialized) {
        console.log('⚠️ PoW Client já inicializado');
        return;
    }
    
    // Verifica autenticação
    if (!window.powClient._isAuthenticated()) {
        console.log('⏳ PoW: aguardando autenticação...');
        return;
    }
    
    window.powClient._isInitialized = true;
    
    // 🔥 SEM auto-refill (só no upload)
    if (autoRefill) {
        window.powClient.startAutoRefill(30000);
    }
    
    // 🔥 SEM pré-solve (só no upload)
    if (preSolve) {
        setTimeout(() => window.powClient.preSolve(), 500);
    }
    
    console.log('✅ PoW Client inicializado (modo sob demanda)');
};

// 🔥 Função para parar o PoW
window.stopPowClient = function() {
    if (window.powClient) {
        window.powClient.stopAutoRefill();
        window.powClient.reset();
        window.powClient._isInitialized = false;
        console.log('⏹️ PoW Client parado');
    }
};

// 🔥 Função para obter diagnóstico
window.getPowDiagnostics = function() {
    if (window.powClient) {
        return window.powClient.getDiagnostics();
    }
    return { error: 'PoW Client não disponível' };
};

console.log('✅ pow-client.js v3.3 carregado (com diagnóstico)');
console.log('   📡 Use window.initPowClient() para iniciar (chamado pelo app.js)');
console.log('   📡 PoW só será ativado no momento do upload');
console.log('   🔍 Use window.getPowDiagnostics() para debug');