// frontend/js/auth.js - VERSÃO COMPLETA CORRIGIDA (COM FETCH PARA CAPTCHA)
/*
 * auth.js - Sistema de Autenticação
 * 
 * CORREÇÕES REALIZADAS:
 * - Uso de fetch() para ler o header X-Captcha-ID do CAPTCHA
 * - Reset completo do estado do CAPTCHA antes de cada requisição
 * - Limpeza de timers e IDs antigos
 * - Evita envio de CAPTCHA ID antigo em novas tentativas
 * - Ordem de validação do login (CAPTCHA primeiro, depois senha)
 * - Tratamento específico para erro 401 (senha errada)
 * - Refresh token com queue system e rate limiting
 */

class Auth {
    constructor() {
        this.apiBase = window.location.hostname.includes('localhost') 
            ? 'http://localhost:8000/api'
            : '/api';
        
        this.user = this.loadUser();
        this.captchaId = null;
        this.captchaIdRegister = null;
        this.tokenCheckInterval = null;
        this.loginAttempts = 0;
        this.maxLoginAttempts = 5;
        this.isRefreshingCaptcha = false;
        
        // Propriedades para refresh token
        this.isRefreshingToken = false;
        this.tokenRefreshQueue = [];
        this.tokenRefreshTimeout = null;
        this.lastRefreshAttempt = 0;
        this.minRefreshInterval = 5000;
        
        // Timer properties
        this.captchaTimer = null;
        this.captchaTimeLeft = 120;
        this.registerCaptchaTimer = null;
        this.registerCaptchaTimeLeft = 120;
        
        // Flag para saber se já usou o pré-carregamento
        this.hasUsedPreloadedCaptcha = false;
        
        // Propriedades para controle de estado do CAPTCHA
        this.lastCaptchaRequestTime = 0;
        this.minCaptchaInterval = 1000; // 1 segundo mínimo entre requisições
        this.isLoadingCaptcha = false;
        
        this.init();
    }
    
    // ==================== LOCALSTORAGE ====================
    
    loadUser() {
        try {
            const userStr = localStorage.getItem('user');
            return userStr ? JSON.parse(userStr) : {};
        } catch {
            return {};
        }
    }
    
    saveUser(user) {
        localStorage.setItem('user', JSON.stringify(user));
        this.user = user;
    }
    
    saveTokens(accessToken, refreshToken, expiresIn) {
        localStorage.setItem('access_token', accessToken);
        
        if (refreshToken) {
            localStorage.setItem('refresh_token', refreshToken);
        }
        
        if (expiresIn) {
            const expiresAt = Date.now() + (expiresIn * 1000);
            localStorage.setItem('token_expires_at', expiresAt.toString());
            console.log(`⏰ Token expira em: ${new Date(expiresAt).toLocaleTimeString()}`);
        }
        
        this.isRefreshingToken = false;
    }
    
