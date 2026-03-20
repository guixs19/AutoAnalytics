// frontend/js/auth.js - VERSÃO FINAL COM CICLO DE VIDA COMPLETO DO TOKEN
/*
 * auth.js - Gerenciamento de autenticação
 * 
 * ✅ Login com CAPTCHA próprio
 * ✅ Registro com CAPTCHA
 * ✅ Ciclo de vida do token (15 minutos)
 * ✅ Refresh automático quando expirado
 * ✅ Limpeza automática do localStorage
 * ✅ Suporte a admin e premium
 * ✅ Rate limiting no frontend
 * ✅ Verificação periódica do token
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
        
        this.init();
    }
    
    // ===== LOCALSTORAGE MANAGEMENT =====
    
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
        
        // Guardar timestamp de expiração (15 minutos)
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
        
        console.log('🧹 LocalStorage completamente limpo');
    }
    
    // ===== TOKEN LIFE CYCLE =====
    
    isTokenExpired() {
        const expiresAt = localStorage.getItem('token_expires_at');
        if (!expiresAt) return true;
        
        const now = Date.now();
        const expired = now > parseInt(expiresAt);
        
        if (expired) {
            console.log('⏰ Token expirado (>15 minutos)');
        }
        
        return expired;
    }
    
    getTimeRemaining() {
        const expiresAt = localStorage.getItem('token_expires_at');
        if (!expiresAt) return 0;
        
        const remaining = Math.max(0, parseInt(expiresAt) - Date.now());
        return Math.floor(remaining / 1000); // em segundos
    }
    
    formatTimeRemaining() {
        const seconds = this.getTimeRemaining();
        if (seconds <= 0) return 'Expirado';
        
        const minutes = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${minutes}:${secs.toString().padStart(2, '0')}`;
    }
    
    // ===== TOKEN VERIFICATION =====
    
    async checkTokenStatus() {
        const token = localStorage.getItem('access_token');
        
        if (!token) {
            console.log('🔍 Nenhum token encontrado');
            return { status: 'no_token' };
        }
        
        // Verificar expiração local primeiro
        if (this.isTokenExpired()) {
            console.log('⏰ Token expirado localmente - tentando refresh...');
        }
        
        try {
            const response = await fetch(`${this.apiBase}/auth/check-token`, {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Cache-Control': 'no-cache'
                },
                credentials: 'include'  // Importante para cookies
            });
            
            const data = await response.json();
            
            if (response.ok) {
                // ✅ CASO 1: TOKEN VÁLIDO (menos de 15 minutos)
                if (data.status === 'valid') {
                    console.log(`✅ Token válido por mais ${data.expires_in}s`);
                    
                    // Atualizar dados do usuário
                    if (data.user) {
                        this.user = {
                            ...this.user,
                            name: data.name,
                            email: data.user,
                            is_admin: data.is_admin,
                            credits: data.credits
                        };
                        this.saveUser(this.user);
                        this.updateUserUI();
                    }
                    
                    return { status: 'valid', data };
                }
                
                // ✅ CASO 2: TOKEN RENOVADO (refresh automático)
                if (data.status === 'refreshed') {
                    console.log('🔄 Token renovado automaticamente - novo token de 15min gerado');
                    
                    // Salvar novos tokens
                    this.saveTokens(
                        data.access_token,
                        data.refresh_token,
                        data.expires_in  // 900 segundos = 15 minutos
                    );
                    
                    // Atualizar usuário
                    this.user = {
                        ...this.user,
                        name: data.name,
                        email: data.user,
                        is_admin: data.is_admin,
                        credits: data.credits
                    };
                    this.saveUser(this.user);
                    this.updateUserUI();
                    
                    return { status: 'refreshed', data };
                }
            }
            
            // ❌ CASO 3: TOKEN INVÁLIDO - LIMPAR TUDO
            if (data.action === 'clear_storage_and_redirect') {
                console.log('🧹 Token inválido - limpando storage');
                this.clearStorage();
                
                if (!this.isLoginPage() && !this.isRegisterPage()) {
                    this.showMessage('Sessão expirada. Faça login novamente.', 'warning');
                    setTimeout(() => {
                        window.location.href = '/login.html';
                    }, 1500);
                }
                
                return { status: 'invalid' };
            }
            
            return { status: 'error', data };
            
        } catch (error) {
            console.error('❌ Erro ao verificar token:', error);
            
            // Em caso de erro de rede, verificar expiração local
            if (this.isTokenExpired()) {
                console.log('⏰ Token expirado localmente - limpando');
                this.clearStorage();
                
                if (!this.isLoginPage() && !this.isRegisterPage()) {
                    window.location.href = '/login.html';
                }
            }
            
            return { status: 'error' };
        }
    }
    
    // ===== INITIALIZATION =====
    
    async init() {
        console.log('🔧 Auth v2.0 inicializado');
        console.log('📍 API Base:', this.apiBase);
        
        const path = window.location.pathname;
        console.log('📍 Página atual:', path);
        
        // Login page
        if (path.includes('login.html') || path === '/login' || path === '/') {
            this.initLoginPage();
        }
        // Register page
        else if (path.includes('register.html') || path === '/register') {
            this.initRegisterPage();
        }
        // Páginas protegidas
        else {
            // Verificar token antes de carregar a página
            const tokenStatus = await this.checkTokenStatus();
            
            if (tokenStatus.status === 'invalid' || tokenStatus.status === 'no_token') {
                this.redirectToLogin();
                return;
            }
            
            // Iniciar verificação periódica (a cada 3 minutos)
            this.startTokenCheckInterval();
            this.updateUserUI();
            this.loadUserCredits();
            
            console.log('✅ Usuário autenticado:', this.user.email);
            console.log(`⏱️ Token expira em: ${this.formatTimeRemaining()}`);
        }
    }
    
    startTokenCheckInterval() {
        // Limpar intervalo anterior
        if (this.tokenCheckInterval) {
            clearInterval(this.tokenCheckInterval);
        }
        
        // Verificar a cada 3 minutos
        this.tokenCheckInterval = setInterval(() => {
            console.log('⏰ Verificando status do token...');
            console.log(`⏱️ Tempo restante: ${this.formatTimeRemaining()}`);
            this.checkTokenStatus();
        }, 3 * 60 * 1000); // 3 minutos
    }
    
    async loadUserCredits() {
        try {
            const token = localStorage.getItem('access_token');
            if (!token) return;
            
            const response = await fetch(`${this.apiBase}/user/credits`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            
            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    this.user.credits = data.credits;
                    this.saveUser(this.user);
                    this.updateCreditsDisplay();
                }
            }
        } catch (error) {
            console.error('Erro ao carregar créditos:', error);
        }
    }
    
    // ===== LOGIN PAGE =====
    
    initLoginPage() {
        console.log('🔐 Inicializando página de login...');
        
        // Limpar qualquer token existente ao entrar na página de login
        this.clearStorage();
        
        setTimeout(() => {
            if (document.getElementById('loginCaptchaImage')) {
                this.loadLoginCaptcha();
                this.bindLoginEvents();
            } else {
                console.warn('Elementos de login não encontrados');
            }
        }, 300);
    }
    
    async loadLoginCaptcha() {
        const img = document.getElementById('loginCaptchaImage');
        const input = document.getElementById('loginCaptchaInput');
        const refreshBtn = document.getElementById('refreshLoginCaptcha');
        
        if (!img) {
            console.error('Elemento loginCaptchaImage não encontrado');
            return;
        }
        
        // Desabilitar botão de refresh
        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        }
        
        // Limpar input
        if (input) {
            input.value = '';
            input.disabled = true;
            input.placeholder = 'Carregando CAPTCHA...';
        }
        
        // Loading image
        img.src = 'data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'200\' height=\'70\' viewBox=\'0 0 200 70\'%3E%3Crect width=\'200\' height=\'70\' fill=\'%23f0f0f0\'/%3E%3Ctext x=\'40\' y=\'45\' font-family=\'Arial\' font-size=\'20\' fill=\'%23999\'%3ECarregando...%3C/text%3E%3C/svg%3E';
        
        try {
            console.log('🔄 Carregando CAPTCHA do servidor...');
            
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 5000);
            
            const response = await fetch(`${this.apiBase}/auth/captcha/generate?t=${Date.now()}`, {
                signal: controller.signal,
                cache: 'no-cache'
            });
            
            clearTimeout(timeoutId);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            // Pegar CAPTCHA ID do header
            const captchaId = response.headers.get('X-Captcha-ID');
            
            if (!captchaId) {
                console.warn('Header X-Captcha-ID não recebido, usando fallback');
                this.generateFallbackCaptcha('login');
                return;
            }
            
            this.captchaId = captchaId;
            
            // Converter blob para URL
            const blob = await response.blob();
            const imageUrl = URL.createObjectURL(blob);
            
            // Limpar URL anterior
            if (img.dataset.blobUrl) {
                URL.revokeObjectURL(img.dataset.blobUrl);
            }
            
            img.src = imageUrl;
            img.dataset.blobUrl = imageUrl;
            
            // Habilitar input
            if (input) {
                input.disabled = false;
                input.placeholder = 'Digite os 6 números';
                input.focus();
            }
            
            console.log('✅ CAPTCHA carregado com ID:', captchaId.substring(0, 8) + '...');
            
        } catch (error) {
            console.error('❌ Erro ao carregar CAPTCHA:', error);
            this.showMessage('Erro ao carregar CAPTCHA. Usando modo alternativo.', 'warning');
            this.generateFallbackCaptcha('login');
            
        } finally {
            // Reabilitar botão de refresh
            if (refreshBtn) {
                refreshBtn.disabled = false;
                refreshBtn.innerHTML = '<i class="fas fa-sync-alt"></i>';
            }
        }
    }
    
    generateFallbackCaptcha(type) {
        console.log(`🔄 Gerando CAPTCHA fallback para ${type}...`);
        
        const img = document.getElementById(`${type}CaptchaImage`);
        const input = document.getElementById(`${type}CaptchaInput`);
        
        if (!img) return;
        
        // Gerar número aleatório de 6 dígitos
        const captchaText = Math.floor(100000 + Math.random() * 900000).toString();
        
        // Criar canvas
        const canvas = document.createElement('canvas');
        canvas.width = 200;
        canvas.height = 70;
        const ctx = canvas.getContext('2d');
        
        // Fundo
        ctx.fillStyle = '#f8f9fa';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        
        // Texto
        ctx.font = 'bold 36px "Courier New", monospace';
        ctx.fillStyle = '#212529';
        ctx.fillText(captchaText, 25, 50);
        
        // Ruído
        for (let i = 0; i < 50; i++) {
            ctx.fillStyle = `rgba(0,0,0,${Math.random() * 0.2})`;
            ctx.fillRect(Math.random() * canvas.width, Math.random() * canvas.height, 2, 2);
        }
        
        img.src = canvas.toDataURL();
        
        // Guardar no dataset para validação
        if (input) {
            input.dataset.fallbackCaptcha = captchaText;
            input.disabled = false;
            input.placeholder = 'Digite o código';
        }
        
        // ID fictício
        if (type === 'login') {
            this.captchaId = 'fallback_' + Date.now();
        } else {
            this.captchaIdRegister = 'fallback_' + Date.now();
        }
        
        console.log(`✅ CAPTCHA fallback gerado: ${captchaText}`);
    }
    
    async handleLogin() {
        const email = document.getElementById('loginEmail')?.value;
        const password = document.getElementById('loginPassword')?.value;
        const captchaInput = document.getElementById('loginCaptchaInput')?.value;
        
        // Validações
        if (!email || !password || !captchaInput) {
            this.showMessage('Preencha todos os campos', 'error');
            return;
        }
        
        if (!email.includes('@')) {
            this.showMessage('Email inválido', 'error');
            return;
        }
        
        if (password.length < 6) {
            this.showMessage('Senha deve ter no mínimo 6 caracteres', 'error');
            return;
        }
        
        // Rate limiting simples
        this.loginAttempts++;
        if (this.loginAttempts > this.maxLoginAttempts) {
            this.showMessage('Muitas tentativas. Aguarde 1 minuto.', 'error');
            setTimeout(() => { this.loginAttempts = 0; }, 60000);
            return;
        }
        
        // Desabilitar botão
        const loginBtn = document.getElementById('loginBtn');
        const originalText = loginBtn.innerHTML;
        loginBtn.disabled = true;
        loginBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Entrando...';
        
        try {
            // Verificar se é fallback
            const isFallback = this.captchaId?.startsWith('fallback_');
            
            // Se for fallback, validar localmente
            if (isFallback) {
                const captchaInput_el = document.getElementById('loginCaptchaInput');
                const fallbackText = captchaInput_el?.dataset.fallbackCaptcha;
                
                if (captchaInput !== fallbackText) {
                    this.showMessage('CAPTCHA incorreto', 'error');
                    this.loadLoginCaptcha();
                    loginBtn.disabled = false;
                    loginBtn.innerHTML = originalText;
                    return;
                }
            }
            
            // Preparar headers
            const headers = {
                'Content-Type': 'application/json'
            };
            
            // Se não for fallback, enviar CAPTCHA ID
            if (!isFallback && this.captchaId) {
                headers['X-Captcha-ID'] = this.captchaId;
            }
            
            console.log('📤 Enviando login para:', email);
            
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
            
            if (response.ok) {
                // ✅ Sucesso no login
                console.log('✅ Login bem-sucedido');
                
                // Salvar tokens com expiração de 15 minutos
                this.saveTokens(
                    data.access_token,
                    data.refresh_token,
                    data.expires_in  // 900 segundos = 15 minutos
                );
                
                // Salvar usuário
                this.saveUser({
                    name: data.user_name,
                    email: data.user_email,
                    workshop_name: data.workshop_name,
                    role: data.role,
                    credits: data.credits,
                    plan: data.plan,
                    is_admin: data.is_admin,
                    is_premium: data.plan === 'premium_mensal'
                });
                
                this.loginAttempts = 0;
                this.showMessage('✅ Login realizado! Redirecionando...', 'success');
                
                // Redirecionar para dashboard
                setTimeout(() => {
                    window.location.href = '/';
                }, 1000);
                
            } else {
                // Erro no login
                this.showMessage(data.detail || 'Erro no login', 'error');
                this.loadLoginCaptcha(); // Recarregar CAPTCHA
                loginBtn.disabled = false;
                loginBtn.innerHTML = originalText;
            }
            
        } catch (error) {
            console.error('❌ Erro no login:', error);
            this.showMessage('Erro de conexão. Tente novamente.', 'error');
            this.loadLoginCaptcha();
            loginBtn.disabled = false;
            loginBtn.innerHTML = originalText;
        }
    }
    
    bindLoginEvents() {
        // Refresh captcha
        document.getElementById('refreshLoginCaptcha')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.loadLoginCaptcha();
        });
        
        // Login form
        document.getElementById('loginForm')?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleLogin();
        });
        
        // Forgot password
        document.getElementById('forgotPassword')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.showMessage('Função de recuperação de senha em breve!', 'info');
        });
        
        // Enter key no captcha
        document.getElementById('loginCaptchaInput')?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                this.handleLogin();
            }
        });
    }
    
    // ===== REGISTER PAGE =====
    
    initRegisterPage() {
        console.log('🔐 Inicializando página de registro...');
        
        setTimeout(() => {
            if (document.getElementById('registerCaptchaImage')) {
                this.loadRegisterCaptcha();
                this.bindRegisterEvents();
            }
        }, 300);
    }
    
    async loadRegisterCaptcha() {
        const img = document.getElementById('registerCaptchaImage');
        const input = document.getElementById('registerCaptchaInput');
        const refreshBtn = document.getElementById('refreshRegisterCaptcha');
        
        if (!img) return;
        
        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        }
        
        if (input) {
            input.value = '';
            input.disabled = true;
            input.placeholder = 'Carregando...';
        }
        
        img.src = 'data:image/svg+xml,%3Csvg...Carregando...%3C/svg%3E';
        
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
            
            console.log('✅ CAPTCHA registro carregado');
            
        } catch (error) {
            console.error('❌ Erro CAPTCHA registro:', error);
            this.generateFallbackCaptcha('register');
            
        } finally {
            if (refreshBtn) {
                refreshBtn.disabled = false;
                refreshBtn.innerHTML = '<i class="fas fa-sync-alt"></i>';
            }
        }
    }
    
    async handleRegister() {
        const name = document.getElementById('regName')?.value;
        const email = document.getElementById('regEmail')?.value;
        const password = document.getElementById('regPassword')?.value;
        const confirm = document.getElementById('regConfirmPassword')?.value;
        const workshop = document.getElementById('regWorkshop')?.value;
        const captchaInput = document.getElementById('registerCaptchaInput')?.value;
        
        if (!name || !email || !password || !confirm || !workshop || !captchaInput) {
            this.showMessage('Preencha todos os campos', 'error');
            return;
        }
        
        if (password !== confirm) {
            this.showMessage('As senhas não coincidem', 'error');
            return;
        }
        
        if (password.length < 6) {
            this.showMessage('A senha deve ter no mínimo 6 caracteres', 'error');
            return;
        }
        
        if (!email.includes('@')) {
            this.showMessage('Email inválido', 'error');
            return;
        }
        
        // Verificar fallback
        const isFallback = this.captchaIdRegister?.startsWith('fallback_');
        
        if (isFallback) {
            const fallbackText = document.getElementById('registerCaptchaInput')?.dataset.fallbackCaptcha;
            if (captchaInput !== fallbackText) {
                this.showMessage('CAPTCHA incorreto', 'error');
                this.loadRegisterCaptcha();
                return;
            }
        }
        
        const registerBtn = document.getElementById('registerBtn');
        const originalText = registerBtn.innerHTML;
        registerBtn.disabled = true;
        registerBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Criando conta...';
        
        try {
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
                this.showMessage('✅ Conta criada! Faça login.', 'success');
                
                // Limpar formulário
                document.getElementById('registerForm').reset();
                
                // Mudar para aba de login
                const loginTab = document.getElementById('login-tab');
                if (loginTab) {
                    loginTab.click();
                    
                    // Pré-preencher email
                    const loginEmail = document.getElementById('loginEmail');
                    if (loginEmail) {
                        loginEmail.value = email.trim().toLowerCase();
                    }
                    
                    this.loadLoginCaptcha();
                }
                
            } else {
                this.showMessage(data.detail || 'Erro no registro', 'error');
                this.loadRegisterCaptcha();
                registerBtn.disabled = false;
                registerBtn.innerHTML = originalText;
            }
            
        } catch (error) {
            console.error('❌ Erro no registro:', error);
            this.showMessage('Erro de conexão', 'error');
            this.loadRegisterCaptcha();
            registerBtn.disabled = false;
            registerBtn.innerHTML = originalText;
        }
    }
    
    bindRegisterEvents() {
        document.getElementById('refreshRegisterCaptcha')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.loadRegisterCaptcha();
        });
        
        document.getElementById('registerForm')?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleRegister();
        });
    }
    
    // ===== LOGOUT =====
    
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
            // ✅ LIMPAR TUDO
            this.clearStorage();
            
            // Limpar intervalo
            if (this.tokenCheckInterval) {
                clearInterval(this.tokenCheckInterval);
            }
            
            // Limpar URLs de objetos
            document.querySelectorAll('img[data-blob-url]').forEach(img => {
                URL.revokeObjectURL(img.dataset.blobUrl);
            });
            
            this.showMessage('Até logo!', 'info');
            
            setTimeout(() => {
                window.location.href = '/login.html';
            }, 500);
        }
    }
    
    // ===== USER INTERFACE =====
    
    updateUserUI() {
        // Nome do usuário
        const userNameEl = document.getElementById('userName');
        if (userNameEl) {
            userNameEl.textContent = this.user?.name || 'Usuário';
        }
        
        // Nome da oficina
        const workshopEl = document.getElementById('workshopName');
        if (workshopEl) {
            workshopEl.textContent = this.user?.workshop_name || 'Oficina';
        }
        
        // Atualizar créditos
        this.updateCreditsDisplay();
        
        // Badge de admin
        const adminBadge = document.getElementById('adminBadge');
        if (adminBadge) {
            adminBadge.style.display = this.isAdmin() ? 'inline-block' : 'none';
        }
        
        // Badge de premium
        const premiumBadge = document.getElementById('premiumBadge');
        if (premiumBadge) {
            premiumBadge.style.display = this.isPremium() ? 'inline-block' : 'none';
        }
        
        // Timer de expiração (opcional)
        const tokenTimer = document.getElementById('tokenTimer');
        if (tokenTimer && this.isAuthenticated()) {
            tokenTimer.textContent = this.formatTimeRemaining();
            
            // Atualizar a cada minuto
            setInterval(() => {
                tokenTimer.textContent = this.formatTimeRemaining();
            }, 60000);
        }
    }
    
    updateCreditsDisplay() {
        const credits = this.getCreditsDisplay();
        
        document.querySelectorAll('#navbarCredits span, #creditsCount, .credits-badge span').forEach(el => {
            if (el) el.textContent = credits;
        });
    }
    
    // ===== UTILITIES =====
    
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
            this.showMessage('Faça login para continuar', 'info');
            setTimeout(() => {
                window.location.href = '/login.html';
            }, 1000);
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
    
    // ===== MESSAGES =====
    
    showMessage(message, type = 'info') {
        const messageDiv = document.getElementById('authMessage');
        if (!messageDiv) {
            alert(message); // Fallback
            return;
        }
        
        const icons = {
            success: '✅',
            error: '❌',
            warning: '⚠️',
            info: 'ℹ️'
        };
        
        messageDiv.innerHTML = `
            <div class="alert alert-${type} alert-dismissible fade show" role="alert">
                <strong>${icons[type] || ''}</strong> ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>
        `;
        
        setTimeout(() => {
            const alert = messageDiv.querySelector('.alert');
            if (alert) {
                alert.classList.remove('show');
                setTimeout(() => {
                    messageDiv.innerHTML = '';
                }, 300);
            }
        }, 5000);
    }
}

// ===== GLOBAL INITIALIZATION =====
document.addEventListener('DOMContentLoaded', () => {
    window.appAuth = new Auth();
});

// ===== GLOBAL FUNCTIONS =====
window.isAdmin = () => window.appAuth?.isAdmin() || false;
window.isPremium = () => window.appAuth?.isPremium() || false;
window.getCreditsDisplay = () => window.appAuth?.getCreditsDisplay() || '0';
window.getCurrentUser = () => window.appAuth?.getCurrentUser() || {};
window.logout = () => window.appAuth?.logout();
window.checkToken = () => window.appAuth?.checkTokenStatus();
window.getTokenTimeRemaining = () => window.appAuth?.formatTimeRemaining();

console.log('✅ auth.js v2.0 carregado - Ciclo de vida do token implementado!');