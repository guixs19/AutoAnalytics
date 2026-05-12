// frontend/js/pow-client.js
/**
 * Cliente Proof of Work - SOLUÇÃO INSTANTÂNEA
 * Sistema de pré-cálculo em background para zero latência no upload
 */

class PoWClient {
    constructor() {
        this.currentChallenge = null;
        this.precomputedSolution = null;
        this.solutionStock = []; // Estoque de soluções pré-calculadas
        this.isSolving = false;
        this.worker = null;
        this.apiBase = window.location.hostname.includes('localhost') 
            ? 'http://localhost:8000/api'
            : '/api';
        
        // Configurações de performance
        this.stockSize = 2; // Mantém 2 soluções prontas
        this.refillThreshold = 1; // Refaz quando só tem 1 restante
        this.lastSolutionTime = 0;
        
        // Inicialização automática
        this.autoRefill = true;
        this.refillInterval = null;
        
        console.log('⚡ PoW Client otimizado - Sistema de pré-cálculo ativo');
    }
    
    /**
     * PRÉ-CÁLCULO INSTANTÂNEO - Chame na inicialização da página
     * Começa a resolver PoW em background ANTES do usuário precisar
     */
    async preSolve() {
        if (this.isSolving || this.solutionStock.length >= this.stockSize) {
            console.log(`📦 Estoque de PoW: ${this.solutionStock.length}/${this.stockSize} soluções prontas`);
            return;
        }
        
        console.log('⚡ Iniciando pré-cálculo de PoW em background...');
        
        try {
            // Pega desafio do servidor
            const challenge = await this.getChallenge();
            
            if (!challenge) {
                console.warn('⚠️ Não foi possível obter desafio PoW');
                return;
            }
            
            // Resolve em worker (não bloqueia UI)
            const solution = await this.solveChallengeAsync(challenge);
            
            if (solution) {
                this.solutionStock.push({
                    solution: solution,
                    challenge: challenge,
                    timestamp: Date.now()
                });
                
                console.log(`✅ PoW pré-calculado (${this.solutionStock.length}/${this.stockSize}) - Pronto para uso instantâneo`);
                
                // Continua calculando se ainda não atingiu o estoque
                if (this.autoRefill && this.solutionStock.length < this.stockSize) {
                    setTimeout(() => this.preSolve(), 100);
                }
            }
        } catch (error) {
            console.error('❌ Erro no pré-cálculo PoW:', error);
        }
    }
    
    /**
     * Inicia refill automático periódico
     */
    startAutoRefill(intervalMs = 25000) { // 25 segundos
        if (this.refillInterval) clearInterval(this.refillInterval);
        
        this.refillInterval = setInterval(() => {
            if (this.solutionStock.length < this.refillThreshold) {
                console.log('🔄 Reposição automática de PoW iniciada');
                this.preSolve();
            } else {
                console.log(`📦 Estoque saudável: ${this.solutionStock.length} PoWs prontos`);
            }
        }, intervalMs);
        
        console.log(`🔄 Auto-refill PoW ativado (a cada ${intervalMs}ms)`);
    }
    
    stopAutoRefill() {
        if (this.refillInterval) {
            clearInterval(this.refillInterval);
            this.refillInterval = null;
        }
    }
    
