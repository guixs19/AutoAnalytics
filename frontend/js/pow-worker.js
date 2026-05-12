// frontend/js/pow-worker.js
/**
 * Web Worker para Proof of Work - CORRIGIDO COM SHA-256
 * Usa algoritmo consistente com o backend
 * Otimizado para mobile com progress reporting
 */

self.onmessage = async function(e) {
    const { prefix, complexity, timestamp, expires_in } = e.data;
    
    const startTime = performance.now();
    
    // Configuração adaptativa baseada na complexidade
    // Para complexity=3-4, é rápido encontrar nonce (normalmente < 5000 tentativas)
    const maxAttempts = Math.pow(2, complexity + 12); // ~65536 para complexity=4
    
    let nonce = 0;
    let lastReport = startTime;
    let bestHash = null;
    let lastProgressNonce = 0;
    
    // Converte prefixo para Uint8Array uma vez (otimização)
    const encoder = new TextEncoder();
    const prefixBuffer = encoder.encode(prefix);
    
    /**
     * Calcula SHA-256 de forma eficiente
     * Usando crypto.subtle.digest que é nativo e rápido
     */
    async function sha256Hash(data) {
        const hashBuffer = await crypto.subtle.digest('SHA-256', data);
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
    }
    
    /**
     * Verifica se o nonce resolve o desafio usando SHA-256
     * Complexity: número de bits zero no início do hash
     * Para complexity <= 4, verificamos primeiro caractere hex = '0' (4 bits zero)
     */
    async function isValidNonce(nonceValue) {
        const nonceStr = nonceValue.toString();
        const nonceBuffer = encoder.encode(nonceStr);
        
        // Concatena prefixo + nonce
        const combined = new Uint8Array(prefixBuffer.length + nonceBuffer.length);
        combined.set(prefixBuffer);
        combined.set(nonceBuffer, prefixBuffer.length);
        
        // Calcula SHA-256
        const hashHex = await sha256Hash(combined);
        
        // Para complexidade <= 4, verifica primeiro caractere hex = '0'
        // 1 caractere hex '0' = 4 bits zero (mais que suficiente)
        const isValid = hashHex.startsWith('0');
        
        if (isValid) {
            bestHash = hashHex;
        }
        
        return isValid;
    }
    
    /**
     * Busca o nonce que resolve o desafio
     * Com checkpoint a cada 1000 tentativas para não travar a UI
     */
    async function findNonce() {
        while (nonce < maxAttempts) {
            // Checkpoint a cada 1000 tentativas para dar chance ao event loop
            if (nonce % 1000 === 0 && nonce > 0) {
                await new Promise(resolve => setTimeout(resolve, 0));
            }
            
            const nonceStr = nonce.toString();
            const nonceBuffer = encoder.encode(nonceStr);
            
            const combined = new Uint8Array(prefixBuffer.length + nonceBuffer.length);
            combined.set(prefixBuffer);
            combined.set(nonceBuffer, prefixBuffer.length);
            
            // SHA-256 via crypto.subtle
            const hashBuffer = await crypto.subtle.digest('SHA-256', combined);
            const hashArray = Array.from(new Uint8Array(hashBuffer));
            const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
            
            // Verifica se o hash começa com '0'
            if (hashHex.startsWith('0')) {
                const timeMs = performance.now() - startTime;
                
                self.postMessage({
                    nonce: nonce.toString(),
                    hash: hashHex,
                    timeMs: Math.round(timeMs),
                    attempts: nonce + 1
                });
                return true;
            }
            
            nonce++;
            
            // Reporta progresso periodicamente (a cada 2 segundos ou a cada 5000 tentativas)
            const now = performance.now();
            const attemptsSinceLastReport = nonce - lastProgressNonce;
            if (now - lastReport > 2000 || attemptsSinceLastReport > 5000) {
                const timeElapsed = now - startTime;
                const attemptsPerSec = Math.round(nonce / (timeElapsed / 1000));
                
                self.postMessage({
                    progress: nonce,
                    hash: hashHex ? hashHex.substring(0, 8) : null,
                    status: 'computing',
                    timeMs: Math.round(timeElapsed),
                    attemptsPerSec: attemptsPerSec,
                    percentComplete: Math.min(99, Math.round((nonce / maxAttempts) * 100))
                });
                lastReport = now;
                lastProgressNonce = nonce;
            }
        }
        
        return false;
    }
    
    try {
        const solved = await findNonce();
        
        if (!solved) {
            self.postMessage({
                error: 'Não foi possível resolver o desafio após ' + maxAttempts + ' tentativas',
                attempts: nonce,
                maxAttempts: maxAttempts,
                timeMs: Math.round(performance.now() - startTime)
            });
        }
    } catch (error) {
        self.postMessage({
            error: `Erro no PoW: ${error.message}`,
            attempts: nonce,
            timeMs: Math.round(performance.now() - startTime)
        });
    }
};

// Fallback para browsers sem crypto.subtle (legado)
if (!crypto.subtle) {
    console.warn('⚠️ crypto.subtle não disponível, usando algoritmo fallback');
    
    self.onmessage = function(e) {
        const { prefix, complexity } = e.data;
        
        // Função hash simples (DJB2) - apenas para compatibilidade
        function simpleHash(str) {
            let hash = 5381;
            for (let i = 0; i < str.length; i++) {
                const char = str.charCodeAt(i);
                hash = ((hash << 5) + hash) ^ char;
                hash = hash & 0xFFFFFFFF;
            }
            return hash >>> 0;
        }
        
        let nonce = 0;
        const startTime = performance.now();
        const maxAttempts = Math.pow(2, complexity + 15); // Aumentado para fallback
        
        while (nonce < maxAttempts) {
            const testStr = `${prefix}${nonce}`;
            const hashVal = simpleHash(testStr);
            
            // Verifica os primeiros 'complexity' bits
            const mask = (1 << complexity) - 1;
            
            if ((hashVal & mask) === 0) {
                self.postMessage({
                    nonce: nonce.toString(),
                    timeMs: Math.round(performance.now() - startTime),
                    attempts: nonce + 1,
                    fallback: true
                });
                return;
            }
            
            nonce++;
            
            // Reporta progresso a cada 10000 tentativas
            if (nonce % 10000 === 0) {
                self.postMessage({
                    progress: nonce,
                    status: 'computing',
                    timeMs: Math.round(performance.now() - startTime),
                    fallback: true
                });
            }
        }
        
        self.postMessage({ 
            error: 'Fallback: não foi possível resolver o desafio',
            attempts: nonce,
            fallback: true
        });
    };
}