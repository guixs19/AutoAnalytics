// frontend/js/auth.js - VERSÃO SEM CAPTCHA
/**
 * Módulo de Autenticação - AutoAnalytics
 * FLUXO: login → dashboard | register → login
 * 🔥 Token expira em 15 minutos (conforme security.py)
 * 🔥 Sincronizado com auth_routes.py e auth.py
 * ✅ CAPTCHA REMOVIDO COMPLETAMENTE
 */

class Auth {
    constructor() {
        this.apiBase = '/api';
        
        this.currentUser = null;
        this._isAuthenticated = false;
        this.userData = null;
        this.initialized = false;
        
        this._isRefreshing = false;
        this._refreshPromise = null;
        this._uiUpdateTimeout = null;
        this._initializing = false;
        
        // 🔥 TIMERS PARA LIMPEZA AUTOMÁTICA (15 MINUTOS - conforme security.py)
        this._tokenExpiryTimer = null;
        this._tokenCheckInterval = null;
        this.pendingRequests = [];
        
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
    // 🔥 LOGIN - POST /api/auth/login (SEM CAPTCHA)
    // ==============================================
    
    async handleLogin(e) {
        e.preventDefault();
        
        const emailInput = document.getElementById('loginEmail');
        const passwordInput = document.getElementById('loginPassword');
        
        const email = emailInput?.value?.trim();
        const password = passwordInput?.value;
        
        console.log('🔍 DETALHES DO LOGIN:');
        console.log('  📧 Email:', email);
        
        if (!email || !password) {
            if (window.toastr) {
                toastr.error('Por favor, preencha todos os campos.');
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
            
            // 🔥 PAYLOAD SEM CAPTCHA
            const payload = {
                email: email,
                password: password,
                session_type: 'login'
            };
            
            console.log('📦 PAYLOAD ENVIADO:', JSON.stringify(payload, null, 2));
            
            const response = await fetch(`${this.apiBase}/auth/login`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });
            
            const data = await response.json();
            console.log('📥 RESPOSTA DO SERVIDOR:', data);
            
            if (response.ok && (data.success || data.access_token)) {
                console.log('✅ Login bem-sucedido!');
                
                if (data.access_token) {
                    localStorage.setItem('access_token', data.access_token);
                }
                if (data.refresh_token) {
                    localStorage.setItem('refresh_token', data.refresh_token);
                }
                
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
                
                if (passwordInput) passwordInput.value = '';
                
                // 🔥 INICIA MONITORAMENTO DO TOKEN (15 MINUTOS)
                this.startTokenMonitoring();
                
                if (window.toastr) {
                    toastr.success('Login realizado com sucesso!');
                }
                
                setTimeout(() => {
                    console.log('🔀 Redirecionando para /dashboard...');
                    window.location.href = '/dashboard';
                }, 600);
                
                return true;
                
            } else {
                let errorMsg = data.detail || data.message || 'Erro ao realizar login.';
                
                if (response.status === 422) {
                    console.error('❌ Erro 422 - Validação falhou:', data);
                    if (data.detail && Array.isArray(data.detail)) {
                        errorMsg = data.detail.map(err => 
                            `${err.loc?.join('.') || 'campo'}: ${err.msg}`
                        ).join('; ');
                    } else if (typeof data.detail === 'string') {
                        errorMsg = data.detail;
                    }
                }
                
                if (window.toastr) {
                    toastr.error(errorMsg);
                }
                return false;
            }
            
        } catch (error) {
            console.error('❌ Erro na requisição de login:', error);
            if (window.toastr) {
                toastr.error('Erro de comunicação com o servidor.');
            }
            return false;
            
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalText;
            }
        }
    }
    
    // ==============================================
    // 🔥 REGISTER - POST /api/auth/register (SEM CAPTCHA)
    // ==============================================
    
