// frontend/js/auth.js - VERSÃO COMPLETA CORRIGIDA
/**
 * Módulo de Autenticação - AutoAnalytics
 * FLUXO: login → dashboard | register → login
 */

class Auth {
    constructor() {
        this.apiBase = '/api';
        
        this.currentUser = null;
        this._isAuthenticated = false;
        this.userData = null;
        this.loginCaptchaId = null;
        this.registerCaptchaId = null;
        this.loginCaptchaTimer = null;
        this.registerCaptchaTimer = null;
        this.initialized = false;
        this.isRegisterCaptchaLoaded = false;
        
        this._isRefreshing = false;
        this._refreshPromise = null;
        this._uiUpdateTimeout = null;
        this._initializing = false;
        
        this.init();
    }
    
    // ==============================================
    // GETTER / SETTER
    // ==============================================
    
    get isAuthenticated() {
        return this._isAuthenticated;
    }
    
    set isAuthenticated(value) {
        const changed = this._isAuthenticated !== value;
        this._isAuthenticated = value;
        if (changed) {
            console.log(`🔄 Estado de autenticação: ${value}`);
            this._scheduleUIUpdate();
        }
    }
    
    _scheduleUIUpdate() {
        if (this._uiUpdateTimeout) {
            clearTimeout(this._uiUpdateTimeout);
        }
        this._uiUpdateTimeout = setTimeout(() => {
            this.updateUI();
            this._uiUpdateTimeout = null;
        }, 50);
    }
    
    // ==============================================
    // CAPTCHA
    // ==============================================
    
