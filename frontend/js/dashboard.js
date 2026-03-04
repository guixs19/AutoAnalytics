// frontend/js/dashboard.js - Versão atualizada com créditos

const API_URL = 'http://localhost:8000/api';

// Função para verificar autenticação (mantida)
function checkAuth() {
    const token = localStorage.getItem('access_token');
    if (!token) {
        return false;
    }
    return true;
}

// Função para fazer logout (mantida)
function logout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user_name');
    localStorage.removeItem('user_email');
    localStorage.removeItem('workshop_name');
    window.location.href = 'login.html';
}

// ===== NOVAS FUNÇÕES DE CRÉDITOS =====

// Carregar créditos do usuário
async function loadUserCredits() {
    try {
        const response = await fetchWithAuth(`${API_URL}/payments/balance`);
        if (response.ok) {
            const data = await response.json();
            
            // Atualizar em todos os lugares que mostram créditos
            const creditElements = document.querySelectorAll('#navbarCredits, .user-credits');
            creditElements.forEach(el => {
                el.textContent = data.credits || 0;
            });
        }
    } catch (error) {
        console.error('Erro ao carregar créditos:', error);
    }
}

// Verificar créditos antes do upload
async function checkCreditsBeforeUpload() {
    try {
        const response = await fetchWithAuth(`${API_URL}/payments/check-analysis`);
        if (response.ok) {
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

// Modal de créditos insuficientes
function showCreditsModal() {
    // Verificar se modal já existe
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
    
    // Atualizar saldo no modal
    const modalCredits = document.getElementById('modalCredits');
    const currentCredits = document.getElementById('navbarCredits')?.textContent || '0';
    if (modalCredits) modalCredits.textContent = currentCredits;
    
    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
}

// ===== FUNÇÕES EXISTENTES (modificadas para incluir créditos) =====

// Carregar informações do usuário (modificada)
async function loadUserInfo() {
    const userName = localStorage.getItem('user_name');
    const userEmail = localStorage.getItem('user_email');
    const workshopName = localStorage.getItem('workshop_name');
    
    // Exibir no navbar ou sidebar
    const userElement = document.getElementById('userName');
    if (userElement) {
        userElement.textContent = userName || 'Usuário';
    }
    
    const workshopElement = document.getElementById('workshopName');
    if (workshopElement) {
        workshopElement.textContent = workshopName || 'Oficina';
    }
    
    // Carregar créditos
    await loadUserCredits();
}

// Carregar histórico de análises (mantida)
async function loadHistory() {
    try {
        const response = await fetchWithAuth(`${API_URL}/analyses/history`);
        
        if (response.ok) {
            const data = await response.json();
            updateHistoryUI(data);
        }
    } catch (error) {
        console.error('Erro ao carregar histórico:', error);
    }
}

// Atualizar UI com histórico (mantida)
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

// Configurar botão de logout (mantida)
function setupLogout() {
    const logoutBtn = document.getElementById('logoutBtn');
    
    if (logoutBtn) {
        logoutBtn.addEventListener('click', function(e) {
            e.preventDefault();
            
            if (confirm('Deseja realmente sair?')) {
                logout();
            }
        });
    }
}

// ===== FUNÇÃO DE UPLOAD MODIFICADA =====
// Esta função substitui a do seu app.js para verificar créditos
async function handleUpload(e) {
    e.preventDefault();
    
    const file = document.getElementById('fileInput').files[0];
    if (!file) {
        showAlert('Selecione um arquivo primeiro', 'warning');
        return;
    }
    
    // Verificar créditos primeiro
    const hasCredits = await checkCreditsBeforeUpload();
    if (!hasCredits) return;
    
    // Continuar com o upload normal
    const formData = new FormData();
    formData.append('file', file);
    formData.append('analysis_type', document.getElementById('tipoAnalise').value);
    formData.append('ai_model', document.getElementById('modeloIA').value);
    
    // Desabilitar botão
    const uploadBtn = document.getElementById('uploadButton');
    uploadBtn.disabled = true;
    uploadBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i> Enviando...';
    
    try {
        const response = await fetch(`${API_URL}/upload`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            },
            body: formData
        });
        
        if (response.ok) {
            const data = await response.json();
            showAlert('Análise iniciada com sucesso!', 'success');
            
            // Atualizar créditos (já deduzidos no backend)
            await loadUserCredits();
            
            // Iniciar processamento (chamar sua função existente)
            if (window.app) {
                window.app.currentProcessId = data.process_id;
                window.app.showProgress();
                window.app.startProgressPolling();
            }
        } else {
            const error = await response.json();
            if (error.detail && error.detail.error === 'Créditos insuficientes') {
                showCreditsModal();
            } else {
                showAlert(error.detail || 'Erro no upload', 'error');
            }
            uploadBtn.disabled = false;
            uploadBtn.innerHTML = '<i class="fas fa-play-circle me-2"></i> Iniciar Análise Inteligente';
        }
    } catch (error) {
        showAlert('Erro de conexão com o servidor', 'error');
        uploadBtn.disabled = false;
        uploadBtn.innerHTML = '<i class="fas fa-play-circle me-2"></i> Iniciar Análise Inteligente';
    }
}

// Função para fazer requisições com token (mantida)
async function fetchWithAuth(url, options = {}) {
    const token = localStorage.getItem('access_token');
    
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };
    
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    
    const response = await fetch(url, { ...options, headers });
    
    if (response.status === 401) {
        // Token expirado, tentar refresh
        const refreshed = await refreshToken();
        if (refreshed) {
            return fetchWithAuth(url, options);
        } else {
            window.location.href = 'login.html';
        }
    }
    
    return response;
}

// Refresh token (mantida)
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
            localStorage.setItem('refresh_token', data.refresh_token);
            return true;
        }
    } catch (error) {
        console.error('Erro no refresh token:', error);
    }
    
    return false;
}

// Mostrar alerta (mantida)
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
    // Verificar autenticação
    if (!checkAuth()) {
        window.location.href = 'login.html';
        return;
    }
    
    // Carregar informações do usuário
    await loadUserInfo();
    
    // Carregar histórico
    await loadHistory();
    
    // Configurar logout
    setupLogout();
    
    // Substituir o handler de upload do formulário
    const uploadForm = document.getElementById('uploadForm');
    if (uploadForm) {
        uploadForm.removeEventListener('submit', window.app?.handleUpload); // Remover handler antigo se existir
        uploadForm.addEventListener('submit', handleUpload);
    }
});