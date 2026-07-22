// frontend/js/pow-worker.js - Web Worker para resolver PoW v2.0
/**
 * 🔥 PoW Worker - Resolve desafios SHA-256 em thread separada
 * 
 * ✅ SEM localStorage, SEM cookies, SEM document (100% isolado)
 * ✅ Puramente matemático (apenas crypto.subtle)
 * ✅ COM PROGRESSO E LOGS (via postMessage)
 * ✅ TRATAMENTO DE ERROS ROBUSTO
 * ✅ FALLBACK AUTOMÁTICO (frontend)
 * 
 * Recebe do frontend:
 * { 
 *   prefix: string,        // Desafio a ser resolvido (32 caracteres hex)
 *   complexity: number,    // Dificuldade (número de zeros no prefixo)
 *   timestamp: number,     // Timestamp do desafio (opcional)
 *   expires_in: number     // Tempo de expiração em segundos (opcional)
 * }
 * 
 * Retorna para o frontend:
 * { 
 *   success: boolean,      // Status da operação
 *   nonce: string,         // Nonce encontrado (se sucesso)
 *   timeMs: number,        // Tempo de execução em ms
 *   attempts: number,      // Número de tentativas realizadas
 *   error: string          // Mensagem de erro (se falha)
 * }
 */

// ==============================================
// 🔥 CONFIGURAÇÕES DO WORKER
// ==============================================

const WORKER_CONFIG = {
    MAX_ATTEMPTS: 1000000,        // 1 milhão de tentativas (segurança)
    PROGRESS_INTERVAL: 10000,      // Log a cada 10.000 tentativas
    PROGRESS_REPORT: true,         // Envia progresso para o frontend
};

// ==============================================
// 🔥 FUNÇÃO PRINCIPAL - RECEBE MENSAGENS
// ==============================================

self.onmessage = async function(e) {
    // 🔥 Valida os dados recebidos
    if (!e.data || typeof e.data !== 'object') {
        self.postMessage({
            success: false,
            error: 'Dados inválidos recebidos'
        });
        return;
    }

    const { prefix, complexity, timestamp, expires_in } = e.data;

    // 🔥 Valida o prefixo
    if (!prefix || typeof prefix !== 'string' || prefix.length !== 32) {
        self.postMessage({
            success: false,
            error: 'Prefixo inválido (deve ser uma string hex de 32 caracteres)'
        });
        return;
    }

    // 🔥 Valida a complexidade
    if (!complexity || typeof complexity !== 'number' || complexity < 3 || complexity > 6) {
        self.postMessage({
            success: false,
            error: 'Complexidade inválida (deve ser entre 3 e 6)'
        });
        return;
    }

    // 🔥 Verifica se o desafio não está expirado (opcional)
    if (timestamp && expires_in) {
        const now = Date.now();
        const challengeAge = (now - timestamp) / 1000;
        if (challengeAge > expires_in) {
            self.postMessage({
                success: false,
                error: `Desafio expirado (${Math.round(challengeAge)}s > ${expires_in}s)`
            });
            return;
        }
    }

    // 🔥 Inicia a resolução
    await resolveChallenge(prefix, complexity);
};

// ==============================================
// 🔥 FUNÇÃO DE RESOLUÇÃO
// ==============================================

async function resolveChallenge(prefix, complexity) {
    const target = '0'.repeat(complexity);
    const encoder = new TextEncoder();
    let nonce = 0;
    const startTime = Date.now();
    const maxAttempts = WORKER_CONFIG.MAX_ATTEMPTS;
    const progressInterval = WORKER_CONFIG.PROGRESS_INTERVAL;
    let lastProgressReport = 0;

    try {
        // 🔥 Envia status inicial
        self.postMessage({
            type: 'progress',
            status: 'started',
            message: `Iniciando busca por nonce (dificuldade: ${complexity})`,
            complexity: complexity,
            maxAttempts: maxAttempts
        });

        // 🔥 Loop principal
        while (nonce < maxAttempts) {
            // 🔥 Prepara os dados
            const data = `${prefix}:${nonce}`;
            const encoded = encoder.encode(data);

            // 🔥 Calcula o hash SHA-256
            const hashBuffer = await crypto.subtle.digest('SHA-256', encoded);
            const hashArray = Array.from(new Uint8Array(hashBuffer));
            const hashHex = hashArray
                .map(b => b.toString(16).padStart(2, '0'))
                .join('');

            // 🔥 Verifica se encontrou
            if (hashHex.startsWith(target)) {
                const timeMs = Date.now() - startTime;
                
                // 🔥 Envia resultado de sucesso
                self.postMessage({
                    success: true,
                    nonce: String(nonce),
                    timeMs: timeMs,
                    attempts: nonce + 1,
                    hash: hashHex,
                    type: 'result'
                });
                
                return;
            }

            nonce++;

            // 🔥 Envia progresso periódico (se habilitado)
            if (WORKER_CONFIG.PROGRESS_REPORT && 
                nonce - lastProgressReport >= progressInterval) {
                lastProgressReport = nonce;
                const elapsed = Date.now() - startTime;
                const rate = elapsed > 0 ? Math.round(nonce / (elapsed / 1000)) : 0;
                
                self.postMessage({
                    type: 'progress',
                    status: 'progress',
                    attempts: nonce,
                    maxAttempts: maxAttempts,
                    percent: Math.round((nonce / maxAttempts) * 100),
                    rate: rate,
                    elapsedMs: elapsed
                });
            }
        }

        // 🔥 Se chegou aqui, não encontrou
        const timeMs = Date.now() - startTime;
        self.postMessage({
            success: false,
            error: `Não foi possível encontrar nonce após ${maxAttempts.toLocaleString()} tentativas`,
            attempts: maxAttempts,
            timeMs: timeMs,
            type: 'result'
        });

    } catch (error) {
        // 🔥 Erro inesperado
        self.postMessage({
            success: false,
            error: `Erro no worker: ${error.message || 'Desconhecido'}`,
            stack: error.stack,
            type: 'error'
        });
    }
}

// ==============================================
// 🔥 LISTENER PARA CANCELAMENTO
// ==============================================

self.addEventListener('message', function(e) {
    if (e.data && e.data.action === 'cancel') {
        self.postMessage({
            type: 'cancel',
            success: false,
            message: 'Cálculo cancelado pelo usuário'
        });
        self.close();
    }
});

// ==============================================
// 🔥 LISTENER PARA ERRO GLOBAL
// ==============================================

self.addEventListener('error', function(e) {
    self.postMessage({
        success: false,
        error: `Erro global no worker: ${e.message || 'Desconhecido'}`,
        type: 'error'
    });
});

// ==============================================
// 🔥 INICIALIZAÇÃO
// ==============================================

// Log silencioso (não usa console no worker em produção)
// O frontend saberá que o worker está pronto quando receber mensagens

// Apenas sinaliza que está pronto (opcional)
self.postMessage({
    type: 'ready',
    status: 'ready',
    message: 'PoW Worker v2.0 pronto para uso'
});