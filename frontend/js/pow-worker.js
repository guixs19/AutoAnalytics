// frontend/js/pow-worker.js
/**
 * Web Worker para resolver Proof of Work
 * Executa em thread separada, não trava a UI
 */

self.onmessage = function(e) {
    const { prefix, complexity, timestamp } = e.data;
    const target = '0'.repeat(complexity);
    const startTime = performance.now();
    
    let nonce = 0;
    let found = false;
    const MAX_ATTEMPTS = 10000000; // Limite de segurança
    
    while (!found && nonce < MAX_ATTEMPTS) {
        const nonceStr = `${timestamp}:${nonce}`;
        const data = `${prefix}:${nonceStr}`;
        
        // Hash SHA-256 usando Web Crypto API (disponível em workers)
        const hash = simpleSha256(data);
        
        if (hash.startsWith(target)) {
            const endTime = performance.now();
            found = true;
            
            self.postMessage({
                success: true,
                nonce: nonceStr,
                timeMs: Math.round(endTime - startTime),
                attempts: nonce + 1,
                hash: hash
            });
            break;
        }
        
        nonce++;
    }
    
    if (!found) {
        self.postMessage({
            success: false,
            error: 'Limite de tentativas excedido',
            attempts: nonce
        });
    }
};

/**
 * Implementação simples de SHA-256
 */
function simpleSha256(message) {
    // Função de rotação
    function rotr(x, n) {
        return (x >>> n) | (x << (32 - n));
    }
    
    function shr(x, n) {
        return x >>> n;
    }
    
    function ch(x, y, z) {
        return (x & y) ^ (~x & z);
    }
    
    function maj(x, y, z) {
        return (x & y) ^ (x & z) ^ (y & z);
    }
    
    function sigma0(x) {
        return rotr(x, 2) ^ rotr(x, 13) ^ rotr(x, 22);
    }
    
    function sigma1(x) {
        return rotr(x, 6) ^ rotr(x, 11) ^ rotr(x, 25);
    }
    
    function gamma0(x) {
        return rotr(x, 7) ^ rotr(x, 18) ^ shr(x, 3);
    }
    
    function gamma1(x) {
        return rotr(x, 17) ^ rotr(x, 19) ^ shr(x, 10);
    }
    
    // Constantes SHA-256
    const K = [
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
        0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
        0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
        0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
        0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
        0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
        0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
    ];
    
    // Converter string para UTF-8 bytes
    function utf8Encode(str) {
        const bytes = [];
        for (let i = 0; i < str.length; i++) {
            let c = str.charCodeAt(i);
            if (c < 0x80) {
                bytes.push(c);
            } else if (c < 0x800) {
                bytes.push(0xc0 | (c >> 6), 0x80 | (c & 0x3f));
            } else if (c < 0xd800 || c >= 0xe000) {
                bytes.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f));
            } else {
                i++;
                c = ((c & 0x3ff) << 10) | (str.charCodeAt(i) & 0x3ff);
                bytes.push(0xf0 | (c >> 18), 0x80 | ((c >> 12) & 0x3f), 0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f));
            }
        }
        return new Uint8Array(bytes);
    }
    
    // Converter para array de bytes (big-endian)
    function toByteArray(data) {
        const result = [];
        for (let i = 0; i < data.length; i++) {
            result.push(data[i]);
        }
        return result;
    }
    
    // Calcular SHA-256
    function sha256(message) {
        const msgBytes = utf8Encode(message);
        const msgLength = msgBytes.length;
        
        // Padding
        const ml = msgLength * 8;
        const padLen = 64 - ((msgLength + 9) % 64);
        if (padLen === 64) padLen = 0;
        
        const padded = new Uint8Array(msgLength + 1 + padLen + 8);
        padded.set(msgBytes);
        padded[msgLength] = 0x80;
        
        for (let i = 0; i < 8; i++) {
            padded[padded.length - 8 + i] = (ml >>> (56 - i * 8)) & 0xff;
        }
        
        // Processar em blocos de 64 bytes
        const words = new Array(64);
        let H = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
        
        for (let block = 0; block < padded.length; block += 64) {
            for (let i = 0; i < 16; i++) {
                words[i] = (padded[block + i * 4] << 24) |
                           (padded[block + i * 4 + 1] << 16) |
                           (padded[block + i * 4 + 2] << 8) |
                           (padded[block + i * 4 + 3]);
            }
            
            for (let i = 16; i < 64; i++) {
                words[i] = (gamma1(words[i - 2]) + words[i - 7] + gamma0(words[i - 15]) + words[i - 16]) >>> 0;
            }
            
            let [a, b, c, d, e, f, g, h] = H;
            
            for (let i = 0; i < 64; i++) {
                const T1 = (h + sigma1(e) + ch(e, f, g) + K[i] + words[i]) >>> 0;
                const T2 = (sigma0(a) + maj(a, b, c)) >>> 0;
                h = g;
                g = f;
                f = e;
                e = (d + T1) >>> 0;
                d = c;
                c = b;
                b = a;
                a = (T1 + T2) >>> 0;
            }
            
            H = [
                (H[0] + a) >>> 0,
                (H[1] + b) >>> 0,
                (H[2] + c) >>> 0,
                (H[3] + d) >>> 0,
                (H[4] + e) >>> 0,
                (H[5] + f) >>> 0,
                (H[6] + g) >>> 0,
                (H[7] + h) >>> 0
            ];
        }
        
        // Converter para hex
        let hex = '';
        for (let i = 0; i < H.length; i++) {
            hex += H[i].toString(16).padStart(8, '0');
        }
        
        return hex;
    }
    
    return sha256(message);
}

console.log('🧮 PoW Worker inicializado');