    clearStorage() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
        localStorage.removeItem('token_expires_at');
        this.user = {};
        console.log('🧹 LocalStorage limpo');
    }
    
    // ==================== TOKEN ====================
    
    isTokenExpired() {
        const expiresAt = localStorage.getItem('token_expires_at');
        if (!expiresAt) return true;
        return Date.now() > parseInt(expiresAt);
    }
    
    getTokenTimeLeft() {
        const expiresAt = localStorage.getItem('token_expires_at');
        if (!expiresAt) return 0;
        const timeLeft = parseInt(expiresAt) - Date.now();
        return Math.max(0, timeLeft);
    }
    
    async refreshToken(force = false) {
        const refreshToken = localStorage.getItem('refresh_token');
        if (!refreshToken) {
            console.log('❌ Refresh token não encontrado');
            return false;
        }
        
        const now = Date.now();
        if (!force && (now - this.lastRefreshAttempt) < this.minRefreshInterval) {
            console.log('⏳ Aguardando rate limit do refresh token');
            return this.queueTokenRefresh();
        }
        
        if (this.isRefreshingToken) {
            console.log('⏳ Refresh token em andamento, aguardando...');
            return this.queueTokenRefresh();
        }
        
        this.isRefreshingToken = true;
        this.lastRefreshAttempt = now;
        
        try {
            console.log('🔄 Tentando renovar token...');
            
            const response = await fetch(`${this.apiBase}/auth/refresh`, {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'X-Refresh-Attempt': now.toString()
                },
                body: JSON.stringify({ 
                    refresh_token: refreshToken,
                    old_access_token: localStorage.getItem('access_token')
                }),
                credentials: 'include'
            });
            
            const data = await response.json();
            
            if (response.ok && data.access_token) {
                console.log('✅ Token renovado com sucesso');
                
                this.saveTokens(
                    data.access_token, 
                    data.refresh_token || refreshToken,
                    data.expires_in || 3600
                );
                
                this.processTokenRefreshQueue(true);
                
                return true;
            }
            
            console.log('❌ Falha ao renovar token:', data.detail || 'Erro desconhecido');
            this.processTokenRefreshQueue(false);
            return false;
            
        } catch (error) {
            console.error('❌ Erro ao renovar token:', error);
            this.processTokenRefreshQueue(false);
            return false;
        } finally {
            this.isRefreshingToken = false;
        }
    }
    
    queueTokenRefresh() {
        return new Promise((resolve) => {
            this.tokenRefreshQueue.push(resolve);
            
            setTimeout(() => {
                const index = this.tokenRefreshQueue.indexOf(resolve);
                if (index !== -1) {
                    this.tokenRefreshQueue.splice(index, 1);
                    resolve(false);
                }
            }, 10000);
        });
    }
    
    processTokenRefreshQueue(success) {
        console.log(`📋 Processando ${this.tokenRefreshQueue.length} requisições enfileiradas`);
        
        while (this.tokenRefreshQueue.length > 0) {
            const callback = this.tokenRefreshQueue.shift();
            if (callback) callback(success);
        }
    }
    
    async ensureValidToken() {
        const token = localStorage.getItem('access_token');
        if (!token) return false;
        
        const timeLeft = this.getTokenTimeLeft();
        
        if (timeLeft <= 120000) {
            console.log(`⏰ Token com ${Math.round(timeLeft / 1000)}s restantes, renovando...`);
            return await this.refreshToken();
        }
        
        return true;
    }
    
    async checkTokenStatus() {
        const token = localStorage.getItem('access_token');
        if (!token) return { status: 'no_token' };
        
        try {
            const response = await fetch(`${this.apiBase}/auth/check-token`, {
                method: 'GET',
                headers: { 'Authorization': `Bearer ${token}` },
                credentials: 'include'
            });
            
            const data = await response.json();
            
            if (response.ok && data.status === 'valid') {
                if (data.user) {
                    this.user = { ...this.user, ...data };
                    this.saveUser(this.user);
                }
                return { status: 'valid', data };
            }
            
            if (data.status === 'refreshed' && data.access_token) {
                this.saveTokens(data.access_token, data.refresh_token, data.expires_in);
                return { status: 'valid', data };
            }
            
            if (data.action === 'clear_storage_and_redirect') {
                this.clearStorage();
                if (!this.isLoginPage()) {
                    window.location.href = '/login.html';
                }
                return { status: 'invalid' };
            }
            
            if (await this.refreshToken()) {
                return { status: 'valid' };
            }
            
            return { status: 'error' };
            
        } catch (error) {
            console.error('Erro ao verificar token:', error);
            return { status: 'error' };
        }
    }
    
    // ==================== INIT ====================
    
    async init() {
        console.log('🔧 Auth inicializado - Sistema com gerenciamento de estado corrigido');
        
        const path = window.location.pathname;
        
        if (path.includes('login.html') || path === '/login' || path === '/') {
            this.initLoginPage();
        } else if (path.includes('register.html') || path === '/register') {
            this.initRegisterPage();
        } else {
            const tokenStatus = await this.checkTokenStatus();
            if (tokenStatus.status === 'invalid' || tokenStatus.status === 'no_token') {
                this.redirectToLogin();
            } else {
                this.updateUserUI();
                this.startTokenAutoRefresh();
            }
        }
        
        window.dispatchEvent(new Event('authReady'));
    }
    
    startTokenAutoRefresh() {
        if (this.tokenCheckInterval) clearInterval(this.tokenCheckInterval);
        
        this.tokenCheckInterval = setInterval(async () => {
            if (this.isLoginPage() || this.isRegisterPage()) return;
            
            const timeLeft = this.getTokenTimeLeft();
            
            if (timeLeft > 0 && timeLeft < 300000) {
                console.log(`🔄 Token expira em ${Math.round(timeLeft / 60000)}min, renovando...`);
                await this.refreshToken();
            }
        }, 60000);
    }
    
    // ==================== TIMER FUNCTIONS ====================
    
    startCaptchaTimer(type = 'login') {
        const timerId = type === 'login' ? 'loginCaptchaTimer' : 'registerCaptchaTimer';
        const timerElement = document.getElementById(timerId);
        
        if (!timerElement) return;
        
        // Limpar timer existente
        if (type === 'login') {
            if (this.captchaTimer) {
                clearInterval(this.captchaTimer);
                this.captchaTimer = null;
            }
            this.captchaTimeLeft = 120;
        } else {
            if (this.registerCaptchaTimer) {
                clearInterval(this.registerCaptchaTimer);
                this.registerCaptchaTimer = null;
            }
            this.registerCaptchaTimeLeft = 120;
        }
        
        const updateTimer = () => {
            let timeLeft;
            if (type === 'login') {
                timeLeft = this.captchaTimeLeft;
            } else {
                timeLeft = this.registerCaptchaTimeLeft;
            }
            
            if (timeLeft <= 0) {
                if (type === 'login') {
                    if (this.captchaTimer) clearInterval(this.captchaTimer);
                    this.captchaTimer = null;
                    timerElement.textContent = '00:00';
                    timerElement.classList.add('expired');
                    
                    const input = document.getElementById(`${type}CaptchaInput`);
                    if (input) {
                        input.disabled = true;
                        input.placeholder = '⏰ CAPTCHA expirado! Clique em atualizar';
                    }
                    
                    console.log('⏰ CAPTCHA expirado após 2 minutos');
                } else {
                    if (this.registerCaptchaTimer) clearInterval(this.registerCaptchaTimer);
                    this.registerCaptchaTimer = null;
                    timerElement.textContent = '00:00';
                    timerElement.classList.add('expired');
                    
                    const input = document.getElementById(`${type}CaptchaInput`);
                    if (input) {
                        input.disabled = true;
                        input.placeholder = '⏰ CAPTCHA expirado! Clique em atualizar';
                    }
                }
                return;
            }
            
            const minutes = Math.floor(timeLeft / 60);
            const seconds = timeLeft % 60;
            timerElement.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
            
            if (timeLeft <= 30) {
                timerElement.classList.add('expiring');
            } else {
                timerElement.classList.remove('expiring');
            }
            
            if (type === 'login') {
                this.captchaTimeLeft--;
            } else {
                this.registerCaptchaTimeLeft--;
            }
        };
        
        updateTimer();
        
        if (type === 'login') {
            this.captchaTimer = setInterval(updateTimer, 1000);
        } else {
            this.registerCaptchaTimer = setInterval(updateTimer, 1000);
        }
        
        console.log(`⏰ Cronômetro do CAPTCHA ${type} iniciado: 2 minutos`);
    }
    
    stopCaptchaTimer(type = 'login') {
        if (type === 'login' && this.captchaTimer) {
            clearInterval(this.captchaTimer);
            this.captchaTimer = null;
        } else if (type === 'register' && this.registerCaptchaTimer) {
            clearInterval(this.registerCaptchaTimer);
            this.registerCaptchaTimer = null;
        }
    }
    
    resetCaptchaUI(type = 'login') {
        const input = document.getElementById(`${type}CaptchaInput`);
        const timerEl = document.getElementById(`${type}CaptchaTimer`);
        
        if (input) {
            input.disabled = false;
            input.value = '';
            input.placeholder = 'Digite os 6 números';
        }
        
        if (timerEl) {
            timerEl.classList.remove('expired', 'expiring');
        }
    }
    
    // Reset completo do estado do CAPTCHA
    resetCaptchaState(type = 'login') {
        console.log(`🔄 Resetando estado do CAPTCHA ${type}`);
        
        if (type === 'login') {
            // Limpar ID antigo
            this.captchaId = null;
            // Parar timer
            this.stopCaptchaTimer('login');
            // Resetar flag de pré-carregamento para permitir novo uso
            this.hasUsedPreloadedCaptcha = false;
            // Resetar tempo restante
            this.captchaTimeLeft = 120;
        } else {
            this.captchaIdRegister = null;
            this.stopCaptchaTimer('register');
            this.registerCaptchaTimeLeft = 120;
        }
        
        // Resetar UI
        this.resetCaptchaUI(type);
        
        console.log(`✅ Estado do CAPTCHA ${type} resetado`);
    }
    
    // ==================== LOGIN CAPTCHA (COM FETCH CORRETO) ====================
    
    async loadLoginCaptcha() {
        // Prevenir múltiplas requisições simultâneas
        if (this.isLoadingCaptcha) {
            console.log('⏳ CAPTCHA já está carregando, aguardando...');
            let waitCount = 0;
            while (this.isLoadingCaptcha && waitCount < 30) {
                await new Promise(resolve => setTimeout(resolve, 100));
                waitCount++;
            }
            if (this.isLoadingCaptcha) {
                console.warn('⚠️ Timeout esperando CAPTCHA, forçando reset');
                this.isLoadingCaptcha = false;
            } else {
                return;
            }
        }
        
        // Rate limiting: evitar requisições muito frequentes
        const now = Date.now();
        if (now - this.lastCaptchaRequestTime < this.minCaptchaInterval) {
            console.log('⏳ Aguardando rate limit do CAPTCHA...');
            await new Promise(resolve => setTimeout(resolve, this.minCaptchaInterval));
        }
        
        this.isLoadingCaptcha = true;
        this.lastCaptchaRequestTime = Date.now();
        
        const img = document.getElementById('loginCaptchaImage');
        const input = document.getElementById('loginCaptchaInput');
        const refreshBtn = document.getElementById('refreshLoginCaptcha');
        const timerEl = document.getElementById('loginCaptchaTimer');
        
        if (!img) {
            console.error('❌ Elemento loginCaptchaImage não encontrado');
            this.isLoadingCaptcha = false;
            return;
        }
        
        // Reset completo do estado antes de carregar novo CAPTCHA
        this.resetCaptchaState('login');
        
        // Atualizar UI para estado de carregamento
        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        }
        
        if (input) {
            input.disabled = true;
            input.value = '';
            input.placeholder = '🔄 Carregando CAPTCHA...';
        }
        
        if (timerEl) {
            timerEl.textContent = '--:--';
            timerEl.classList.remove('expiring', 'expired');
        }
        
        img.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="200" height="70"%3E%3Crect width="200" height="70" fill="%23f0f0f0"/%3E%3Ctext x="35" y="45" font-family="Arial" font-size="18" fill="%23999"%3E🔄 Carregando...%3C/text%3E%3C/svg%3E';
        
        try {
            console.log('🔄 Solicitando CAPTCHA via fetch...');
            
            // 🔥 IMPORTANTE: Usar fetch para ler o header X-Captcha-ID
            const response = await fetch(`${this.apiBase}/auth/captcha/generate?t=${Date.now()}`, {
                cache: 'no-cache',
                headers: { 'Cache-Control': 'no-cache' }
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            // 🔥 LER O ID DO HEADER (agora funciona com Access-Control-Expose-Headers)
            const captchaId = response.headers.get('X-Captcha-ID');
            
            if (!captchaId) {
                console.warn('❌ Header X-Captcha-ID não recebido - verifique CORS no servidor');
                this.generateFallbackCaptcha('login');
                return;
            }
            
            console.log('✅ CAPTCHA ID recebido do header:', captchaId.substring(0, 8) + '...');
            
            // 🔥 CONVERTER RESPOSTA PARA BLOB E CRIAR URL PARA A IMAGEM
            const blob = await response.blob();
            
            // Garantir que o ID antigo foi substituído
            this.captchaId = captchaId;
            console.log('✅ CAPTCHA carregado - NOVO ID:', captchaId.substring(0, 8) + '...');
            
            // Criar URL do blob e atribuir à imagem
            const imageUrl = URL.createObjectURL(blob);
            
            // Limpar URL anterior para evitar memory leak
            if (img.dataset.blobUrl) {
                URL.revokeObjectURL(img.dataset.blobUrl);
            }
            
            img.src = imageUrl;
            img.dataset.blobUrl = imageUrl;
            
            if (input) {
                input.disabled = false;
                input.placeholder = 'Digite os 6 números';
                input.focus();
            }
            
            this.startCaptchaTimer('login');
            
        } catch (error) {
            console.error('❌ Erro ao carregar CAPTCHA:', error);
            this.generateFallbackCaptcha('login');
        } finally {
            if (refreshBtn) {
                refreshBtn.disabled = false;
                refreshBtn.innerHTML = '<i class="fas fa-sync-alt"></i>';
            }
            this.isLoadingCaptcha = false;
        }
    }
    
    generateFallbackCaptcha(type) {
        console.log(`🔄 Gerando CAPTCHA fallback para ${type} (modo offline)`);
        
        const img = document.getElementById(`${type}CaptchaImage`);
        const input = document.getElementById(`${type}CaptchaInput`);
        
        if (!img) return;
        
        this.stopCaptchaTimer(type);
        
        const captchaText = Math.floor(100000 + Math.random() * 900000).toString();
        
        const canvas = document.createElement('canvas');
        canvas.width = 200;
        canvas.height = 70;
        const ctx = canvas.getContext('2d');
        
        // Fundo
        ctx.fillStyle = '#f8f9fa';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        
        // Ruído de fundo
        for (let i = 0; i < 100; i++) {
            ctx.fillStyle = `rgba(0,0,0,${Math.random() * 0.1})`;
            ctx.fillRect(Math.random() * canvas.width, Math.random() * canvas.height, 2, 2);
        }
        
        // Linhas de distorção
        for (let i = 0; i < 5; i++) {
            ctx.beginPath();
            ctx.moveTo(Math.random() * canvas.width, Math.random() * canvas.height);
            ctx.lineTo(Math.random() * canvas.width, Math.random() * canvas.height);
            ctx.strokeStyle = `rgba(102, 126, 234, ${Math.random() * 0.5})`;
            ctx.stroke();
        }
        
        // Texto do CAPTCHA com distorção
        ctx.font = 'bold 36px "Courier New", monospace';
        ctx.fillStyle = '#212529';
        
        const chars = captchaText.split('');
        let x = 25;
        chars.forEach((char, idx) => {
            ctx.save();
            ctx.translate(x + (idx * 25), 50);
            ctx.rotate((Math.random() - 0.5) * 0.3);
            ctx.fillText(char, 0, 0);
            ctx.restore();
        });
        
        img.src = canvas.toDataURL();
        
        if (input) {
            input.dataset.fallbackCaptcha = captchaText;
            input.disabled = false;
            input.placeholder = 'Digite o código';
        }
        
        if (type === 'login') {
            this.captchaId = 'fallback_' + Date.now();
            console.log(`✅ CAPTCHA fallback gerado - ID: ${this.captchaId}`);
            console.log(`   📝 Código (apenas para teste): ${captchaText}`);
        } else {
            this.captchaIdRegister = 'fallback_' + Date.now();
            console.log(`✅ CAPTCHA fallback register gerado - ID: ${this.captchaIdRegister}`);
            console.log(`   📝 Código (apenas para teste): ${captchaText}`);
        }
        
        this.startCaptchaTimer(type);
    }
    
    // ==================== LOGIN ====================
    
    async handleLogin() {
        const email = document.getElementById('loginEmail')?.value;
        const password = document.getElementById('loginPassword')?.value;
        const captchaInput = document.getElementById('loginCaptchaInput')?.value;
        
        // Verificar se tem CAPTCHA válido
        if (!this.captchaId) {
            this.showMessage('🔄 CAPTCHA não carregado. Aguarde...', 'warning');
            await this.loadLoginCaptcha();
            return;
        }
        
        if (this.captchaTimeLeft <= 0 && !this.captchaId?.startsWith('fallback_')) {
            this.showMessage('⏰ CAPTCHA expirou! Clique em atualizar.', 'warning');
            await this.loadLoginCaptcha();
            return;
        }
        
        if (!email || !password || !captchaInput) {
            this.showMessage('❌ Preencha todos os campos', 'error');
            return;
        }
        
        if (!email.includes('@')) {
            this.showMessage('❌ Email inválido', 'error');
            return;
        }
        
        if (password.length < 6) {
            this.showMessage('❌ Senha deve ter no mínimo 6 caracteres', 'error');
            return;
        }
        
        this.loginAttempts++;
        if (this.loginAttempts > this.maxLoginAttempts) {
            this.showMessage('⏳ Muitas tentativas. Aguarde 1 minuto.', 'error');
            setTimeout(() => { this.loginAttempts = 0; }, 60000);
            return;
        }
        
        const loginBtn = document.getElementById('loginBtn');
        const originalText = loginBtn.innerHTML;
        loginBtn.disabled = true;
        loginBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Verificando...';
        
        // Salvar o ID atual antes de enviar
        const currentCaptchaId = this.captchaId;
        console.log('📤 Enviando login com CAPTCHA ID:', currentCaptchaId.substring(0, 8) + '...');
        
        try {
            const isFallback = currentCaptchaId?.startsWith('fallback_');
            
            const headers = {
                'Content-Type': 'application/json'
            };
            
            if (!isFallback && currentCaptchaId) {
                headers['X-Captcha-ID'] = currentCaptchaId;
            }
            
            const response = await fetch(`${this.apiBase}/auth/login`, {
                method: 'POST',
                headers: headers,
                body: JSON.stringify({
                    email: email.trim().toLowerCase(),
                    password: password,
                    captcha_text: captchaInput
                }),
                credentials: 'include'
            });
            
            const data = await response.json();
            
            if (response.ok && data.success !== false) {
                console.log('✅ Login bem-sucedido');
                this.stopCaptchaTimer('login');
                
                this.saveTokens(data.access_token, data.refresh_token, data.expires_in);
                
                this.saveUser({
                    name: data.user_name,
                    email: data.user_email,
                    workshop_name: data.workshop_name,
                    role: data.role,
                    credits: data.credits,
                    plan: data.plan,
                    is_admin: data.is_admin
                });
                
                this.loginAttempts = 0;
                this.showMessage('✅ Login realizado! Redirecionando...', 'success');
                
                setTimeout(() => {
                    window.location.href = '/';
                }, 1000);
                
            } else if (response.status === 401) {
                // Senha errada - resetar estado completo
                this.showMessage('❌ Email ou senha incorretos', 'error');
                console.log('🔄 Senha incorreta - resetando estado do CAPTCHA');
                
                // Reset completo do estado antes de carregar novo CAPTCHA
                this.resetCaptchaState('login');
                await this.loadLoginCaptcha();
                
                loginBtn.disabled = false;
                loginBtn.innerHTML = originalText;
                
            } else if (response.status === 400 && data.detail && 
                       (data.detail.includes('CAPTCHA') || data.detail.includes('captcha'))) {
                // CAPTCHA inválido - resetar estado completo
                this.showMessage('❌ CAPTCHA inválido ou expirado', 'error');
                console.log('🔄 CAPTCHA inválido - resetando estado');
                
                this.resetCaptchaState('login');
                await this.loadLoginCaptcha();
                
                loginBtn.disabled = false;
                loginBtn.innerHTML = originalText;
                
            } else {
                this.showMessage(data.detail || data.message || '❌ Erro no login', 'error');
                await this.loadLoginCaptcha();
                loginBtn.disabled = false;
                loginBtn.innerHTML = originalText;
            }
            
        } catch (error) {
            console.error('❌ Erro no login:', error);
            this.showMessage('❌ Erro de conexão. Tente novamente.', 'error');
            await this.loadLoginCaptcha();
            loginBtn.disabled = false;
            loginBtn.innerHTML = originalText;
        }
    }
    
    initLoginPage() {
        console.log('🔐 Inicializando página de login...');
        this.clearStorage();
        
        // Resetar estado antes de carregar
        this.resetCaptchaState('login');
        
        // Carregar CAPTCHA
        setTimeout(() => {
            if (document.getElementById('loginCaptchaImage')) {
                this.loadLoginCaptcha();
                this.bindLoginEvents();
            }
        }, 50);
    }
    
    bindLoginEvents() {
        const refreshBtn = document.getElementById('refreshLoginCaptcha');
        if (refreshBtn) {
            const newRefreshBtn = refreshBtn.cloneNode(true);
            refreshBtn.parentNode.replaceChild(newRefreshBtn, refreshBtn);
            
            newRefreshBtn.addEventListener('click', async (e) => {
                e.preventDefault();
                console.log('🔄 Usuário solicitou novo CAPTCHA');
                
                // Reset completo do estado no refresh manual
                this.resetCaptchaState('login');
                await this.loadLoginCaptcha();
            });
        }
        
        const loginForm = document.getElementById('loginForm');
        if (loginForm) {
            const newLoginForm = loginForm.cloneNode(true);
            loginForm.parentNode.replaceChild(newLoginForm, loginForm);
            
            newLoginForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.handleLogin();
            });
        }
        
        const forgotBtn = document.getElementById('forgotPassword');
        if (forgotBtn) {
            forgotBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.showMessage('📧 Função de recuperação de senha em breve!', 'info');
            });
        }
        
        const captchaInput = document.getElementById('loginCaptchaInput');
        if (captchaInput) {
            captchaInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this.handleLogin();
                }
            });
        }
    }
    
    // ==================== REGISTER CAPTCHA ====================
    
    async loadRegisterCaptcha() {
        if (this.isRefreshingCaptcha) {
            console.log('⏳ CAPTCHA já está sendo carregado...');
            return;
        }
        
        this.isRefreshingCaptcha = true;
        
        const img = document.getElementById('registerCaptchaImage');
        const input = document.getElementById('registerCaptchaInput');
        const refreshBtn = document.getElementById('refreshRegisterCaptcha');
        const timerEl = document.getElementById('registerCaptchaTimer');
        
        if (!img) {
            this.isRefreshingCaptcha = false;
            return;
        }
        
        this.stopCaptchaTimer('register');
        this.resetCaptchaUI('register');
        
        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        }
        
        if (input) {
            input.disabled = true;
            input.value = '';
            input.placeholder = '🔄 Carregando...';
        }
        
        if (timerEl) {
            timerEl.textContent = '--:--';
            timerEl.classList.remove('expiring', 'expired');
        }
        
        img.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="200" height="70"%3E%3Crect width="200" height="70" fill="%23f0f0f0"/%3E%3Ctext x="35" y="45" font-family="Arial" font-size="18" fill="%23999"%3E🔄 Carregando...%3C/text%3E%3C/svg%3E';
        
        try {
            console.log('🔄 Solicitando CAPTCHA para registro via fetch...');
            
            const response = await fetch(`${this.apiBase}/auth/captcha/generate?t=${Date.now()}`, {
                cache: 'no-cache'
            });
            
            if (!response.ok) throw new Error('Erro no servidor');
            
            const captchaId = response.headers.get('X-Captcha-ID');
            
            if (!captchaId) {
                this.generateFallbackCaptcha('register');
                return;
            }
            
            this.captchaIdRegister = captchaId;
            console.log('✅ CAPTCHA Register ID recebido:', captchaId.substring(0, 8) + '...');
            
            const blob = await response.blob();
            const imageUrl = URL.createObjectURL(blob);
            
            if (img.dataset.blobUrl) {
                URL.revokeObjectURL(img.dataset.blobUrl);
            }
            
            img.src = imageUrl;
            img.dataset.blobUrl = imageUrl;
            
            if (input) {
                input.disabled = false;
                input.placeholder = 'Digite os 6 números';
            }
            
            this.startCaptchaTimer('register');
            
        } catch (error) {
            console.error('❌ Erro CAPTCHA registro:', error);
            this.generateFallbackCaptcha('register');
        } finally {
            if (refreshBtn) {
                refreshBtn.disabled = false;
                refreshBtn.innerHTML = '<i class="fas fa-sync-alt"></i>';
            }
            this.isRefreshingCaptcha = false;
        }
    }
    
    async handleRegister() {
        const name = document.getElementById('regName')?.value;
        const email = document.getElementById('regEmail')?.value;
        const password = document.getElementById('regPassword')?.value;
        const confirm = document.getElementById('regConfirmPassword')?.value;
        const workshop = document.getElementById('regWorkshop')?.value;
        const captchaInput = document.getElementById('registerCaptchaInput')?.value;
        
        if (this.registerCaptchaTimeLeft <= 0 && !this.captchaIdRegister?.startsWith('fallback_')) {
            this.showMessage('⏰ CAPTCHA expirou! Clique em atualizar.', 'warning');
            this.loadRegisterCaptcha();
            return;
        }
        
        if (!name || !email || !password || !confirm || !workshop || !captchaInput) {
            this.showMessage('❌ Preencha todos os campos', 'error');
            return;
        }
        
        if (password !== confirm) {
            this.showMessage('❌ As senhas não coincidem', 'error');
            return;
        }
        
        if (password.length < 6) {
            this.showMessage('❌ A senha deve ter no mínimo 6 caracteres', 'error');
            return;
        }
        
        if (!email.includes('@')) {
            this.showMessage('❌ Email inválido', 'error');
            return;
        }
        
        const registerBtn = document.getElementById('registerBtn');
        const originalText = registerBtn.innerHTML;
        registerBtn.disabled = true;
        registerBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Criando conta...';
        
        try {
            const isFallback = this.captchaIdRegister?.startsWith('fallback_');
            
            const headers = {
                'Content-Type': 'application/json'
            };
            
            if (!isFallback && this.captchaIdRegister) {
                headers['X-Captcha-ID'] = this.captchaIdRegister;
            }
            
            const response = await fetch(`${this.apiBase}/auth/register`, {
                method: 'POST',
                headers: headers,
                body: JSON.stringify({
                    name: name.trim(),
                    email: email.trim().toLowerCase(),
                    password: password,
                    workshop_name: workshop.trim(),
                    captcha_text: captchaInput
                })
            });
            
            const data = await response.json();
            
            if (response.ok) {
                this.stopCaptchaTimer('register');
                
                this.showMessage('✅ Conta criada com sucesso! Faça login.', 'success');
                document.getElementById('registerForm').reset();
                
                const loginTab = document.getElementById('login-tab');
                if (loginTab) {
                    loginTab.click();
                    const loginEmail = document.getElementById('loginEmail');
                    if (loginEmail) {
                        loginEmail.value = email.trim().toLowerCase();
                    }
                    this.loadLoginCaptcha();
                }
            } else {
                this.showMessage(data.detail || '❌ Erro no registro', 'error');
                this.loadRegisterCaptcha();
                registerBtn.disabled = false;
                registerBtn.innerHTML = originalText;
            }
            
        } catch (error) {
            console.error('❌ Erro no registro:', error);
            this.showMessage('❌ Erro de conexão', 'error');
            this.loadRegisterCaptcha();
            registerBtn.disabled = false;
            registerBtn.innerHTML = originalText;
        }
    }
    
    initRegisterPage() {
        console.log('🔐 Inicializando página de registro...');
        setTimeout(() => {
            if (document.getElementById('registerCaptchaImage')) {
                this.loadRegisterCaptcha();
                this.bindRegisterEvents();
            }
        }, 100);
    }
    
    bindRegisterEvents() {
        const refreshBtn = document.getElementById('refreshRegisterCaptcha');
        if (refreshBtn) {
            const newRefreshBtn = refreshBtn.cloneNode(true);
            refreshBtn.parentNode.replaceChild(newRefreshBtn, refreshBtn);
            
            newRefreshBtn.addEventListener('click', (e) => {
                e.preventDefault();
                console.log('🔄 Solicitado novo CAPTCHA para registro');
                this.loadRegisterCaptcha();
            });
        }
        
        const registerForm = document.getElementById('registerForm');
        if (registerForm) {
            const newRegisterForm = registerForm.cloneNode(true);
            registerForm.parentNode.replaceChild(newRegisterForm, registerForm);
            
            newRegisterForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.handleRegister();
            });
        }
    }
    
    // ==================== LOGOUT ====================
    
    async logout() {
        if (!confirm('Deseja realmente sair?')) return;
        
        const refreshToken = localStorage.getItem('refresh_token');
        const accessToken = localStorage.getItem('access_token');
        
        try {
            if (refreshToken) {
                await fetch(`${this.apiBase}/auth/logout`, {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        'Authorization': accessToken ? `Bearer ${accessToken}` : ''
                    },
                    body: JSON.stringify({ refresh_token: refreshToken }),
                    credentials: 'include'
                });
            }
        } catch (error) {
            console.error('Erro no logout:', error);
        } finally {
            this.clearStorage();
            if (this.tokenCheckInterval) clearInterval(this.tokenCheckInterval);
            window.location.href = '/login.html';
        }
    }
    
    // ==================== UI ====================
    
    updateUserUI() {
        const userNameEl = document.getElementById('userName');
        if (userNameEl) userNameEl.textContent = this.user?.name || 'Usuário';
        
        const workshopEl = document.getElementById('workshopName');
        if (workshopEl) workshopEl.textContent = this.user?.workshop_name || 'Oficina';
        
        this.updateCreditsDisplay();
    }
    
    updateCreditsDisplay() {
        const credits = this.getCreditsDisplay();
        document.querySelectorAll('#navbarCredits span, #creditsCount').forEach(el => {
            if (el) el.textContent = credits;
        });
    }
    
    // ==================== UTILITIES ====================
    
    isLoginPage() {
        return window.location.pathname.includes('login.html') || 
               window.location.pathname === '/login' ||
               window.location.pathname === '/';
    }
    
    isRegisterPage() {
        return window.location.pathname.includes('register.html') || 
               window.location.pathname === '/register';
    }
    
    isAuthenticated() {
        return !!localStorage.getItem('access_token');
    }
    
    redirectToLogin() {
        this.clearStorage();
        if (!this.isLoginPage() && !this.isRegisterPage()) {
            this.showMessage('🔐 Faça login para continuar', 'info');
            setTimeout(() => window.location.href = '/login.html', 1000);
        }
    }
    
    isAdmin() {
        return this.user?.is_admin === true;
    }
    
    isPremium() {
        return this.user?.is_premium === true || this.user?.plan === 'premium_mensal';
    }
    
    getCreditsDisplay() {
        if (this.isAdmin()) return '∞';
        return this.user?.credits || 0;
    }
    
    getCurrentUser() {
        return this.user || {};
    }
    
    showMessage(message, type = 'info') {
        const messageDiv = document.getElementById('authMessage');
        if (!messageDiv) {
            alert(message);
            return;
        }
        
        const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
        const alertClass = type === 'error' ? 'danger' : type;
        
        messageDiv.innerHTML = `
            <div class="alert alert-${alertClass} alert-dismissible fade show" role="alert">
                <strong>${icons[type] || ''}</strong> ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        
        setTimeout(() => {
            const alert = messageDiv.querySelector('.alert');
            if (alert) {
                alert.classList.remove('show');
                setTimeout(() => messageDiv.innerHTML = '', 300);
            }
        }, 5000);
    }
}

// ==================== INICIALIZAÇÃO GLOBAL ====================
document.addEventListener('DOMContentLoaded', () => {
    window.appAuth = new Auth();
});

// Funções globais para uso em outros scripts
window.isAdmin = () => window.appAuth?.isAdmin() || false;
window.isPremium = () => window.appAuth?.isPremium() || false;
window.getCreditsDisplay = () => window.appAuth?.getCreditsDisplay() || '0';
window.getCurrentUser = () => window.appAuth?.getCurrentUser() || {};
window.logout = () => window.appAuth?.logout();
window.refreshToken = () => window.appAuth?.refreshToken();

console.log('✅ auth.js carregado - Versão com fetch() para CAPTCHA');
console.log('   🔄 CAPTCHA: fetch() para ler header X-Captcha-ID');
console.log('   🔄 Reset completo de estado antes de cada CAPTCHA');
console.log('   🔄 Prevenção de múltiplas requisições simultâneas');
console.log('   🔄 Rate limiting entre requisições de CAPTCHA');
console.log('   🔄 Login: CAPTCHA primeiro, depois senha');