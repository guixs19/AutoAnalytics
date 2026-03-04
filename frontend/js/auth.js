// frontend/js/auth.js - COM CAPTCHA

const API_URL = 'http://localhost:8000/api';

// Função para carregar CAPTCHA
async function loadCaptcha() {
    try {
        const response = await fetch(`${API_URL}/auth/captcha/generate`);
        const data = await response.json();
        
        if (data.type === 'recaptcha_v2') {
            // Carregar reCAPTCHA v2
            loadRecaptchaV2(data.site_key);
        } else if (data.type === 'recaptcha_v3') {
            // reCAPTCHA v3 (invisível)
            window.captchaSiteKey = data.site_key;
        } else if (data.type === 'custom') {
            // CAPTCHA próprio
            displayCustomCaptcha(data);
        }
    } catch (error) {
        console.error('Erro ao carregar CAPTCHA:', error);
    }
}

// Função de login com CAPTCHA
async function login(email, password) {
    try {
        // Obter token CAPTCHA
        let captchaToken = '';
        
        if (window.captchaType === 'recaptcha_v3') {
            // reCAPTCHA v3 (automático)
            captchaToken = await executeRecaptchaV3();
        } else if (window.captchaType === 'recaptcha_v2') {
            // reCAPTCHA v2 (usuário clica)
            captchaToken = document.getElementById('g-recaptcha-response').value;
        } else if (window.customCaptchaId) {
            // CAPTCHA próprio
            const userInput = document.getElementById('captcha-input').value;
            captchaToken = `${window.customCaptchaId}:${userInput}`;
        }
        
        const response = await fetch(`${API_URL}/auth/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Captcha-Token': captchaToken
            },
            body: JSON.stringify({ email, password })
        });
        
        if (response.ok) {
            const data = await response.json();
            
            // Salvar tokens
            localStorage.setItem('access_token', data.access_token);
            localStorage.setItem('refresh_token', data.refresh_token);
            
            // Redirecionar
            window.location.href = '/dashboard.html';
        } else {
            const error = await response.json();
            showError(error.detail);
            
            // Recarregar CAPTCHA se falhou
            if (window.grecaptcha) {
                window.grecaptcha.reset();
            }
        }
    } catch (error) {
        console.error('Erro no login:', error);
    }
}

// Refresh token automático
async function refreshAccessToken() {
    const refreshToken = localStorage.getItem('refresh_token');
    
    if (!refreshToken) return false;
    
    try {
        const response = await fetch(`${API_URL}/auth/refresh`, {
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
            // Refresh token inválido - logout
            logout();
            return false;
        }
    } catch (error) {
        console.error('Erro no refresh token:', error);
        return false;
    }
}

// Interceptar requisições para adicionar token e refresh automático
async function apiRequest(url, options = {}) {
    // Tentar até 2 vezes (caso precise refresh)
    for (let attempt = 0; attempt < 2; attempt++) {
        let token = localStorage.getItem('access_token');
        
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers
        };
        
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        
        const response = await fetch(url, { ...options, headers });
        
        if (response.status === 401) {
            // Token expirado - tentar refresh
            const refreshed = await refreshAccessToken();
            if (refreshed) {
                // Tentar novamente com novo token
                continue;
            } else {
                // Refresh falhou - redirecionar para login
                window.location.href = '/login.html';
                throw new Error('Sessão expirada');
            }
        }
        
        return response;
    }
}