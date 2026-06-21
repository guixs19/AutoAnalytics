// frontend/js/auth.js - VERSÃO CORRIGIDA (SINCRONIZADA COM BACKEND)
/**
 * Módulo de Autenticação - AutoAnalytics
 * FLUXO: login → dashboard | register → login
 * 🔥 Token expira em 15 minutos (conforme security.py)
 * 🔥 Sincronizado com auth_routes.py, auth.py e security.py
 * ✅ CAPTCHA REMOVIDO COMPLETAMENTE
 * 🔥 CORREÇÕES:
 *   - checkToken() processa corretamente status 'refreshed'
 *   - refreshToken() envia old_access_token
 *   - fetchWithAuth() atualiza token após refresh
 *   - Constantes sincronizadas com backend
 *   - getCreditsDisplay() usa MAX_CREDITS_BALANCE
 */

// ==============================================
// 🔥 CONSTANTES SINCRONIZADAS COM BACKEND
// ==============================================
const MAX_CREDITS_BALANCE = 3;
const TOKEN_EXPIRY_MINUTES = 15; // security.py
const REFRESH_TOKEN_EXPIRY_DAYS = 7;

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
        
        // 🔥 TIMERS PARA LIMPEZA AUTOMÁTICA
        this._tokenExpiryTimer = null;
        this._tokenCheckInterval = null;
        this.pendingRequests = [];
        this._lastTokenCheck = 0;
        
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
            const payload = {
                email: email,
                password: password,
                session_type: 'login'
            };
            
            const response = await fetch(`${this.apiBase}/auth/login`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });
            
            const data = await response.json();
            
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
                    is_admin: data.is_admin || false,
                    credits_display: data.credits_display || String(data.credits || 0)
                };
                
                this.currentUser = this.userData;
                this.isAuthenticated = true;
                
                if (passwordInput) passwordInput.value = '';
                
                // 🔥 INICIA MONITORAMENTO DO TOKEN
                this.startTokenMonitoring();
                
                if (window.toastr) {
                    toastr.success('Login realizado com sucesso!');
                }
                
                setTimeout(() => {
                    window.location.href = '/dashboard';
                }, 600);
                
                return true;
                
            } else {
                let errorMsg = data.detail || data.message || 'Erro ao realizar login.';
                
                if (response.status === 422) {
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
        
        // ==============================================
        // 🔥 VALIDAÇÕES
        // ==============================================
        
        if (!name || !email || !password || !workshopName) {
            if (window.toastr) {
                toastr.error('Preencha todos os campos obrigatórios.');
            }
            return;
        }
        
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
        
        if (password.length < 6) {
            if (window.toastr) {
                toastr.error('Senha deve ter no mínimo 6 caracteres.');
            }
            return;
        }
        
        if (password !== confirmPassword) {
            if (window.toastr) {
                toastr.error('As senhas não coincidem.');
            }
            return;
        }
        
        const submitBtn = document.getElementById('registerBtn');
        const originalText = submitBtn?.innerHTML;
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i> Criando conta...';
        }
        
        try {
            const requestBody = {
                name: name,
                email: email,
                password: password,
                workshop_name: workshopName,
                phone: phone || null,
                session_type: 'register'
            };
            
            const response = await fetch(`${this.apiBase}/auth/register`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestBody)
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                let errorMsg = data.detail || data.message || 'Falha no registro';
                
                if (response.status === 422) {
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
                
                if (nameInput) nameInput.value = '';
                if (emailInput) emailInput.value = '';
                if (passwordInput) passwordInput.value = '';
                if (confirmPasswordInput) confirmPasswordInput.value = '';
                if (workshopInput) workshopInput.value = '';
                if (phoneInput) phoneInput.value = '';
                
                setTimeout(() => {
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
        const accessToken = localStorage.getItem('access_token');
        
        if (refreshToken) {
            try {
                // 🔥 CORRIGIDO: Envia ambos os tokens para blacklist
                await fetch(`${this.apiBase}/auth/logout`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': accessToken ? `Bearer ${accessToken}` : ''
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
        this.userData = null;
        
        // 🔥 Dispara evento de logout
        window.dispatchEvent(new CustomEvent('authLogout'));
        
        window.location.href = '/login';
    }
    
    clearTokens() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
    }
    
    // ==============================================
    // 🔥 MONITORAMENTO DE TOKEN (SINCRONIZADO COM BACKEND)
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
        
        // 🔥 Calcular tempo restante do token baseado no payload
        let remainingTime = TOKEN_EXPIRY_MINUTES * 60 * 1000;
        try {
            const payload = this._parseJwt(token);
            if (payload && payload.exp) {
                const now = Math.floor(Date.now() / 1000);
                const exp = payload.exp;
                if (exp > now) {
                    remainingTime = (exp - now) * 1000;
                    console.log(`⏰ Token expira em ${Math.floor(remainingTime / 60000)} minutos`);
                }
            }
        } catch (e) {
            console.warn('Não foi possível decodificar token para expiração');
        }
        
        // 🔥 Verificação a cada 30 segundos
        this._tokenCheckInterval = setInterval(() => {
            this.checkTokenHealth();
        }, 30000);
        
        // 🔥 Expiração com base no tempo real do token
        this._tokenExpiryTimer = setTimeout(() => {
            console.log('⏰ Token expirado - limpando localStorage');
            this.clearTokens();
            this.isAuthenticated = false;
            this.currentUser = null;
            this.userData = null;
            
            if (window.toastr) {
                toastr.warning('⏰ Sessão expirada. Faça login novamente.');
            }
            
            setTimeout(() => {
                window.location.href = '/login';
            }, 1500);
        }, remainingTime + 5000); // +5 segundos de margem
        
        console.log(`⏰ Monitoramento iniciado (${Math.floor(remainingTime / 60000)}min)`);
    }
    
    _parseJwt(token) {
        try {
            const base64Url = token.split('.')[1];
            const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
            const jsonPayload = decodeURIComponent(atob(base64).split('').map(c => {
                return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
            }).join(''));
            return JSON.parse(jsonPayload);
        } catch (e) {
            return null;
        }
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
        // Evita verificações muito frequentes
        const now = Date.now();
        if (now - this._lastTokenCheck < 5000) return;
        this._lastTokenCheck = now;
        
        try {
            const token = localStorage.getItem('access_token');
            if (!token) {
                this.handleTokenExpired();
                return;
            }
            
            const response = await fetch(`${this.apiBase}/auth/check-token`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            
            const data = await response.json();
            
            // 🔥 CORRIGIDO: Processa status 'refreshed'
            if (response.status === 401) {
                console.log('🔄 Token expirou, tentando refresh...');
                const refreshed = await this.refreshToken();
                if (!refreshed) {
                    this.handleTokenExpired();
                }
            } else if (response.ok) {
                // 🔥 CORRIGIDO: Atualiza token se foi renovado
                if (data.status === 'refreshed' && data.access_token) {
                    console.log('🔄 Token renovado via check-token');
                    localStorage.setItem('access_token', data.access_token);
                    if (data.refresh_token) {
                        localStorage.setItem('refresh_token', data.refresh_token);
                    }
                    
                    // Reinicia monitoramento com novo token
                    this.stopTokenMonitoring();
                    this.startTokenMonitoring();
                }
                
                // Atualiza dados do usuário
                if (data.user) {
                    this.userData = {
                        ...this.userData,
                        email: data.user,
                        name: data.name,
                        is_admin: data.is_admin || false,
                        credits: data.credits || 0,
                        credits_display: data.credits_display || String(data.credits || 0)
                    };
                    this.currentUser = this.userData;
                    this.updateCreditsDisplay();
                }
            }
        } catch (error) {
            console.warn('Erro ao verificar token:', error);
        }
    }
    
    // ==============================================
    // 🔥 REFRESH TOKEN - POST /api/auth/refresh (CORRIGIDO)
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
            const accessToken = localStorage.getItem('access_token');
            
            if (!refreshToken) return false;
            
            // 🔥 CORRIGIDO: Envia old_access_token
            const response = await fetch(`${this.apiBase}/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    refresh_token: refreshToken,
                    old_access_token: accessToken || null
                })
            });
            
            if (response.ok) {
                const data = await response.json();
                localStorage.setItem('access_token', data.access_token);
                if (data.refresh_token) {
                    localStorage.setItem('refresh_token', data.refresh_token);
                }
                
                // Atualiza dados do usuário
                if (data.user_email) {
                    this.userData = {
                        ...this.userData,
                        email: data.user_email,
                        name: data.user_name,
                        workshop_name: data.workshop_name,
                        role: data.role,
                        plan: data.plan,
                        credits: data.credits || 0,
                        is_admin: data.is_admin || false,
                        credits_display: data.credits_display || String(data.credits || 0)
                    };
                    this.currentUser = this.userData;
                    this.updateCreditsDisplay();
                }
                
                this.stopTokenMonitoring();
                this.startTokenMonitoring();
                
                console.log('✅ Token refresh realizado com sucesso');
                return true;
            }
            return false;
        } catch (error) {
            console.error('❌ Erro no refresh:', error);
            return false;
        } finally {
            this._isRefreshing = false;
            // Resolve pendentes
            while (this.pendingRequests.length) {
                const resolve = this.pendingRequests.pop();
                resolve(false);
            }
        }
    }
    
    // Alias para compatibilidade
    async refreshToken() {
        return this.refreshTokenSafely();
    }
    
    handleTokenExpired() {
        console.log('⏰ Token expirado - limpando sessão');
        this.stopTokenMonitoring();
        this.clearTokens();
        this.isAuthenticated = false;
        this.currentUser = null;
        this.userData = null;
        
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
        
        const loginForm = document.getElementById('loginForm');
        if (loginForm) {
            loginForm.addEventListener('submit', (e) => this.handleLogin(e));
        }
        
        const registerForm = document.getElementById('registerForm');
        if (registerForm) {
            registerForm.addEventListener('submit', (e) => this.handleRegister(e));
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
            this.userData = null;
            return false;
        }
        
        try {
            const response = await fetch(`${this.apiBase}/auth/check-token`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            
            const data = await response.json();
            
            // 🔥 CORRIGIDO: Processa status 'valid' e 'refreshed'
            if (response.ok && (data.status === 'valid' || data.status === 'refreshed')) {
                // Se foi renovado, atualiza tokens
                if (data.status === 'refreshed' && data.access_token) {
                    localStorage.setItem('access_token', data.access_token);
                    if (data.refresh_token) {
                        localStorage.setItem('refresh_token', data.refresh_token);
                    }
                    this.stopTokenMonitoring();
                    this.startTokenMonitoring();
                }
                
                this.isAuthenticated = true;
                
                this.userData = {
                    email: data.user || data.user_email,
                    name: data.name || data.user_name,
                    is_admin: data.is_admin || false,
                    credits: data.credits || 0,
                    credits_display: data.credits_display || String(data.credits || 0),
                    plan: data.plan || 'basico'
                };
                
                this.currentUser = this.userData;
                this.updateCreditsDisplay();
                
                return true;
            }
            
            // Tenta refresh se tiver refresh token
            if (response.status === 401 && localStorage.getItem('refresh_token')) {
                const refreshed = await this.refreshToken();
                if (refreshed) {
                    return this.checkToken();
                }
            }
            
            this.clearTokens();
            this.isAuthenticated = false;
            this.currentUser = null;
            this.userData = null;
            return false;
            
        } catch (error) {
            console.error('Token check error:', error);
            this.isAuthenticated = false;
            this.currentUser = null;
            this.userData = null;
            return false;
        }
    }
    
    // ==============================================
    // CRÉDITOS (SINCRONIZADO COM BACKEND)
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
                        this.userData.credits_display = data.credits_display || this.getCreditsDisplay();
                    }
                    
                    this.updateCreditsDisplay();
                    
                    // 🔥 Dispara evento de atualização
                    window.dispatchEvent(new CustomEvent('creditsUpdated', {
                        detail: {
                            credits: data.credits,
                            display: data.credits_display,
                            maxCredits: MAX_CREDITS_BALANCE,
                            isPremium: this.isPremium()
                        }
                    }));
                    
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
    
    // 🔥 CORRIGIDO: Usa constante do backend
    getCreditsDisplay() {
        if (this.isAdmin()) return '∞';
        if (this.isPremium()) {
            const credits = this.getCredits();
            return `${credits}/${MAX_CREDITS_BALANCE}`;
        }
        return String(this.getCredits());
    }
    
    updateCreditsDisplay() {
        const displayValue = this.getCreditsDisplay();
        const selectors = '.credits-display, .user-credits, #creditsDisplay, #creditsCount, #uploadCredits, .credits-badge span, .credits-value';
        
        document.querySelectorAll(selectors).forEach(el => {
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
    // FETCH WITH AUTH (CORRIGIDO)
    // ==============================================
    
    async fetchWithAuth(url, options = {}) {
        let token = localStorage.getItem('access_token');
        
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
            
            // 🔥 CORRIGIDO: Tenta refresh se 401
            if (response.status === 401) {
                const refreshed = await this.refreshToken();
                
                if (refreshed) {
                    // 🔥 CORRIGIDO: Atualiza token e refaz requisição
                    const newToken = localStorage.getItem('access_token');
                    headers['Authorization'] = `Bearer ${newToken}`;
                    response = await fetch(url, { ...options, headers });
                } else {
                    this.clearTokens();
                    this.isAuthenticated = false;
                    this.currentUser = null;
                    this.userData = null;
                    
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
        
        // 🔥 Dispara evento de auth ready
        window.dispatchEvent(new CustomEvent('authReady', {
            detail: {
                isAuthenticated: this.isAuthenticated,
                user: this.userData
            }
        }));
    }
}

// ==============================================
// INSTÂNCIA GLOBAL
// ==============================================

window.appAuth = new Auth();

console.log('✅ Auth carregado (v2.0 - sincronizado com backend)');
console.log('   ✅ Use window.appAuth para acessar');
console.log('   ✅ CAPTCHA REMOVIDO');
console.log(`   ✅ MAX_CREDITS_BALANCE: ${MAX_CREDITS_BALANCE}`);
console.log(`   ✅ TOKEN_EXPIRY_MINUTES: ${TOKEN_EXPIRY_MINUTES}`);