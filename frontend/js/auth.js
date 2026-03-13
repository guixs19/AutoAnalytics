// frontend/js/auth.js - VERSÃO SIMPLIFICADA
// Sistema de autenticação com JWT e reCAPTCHA

const API_BASE = (function() {
    const isLocalhost = window.location.hostname === 'localhost' || 
                        window.location.hostname === '127.0.0.1';
    
    if (isLocalhost) {
        return 'http://localhost:8000/api';
    }
    return '/api';
})();

console.log('🌐 API Base URL:', API_BASE);

const CHECK_INTERVAL = 5 * 60 * 1000;

let siteKey = null;
let recaptchaReady = false;

function buildUrl(endpoint) {
    if (!endpoint) return null;
    if (endpoint.startsWith('http')) return endpoint;
    
    const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    const base = API_BASE.endsWith('/') ? API_BASE.slice(0, -1) : API_BASE;
    
    return `${base}${cleanEndpoint}`;
}

// ==============================================
// VALIDAÇÃO DE SESSÃO
// ==============================================

async function validarELimparSessao() {
    const token = localStorage.getItem('access_token');
    
    if (!token) {
        if (isProtectedPage()) window.location.href = '/login';
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
            showMessage('Sessão expirada. Faça login novamente.', 'warning');
            if (window.location.pathname !== '/login') {
                setTimeout(() => window.location.href = '/login', 1500);
            }
        } else if (response.ok) {
            const data = await response.json();
            updateUserData(data);
        }
    } catch (error) {
        console.error('❌ Erro ao validar sessão:', error);
    }
}

function updateUserData(data) {
    try {
        const user = JSON.parse(localStorage.getItem('user') || '{}');
        if (data.name) user.name = data.name;
        if (data.email) user.email = data.email;
        if (data.credits !== undefined) user.credits = data.credits;
        localStorage.setItem('user', JSON.stringify(user));
    } catch (error) {
        console.error('Erro ao atualizar dados:', error);
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
    
    if (showMessage_) showMessage('Sessão encerrada.', 'info');
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
// reCAPTCHA
// ==============================================

async function loadCaptchaConfig() {
    try {
        console.log('🔄 Carregando configuração do reCAPTCHA...');
        
        const url = buildUrl('/auth/captcha/generate');
        if (!url) return null;
        
        const response = await fetch(url + `?t=${Date.now()}`);
        if (!response.ok) return null;
        
        const data = await response.json();
        console.log('✅ Configuração reCAPTCHA:', data);
        
        if (data.site_key) {
            siteKey = data.site_key;
            loadRecaptchaScript();
        }
        
        return data;
    } catch (error) {
        console.error('❌ Erro:', error);
        return null;
    }
}

function loadRecaptchaScript() {
    if (document.getElementById('recaptcha-script')) return;
    if (!siteKey) return;
    
    console.log('📦 Carregando script reCAPTCHA...');
    
    window.onRecaptchaLoad = function() {
        console.log('✅ reCAPTCHA pronto');
        recaptchaReady = true;
    };
    
    const script = document.createElement('script');
    script.id = 'recaptcha-script';
    script.src = `https://www.google.com/recaptcha/api.js?render=${siteKey}&onload=onRecaptchaLoad`;
    script.async = true;
    script.defer = true;
    
    script.onerror = () => {
        console.warn('⚠️ reCAPTCHA não carregou - modo fallback ativado');
        recaptchaReady = true; // Fallback para desenvolvimento
    };
    
    document.head.appendChild(script);
}

async function generateRecaptchaToken(action = 'login') {
    // Fallback para desenvolvimento
    if (!recaptchaReady || !window.grecaptcha || !window.grecaptcha.execute) {
        if (window.location.hostname === 'localhost') {
            console.warn('⚠️ Usando fallback para desenvolvimento');
            return 'dev-fallback-token';
        }
        return null;
    }
    
    try {
        const token = await window.grecaptcha.execute(siteKey, { action });
        return token;
    } catch (error) {
        console.error('❌ Erro ao gerar token:', error);
        return null;
    }
}

// ==============================================
// LOGIN
// ==============================================

async function login(email, password) {
    try {
        showLoading('loginForm');
        
        if (!email || !password) {
            showMessage('Preencha todos os campos', 'warning');
            hideLoading('loginForm');
            return;
        }
        
        const recaptchaToken = await generateRecaptchaToken('login');
        
        const loginData = {
            email: email.trim().toLowerCase(),
            password: password
        };
        
        const headers = {
            'Content-Type': 'application/json'
        };
        
        if (recaptchaToken) {
            headers['X-Captcha-Token'] = recaptchaToken;
        }
        
        const url = buildUrl('/auth/login');
        if (!url) {
            hideLoading('loginForm');
            return;
        }
        
        const response = await fetch(url, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(loginData)
        });
        
        hideLoading('loginForm');
        
        if (response.ok) {
            const data = await response.json();
            
            localStorage.setItem('access_token', data.access_token);
            localStorage.setItem('refresh_token', data.refresh_token);
            
            const userData = {
                name: data.user_name || '',
                email: data.user_email || email,
                workshop: data.workshop_name || '',
                role: data.role || 'user',
                plan: data.plan || 'free',
                credits: data.credits || 0
            };
            localStorage.setItem('user', JSON.stringify(userData));
            
            showMessage('Login realizado com sucesso!', 'success');
            setTimeout(() => window.location.href = '/dashboard', 1000);
        } else {
            let errorMessage = 'Erro no login';
            try {
                const error = await response.json();
                errorMessage = error.detail || error.message || errorMessage;
            } catch {
                errorMessage = `Erro ${response.status}`;
            }
            showMessage(errorMessage, 'error');
        }
    } catch (error) {
        hideLoading('loginForm');
        console.error('❌ Erro no login:', error);
        showMessage('Erro de conexão', 'error');
    }
}

// ==============================================
// REGISTRO
// ==============================================

async function register(userData) {
    try {
        showLoading('registerForm');
        
        // Validações
        if (!userData.name || !userData.email || !userData.password) {
            showMessage('Preencha todos os campos', 'warning');
            hideLoading('registerForm');
            return;
        }
        
        if (userData.password !== document.getElementById('regConfirmPassword')?.value) {
            showMessage('As senhas não coincidem', 'error');
            hideLoading('registerForm');
            return;
        }
        
        const termsChecked = document.getElementById('terms')?.checked;
        if (!termsChecked) {
            showMessage('Aceite os termos de uso', 'warning');
            hideLoading('registerForm');
            return;
        }
        
        const recaptchaToken = await generateRecaptchaToken('register');
        
        const registerData = {
            name: userData.name.trim(),
            email: userData.email.trim().toLowerCase(),
            password: userData.password,
            workshop_name: userData.workshop_name?.trim() || ''
        };
        
        const headers = {
            'Content-Type': 'application/json'
        };
        
        if (recaptchaToken) {
            headers['X-Captcha-Token'] = recaptchaToken;
        }
        
        const url = buildUrl('/auth/register');
        if (!url) {
            hideLoading('registerForm');
            return;
        }
        
        const response = await fetch(url, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(registerData)
        });
        
        hideLoading('registerForm');
        
        if (response.ok) {
            showMessage('Conta criada! Faça login.', 'success');
            document.getElementById('registerForm')?.reset();
            
            setTimeout(() => {
                document.getElementById('login-tab')?.click();
            }, 1500);
        } else {
            let errorMessage = 'Erro no registro';
            try {
                const error = await response.json();
                errorMessage = error.detail || error.message || errorMessage;
            } catch {
                errorMessage = `Erro ${response.status}`;
            }
            showMessage(errorMessage, 'error');
        }
    } catch (error) {
        hideLoading('registerForm');
        console.error('❌ Erro no registro:', error);
        showMessage('Erro de conexão', 'error');
    }
}

