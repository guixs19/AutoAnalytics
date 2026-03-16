// frontend/js/auth.js - VERSÃO ATUALIZADA COM SUPORTE A ADMIN
// Sistema de autenticação com JWT e CAPTCHA próprio

const API_BASE = (function() {
    const isLocalhost = window.location.hostname === 'localhost' || 
                        window.location.hostname === '127.0.0.1';
    
    if (isLocalhost) {
        return 'http://localhost:8000/api';
    }
    return '/api';
})();

console.log('🌐 API Base URL:', API_BASE);

const CHECK_INTERVAL = 5 * 60 * 1000; // 5 minutos

// Armazenar CAPTCHA IDs
let loginCaptchaId = null;
let registerCaptchaId = null;
let loginCaptchaExpiration = null;
let registerCaptchaExpiration = null;
let loginTimerInterval = null;
let registerTimerInterval = null;

function buildUrl(endpoint) {
    if (!endpoint) return null;
    if (endpoint.startsWith('http')) return endpoint;
    
    const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    const base = API_BASE.endsWith('/') ? API_BASE.slice(0, -1) : API_BASE;
    
    return `${base}${cleanEndpoint}`;
}

// ==============================================
// FUNÇÕES DE ADMIN
// ==============================================

function isAdmin() {
    const user = getCurrentUser();
    return user?.is_admin === true;
}

function getCreditsDisplay() {
    const user = getCurrentUser();
    if (!user) return '0';
    if (user.is_admin) return '∞';
    return user.credits?.toString() || '0';
}

// ==============================================
// VALIDAÇÃO DE SESSÃO
// ==============================================

async function validarELimparSessao() {
    const token = localStorage.getItem('access_token');
    
    if (!token) {
        if (isProtectedPage()) window.location.href = '/login.html';
        return;
    }

    try {
        const url = buildUrl('/auth/check-token');
        if (!url) return;
        
        const response = await fetch(url, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });

        if (response.status === 401) {
            await clearSession();
            showMessage('⏰ Sessão expirada. Faça login novamente.', 'warning');
            if (window.location.pathname !== '/login.html') {
                setTimeout(() => window.location.href = '/login.html', 1500);
            }
        } else if (response.ok) {
            const data = await response.json();
            await updateUserData(data);
        }
    } catch (error) {
        console.error('❌ Erro ao validar sessão:', error);
    }
}

async function updateUserData(data) {
    try {
        const user = JSON.parse(localStorage.getItem('user') || '{}');
        if (data.name) user.name = data.name;
        if (data.user) user.email = data.user;
        if (data.credits !== undefined) user.credits = data.credits;
        if (data.is_admin !== undefined) user.is_admin = data.is_admin;  // ✅ ADICIONADO
        
        localStorage.setItem('user', JSON.stringify(user));
        
        // Atualizar elementos na UI se existirem
        updateCreditsDisplay();
    } catch (error) {
        console.error('Erro ao atualizar dados:', error);
    }
}

function updateCreditsDisplay() {
    // Atualizar elementos que mostram créditos na navbar
    const creditsElements = document.querySelectorAll('.credits-display');
    creditsElements.forEach(el => {
        el.textContent = getCreditsDisplay();
    });
    
    // Adicionar badge de admin se necessário
    if (isAdmin()) {
        document.body.classList.add('is-admin');
        const adminBadges = document.querySelectorAll('.admin-badge');
        adminBadges.forEach(el => {
            el.style.display = 'inline-block';
        });
    }
}

function isProtectedPage() {
    const protectedPaths = ['/dashboard', '/planos', '/checkout', '/admin'];
    return protectedPaths.some(path => window.location.pathname.startsWith(path));
}

function isAuthenticated() {
    return !!localStorage.getItem('access_token');
}

