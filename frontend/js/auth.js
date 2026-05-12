// frontend/js/auth.js - VERSÃO CORRIGIDA COM CAPTCHA DE NÚMEROS RABISCADOS
/**
 * Sistema de Autenticação com CAPTCHA simples
 * Usuário deve reescrever os números que aparecem na imagem
 */

class Auth {
    constructor() {
        this.apiBase = window.location.hostname.includes('localhost') 
            ? 'http://localhost:8000/api'
            : '/api';
        
        this.currentUser = null;
        this.isAuthenticated = false;
        this.userData = null;
        this.currentCaptchaId = null;
        this.captchaTimer = null;
        
        this.init();
    }
    
    async init() {
        console.log('🔐 Inicializando Auth Manager...');
        await this.checkToken();
        this.setupAuthPageListeners();
        this.updateUI();
        console.log(`✅ Auth Manager inicializado - Autenticado: ${this.isAuthenticated}`);
    }
    
    // ==============================================
    // CAPTCHA DE NÚMEROS RABISCADOS - CORRIGIDO
    // ==============================================
    
    async loadCaptcha(sessionType = 'login') {
        try {
            // CORREÇÃO: Adicionado /auth/ antes de /captcha/generate
            const url = `${this.apiBase}/auth/captcha/generate?session_type=${sessionType}&t=${Date.now()}`;
            console.log(`🔄 Carregando CAPTCHA de: ${url}`);
            
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache'
                }
            });
            
            if (!response.ok) {
                const errorText = await response.text();
                console.error(`❌ Erro HTTP ${response.status}: ${errorText}`);
                throw new Error(`Erro ao carregar CAPTCHA: ${response.status}`);
            }
            
            // Verifica o tipo de conteúdo
            const contentType = response.headers.get('Content-Type');
            const captchaId = response.headers.get('X-Captcha-ID');
            
            if (!captchaId) {
                console.error('❌ CAPTCHA ID não recebido nos headers');
                throw new Error('CAPTCHA ID não recebido');
            }
            
            console.log(`✅ CAPTCHA ID recebido: ${captchaId.substring(0, 8)}...`);
            this.currentCaptchaId = captchaId;
            
            // Converte resposta para blob e cria URL
            const blob = await response.blob();
            const imageUrl = URL.createObjectURL(blob);
            
            // Atualiza imagem do CAPTCHA
            const captchaImage = document.getElementById(`${sessionType}CaptchaImage`);
            if (captchaImage) {
                // Revoga URL antiga para evitar memory leak
                if (captchaImage.src && captchaImage.src.startsWith('blob:')) {
                    URL.revokeObjectURL(captchaImage.src);
                }
                captchaImage.src = imageUrl;
                console.log(`✅ Imagem CAPTCHA atualizada para ${sessionType}`);
            } else {
                console.error(`❌ Elemento ${sessionType}CaptchaImage não encontrado`);
            }
            
            // Atualiza hidden field com o ID
            const captchaIdField = document.getElementById(`${sessionType}CaptchaId`);
            if (captchaIdField) {
                captchaIdField.value = captchaId;
            }
            
            // Inicia timer de 2 minutos
            this.startCaptchaTimer(sessionType);
            
            // Limpa input anterior
            const captchaInput = document.getElementById(`${sessionType}CaptchaInput`);
            if (captchaInput) {
                captchaInput.value = '';
                captchaInput.disabled = false;
                captchaInput.placeholder = 'Digite os números da imagem';
            }
            
            return captchaId;
            
        } catch (error) {
            console.error('❌ Erro ao carregar CAPTCHA:', error);
            this.showCaptchaError(sessionType);
            return null;
        }
    }
    
    showCaptchaError(sessionType = 'login') {
        const captchaImage = document.getElementById(`${sessionType}CaptchaImage`);
        if (captchaImage) {
            captchaImage.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="280" height="100" viewBox="0 0 280 100"%3E%3Crect width="280" height="100" fill="%23e53e3e"/%3E%3Ctext x="140" y="55" font-family="monospace" font-size="16" fill="white" text-anchor="middle"%3E⚠️ ERRO - Clique para recarregar%3C/text%3E%3C/svg%3E';
        }
    }
    
    startCaptchaTimer(sessionType) {
        // Limpa timer anterior
        if (this.captchaTimer) {
            clearInterval(this.captchaTimer);
        }
        
        const expirySeconds = 120;
        let remaining = expirySeconds;
        
        const timerElement = document.getElementById(`${sessionType}CaptchaTimer`);
        
        this.captchaTimer = setInterval(() => {
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
                clearInterval(this.captchaTimer);
                if (timerElement) {
                    timerElement.textContent = '00:00';
                    timerElement.classList.add('expired');
                }
                
                // Desabilita input
                const captchaInput = document.getElementById(`${sessionType}CaptchaInput`);
                if (captchaInput) {
                    captchaInput.disabled = true;
                    captchaInput.placeholder = 'EXPIRADO - Clique em ↻';
                }
            }
        }, 1000);
    }
    
    async refreshCaptcha(sessionType = 'login') {
        console.log(`🔄 Atualizando CAPTCHA para ${sessionType}...`);
        
        // Reseta timer
        if (this.captchaTimer) {
            clearInterval(this.captchaTimer);
        }
        
        // Recarrega
        await this.loadCaptcha(sessionType);
    }
    
    // ==============================================
    // LOGIN - CORRIGIDO COM HEADERS CAPTCHA
    // ==============================================
    
    async login(email, password, captchaText, captchaId) {
        if (!email || !password) {
            this.showError('Preencha email e senha');
            return false;
        }
        
        if (!captchaText) {
            this.showError('Digite os números que aparecem na imagem');
            return false;
        }
        
        if (!captchaId) {
            this.showError('CAPTCHA não carregado. Recarregue a página.');
            return false;
        }
        
        this.setLoading(true);
        
        try {
            const response = await fetch(`${this.apiBase}/auth/login`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Captcha-ID': captchaId,
                    'X-Captcha-Text': captchaText
                },
                body: JSON.stringify({
                    email,
                    password,
                    captcha_id: captchaId,
                    captcha_text: captchaText
                })
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.detail || data.message || 'Falha no login');
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
                
                console.log('✅ Login realizado com sucesso');
                this.showSuccess('Login realizado! Redirecionando...');
                
                document.dispatchEvent(new CustomEvent('userAuthenticated', { detail: this.userData }));
                
                setTimeout(() => {
                    window.location.href = '/dashboard.html';
                }, 1000);
                
                return true;
            }
            
            throw new Error(data.message || 'Erro no login');
            
        } catch (error) {
            console.error('❌ Login error:', error);
            this.showError(error.message);
            await this.refreshCaptcha('login');
            return false;
        } finally {
            this.setLoading(false);
        }
    }
    
    // ==============================================
    // REGISTRO - CORRIGIDO COM HEADERS CAPTCHA
    // ==============================================
    
    async register(name, email, password, workshopName, captchaText, captchaId) {
        if (!name || !email || !password || !workshopName) {
            this.showError('Preencha todos os campos');
            return false;
        }
        
        if (password.length < 6) {
            this.showError('Senha deve ter no mínimo 6 caracteres');
            return false;
        }
        
        if (!captchaText) {
            this.showError('Digite os números que aparecem na imagem');
            return false;
        }
        
        if (!captchaId) {
            this.showError('CAPTCHA não carregado. Recarregue a página.');
            return false;
        }
        
        this.setLoading(true);
        
        try {
            const response = await fetch(`${this.apiBase}/auth/register`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Captcha-ID': captchaId,
                    'X-Captcha-Text': captchaText
                },
                body: JSON.stringify({
                    name,
                    email,
                    password,
                    workshop_name: workshopName,
                    captcha_text: captchaText,
                    captcha_id: captchaId
                })
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.detail || data.message || 'Falha no registro');
            }
            
            if (data.success) {
                console.log('✅ Registro realizado com sucesso');
                this.showSuccess('Conta criada! Faça login para continuar.');
                
                setTimeout(() => {
                    window.location.href = '/login.html';
                }, 2000);
                
                return true;
            }
            
            throw new Error(data.message || 'Erro no registro');
            
        } catch (error) {
            console.error('❌ Registration error:', error);
            this.showError(error.message);
            await this.refreshCaptcha('register');
            return false;
        } finally {
            this.setLoading(false);
        }
    }
    
    // ==============================================
    // VERIFICAÇÃO DE TOKEN
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
    
    // ==============================================
    // LOGOUT
    // ==============================================
    
    async logout() {
        const refreshToken = localStorage.getItem('refresh_token');
        const accessToken = localStorage.getItem('access_token');
        
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
        
        window.location.href = '/login.html';
    }
    
    clearTokens() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
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
            if (window.location.pathname !== '/planos.html') {
                window.location.href = '/planos.html';
            }
        }, 2000);
    }
    
    updateCreditsDisplay() {
        const creditsElements = document.querySelectorAll('.credits-display, .user-credits');
        const displayValue = this.getCreditsDisplay();
        
        creditsElements.forEach(el => {
            el.textContent = displayValue;
        });
        
        const uploadBtn = document.getElementById('uploadButton');
        if (uploadBtn && uploadBtn.innerHTML.includes('créditos')) {
            const icon = this.isAdmin() ? '👑' : (this.isPremium() ? '⭐' : '🚀');
            uploadBtn.innerHTML = `${icon} Iniciar Análise <span class="credit-badge">${displayValue} créditos</span>`;
        }
    }
    
    // ==============================================
    // UTILIDADES
    // ==============================================
    
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
            console.log('❌ Sem token disponível');
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
                console.log('🔄 Token expirado, tentando refresh...');
                
                const refreshed = await this.refreshToken();
                
                if (refreshed) {
                    const newToken = localStorage.getItem('access_token');
                    headers['Authorization'] = `Bearer ${newToken}`;
                    response = await fetch(url, { ...options, headers });
                    console.log('✅ Requisição retentada com novo token');
                } else {
                    console.log('❌ Refresh falhou');
                    this.clearTokens();
                    this.isAuthenticated = false;
                    return null;
                }
            }
            
            return response;
            
        } catch (error) {
            console.error('❌ Erro na requisição:', error);
            return null;
        }
    }
    
    // ==============================================
    // UI HELPERS
    // ==============================================
    
    setLoading(loading) {
        const submitBtn = document.querySelector('button[type="submit"]');
        if (submitBtn) {
            submitBtn.disabled = loading;
            if (loading) {
                submitBtn.innerHTML = '<div class="spinner-border spinner-border-sm me-2"></div>Processando...';
            } else {
                const originalText = submitBtn.id === 'loginBtn' ? 'Entrar' : 'Criar Conta';
                submitBtn.innerHTML = submitBtn.id === 'loginBtn' 
                    ? '<i class="fas fa-sign-in-alt me-2"></i>Entrar'
                    : '<i class="fas fa-user-plus me-2"></i>Criar Conta';
            }
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
    
    setupAuthPageListeners() {
        // Login form
        const loginForm = document.getElementById('loginForm');
        if (loginForm) {
            loginForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                
                const email = document.getElementById('loginEmail')?.value;
                const password = document.getElementById('loginPassword')?.value;
                const captchaText = document.getElementById('loginCaptchaInput')?.value;
                const captchaId = document.getElementById('loginCaptchaId')?.value;
                
                await this.login(email, password, captchaText, captchaId);
            });
            
            // Carrega CAPTCHA do login
            this.loadCaptcha('login');
            
            const refreshBtn = document.getElementById('refreshLoginCaptcha');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', () => this.refreshCaptcha('login'));
            }
        }
        
        // Register form
        const registerForm = document.getElementById('registerForm');
        if (registerForm) {
            registerForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                
                const name = document.getElementById('regName')?.value;
                const email = document.getElementById('regEmail')?.value;
                const password = document.getElementById('regPassword')?.value;
                const workshopName = document.getElementById('regWorkshop')?.value;
                const captchaText = document.getElementById('registerCaptchaInput')?.value;
                const captchaId = document.getElementById('registerCaptchaId')?.value;
                
                await this.register(name, email, password, workshopName, captchaText, captchaId);
            });
            
            // Carrega CAPTCHA do registro
            this.loadCaptcha('register');
            
            const refreshBtn = document.getElementById('refreshRegisterCaptcha');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', () => this.refreshCaptcha('register'));
            }
        }
        
        // Password visibility toggle
        document.querySelectorAll('.password-toggle').forEach(btn => {
            btn.addEventListener('click', () => {
                const fieldId = btn.getAttribute('data-field') || 
                               (btn.previousElementSibling?.id) ||
                               btn.parentElement?.querySelector('input')?.id;
                const field = document.getElementById(fieldId);
                if (field) {
                    const icon = btn.querySelector('i');
                    if (field.type === 'password') {
                        field.type = 'text';
                        icon.classList.remove('fa-eye');
                        icon.classList.add('fa-eye-slash');
                    } else {
                        field.type = 'password';
                        icon.classList.remove('fa-eye-slash');
                        icon.classList.add('fa-eye');
                    }
                }
            });
        });
    }
}

// Instância global
window.appAuth = new Auth();

// Exporta funções úteis
window.getAuth = () => window.appAuth;
window.refreshCaptcha = (type) => window.appAuth?.refreshCaptcha(type);

console.log('✅ auth.js carregado - CAPTCHA de números rabiscados ativo');