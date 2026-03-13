// frontend/js/auth.js - VERSÃO COMPLETA COM TODAS AS FUNCIONALIDADES
// Sistema de autenticação com JWT, refresh token, validação automática e CAPTCHA

// ==============================================
// CONFIGURAÇÕES
// ==============================================

const API_BASE = '/api';
const CHECK_INTERVAL = 5 * 60 * 1000; // 5 minutos em millisegundos

// ==============================================
// VARIÁVEIS GLOBAIS
// ==============================================

let captchaId = null;
let captchaType = 'disabled';
let captchaSiteKey = null;

// ==============================================
// VALIDAÇÃO E LIMPEZA INTELIGENTE DE SESSÃO
// ==============================================

/**
 * Valida se o token atual ainda é válido e limpa se necessário
 */
async function validarELimparSessao() {
    const token = localStorage.getItem('access_token');
    
    if (!token) {
        console.log('ℹ️ Sem token para validar');
        
        if (isProtectedPage()) {
            console.log('🔒 Página protegida sem token, redirecionando...');
            window.location.href = '/login';
        }
        return;
    }

    try {
        console.log('🔍 Validando token existente...');
        
        const response = await fetch(`${API_BASE}/auth/check-token`, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });

        if (response.status === 401) {
            console.warn('⚠️ Sessão expirada. A limpar lixo...');
            await clearSession();
            showMessage('Sessão expirada. Faça login novamente.', 'warning');
            
            if (window.location.pathname !== '/login') {
                setTimeout(() => {
                    window.location.href = '/login';
                }, 1500);
            }
            
        } else if (response.ok) {
            const data = await response.json();
            console.log('✅ Token válido para:', data.user);
            updateUserData(data);
        }
    } catch (error) {
        console.error('❌ Erro ao conectar ao servidor:', error);
    }
}

/**
 * Atualiza dados do usuário no localStorage
 */
function updateUserData(data) {
    try {
        const user = JSON.parse(localStorage.getItem('user') || '{}');
        
        if (data.name) user.name = data.name;
        if (data.email) user.email = data.email;
        if (data.credits !== undefined) user.credits = data.credits;
        if (data.plan) user.plan = data.plan;
        if (data.role) user.role = data.role;
        
        localStorage.setItem('user', JSON.stringify(user));
    } catch (error) {
        console.error('Erro ao atualizar dados do usuário:', error);
    }
}

// ==============================================
// VERIFICAÇÃO DE PÁGINAS
// ==============================================

function isProtectedPage() {
    const protectedPaths = ['/dashboard', '/planos', '/checkout', '/admin', '/profile', '/configuracoes'];
    const currentPath = window.location.pathname;
    return protectedPaths.some(path => currentPath.startsWith(path));
}

function isPublicPage() {
    const publicPaths = ['/login', '/register', '/recuperar-senha', '/', '/sobre', '/termos', '/privacidade'];
    const currentPath = window.location.pathname;
    return publicPaths.some(path => currentPath === path);
}

function isAuthenticated() {
    return !!localStorage.getItem('access_token');
}

// ==============================================
// GERENCIAMENTO DE SESSÃO
// ==============================================

async function clearSession(showMessage_ = false) {
    console.log('🧹 Limpando sessão...');
    
    const refreshToken = localStorage.getItem('refresh_token');
    
    if (refreshToken) {
        try {
            await fetch(`${API_BASE}/auth/logout`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: refreshToken })
            });
        } catch (error) {
            console.error('Erro ao fazer logout no backend:', error);
        }
    }
    
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
    
    if (showMessage_) {
        showMessage('Sessão encerrada.', 'info');
    }
}

function requireAuth() {
    if (!isAuthenticated()) {
        window.location.href = '/login';
        return false;
    }
    return true;
}

function redirectIfAuthenticated() {
    if (isAuthenticated()) {
        window.location.href = '/dashboard';
        return true;
    }
    return false;
}

// ==============================================
// REFRESH TOKEN AUTOMÁTICO
// ==============================================

