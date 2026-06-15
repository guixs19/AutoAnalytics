// frontend/js/auth.js - VERSÃO PRODUÇÃO

class Auth {
    constructor() {
        // 🔥 API BASE DINÂMICA PARA PRODUÇÃO
        this.apiBase = '/api';
        
        this.currentUser = null;
        this.isAuthenticated = false;
        this.userData = null;
        this.loginCaptchaId = null;
        this.registerCaptchaId = null;
        this.loginCaptchaTimer = null;
        this.registerCaptchaTimer = null;
        this.initialized = false;
        this.isRegisterCaptchaLoaded = false;
        
        this.init();
    }
    
    async init() {
        await this.checkToken();
        this.setupAuthPageListeners();
        this.updateUI();
        this.initialized = true;
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
    
    showCaptchaError(sessionType = 'login') {
        const captchaImage = document.getElementById(`${sessionType}CaptchaImage`);
        if (captchaImage) {
            captchaImage.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="280" height="100" viewBox="0 0 280 100"%3E%3Crect width="280" height="100" fill="%23e53e3e"/%3E%3Ctext x="140" y="55" font-family="monospace" font-size="14" fill="white" text-anchor="middle"%3E⚠️ ERRO%3C/text%3E%3C/svg%3E';
        }
    }
    
    startCaptchaTimer(sessionType) {
        if (sessionType === 'login' && this.loginCaptchaTimer) {
            clearInterval(this.loginCaptchaTimer);
        }
        if (sessionType === 'register' && this.registerCaptchaTimer) {
            clearInterval(this.registerCaptchaTimer);
        }
        
        const expirySeconds = 120;
        let remaining = expirySeconds;
        
        const timerElement = document.getElementById(`${sessionType}CaptchaTimer`);
        
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
                    captchaInput.placeholder = 'Expirado';
                }
            }
        }, 1000);
        
        if (sessionType === 'login') {
            this.loginCaptchaTimer = timer;
        } else {
            this.registerCaptchaTimer = timer;
        }
    }
    
    async refreshCaptcha(sessionType = 'login') {
        if (sessionType === 'login' && this.loginCaptchaTimer) {
            clearInterval(this.loginCaptchaTimer);
        }
        if (sessionType === 'register' && this.registerCaptchaTimer) {
            clearInterval(this.registerCaptchaTimer);
        }
        
        await this.loadCaptcha(sessionType);
    }
    
    // ==============================================
    // LOGIN
    // ==============================================
    
    async login(email, password, captchaText, captchaId) {
        if (!captchaId) {
            const hiddenField = document.getElementById('loginCaptchaId');
            if (hiddenField && hiddenField.value) {
                captchaId = hiddenField.value;
            }
        }
        
        if (!email || !password) {
            this.showError('Preencha email e senha');
            return false;
        }
        
        if (!captchaText) {
            this.showError('Digite os números da imagem');
            return false;
        }
        
        if (!captchaId) {
            this.showError('CAPTCHA não carregado');
            await this.refreshCaptcha('login');
            return false;
        }
        
        const submitBtn = document.getElementById('loginBtn');
        const originalText = submitBtn?.innerHTML;
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = 'Entrando...';
        }
        
        try {
            const response = await fetch(`${this.apiBase}/auth/login`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Captcha-ID': captchaId
                },
                body: JSON.stringify({
                    email: email,
                    password: password,
                    captcha_id: captchaId,
                    captcha_text: captchaText
                })
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                const errorMsg = data.detail || data.message || 'Falha no login';
                this.showError(errorMsg);
                await this.refreshCaptcha('login');
                return false;
            }
            
            if (data.success || data.access_token) {
                if (data.access_token) {
                    localStorage.setItem('access_token', data.access_token);
                }
                if (data.refresh_token) {
                    localStorage.setItem('refresh_token', data.refresh_token);
                }
                
                this.isAuthenticated = true;
                this.userData = {
                    email: data.user_email,
                    name: data.user_name,
                    workshop_name: data.workshop_name,
                    role: data.role,
                    plan: data.plan,
                    credits: data.credits,
                    is_admin: data.is_admin,
                    admin_level: data.admin_level
                };
                
                this.currentUser = this.userData;
                
                this.showSuccess('Login realizado! Redirecionando...');
                
                setTimeout(() => {
                    window.location.href = '/dashboard';
                }, 1000);
                
                return true;
            }
            
            throw new Error(data.message || 'Erro no login');
            
        } catch (error) {
            console.error('Login error:', error);
            this.showError(error.message);
            return false;
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalText;
            }
        }
    }
    
    // ==============================================
    // REGISTRO
    // ==============================================
    
    async register(name, email, password, workshopName, captchaText, captchaId) {
        if (!captchaId || captchaId === '') {
            const hiddenField = document.getElementById('registerCaptchaId');
            if (hiddenField && hiddenField.value && hiddenField.value !== '') {
                captchaId = hiddenField.value;
            }
        }
        
        if (!name || !email || !password || !workshopName) {
            this.showError('Preencha todos os campos');
            return false;
        }
        
        if (password.length < 6) {
            this.showError('Senha deve ter no mínimo 6 caracteres');
            return false;
        }
        
        if (!captchaText) {
            this.showError('Digite os números da imagem');
            return false;
        }
        
        if (!captchaId) {
            this.showError('CAPTCHA não carregado. Clique no ícone de recarregar.');
            await this.refreshCaptcha('register');
            return false;
        }
        
        const submitBtn = document.getElementById('registerBtn');
        const originalText = submitBtn?.innerHTML;
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = 'Criando conta...';
        }
        
        try {
            const requestBody = {
                name: name,
                email: email,
                password: password,
                workshop_name: workshopName,
                captcha_text: captchaText,
                captcha_id: captchaId
            };
            
            const response = await fetch(`${this.apiBase}/auth/register`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Captcha-ID': captchaId
                },
                body: JSON.stringify(requestBody)
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                const errorMsg = data.detail || data.message || 'Falha no registro';
                this.showError(errorMsg);
                await this.refreshCaptcha('register');
                return false;
            }
            
            if (data.success) {
                this.showSuccess('Conta criada! Faça login para continuar.');
                
                setTimeout(() => {
                    window.location.href = '/login';
                }, 2000);
                
                return true;
            }
            
            throw new Error(data.message || 'Erro no registro');
            
        } catch (error) {
            console.error('Registration error:', error);
            this.showError(error.message);
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
    // SETUP DOS LISTENERS (COM LAZY LOADING)
    // ==============================================
    
    setupAuthPageListeners() {
        const loginForm = document.getElementById('loginForm');
        if (loginForm) {
            loginForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                e.stopPropagation();
                
                const email = document.getElementById('loginEmail')?.value;
                const password = document.getElementById('loginPassword')?.value;
                const captchaText = document.getElementById('loginCaptchaInput')?.value;
                const captchaId = document.getElementById('loginCaptchaId')?.value;
                
                await this.login(email, password, captchaText, captchaId);
            });
            
            this.loadCaptcha('login');
            
            const refreshBtn = document.getElementById('refreshLoginCaptcha');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', () => this.refreshCaptcha('login'));
            }
        }
        
        const registerForm = document.getElementById('registerForm');
        if (registerForm) {
            registerForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                e.stopPropagation();
                
                const name = document.getElementById('regName')?.value;
                const email = document.getElementById('regEmail')?.value;
                const password = document.getElementById('regPassword')?.value;
                const workshopName = document.getElementById('regWorkshop')?.value;
                const captchaText = document.getElementById('registerCaptchaInput')?.value;
                const captchaId = document.getElementById('registerCaptchaId')?.value;
                
                await this.register(name, email, password, workshopName, captchaText, captchaId);
            });
            
            const refreshBtn = document.getElementById('refreshRegisterCaptcha');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', () => this.refreshCaptcha('register'));
            }
        }
        
        const registerTab = document.querySelector('#register-tab') || document.querySelector('button[data-bs-target="#register"]');
        if (registerTab) {
            registerTab.addEventListener('click', () => {
                if (!this.isRegisterCaptchaLoaded) {
                    this.loadCaptcha('register');
                }
            });
        }
        
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
                    email: data.user,
                    name: data.name,
                    is_admin: data.is_admin,
                    admin_level: data.admin_level,
                    credits: data.credits,
                    credits_display: data.credits_display
                };
                
                this.currentUser = this.userData;
                
                return true;
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
        const refreshToken = localStorage.getItem('refresh_token');
        
        if (!refreshToken) {
            return false;
        }
        
        try {
            const response = await fetch(`${this.apiBase}/auth/refresh`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    refresh_token: refreshToken
                })
            });
            
            const data = await response.json();
            
            if (response.ok && data.access_token) {
                localStorage.setItem('access_token', data.access_token);
                if (data.refresh_token) {
                    localStorage.setItem('refresh_token', data.refresh_token);
                }
                return true;
            }
            
            return false;
            
        } catch (error) {
            console.error('Token refresh error:', error);
            return false;
        }
    }
    
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
        
        document.dispatchEvent(new CustomEvent('userLoggedOut'));
        
        window.location.href = '/login';
    }
    
    clearTokens() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
    }
    
    async loadUserCredits() {
        if (!this.isAuthenticated) return false;
        
        try {
            const response = await this.fetchWithAuth(`${this.apiBase}/payments/balance`);
            
            if (response && response.ok) {
                const data = await response.json();
                
                if (data.success) {
                    if (this.userData) {
                        this.userData.credits = data.credits;
                        this.userData.credits_display = data.plan?.is_premium ? '∞' : String(data.credits);
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
        if (this.isPremium()) return '∞';
        return String(this.getCredits());
    }
    
    async checkCreditsForAnalysis() {
        if (this.isAdmin()) return true;
        
        const credits = this.getCredits();
        
        if (credits <= 0) {
            this.showCreditsModal();
            return false;
        }
        
        return true;
    }
    
    showCreditsModal() {
        if (window.toastr) {
            toastr.warning('Créditos insuficientes! Adquira o plano premium.', 'Atenção');
        }
        
        setTimeout(() => {
            if (window.location.pathname !== '/planos') {
                window.location.href = '/planos';
            }
        }, 2000);
    }
    
    updateCreditsDisplay() {
        const creditsElements = document.querySelectorAll('.credits-display, .user-credits');
        const displayValue = this.getCreditsDisplay();
        
        creditsElements.forEach(el => {
            el.textContent = displayValue;
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
    
    isAuthenticated() {
        return this.isAuthenticated;
    }
    
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
                    return null;
                }
            }
            
            return response;
            
        } catch (error) {
            console.error('Erro na requisição:', error);
            return null;
        }
    }
    
    showError(message) {
        const errorDiv = document.getElementById('authMessage');
        if (errorDiv) {
            errorDiv.innerHTML = `<div class="alert alert-danger alert-dismissible fade show" role="alert">
                <i class="fas fa-exclamation-circle me-2"></i>${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>`;
            setTimeout(() => {
                const alert = errorDiv.querySelector('.alert');
                if (alert) alert.remove();
            }, 5000);
        }
        
        if (window.toastr) {
            toastr.error(message);
        }
    }
    
    showSuccess(message) {
        if (window.toastr) {
            toastr.success(message);
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
}

// Instância global
window.appAuth = new Auth();

window.getAuth = () => window.appAuth;
window.refreshCaptcha = (type) => window.appAuth?.refreshCaptcha(type);