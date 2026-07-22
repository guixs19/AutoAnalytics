// frontend/js/pow-worker.js - Web Worker para resolver PoW v1.0
/**
 * 🔥 PoW Worker - Resolve desafios SHA-256 em thread separada
 * 
 * ✅ NÃO BLOQUEIA A UI
 * ✅ USA CRYPTO.SUBTLE (nativo do navegador)
 * ✅ COM PROGRESSO E LOGS
 * ✅ TRATAMENTO DE ERROS ROBUSTO
 * 
 * Recebe do frontend:
 * { 
 *   prefix: string,        // Desafio a ser resolvido (32 caracteres hex)
 *   complexity: number,    // Dificuldade (número de zeros no prefixo)
 *   timestamp: number,     // Timestamp do desafio
 *   expires_in: number     // Tempo de expiração em segundos
 * }
 * 
 * Retorna para o frontend:
 * { 
 *   nonce: string,         // Nonce encontrado
 *   timeMs: number,        // Tempo de execução em ms
 *   success: boolean,      // Status da operação
 *   attempts: number       // Número de tentativas realizadas
 * }
 */

// ==============================================
// 🔥 CONFIGURAÇÕES DO WORKER
// ==============================================

const WORKER_CONFIG = {
    MAX_ATTEMPTS: 1000000,        // 1 milhão de tentativas (segurança)
    PROGRESS_INTERVAL: 10000,      // Log a cada 10.000 tentativas
    MAX_TIMEOUT: 60000,            // Timeout máximo de 60 segundos
};

// ==============================================
// 🔥 FUNÇÃO PRINCIPAL
// ==============================================

self.onmessage = async function (e) {
    // 🔥 Valida os dados recebidos
    if (!e.data || typeof e.data !== 'object') {
        self.postMessage({
            error: 'Dados inválidos recebidos',
            success: false
        });
        return;
    }

    const { prefix, complexity, timestamp, expires_in } = e.data;

    // 🔥 Valida o prefixo
    if (!prefix || typeof prefix !== 'string' || prefix.length !== 32) {
        self.postMessage({
            error: 'Prefixo inválido (deve ser uma string hex de 32 caracteres)',
            success: false
        });
        return;
    }

    // 🔥 Valida a complexidade
    if (!complexity || typeof complexity !== 'number' || complexity < 3 || complexity > 6) {
        self.postMessage({
            error: 'Complexidade inválida (deve ser entre 3 e 6)',
            success: false
        });
        return;
    }

    // 🔥 Verifica se o desafio não está expirado
    if (timestamp && expires_in) {
        const now = Date.now();
        const challengeAge = (now - timestamp) / 1000;
        if (challengeAge > expires_in) {
            self.postMessage({
                error: `Desafio expirado (${Math.round(challengeAge)}s > ${expires_in}s)`,
                success: false
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
    let lastProgressLog = 0;

    try {
        // 🔥 Log inicial
        console.log(`🧵 [Worker] 🔐 Iniciando busca por nonce`);
        console.log(`   - Prefixo: ${prefix.substring(0, 8)}...${prefix.substring(24)}`);
        console.log(`   - Dificuldade: ${complexity} (${target}...)`);
        console.log(`   - Máximo de tentativas: ${maxAttempts.toLocaleString()}`);

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
                console.log(`🧵 [Worker] ✅ Nonce encontrado!`);
                console.log(`   - Nonce: ${nonce}`);
                console.log(`   - Hash: ${hashHex.substring(0, 20)}...`);
                console.log(`   - Tempo: ${timeMs}ms`);
                console.log(`   - Tentativas: ${(nonce + 1).toLocaleString()}`);

                self.postMessage({
                    nonce: String(nonce),
                    timeMs: timeMs,
                    success: true,
                    attempts: nonce + 1,
                    hash: hashHex
                });
                return;
            }

            nonce++;

            // 🔥 Log de progresso
            if (nonce % progressInterval === 0 && nonce > 0) {
                const elapsed = Date.now() - startTime;
                const rate = Math.round(nonce / (elapsed / 1000));
                console.log(`🧵 [Worker] 🔄 Progresso: ${nonce.toLocaleString()}/${maxAttempts.toLocaleString()} (${rate} tentativas/segundo)`);
            }
        }

        // 🔥 Se chegou aqui, não encontrou
        console.error(`🧵 [Worker] ❌ Nonce não encontrado após ${maxAttempts.toLocaleString()} tentativas`);
        self.postMessage({
            error: `Não foi possível encontrar nonce após ${maxAttempts.toLocaleString()} tentativas`,
            success: false,
            attempts: maxAttempts,
            timeMs: Date.now() - startTime
        });

    } catch (error) {
        // 🔥 Erro inesperado
        console.error(`🧵 [Worker] ❌ Erro durante a execução:`, error);
        self.postMessage({
            error: `Erro no worker: ${error.message || 'Desconhecido'}`,
            success: false,
            stack: error.stack
        });
    }
}

// ==============================================
// 🔥 LISTENERS ADICIONAIS (OPCIONAIS)
// ==============================================

// 🔥 Listener para cancelamento (se o frontend enviar 'cancel')
self.addEventListener('message', function(e) {
    if (e.data && e.data.action === 'cancel') {
        console.log('🧵 [Worker] ⏹️ Cancelamento solicitado');
        self.close();
    }
});

// 🔥 Listener para erro global
self.addEventListener('error', function(e) {
    console.error('🧵 [Worker] ❌ Erro global:', e.message);
    // Não fechamos automaticamente, deixamos o fluxo principal lidar
});

// ==============================================
// 🔥 INICIALIZAÇÃO
// ==============================================

console.log('🧵 [Worker] ════════════════════════════════════════');
console.log('🧵 [Worker] 🔥 PoW Worker v1.0 carregado!');
console.log(`🧵 [Worker]    - Máximo de tentativas: ${WORKER_CONFIG.MAX_ATTEMPTS.toLocaleString()}`);
console.log(`🧵 [Worker]    - Intervalo de progresso: ${WORKER_CONFIG.PROGRESS_INTERVAL.toLocaleString()} tentativas`);
console.log(`🧵 [Worker]    - Timeout máximo: ${WORKER_CONFIG.MAX_TIMEOUT / 1000}s`);
console.log('🧵 [Worker] ════════════════════════════════════════');

// ==============================================
// 🔥 EXPORTAÇÃO (se necessário para módulos)
// ==============================================

// Nota: Workers não usam export, o código acima é executado diretamente
// O arquivo é carregado via new Worker('/js/pow-worker.js')