    async loadCaptcha(sessionType = 'login') {
        try {
            const url = `${this.apiBase}/auth/captcha/generate?session_type=${sessionType}&t=${Date.now()}`;
            
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache'
                }
            });
            
            if (!response.ok) {
                throw new Error(`Erro HTTP ${response.status}`);
            }
            
            const captchaId = response.headers.get('X-Captcha-ID');
            
            if (!captchaId) {
                throw new Error('CAPTCHA ID não recebido');
            }
            
            if (sessionType === 'login') {
                this.loginCaptchaId = captchaId;
            } else {
                this.registerCaptchaId = captchaId;
                this.isRegisterCaptchaLoaded = true;
            }
            
            const hiddenField = document.getElementById(`${sessionType}CaptchaId`);
            if (hiddenField) {
                hiddenField.value = captchaId;
            }
            
            const blob = await response.blob();
            const imageUrl = URL.createObjectURL(blob);
            
            const captchaImage = document.getElementById(`${sessionType}CaptchaImage`);
            if (captchaImage) {
                if (captchaImage.src && captchaImage.src.startsWith('blob:')) {
                    URL.revokeObjectURL(captchaImage.src);
                }
                captchaImage.src = imageUrl;
            }
            
            this.startCaptchaTimer(sessionType);
            
            const captchaInput = document.getElementById(`${sessionType}CaptchaInput`);
            if (captchaInput) {
                captchaInput.value = '';
                captchaInput.disabled = false;
                captchaInput.placeholder = 'Digite os 4 números';
                captchaInput.focus();
            }
            
            return captchaId;
            
        } catch (error) {
            console.error('Erro ao carregar CAPTCHA:', error);
            this.showCaptchaError(sessionType);
            return null;
        }
    }
    
    startCaptchaTimer(sessionType) {
        if (sessionType === 'login' && this.loginCaptchaTimer) {
            clearInterval(this.loginCaptchaTimer);
            this.loginCaptchaTimer = null;
        }
        if (sessionType === 'register' && this.registerCaptchaTimer) {
            clearInterval(this.registerCaptchaTimer);
            this.registerCaptchaTimer = null;
        }
        
        const expirySeconds = 120;
        let remaining = expirySeconds;
        
        const timerElement = document.getElementById(`${sessionType}CaptchaTimer`);
        
        if (timerElement) {
            timerElement.textContent = '02:00';
            timerElement.classList.remove('expiring', 'expired');
        }
        
        const timer = setInterval(() => {
            remaining--;
            
            if (timerElement) {
                const minutes = Math.floor(remaining / 60);
                const seconds = remaining % 60;
                timerElement.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
                
                if (remaining <= 10) {
                    timerElement.classList.add('expiring');
                } else {
                    timerElement.classList.remove('expiring');
                }
            }
            
            if (remaining <= 0) {
                clearInterval(timer);
                if (timerElement) {
                    timerElement.textContent = '00:00';
                    timerElement.classList.add('expired');
                }
                
                const captchaInput = document.getElementById(`${sessionType}CaptchaInput`);
                if (captchaInput) {
                    captchaInput.disabled = true;
                    captchaInput.placeholder = 'Expirado - Clique em 🔄';
                }
            }
        }, 1000);
        
        if (sessionType === 'login') {
            this.loginCaptchaTimer = timer;
        } else {
            this.registerCaptchaTimer = timer;
        }
    }
    
    clearCaptchaTimer(sessionType) {
        if (sessionType === 'login' && this.loginCaptchaTimer) {
            clearInterval(this.loginCaptchaTimer);
            this.loginCaptchaTimer = null;
        }
        if (sessionType === 'register' && this.registerCaptchaTimer) {
            clearInterval(this.registerCaptchaTimer);
            this.registerCaptchaTimer = null;
        }
    }
    
    resetCaptchaTimer(sessionType) {
        this.clearCaptchaTimer(sessionType);
        
        const timerElement = document.getElementById(`${sessionType}CaptchaTimer`);
        if (timerElement) {
            timerElement.textContent = '02:00';
            timerElement.classList.remove('expiring', 'expired');
        }
        
        const captchaInput = document.getElementById(`${sessionType}CaptchaInput`);
        if (captchaInput) {
            captchaInput.disabled = false;
            captchaInput.placeholder = 'Digite os 4 números';
        }
    }
    
    async refreshCaptcha(sessionType = 'login') {
        this.resetCaptchaTimer(sessionType);
        await this.loadCaptcha(sessionType);
    }
    
    showCaptchaError(sessionType = 'login') {
        const captchaImage = document.getElementById(`${sessionType}CaptchaImage`);
        if (captchaImage) {
            captchaImage.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="350" height="125" viewBox="0 0 350 125"%3E%3Crect width="350" height="125" fill="%23e53e3e"/%3E%3Ctext x="175" y="68" font-family="monospace" font-size="16" fill="white" text-anchor="middle"%3E⚠️ ERRO%3C/text%3E%3C/svg%3E';
        }
    }
    
    // ==============================================
    // 🔥 LOGIN - COM REDIRECIONAMENTO CORRETO
    // ==============================================
    
    async handleLogin(e) {
        e.preventDefault();
        
        const email = document.getElementById('loginEmail')?.value;
        const password = document.getElementById('loginPassword')?.value;
        const captchaCode = document.getElementById('loginCaptchaInput')?.value;
        const captchaId = document.getElementById('loginCaptchaId')?.value || this.loginCaptchaId;
        
        if (!email || !password || !captchaCode) {
            if (window.toastr) {
                toastr.error('Por favor, preencha todos os campos.');
            }
            return;
        }
        
        if (captchaCode.length < 4) {
            if (window.toastr) {
                toastr.error('Digite os 4 números da imagem.');
            }
            return;
        }
        
        const submitBtn = document.getElementById('loginBtn');
        const originalText = submitBtn?.innerHTML;
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i> Entrando...';
        }
        
        try {
            console.log('🔄 Enviando requisição de login...');
            
            const response = await fetch(`${this.apiBase}/auth/login`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Captcha-ID': captchaId || ''
                },
                body: JSON.stringify({
                    email: email,
                    password: password,
                    captcha_id: captchaId || this.loginCaptchaId,
                    captcha_code: captchaCode,
                    session_type: 'login'
                })
            });
            
            const data = await response.json();
            
            if (response.ok && (data.success || data.access_token)) {
                console.log('✅ Login bem-sucedido!');
                
                // 1. Salvar tokens
                if (data.access_token) {
                    localStorage.setItem('access_token', data.access_token);
                }
                if (data.refresh_token) {
                    localStorage.setItem('refresh_token', data.refresh_token);
                }
                
                // 2. Atualizar dados
                this.userData = {
                    email: data.user_email || email,
                    name: data.user_name || 'Usuário',
                    workshop_name: data.workshop_name,
                    role: data.role,
                    plan: data.plan,
                    credits: data.credits || 0,
                    is_admin: data.is_admin || false
                };
                
                this.currentUser = this.userData;
                this.isAuthenticated = true;
                
                // 3. Limpar campos
                this.clearCaptchaTimer('login');
                const passwordField = document.getElementById('loginPassword');
                if (passwordField) passwordField.value = '';
                const captchaInput = document.getElementById('loginCaptchaInput');
                if (captchaInput) captchaInput.value = '';
                
                // 4. Mensagem
                if (window.toastr) {
                    toastr.success('Login realizado com sucesso!');
                }
                
                // 5. REDIRECIONAMENTO
                setTimeout(() => {
                    console.log('🔀 Redirecionando para /dashboard...');
                    window.location.href = '/dashboard';
                }, 600);
                
                return true;
                
            } else {
                const errorMsg = data.detail || data.message || 'Erro ao realizar login.';
                if (window.toastr) {
                    toastr.error(errorMsg);
                }
                
                await this.refreshCaptcha('login');
                const captchaInput = document.getElementById('loginCaptchaInput');
                if (captchaInput) {
                    captchaInput.value = '';
                    captchaInput.focus();
                }
                return false;
            }
            
        } catch (error) {
            console.error('❌ Erro na requisição de login:', error);
            if (window.toastr) {
                toastr.error('Erro de comunicação com o servidor.');
            }
            await this.refreshCaptcha('login');
            return false;
            
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalText;
            }
        }
    }
    
    // ==============================================
    // 🔥 REGISTER - CORRIGIDO E FUNCIONANDO
    // ==============================================
    
    async handleRegister(e) {
        e.preventDefault();
        
        // 🔥 PEGAR TODOS OS CAMPOS DO FORMULÁRIO
        const name = document.getElementById('regName')?.value?.trim();
        const email = document.getElementById('regEmail')?.value?.trim();
        const password = document.getElementById('regPassword')?.value;
        const confirmPassword = document.getElementById('regConfirmPassword')?.value;
        const workshopName = document.getElementById('regWorkshop')?.value?.trim();
        const captchaCode = document.getElementById('registerCaptchaInput')?.value?.trim();
        const captchaId = document.getElementById('registerCaptchaId')?.value || this.registerCaptchaId;
        
        console.log('📝 Tentando registrar:', { name, email, workshopName });
        
        // 🔥 VALIDAÇÕES
        if (!name || !email || !password || !workshopName) {
            if (window.toastr) {
                toastr.error('Preencha todos os campos.');
            } else {
                alert('Preencha todos os campos.');
            }
            return;
        }
        
        if (password.length < 6) {
            if (window.toastr) {
                toastr.error('Senha deve ter no mínimo 6 caracteres.');
            } else {
                alert('Senha deve ter no mínimo 6 caracteres.');
            }
            return;
        }
        
        if (password !== confirmPassword) {
            if (window.toastr) {
                toastr.error('As senhas não coincidem.');
            } else {
                alert('As senhas não coincidem.');
            }
            return;
        }
        
        if (!captchaCode || captchaCode.length < 4) {
            if (window.toastr) {
                toastr.error('Digite os 4 números da imagem.');
            } else {
                alert('Digite os 4 números da imagem.');
            }
            return;
        }
        
        if (!captchaId) {
            if (window.toastr) {
                toastr.error('CAPTCHA não carregado. Clique em 🔄');
            } else {
                alert('CAPTCHA não carregado. Clique em 🔄');
            }
            await this.refreshCaptcha('register');
            return;
        }
        
        // 🔥 BLOQUEAR BOTÃO
        const submitBtn = document.getElementById('registerBtn');
        const originalText = submitBtn?.innerHTML;
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i> Criando conta...';
        }
        
        try {
            console.log('🔄 Enviando requisição de registro...');
            
            const requestBody = {
                name: name,
                email: email,
                password: password,
                workshop_name: workshopName,
                captcha_id: captchaId,
                captcha_code: captchaCode,
                session_type: 'register'
            };
            
            console.log('📦 Body:', requestBody);
            
            const response = await fetch(`${this.apiBase}/auth/register`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Captcha-ID': captchaId
                },
                body: JSON.stringify(requestBody)
            });
            
            const data = await response.json();
            console.log('📥 Resposta:', data);
            
            if (!response.ok) {
                const errorMsg = data.detail || data.message || 'Falha no registro';
                if (window.toastr) {
                    toastr.error(errorMsg);
                } else {
                    alert(errorMsg);
                }
                await this.refreshCaptcha('register');
                return false;
            }
            
            if (data.success) {
                if (window.toastr) {
                    toastr.success('✅ Conta criada! Faça login para continuar.');
                } else {
                    alert('✅ Conta criada! Faça login para continuar.');
                }
                
                // 🔥 REDIRECIONAR PARA O LOGIN
                setTimeout(() => {
                    console.log('🔀 Redirecionando para /login...');
                    window.location.href = '/login';
                }, 2000);
                
                return true;
            }
            
            throw new Error(data.message || 'Erro no registro');
            
        } catch (error) {
            console.error('❌ Erro no registro:', error);
            if (window.toastr) {
                toastr.error(error.message);
            } else {
                alert(error.message);
            }
            await this.refreshCaptcha('register');
            return false;
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalText;
            }
        }
    }
    
    // ==============================================
    // LOGOUT
    // ==============================================
    
    async logout() {
        const refreshToken = localStorage.getItem('refresh_token');
        
        if (refreshToken) {
            try {
                await fetch(`${this.apiBase}/auth/logout`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        refresh_token: refreshToken
                    })
                });
            } catch (error) {
                console.error('Logout API error:', error);
            }
        }
        
        this.clearTokens();
        this.isAuthenticated = false;
        this.currentUser = null;
        
        window.location.href = '/login';
    }
    
    clearTokens() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
    }
    
    // ==============================================
    // 🔥 SETUP DOS LISTENERS - CORRIGIDO
    // ==============================================
    
    setupAuthPageListeners() {
        // 🔥 LOGIN FORM
        const loginForm = document.getElementById('loginForm');
        if (loginForm) {
            loginForm.addEventListener('submit', (e) => this.handleLogin(e));
            this.loadCaptcha('login');
            
            const refreshBtn = document.getElementById('refreshLoginCaptcha');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', () => {
                    this.refreshCaptcha('login');
                });
            }
        }
        
        // 🔥 REGISTER FORM - CORRIGIDO
        const registerForm = document.getElementById('registerForm');
        if (registerForm) {
            console.log('📝 Formulário de registro encontrado!');
            registerForm.addEventListener('submit', (e) => this.handleRegister(e));
            
            // Carregar CAPTCHA do registro
            this.loadCaptcha('register');
            
            const refreshBtn = document.getElementById('refreshRegisterCaptcha');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', () => {
                    this.refreshCaptcha('register');
                });
            }
        } else {
            console.warn('⚠️ Formulário de registro não encontrado!');
        }
        
        // 🔥 TAB DE REGISTRO - carregar CAPTCHA quando clicar
        const registerTab = document.querySelector('#register-tab') || 
                           document.querySelector('button[data-bs-target="#register"]') ||
                           document.querySelector('.tab[data-tab="register"]');
        if (registerTab) {
            registerTab.addEventListener('click', () => {
                if (!this.isRegisterCaptchaLoaded) {
                    this.loadCaptcha('register');
                }
            });
        }
        
        // 🔥 PASSWORD TOGGLE
        document.querySelectorAll('.password-toggle').forEach(btn => {
            btn.addEventListener('click', () => {
                const targetId = btn.getAttribute('data-target');
                const field = document.getElementById(targetId);
                if (field) {
                    const icon = btn.querySelector('i');
                    if (field.type === 'password') {
                        field.type = 'text';
                        icon.classList.remove('fa-eye-slash');
                        icon.classList.add('fa-eye');
                    } else {
                        field.type = 'password';
                        icon.classList.remove('fa-eye');
                        icon.classList.add('fa-eye-slash');
                    }
                }
            });
        });
        
        // 🔥 LOGOUT
        const logoutBtn = document.getElementById('logoutBtn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.logout();
            });
        }
    }
    
    // ==============================================
    // TOKEN E AUTENTICAÇÃO
    // ==============================================
    
    async checkToken() {
        const token = localStorage.getItem('access_token');
        
        if (!token) {
            this.isAuthenticated = false;
            this.currentUser = null;
            return false;
        }
        
        try {
            const response = await fetch(`${this.apiBase}/auth/check-token`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            
            const data = await response.json();
            
            if (response.ok && (data.status === 'valid' || data.status === 'refreshed')) {
                this.isAuthenticated = true;
                
                if (data.access_token && data.access_token !== token) {
                    localStorage.setItem('access_token', data.access_token);
                }
                if (data.refresh_token) {
                    localStorage.setItem('refresh_token', data.refresh_token);
                }
                
                this.userData = {
                    email: data.user || data.user_email,
                    name: data.name || data.user_name,
                    is_admin: data.is_admin || false,
                    credits: data.credits || 0,
                    credits_display: data.credits_display || '0'
                };
                
                this.currentUser = this.userData;
                
                return true;
            }
            
            if (response.status === 401 && localStorage.getItem('refresh_token')) {
                const refreshed = await this.refreshToken();
                if (refreshed) {
                    return this.checkToken();
                }
            }
            
            this.clearTokens();
            this.isAuthenticated = false;
            this.currentUser = null;
            return false;
            
        } catch (error) {
            console.error('Token check error:', error);
            this.isAuthenticated = false;
            this.currentUser = null;
            return false;
        }
    }
    
    async refreshToken() {
        if (this._isRefreshing) {
            return this._refreshPromise;
        }
        
        const refreshToken = localStorage.getItem('refresh_token');
        const accessToken = localStorage.getItem('access_token');
        
        if (!refreshToken) {
            return false;
        }
        
        this._isRefreshing = true;
        
        this._refreshPromise = (async () => {
            try {
                const response = await fetch(`${this.apiBase}/auth/refresh`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        refresh_token: refreshToken,
                        old_access_token: accessToken || null
                    })
                });
                
                const data = await response.json();
                
                if (response.ok && data.access_token) {
                    localStorage.setItem('access_token', data.access_token);
                    if (data.refresh_token) {
                        localStorage.setItem('refresh_token', data.refresh_token);
                    }
                    
                    if (data.user_email) {
                        this.userData = {
                            ...this.userData,
                            email: data.user_email,
                            name: data.user_name,
                            workshop_name: data.workshop_name,
                            role: data.role,
                            plan: data.plan,
                            credits: data.credits,
                            is_admin: data.is_admin
                        };
                        this.currentUser = this.userData;
                    }
                    
                    this.isAuthenticated = true;
                    
                    console.log('✅ Token refresh realizado com sucesso');
                    return true;
                }
                
                console.warn('❌ Refresh token falhou:', data.message || 'Resposta inválida');
                return false;
                
            } catch (error) {
                console.error('❌ Token refresh error:', error);
                return false;
            } finally {
                this._isRefreshing = false;
                this._refreshPromise = null;
            }
        })();
        
        return this._refreshPromise;
    }
    
    // ==============================================
    // CRÉDITOS
    // ==============================================
    
    async loadUserCredits() {
        if (!this.isAuthenticated) return false;
        
        try {
            const response = await this.fetchWithAuth(`${this.apiBase}/payments/balance`);
            
            if (response && response.ok) {
                const data = await response.json();
                
                if (data.success) {
                    if (this.userData) {
                        this.userData.credits = data.credits;
                        this.userData.credits_display = data.credits_display || String(data.credits);
                    }
                    
                    this.updateCreditsDisplay();
                    return true;
                }
            }
            
            return false;
            
        } catch (error) {
            console.error('Erro ao carregar créditos:', error);
            return false;
        }
    }
    
    getCredits() {
        return this.userData?.credits || 0;
    }
    
    getCreditsDisplay() {
        if (this.isAdmin()) return '∞';
        if (this.isPremium()) {
            const credits = this.getCredits();
            return `${credits}/3`;
        }
        return String(this.getCredits());
    }
    
    updateCreditsDisplay() {
        const creditsElements = document.querySelectorAll('.credits-display, .user-credits, #creditsDisplay, #creditsCount, #uploadCredits');
        const displayValue = this.getCreditsDisplay();
        
        creditsElements.forEach(el => {
            if (el) el.textContent = displayValue;
        });
    }
    
    isAdmin() {
        return this.userData?.is_admin === true;
    }
    
    isPremium() {
        return this.userData?.plan === 'premium_mensal' || this.userData?.plan === 'PREMIUM_MENSAL';
    }
    
    getCurrentUser() {
        return this.userData || {};
    }
    
    // ==============================================
    // FETCH WITH AUTH
    // ==============================================
    
    async fetchWithAuth(url, options = {}) {
        const token = localStorage.getItem('access_token');
        
        if (!token) {
            return null;
        }
        
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers
        };
        
        headers['Authorization'] = `Bearer ${token}`;
        
        try {
            let response = await fetch(url, { ...options, headers });
            
            if (response.status === 401) {
                const refreshed = await this.refreshToken();
                
                if (refreshed) {
                    const newToken = localStorage.getItem('access_token');
                    headers['Authorization'] = `Bearer ${newToken}`;
                    response = await fetch(url, { ...options, headers });
                } else {
                    this.clearTokens();
                    this.isAuthenticated = false;
                    this.currentUser = null;
                    
                    if (!window.location.pathname.includes('/login')) {
                        window.location.href = '/login';
                    }
                    return null;
                }
            }
            
            return response;
            
        } catch (error) {
            console.error('Erro na requisição:', error);
            return null;
        }
    }
    
    // ==============================================
    // UI
    // ==============================================
    
    showError(message) {
        const errorDiv = document.getElementById('authMessage');
        if (errorDiv) {
            errorDiv.innerHTML = `
                <div class="alert alert-danger alert-dismissible fade show" role="alert">
                    <i class="fas fa-exclamation-circle me-2"></i>${message}
                    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                </div>
            `;
            setTimeout(() => {
                const alert = errorDiv.querySelector('.alert');
                if (alert) alert.remove();
            }, 5000);
        }
    }
    
    updateUI() {
        const authRequiredElements = document.querySelectorAll('.auth-required');
        const guestElements = document.querySelectorAll('.guest-only');
        
        if (this.isAuthenticated) {
            authRequiredElements.forEach(el => el.classList.remove('d-none'));
            guestElements.forEach(el => el.classList.add('d-none'));
            
            const userNameElements = document.querySelectorAll('.user-name');
            userNameElements.forEach(el => {
                el.textContent = this.userData?.name || 'Usuário';
            });
            
            this.updateCreditsDisplay();
        } else {
            authRequiredElements.forEach(el => el.classList.add('d-none'));
            guestElements.forEach(el => el.classList.remove('d-none'));
        }
    }
    
    // ==============================================
    // INICIALIZAÇÃO
    // ==============================================
    
    async init() {
        console.log('🚀 Inicializando Auth...');
        
        this._initializing = true;
        this.initialized = true;
        
        await this.checkToken();
        
        this.setupAuthPageListeners();
        
        this._initializing = false;
        
        this.updateUI();
        
        console.log(`✅ Auth inicializado. Autenticado: ${this.isAuthenticated}`);
    }
}

// ==============================================
// INSTÂNCIA GLOBAL
// ==============================================

window.appAuth = new Auth();

console.log('✅ Auth carregado. Use window.appAuth para acessar.');
console.log('   Ex: window.appAuth.isAuthenticated');