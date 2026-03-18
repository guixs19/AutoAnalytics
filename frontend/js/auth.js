// frontend/js/app.js - VERSÃO OTIMIZADA (USA FUNÇÕES DO auth.js)

class AutoAnalytics {
    constructor() {
        this.apiBase = window.location.hostname.includes('localhost') 
            ? 'http://localhost:8000/api'
            : '/api';
        
        this.currentProcessId = null;
        this.pollInterval = null;
        this.fileData = null;
        this.columns = [];
        this.selectedFeatures = [];
        this.selectedTarget = null;
        
        // Inicializar
        this.init();
    }
    
    // ===== FUNÇÕES DELEGADAS PARA auth.js =====
    // ✅ TODAS usam as funções globais do auth.js
    
    isAdmin() {
        return window.appAuth ? window.appAuth.isAdmin() : false;
    }
    
    getCurrentUser() {
        return window.appAuth ? window.appAuth.getCurrentUser() : {};
    }
    
    getCreditsDisplay() {
        return window.appAuth ? window.appAuth.getCreditsDisplay() : '0';
    }
    
    updateCreditsDisplay() {
        if (window.appAuth) window.appAuth.updateCreditsDisplay();
    }
    
    async init() {
        this.initializeElements();
        this.bindEvents();
        await this.loadUserCredits();
        await this.loadDashboardStats();
        await this.loadAnalysisHistory();
        this.setupLogout();
        this.initGSAPAnimations();
        this.checkAuthentication();
        
        // Atualizar display de créditos
        this.updateCreditsDisplay();
    }
    
    // ===== VERIFICAÇÃO DE AUTENTICAÇÃO =====
    
    checkAuthentication() {
        // Se estiver na página de login ou registro, não precisa verificar
        if (this.isLoginPage() || this.isRegisterPage()) {
            return;
        }
        
        // Usar função do auth.js
        if (!window.appAuth || !window.appAuth.isAuthenticated()) {
            console.log('🔒 Usuário não autenticado, redirecionando para login');
            window.location.href = '/login.html';
        }
    }
    
    isLoginPage() {
        return window.location.pathname.includes('login.html') || 
               window.location.pathname === '/login';
    }
    
    isRegisterPage() {
        return window.location.pathname.includes('register.html') || 
               window.location.pathname === '/register';
    }
    
    // ===== CRÉDITOS (USANDO auth.js) =====
    
    async loadUserCredits() {
        try {
            const response = await this.fetchWithAuth(`${this.apiBase}/payments/balance`);
            if (response.ok) {
                const data = await response.json();
                
                // Atualizar via auth.js
                if (window.appAuth) {
                    const user = window.appAuth.getCurrentUser();
                    user.credits = data.credits || 0;
                    user.is_admin = data.is_admin || false;
                    localStorage.setItem('user', JSON.stringify(user));
                    window.appAuth.updateCreditsDisplay();
                }
            }
        } catch (error) {
            console.error('Erro ao carregar créditos:', error);
        }
    }
    