async function clearSession(showMessage_ = false) {
    const refreshToken = localStorage.getItem('refresh_token');
    
    if (refreshToken) {
        try {
            const url = buildUrl('/auth/logout');
            if (url) {
                await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ refresh_token: refreshToken })
                });
            }
        } catch (error) {
            console.error('Erro ao fazer logout:', error);
        }
    }
    
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
    
    if (showMessage_) showMessage('👋 Sessão encerrada.', 'info');
}

async function refreshAccessToken() {
    const refreshToken = localStorage.getItem('refresh_token');
    if (!refreshToken) return false;
    
    try {
        const url = buildUrl('/auth/refresh');
        if (!url) return false;
        
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: refreshToken })
        });
        
        if (response.ok) {
            const data = await response.json();
            localStorage.setItem('access_token', data.access_token);
            localStorage.setItem('refresh_token', data.refresh_token);
            return true;
        } else {
            await clearSession(true);
            return false;
        }
    } catch (error) {
        console.error('❌ Erro no refresh token:', error);
        return false;
    }
}

// ==============================================
// CAPTCHA PRÓPRIO
// ==============================================

async function loadCaptchaForTab(tab) {
    try {
        console.log(`🔄 Carregando CAPTCHA para ${tab}...`);
        
        const url = buildUrl('/auth/captcha/generate');
        if (!url) return null;
        
        const response = await fetch(url + `?t=${Date.now()}`);
        
        if (!response.ok) {
            console.error('❌ Erro ao carregar CAPTCHA:', response.status);
            return null;
        }
        
        // Pegar ID do header
        const captchaId = response.headers.get('X-Captcha-ID');
        
        // Converter para blob e criar URL
        const blob = await response.blob();
        const imageUrl = URL.createObjectURL(blob);
        
        // Atualizar elementos na tela
        if (tab === 'login') {
            const captchaImage = document.getElementById('loginCaptchaImage');
            const captchaInput = document.getElementById('loginCaptchaInput');
            const timerElement = document.getElementById('loginCaptchaTimer');
            
            if (captchaImage) {
                // Limpar URL antiga
                if (captchaImage.dataset.url) {
                    URL.revokeObjectURL(captchaImage.dataset.url);
                }
                
                captchaImage.src = imageUrl;
                captchaImage.dataset.url = imageUrl;
                captchaImage.dataset.captchaId = captchaId;
                
                // Armazenar ID global
                loginCaptchaId = captchaId;
                
                // Limpar input
                if (captchaInput) captchaInput.value = '';
                
                // Configurar timer de 2 minutos
                loginCaptchaExpiration = Date.now() + 2 * 60 * 1000;
                
                if (loginTimerInterval) clearInterval(loginTimerInterval);
                loginTimerInterval = setInterval(() => {
                    updateCaptchaTimer('login', timerElement);
                }, 1000);
                
                console.log('✅ CAPTCHA login carregado:', captchaId);
            }
        } else {
            const captchaImage = document.getElementById('registerCaptchaImage');
            const captchaInput = document.getElementById('registerCaptchaInput');
            const timerElement = document.getElementById('registerCaptchaTimer');
            
            if (captchaImage) {
                // Limpar URL antiga
                if (captchaImage.dataset.url) {
                    URL.revokeObjectURL(captchaImage.dataset.url);
                }
                
                captchaImage.src = imageUrl;
                captchaImage.dataset.url = imageUrl;
                captchaImage.dataset.captchaId = captchaId;
                
                // Armazenar ID global
                registerCaptchaId = captchaId;
                
                // Limpar input
                if (captchaInput) captchaInput.value = '';
                
                // Configurar timer de 2 minutos
                registerCaptchaExpiration = Date.now() + 2 * 60 * 1000;
                
                if (registerTimerInterval) clearInterval(registerTimerInterval);
                registerTimerInterval = setInterval(() => {
                    updateCaptchaTimer('register', timerElement);
                }, 1000);
                
                console.log('✅ CAPTCHA registro carregado:', captchaId);
            }
        }
        
        return captchaId;
    } catch (error) {
        console.error('❌ Erro ao carregar CAPTCHA:', error);
        return null;
    }
}

