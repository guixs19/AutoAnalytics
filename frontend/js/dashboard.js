// frontend/js/dashboard.js - VERSÃO MODIFICADA (com suporte a PoW)

const API_URL = 'http://localhost:8000/api';

// ===== FUNÇÕES DELEGADAS PARA auth.js =====

function isAdmin() {
    return window.appAuth ? window.appAuth.isAdmin() : false;
}

function getCreditsDisplay() {
    return window.appAuth ? window.appAuth.getCreditsDisplay() : '0';
}

function getCurrentUser() {
    return window.appAuth ? window.appAuth.getCurrentUser() : {};
}

function checkAuth() {
    return window.appAuth ? window.appAuth.isAuthenticated() : !!localStorage.getItem('access_token');
}

function logout() {
    if (window.powClient) window.powClient.reset();
    if (window.appAuth) {
        window.appAuth.logout();
    } else {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
        window.location.href = 'login.html';
    }
}

// ===== FUNÇÕES DE CRÉDITOS =====

async function loadUserCredits() {
    try {
        const response = await fetchWithAuth(`${API_URL}/payments/balance`);
        if (response && response.ok) {
            const data = await response.json();
            
            if (window.appAuth) {
                const user = window.appAuth.getCurrentUser();
                user.credits = data.credits || 0;
                user.is_admin = data.is_admin || false;
                localStorage.setItem('user', JSON.stringify(user));
                window.appAuth.updateCreditsDisplay();
            }
            
            updateCreditsDisplay();
        }
    } catch (error) {
        console.error('Erro ao carregar créditos:', error);
    }
}

function updateCreditsDisplay() {
    const user = getCurrentUser();
    const creditsDisplay = getCreditsDisplay();
    
    const creditElements = document.querySelectorAll('#navbarCredits, .user-credits, #creditsCount');
    creditElements.forEach(el => {
        if (el.tagName === 'SPAN' || el.tagName === 'DIV') {
            el.textContent = creditsDisplay;
        } else {
            const span = el.querySelector('span');
            if (span) span.textContent = creditsDisplay;
        }
    });
    
    const adminBadges = document.querySelectorAll('.admin-badge');
    if (user.is_admin) {
        adminBadges.forEach(el => {
            el.style.display = 'inline-block';
        });
        document.body.classList.add('is-admin');
    } else {
        adminBadges.forEach(el => {
            el.style.display = 'none';
        });
        document.body.classList.remove('is-admin');
    }
}

async function checkCreditsBeforeUpload() {
    if (isAdmin()) return true;
    
    try {
        const response = await fetchWithAuth(`${API_URL}/payments/check-analysis`);
        if (response && response.ok) {
            const data = await response.json();
            
            if (!data.has_credits) {
                showCreditsModal();
                return false;
            }
            return true;
        }
    } catch (error) {
        console.error('Erro ao verificar créditos:', error);
    }
    return false;
}