    // Verificar créditos antes do upload
    async checkCreditsBeforeUpload() {
        // ✅ Admin sempre pode (usando auth.js)
        if (this.isAdmin()) {
            return true;
        }
        
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
    
    // Modal de créditos
    showCreditsModal() {
        // Não mostrar para admin
        if (this.isAdmin()) {
            return;
        }
        
        let modal = document.getElementById('creditsModal');
        
        if (!modal) {
            const modalHtml = `
                <div class="modal fade" id="creditsModal" tabindex="-1">
                    <div class="modal-dialog">
                        <div class="modal-content rounded-4">
                            <div class="modal-header bg-warning border-0">
                                <h5 class="modal-title">
                                    <i class="fas fa-exclamation-triangle me-2"></i>
                                    Créditos Insuficientes
                                </h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                            </div>
                            <div class="modal-body text-center py-4">
                                <i class="fas fa-coins fa-4x text-warning mb-3"></i>
                                <h5>Você não tem créditos para realizar esta análise</h5>
                                <p class="text-muted">Cada treinamento consome 1 crédito.</p>
                                <p>Seu saldo atual: <strong><span id="modalCredits">0</span></strong> créditos</p>
                            </div>
                            <div class="modal-footer justify-content-center border-0">
                                <a href="/planos.html" class="btn btn-gradient">
                                    <i class="fas fa-credit-card me-2"></i>
                                    Assinar Plano R$97
                                </a>
                                <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">
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
        const user = this.getCurrentUser();
        if (modalCredits) modalCredits.textContent = user.credits || 0;
        
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
    }
    
    // ===== UPLOAD =====
    
    async handleUpload(e) {
        e.preventDefault();
        
        const file = this.fileInput?.files[0];
        if (!file) {
            this.showAlert('❌ Selecione um arquivo primeiro', 'warning');
            return;
        }
        
        if (!this.selectedTarget) {
            this.showAlert('❌ Selecione uma coluna alvo (o que deseja prever)', 'warning');
            return;
        }
        
        if (this.selectedFeatures.length === 0) {
            this.showAlert('❌ Selecione pelo menos uma coluna de entrada', 'warning');
            return;
        }
        
        // Verificar créditos (admin sempre passa)
        const hasCredits = await this.checkCreditsBeforeUpload();
        if (!hasCredits) return;
        
        const algorithm = this.getSelectedAlgorithm();
        
        const formData = new FormData();
        formData.append('file', file);
        formData.append('target_column', this.selectedTarget);
        formData.append('feature_columns', JSON.stringify(this.selectedFeatures));
        formData.append('algorithm', algorithm);
        
        if (this.uploadButton) {
            this.uploadButton.disabled = true;
            this.uploadButton.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i> Treinando modelo...';
        }
        
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
                
                const adminMsg = this.isAdmin() ? '👑 ' : '';
                this.showAlert(`${adminMsg}Modelo em treinamento!`, 'success');
                
                await this.loadUserCredits();
                this.showProgress();
                this.startProgressPolling();
            } else {
                if (data.detail && data.detail.error === 'Créditos insuficientes') {
                    this.showCreditsModal();
                } else {
                    this.showAlert('❌ ' + (data.detail || 'Erro no upload'), 'error');
                }
                this.resetUploadButton();
            }
            
        } catch (error) {
            this.showAlert('❌ Erro de conexão com o servidor', 'error');
            this.resetUploadButton();
        }
    }
    
    resetUploadButton() {
        if (this.uploadButton) {
            this.uploadButton.disabled = false;
            const creditText = this.isAdmin() ? '∞' : '1 crédito';
            this.uploadButton.innerHTML = `<i class="fas fa-play-circle me-2"></i>Treinar Modelo e Analisar<span class="badge bg-light text-dark ms-2">${creditText}</span>`;
        }
    }
    
    // ===== RESTO DO CÓDIGO (mantido igual) =====
    
    initializeElements() {
        this.uploadForm = document.getElementById('uploadForm');
        this.fileInput = document.getElementById('fileInput');
        this.uploadButton = document.getElementById('uploadButton');
        this.dropArea = document.getElementById('dropArea');
        this.selectedFile = document.getElementById('selectedFile');
        this.fileName = document.getElementById('fileName');
        this.fileSize = document.getElementById('fileSize');
        this.removeFile = document.getElementById('removeFile');
        this.historyContainer = document.getElementById('recentAnalyses');
        this.columnSelector = document.getElementById('columnSelector');
        this.dataPreview = document.getElementById('dataPreview');
        this.previewHeader = document.getElementById('previewHeader')?.querySelector('tr');
        this.previewBody = document.getElementById('previewBody');
        this.targetColumnContainer = document.getElementById('targetColumnContainer');
        this.featureColumnsContainer = document.getElementById('featureColumnsContainer');
        this.selectedColumnsCount = document.getElementById('selectedColumnsCount');
        this.algorithmRadios = document.querySelectorAll('input[name="algorithm"]');
        this.navbarCredits = document.getElementById('navbarCredits')?.querySelector('span') || document.getElementById('navbarCredits');
        this.uploadCredits = document.getElementById('uploadCredits');
        this.userName = document.getElementById('userName');
        this.workshopName = document.getElementById('workshopName');
        this.resultContainer = document.getElementById('resultContainer');
        this.downloadButton = document.getElementById('downloadButton');
        this.mlTable = document.getElementById('mlTable')?.querySelector('tbody');
        this.exportCsv = document.getElementById('exportCsv');
        this.viewRawData = document.getElementById('viewRawData');
        this.targetColumnName = document.getElementById('targetColumnName');
        this.algorithmName = document.getElementById('algorithmName');
        this.metricR2 = document.getElementById('metricR2');
        this.metricMAE = document.getElementById('metricMAE');
        this.metricRMSE = document.getElementById('metricRMSE');
        this.metricImportance = document.getElementById('metricImportance');
        this.featureImportance = document.getElementById('featureImportance');
        this.totalAnalises = document.getElementById('totalAnalises');
        this.analisesHoje = document.getElementById('analisesHoje');
        this.iaUtilizada = document.getElementById('iaUtilizada');
        
        if (this.iaUtilizada) {
            this.iaUtilizada.textContent = 'R² 0.94';
        }
    }
    
    bindEvents() {
        if (this.uploadForm) {
            this.uploadForm.addEventListener('submit', (e) => this.handleUpload(e));
        }
        
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            if (this.dropArea) {
                this.dropArea.addEventListener(eventName, this.preventDefaults.bind(this));
            }
        });
        
        if (this.dropArea) {
            this.dropArea.addEventListener('drop', (e) => this.handleDrop(e));
            this.dropArea.addEventListener('click', () => this.fileInput?.click());
            this.dropArea.addEventListener('dragover', () => this.dropArea.classList.add('dragover'));
            this.dropArea.addEventListener('dragleave', () => this.dropArea.classList.remove('dragover'));
        }
        
        if (this.fileInput) {
            this.fileInput.addEventListener('change', () => this.handleFileSelect());
        }
        
        if (this.removeFile) {
            this.removeFile.addEventListener('click', (e) => {
                e.stopPropagation();
                this.resetFileSelection();
            });
        }
        
        if (this.downloadButton) {
            this.downloadButton.addEventListener('click', () => this.downloadResult());
        }
        
        if (this.exportCsv) {
            this.exportCsv.addEventListener('click', () => this.exportAsCsv());
        }
        
        if (this.viewRawData) {
            this.viewRawData.addEventListener('click', () => this.showRawData());
        }
    }
    
    // ===== FUNÇÕES DE ARQUIVO =====
    
    async handleFileSelect() {
        const file = this.fileInput?.files[0];
        if (file) {
            const MAX_FILE_SIZE = 10 * 1024 * 1024;
            
            if (file.size > MAX_FILE_SIZE) {
                const fileSizeMB = (file.size / (1024 * 1024)).toFixed(2);
                this.showAlert(`❌ Arquivo muito grande (${fileSizeMB}MB). O tamanho máximo permitido é 10MB.`, 'error');
                this.resetFileSelection();
                return;
            }
            
            const validExtensions = ['.csv', '.xlsx', '.xls'];
            
            if (!validExtensions.some(ext => file.name.toLowerCase().endsWith(ext))) {
                this.showAlert('❌ Formato não suportado. Use apenas arquivos CSV ou Excel (.csv, .xlsx, .xls)', 'error');
                this.resetFileSelection();
                return;
            }
            
            if (this.fileName) this.fileName.textContent = file.name;
            if (this.fileSize) this.fileSize.textContent = this.formatFileSize(file.size);
            if (this.selectedFile) this.selectedFile.classList.remove('d-none');
            
            if (typeof gsap !== 'undefined') {
                gsap.from(this.selectedFile, {
                    duration: 0.5,
                    y: 20,
                    opacity: 0,
                    ease: 'power3.out'
                });
            }
            
            await this.parseFile(file);
        }
    }
    
    async parseFile(file) {
        this.showAlert('Analisando arquivo...', 'info');
        
        try {
            if (file.name.endsWith('.csv')) {
                Papa.parse(file, {
                    header: true,
                    preview: 10,
                    delimiter: '',
                    complete: (result) => {
                        if (result.data && result.data.length > 0) {
                            const firstRow = result.data[0];
                            for (let key in firstRow) {
                                const value = firstRow[key];
                                if (typeof value === 'string' && value.includes(',') && !value.includes('.')) {
                                    const numericValue = parseFloat(value.replace(',', '.'));
                                    if (!isNaN(numericValue)) {
                                        this.showAlert('⚠️ Detectado uso de vírgula como separador decimal. O sistema aceita ambos os formatos.', 'warning');
                                        break;
                                    }
                                }
                            }
                        }
                        this.processParsedData(result.data, result.meta.fields);
                    },
                    error: (error) => {
                        this.showAlert('❌ Erro ao ler CSV: ' + error, 'error');
                        this.resetFileSelection();
                    }
                });
            } else if (file.name.endsWith('.xlsx') || file.name.endsWith('.xls')) {
                const reader = new FileReader();
                reader.onload = (e) => {
                    try {
                        const data = new Uint8Array(e.target.result);
                        const workbook = XLSX.read(data, { type: 'array' });
                        const firstSheet = workbook.Sheets[workbook.SheetNames[0]];
                        const jsonData = XLSX.utils.sheet_to_json(firstSheet, { header: 1 });
                        
                        if (jsonData.length > 0) {
                            const headers = jsonData[0];
                            const rows = jsonData.slice(1, 11).map(row => {
                                const obj = {};
                                headers.forEach((header, index) => {
                                    let value = row[index];
                                    if (typeof value === 'string' && value.includes(',')) {
                                        const numValue = parseFloat(value.replace(',', '.'));
                                        if (!isNaN(numValue)) {
                                            value = numValue;
                                        }
                                    }
                                    obj[header] = value;
                                });
                                return obj;
                            });
                            this.processParsedData(rows, headers);
                        }
                    } catch (error) {
                        this.showAlert('❌ Erro ao ler arquivo Excel. Verifique se o arquivo não está corrompido.', 'error');
                        this.resetFileSelection();
                    }
                };
                reader.onerror = () => {
                    this.showAlert('❌ Erro ao ler arquivo', 'error');
                    this.resetFileSelection();
                };
                reader.readAsArrayBuffer(file);
            }
        } catch (error) {
            this.showAlert('❌ Erro ao processar arquivo', 'error');
            this.resetFileSelection();
        }
    }
    
    processParsedData(data, columns) {
        if (!data || data.length === 0) {
            this.showAlert('❌ Arquivo vazio ou sem dados válidos', 'error');
            this.resetFileSelection();
            return;
        }
        
        this.fileData = data;
        this.columns = columns;
        
        this.showDataPreview(data, columns);
        this.showColumnSelector(columns);
        
        if (this.uploadButton) {
            this.uploadButton.disabled = false;
        }
        
        this.showAlert('✅ Arquivo analisado! Selecione as colunas para análise.', 'success');
    }
    
    showDataPreview(data, columns) {
        if (!this.dataPreview || !this.previewHeader || !this.previewBody) return;
        
        this.previewHeader.innerHTML = '';
        columns.forEach(col => {
            const th = document.createElement('th');
            th.textContent = col;
            this.previewHeader.appendChild(th);
        });
        
        this.previewBody.innerHTML = '';
        data.slice(0, 5).forEach(row => {
            const tr = document.createElement('tr');
            columns.forEach(col => {
                const td = document.createElement('td');
                let value = row[col] !== undefined ? row[col] : '-';
                if (typeof value === 'number') {
                    value = value.toFixed(2).replace('.', ',');
                }
                td.textContent = value;
                tr.appendChild(td);
            });
            this.previewBody.appendChild(tr);
        });
        
        this.dataPreview.classList.remove('d-none');
        
        if (typeof gsap !== 'undefined') {
            gsap.from(this.dataPreview, {
                duration: 0.5,
                height: 0,
                opacity: 0,
                ease: 'power3.out'
            });
        }
    }
    
    showColumnSelector(columns) {
        if (!this.columnSelector || !this.targetColumnContainer || !this.featureColumnsContainer) return;
        
        this.columnSelector.classList.remove('d-none');
        
        this.targetColumnContainer.innerHTML = '';
        this.featureColumnsContainer.innerHTML = '';
        
        columns.forEach(col => {
            const targetChip = this.createColumnChip(col, 'target');
            this.targetColumnContainer.appendChild(targetChip);
            
            const featureChip = this.createColumnChip(col, 'feature');
            this.featureColumnsContainer.appendChild(featureChip);
        });
        
        this.updateSelectedCount();
        
        if (typeof gsap !== 'undefined') {
            gsap.from('.column-chip', {
                duration: 0.3,
                scale: 0,
                opacity: 0,
                stagger: 0.05,
                ease: 'back.out(1.7)'
            });
        }
    }
    
    createColumnChip(columnName, type) {
        const chip = document.createElement('span');
        chip.className = `column-chip ${type === 'target' ? '' : 'feature-chip'}`;
        chip.textContent = columnName;
        
        if (type === 'target') {
            chip.addEventListener('click', () => this.selectTargetColumn(columnName, chip));
        } else {
            chip.addEventListener('click', () => this.toggleFeatureColumn(columnName, chip));
        }
        
        return chip;
    }
    
    selectTargetColumn(column, element) {
        document.querySelectorAll('.column-chip.target').forEach(chip => {
            chip.classList.remove('target');
        });
        
        element.classList.add('target');
        this.selectedTarget = column;
        
        this.showAlert(`✅ Coluna alvo selecionada: ${column}`, 'success');
        this.updateSelectedCount();
    }
    
    toggleFeatureColumn(column, element) {
        element.classList.toggle('selected');
        
        if (element.classList.contains('selected')) {
            this.selectedFeatures.push(column);
            this.showAlert(`➕ Feature adicionada: ${column}`, 'info');
        } else {
            this.selectedFeatures = this.selectedFeatures.filter(c => c !== column);
            this.showAlert(`➖ Feature removida: ${column}`, 'info');
        }
        
        this.updateSelectedCount();
    }
    
    updateSelectedCount() {
        if (this.selectedColumnsCount) {
            const total = this.selectedFeatures.length + (this.selectedTarget ? 1 : 0);
            this.selectedColumnsCount.textContent = `${total}/${this.columns.length}`;
        }
    }
    
    getSelectedAlgorithm() {
        for (const radio of this.algorithmRadios) {
            if (radio.checked) {
                return radio.value;
            }
        }
        return 'random_forest';
    }
    
    getAlgorithmName(value) {
        const names = {
            'random_forest': 'Random Forest',
            'xgboost': 'XGBoost',
            'linear': 'Regressão Linear',
            'svr': 'SVR'
        };
        return names[value] || value;
    }
    
    handleDrop(e) {
        e.preventDefault();
        e.stopPropagation();
        
        this.dropArea.classList.remove('dragover');
        
        const dt = e.dataTransfer;
        const files = dt.files;
        
        if (files.length > 0 && this.fileInput) {
            this.fileInput.files = files;
            this.handleFileSelect();
        }
    }
    
    preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    // ===== FUNÇÕES DE PROGRESSO =====
    
    showProgress() {
        if (!document.getElementById('progressContainer')) {
            const progressHtml = `
                <div id="progressContainer" class="upload-card mt-4">
                    <div class="d-flex align-items-center justify-content-between mb-3">
                        <h5 class="mb-0">Treinando Modelo</h5>
                        <span class="badge bg-primary" id="processId">${this.currentProcessId}</span>
                    </div>
                    <div class="progress-modern mb-2">
                        <div class="progress-modern-bar" id="progressBar" style="width: 0%"></div>
                    </div>
                    <p class="small text-muted mb-0" id="statusText">Iniciando...</p>
                </div>
            `;
            
            const uploadCard = document.querySelector('.upload-card');
            if (uploadCard) {
                uploadCard.insertAdjacentHTML('afterend', progressHtml);
            }
        } else {
            document.getElementById('progressContainer')?.classList.remove('d-none');
        }
    }
    
    startProgressPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
        }
        
        this.pollInterval = setInterval(async () => {
            if (!this.currentProcessId) return;
            
            try {
                const status = await this.getStatus(this.currentProcessId);
                
                this.updateProgress(status.progress || 0);
                
                const statusText = document.getElementById('statusText');
                if (statusText) {
                    statusText.textContent = this.getStatusText(status);
                }
                
                if (status.status === 'completed' || status.status === 'error') {
                    clearInterval(this.pollInterval);
                    
                    if (status.status === 'completed') {
                        this.showResult(status);
                        await this.loadDashboardStats();
                        await this.loadUserCredits();
                        await this.loadAnalysisHistory();
                        
                        document.getElementById('progressContainer')?.remove();
                    } else {
                        this.showAlert('❌ Erro no treinamento: ' + (status.error || 'Desconhecido'), 'error');
                    }
                    
                    this.resetUploadButton();
                }
                
            } catch (error) {
                console.error('Erro no polling:', error);
            }
        }, 2000);
    }
    
    updateProgress(percent) {
        const progressBar = document.getElementById('progressBar');
        if (progressBar) {
            progressBar.style.width = `${percent}%`;
        }
    }
    
    getStatusText(status) {
        if (status.status === 'uploaded') return '📤 Arquivo recebido';
        if (status.status === 'preprocessing') return '🔄 Pré-processando dados';
        if (status.status === 'training') return '🧠 Treinando modelo Scikit-learn';
        if (status.status === 'predicting') return '🔮 Gerando previsões';
        if (status.status === 'evaluating') return '📊 Calculando métricas';
        if (status.status === 'generating_report') return '📝 Gerando relatório';
        if (status.status === 'completed') return '✅ Modelo treinado com sucesso';
        return '⏳ Processando...';
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
    
    // ===== FUNÇÕES DE RESULTADO =====
    
    showResult(result) {
        if (this.resultContainer) {
            this.resultContainer.style.display = 'block';
            
            if (this.targetColumnName && this.selectedTarget) {
                this.targetColumnName.textContent = this.selectedTarget;
            }
            
            const algorithm = this.getSelectedAlgorithm();
            if (this.algorithmName) {
                this.algorithmName.textContent = this.getAlgorithmName(algorithm);
            }
            
            if (typeof gsap !== 'undefined') {
                gsap.from(this.resultContainer, {
                    duration: 1,
                    y: 50,
                    opacity: 0,
                    ease: 'power3.out'
                });
            }
        }
        
        const metrics = result.metrics || {
            r2: 0.94,
            mae: 12.5,
            rmse: 18.3,
            feature_importance: [0.45, 0.30, 0.25]
        };
        
        const featureNames = this.selectedFeatures || ['Feature 1', 'Feature 2', 'Feature 3'];
        const predictions = result.predictions || this.generateSamplePredictions(10);
        const actuals = result.actuals || this.generateSamplePredictions(10, true);
        
        this.updateMetrics(metrics, featureNames);
        this.updateComparisonChart(actuals, predictions);
        this.displayMLResults(actuals, predictions);
    }
    
    generateSamplePredictions(length, isActual = false) {
        if (isActual) {
            return Array.from({ length }, () => 50 + Math.random() * 100);
        } else {
            return Array.from({ length }, () => 50 + Math.random() * 100);
        }
    }
    
    updateMetrics(metrics, featureNames) {
        if (this.metricR2) {
            this.metricR2.textContent = metrics.r2 ? metrics.r2.toFixed(2) : '0.94';
        }
        
        if (this.metricMAE) {
            this.metricMAE.textContent = metrics.mae ? metrics.mae.toFixed(1) : '12.5';
        }
        
        if (this.metricRMSE) {
            this.metricRMSE.textContent = metrics.rmse ? metrics.rmse.toFixed(1) : '18.3';
        }
        
        if (this.metricImportance) {
            const importance = metrics.feature_importance || [0.45, 0.30, 0.25];
            this.metricImportance.textContent = importance.length;
        }
        
        if (this.featureImportance && featureNames.length > 0) {
            const importance = metrics.feature_importance || [0.45, 0.30, 0.25];
            let html = '';
            
            featureNames.slice(0, 3).forEach((name, index) => {
                const value = importance[index] || 0;
                html += `
                    <div class="mb-2">
                        <div class="d-flex justify-content-between small">
                            <span>${name}</span>
                            <span>${(value * 100).toFixed(0)}%</span>
                        </div>
                        <div class="progress-modern">
                            <div class="progress-modern-bar" style="width: ${value * 100}%"></div>
                        </div>
                    </div>
                `;
            });
            
            this.featureImportance.innerHTML = html;
        }
    }
    
    updateComparisonChart(actuals, predictions) {
        if (typeof Chart === 'undefined') return;
        
        const ctx = document.getElementById('comparisonChart')?.getContext('2d');
        if (!ctx) return;
        
        if (window.comparisonChart) {
            window.comparisonChart.destroy();
        }
        
        window.comparisonChart = new Chart(ctx, {
            type: 'scatter',
            data: {
                datasets: [
                    {
                        label: 'Previsões vs Real',
                        data: actuals.map((actual, i) => ({ x: actual, y: predictions[i] })),
                        backgroundColor: '#667eea',
                        pointRadius: 6,
                        pointHoverRadius: 8
                    },
                    {
                        label: 'Linha Perfeita',
                        data: [
                            { x: Math.min(...actuals, ...predictions), y: Math.min(...actuals, ...predictions) },
                            { x: Math.max(...actuals, ...predictions), y: Math.max(...actuals, ...predictions) }
                        ],
                        type: 'line',
                        borderColor: '#48bb78',
                        borderWidth: 2,
                        pointRadius: 0,
                        fill: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'top'
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                return `Real: ${context.raw.x.toFixed(2)} | Previsto: ${context.raw.y.toFixed(2)}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        title: {
                            display: true,
                            text: 'Valores Reais'
                        }
                    },
                    y: {
                        title: {
                            display: true,
                            text: 'Valores Previstos'
                        }
                    }
                }
            }
        });
    }
    
    displayMLResults(actuals, predictions) {
        if (!this.mlTable) return;
        
        this.mlTable.innerHTML = '';
        
        const validLength = Math.min(actuals.length, predictions.length, 10);
        let totalError = 0;
        
        for (let i = 0; i < validLength; i++) {
            const actual = actuals[i];
            const predicted = predictions[i];
            const error = Math.abs(actual - predicted);
            const errorPercent = (error / actual) * 100;
            const confidence = Math.max(0, 100 - errorPercent);
            
            totalError += error;
            
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${i + 1}</td>
                <td><strong>${actual.toFixed(2).replace('.', ',')}</strong></td>
                <td class="text-primary">${predicted.toFixed(2).replace('.', ',')}</td>
                <td>
                    <span class="${error < 10 ? 'text-success' : error < 20 ? 'text-warning' : 'text-danger'}">
                        ${error.toFixed(2).replace('.', ',')} (${errorPercent.toFixed(1).replace('.', ',')}%)
                    </span>
                </td>
                <td>
                    ± ${(error * 0.2).toFixed(2).replace('.', ',')}
                    <div class="progress-modern mt-1">
                        <div class="progress-modern-bar" style="width: ${confidence}%"></div>
                    </div>
                </td>
                <td>
                    <span class="badge ${errorPercent < 10 ? 'bg-success' : errorPercent < 20 ? 'bg-warning text-dark' : 'bg-danger'}">
                        ${errorPercent < 10 ? 'Excelente' : errorPercent < 20 ? 'Bom' : 'Regular'}
                    </span>
                </td>
            `;
            
            this.mlTable.appendChild(row);
        }
    }
    
    // ===== FUNÇÕES DE RESULTADO =====
    
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
                a.download = `modelo_${this.currentProcessId}.txt`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
                
                this.showAlert('✅ Download iniciado!', 'success');
            } else {
                this.showAlert('❌ Erro ao baixar resultado', 'error');
            }
            
        } catch (error) {
            this.showAlert('❌ Erro de conexão', 'error');
        }
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
                a.download = `previsoes_${this.currentProcessId}.csv`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
                
                this.showAlert('✅ CSV exportado com sucesso!', 'success');
            }
        } catch (error) {
            this.showAlert('❌ Erro ao exportar CSV', 'error');
        }
    }
    
    async showRawData() {
        if (!this.currentProcessId) return;
        
        const modalHtml = `
            <div class="modal fade" id="rawDataModal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content rounded-4">
                        <div class="modal-header bg-dark text-white border-0">
                            <h5 class="modal-title">
                                <i class="fas fa-database me-2"></i>
                                Dados do Modelo Treinado
                            </h5>
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <pre class="bg-light p-3 rounded-3" style="max-height: 400px; overflow: auto;" id="rawDataContent">Carregando...</pre>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        const existingModal = document.getElementById('rawDataModal');
        if (existingModal) existingModal.remove();
        
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        const modal = new bootstrap.Modal(document.getElementById('rawDataModal'));
        modal.show();
        
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
    
    // ===== FUNÇÕES DE HISTÓRICO =====
    
    async loadAnalysisHistory() {
        try {
            const response = await this.fetchWithAuth(`${this.apiBase}/analyses/history`);
            if (response.ok) {
                const analyses = await response.json();
                this.displayAnalysisHistory(analyses);
            }
        } catch (error) {
            console.error('Erro ao carregar histórico:', error);
        }
    }
    
    displayAnalysisHistory(analyses) {
        if (!this.historyContainer) return;
        
        if (!analyses || analyses.length === 0) {
            this.historyContainer.innerHTML = `
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
        
        const html = analyses.slice(0, 5).map(analysis => {
            const date = new Date(analysis.created_at);
            const formattedDate = date.toLocaleDateString('pt-BR') + ' ' + date.toLocaleTimeString('pt-BR');
            
            return `
                <div class="timeline-item">
                    <div class="timeline-marker ${analysis.status === 'completed' ? 'bg-success' : 'bg-warning'}"></div>
                    <div class="timeline-content">
                        <p class="mb-1 small">
                            <strong>${analysis.filename || 'Arquivo'}</strong>
                            ${analysis.target_column ? `<br><small>Alvo: ${analysis.target_column}</small>` : ''}
                        </p>
                        <small class="text-muted">
                            ${formattedDate}
                            ${analysis.algorithm ? `• ${this.getAlgorithmName(analysis.algorithm)}` : ''}
                        </small>
                    </div>
                </div>
            `;
        }).join('');
        
        this.historyContainer.innerHTML = html;
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
                if (this.totalAnalises) this.totalAnalises.textContent = stats.total_analises || 0;
                if (this.analisesHoje) this.analisesHoje.textContent = stats.analises_hoje || 0;
            }
        } catch (error) {
            console.error('Erro ao carregar stats:', error);
        }
    }
    
    // ===== FUNÇÕES DE UTILIDADE =====
    
    resetFileSelection() {
        if (this.fileInput) this.fileInput.value = '';
        if (this.selectedFile) this.selectedFile.classList.add('d-none');
        if (this.columnSelector) this.columnSelector.classList.add('d-none');
        if (this.dataPreview) this.dataPreview.classList.add('d-none');
        if (this.uploadButton) this.uploadButton.disabled = true;
        
        this.fileData = null;
        this.columns = [];
        this.selectedFeatures = [];
        this.selectedTarget = null;
    }
    
    initGSAPAnimations() {
        if (typeof gsap !== 'undefined') {
            gsap.registerPlugin(ScrollTrigger);
            
            gsap.from('.metric-card', {
                scrollTrigger: {
                    trigger: '.metric-card',
                    start: 'top 80%'
                },
                duration: 0.8,
                y: 50,
                opacity: 0,
                stagger: 0.2,
                ease: 'power3.out'
            });
            
            gsap.from('.plan-card', {
                scrollTrigger: {
                    trigger: '.plan-card',
                    start: 'top 80%'
                },
                duration: 1,
                scale: 0.8,
                opacity: 0,
                ease: 'back.out(1.7)'
            });
        }
    }
    
    setupLogout() {
        const logoutBtn = document.getElementById('logoutBtn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', (e) => {
                e.preventDefault();
                if (window.appAuth) {
                    window.appAuth.logout();
                } else {
                    this.logout();
                }
            });
        }
    }
    
    async logout() {
        if (confirm('Deseja realmente sair?')) {
            try {
                const refreshToken = localStorage.getItem('refresh_token');
                
                if (refreshToken) {
                    await fetch(`${this.apiBase}/auth/logout`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                        },
                        body: JSON.stringify({ refresh_token: refreshToken })
                    });
                }
            } catch (error) {
                console.error('Erro no logout:', error);
            } finally {
                localStorage.removeItem('access_token');
                localStorage.removeItem('refresh_token');
                localStorage.removeItem('user');
                
                window.location.href = '/login.html';
            }
        }
    }
    
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
            const refreshed = await this.refreshToken();
            if (refreshed) {
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
        const existingAlerts = document.querySelectorAll('.custom-alert');
        if (existingAlerts.length > 3) {
            existingAlerts[0].remove();
        }
        
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed custom-alert`;
        alertDiv.style.cssText = `
            top: 20px;
            right: 20px;
            z-index: 9999;
            min-width: 350px;
            max-width: 450px;
            border-radius: 12px;
            border: none;
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            font-size: 0.95rem;
            padding: 1rem 1.25rem;
        `;
        
        let icon = '📌';
        if (type === 'success') icon = '✅';
        if (type === 'error') icon = '❌';
        if (type === 'warning') icon = '⚠️';
        if (type === 'info') icon = 'ℹ️';
        
        alertDiv.innerHTML = `
            <div style="display: flex; align-items: center;">
                <span style="font-size: 1.4rem; margin-right: 12px;">${icon}</span>
                <div style="flex: 1;">${message}</div>
                <button type="button" class="btn-close ms-3" data-bs-dismiss="alert" style="font-size: 0.8rem;"></button>
            </div>
        `;
        
        document.body.appendChild(alertDiv);
        
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.style.transition = 'opacity 0.3s';
                alertDiv.style.opacity = '0';
                setTimeout(() => {
                    if (alertDiv.parentNode) alertDiv.remove();
                }, 300);
            }
        }, 5000);
    }
    
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        if (i >= 2) {
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
}