function updateCaptchaTimer(tab, timerElement) {
    if (!timerElement) return;
    
    const expiration = tab === 'login' ? loginCaptchaExpiration : registerCaptchaExpiration;
    
    if (!expiration) {
        timerElement.textContent = '2:00';
        return;
    }
    
    const now = Date.now();
    const remaining = Math.max(0, Math.floor((expiration - now) / 1000));
    
    if (remaining <= 0) {
        // CAPTCHA expirou
        timerElement.textContent = 'Expirado';
        timerElement.style.color = '#e53e3e';
        
        // Limpar ID
        if (tab === 'login') {
            loginCaptchaId = null;
            if (loginTimerInterval) clearInterval(loginTimerInterval);
        } else {
            registerCaptchaId = null;
            if (registerTimerInterval) clearInterval(registerTimerInterval);
        }
        return;
    }
    
    const minutes = Math.floor(remaining / 60);
    const seconds = remaining % 60;
    timerElement.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;
    timerElement.style.color = remaining < 30 ? '#e53e3e' : '#667eea';
}

function refreshCaptcha(tab) {
    console.log(`🔄 Atualizando CAPTCHA ${tab}...`);
    loadCaptchaForTab(tab);
}

// ==============================================
// LOGIN ATUALIZADO
// ==============================================

async function login(email, password) {
    try {
        showLoading('loginForm');
        
        // 🔥 VALIDAÇÕES
        if (!email) {
            showMessage('📧 Digite seu e-mail', 'warning');
            hideLoading('loginForm');
            document.getElementById('loginEmail')?.focus();
            return;
        }
        
        if (!email.includes('@') || !email.includes('.')) {
            showMessage('📧 Digite um e-mail válido (ex: nome@email.com)', 'warning');
            hideLoading('loginForm');
            document.getElementById('loginEmail')?.focus();
            return;
        }
        
        if (!password) {
            showMessage('🔒 Digite sua senha', 'warning');
            hideLoading('loginForm');
            document.getElementById('loginPassword')?.focus();
            return;
        }
        
        // PEGAR CAPTCHA
        const captchaImage = document.getElementById('loginCaptchaImage');
        const captchaInput = document.getElementById('loginCaptchaInput');
        
        if (!captchaImage || !captchaImage.dataset.captchaId) {
            showMessage('🔄 CAPTCHA não carregado. Clique no botão de atualizar ao lado da imagem', 'warning');
            hideLoading('loginForm');
            await loadCaptchaForTab('login');
            return;
        }
        
        const captchaText = captchaInput ? captchaInput.value : '';
        
        if (!captchaText) {
            showMessage('🔢 Digite os números que aparecem na imagem CAPTCHA', 'warning');
            hideLoading('loginForm');
            document.getElementById('loginCaptchaInput')?.focus();
            return;
        }
        
        if (captchaText.length !== 6 || !/^\d+$/.test(captchaText)) {
            showMessage('🔢 O CAPTCHA deve conter exatamente 6 números', 'warning');
            hideLoading('loginForm');
            document.getElementById('loginCaptchaInput')?.focus();
            return;
        }
        
        const captchaId = captchaImage.dataset.captchaId;
        
        const loginData = {
            email: email.trim().toLowerCase(),
            password: password,
            captcha_text: captchaText
        };
        
        const url = buildUrl('/auth/login');
        if (!url) {
            hideLoading('loginForm');
            return;
        }
        
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Captcha-ID': captchaId
            },
            body: JSON.stringify(loginData)
        });
        
        hideLoading('loginForm');
        
        if (response.ok) {
            const data = await response.json();
            
            localStorage.setItem('access_token', data.access_token);
            localStorage.setItem('refresh_token', data.refresh_token);
            
            // ✅ ARMAZENAR IS_ADMIN
            const userData = {
                name: data.user_name || '',
                email: data.user_email || email,
                workshop: data.workshop_name || '',
                role: data.role || 'user',
                plan: data.plan || 'basico',
                credits: data.credits || 0,
                is_admin: data.is_admin || false  // ✅ ADICIONADO
            };
            localStorage.setItem('user', JSON.stringify(userData));
            
            const adminMsg = userData.is_admin ? '👑 ' : '';
            showMessage(`${adminMsg}Login realizado com sucesso! Redirecionando...`, 'success');
            
            if (loginTimerInterval) clearInterval(loginTimerInterval);
            
            setTimeout(() => window.location.href = '/dashboard', 1000);
        } else {
            let errorMessage = 'Erro no login';
            try {
                const error = await response.json();
                errorMessage = error.detail || error.message || errorMessage;
                
                if (errorMessage.includes('CAPTCHA')) {
                    errorMessage = '🔢 CAPTCHA inválido ou expirado. Tente novamente.';
                    await loadCaptchaForTab('login');
                } else if (errorMessage.includes('Email ou senha incorretos')) {
                    errorMessage = '📧🔒 E-mail ou senha incorretos. Verifique e tente novamente.';
                } else if (errorMessage.includes('Conta desativada')) {
                    errorMessage = '🚫 Sua conta foi desativada. Entre em contato com o suporte.';
                }
            } catch {
                errorMessage = `❌ Erro ${response.status} no servidor`;
            }
            showMessage(errorMessage, 'error');
        }
    } catch (error) {
        hideLoading('loginForm');
        console.error('❌ Erro no login:', error);
        showMessage('❌ Erro de conexão com o servidor. Verifique sua internet.', 'error');
    }
}

