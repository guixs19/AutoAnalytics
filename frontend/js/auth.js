// frontend/js/auth.js - VERSÃO COM CAPTCHA MATEMÁTICO (SOMA SIMPLES)

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
        
        // Timer properties
        this.captchaTimer = null;
        this.captchaTimeLeft = 120;
        this.registerCaptchaTimer = null;
        this.registerCaptchaTimeLeft = 120;
        
        // Flag para evitar múltiplas requisições
        this.isLoadingCaptcha = false;
        this.isLoadingRegisterCaptcha = false;
        
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
        }
    }
    
    clearStorage() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
        localStorage.removeItem('token_expires_at');
        this.user = {};
    }
    
    // ==================== CAPTCHA MATEMÁTICO ====================
    
    async loadLoginCaptcha() {
        if (this.isLoadingCaptcha) {
            console.log('⏳ CAPTCHA já está carregando...');
            return;
        }
        
        this.isLoadingCaptcha = true;
        
        const img = document.getElementById('loginCaptchaImage');
        const input = document.getElementById('loginCaptchaInput');
        const refreshBtn = document.getElementById('refreshLoginCaptcha');
        const timerEl = document.getElementById('loginCaptchaTimer');
        
        if (!img) {
            this.isLoadingCaptcha = false;
            return;
        }
        
        // Reset UI
        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        }
        
        if (input) {
            input.disabled = true;
            input.value = '';
            input.placeholder = '🔄 Carregando desafio matemático...';
        }
        
        if (timerEl) {
            timerEl.textContent = '--:--';
            timerEl.classList.remove('expiring', 'expired');
        }
        
        // Limpar timer anterior
        if (this.captchaTimer) {
            clearInterval(this.captchaTimer);
            this.captchaTimer = null;
        }
        
        img.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="240" height="80"%3E%3Crect width="240" height="80" fill="%23667eea"/%3E%3Ctext x="120" y="45" font-family="Arial" font-size="24" fill="white" text-anchor="middle"%3E🔢 Carregando...%3C/text%3E%3C/svg%3E';
        
        try {
            const startTime = Date.now();
            console.log('🧮 Gerando desafio matemático...');
            
            const response = await fetch(`${this.apiBase}/auth/captcha/generate?t=${Date.now()}`, {
                cache: 'no-cache',
                headers: { 'Cache-Control': 'no-cache' }
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            this.captchaId = response.headers.get('X-Captcha-ID');
            
            if (!this.captchaId) {
                throw new Error('X-Captcha-ID não recebido');
            }
            
            const blob = await response.blob();
            const imageUrl = URL.createObjectURL(blob);
            
            if (img.dataset.blobUrl) {
                URL.revokeObjectURL(img.dataset.blobUrl);
            }
            
            img.src = imageUrl;
            img.dataset.blobUrl = imageUrl;
            
            const elapsed = Date.now() - startTime;
            console.log(`✅ Desafio matemático gerado em ${elapsed}ms - ID: ${this.captchaId.substring(0, 8)}...`);
            
            if (input) {
                input.disabled = false;
                input.placeholder = 'Ex: 8 (resultado da soma)';
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
    
    startCaptchaTimer(type = 'login') {
        const timerId = type === 'login' ? 'loginCaptchaTimer' : 'registerCaptchaTimer';
        const timerElement = document.getElementById(timerId);
        
        if (!timerElement) return;
        
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
                } else {
                    if (this.registerCaptchaTimer) clearInterval(this.registerCaptchaTimer);
                    this.registerCaptchaTimer = null;
                }
                
                timerElement.textContent = '00:00';
                timerElement.classList.add('expired');
                
                const input = document.getElementById(`${type}CaptchaInput`);
                if (input) {
                    input.disabled = true;
                    input.placeholder = '⏰ Desafio expirado! Clique em atualizar';
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
    }
    
    generateFallbackCaptcha(type) {
        console.log(`🔄 Gerando desafio matemático fallback para ${type}`);
        
        const img = document.getElementById(`${type}CaptchaImage`);
        const input = document.getElementById(`${type}CaptchaInput`);
        
        if (!img) return;
        
        if (type === 'login') {
            if (this.captchaTimer) clearInterval(this.captchaTimer);
        } else {
            if (this.registerCaptchaTimer) clearInterval(this.registerCaptchaTimer);
        }
        
        // Gerar números aleatórios para soma
        const n1 = Math.floor(Math.random() * 9) + 1;
        const n2 = Math.floor(Math.random() * 9) + 1;
        const resultado = n1 + n2;
        const pergunta = `${n1} + ${n2} = ?`;
        
        const canvas = document.createElement('canvas');
        canvas.width = 240;
        canvas.height = 80;
        const ctx = canvas.getContext('2d');
        
        // Fundo gradiente
        const gradient = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
        gradient.addColorStop(0, '#667eea');
        gradient.addColorStop(1, '#764ba2');
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        
        // Ruído visual
        for (let i = 0; i < 150; i++) {
            ctx.fillStyle = `rgba(255,255,255,${Math.random() * 0.15})`;
            ctx.fillRect(Math.random() * canvas.width, Math.random() * canvas.height, 2, 2);
        }
        
        // Linhas decorativas
        for (let i = 0; i < 8; i++) {
            ctx.beginPath();
            ctx.moveTo(Math.random() * canvas.width, Math.random() * canvas.height);
            ctx.lineTo(Math.random() * canvas.width, Math.random() * canvas.height);
            ctx.strokeStyle = `rgba(255,255,255,${Math.random() * 0.2})`;
            ctx.stroke();
        }
        
        // Texto do desafio
        ctx.font = 'bold 34px "Courier New", monospace';
        ctx.fillStyle = 'white';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(pergunta, canvas.width / 2, canvas.height / 2);
        
        img.src = canvas.toDataURL();
        
        if (input) {
            input.dataset.fallbackCaptcha = resultado.toString();
            input.disabled = false;
            input.placeholder = 'Ex: resultado da soma';
        }
        
        if (type === 'login') {
            this.captchaId = 'fallback_' + Date.now();
            console.log(`✅ Desafio fallback: ${pergunta} = ${resultado}`);
        } else {
            this.captchaIdRegister = 'fallback_' + Date.now();
            console.log(`✅ Desafio fallback register: ${pergunta} = ${resultado}`);
        }
        
        this.startCaptchaTimer(type);
    }
    
    async loadRegisterCaptcha() {
        if (this.isLoadingRegisterCaptcha) {
            console.log('⏳ CAPTCHA register já está carregando...');
            return;
        }
        
        this.isLoadingRegisterCaptcha = true;
        
        const img = document.getElementById('registerCaptchaImage');
        const input = document.getElementById('registerCaptchaInput');
        const refreshBtn = document.getElementById('refreshRegisterCaptcha');
        const timerEl = document.getElementById('registerCaptchaTimer');
        
        if (!img) {
            this.isLoadingRegisterCaptcha = false;
            return;
        }
        
        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        }
        
        if (input) {
            input.disabled = true;
            input.value = '';
            input.placeholder = '🔄 Carregando desafio matemático...';
        }
        
        if (timerEl) {
            timerEl.textContent = '--:--';
        }
        
        if (this.registerCaptchaTimer) {
            clearInterval(this.registerCaptchaTimer);
            this.registerCaptchaTimer = null;
        }
        
        img.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="240" height="80"%3E%3Crect width="240" height="80" fill="%23667eea"/%3E%3Ctext x="120" y="45" font-family="Arial" font-size="24" fill="white" text-anchor="middle"%3E🔢 Carregando...%3C/text%3E%3C/svg%3E';
        
        try {
            const response = await fetch(`${this.apiBase}/auth/captcha/generate?t=${Date.now()}`, {
                cache: 'no-cache'
            });
            
            if (!response.ok) throw new Error('Erro no servidor');
            
            this.captchaIdRegister = response.headers.get('X-Captcha-ID');
            
            if (!this.captchaIdRegister) {
                throw new Error('X-Captcha-ID não recebido');
            }
            
            const blob = await response.blob();
            const imageUrl = URL.createObjectURL(blob);
            
            if (img.dataset.blobUrl) {
                URL.revokeObjectURL(img.dataset.blobUrl);
            }
            
            img.src = imageUrl;
            img.dataset.blobUrl = imageUrl;
            
            if (input) {
                input.disabled = false;
                input.placeholder = 'Ex: 8 (resultado da soma)';
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
            this.isLoadingRegisterCaptcha = false;
        }
    }
    
    // ==================== LOGIN ====================
    
    async handleLogin() {
        const email = document.getElementById('loginEmail')?.value;
        const password = document.getElementById('loginPassword')?.value;
        const captchaInput = document.getElementById('loginCaptchaInput')?.value;
        
        if (!this.captchaId) {
            this.showMessage('🧮 CAPTCHA não carregado. Aguarde...', 'warning');
            await this.loadLoginCaptcha();
            return;
        }
        
        if (this.captchaTimeLeft <= 0 && !this.captchaId?.startsWith('fallback_')) {
            this.showMessage('⏰ Desafio matemático expirou! Clique em atualizar.', 'warning');
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
        
        // Validar se resposta é número
        if (isNaN(parseInt(captchaInput))) {
            this.showMessage('🧮 Digite apenas o NÚMERO do resultado da soma', 'warning');
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
        
        const currentCaptchaId = this.captchaId;
        
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
                
                if (this.captchaTimer) clearInterval(this.captchaTimer);
                
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
                this.showMessage('❌ Email ou senha incorretos', 'error');
                this.captchaId = null;
                await this.loadLoginCaptcha();
                loginBtn.disabled = false;
                loginBtn.innerHTML = originalText;
                
            } else if (response.status === 400 && data.detail && 
                       (data.detail.includes('CAPTCHA') || data.detail.includes('captcha') || data.detail.includes('som'))) {
                this.showMessage('🧮 Resposta incorreta! Calcule a soma corretamente.', 'error');
                this.captchaId = null;
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
    
    async handleRegister() {
        const name = document.getElementById('regName')?.value;
        const email = document.getElementById('regEmail')?.value;
        const password = document.getElementById('regPassword')?.value;
        const confirm = document.getElementById('regConfirmPassword')?.value;
        const workshop = document.getElementById('regWorkshop')?.value;
        const captchaInput = document.getElementById('registerCaptchaInput')?.value;
        
        if (this.registerCaptchaTimeLeft <= 0 && !this.captchaIdRegister?.startsWith('fallback_')) {
            this.showMessage('⏰ Desafio matemático expirou! Clique em atualizar.', 'warning');
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
        
        // Validar se resposta é número
        if (isNaN(parseInt(captchaInput))) {
            this.showMessage('🧮 Digite apenas o NÚMERO do resultado da soma', 'warning');
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
                if (this.registerCaptchaTimer) clearInterval(this.registerCaptchaTimer);
                
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
    
    async refreshToken() {
        const refreshToken = localStorage.getItem('refresh_token');
        if (!refreshToken) return false;
        
        try {
            const response = await fetch(`${this.apiBase}/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: refreshToken }),
                credentials: 'include'
            });
            
            const data = await response.json();
            
            if (response.ok && data.access_token) {
                this.saveTokens(data.access_token, data.refresh_token, data.expires_in);
                return true;
            }
            
            return false;
            
        } catch (error) {
            console.error('❌ Erro ao renovar token:', error);
            return false;
        }
    }
    
    async ensureValidToken() {
        const token = localStorage.getItem('access_token');
        if (!token) return false;
        
        const timeLeft = this.getTokenTimeLeft();
        
        if (timeLeft <= 120000) {
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
                return { status: 'valid', data };
            }
            
            if (data.status === 'refreshed' && data.access_token) {
                this.saveTokens(data.access_token, data.refresh_token, data.expires_in);
                return { status: 'valid', data };
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
        console.log('🔧 Auth inicializado - Versão com CAPTCHA Matemático');
        console.log('🧮 Desafio: soma simples de 1+1 até 9+9');
        console.log('📱 Otimizado para mobile com teclado numérico');
        
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
                await this.refreshToken();
            }
        }, 60000);
    }
    
    initLoginPage() {
        console.log('🔐 Inicializando página de login com desafio matemático...');
        this.clearStorage();
        
        this.captchaId = null;
        if (this.captchaTimer) clearInterval(this.captchaTimer);
        this.captchaTimeLeft = 120;
        
        setTimeout(() => {
            if (document.getElementById('loginCaptchaImage')) {
                this.loadLoginCaptcha();
                this.bindLoginEvents();
            }
        }, 100);
    }
    
    initRegisterPage() {
        console.log('🔐 Inicializando página de registro com desafio matemático...');
        
        setTimeout(() => {
            if (document.getElementById('registerCaptchaImage')) {
                this.loadRegisterCaptcha();
                this.bindRegisterEvents();
            }
        }, 100);
    }
    
    bindLoginEvents() {
        const refreshBtn = document.getElementById('refreshLoginCaptcha');
        if (refreshBtn) {
            const newRefreshBtn = refreshBtn.cloneNode(true);
            refreshBtn.parentNode.replaceChild(newRefreshBtn, refreshBtn);
            
            newRefreshBtn.addEventListener('click', async (e) => {
                e.preventDefault();
                console.log('🔄 Solicitando novo desafio matemático');
                this.captchaId = null;
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
    
    bindRegisterEvents() {
        const refreshBtn = document.getElementById('refreshRegisterCaptcha');
        if (refreshBtn) {
            const newRefreshBtn = refreshBtn.cloneNode(true);
            refreshBtn.parentNode.replaceChild(newRefreshBtn, refreshBtn);
            
            newRefreshBtn.addEventListener('click', (e) => {
                e.preventDefault();
                console.log('🔄 Solicitando novo desafio matemático para registro');
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

// Funções globais
window.isAdmin = () => window.appAuth?.isAdmin() || false;
window.isPremium = () => window.appAuth?.isPremium() || false;
window.getCreditsDisplay = () => window.appAuth?.getCreditsDisplay() || '0';
window.getCurrentUser = () => window.appAuth?.getCurrentUser() || {};
window.logout = () => window.appAuth?.logout();
window.refreshToken = () => window.appAuth?.refreshToken();

console.log('✅ auth.js carregado - Versão com CAPTCHA Matemático');
console.log('   🧮 Desafio: soma simples (ex: 5 + 3 = ?)');
console.log('   📱 Otimizado para mobile com inputmode="numeric"');
console.log('   ⚡ Geração ultrarrápida com SVG');