    /**
     * Obtém um desafio do servidor (otimizado)
     */
    async getChallenge() {
        try {
            const response = await fetch(`${this.apiBase}/pow/challenge`, {
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
                    'Cache-Control': 'no-cache' // Evita cache
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
     * Resolve desafio de forma assíncrona (não bloqueante)
     */
    async solveChallengeAsync(challenge) {
        return new Promise((resolve, reject) => {
            const startTime = performance.now();
            
            // Criar Web Worker para resolver em background
            const worker = new Worker('/js/pow-worker.js');
            
            worker.postMessage(challenge);
            
            worker.onmessage = (e) => {
                const { nonce, timeMs } = e.data;
                const totalTime = performance.now() - startTime;
                
                worker.terminate();
                
                console.log(`⚡ PoW resolvido em ${timeMs}ms (total: ${totalTime.toFixed(0)}ms, complexidade ${challenge.complexity})`);
                
                resolve({
                    nonce,
                    prefix: challenge.prefix,
                    complexity: challenge.complexity,
                    solvedAt: Date.now()
                });
            };
            
            worker.onerror = (error) => {
                worker.terminate();
                reject(error);
            };
        });
    }
    
    /**
     * PEGA SOLUÇÃO INSTANTÂNEA - Zero espera!
     */
    async getInstantSolution() {
        // Se tem solução no estoque, usa imediatamente
        if (this.solutionStock.length > 0) {
            const stockItem = this.solutionStock.shift();
            console.log(`⚡ Usando PoW pré-calculado (restam ${this.solutionStock.length})`);
            
            // Dispara reposição em background
            if (this.autoRefill && this.solutionStock.length < this.refillThreshold) {
                setTimeout(() => this.preSolve(), 50);
            }
            
            return stockItem.solution;
        }
        
        // Fallback: calcula na hora (nunca deve acontecer com auto-refill)
        console.warn('⚠️ Estoque vazio! Calculando PoW sob demanda...');
        
        const challenge = await this.getChallenge();
        const solution = await this.solveChallengeAsync(challenge);
        
        return solution;
    }
    
    /**
     * Upload com PoW INSTANTÂNEO (sem espera)
     */
    async uploadWithPow(file, endpoint = '/api/upload') {
        // Pega solução instantânea do estoque
        const solution = await this.getInstantSolution();
        
        const formData = new FormData();
        formData.append('file', file);
        
        // Adiciona campos específicos da análise
        const analysisType = document.getElementById('tipoAnalise')?.value || 'auto';
        const aiModel = document.getElementById('modeloIA')?.value || 'auto';
        formData.append('analysis_type', analysisType);
        formData.append('ai_model', aiModel);
        
        const startTime = performance.now();
        
        const response = await fetch(`${this.apiBase}${endpoint}`, {
            method: 'POST',
            headers: {
                'X-PoW-Prefix': solution.prefix,
                'X-PoW-Nonce': solution.nonce,
                'X-PoW-Complexity': solution.complexity,
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            },
            body: formData
        });
        
        const totalTime = performance.now() - startTime;
        console.log(`📤 Upload concluído em ${totalTime.toFixed(0)}ms (PoW incluso)`);
        
        // Tratamento de erro: PoW expirado
        if (response.status === 428 || response.status === 401) {
            console.log('🔄 PoW expirado, usando próximo do estoque...');
            
            if (this.solutionStock.length > 0) {
                // Tenta com a próxima solução
                return this.uploadWithPow(file, endpoint);
            } else {
                // Recalcula
                await this.preSolve();
                return this.uploadWithPow(file, endpoint);
            }
        }
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `Upload falhou: ${response.status}`);
        }
        
        return response.json();
    }
    
    /**
     * Pré-prepara para drag & drop (chamado durante o drag)
     */
    async prepareForUpload() {
        // Garante que temos pelo menos uma solução pronta
        if (this.solutionStock.length === 0) {
            console.log('🔄 Preparando PoW durante drag...');
            await this.preSolve();
        } else {
            console.log(`⚡ PoW pronto para drag (${this.solutionStock.length} disponíveis)`);
        }
    }
    
    /**
     * Reseta o estado (útil no logout)
     */
    reset() {
        this.solutionStock = [];
        this.currentChallenge = null;
        this.precomputedSolution = null;
        console.log('🔄 PoW Client resetado');
    }
    
    /**
     * Retorna estatísticas do PoW
     */
    getStats() {
        return {
            solutionsReady: this.solutionStock.length,
            maxStock: this.stockSize,
            autoRefill: this.autoRefill,
            lastSolutionAge: this.solutionStock[0] ? Date.now() - this.solutionStock[0].timestamp : null
        };
    }
}

// Instância global com auto-refill
window.powClient = new PoWClient();

// Inicia auto-refill quando autenticado
document.addEventListener('userAuthenticated', () => {
    window.powClient.startAutoRefill(30000); // Refill a cada 30 segundos
    window.powClient.preSolve(); // Pré-cálculo inicial
});

console.log('✅ PoW Client otimizado - Sistema de pré-cálculo ativo');