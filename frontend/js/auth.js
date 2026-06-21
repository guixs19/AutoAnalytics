// frontend/js/auth.js - VERSÃO CORRIGIDA E OTIMIZADA
/**
 * Módulo de Autenticação - AutoAnalytics
 * FLUXO: login → dashboard | register → login
 * 🔥 Token expira em 15 minutos (conforme security.py)
 * 🔥 Sincronizado com auth_routes.py e auth.py
 * ✅ CORREÇÃO: captcha_code enviado corretamente
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
    // 🔥 CAPTCHA - /api/auth/captcha/generate
    // ==============================================
    
    async loadCaptcha(sessionType = 'login') {
        try {
            console.log(`🔄 Carregando CAPTCHA para: ${sessionType}`);
            
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
            
            console.log(`✅ CAPTCHA ID recebido: ${captchaId}`);
            
            if (sessionType === 'login') {
                this.loginCaptchaId = captchaId;
            } else {
                this.registerCaptchaId = captchaId;
                this.isRegisterCaptchaLoaded = true;
            }
            
            const hiddenField = document.getElementById(`${sessionType}CaptchaId`);
            if (hiddenField) {
                hiddenField.value = captchaId;
                console.log(`📝 Hidden field ${sessionType}CaptchaId atualizado`);
            }
            
            const blob = await response.blob();
            const imageUrl = URL.createObjectURL(blob);
            
            const imageId = sessionType === 'login' ? 'loginCaptchaImg' : 'registerCaptchaImg';
            const captchaImage = document.getElementById(imageId);
            if (captchaImage) {
                if (captchaImage.src && captchaImage.src.startsWith('blob:')) {
                    URL.revokeObjectURL(captchaImage.src);
                }
                captchaImage.src = imageUrl;
                console.log(`🖼️ Imagem CAPTCHA atualizada: #${imageId}`);
            } else {
                console.warn(`⚠️ Elemento #${imageId} não encontrado`);
            }
            
            this.startCaptchaTimer(sessionType);
            
            const inputId = sessionType === 'login' ? 'loginCaptchaInput' : 'registerCaptchaInput';
            const captchaInput = document.getElementById(inputId);
            if (captchaInput) {
                captchaInput.value = '';
                captchaInput.disabled = false;
                captchaInput.placeholder = 'Digite os 4 números';
                captchaInput.focus();
            }
            
            return captchaId;
            
        } catch (error) {
            console.error('❌ Erro ao carregar CAPTCHA:', error);
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
        
        const timerId = sessionType === 'login' ? 'loginCaptchaTimer' : 'registerCaptchaTimer';
        const timerElement = document.getElementById(timerId);
        
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
                
                const inputId = sessionType === 'login' ? 'loginCaptchaInput' : 'registerCaptchaInput';
                const captchaInput = document.getElementById(inputId);
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
        
        const timerId = sessionType === 'login' ? 'loginCaptchaTimer' : 'registerCaptchaTimer';
        const timerElement = document.getElementById(timerId);
        if (timerElement) {
            timerElement.textContent = '02:00';
            timerElement.classList.remove('expiring', 'expired');
        }
        
        const inputId = sessionType === 'login' ? 'loginCaptchaInput' : 'registerCaptchaInput';
        const captchaInput = document.getElementById(inputId);
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
        const imageId = sessionType === 'login' ? 'loginCaptchaImg' : 'registerCaptchaImg';
        const captchaImage = document.getElementById(imageId);
        if (captchaImage) {
            captchaImage.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="350" height="125" viewBox="0 0 350 125"%3E%3Crect width="350" height="125" fill="%23e53e3e"/%3E%3Ctext x="175" y="68" font-family="monospace" font-size="16" fill="white" text-anchor="middle"%3E⚠️ ERRO%3C/text%3E%3C/svg%3E';
        }
    }
    
    // ==============================================
    // 🔥 LOGIN - POST /api/auth/login
    // ==============================================
    
    async handleLogin(e) {
        e.preventDefault();
        
        const emailInput = document.getElementById('loginEmail');
        const passwordInput = document.getElementById('loginPassword');
        const captchaInput = document.getElementById('loginCaptchaInput');
        const captchaIdInput = document.getElementById('loginCaptchaId');
        
        const email = emailInput?.value?.trim();
        const password = passwordInput?.value;
        const captchaCode = captchaInput?.value?.trim();
        const captchaId = captchaIdInput?.value || this.loginCaptchaId;
        
        // 🔍 LOG DETALHADO PARA DEBUG
        console.log('🔍 DETALHES DO LOGIN:');
        console.log('  📧 Email:', email);
        console.log('  🔑 CAPTCHA Code:', captchaCode);
        console.log('  🆔 CAPTCHA ID (input):', captchaIdInput?.value);
        console.log('  🆔 CAPTCHA ID (classe):', this.loginCaptchaId);
        console.log('  🆔 CAPTCHA ID (final):', captchaId);
        
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
            
            // 🔥 PAYLOAD CORRETO - Compatível com auth_routes.py (LoginRequest)
            const payload = {
                email: email,
                password: password,
                captcha_id: captchaId,  // ✅ CORRETO
                captcha_code: captchaCode,  // ✅ CORRETO - NÃO É captcha_input!
                session_type: 'login'
            };
            
            console.log('📦 PAYLOAD ENVIADO:', JSON.stringify(payload, null, 2));
            console.log('🔑 captcha_code:', payload.captcha_code);
            console.log('🆔 captcha_id:', payload.captcha_id);
            
            const response = await fetch(`${this.apiBase}/auth/login`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Captcha-ID': captchaId || ''
                },
                body: JSON.stringify(payload)
            });
            
            const data = await response.json();
            console.log('📥 RESPOSTA DO SERVIDOR:', data);
            
            // 🔥 Resposta compatível com auth_routes.py
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
                
                this.clearCaptchaTimer('login');
                if (passwordInput) passwordInput.value = '';
                if (captchaInput) captchaInput.value = '';
                
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
                // 🔥 TRATAMENTO DE ERRO MELHORADO
                let errorMsg = data.detail || data.message || 'Erro ao realizar login.';
                
                // Se for erro 422, mostra detalhes
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
                
                await this.refreshCaptcha('login');
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
    // 🔥 REGISTER - POST /api/auth/register
    // ==============================================
    
    async handleRegister(e) {
        e.preventDefault();
        
        const nameInput = document.getElementById('registerName');
        const emailInput = document.getElementById('registerEmail');
        const passwordInput = document.getElementById('registerPassword');
        const confirmPasswordInput = document.getElementById('registerConfirmPassword');
        const workshopInput = document.getElementById('registerWorkshop');
        const phoneInput = document.getElementById('registerPhone');
        const captchaInput = document.getElementById('registerCaptchaInput');
        const captchaIdInput = document.getElementById('registerCaptchaId');
        
        const name = nameInput?.value?.trim();
        const email = emailInput?.value?.trim();
        const password = passwordInput?.value;
        const confirmPassword = confirmPasswordInput?.value;
        const workshopName = workshopInput?.value?.trim();
        const phone = phoneInput?.value?.trim();
        const captchaCode = captchaInput?.value?.trim();
        const captchaId = captchaIdInput?.value || this.registerCaptchaId;
        
        console.log('📝 Tentando registrar:', { name, email, workshopName, phone, captchaId });
        
        // ==============================================
        // 🔥 VALIDAÇÕES
        // ==============================================
        
        // 1. Campos obrigatórios (name, email, password, workshop_name)
        if (!name || !email || !password || !workshopName) {
            if (window.toastr) {
                toastr.error('Preencha todos os campos obrigatórios.');
            }
            return;
        }
        
        // 2. Validação de telefone (opcional - compatível com auth.py)
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
        
        // 3. Senha (mínimo 6 caracteres - compatível com auth.py)
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
        
        // 5. CAPTCHA (compatível com auth.py)
        if (!captchaCode || captchaCode.length < 4) {
            if (window.toastr) {
                toastr.error('Digite os 4 números da imagem.');
            }
            return;
        }
        
        if (!captchaId) {
            if (window.toastr) {
                toastr.error('CAPTCHA não carregado. Clique em 🔄');
            }
            await this.refreshCaptcha('register');
            return;
        }
        
        // ==============================================
        // 🔥 ENVIAR REGISTRO - Compatível com auth.py
        // ==============================================
        
        const submitBtn = document.getElementById('registerBtn');
        const originalText = submitBtn?.innerHTML;
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i> Criando conta...';
        }
        
        try {
            console.log('🔄 Enviando requisição de registro...');
            
            // 🔥 PAYLOAD CORRETO - Compatível com auth.py (RegisterRequest)
            const requestBody = {
                name: name,
                email: email,
                password: password,
                workshop_name: workshopName,
                phone: phone || null,  // Opcional - compatível com auth.py
                captcha_id: captchaId,  // ✅ CORRETO
                captcha_code: captchaCode,  // ✅ CORRETO - NÃO É captcha_input!
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
            
            // 🔥 Resposta compatível com auth.py
            if (!response.ok) {
                let errorMsg = data.detail || data.message || 'Falha no registro';
                
                // Tratamento especial para erro 422
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
                await this.refreshCaptcha('register');
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
                if (captchaInput) captchaInput.value = '';
                
                // Redireciona para login (compatível com auth.py redirect_to)
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
        // Limpa timers anteriores
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
        
        // 🔥 VERIFICAÇÃO PERIÓDICA (a cada 60 segundos) - GET /api/auth/check-token
        this._tokenCheckInterval = setInterval(() => {
            this.checkTokenHealth();
        }, 60000);
        
        // 🔥 LIMPEZA AUTOMÁTICA APÓS 15 MINUTOS (conforme security.py)
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
        }, 15 * 60 * 1000); // 15 minutos em milissegundos
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
            
            // 🔥 GET /api/auth/check-token
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
            
            // 🔥 POST /api/auth/refresh
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
                
                // Reinicia o monitoramento
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
            this.loadCaptcha('login');
            
            const refreshBtn = document.getElementById('refreshLoginCaptcha');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', () => {
                    this.refreshCaptcha('login');
                });
            }
        } else {
            console.warn('⚠️ Formulário de login NÃO encontrado!');
        }
        
        // REGISTER FORM
        const registerForm = document.getElementById('registerForm');
        if (registerForm) {
            console.log('✅ Formulário de registro encontrado!');
            registerForm.addEventListener('submit', (e) => this.handleRegister(e));
            
            this.loadCaptcha('register');
            
            const refreshBtn = document.getElementById('refreshRegisterCaptcha');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', () => {
                    console.log('🔄 Atualizando CAPTCHA de registro...');
                    this.refreshCaptcha('register');
                });
            }
        } else {
            console.warn('⚠️ Formulário de registro NÃO encontrado!');
        }
        
        // TAB DE REGISTRO
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
            // 🔥 GET /api/auth/check-token
            const response = await fetch(`${this.apiBase}/auth/check-token`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            
            const data = await response.json();
            
            // 🔥 Resposta compatível com auth_routes.py (check-token)
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
                
                // 🔥 INICIA MONITORAMENTO DO TOKEN
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
                // 🔥 POST /api/auth/refresh
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
                
                // 🔥 Resposta compatível com auth_routes.py (refresh)
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
                    
                    // Reinicia o monitoramento
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