// ==============================================
// REGISTRO
// ==============================================

async function register(userData) {
    try {
        showLoading('registerForm');
        
        // 🔥 VALIDAÇÕES
        if (!userData.name || userData.name.trim().length < 3) {
            showMessage('👤 Por favor, digite seu nome completo (mínimo 3 caracteres)', 'warning');
            hideLoading('registerForm');
            document.getElementById('regName')?.focus();
            return;
        }
        
        if (!userData.email) {
            showMessage('📧 Digite seu e-mail', 'warning');
            hideLoading('registerForm');
            document.getElementById('regEmail')?.focus();
            return;
        }
        
        if (!userData.email.includes('@') || !userData.email.includes('.')) {
            showMessage('📧 Digite um e-mail válido (ex: nome@email.com)', 'warning');
            hideLoading('registerForm');
            document.getElementById('regEmail')?.focus();
            return;
        }
        
        if (!userData.password) {
            showMessage('🔒 Digite sua senha', 'warning');
            hideLoading('registerForm');
            document.getElementById('regPassword')?.focus();
            return;
        }
        
        if (userData.password.length < 6) {
            showMessage('🔒 A senha deve ter pelo menos 6 caracteres', 'warning');
            hideLoading('registerForm');
            document.getElementById('regPassword')?.focus();
            return;
        }
        
        const confirmPassword = document.getElementById('regConfirmPassword')?.value;
        if (userData.password !== confirmPassword) {
            showMessage('🔒 As senhas não coincidem. Digite a mesma senha nos dois campos', 'error');
            hideLoading('registerForm');
            document.getElementById('regConfirmPassword')?.focus();
            return;
        }
        
        // Workshop é opcional
        const termsChecked = document.getElementById('terms')?.checked;
        if (!termsChecked) {
            showMessage('📝 Você precisa aceitar os Termos de Uso para continuar', 'warning');
            hideLoading('registerForm');
            return;
        }
        
        // PEGAR CAPTCHA
        const captchaImage = document.getElementById('registerCaptchaImage');
        const captchaInput = document.getElementById('registerCaptchaInput');
        
        if (!captchaImage || !captchaImage.dataset.captchaId) {
            showMessage('🔄 CAPTCHA não carregado. Clique no botão de atualizar ao lado da imagem', 'warning');
            hideLoading('registerForm');
            await loadCaptchaForTab('register');
            return;
        }
        
        const captchaText = captchaInput ? captchaInput.value : '';
        
        if (!captchaText) {
            showMessage('🔢 Digite os números que aparecem na imagem CAPTCHA', 'warning');
            hideLoading('registerForm');
            document.getElementById('registerCaptchaInput')?.focus();
            return;
        }
        
        if (captchaText.length !== 6 || !/^\d+$/.test(captchaText)) {
            showMessage('🔢 O CAPTCHA deve conter exatamente 6 números', 'warning');
            hideLoading('registerForm');
            document.getElementById('registerCaptchaInput')?.focus();
            return;
        }
        
        const captchaId = captchaImage.dataset.captchaId;
        
        const registerData = {
            name: userData.name.trim(),
            email: userData.email.trim().toLowerCase(),
            password: userData.password,
            workshop_name: userData.workshop_name?.trim() || null,
            captcha_text: captchaText
        };
        
        const url = buildUrl('/auth/register');
        if (!url) {
            hideLoading('registerForm');
            return;
        }
        
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Captcha-ID': captchaId
            },
            body: JSON.stringify(registerData)
        });
        
        hideLoading('registerForm');
        
        if (response.ok) {
            showMessage('✅ Conta criada com sucesso! Agora faça login.', 'success');
            document.getElementById('registerForm')?.reset();
            
            if (registerTimerInterval) clearInterval(registerTimerInterval);
            
            setTimeout(() => {
                document.getElementById('login-tab')?.click();
                loadCaptchaForTab('login');
            }, 1500);
        } else {
            let errorMessage = 'Erro no registro';
            try {
                const error = await response.json();
                errorMessage = error.detail || error.message || errorMessage;
                
                if (errorMessage.includes('CAPTCHA')) {
                    errorMessage = '🔢 CAPTCHA inválido ou expirado. Tente novamente.';
                    await loadCaptchaForTab('register');
                } else if (errorMessage.includes('Email já cadastrado')) {
                    errorMessage = '📧 Este e-mail já está cadastrado. Faça login ou use outro e-mail.';
                } else if (errorMessage.includes('Nome deve ter')) {
                    errorMessage = '👤 ' + errorMessage;
                } else if (errorMessage.includes('Senha deve ter')) {
                    errorMessage = '🔒 ' + errorMessage;
                }
            } catch {
                errorMessage = `❌ Erro ${response.status} no servidor`;
            }
            showMessage(errorMessage, 'error');
        }
    } catch (error) {
        hideLoading('registerForm');
        console.error('❌ Erro no registro:', error);
        showMessage('❌ Erro de conexão com o servidor. Verifique sua internet.', 'error');
    }
}

