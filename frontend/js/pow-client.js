// frontend/js/pow-client.js
/**
 * Cliente Proof of Work - Solução silenciosa em background
 * Não atrapalha a experiência do usuário (drag & drop)
 */

class PoWClient {
    constructor() {
        this.currentChallenge = null;
        this.isSolving = false;
        this.worker = null;
        this.apiBase = window.location.hostname.includes('localhost') 
            ? 'http://localhost:8000/api'
            : '/api';
    }
    
    /**
     * Obtém um desafio do servidor
     */
    async getChallenge() {
        try {
            const response = await fetch(`${this.apiBase}/pow/challenge`, {
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                }
            });
            
            if (!response.ok) {
                throw new Error('Falha ao obter desafio');
            }
            
            this.currentChallenge = await response.json();
            return this.currentChallenge;
        } catch (error) {
            console.error('❌ Erro ao obter desafio PoW:', error);
            throw error;
        }
    }
    
    /**
     * Resolve o desafio PoW usando Web Worker (não trava a UI)
     */
    async solveChallenge(challenge = null) {
        const challengeToSolve = challenge || this.currentChallenge;
        
        if (!challengeToSolve) {
            throw new Error('Nenhum desafio disponível');
        }
        
        if (this.isSolving) {
            // Aguarda solução em andamento
            return new Promise((resolve) => {
                const checkInterval = setInterval(() => {
                    if (!this.isSolving && this.lastSolution) {
                        clearInterval(checkInterval);
                        resolve(this.lastSolution);
                    }
                }, 50);
            });
        }
        
        this.isSolving = true;
        
        return new Promise((resolve, reject) => {
            // Criar Web Worker para resolver em background
            const worker = new Worker('/js/pow-worker.js');
            
            worker.postMessage(challengeToSolve);
            
            worker.onmessage = (e) => {
                const { nonce, timeMs } = e.data;
                this.lastSolution = {
                    nonce,
                    prefix: challengeToSolve.prefix,
                    complexity: challengeToSolve.complexity
                };
                this.isSolving = false;
                worker.terminate();
                
                console.log(`⚡ PoW resolvido em ${timeMs}ms (complexidade ${challengeToSolve.complexity})`);
                resolve(this.lastSolution);
            };
            
            worker.onerror = (error) => {
                this.isSolving = false;
                worker.terminate();
                reject(error);
            };
        });
    }
    
    /**
     * Prepara headers para requisição protegida
     * (Já inclui PoW automaticamente)
     */
    async getProtectedHeaders() {
        // Se não tem desafio ou expirou, pega um novo
        if (!this.currentChallenge || this.isChallengeExpired()) {
            await this.getChallenge();
        }
        
        // Resolve PoW se ainda não resolveu
        if (!this.lastSolution || this.needsNewSolution()) {
            await this.solveChallenge();
        }
        
        return {
            'X-PoW-Prefix': this.lastSolution.prefix,
            'X-PoW-Nonce': this.lastSolution.nonce,
            'X-PoW-Complexity': this.lastSolution.complexity,
            'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        };
    }
    
    isChallengeExpired() {
        if (!this.currentChallenge) return true;
        const now = Math.floor(Date.now() / 1000);
        const expiresAt = this.currentChallenge.timestamp + this.currentChallenge.expires_in;
        return now > expiresAt;
    }
    
    needsNewSolution() {
        if (!this.lastSolution) return true;
        // Se passou mais de 30s, resolve novamente
        if (this.lastSolution.solvedAt && (Date.now() - this.lastSolution.solvedAt) > 30000) {
            return true;
        }
        return false;
    }
    
    /**
     * Para integração com drag & drop: resolve PoW automaticamente
     * enquanto o usuário arrasta o arquivo
     */
    async prepareForUpload() {
        // Pré-resolve PoW em background durante o drag
        if (!this.currentChallenge || this.isChallengeExpired()) {
            await this.getChallenge();
        }
        
        if (!this.lastSolution || this.needsNewSolution()) {
            // Inicia resolução em background (não aguarda)
            this.solveChallenge().catch(console.error);
        }
    }
    
    /**
     * Faz upload com PoW incluso (para drag & drop)
     */
    async uploadWithPow(file, endpoint = '/api/upload') {
        // Garante que temos uma solução
        if (!this.lastSolution || this.needsNewSolution()) {
            await this.solveChallenge();
        }
        
        const formData = new FormData();
        formData.append('file', file);
        
        const response = await fetch(`${this.apiBase}${endpoint}`, {
            method: 'POST',
            headers: {
                'X-PoW-Prefix': this.lastSolution.prefix,
                'X-PoW-Nonce': this.lastSolution.nonce,
                'X-PoW-Complexity': this.lastSolution.complexity,
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            },
            body: formData
        });
        
        if (response.status === 428 || response.status === 401) {
            // PoW expirou ou inválido - resolve novamente e tenta
            console.log('🔄 PoW expirado, resolvendo novamente...');
            this.currentChallenge = null;
            this.lastSolution = null;
            return this.uploadWithPow(file, endpoint);
        }
        
        if (!response.ok) {
            throw new Error(`Upload falhou: ${response.status}`);
        }
        
        return response.json();
    }
}

// Instância global
window.powClient = new PoWClient();

console.log('✅ PoW Client inicializado - Proteção silenciosa ativa');