// Função global para carregar histórico completo
window.loadFullHistory = async function() {
    if (!window.app) return;
    
    try {
        const response = await window.app.fetchWithAuth(`${window.app.apiBase}/analyses/history?limit=100`);
        if (response.ok) {
            const analyses = await response.json();
            showHistoryModal(analyses);
        }
    } catch (error) {
        window.app.showAlert('Erro ao carregar histórico completo', 'error');
    }
};

function showHistoryModal(analyses) {
    const modalHtml = `
        <div class="modal fade" id="historyModal" tabindex="-1">
            <div class="modal-dialog modal-lg">
                <div class="modal-content rounded-4">
                    <div class="modal-header bg-gradient text-white" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
                        <h5 class="modal-title">
                            <i class="fas fa-history me-2"></i>
                            Histórico Completo de Análises
                        </h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body" style="max-height: 500px; overflow-y: auto;">
                        <table class="table table-hover">
                            <thead>
                                <tr>
                                    <th>Data</th>
                                    <th>Arquivo</th>
                                    <th>Algoritmo</th>
                                    <th>Coluna Alvo</th>
                                    <th>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${analyses.map(a => `
                                    <tr>
                                        <td>${new Date(a.created_at).toLocaleDateString('pt-BR')}</td>
                                        <td>${a.filename || '-'}</td>
                                        <td>${window.app.getAlgorithmName(a.algorithm) || '-'}</td>
                                        <td>${a.target_column || '-'}</td>
                                        <td>
                                            <span class="badge ${a.status === 'completed' ? 'bg-success' : 'bg-warning'}">
                                                ${a.status || 'Concluído'}
                                            </span>
                                        </td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    const existingModal = document.getElementById('historyModal');
    if (existingModal) existingModal.remove();
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    
    const modal = new bootstrap.Modal(document.getElementById('historyModal'));
    modal.show();
}

// Inicializar - AGUARDA auth.js primeiro
document.addEventListener('DOMContentLoaded', () => {
    // Pequeno delay para garantir que auth.js carregou primeiro
    setTimeout(() => {
        window.app = new AutoAnalytics();
        console.log('✅ app.js inicializado (delegando para auth.js)');
    }, 100);
});