function showCreditsModal() {
    if (isAdmin()) return;
    
    let modal = document.getElementById('creditsModal');
    
    if (!modal) {
        const modalHtml = `
            <div class="modal fade" id="creditsModal" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header bg-warning">
                            <h5 class="modal-title">
                                <i class="fas fa-exclamation-triangle me-2"></i>
                                Créditos Insuficientes
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body text-center py-4">
                            <i class="fas fa-coins fa-4x text-warning mb-3"></i>
                            <h5>Você não tem créditos para realizar esta análise</h5>
                            <p class="text-muted">Cada análise consome 1 crédito.</p>
                            <p>Seu saldo atual: <strong><span id="modalCredits">0</span></strong> créditos</p>
                        </div>
                        <div class="modal-footer justify-content-center">
                            <a href="/planos.html" class="btn btn-primary">
                                <i class="fas fa-credit-card me-2"></i>
                                Comprar Créditos
                            </a>
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                Cancelar
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        modal = document.getElementById('creditsModal');
    }
    
    const modalCredits = document.getElementById('modalCredits');
    const user = getCurrentUser();
    if (modalCredits) modalCredits.textContent = user.credits || 0;
    
    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
}

async function loadUserInfo() {
    const user = getCurrentUser();
    
    const userElement = document.getElementById('userName');
    if (userElement) {
        userElement.textContent = user.name || 'Usuário';
    }
    
    const workshopElement = document.getElementById('workshopName');
    if (workshopElement) {
        workshopElement.textContent = user.workshop || 'Oficina';
    }
    
    await loadUserCredits();
    updateCreditsDisplay();
}

async function loadHistory() {
    try {
        const response = await fetchWithAuth(`${API_URL}/analyses/history`);
        
        if (response && response.ok) {
            const data = await response.json();
            updateHistoryUI(data);
        }
    } catch (error) {
        console.error('Erro ao carregar histórico:', error);
    }
}

function updateHistoryUI(analyses) {
    const container = document.getElementById('recentAnalyses');
    
    if (!container || !analyses || analyses.length === 0) {
        container.innerHTML = `
            <div class="timeline-item">
                <div class="timeline-marker"></div>
                <div class="timeline-content">
                    <p class="mb-1 small">Nenhuma análise realizada</p>
                    <small class="text-muted">Envie seu primeiro arquivo</small>
                </div>
            </div>
        `;
        return;
    }
    
    const html = analyses.slice(0, 5).map(analysis => `
        <div class="timeline-item">
            <div class="timeline-marker bg-success"></div>
            <div class="timeline-content">
                <p class="mb-1 small">${analysis.filename || 'Arquivo'}</p>
                <small class="text-muted">
                    ${new Date(analysis.created_at).toLocaleDateString('pt-BR')}
                    • ${analysis.status || 'Concluído'}
                </small>
            </div>
        </div>
    `).join('');
    
    container.innerHTML = html;
}

function setupLogout() {
    const logoutBtn = document.getElementById('logoutBtn');
    
    if (logoutBtn) {
        logoutBtn.addEventListener('click', function(e) {
            e.preventDefault();
            
            if (confirm('Deseja realmente sair?')) {
                if (window.powClient) window.powClient.reset();
                logout();
            }
        });
    }
}

// ===== UPLOAD COM PoW =====
async function handleUpload(e) {
    e.preventDefault();
    
    const file = document.getElementById('fileInput').files[0];
    if (!file) {
        showAlert('Selecione um arquivo primeiro', 'warning');
        return;
    }
    
    const hasCredits = await checkCreditsBeforeUpload();
    if (!hasCredits) return;
    
    const uploadBtn = document.getElementById('uploadButton');
    uploadBtn.disabled = true;
    uploadBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i> Enviando...';
    
    try {
        // 🔐 UPLOAD COM PoW (usando powClient se disponível)
        let response;
        
        if (window.powClient) {
            response = await window.powClient.uploadWithPow(file, '/api/upload');
        } else {
            // Fallback (sem PoW)
            const formData = new FormData();
            formData.append('file', file);
            formData.append('analysis_type', document.getElementById('tipoAnalise')?.value || 'auto');
            formData.append('ai_model', document.getElementById('modeloIA')?.value || 'auto');
            
            const token = localStorage.getItem('access_token');
            response = await fetch(`${API_URL}/upload`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData
            });
        }
        
        if (response.ok) {
            const data = await response.json();
            showAlert('Análise iniciada com sucesso!', 'success');
            await loadUserCredits();
            
            if (window.app) {
                window.app.currentProcessId = data.process_id;
                window.app.showProgress();
                window.app.startProgressPolling();
            }
        } else {
            const error = await response.json();
            if (error.detail && error.detail.error === 'Créditos insuficientes') {
                showCreditsModal();
            } else if (response.status === 428 || response.status === 401) {
                showAlert('Desafio de segurança expirado. Tente novamente.', 'warning');
            } else {
                showAlert(error.detail || 'Erro no upload', 'error');
            }
            uploadBtn.disabled = false;
            uploadBtn.innerHTML = '<i class="fas fa-play-circle me-2"></i> Iniciar Análise Inteligente';
        }
    } catch (error) {
        console.error('Erro no upload:', error);
        showAlert('Erro de conexão com o servidor', 'error');
        uploadBtn.disabled = false;
        uploadBtn.innerHTML = '<i class="fas fa-play-circle me-2"></i> Iniciar Análise Inteligente';
    }
}

// ===== FETCH COM AUTENTICAÇÃO (ATUALIZADO) =====
async function fetchWithAuth(url, options = {}) {
    const token = localStorage.getItem('access_token');
    
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };
    
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    
    try {
        let response = await fetch(url, { ...options, headers });
        
        if (response.status === 401) {
            const refreshed = await refreshToken();
            if (refreshed) {
                const newToken = localStorage.getItem('access_token');
                headers['Authorization'] = `Bearer ${newToken}`;
                return fetch(url, { ...options, headers });
            } else {
                window.location.href = 'login.html';
                return null;
            }
        }
        
        return response;
    } catch (error) {
        console.error('Erro no fetch:', error);
        return null;
    }
}

async function refreshToken() {
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
            if (data.refresh_token) {
                localStorage.setItem('refresh_token', data.refresh_token);
            }
            return true;
        }
    } catch (error) {
        console.error('Erro no refresh token:', error);
    }
    
    return false;
}

function showAlert(message, type = 'info') {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    alertDiv.style.cssText = `
        top: 20px;
        right: 20px;
        z-index: 9999;
        min-width: 300px;
    `;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(alertDiv);
    
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 5000);
}

// ===== INICIALIZAÇÃO =====
document.addEventListener('DOMContentLoaded', async function() {
    if (!checkAuth()) {
        window.location.href = 'login.html';
        return;
    }
    
    setTimeout(async () => {
        await loadUserInfo();
        await loadHistory();
        setupLogout();
        
        const uploadForm = document.getElementById('uploadForm');
        if (uploadForm) {
            uploadForm.removeEventListener('submit', window.app?.handleUpload);
            uploadForm.addEventListener('submit', handleUpload);
        }
        
        const navbar = document.querySelector('.navbar-modern .container');
        if (navbar && isAdmin() && !document.querySelector('.admin-badge-nav')) {
            const adminBadge = document.createElement('span');
            adminBadge.className = 'admin-badge-nav badge bg-warning text-dark ms-2';
            adminBadge.innerHTML = '<i class="fas fa-crown me-1"></i>Admin';
            navbar.appendChild(adminBadge);
        }
        
        console.log('✅ dashboard.js inicializado com suporte a PoW');
    }, 200);
});