// ==============================================
// LOGOUT
// ==============================================

async function logout() {
    if (confirm('Deseja realmente sair?')) {
        await clearSession(true);
        window.location.href = '/login.html';
    }
}

// ==============================================
// UTILITÁRIOS
// ==============================================

function showLoading(formId) {
    const btn = document.querySelector(`#${formId} button[type="submit"]`);
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Processando...';
    }
}

function hideLoading(formId) {
    const btn = document.querySelector(`#${formId} button[type="submit"]`);
    if (btn) {
        btn.disabled = false;
        btn.innerHTML = formId === 'loginForm' 
            ? '<i class="fas fa-sign-in-alt me-2"></i>Entrar'
            : '<i class="fas fa-user-plus me-2"></i>Criar Conta';
    }
}

function showMessage(message, type = 'info') {
    const messageDiv = document.getElementById('authMessage');
    if (!messageDiv) return;
    
    const alertClass = type === 'success' ? 'alert-success' 
        : type === 'error' ? 'alert-danger' 
        : type === 'warning' ? 'alert-warning' 
        : 'alert-info';
    
    const icon = type === 'success' ? 'check-circle' 
        : type === 'error' ? 'exclamation-circle' 
        : type === 'warning' ? 'exclamation-triangle' 
        : 'info-circle';
    
    messageDiv.innerHTML = `
        <div class="alert ${alertClass} alert-dismissible fade show" role="alert">
            <i class="fas fa-${icon} me-2"></i>
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    
    // Auto-dismiss após 5 segundos
    setTimeout(() => {
        const alert = messageDiv.querySelector('.alert');
        if (alert) {
            alert.classList.remove('show');
            setTimeout(() => {
                if (messageDiv.innerHTML.includes(alert.outerHTML)) {
                    messageDiv.innerHTML = '';
                }
            }, 300);
        }
    }, 5000);
}

// ==============================================
// SETUP DOS FORMULÁRIOS
// ==============================================

function setupForms() {
    const loginForm = document.getElementById('loginForm');
    if (loginForm) {
        loginForm.addEventListener('submit', (e) => {
            e.preventDefault();
            login(
                document.getElementById('loginEmail').value,
                document.getElementById('loginPassword').value
            );
        });
    }
    
    const registerForm = document.getElementById('registerForm');
    if (registerForm) {
        registerForm.addEventListener('submit', (e) => {
            e.preventDefault();
            register({
                name: document.getElementById('regName').value,
                email: document.getElementById('regEmail').value,
                password: document.getElementById('regPassword').value,
                workshop_name: document.getElementById('regWorkshop')?.value
            });
        });
    }
    
    // Botões de refresh do CAPTCHA
    document.getElementById('refreshLoginCaptcha')?.addEventListener('click', (e) => {
        e.preventDefault();
        refreshCaptcha('login');
    });
    
    document.getElementById('refreshRegisterCaptcha')?.addEventListener('click', (e) => {
        e.preventDefault();
        refreshCaptcha('register');
    });
    
    // Quando mudar de aba, carregar CAPTCHA correspondente
    document.querySelectorAll('button[data-bs-toggle="tab"]').forEach(button => {
        button.addEventListener('shown.bs.tab', (event) => {
            const targetId = event.target.getAttribute('data-bs-target');
            if (targetId === '#login') {
                loadCaptchaForTab('login');
            } else if (targetId === '#register') {
                loadCaptchaForTab('register');
            }
        });
    });
}

// ==============================================
// INICIALIZAÇÃO
// ==============================================

document.addEventListener('DOMContentLoaded', async () => {
    console.log('🚀 Auth.js inicializado (CAPTCHA próprio)');
    
    // SÓ validar sessão se NÃO estiver na página de login
    if (window.location.pathname !== '/login.html') {
        await validarELimparSessao();
        setInterval(validarELimparSessao, CHECK_INTERVAL);
        
        // Atualizar display de créditos na navbar
        updateCreditsDisplay();
    }
    
    // Redirecionar se já estiver logado
    if (window.location.pathname === '/login.html' && isAuthenticated()) {
        console.log('👤 Usuário já logado, redirecionando para dashboard');
        window.location.href = '/dashboard';
        return;
    }
    
    // Proteger páginas
    if (isProtectedPage() && !isAuthenticated()) {
        console.log('🔒 Página protegida, redirecionando para login');
        window.location.href = '/login.html';
        return;
    }
    
    // Carregar CAPTCHA se estiver na página de login
    if (window.location.pathname === '/login.html') {
        console.log('🖼️ Página de login detectada, carregando CAPTCHA...');
        setTimeout(() => {
            loadCaptchaForTab('login');
        }, 200);
    }
    
    setupForms();
});

// ==============================================
// EXPORTAÇÕES
// ==============================================

window.app = {
    login,
    register,
    logout,
    isAuthenticated,
    isAdmin,  // ✅ NOVA FUNÇÃO
    getCreditsDisplay,  // ✅ NOVA FUNÇÃO
    refreshCaptcha,
    getCurrentUser: () => {
        try {
            return JSON.parse(localStorage.getItem('user') || 'null');
        } catch {
            return null;
        }
    },
    getToken: () => localStorage.getItem('access_token')
};

console.log('✅ Auth.js carregado com suporte a admin');