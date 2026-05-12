// frontend/js/dashboard.js - VERSÃO ATUALIZADA
// Dashboard simplificado - sem PoW, apenas funcionalidades principais

document.addEventListener('DOMContentLoaded', async function() {
    console.log('🚀 Inicializando Dashboard...');
    
    const API_URL = window.location.hostname.includes('localhost') 
        ? 'http://localhost:8000/api'
        : '/api';
    
    // ===== FUNÇÕES DE AUTENTICAÇÃO =====
    
    function isAuthenticated() {
        return !!localStorage.getItem('access_token');
    }
    
    function redirectToLogin() {
        window.location.href = 'login.html';
    }
    
    // Verifica autenticação
    if (!isAuthenticated()) {
        console.log('❌ Usuário não autenticado');
        redirectToLogin();
        return;
    }
    
    // ===== FUNÇÕES DE FETCH COM AUTENTICAÇÃO =====
    
    async function fetchWithAuth(url, options = {}) {
        const token = localStorage.getItem('access_token');
        
        if (!token) {
            redirectToLogin();
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
                // Tenta refresh
                const refreshed = await refreshToken();
                if (refreshed) {
                    const newToken = localStorage.getItem('access_token');
                    headers['Authorization'] = `Bearer ${newToken}`;
                    response = await fetch(url, { ...options, headers });
                    return response;
                } else {
                    redirectToLogin();
                    return null;
                }
            }
            
            return response;
        } catch (error) {
            console.error('Erro na requisição:', error);
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
            console.error('Erro no refresh:', error);
        }
        return false;
    }
    
    async function logout() {
        const refreshToken = localStorage.getItem('refresh_token');
        
        if (refreshToken) {
            try {
                await fetch(`${API_URL}/auth/logout`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ refresh_token: refreshToken })
                });
            } catch (e) {}
        }
        
        localStorage.clear();
        sessionStorage.clear();
        window.location.href = 'login.html';
    }
    
    // ===== FUNÇÕES DE CRÉDITOS =====
    
    async function loadUserCredits() {
        try {
            const response = await fetchWithAuth(`${API_URL}/payments/balance`);
            if (response && response.ok) {
                const data = await response.json();
                const credits = data.plan?.is_premium ? '∞' : (data.credits || 0);
                
                const creditElements = document.querySelectorAll('.credits-display, .user-credits, #creditsCount');
                creditElements.forEach(el => {
                    el.textContent = credits;
                });
                
                return data;
            }
        } catch (error) {
            console.error('Erro ao carregar créditos:', error);
        }
        return null;
    }
    
    async function checkCreditsBeforeUpload() {
        const isAdmin = document.body.classList.contains('is-admin');
        if (isAdmin) return true;
        
        const creditsSpan = document.querySelector('.credits-display');
        const credits = creditsSpan ? creditsSpan.textContent : '0';
        
        if (credits === '0' || credits === '∞') {
            if (credits === '0') {
                showCreditsModal();
                return false;
            }
        }
        return true;
    }
    
    function showCreditsModal() {
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
                                <a href="/planos.html" class="btn btn-primary mt-2">
                                    <i class="fas fa-credit-card me-2"></i> Comprar Créditos
                                </a>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            document.body.insertAdjacentHTML('beforeend', modalHtml);
            modal = document.getElementById('creditsModal');
        }
        
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
    }
    
    // ===== FUNÇÕES DE UI =====
    
    function showAlert(message, type = 'info') {
        const bgColor = type === 'success' ? '#48bb78' : 
                        type === 'error' ? '#f56565' :
                        type === 'warning' ? '#ed8936' : '#4299e1';
        
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
        alertDiv.style.cssText = `
            top: 20px;
            right: 20px;
            z-index: 9999;
            min-width: 300px;
            max-width: 400px;
            background: white;
            border-left: 4px solid ${bgColor};
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
            border-radius: 12px;
            animation: slideInRight 0.3s ease-out;
        `;
        
        alertDiv.innerHTML = `
            <div class="d-flex align-items-center">
                <div class="me-3">
                    <i class="fas ${type === 'success' ? 'fa-check-circle' : 
                                  type === 'error' ? 'fa-exclamation-circle' :
                                  type === 'warning' ? 'fa-exclamation-triangle' : 'fa-info-circle'} 
                       fa-lg" style="color: ${bgColor}"></i>
                </div>
                <div class="flex-grow-1">${escapeHtml(message)}</div>
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        
        document.body.appendChild(alertDiv);
        
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.style.animation = 'fadeOut 0.3s ease-out';
                setTimeout(() => alertDiv.remove(), 300);
            }
        }, 5000);
    }
    
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    // ===== HANDLE UPLOAD =====
    
    async function handleUpload(e) {
        e.preventDefault();
        
        const fileInput = document.getElementById('fileInput');
        const file = fileInput?.files[0];
        
        if (!file) {
            showAlert('Selecione um arquivo primeiro', 'warning');
            return;
        }
        
        const validTypes = ['.xlsx', '.xls', '.csv'];
        const fileExt = '.' + file.name.split('.').pop().toLowerCase();
        if (!validTypes.includes(fileExt)) {
            showAlert('Formato não suportado. Use Excel (.xlsx, .xls) ou CSV', 'error');
            return;
        }
        
        const hasCredits = await checkCreditsBeforeUpload();
        if (!hasCredits) return;
        
        const uploadBtn = document.getElementById('uploadButton');
        const originalText = uploadBtn.innerHTML;
        uploadBtn.disabled = true;
        uploadBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i> Processando...';
        
        try {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('analysis_type', document.getElementById('tipoAnalise')?.value || 'auto');
            formData.append('ai_model', document.getElementById('modeloIA')?.value || 'auto');
            
            const token = localStorage.getItem('access_token');
            const response = await fetch(`${API_URL}/upload-auto`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData
            });
            
            const data = await response.json();
            
            if (response.ok && (data.id || data.process_id)) {
                showAlert('✅ Análise iniciada com sucesso!', 'success');
                
                await loadUserCredits();
                await loadHistory();
                
                fileInput.value = '';
                
                if (window.app && window.app.showProgress) {
                    window.app.currentProcessId = data.process_id || data.id;
                    window.app.showProgress();
                    window.app.startProgressPolling();
                }
            } else {
                const errorMsg = data?.detail || data?.error || 'Erro no upload';
                if (errorMsg.includes('Créditos insuficientes')) {
                    showCreditsModal();
                } else {
                    showAlert(errorMsg, 'error');
                }
            }
        } catch (error) {
            console.error('Erro no upload:', error);
            showAlert(error.message || 'Erro ao processar arquivo', 'error');
        } finally {
            uploadBtn.disabled = false;
            uploadBtn.innerHTML = originalText;
        }
    }
    
    // ===== LOAD HISTORY =====
    
    async function loadHistory() {
        try {
            const response = await fetchWithAuth(`${API_URL}/analyses/history`);
            if (response && response.ok) {
                const analyses = await response.json();
                updateHistoryUI(analyses);
            }
        } catch (error) {
            console.error('Erro ao carregar histórico:', error);
        }
    }
    
    function updateHistoryUI(analyses) {
        const container = document.getElementById('recentAnalyses');
        
        if (!container) return;
        
        if (!analyses || analyses.length === 0) {
            container.innerHTML = `
                <div class="text-center text-muted py-4">
                    <i class="fas fa-chart-line fa-2x mb-2"></i>
                    <p>Nenhuma análise realizada</p>
                    <small>Envie seu primeiro arquivo</small>
                </div>
            `;
            return;
        }
        
        const html = analyses.slice(0, 5).map(analysis => `
            <div class="list-group-item list-group-item-action">
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <i class="fas fa-file-alt me-2 text-primary"></i>
                        <strong>${escapeHtml(analysis.filename || 'Análise')}</strong>
                    </div>
                    <span class="badge ${analysis.status === 'completed' ? 'bg-success' : 'bg-secondary'}">${analysis.status || 'Concluído'}</span>
                </div>
                <small class="text-muted">${new Date(analysis.created_at).toLocaleDateString('pt-BR')}</small>
            </div>
        `).join('');
        
        container.innerHTML = `<div class="list-group">${html}</div>`;
    }
    
    // ===== SETUP DRAG & DROP =====
    
    function setupDragAndDrop() {
        const dropZone = document.getElementById('dropZone');
        if (!dropZone) return;
        
        dropZone.addEventListener('dragenter', (e) => {
            e.preventDefault();
            dropZone.classList.add('drag-over');
        });
        
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('drag-over');
        });
        
        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('drag-over');
        });
        
        dropZone.addEventListener('drop', async (e) => {
            e.preventDefault();
            dropZone.classList.remove('drag-over');
            
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                const file = files[0];
                const fileInput = document.getElementById('fileInput');
                fileInput.files = files;
                
                showAlert(`📁 Arquivo selecionado: ${file.name}`, 'info');
                
                const autoUpload = document.getElementById('autoUpload')?.checked || false;
                if (autoUpload) {
                    await handleUpload(new Event('submit'));
                }
            }
        });
        
        dropZone.addEventListener('click', () => {
            document.getElementById('fileInput').click();
        });
    }
    
    // ===== SETUP LOGOUT =====
    
    function setupLogout() {
        const logoutBtn = document.getElementById('logoutBtn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', async (e) => {
                e.preventDefault();
                const confirmLogout = confirm('Deseja realmente sair?');
                if (confirmLogout) {
                    await logout();
                }
            });
        }
    }
    
    // ===== INICIALIZAÇÃO =====
    
    // Carrega informações do usuário
    const userStr = localStorage.getItem('user');
    if (userStr) {
        try {
            const user = JSON.parse(userStr);
            const userNameEl = document.getElementById('userName');
            if (userNameEl) userNameEl.textContent = user.name || 'Usuário';
            
            if (user.is_admin) {
                document.body.classList.add('is-admin');
            }
        } catch (e) {}
    }
    
    // Carrega créditos
    await loadUserCredits();
    
    // Carrega histórico
    await loadHistory();
    
    // Setup eventos
    setupDragAndDrop();
    setupLogout();
    
    const uploadForm = document.getElementById('uploadForm');
    if (uploadForm) {
        uploadForm.addEventListener('submit', handleUpload);
    }
    
    const autoUploadCheckbox = document.getElementById('autoUpload');
    if (autoUploadCheckbox) {
        autoUploadCheckbox.checked = localStorage.getItem('autoUpload') === 'true';
        autoUploadCheckbox.addEventListener('change', (e) => {
            localStorage.setItem('autoUpload', e.target.checked);
        });
    }
    
    console.log('✅ Dashboard inicializado com sucesso!');
});

// Adiciona CSS para animações
const style = document.createElement('style');
style.textContent = `
    @keyframes slideInRight {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes fadeOut {
        from { opacity: 1; }
        to { opacity: 0; }
    }
    .drag-over {
        background: linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%);
        border: 2px dashed #667eea !important;
        transform: scale(1.02);
        transition: all 0.2s ease;
    }
`;
document.head.appendChild(style);