    async handleRegister(e) {
        e.preventDefault();
        
        const nameInput = document.getElementById('registerName');
        const emailInput = document.getElementById('registerEmail');
        const passwordInput = document.getElementById('registerPassword');
        const confirmPasswordInput = document.getElementById('registerConfirmPassword');
        const workshopInput = document.getElementById('registerWorkshop');
        const phoneInput = document.getElementById('registerPhone');
        
        const name = nameInput?.value?.trim();
        const email = emailInput?.value?.trim();
        const password = passwordInput?.value;
        const confirmPassword = confirmPasswordInput?.value;
        const workshopName = workshopInput?.value?.trim();
        const phone = phoneInput?.value?.trim();
        
        console.log('📝 Tentando registrar:', { name, email, workshopName, phone });
        
        // ==============================================
        // 🔥 VALIDAÇÕES
        // ==============================================
        
        // 1. Campos obrigatórios
        if (!name || !email || !password || !workshopName) {
            if (window.toastr) {
                toastr.error('Preencha todos os campos obrigatórios.');
            }
            return;
        }
        
        // 2. Validação de telefone (opcional)
        if (phone) {
            const phoneClean = phone.replace(/\D/g, '');
            
            if (phoneClean.length > 0 && phoneClean.length < 10) {
                if (window.toastr) {
                    toastr.warning('Telefone deve ter pelo menos 10 dígitos (incluindo DDD).');
                }
                return;
            }
            
            if (phoneClean.length > 11) {
                if (window.toastr) {
                    toastr.warning('Telefone deve ter no máximo 11 dígitos.');
                }
                return;
            }
        }
        
        // 3. Senha (mínimo 6 caracteres)
        if (password.length < 6) {
            if (window.toastr) {
                toastr.error('Senha deve ter no mínimo 6 caracteres.');
            }
            return;
        }
        
        // 4. Confirmação de senha
        if (password !== confirmPassword) {
            if (window.toastr) {
                toastr.error('As senhas não coincidem.');
            }
            return;
        }
        
        // ==============================================
        // 🔥 ENVIAR REGISTRO - SEM CAPTCHA
        // ==============================================
        
        const submitBtn = document.getElementById('registerBtn');
        const originalText = submitBtn?.innerHTML;
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i> Criando conta...';
        }
        