// ==============================================
// LOGOUT
// ==============================================

async function logout() {
    await clearSession(true);
    window.location.href = '/login';
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
    
    setTimeout(() => {
        messageDiv.innerHTML = '';
    }, 5000);
}

function setupForms() {
    document.getElementById('loginForm')?.addEventListener('submit', (e) => {
        e.preventDefault();
        login(
            document.getElementById('loginEmail').value,
            document.getElementById('loginPassword').value
        );
    });
    
    document.getElementById('registerForm')?.addEventListener('submit', (e) => {
        e.preventDefault();
        register({
            name: document.getElementById('regName').value,
            email: document.getElementById('regEmail').value,
            password: document.getElementById('regPassword').value,
            workshop_name: document.getElementById('regWorkshop')?.value
        });
    });
}

// ==============================================
// INICIALIZAÇÃO
// ==============================================

document.addEventListener('DOMContentLoaded', async () => {
    console.log('🚀 Auth.js inicializado');
    
    await validarELimparSessao();
    setInterval(validarELimparSessao, CHECK_INTERVAL);
    
    if (window.location.pathname === '/login' && isAuthenticated()) {
        window.location.href = '/dashboard';
        return;
    }
    
    if (isProtectedPage() && !isAuthenticated()) {
        window.location.href = '/login';
        return;
    }
    
    if (window.location.pathname === '/login') {
        await loadCaptchaConfig();
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
    getCurrentUser: () => {
        try {
            return JSON.parse(localStorage.getItem('user') || 'null');
        } catch {
            return null;
        }
    },
    getToken: () => localStorage.getItem('access_token')
};

console.log('✅ Auth.js carregado');