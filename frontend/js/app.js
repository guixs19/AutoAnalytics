// frontend/js/app.js - ATUALIZADO COM SISTEMA DE CRÉDITOS

class AutoAnalytics {
    constructor() {
        // Configuração da API
        this.apiBase = window.location.hostname.includes('localhost') 
            ? 'http://localhost:8000/api'
            : '/api';
        
        this.currentProcessId = null;
        this.pollInterval = null;
        
        // Inicializar
        this.init();
    }
    
    async init() {
        this.initializeElements();
        this.bindEvents();
        await this.loadUserCredits(); // NOVO: Carregar créditos primeiro
        await this.loadDashboardStats();
        await this.loadRecentAnalyses();
        this.setupLogout(); // NOVO: Configurar logout
    }
    
    initializeElements() {
        // Formulário
        this.uploadForm = document.getElementById('uploadForm');
        this.fileInput = document.getElementById('fileInput');
        this.uploadButton = document.getElementById('uploadButton');
        this.dropArea = document.getElementById('dropArea');
        this.selectedFile = document.getElementById('selectedFile');
        this.fileName = document.getElementById('fileName');
        this.fileSize = document.getElementById('fileSize');
        this.removeFile = document.getElementById('removeFile');
        
        // Status
        this.statusContainer = document.getElementById('statusContainer');
        this.statusText = document.getElementById('statusText');
        this.processId = document.getElementById('processId');
        this.progressBar = document.getElementById('progressBar');
        this.progressText = document.getElementById('progressText');
        
        // Resultados
        this.resultContainer = document.getElementById('resultContainer');
        this.downloadButton = document.getElementById('downloadButton');
        this.newAnalysisButton = document.getElementById('newAnalysisButton');
        this.printButton = document.getElementById('printButton');
        
        // Relatório da IA
        this.aiReportText = document.getElementById('aiReportText');
        this.copyAiReport = document.getElementById('copyAiReport');
        
        // TensorFlow
        this.tensorflowTable = document.getElementById('tensorflowTable');
        this.tfSummary = document.getElementById('tfSummary');
        this.exportCsv = document.getElementById('exportCsv');
        this.exportJson = document.getElementById('exportJson');
        this.viewRawData = document.getElementById('viewRawData');
        
        // Dashboard
        this.totalRows = document.getElementById('totalRows');
        this.totalCols = document.getElementById('totalCols');
        this.aiUsed = document.getElementById('aiUsed');
        this.analisesHoje = document.getElementById('analisesHoje');
        this.totalAnalises = document.getElementById('totalAnalises');
        this.iaUtilizada = document.getElementById('iaUtilizada');
        this.recentAnalyses = document.getElementById('recentAnalyses');
        
        // NOVO: Elementos de créditos
        this.navbarCredits = document.getElementById('navbarCredits');
        this.uploadCredits = document.getElementById('uploadCredits');
        this.sidebarCredits = document.getElementById('sidebarCredits');
        this.userName = document.getElementById('userName');
        this.workshopName = document.getElementById('workshopName');
    }
    