        try {
            console.log('🔄 Enviando requisição de registro...');
            
            // 🔥 PAYLOAD SEM CAPTCHA
            const requestBody = {
                name: name,
                email: email,
                password: password,
                workshop_name: workshopName,
                phone: phone || null,
                session_type: 'register'
            };
            
            console.log('📦 Body:', requestBody);
            
            const response = await fetch(`${this.apiBase}/auth/register`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestBody)
            });
            
            const data = await response.json();
            console.log('📥 Resposta:', data);
            
            if (!response.ok) {
                let errorMsg = data.detail || data.message || 'Falha no registro';
                
                if (response.status === 422) {
                    console.error('❌ Erro 422 - Validação falhou:', data);
                    if (data.detail && Array.isArray(data.detail)) {
                        errorMsg = data.detail.map(err => 
                            `${err.loc?.join('.') || 'campo'}: ${err.msg}`
                        ).join('; ');
                    } else if (typeof data.detail === 'string') {
                        errorMsg = data.detail;
                    }
                }
                
                if (window.toastr) {
                    toastr.error(errorMsg);
                }
                return false;
            }
            
            if (data.success) {
                if (window.toastr) {
                    toastr.success('✅ Conta criada! Faça login para continuar.');
                }
                
                // 🔥 Limpa o formulário
                if (nameInput) nameInput.value = '';
                if (emailInput) emailInput.value = '';
                if (passwordInput) passwordInput.value = '';
                if (confirmPasswordInput) confirmPasswordInput.value = '';
                if (workshopInput) workshopInput.value = '';
                if (phoneInput) phoneInput.value = '';
                
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
                toastr.error(error.message || 'Erro ao criar conta. Tente novamente.');
            }
            return false;
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalText;
            }
        }
    }
    
    // ==============================================
    // 🔥 LOGOUT - POST /api/auth/logout
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
        
        this.stopTokenMonitoring();
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
    // 🔥 MONITORAMENTO DE TOKEN (15 MINUTOS)
    // ==============================================
    
    startTokenMonitoring() {
        if (this._tokenExpiryTimer) {
            clearTimeout(this._tokenExpiryTimer);
            this._tokenExpiryTimer = null;
        }
        if (this._tokenCheckInterval) {
            clearInterval(this._tokenCheckInterval);
            this._tokenCheckInterval = null;
        }
        
        const token = localStorage.getItem('access_token');
        if (!token) {
            console.log('❌ Sem token para monitorar');
            return;
        }
        
        console.log('⏰ Iniciando monitoramento de token (15min)');
        
        this._tokenCheckInterval = setInterval(() => {
            this.checkTokenHealth();
        }, 60000);
        
        this._tokenExpiryTimer = setTimeout(() => {
            console.log('⏰ Token expirado (15min) - limpando localStorage');
            this.clearTokens();
            this.isAuthenticated = false;
            this.currentUser = null;
            
            if (window.toastr) {
                toastr.warning('⏰ Sessão expirada. Faça login novamente.');
            }
            
            setTimeout(() => {
                window.location.href = '/login';
            }, 1500);
        }, 15 * 60 * 1000);
    }
    
    stopTokenMonitoring() {
        if (this._tokenExpiryTimer) {
            clearTimeout(this._tokenExpiryTimer);
            this._tokenExpiryTimer = null;
        }
        if (this._tokenCheckInterval) {
            clearInterval(this._tokenCheckInterval);
            this._tokenCheckInterval = null;
        }
    }
    
    async checkTokenHealth() {
        try {
            const token = localStorage.getItem('access_token');
            if (!token) {
                this.handleTokenExpired();
                return;
            }
            
            const response = await fetch(`${this.apiBase}/auth/check-token`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            
            if (response.status === 401) {
                console.log('🔄 Token expirou, tentando refresh...');
                const refreshed = await this.refreshTokenSafely();
                if (!refreshed) {
                    this.handleTokenExpired();
                }
            }
        } catch (error) {
            console.warn('Erro ao verificar token:', error);
        }
    }
    
    // ==============================================
    // 🔥 REFRESH TOKEN - POST /api/auth/refresh
    // ==============================================
    
    async refreshTokenSafely() {
        if (this._isRefreshing) {
            return new Promise((resolve) => {
                this.pendingRequests.push(resolve);
            });
        }
        
        this._isRefreshing = true;
        
        try {
            const refreshToken = localStorage.getItem('refresh_token');
            if (!refreshToken) return false;
            
            const response = await fetch(`${this.apiBase}/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    refresh_token: refreshToken,
                    old_access_token: localStorage.getItem('access_token') 
                })
            });
            
            if (response.ok) {
                const data = await response.json();
                localStorage.setItem('access_token', data.access_token);
                if (data.refresh_token) {
                    localStorage.setItem('refresh_token', data.refresh_token);
                }
                
                this.stopTokenMonitoring();
                this.startTokenMonitoring();
                
                console.log('✅ Token refresh realizado com sucesso');
                return true;
            }
            return false;
        } catch (error) {
            return false;
        } finally {
            this._isRefreshing = false;
        }
    }
    
    handleTokenExpired() {
        console.log('⏰ Token expirado - limpando sessão');
        this.stopTokenMonitoring();
        this.clearTokens();
        this.isAuthenticated = false;
        this.currentUser = null;
        
        if (window.toastr) {
            toastr.warning('⏰ Sessão expirada. Faça login novamente.');
        }
        
        setTimeout(() => {
            window.location.href = '/login';
        }, 1500);
    }
    
    // ==============================================
    // SETUP DOS LISTENERS
    // ==============================================
    
    setupAuthPageListeners() {
        console.log('🔧 Configurando listeners de autenticação...');
        
        // LOGIN FORM
        const loginForm = document.getElementById('loginForm');
        if (loginForm) {
            console.log('✅ Formulário de login encontrado!');
            loginForm.addEventListener('submit', (e) => this.handleLogin(e));
        } else {
            console.warn('⚠️ Formulário de login NÃO encontrado!');
        }
        
        // REGISTER FORM
        const registerForm = document.getElementById('registerForm');
        if (registerForm) {
            console.log('✅ Formulário de registro encontrado!');
            registerForm.addEventListener('submit', (e) => this.handleRegister(e));
        } else {
            console.warn('⚠️ Formulário de registro NÃO encontrado!');
        }
        
        // PASSWORD TOGGLE
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
        
        // LOGOUT
        const logoutBtn = document.getElementById('logoutBtn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.logout();
            });
        }
        
        console.log('✅ Listeners configurados!');
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
                
                this.startTokenMonitoring();
                
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
                    this.stopTokenMonitoring();
                    this.startTokenMonitoring();
                    
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
    // UPDATE UI
    // ==============================================
    
    updateUI() {
        const authRequiredElements = document.querySelectorAll('.auth-required');
        const guestElements = document.querySelectorAll('.guest-only');
        
        if (authRequiredElements.length === 0 && guestElements.length === 0) {
            return;
        }
        
        console.log('🔄 Atualizando UI - Autenticado:', this.isAuthenticated);
        
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
        console.log(`📝 Formulários configurados: login=${!!document.getElementById('loginForm')}, register=${!!document.getElementById('registerForm')}`);
    }
}

// ==============================================
// INSTÂNCIA GLOBAL
// ==============================================

window.appAuth = new Auth();

console.log('✅ Auth carregado. Use window.appAuth para acessar.');
console.log('   Ex: window.appAuth.isAuthenticated');
console.log('   ✅ CAPTCHA REMOVIDO COMPLETAMENTE!');