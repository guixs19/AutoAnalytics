// frontend/js/dashboard.js - VERSÃO ATUALIZADA COM ANÁLISES INDIVIDUAIS POR ARQUIVO
// Suporte a múltiplos arquivos (até 3 por vez) com cards individuais

document.addEventListener('DOMContentLoaded', async function() {
    console.log('🚀 Inicializando Dashboard...');
    
    const API_URL = window.location.hostname.includes('localhost') 
        ? 'http://localhost:8000/api'
        : '/api';
    
    const MAX_FILES_PER_BATCH = 3;
    const MAX_FILE_SIZE_KB = 15;
    
    // Armazenar análises ativas
    let activeAnalyses = [];
    let pollingIntervals = [];
    
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
                const maxCredits = data.max_credits_balance || 3;
                
                const creditElements = document.querySelectorAll('.credits-display, .user-credits, #creditsCount');
                creditElements.forEach(el => {
                    el.textContent = credits;
                });
                
                // Atualizar badge de limite
                const limitBadge = document.getElementById('creditLimitBadge');
                if (limitBadge) {
                    if (credits === '∞') {
                        limitBadge.innerHTML = '<i class="fas fa-infinity me-1"></i> Ilimitado';
                    } else {
                        limitBadge.innerHTML = `<i class="fas fa-coins me-1"></i> ${credits}/${maxCredits} créditos`;
                    }
                }
                
                return data;
            }
        } catch (error) {
            console.error('Erro ao carregar créditos:', error);
        }
        return null;
    }
    
    async function checkCreditsBeforeUpload(filesCount = 1) {
        const isAdmin = document.body.classList.contains('is-admin');
        if (isAdmin) return true;
        
        const creditsSpan = document.querySelector('.credits-display');
        let credits = creditsSpan ? creditsSpan.textContent : '0';
        
        if (credits === '0' || credits === '∞') {
            if (credits === '0') {
                showCreditsModal();
                return false;
            }
        }
        
        const numericCredits = parseInt(credits);
        if (numericCredits < filesCount) {
            showNotification(`❌ Você precisa de ${filesCount} crédito(s) para processar ${filesCount} arquivo(s). Você tem apenas ${numericCredits}.`, 'warning');
            showCreditsModal();
            return false;
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
                                <h5>Você não tem créditos suficientes</h5>
                                <p class="text-muted">Cada análise consome 1 crédito. Você pode processar até ${MAX_FILES_PER_BATCH} arquivos por vez.</p>
                                <div class="alert alert-info small">
                                    <i class="fas fa-info-circle me-1"></i>
                                    Limite máximo de 3 créditos acumulados. Use-os para continuar recebendo!
                                </div>
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
    
    function showNotification(message, type = 'info') {
        const bgColor = type === 'success' ? '#48bb78' : 
                        type === 'error' ? '#f56565' :
                        type === 'warning' ? '#ed8936' : '#4299e1';
        
        const icon = type === 'success' ? 'fa-check-circle' : 
                     type === 'error' ? 'fa-exclamation-circle' :
                     type === 'warning' ? 'fa-exclamation-triangle' : 'fa-info-circle';
        
        // Verificar se toastr está disponível
        if (window.toastr) {
            toastr[type](message);
            return;
        }
        
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
                    <i class="fas ${icon} fa-lg" style="color: ${bgColor}"></i>
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
    
    // ===== 🔥 NOVO: DASHBOARD COM CARDS INDIVIDUAIS POR ARQUIVO =====
    
    function createAnalysisCard(processId, filename, index) {
        const cardId = `analysis-card-${processId}`;
        const statusId = `status-${processId}`;
        const progressId = `progress-${processId}`;
        
        return `
            <div class="analysis-card mb-4" id="${cardId}" data-process-id="${processId}" data-filename="${filename}">
                <div class="card border-0 shadow-sm rounded-4 overflow-hidden">
                    <div class="card-header bg-gradient-primary text-white py-3" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
                        <div class="d-flex justify-content-between align-items-center">
                            <div>
                                <i class="fas fa-chart-line me-2"></i>
                                <strong>Análise #${index + 1}</strong>
                                <span class="badge bg-light text-dark ms-2" id="${statusId}">Aguardando</span>
                            </div>
                            <div>
                                <i class="fas fa-file-excel me-1"></i>
                                <small>${escapeHtml(filename.length > 30 ? filename.substring(0, 30) + '...' : filename)}</small>
                            </div>
                        </div>
                    </div>
                    <div class="card-body">
                        <!-- Progresso -->
                        <div class="progress-container mb-4" id="progress-container-${processId}">
                            <div class="d-flex justify-content-between small mb-1">
                                <span><i class="fas fa-spinner fa-spin me-1"></i> Processando...</span>
                                <span id="progress-text-${processId}" class="text-muted">0%</span>
                            </div>
                            <div class="progress" style="height: 10px;">
                                <div id="${progressId}" class="progress-bar progress-bar-striped progress-bar-animated" style="width: 0%"></div>
                            </div>
                        </div>
                        
                        <!-- Resultados (inicialmente ocultos) -->
                        <div id="results-${processId}" style="display: none;">
                            <!-- Métricas -->
                            <div class="row g-3 mb-4" id="metrics-${processId}">
                                <div class="col-md-3 col-6">
                                    <div class="metric-box text-center p-3 bg-light rounded-3">
                                        <div class="metric-value h3 mb-0 text-primary" id="total-rows-${processId}">-</div>
                                        <div class="metric-label small text-muted">Total Registros</div>
                                    </div>
                                </div>
                                <div class="col-md-3 col-6">
                                    <div class="metric-box text-center p-3 bg-light rounded-3">
                                        <div class="metric-value h3 mb-0 text-success" id="accuracy-${processId}">-</div>
                                        <div class="metric-label small text-muted">Precisão</div>
                                    </div>
                                </div>
                                <div class="col-md-3 col-6">
                                    <div class="metric-box text-center p-3 bg-light rounded-3">
                                        <div class="metric-value h3 mb-0 text-info" id="features-${processId}">-</div>
                                        <div class="metric-label small text-muted">Features</div>
                                    </div>
                                </div>
                                <div class="col-md-3 col-6">
                                    <div class="metric-box text-center p-3 bg-light rounded-3">
                                        <div class="metric-value h3 mb-0 text-warning" id="model-${processId}">-</div>
                                        <div class="metric-label small text-muted">Modelo</div>
                                    </div>
                                </div>
                            </div>
                            
                            <!-- Informações da análise -->
                            <div class="alert alert-info small" id="analysis-info-${processId}">
                                <i class="fas fa-info-circle me-2"></i>
                                Aguardando conclusão da análise...
                            </div>
                            
                            <!-- Botões de ação -->
                            <div class="d-flex gap-2 mt-3">
                                <button class="btn btn-sm btn-outline-primary" onclick="downloadReport('${processId}')">
                                    <i class="fas fa-download me-1"></i> Relatório
                                </button>
                                <button class="btn btn-sm btn-outline-success" onclick="exportCsv('${processId}')">
                                    <i class="fas fa-file-csv me-1"></i> Exportar CSV
                                </button>
                                <button class="btn btn-sm btn-outline-info" onclick="viewDetails('${processId}')">
                                    <i class="fas fa-chart-bar me-1"></i> Detalhes
                                </button>
                            </div>
                        </div>
                        
                        <!-- Mensagem de erro -->
                        <div id="error-${processId}" style="display: none;" class="alert alert-danger">
                            <i class="fas fa-exclamation-triangle me-2"></i>
                            <span id="error-msg-${processId}"></span>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    function displayActiveAnalyses() {
        const container = document.getElementById('activeAnalysesContainer');
        if (!container) return;
        
        if (activeAnalyses.length === 0) {
            container.innerHTML = `
                <div class="text-center text-muted py-5">
                    <i class="fas fa-chart-line fa-3x mb-3 opacity-50"></i>
                    <h5>Nenhuma análise em andamento</h5>
                    <p class="small">Envie arquivos para ver os resultados aqui</p>
                </div>
            `;
            return;
        }
        
        let html = '<div class="analyses-grid">';
        activeAnalyses.forEach((analysis, index) => {
            html += createAnalysisCard(analysis.processId, analysis.filename, index);
        });
        html += '</div>';
        
        container.innerHTML = html;
    }
    
    function updateAnalysisProgress(processId, status, progress, analysisInfo = null) {
        const progressBar = document.getElementById(`progress-${processId}`);
        const progressText = document.getElementById(`progress-text-${processId}`);
        const statusBadge = document.getElementById(`status-${processId}`);
        const progressContainer = document.getElementById(`progress-container-${processId}`);
        const resultsDiv = document.getElementById(`results-${processId}`);
        const errorDiv = document.getElementById(`error-${processId}`);
        
        if (progressBar) progressBar.style.width = `${progress || 0}%`;
        if (progressText) progressText.textContent = `${progress || 0}%`;
        
        if (statusBadge) {
            let statusClass = 'bg-secondary';
            let statusIcon = '⏳';
            
            if (status === 'completed') {
                statusClass = 'bg-success';
                statusIcon = '✅';
                statusText = 'Concluído';
            } else if (status === 'error') {
                statusClass = 'bg-danger';
                statusIcon = '❌';
                statusText = 'Erro';
            } else if (status === 'processing') {
                statusClass = 'bg-info';
                statusIcon = '⚙️';
                statusText = 'Processando';
            } else if (status === 'analyzing') {
                statusClass = 'bg-primary';
                statusIcon = '🔍';
                statusText = 'Analisando';
            } else {
                statusText = status || 'Processando';
            }
            
            statusBadge.innerHTML = `${statusIcon} ${statusText}`;
            statusBadge.className = `badge ${statusClass} ms-2`;
        }
        
        if (status === 'completed' && analysisInfo) {
            if (progressContainer) progressContainer.style.display = 'none';
            if (resultsDiv) resultsDiv.style.display = 'block';
            
            // Preencher métricas
            const totalRows = document.getElementById(`total-rows-${processId}`);
            const accuracy = document.getElementById(`accuracy-${processId}`);
            const features = document.getElementById(`features-${processId}`);
            const model = document.getElementById(`model-${processId}`);
            const analysisInfoDiv = document.getElementById(`analysis-info-${processId}`);
            
            if (totalRows) totalRows.textContent = analysisInfo.rows_processed || analysisInfo.total_rows || '-';
            if (accuracy) accuracy.textContent = analysisInfo.accuracy ? `${(analysisInfo.accuracy * 100).toFixed(1)}%` : '-';
            if (features) features.textContent = analysisInfo.features_count || analysisInfo.columns_detected || '-';
            if (model) model.textContent = analysisInfo.model_used || analysisInfo.best_model || 'AutoML';
            
            if (analysisInfoDiv) {
                analysisInfoDiv.innerHTML = `
                    <i class="fas fa-info-circle me-2"></i>
                    <strong>Análise concluída!</strong><br>
                    Arquivo: ${escapeHtml(analysisInfo.filename || 'desconhecido')}<br>
                    Coluna alvo: <strong>${analysisInfo.target_column || 'automática'}</strong><br>
                    ${analysisInfo.description || 'Análise preditiva concluída com sucesso.'}
                `;
            }
            
            showNotification(`✅ Análise concluída: ${analysisInfo.filename || 'Arquivo'}`, 'success');
            
        } else if (status === 'error') {
            if (progressContainer) progressContainer.style.display = 'none';
            if (errorDiv) errorDiv.style.display = 'block';
            const errorMsg = document.getElementById(`error-msg-${processId}`);
            if (errorMsg) errorMsg.textContent = analysisInfo?.error || 'Erro no processamento do arquivo';
            
            showNotification(`❌ Erro na análise: ${analysisInfo?.filename || 'Arquivo'}`, 'error');
        }
    }
    
    async function pollAnalysisStatus(processId, filename) {
        return new Promise((resolve) => {
            const interval = setInterval(async () => {
                try {
                    const response = await fetchWithAuth(`${API_URL}/status/${processId}`);
                    if (!response) return;
                    
                    const data = await response.json();
                    
                    updateAnalysisProgress(
                        processId, 
                        data.status, 
                        data.progress || 0,
                        {
                            ...data.analysis_info,
                            filename: filename,
                            rows_processed: data.analysis_info?.rows_processed,
                            accuracy: data.prediction_stats?.accuracy,
                            total_rows: data.analysis_info?.rows_processed
                        }
                    );
                    
                    if (data.status === 'completed' || data.status === 'error') {
                        clearInterval(interval);
                        // Remover do índice de polling
                        const intervalIndex = pollingIntervals.findIndex(i => i.processId === processId);
                        if (intervalIndex !== -1) {
                            pollingIntervals.splice(intervalIndex, 1);
                        }
                        resolve(data);
                    }
                } catch (error) {
                    console.error(`Erro no polling para ${processId}:`, error);
                }
            }, 2000);
            
            pollingIntervals.push({ processId, interval });
        });
    }
    
    // ===== HANDLE UPLOAD COM MÚLTIPLOS ARQUIVOS =====
    
    async function handleUpload(e) {
        e.preventDefault();
        
        const fileInput = document.getElementById('fileInput');
        const files = fileInput?.files;
        
        if (!files || files.length === 0) {
            showNotification('Selecione pelo menos um arquivo primeiro', 'warning');
            return;
        }
        
        const totalFiles = files.length;
        
        if (totalFiles > MAX_FILES_PER_BATCH) {
            showNotification(`Máximo de ${MAX_FILES_PER_BATCH} arquivos por vez. Você selecionou ${totalFiles}.`, 'error');
            return;
        }
        
        // Validar tamanho de cada arquivo
        const invalidFiles = [];
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            const fileSizeKB = file.size / 1024;
            if (file.size > MAX_FILE_SIZE_KB * 1024) {
                invalidFiles.push(`${file.name} (${fileSizeKB.toFixed(1)}KB)`);
            }
        }
        
        if (invalidFiles.length > 0) {
            showNotification(`❌ Arquivos excedem o limite de ${MAX_FILE_SIZE_KB}KB: ${invalidFiles.join(', ')}`, 'error');
            return;
        }
        
        // Validar formatos
        const validExtensions = ['.xlsx', '.xls', '.csv'];
        const invalidFormatFiles = [];
        for (const file of files) {
            const fileExt = '.' + file.name.split('.').pop().toLowerCase();
            if (!validExtensions.includes(fileExt)) {
                invalidFormatFiles.push(file.name);
            }
        }
        
        if (invalidFormatFiles.length > 0) {
            showNotification(`Formatos não suportados: ${invalidFormatFiles.join(', ')}`, 'error');
            return;
        }
        
        // Verificar créditos
        const hasCredits = await checkCreditsBeforeUpload(totalFiles);
        if (!hasCredits) return;
        
        // Criar cards para cada arquivo antes do upload
        const newAnalyses = [];
        for (let i = 0; i < files.length; i++) {
            const tempId = `temp_${Date.now()}_${i}`;
            newAnalyses.push({
                processId: tempId,
                filename: files[i].name,
                status: 'waiting'
            });
        }
        
        activeAnalyses = [...newAnalyses, ...activeAnalyses];
        displayActiveAnalyses();
        
        const uploadBtn = document.getElementById('uploadButton');
        const originalText = uploadBtn.innerHTML;
        uploadBtn.disabled = true;
        uploadBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i> Processando arquivos...';
        
        try {
            const formData = new FormData();
            for (let i = 0; i < files.length; i++) {
                formData.append('files', files[i]);
            }
            formData.append('analysis_type', document.getElementById('tipoAnalise')?.value || 'auto');
            formData.append('ai_model', document.getElementById('modeloIA')?.value || 'auto');
            
            const token = localStorage.getItem('access_token');
            const response = await fetch(`${API_URL}/upload-auto`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData
            });
            
            const data = await response.json();
            
            if (response.ok && data.processed_files && data.processed_files.length > 0) {
                // Atualizar os processIds reais
                const successCount = data.processed_files.length;
                const failCount = data.failed_files?.length || 0;
                
                // Substituir IDs temporários pelos reais
                for (let i = 0; i < data.processed_files.length; i++) {
                    const processed = data.processed_files[i];
                    const tempAnalysis = activeAnalyses[i];
                    if (tempAnalysis) {
                        tempAnalysis.processId = processed.process_id;
                        tempAnalysis.status = 'processing';
                    }
                }
                
                // Adicionar arquivos com erro
                if (data.failed_files && data.failed_files.length > 0) {
                    for (const failed of data.failed_files) {
                        activeAnalyses.push({
                            processId: `error_${Date.now()}_${Math.random()}`,
                            filename: failed.filename,
                            status: 'error',
                            error: failed.error
                        });
                    }
                }
                
                displayActiveAnalyses();
                
                let message = `✅ ${successCount} de ${totalFiles} arquivo(s) processado(s)!`;
                if (failCount > 0) message += ` ⚠️ ${failCount} falharam.`;
                showNotification(message, successCount > 0 ? 'success' : 'warning');
                
                // Iniciar polling para cada arquivo processado
                for (const processed of data.processed_files) {
                    pollAnalysisStatus(processed.process_id, processed.filename);
                }
                
                // Atualizar créditos
                await loadUserCredits();
                await loadHistory();
                
                fileInput.value = '';
                
                // Limpar preview
                const filePreviewContainer = document.getElementById('filePreviewContainer');
                if (filePreviewContainer) filePreviewContainer.innerHTML = '';
                
            } else {
                // Remover análises temporárias
                activeAnalyses = activeAnalyses.filter(a => !a.processId.toString().startsWith('temp_'));
                displayActiveAnalyses();
                
                const errorMsg = data?.detail || data?.error || 'Erro no upload';
                if (errorMsg.includes('Créditos insuficientes')) {
                    showCreditsModal();
                } else {
                    showNotification(errorMsg, 'error');
                }
            }
        } catch (error) {
            console.error('Erro no upload:', error);
            showNotification(error.message || 'Erro ao processar arquivo(s)', 'error');
            
            // Remover análises temporárias
            activeAnalyses = activeAnalyses.filter(a => !a.processId.toString().startsWith('temp_'));
            displayActiveAnalyses();
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
                const data = await response.json();
                const analyses = data.analyses || data;
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
                    <small>Envie seu primeiro arquivo (até ${MAX_FILES_PER_BATCH} por vez)</small>
                </div>
            `;
            return;
        }
        
        const html = analyses.slice(0, 10).map(analysis => {
            const date = new Date(analysis.created_at);
            const fileSizeInfo = analysis.file_size ? `${(analysis.file_size/1024).toFixed(1)}KB` : '';
            const statusClass = analysis.status === 'completed' ? 'bg-success' : 'bg-secondary';
            const statusText = analysis.status === 'completed' ? 'Concluído' : (analysis.status || 'Processado');
            
            return `
                <div class="list-group-item list-group-item-action">
                    <div class="d-flex justify-content-between align-items-center">
                        <div class="flex-grow-1">
                            <div class="d-flex align-items-center gap-2 mb-1">
                                <i class="fas fa-file-alt text-primary"></i>
                                <strong>${escapeHtml(analysis.filename || 'Análise')}</strong>
                                ${fileSizeInfo ? `<span class="badge bg-light text-dark">${fileSizeInfo}</span>` : ''}
                                <span class="badge ${statusClass}">${statusText}</span>
                            </div>
                            <small class="text-muted">
                                <i class="far fa-calendar-alt me-1"></i>${date.toLocaleDateString('pt-BR')}
                                <i class="far fa-clock ms-2 me-1"></i>${date.toLocaleTimeString('pt-BR')}
                            </small>
                        </div>
                        <button class="btn btn-sm btn-outline-primary" onclick="viewAnalysisDetails('${analysis.id || analysis.process_id}')">
                            <i class="fas fa-eye"></i>
                        </button>
                    </div>
                </div>
            `;
        }).join('');
        
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
            
            const files = Array.from(e.dataTransfer.files);
            
            if (files.length > 0) {
                if (files.length > MAX_FILES_PER_BATCH) {
                    showNotification(`Máximo de ${MAX_FILES_PER_BATCH} arquivos por vez.`, 'error');
                    return;
                }
                
                // Validar tamanhos
                const oversized = files.filter(f => f.size > MAX_FILE_SIZE_KB * 1024);
                if (oversized.length > 0) {
                    showNotification(`${oversized.length} arquivo(s) excedem o limite de ${MAX_FILE_SIZE_KB}KB`, 'error');
                    return;
                }
                
                const dataTransfer = new DataTransfer();
                files.forEach(file => dataTransfer.items.add(file));
                
                const fileInput = document.getElementById('fileInput');
                if (fileInput) {
                    fileInput.files = dataTransfer.files;
                    showFilePreview(files);
                    showNotification(`📁 ${files.length} arquivo(s) selecionado(s)! Clique em "Iniciar Análise"`, 'info');
                }
            }
        });
        
        dropZone.addEventListener('click', () => {
            document.getElementById('fileInput').click();
        });
    }
    
    function showFilePreview(files) {
        let container = document.getElementById('filePreviewContainer');
        
        if (!container) {
            container = document.createElement('div');
            container.id = 'filePreviewContainer';
            container.className = 'mt-3';
            const dropZone = document.getElementById('dropZone');
            if (dropZone) {
                dropZone.insertAdjacentElement('afterend', container);
            }
        }
        
        let html = `
            <div class="bg-light p-3 rounded-3">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <strong><i class="fas fa-files me-2"></i>${files.length} arquivo(s) selecionado(s):</strong>
                    <button type="button" class="btn btn-sm btn-outline-danger" id="clearFilesBtn">
                        <i class="fas fa-trash-alt me-1"></i>Limpar
                    </button>
                </div>
                <div class="list-group list-group-flush bg-transparent" style="max-height: 200px; overflow-y: auto;">
        `;
        
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            const fileSizeKB = (file.size / 1024).toFixed(1);
            const isValid = file.size <= MAX_FILE_SIZE_KB * 1024;
            
            html += `
                <div class="list-group-item bg-transparent px-0 py-2">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <i class="fas ${file.name.endsWith('.csv') ? 'fa-file-csv' : 'fa-file-excel'} text-success me-2"></i>
                            <span class="small">${escapeHtml(file.name)}</span>
                            <span class="badge ${isValid ? 'bg-success' : 'bg-danger'} ms-2">${fileSizeKB}KB</span>
                        </div>
                    </div>
                </div>
            `;
        }
        
        html += `
                </div>
                <div class="text-muted small mt-2">
                    <i class="fas fa-info-circle me-1"></i>
                    Cada arquivo consome 1 crédito. Limite de ${MAX_FILE_SIZE_KB}KB por arquivo.
                </div>
            </div>
        `;
        
        container.innerHTML = html;
        
        document.getElementById('clearFilesBtn')?.addEventListener('click', () => {
            const fileInput = document.getElementById('fileInput');
            if (fileInput) fileInput.value = '';
            container.innerHTML = '';
            showNotification('Arquivos removidos', 'info');
        });
    }
    
    // ===== FUNÇÕES GLOBAIS PARA OS CARDS =====
    
    window.downloadReport = function(processId) {
        showNotification(`Download do relatório para ${processId} em breve`, 'info');
    };
    
    window.exportCsv = function(processId) {
        showNotification(`Exportação CSV para ${processId} em breve`, 'info');
    };
    
    window.viewDetails = function(processId) {
        showNotification(`Detalhes da análise ${processId} em breve`, 'info');
    };
    
    window.viewAnalysisDetails = function(analysisId) {
        showNotification(`Detalhes da análise ${analysisId} em breve`, 'info');
    };
    
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
            if (userNameEl) userNameEl.textContent = user.name || user.email?.split('@')[0] || 'Usuário';
            
            if (user.is_admin) {
                document.body.classList.add('is-admin');
                const adminBadge = document.getElementById('adminBadge');
                if (adminBadge) adminBadge.style.display = 'inline-block';
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
    
    const fileInput = document.getElementById('fileInput');
    if (fileInput) {
        fileInput.setAttribute('multiple', 'multiple');
        fileInput.addEventListener('change', (e) => {
            const files = e.target.files;
            if (files && files.length > 0) {
                showFilePreview(Array.from(files));
            }
        });
    }
    
    const autoUploadCheckbox = document.getElementById('autoUpload');
    if (autoUploadCheckbox) {
        autoUploadCheckbox.checked = localStorage.getItem('autoUpload') === 'true';
        autoUploadCheckbox.addEventListener('change', (e) => {
            localStorage.setItem('autoUpload', e.target.checked);
        });
    }
    
    console.log('✅ Dashboard inicializado com suporte a múltiplos arquivos!');
    console.log(`📁 Máximo de arquivos por vez: ${MAX_FILES_PER_BATCH}`);
    console.log(`📦 Limite por arquivo: ${MAX_FILE_SIZE_KB}KB`);
});