async function refreshAccessToken() {
    const refreshToken = localStorage.getItem('refresh_token');
    
    if (!refreshToken) {
        console.log('ℹ️ Sem refresh token disponível');
        return false;
    }
    
    try {
        console.log('🔄 Tentando renovar token...');
        
        const response = await fetch(`${API_BASE}/auth/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: refreshToken })
        });
        
        if (response.ok) {
            const data = await response.json();
            localStorage.setItem('access_token', data.access_token);
            localStorage.setItem('refresh_token', data.refresh_token);
            console.log('✅ Token renovado com sucesso');
            return true;
        } else {
            console.warn('⚠️ Refresh token inválido, limpando sessão');
            await clearSession(true);
            return false;
        }
    } catch (error) {
        console.error('❌ Erro no refresh token:', error);
        return false;
    }
}

// ==============================================
// API REQUEST COM RETRY AUTOMÁTICO
// ==============================================

async function apiRequest(endpoint, options = {}) {
    const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;
    
    for (let attempt = 0; attempt < 2; attempt++) {
        const token = localStorage.getItem('access_token');
        
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers
        };
        
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        
        try {
            const response = await fetch(url, { ...options, headers });
            
            if (response.status === 401) {
                console.log('🔄 Token expirado, tentando refresh...');
                const refreshed = await refreshAccessToken();
                
                if (refreshed) {
                    console.log('🔄 Tentando requisição novamente...');
                    continue;
                } else {
                    console.warn('⚠️ Refresh falhou, redirecionando para login');
                    await clearSession();
                    
                    if (!isPublicPage()) {
                        window.location.href = '/login';
                    }
                    
                    throw new Error('Sessão expirada');
                }
            }
            
            return response;
            
        } catch (error) {
            if (attempt === 1) throw error;
            console.warn(`⚠️ Tentativa ${attempt + 1} falhou, tentando novamente...`);
            await new Promise(resolve => setTimeout(resolve, 1000));
        }
    }
}

// ==============================================
// CAPTCHA - FUNÇÕES CORRIGIDAS
// ==============================================

async function loadCaptcha() {
    try {
        console.log('🔄 Carregando CAPTCHA...');
        
        const response = await fetch(`${API_BASE}/auth/captcha/generate`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('✅ CAPTCHA carregado:', data);
        
        captchaType = data.type || 'custom';
        
        if (data.type === 'recaptcha_v2') {
            captchaSiteKey = data.site_key;
            loadRecaptchaV2(data.site_key);
            
        } else if (data.type === 'recaptcha_v3') {
            captchaSiteKey = data.site_key;
            console.log('ℹ️ reCAPTCHA v3 configurado');
            
        } else {
            captchaId = data.captcha_id;
            displayCustomCaptcha(data);
        }
        
        return data;
        
    } catch (error) {
        console.error('❌ Erro ao carregar CAPTCHA:', error);
        captchaType = 'disabled';
        return null;
    }
}

function displayCustomCaptcha(data) {
    const container = document.getElementById('captcha-container');
    if (!container) {
        console.warn('⚠️ Container do CAPTCHA não encontrado');
        return;
    }
    
    captchaId = data.captcha_id;
    
    container.innerHTML = `
        <div class="mb-3">
            <label class="form-label small fw-bold">CAPTCHA</label>
            <div class="d-flex align-items-center gap-2">
                <img src="${data.image}" alt="CAPTCHA" class="img-fluid border rounded" 
                     style="max-width: 150px; height: 50px; object-fit: cover;">
                <i class="fas fa-sync-alt text-primary" style="cursor: pointer;" 
                   onclick="window.app.reloadCaptcha()" title="Recarregar CAPTCHA"></i>
            </div>
            <input type="text" class="form-control mt-2" id="captcha-input" 
                   placeholder="Digite o resultado" required>
            <small class="text-muted">Digite o resultado da operação matemática</small>
        </div>
    `;
    
    console.log('✅ CAPTCHA customizado exibido, ID:', captchaId);
}

async function reloadCaptcha() {
    await loadCaptcha();
}

function getCaptchaData() {
    if (captchaType === 'recaptcha_v3') {
        return new Promise((resolve) => {
            if (window.grecaptcha && captchaSiteKey) {
                window.grecaptcha.ready(function() {
                    window.grecaptcha.execute(captchaSiteKey, {action: 'register'})
                        .then(token => {
                            resolve({
                                captcha_type: 'recaptcha_v3',
                                captcha_token: token
                            });
                        })
                        .catch(() => resolve(null));
                });
            } else {
                resolve(null);
            }
        });
    }
    
    if (captchaType === 'recaptcha_v2') {
        const token = document.getElementById('g-recaptcha-response')?.value;
        if (!token) {
            console.warn('⚠️ reCAPTCHA v2 não preenchido');
            return null;
        }
        return {
            captcha_type: 'recaptcha_v2',
            captcha_token: token
        };
    }
    
    if (captchaType === 'custom') {
        const input = document.getElementById('captcha-input');
        if (!input || !input.value) {
            console.warn('⚠️ CAPTCHA não preenchido');
            return null;
        }
        
        return {
            captcha_type: 'custom',
            captcha_id: captchaId,
            captcha_text: input.value.trim()
        };
    }
    
    return null;
}

function loadRecaptchaV2(siteKey) {
    const container = document.getElementById('captcha-container');
    if (!container) return;
    
    container.innerHTML = '';
    
    const recaptchaDiv = document.createElement('div');
    recaptchaDiv.id = 'recaptcha-element';
    container.appendChild(recaptchaDiv);
    
    if (!document.getElementById('recaptcha-script')) {
        const script = document.createElement('script');
        script.id = 'recaptcha-script';
        script.src = 'https://www.google.com/recaptcha/api.js';
        script.async = true;
        script.defer = true;
        script.onload = () => {
            if (window.grecaptcha) {
                window.grecaptcha.render('recaptcha-element', {
                    'sitekey': siteKey,
                    'theme': 'light'
                });
            }
        };
        document.head.appendChild(script);
    } else if (window.grecaptcha) {
        window.grecaptcha.render('recaptcha-element', {
            'sitekey': siteKey,
            'theme': 'light'
        });
    }
}

async function executeRecaptchaV3(action = 'login') {
    return new Promise((resolve) => {
        if (window.grecaptcha && captchaSiteKey) {
            window.grecaptcha.ready(function() {
                window.grecaptcha.execute(captchaSiteKey, {action: action})
                    .then(resolve)
                    .catch(() => resolve(''));
            });
        } else {
            resolve('');
        }
    });
}

// ==============================================
// AUTENTICAÇÃO - FUNÇÕES CORRIGIDAS
// ==============================================

async function login(email, password) {
    try {
        showLoading('login');
        
        const loginData = {
            email: email,
            password: password
        };
        
        const captchaData = getCaptchaData();
        if (captchaData) {
            if (captchaData.captcha_type === 'custom') {
                loginData.captcha_id = captchaData.captcha_id;
                loginData.captcha_text = captchaData.captcha_text;
            } else {
                window.captchaToken = captchaData.captcha_token;
            }
        }
        
        const response = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Captcha-Token': window.captchaToken || ''
            },
            body: JSON.stringify(loginData)
        });
        
        hideLoading('login');
        
        if (response.ok) {
            const data = await response.json();
            
            localStorage.setItem('access_token', data.access_token);
            localStorage.setItem('refresh_token', data.refresh_token);
            
            const userData = {
                name: data.user_name,
                email: data.user_email,
                workshop: data.workshop_name,
                role: data.role,
                plan: data.plan,
                credits: data.credits
            };
            localStorage.setItem('user', JSON.stringify(userData));
            
            showMessage('Login realizado com sucesso!', 'success');
            
            setTimeout(() => {
                window.location.href = '/dashboard';
            }, 1000);
        } else {
            const error = await response.json();
            showMessage(error.detail || 'Erro no login', 'error');
            await loadCaptcha();
        }
    } catch (error) {
        hideLoading('login');
        console.error('❌ Erro no login:', error);
        showMessage('Erro de conexão com o servidor', 'error');
    }
}

/**
 * 🔥 FUNÇÃO DE REGISTRO CORRIGIDA - Agora envia CAPTCHA corretamente
 */
async function register(userData) {
    try {
        showLoading('register');
        
        const registerData = {
            name: userData.name,
            email: userData.email,
            password: userData.password,
            workshop_name: userData.workshop_name || ''
        };
        
        // 🔥 OBTER DADOS DO CAPTCHA
        const captchaData = getCaptchaData();
        
        // Se for CAPTCHA customizado, adicionar campos no body
        if (captchaData && captchaData.captcha_type === 'custom') {
            registerData.captcha_id = captchaData.captcha_id;
            registerData.captcha_text = captchaData.captcha_text;
            console.log('📤 Enviando CAPTCHA customizado:', {
                id: captchaData.captcha_id,
                text: captchaData.captcha_text
            });
        }
        
        // Preparar headers
        const headers = {
            'Content-Type': 'application/json'
        };
        
        // Se for reCAPTCHA, adicionar token no header
        if (captchaData && captchaData.captcha_type?.startsWith('recaptcha')) {
            headers['X-Captcha-Token'] = captchaData.captcha_token;
            console.log('📤 Enviando reCAPTCHA token');
        }
        
        console.log('📤 Enviando registro:', {
            url: `${API_BASE}/auth/register`,
            data: { ...registerData, password: '***' }
        });
        
        const response = await fetch(`${API_BASE}/auth/register`, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(registerData)
        });
        
        hideLoading('register');
        
        if (response.ok) {
            const data = await response.json();
            showMessage('Conta criada com sucesso! Faça login.', 'success');
            
            document.getElementById('registerForm')?.reset();
            
            setTimeout(() => {
                document.getElementById('login-tab')?.click();
            }, 1500);
        } else {
            const error = await response.json();
            console.error('❌ Erro no registro:', error);
            showMessage(error.detail || 'Erro no registro', 'error');
            
            // 🔥 RECARREGAR CAPTCHA em caso de erro
            await loadCaptcha();
        }
    } catch (error) {
        hideLoading('register');
        console.error('❌ Erro no registro:', error);
        showMessage('Erro de conexão com o servidor', 'error');
    }
}

async function logout() {
    await clearSession(true);
    window.location.href = '/login';
}

// ==============================================
// UTILITÁRIOS DE UI
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
    
    setTimeout(() => {
        messageDiv.innerHTML = '';
    }, 5000);
}

// ==============================================
// CONFIGURAÇÃO DE FORMULÁRIOS
// ==============================================

function setupForms() {
    const loginForm = document.getElementById('loginForm');
    if (loginForm) {
        loginForm.addEventListener('submit', function(e) {
            e.preventDefault();
            const email = document.getElementById('loginEmail').value;
            const password = document.getElementById('loginPassword').value;
            login(email, password);
        });
    }
    
    const registerForm = document.getElementById('registerForm');
    if (registerForm) {
        registerForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const password = document.getElementById('regPassword').value;
            const confirmPassword = document.getElementById('regConfirmPassword').value;
            
            if (password !== confirmPassword) {
                showMessage('As senhas não coincidem', 'error');
                return;
            }
            
            const userData = {
                name: document.getElementById('regName').value,
                email: document.getElementById('regEmail').value,
                password: password,
                workshop_name: document.getElementById('regWorkshop')?.value || ''
            };
            
            register(userData);
        });
    }
}

// ==============================================
// INICIALIZAÇÃO
// ==============================================

document.addEventListener('DOMContentLoaded', async function() {
    console.log('🚀 Auth.js inicializado');
    
    await validarELimparSessao();
    
    setInterval(validarELimparSessao, CHECK_INTERVAL);
    window.addEventListener('focus', validarELimparSessao);
    
    if (window.location.pathname === '/login' && isAuthenticated()) {
        window.location.href = '/dashboard';
        return;
    }
    
    if (isProtectedPage() && !isAuthenticated()) {
        window.location.href = '/login';
        return;
    }
    
    if (window.location.pathname === '/login') {
        await loadCaptcha();
    }
    
    setupForms();
});

// ==============================================
// EXPORTAÇÕES PARA USO GLOBAL
// ==============================================

window.app = {
    login,
    register,
    logout,
    apiRequest,
    isAuthenticated,
    validateSession: validarELimparSessao,
    reloadCaptcha: loadCaptcha,
    getCurrentUser: () => {
        try {
            const user = localStorage.getItem('user');
            return user ? JSON.parse(user) : null;
        } catch {
            return null;
        }
    },
    getToken: () => localStorage.getItem('access_token'),
    getRefreshToken: () => localStorage.getItem('refresh_token')
};

console.log('✅ Auth.js carregado com sucesso');