    bindEvents() {
        // Upload (modificado para verificar créditos)
        this.uploadForm.addEventListener('submit', (e) => this.handleUpload(e));
        
        // Drag & Drop
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            this.dropArea.addEventListener(eventName, this.preventDefaults.bind(this));
        });
        
        this.dropArea.addEventListener('drop', (e) => this.handleDrop(e));
        this.dropArea.addEventListener('click', () => this.fileInput.click());
        this.fileInput.addEventListener('change', () => this.handleFileSelect());
        
        // Remover arquivo
        this.removeFile.addEventListener('click', (e) => {
            e.stopPropagation();
            this.fileInput.value = '';
            this.selectedFile.classList.add('d-none');
        });
        
        // Botões principais
        this.downloadButton.addEventListener('click', () => this.downloadResult());
        this.newAnalysisButton.addEventListener('click', () => this.resetAnalysis());
        this.printButton.addEventListener('click', () => window.print());
        
        // Relatório da IA
        this.copyAiReport.addEventListener('click', () => this.copyAiReportText());
        
        // TensorFlow
        this.exportCsv.addEventListener('click', () => this.exportAsCsv());
        this.exportJson.addEventListener('click', () => this.exportAsJson());
        this.viewRawData.addEventListener('click', () => this.showRawData());
    }
    
    // ===== NOVAS FUNÇÕES DE CRÉDITOS =====
    
    async loadUserCredits() {
        try {
            const response = await this.fetchWithAuth(`${this.apiBase}/payments/balance`);
            if (response.ok) {
                const data = await response.json();
                this.updateCreditsDisplay(data.credits || 0);
                
                // Salvar no localStorage
                localStorage.setItem('user_credits', data.credits || 0);
                localStorage.setItem('user_name', data.user_name || 'Usuário');
                localStorage.setItem('workshop_name', data.workshop_name || 'Oficina');
            }
        } catch (error) {
            console.error('Erro ao carregar créditos:', error);
        }
    }
    
    updateCreditsDisplay(credits) {
        // Atualizar todos os elementos que mostram créditos
        if (this.navbarCredits) this.navbarCredits.textContent = credits;
        if (this.uploadCredits) this.uploadCredits.textContent = credits;
        if (this.sidebarCredits) this.sidebarCredits.textContent = credits;
        
        // Atualizar nome do usuário
        if (this.userName) {
            this.userName.textContent = localStorage.getItem('user_name') || 'Usuário';
        }
        if (this.workshopName) {
            this.workshopName.textContent = localStorage.getItem('workshop_name') || 'Oficina';
        }
    }
    
    async checkCreditsBeforeUpload() {
        try {
            const response = await this.fetchWithAuth(`${this.apiBase}/payments/check-analysis`);
            if (response.ok) {
                const data = await response.json();
                
                if (!data.has_credits) {
                    this.showCreditsModal();
                    return false;
                }
                return true;
            }
        } catch (error) {
            console.error('Erro ao verificar créditos:', error);
        }
        return false;
    }
    
    showCreditsModal() {
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
        const currentCredits = this.navbarCredits?.textContent || '0';
        if (modalCredits) modalCredits.textContent = currentCredits;
        
        // Mostrar modal
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
    }
    
    // ===== FUNÇÕES EXISTENTES MODIFICADAS =====
    
    preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        
        if (files.length > 0) {
            this.fileInput.files = files;
            this.handleFileSelect();
        }
    }
    
    handleFileSelect() {
        const file = this.fileInput.files[0];
        if (file) {
            this.fileName.textContent = file.name;
            this.fileSize.textContent = this.formatFileSize(file.size);
            this.selectedFile.classList.remove('d-none');
        }
    }
    
    async handleUpload(e) {
        e.preventDefault();
        
        const file = this.fileInput.files[0];
        if (!file) {
            this.showAlert('Selecione um arquivo primeiro', 'warning');
            return;
        }
        
        // Validar extensão
        const ext = file.name.toLowerCase().slice(-4);
        if (!['.csv', '.xlsx', 'xls'].some(e => ext.endsWith(e))) {
            this.showAlert('Formato não suportado. Use CSV ou Excel.', 'error');
            return;
        }
        
        // NOVO: Verificar créditos primeiro
        const hasCredits = await this.checkCreditsBeforeUpload();
        if (!hasCredits) return;
        
        const analysisType = document.getElementById('tipoAnalise').value;
        const aiModel = document.getElementById('modeloIA').value;
        
        const formData = new FormData();
        formData.append('file', file);
        formData.append('analysis_type', analysisType);
        formData.append('ai_model', aiModel);
        
        // Desabilitar botão
        this.uploadButton.disabled = true;
        this.uploadButton.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i> Enviando...';
        
        try {
            const response = await fetch(`${this.apiBase}/upload`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                },
                body: formData
            });
            
            const data = await response.json();
            
            if (response.ok) {
                this.currentProcessId = data.process_id;
                this.showAlert('Análise iniciada com sucesso!', 'success');
                
                // NOVO: Atualizar créditos (já deduzidos no backend)
                await this.loadUserCredits();
                
                this.showProgress();
                this.startProgressPolling();
            } else {
                if (data.detail && data.detail.error === 'Créditos insuficientes') {
                    this.showCreditsModal();
                } else {
                    this.showAlert(data.detail || 'Erro no upload', 'error');
                }
                this.resetUploadButton();
            }
            
        } catch (error) {
            this.showAlert('Erro de conexão com o servidor', 'error');
            this.resetUploadButton();
        }
    }
    
    showProgress() {
        this.statusContainer.classList.remove('d-none');
        this.resultContainer.classList.add('d-none');
        this.processId.textContent = this.currentProcessId;
    }
    
    async startProgressPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
        }
        
        this.pollInterval = setInterval(async () => {
            if (!this.currentProcessId) return;
            
            try {
                const status = await this.getStatus(this.currentProcessId);
                
                // Atualizar progresso
                this.updateProgress(status.progress || 0);
                this.statusText.textContent = this.getStatusText(status);
                
                // Se completou ou erro
                if (status.status === 'completed' || status.status === 'error') {
                    clearInterval(this.pollInterval);
                    
                    if (status.status === 'completed') {
                        this.showResult(status);
                        await this.loadDashboardStats();
                        await this.loadRecentAnalyses();
                        // NOVO: Recarregar créditos (pode ter mudado)
                        await this.loadUserCredits();
                    } else {
                        this.showAlert('Erro na análise: ' + (status.error || 'Desconhecido'), 'error');
                    }
                    
                    this.resetUploadButton();
                }
                
            } catch (error) {
                console.error('Erro no polling:', error);
            }
        }, 2000);
    }
    
    updateProgress(percent) {
        this.progressBar.style.width = `${percent}%`;
        this.progressBar.setAttribute('aria-valuenow', percent);
        this.progressText.textContent = `${percent}%`;
        
        // Atualizar etapas
        this.updateStepCards(percent);
    }
    
    updateStepCards(percent) {
        const steps = document.querySelectorAll('.step-card');
        const activeStep = Math.floor(percent / 20);
        
        steps.forEach((step, index) => {
            if (index <= activeStep) {
                step.classList.add('active');
            } else {
                step.classList.remove('active');
            }
        });
    }
    
    getStatusText(status) {
        if (status.status === 'uploaded') return 'Arquivo recebido';
        if (status.status === 'preprocessing') return 'Pré-processando dados';
        if (status.status === 'cardinality') return 'Aplicando sistema de cardinalidade';
        if (status.status === 'tensorflow') return 'Executando TensorFlow';
        if (status.status === 'ai_analysis') return 'Analisando com IA';
        if (status.status === 'generating_report') return 'Gerando relatório';
        if (status.status === 'completed') return 'Análise concluída';
        return 'Processando...';
    }
    
    async getStatus(processId) {
        try {
            const response = await fetch(`${this.apiBase}/status/${processId}`, {
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                }
            });
            return await response.json();
        } catch {
            return { status: 'unknown' };
        }
    }
    
    showResult(result) {
        this.statusContainer.classList.add('d-none');
        this.resultContainer.classList.remove('d-none');
        
        // Atualizar estatísticas
        if (result.summary) {
            this.totalRows.textContent = result.summary.linhas || 0;
            this.totalCols.textContent = result.summary.colunas || 0;
            this.aiUsed.textContent = result.ai_used ? 'Sim' : 'Não';
        }
        
        // Mostrar relatório da IA
        this.displayAiReport(result);
        
        // Mostrar previsões do TensorFlow
        this.displayTensorFlowResults(result);
    }
    
    displayAiReport(result) {
        if (!this.aiReportText) return;
        
        let report = '';
        
        if (result.ai_report) {
            report = result.ai_report;
        } else if (result.ai_response) {
            const ai = result.ai_response;
            
            report = "🤖 RELATÓRIO DA IA - AUTOANALYTICS\n";
            report += "=".repeat(50) + "\n\n";
            
            if (ai.insights && ai.insights.length > 0) {
                report += "📊 INSIGHTS PRINCIPAIS:\n";
                report += "-".repeat(30) + "\n";
                ai.insights.forEach((insight, i) => {
                    report += `${i + 1}. ${insight}\n`;
                });
                report += "\n";
            }
            
            if (ai.recommendations && ai.recommendations.length > 0) {
                report += "💡 RECOMENDAÇÕES:\n";
                report += "-".repeat(30) + "\n";
                ai.recommendations.forEach((rec, i) => {
                    report += `✅ ${rec}\n`;
                });
                report += "\n";
            }
            
            if (ai.immediate_action) {
                report += "⚡ AÇÃO IMEDIATA:\n";
                report += "-".repeat(30) + "\n";
                report += `🎯 ${ai.immediate_action}\n\n`;
            }
            
            report += "📋 METADADOS:\n";
            report += "-".repeat(30) + "\n";
            report += `Processo: ${this.currentProcessId}\n`;
            report += `Data: ${new Date().toLocaleString('pt-BR')}\n`;
            report += `IA utilizada: ${ai.ai_available !== false ? 'Sim' : 'Não'}\n`;
            
        } else {
            report = "📋 RELATÓRIO BÁSICO\n";
            report += "=".repeat(50) + "\n\n";
            report += `Processo: ${this.currentProcessId}\n`;
            report += `Status: Análise concluída\n`;
            report += `Registros: ${result.summary?.linhas || 'N/A'}\n`;
            report += `Colunas: ${result.summary?.colunas || 'N/A'}\n\n`;
            report += "Relatório completo disponível para download.";
        }
        
        this.aiReportText.value = report;
    }
    
    displayTensorFlowResults(result) {
        const tableBody = this.tensorflowTable.querySelector('tbody');
        if (!tableBody) return;
        
        tableBody.innerHTML = '';
        
        if (result.predictions && Array.isArray(result.predictions)) {
            const predictions = result.predictions;
            let positiveCount = 0;
            let negativeCount = 0;
            
            predictions.forEach((pred, index) => {
                const value = typeof pred === 'object' ? pred.value || pred.prediction || 0.5 : pred;
                const confidence = typeof pred === 'object' ? pred.confidence || 0.8 : 0.8;
                const isPositive = value > 0.5;
                
                if (isPositive) positiveCount++;
                else negativeCount++;
                
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${index + 1}</td>
                    <td class="${isPositive ? 'prediction-positive' : 'prediction-negative'}">
                        ${value.toFixed(4)}
                    </td>
                    <td>
                        ${(confidence * 100).toFixed(1)}%
                        <div class="confidence-bar">
                            <div class="confidence-fill" style="width: ${confidence * 100}%"></div>
                        </div>
                    </td>
                    <td>
                        <span class="badge ${isPositive ? 'bg-success' : 'bg-danger'} badge-prediction">
                            ${isPositive ? 'POSITIVO' : 'NEGATIVO'}
                        </span>
                    </td>
                    <td>
                        <button class="btn btn-sm btn-outline-info view-details" data-index="${index}">
                            <i class="fas fa-eye"></i>
                        </button>
                    </td>
                `;
                
                tableBody.appendChild(row);
            });
            
            // Atualizar resumo
            this.tfSummary.innerHTML = `
                <i class="fas fa-chart-pie me-1"></i>
                Total: ${predictions.length} previsões | 
                <span class="text-success">${positiveCount} positivas</span> | 
                <span class="text-danger">${negativeCount} negativas</span>
            `;
            
            // Adicionar eventos aos botões de detalhes
            tableBody.querySelectorAll('.view-details').forEach(button => {
                button.addEventListener('click', (e) => {
                    const index = parseInt(e.target.closest('button').dataset.index);
                    this.showPredictionDetails(index, predictions[index]);
                });
            });
            
        } else {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="5" class="text-center text-muted py-4">
                        <i class="fas fa-info-circle me-2"></i>
                        Previsões do TensorFlow não disponíveis
                    </td>
                </tr>
            `;
            this.tfSummary.textContent = "TensorFlow não retornou previsões para esta análise.";
        }
    }
    
    showPredictionDetails(index, prediction) {
        const modalHtml = `
            <div class="modal fade" id="predictionModal" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">
                                <i class="fas fa-search me-2"></i>
                                Detalhes da Previsão #${index + 1}
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="mb-3">
                                <strong>Valor:</strong> 
                                <span class="${(prediction.value || prediction) > 0.5 ? 'text-success' : 'text-danger'}">
                                    ${(prediction.value || prediction).toFixed(4)}
                                </span>
                            </div>
                            <div class="mb-3">
                                <strong>Confiança:</strong> 
                                ${((prediction.confidence || 0.8) * 100).toFixed(1)}%
                            </div>
                            <div class="mb-3">
                                <strong>Classificação:</strong> 
                                <span class="badge ${(prediction.value || prediction) > 0.5 ? 'bg-success' : 'bg-danger'}">
                                    ${(prediction.value || prediction) > 0.5 ? 'POSITIVO' : 'NEGATIVO'}
                                </span>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Fechar</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // Remover modal anterior
        const existingModal = document.getElementById('predictionModal');
        if (existingModal) existingModal.remove();
        
        // Adicionar novo modal
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        // Mostrar modal
        const modal = new bootstrap.Modal(document.getElementById('predictionModal'));
        modal.show();
    }
    
    async downloadResult() {
        if (!this.currentProcessId) return;
        
        try {
            const response = await fetch(`${this.apiBase}/result/${this.currentProcessId}`, {
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                }
            });
            
            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `analise_${this.currentProcessId}.txt`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
                
                this.showAlert('Download iniciado!', 'success');
            } else {
                this.showAlert('Erro ao baixar resultado', 'error');
            }
            
        } catch (error) {
            this.showAlert('Erro de conexão', 'error');
        }
    }
    
    copyAiReportText() {
        if (!this.aiReportText.value) {
            this.showAlert('Nenhum relatório para copiar', 'warning');
            return;
        }
        
        this.aiReportText.select();
        document.execCommand('copy');
        
        // Feedback visual
        const originalText = this.copyAiReport.innerHTML;
        this.copyAiReport.innerHTML = '<i class="fas fa-check me-1"></i> Copiado!';
        this.copyAiReport.classList.remove('btn-outline-secondary');
        this.copyAiReport.classList.add('btn-success');
        
        setTimeout(() => {
            this.copyAiReport.innerHTML = originalText;
            this.copyAiReport.classList.remove('btn-success');
            this.copyAiReport.classList.add('btn-outline-secondary');
        }, 2000);
    }
    
    async exportAsCsv() {
        if (!this.currentProcessId) return;
        
        try {
            const response = await fetch(`${this.apiBase}/export/${this.currentProcessId}?format=csv`, {
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                }
            });
            
            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `predictions_${this.currentProcessId}.csv`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
                
                this.showAlert('CSV exportado com sucesso!', 'success');
            }
        } catch (error) {
            this.showAlert('Erro ao exportar CSV', 'error');
        }
    }
    
    async exportAsJson() {
        if (!this.currentProcessId) return;
        
        try {
            const response = await fetch(`${this.apiBase}/result/${this.currentProcessId}`, {
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                }
            });
            
            if (response.ok) {
                const data = await response.json();
                const jsonStr = JSON.stringify(data, null, 2);
                const blob = new Blob([jsonStr], { type: 'application/json' });
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `analise_${this.currentProcessId}.json`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
                
                this.showAlert('JSON exportado com sucesso!', 'success');
            }
        } catch (error) {
            this.showAlert('Erro ao exportar JSON', 'error');
        }
    }
    
    async showRawData() {
        if (!this.currentProcessId) return;
        
        const modalHtml = `
            <div class="modal fade raw-data-modal" id="rawDataModal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">
                                <i class="fas fa-database me-2"></i>
                                Dados Brutos da Análise
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="raw-data-content" id="rawDataContent">
                                Carregando dados...
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Fechar</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // Remover modal anterior
        const existingModal = document.getElementById('rawDataModal');
        if (existingModal) existingModal.remove();
        
        // Adicionar novo modal
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        // Mostrar modal
        const modal = new bootstrap.Modal(document.getElementById('rawDataModal'));
        modal.show();
        
        // Carregar dados
        await this.loadRawData();
    }
    
    async loadRawData() {
        const contentDiv = document.getElementById('rawDataContent');
        if (!contentDiv) return;
        
        contentDiv.textContent = 'Carregando...';
        
        try {
            const response = await fetch(`${this.apiBase}/raw/${this.currentProcessId}`, {
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                }
            });
            if (response.ok) {
                const data = await response.json();
                contentDiv.textContent = JSON.stringify(data, null, 2);
            } else {
                contentDiv.textContent = 'Erro ao carregar dados.';
            }
        } catch (error) {
            contentDiv.textContent = 'Erro de conexão: ' + error.message;
        }
    }
    
    resetAnalysis() {
        this.resultContainer.classList.add('d-none');
        this.selectedFile.classList.add('d-none');
        this.fileInput.value = '';
        this.aiReportText.value = '';
        this.currentProcessId = null;
        
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
        
        this.resetUploadButton();
    }
    
    resetUploadButton() {
        this.uploadButton.disabled = false;
        this.uploadButton.innerHTML = '<i class="fas fa-play-circle me-2"></i> Iniciar Análise Inteligente (1 crédito)';
    }
    
    async loadDashboardStats() {
        try {
            const response = await fetch(`${this.apiBase}/stats`, {
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                }
            });
            const stats = await response.json();
            
            if (stats) {
                this.totalAnalises.textContent = stats.total_analises || 0;
                this.analisesHoje.textContent = stats.analises_hoje || 0;
                this.iaUtilizada.textContent = stats.ia_utilizada || 0;
            }
        } catch (error) {
            console.error('Erro ao carregar stats:', error);
        }
    }
    
    async loadRecentAnalyses() {
        try {
            const response = await fetch(`${this.apiBase}/recent-analyses?limit=3`, {
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                }
            });
            const analyses = await response.json();
            
            if (Array.isArray(analyses) && analyses.length > 0) {
                this.recentAnalyses.innerHTML = '';
                
                analyses.forEach(analysis => {
                    const item = document.createElement('div');
                    item.className = 'timeline-item';
                    item.innerHTML = `
                        <div class="timeline-marker"></div>
                        <div class="timeline-content">
                            <h6>${analysis.filename || 'Arquivo'}</h6>
                            <p class="mb-1 small">${analysis.analysis_type || 'Análise'}</p>
                            <small class="text-muted">${new Date(analysis.timestamp).toLocaleString('pt-BR')}</small>
                        </div>
                    `;
                    this.recentAnalyses.appendChild(item);
                });
            }
        } catch (error) {
            console.error('Erro ao carregar análises recentes:', error);
        }
    }
    
    setupLogout() {
        const logoutBtn = document.getElementById('logoutBtn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.logout();
            });
        }
    }
    
    logout() {
        if (confirm('Deseja realmente sair?')) {
            localStorage.removeItem('access_token');
            localStorage.removeItem('refresh_token');
            localStorage.removeItem('user_name');
            localStorage.removeItem('user_email');
            localStorage.removeItem('workshop_name');
            localStorage.removeItem('user_credits');
            window.location.href = 'login.html';
        }
    }
    
    // ===== FUNÇÕES DE UTILIDADE =====
    
    async fetchWithAuth(url, options = {}) {
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
            const refreshed = await this.refreshToken();
            if (refreshed) {
                // Tentar novamente com novo token
                return this.fetchWithAuth(url, options);
            } else {
                this.logout();
            }
        }
        
        return response;
    }
    
    async refreshToken() {
        const refreshToken = localStorage.getItem('refresh_token');
        
        if (!refreshToken) return false;
        
        try {
            const response = await fetch(`${this.apiBase}/auth/refresh`, {
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
    
    showAlert(message, type = 'info') {
        // Criar alerta Bootstrap
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
        
        // Adicionar ao body
        document.body.appendChild(alertDiv);
        
        // Auto-remover após 5 segundos
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.remove();
            }
        }, 5000);
    }
    
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
}

// Inicializar quando a página carregar
document.addEventListener('DOMContentLoaded', () => {
    window.app = new AutoAnalytics();
});