// frontend/js/auth.js - VERSÃO FINAL COMPLETAMENTE CORRIGIDA
/*
 * auth.js - Sistema de Autenticação
 * 
 * Ciclo de vida do CAPTCHA:
 * 1. Geração → CAPTCHA válido por 2 minutos (120 segundos)
 * 2. Cronômetro visual mostrando o tempo restante
 * 3. Se usuário gerar novo → anterior é desativado automaticamente
 * 4. Expiração automática após 2 minutos
 * 5. Uso único (valida e remove)
 * 
 * FLUXO CORRETO:
 * - CAPTCHA ID vai no HEADER (X-Captcha-ID)
 * - CAPTCHA TEXT vai no BODY (JSON)
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
        
        // Timer properties
        this.captchaTimer = null;
        this.captchaTimeLeft = 120;
        this.registerCaptchaTimer = null;
        this.registerCaptchaTimeLeft = 120;
        
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
        localStorage.setItem('refresh_token', refreshToken);
        
        if (expiresIn) {
            const expiresAt = Date.now() + (expiresIn * 1000);
            localStorage.setItem('token_expires_at', expiresAt.toString());
            console.log(`⏰ Token expira em: ${new Date(expiresAt).toLocaleTimeString()}`);
        }
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
    
    async refreshToken() {
        const refreshToken = localStorage.getItem('refresh_token');
        if (!refreshToken) return false;
        
        try {
            const response = await fetch(`${this.apiBase}/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: refreshToken })
            });
            
            if (response.ok) {
                const data = await response.json();
                this.saveTokens(data.access_token, data.refresh_token, data.expires_in);
                console.log('✅ Token renovado com sucesso');
                return true;
            }
        } catch (error) {
            console.error('❌ Erro ao renovar token:', error);
        }
        
        return false;
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
            
            return { status: 'error' };
            
        } catch (error) {
            console.error('Erro ao verificar token:', error);
            return { status: 'error' };
        }
    }
    
    // ==================== INIT ====================
    
    async init() {
        console.log('🔧 Auth inicializado - Ciclo de vida do CAPTCHA ativo');
        
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
            }
        }
        
        // Disparar evento que o auth está pronto
        window.dispatchEvent(new Event('authReady'));
    }
    
    // ==================== TIMER FUNCTIONS ====================
    
    startCaptchaTimer(type = 'login') {
        const timerId = type === 'login' ? 'loginCaptchaTimer' : 'registerCaptchaTimer';
        const timerElement = document.getElementById(timerId);
        
        if (!timerElement) return;
        
        // Parar timer existente
        if (type === 'login' && this.captchaTimer) {
            clearInterval(this.captchaTimer);
            this.captchaTimer = null;
        } else if (type === 'register' && this.registerCaptchaTimer) {
            clearInterval(this.registerCaptchaTimer);
            this.registerCaptchaTimer = null;
        }
        
        // Reset time
        if (type === 'login') {
            this.captchaTimeLeft = 120;
        } else {
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
                // Timer expirou
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
                    
                    const container = document.getElementById(`${type}CaptchaContainer`);
                    if (container) {
                        container.classList.add('captcha-expired');
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
        const container = document.getElementById(`${type}CaptchaContainer`);
        
        if (input) {
            input.disabled = false;
            input.value = '';
            input.placeholder = 'Digite os 6 números';
        }
        
        if (timerEl) {
            timerEl.classList.remove('expired', 'expiring');
        }
        
        if (container) {
            container.classList.remove('captcha-expired');
        }
    }
    
    // ==================== LOGIN CAPTCHA ====================
    
    async loadLoginCaptcha() {
        if (this.isRefreshingCaptcha) {
            console.log('⏳ CAPTCHA já está sendo carregado...');
            return;
        }
        
        this.isRefreshingCaptcha = true;
        
        const img = document.getElementById('loginCaptchaImage');
        const input = document.getElementById('loginCaptchaInput');
        const refreshBtn = document.getElementById('refreshLoginCaptcha');
        const timerEl = document.getElementById('loginCaptchaTimer');
        
        if (!img) {
            console.error('Elemento loginCaptchaImage não encontrado');
            this.isRefreshingCaptcha = false;
            return;
        }
        
        this.stopCaptchaTimer('login');
        this.resetCaptchaUI('login');
        
        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        }
        
        if (input) {
            input.disabled = true;
            input.value = '';
            input.placeholder = '🔄 Carregando novo CAPTCHA...';
        }
        
        if (timerEl) {
            timerEl.textContent = '--:--';
            timerEl.classList.remove('expiring', 'expired');
        }
        
        img.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="200" height="70"%3E%3Crect width="200" height="70" fill="%23f0f0f0"/%3E%3Ctext x="35" y="45" font-family="Arial" font-size="18" fill="%23999"%3E🔄 Carregando...%3C/text%3E%3C/svg%3E';
        
        try {
            console.log('🔄 Solicitando novo CAPTCHA...');
            
            const response = await fetch(`${this.apiBase}/auth/captcha/generate?t=${Date.now()}`, {
                cache: 'no-cache',
                headers: { 'Cache-Control': 'no-cache' }
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            // ✅ Ler o ID do HEADER (exposed via CORS)
            const captchaId = response.headers.get('X-Captcha-ID');
            
            if (!captchaId) {
                console.warn('Header X-Captcha-ID não recebido, usando fallback');
                this.generateFallbackCaptcha('login');
                return;
            }
            
            this.captchaId = captchaId;
            console.log('✅ Novo CAPTCHA gerado - ID:', captchaId.substring(0, 8) + '...');
            console.log('   🔄 CAPTCHA anterior foi desativado automaticamente');
            
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
            this.isRefreshingCaptcha = false;
        }
    }
    
    generateFallbackCaptcha(type) {
        console.log(`🔄 Gerando CAPTCHA fallback para ${type}`);
        
        const img = document.getElementById(`${type}CaptchaImage`);
        const input = document.getElementById(`${type}CaptchaInput`);
        
        if (!img) return;
        
        this.stopCaptchaTimer(type);
        
        const captchaText = Math.floor(100000 + Math.random() * 900000).toString();
        
        const canvas = document.createElement('canvas');
        canvas.width = 200;
        canvas.height = 70;
        const ctx = canvas.getContext('2d');
        
        ctx.fillStyle = '#f8f9fa';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        
        ctx.font = 'bold 36px "Courier New", monospace';
        ctx.fillStyle = '#212529';
        ctx.fillText(captchaText, 25, 50);
        
        for (let i = 0; i < 50; i++) {
            ctx.fillStyle = `rgba(0,0,0,${Math.random() * 0.2})`;
            ctx.fillRect(Math.random() * canvas.width, Math.random() * canvas.height, 2, 2);
        }
        
        img.src = canvas.toDataURL();
        
        if (input) {
            input.dataset.fallbackCaptcha = captchaText;
            input.disabled = false;
            input.placeholder = 'Digite o código';
        }
        
        if (type === 'login') {
            this.captchaId = 'fallback_' + Date.now();
        } else {
            this.captchaIdRegister = 'fallback_' + Date.now();
        }
        
        this.startCaptchaTimer(type);
        
        console.log(`✅ CAPTCHA fallback gerado: ${captchaText}`);
    }
    
    // ==================== LOGIN ====================
    
    async handleLogin() {
        const email = document.getElementById('loginEmail')?.value;
        const password = document.getElementById('loginPassword')?.value;
        const captchaInput = document.getElementById('loginCaptchaInput')?.value;
        
        // Verificar se CAPTCHA expirou
        if (this.captchaTimeLeft <= 0 && !this.captchaId?.startsWith('fallback_')) {
            this.showMessage('⏰ CAPTCHA expirou! Clique em atualizar.', 'warning');
            this.loadLoginCaptcha();
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
        
        try {
            const isFallback = this.captchaId?.startsWith('fallback_');
            
            if (isFallback) {
                const inputEl = document.getElementById('loginCaptchaInput');
                const fallbackText = inputEl?.dataset.fallbackCaptcha;
                if (captchaInput !== fallbackText) {
                    this.showMessage('❌ CAPTCHA incorreto', 'error');
                    this.loadLoginCaptcha();
                    loginBtn.disabled = false;
                    loginBtn.innerHTML = originalText;
                    return;
                }
            }
            
            // ✅ CONFIGURAÇÃO CORRETA:
            // - captcha_id vai no HEADER (X-Captcha-ID)
            // - captcha_text vai no BODY (JSON)
            const headers = {
                'Content-Type': 'application/json'
            };
            
            if (!isFallback && this.captchaId) {
                headers['X-Captcha-ID'] = this.captchaId;
                console.log('📤 Enviando CAPTCHA ID no header:', this.captchaId.substring(0, 8) + '...');
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
                console.log('✅ Login bem-sucedido - CAPTCHA validado e removido');
                
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
                
            } else {
                this.showMessage(data.detail || data.message || '❌ Erro no login', 'error');
                this.loadLoginCaptcha();
                loginBtn.disabled = false;
                loginBtn.innerHTML = originalText;
            }
            
        } catch (error) {
            console.error('❌ Erro no login:', error);
            this.showMessage('❌ Erro de conexão. Tente novamente.', 'error');
            this.loadLoginCaptcha();
            loginBtn.disabled = false;
            loginBtn.innerHTML = originalText;
        }
    }
    
    initLoginPage() {
        console.log('🔐 Inicializando página de login...');
        this.clearStorage();
        
        setTimeout(() => {
            if (document.getElementById('loginCaptchaImage')) {
                this.loadLoginCaptcha();
                this.bindLoginEvents();
            }
        }, 100);
    }
    
    bindLoginEvents() {
        const refreshBtn = document.getElementById('refreshLoginCaptcha');
        if (refreshBtn) {
            const newRefreshBtn = refreshBtn.cloneNode(true);
            refreshBtn.parentNode.replaceChild(newRefreshBtn, refreshBtn);
            
            newRefreshBtn.addEventListener('click', (e) => {
                e.preventDefault();
                console.log('🔄 Solicitado novo CAPTCHA - anterior será desativado');
                this.loadLoginCaptcha();
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
        
        try {
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
            console.log('✅ Novo CAPTCHA Register ID:', captchaId.substring(0, 8) + '...');
            
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
        
        try {
            if (refreshToken) {
                await fetch(`${this.apiBase}/auth/logout`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
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

console.log('✅ auth.js carregado - Ciclo de vida do CAPTCHA ativo');
console.log('   ⏰ Cronômetro: 2 minutos de validade');
console.log('   🔄 CAPTCHA: Uso único | Novo desativa anterior');
console.log('   📍 CAPTCHA ID vai no HEADER | CAPTCHA Text vai no BODY');