// Adiciona CSS para animações e cards
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
    @keyframes pulse-green {
        0%, 100% { box-shadow: 0 0 0 0 rgba(72, 187, 120, 0.4); }
        50% { box-shadow: 0 0 0 10px rgba(72, 187, 120, 0); }
    }
    
    .drag-over {
        background: linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%);
        border: 2px dashed #667eea !important;
        transform: scale(1.02);
        transition: all 0.2s ease;
    }
    
    .analysis-card {
        animation: slideInRight 0.3s ease-out;
    }
    
    .analysis-card .card {
        transition: transform 0.2s, box-shadow 0.2s;
    }
    
    .analysis-card .card:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 30px rgba(0,0,0,0.15) !important;
    }
    
    .metric-box {
        transition: all 0.2s;
    }
    
    .metric-box:hover {
        transform: translateY(-2px);
        background: #e9ecef !important;
    }
    
    .progress-bar {
        transition: width 0.5s ease;
    }
    
    .bg-gradient-primary {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    }
    
    .analyses-grid {
        display: flex;
        flex-direction: column;
        gap: 1rem;
    }
    
    .list-group-item {
        border-radius: 12px !important;
        margin-bottom: 8px;
        border: 1px solid #e2e8f0;
        transition: all 0.2s;
    }
    
    .list-group-item:hover {
        background: #f8fafc;
        transform: translateX(4px);
    }
    
    #activeAnalysesContainer {
        min-height: 200px;
    }
`;
document.head.appendChild(style);