// frontend/js/app.js - VERSÃO MODIFICADA COM PoW

class AutoAnalytics {
    constructor() {
        this.apiBase = window.location.hostname.includes('localhost') 
            ? 'http://localhost:8000/api'
            : '/api';
        
        this.currentProcessId = null;
        this.pollInterval = null;
        this.fileData = null;
        this.columns = [];
        this.dataTypes = {};
        this.initialized = false;
        this.authCheckInterval = null;
        
        // ⏳ Aguardar auth.js inicializar
        this.waitForAuth();
    }
    
    // ===== AGUARDAR AUTH.JS INICIALIZAR =====
    async waitForAuth() {
        console.log('⏳ Aguardando auth.js inicializar...');
        
        for (let i = 0; i < 50; i++) {
            if (window.appAuth) {
                console.log('✅ auth.js encontrado!');
                
                if (this.isLoginPage() || this.isRegisterPage()) {
                    console.log('📝 Página de autenticação - app não será inicializado');
                    return;
                }
                
                if (!window.appAuth.isAuthenticated()) {
                    console.log('❌ Usuário não autenticado');
                    this.redirectToLogin();
                    return;
                }
                
                console.log('✅ Usuário autenticado, inicializando app...');
                this.init();
                return;
            }
            await new Promise(resolve => setTimeout(resolve, 100));
        }
        
        if (this.isLoginPage() || this.isRegisterPage()) {
            console.log('📝 Página de autenticação - app não será inicializado');
            return;
        }
        
        console.log('❌ Timeout aguardando auth.js');
        this.redirectToLogin();
    }
    
    // ===== VERIFICAÇÕES DE PÁGINA =====
    
    isLoginPage() {
        return window.location.pathname.includes('login.html') || 
               window.location.pathname === '/login' ||
               window.location.pathname === '/';
    }
    
    isRegisterPage() {
        return window.location.pathname.includes('register.html') || 
               window.location.pathname === '/register';
    }
    
    isPlanosPage() {
        return window.location.pathname.includes('planos.html') || 
               window.location.pathname === '/planos';
    }
    
    isCheckoutPage() {
        return window.location.pathname.includes('checkout.html') || 
               window.location.pathname === '/checkout';
    }
    
    // ===== REDIRECIONAMENTO =====
    
    redirectToLogin() {
        if (!this.isLoginPage() && !this.isRegisterPage() && 
            !this.isPlanosPage() && !this.isCheckoutPage()) {
            console.log('🔄 Redirecionando para login...');
            window.location.href = '/login.html';
        }
    }
    
    // ===== FUNÇÕES DELEGADAS PARA auth.js =====
    
    isAdmin() {
        return window.appAuth ? window.appAuth.isAdmin() : false;
    }
    
    isPremium() {
        return window.appAuth ? window.appAuth.isPremium() : false;
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
    
    // ===== INICIALIZAÇÃO PRINCIPAL =====
    
    async init() {
        console.log('🚀 Inicializando AutoAnalytics App...');
        
        if (this.isLoginPage() || this.isRegisterPage()) {
            console.log('🚫 App não inicializado em página de autenticação');
            return;
        }
        
        if (!window.appAuth || !window.appAuth.isAuthenticated()) {
            console.log('❌ Não autenticado');
            this.redirectToLogin();
            return;
        }
        
        this.initializeElements();
        this.bindEvents();
        
        setTimeout(async () => {
            await this.loadUserCredits();
            await this.loadDashboardStats();
            await this.loadAnalysisHistory();
            
            if (this.isPremium()) {
                await this.loadPremiumStatus();
            }
            
            this.setupLogout();
            this.initAnimations();
            this.updateCreditsDisplay();
            this.initialized = true;
            
            console.log('✅ App inicializado com sucesso');
            console.log(`👤 Usuário: ${this.getCurrentUser().email}`);
            console.log(`💰 Créditos: ${this.getCreditsDisplay()}`);
            
            this.startAuthCheck();
        }, 500);
    }
    
    startAuthCheck() {
        this.authCheckInterval = setInterval(() => {
            if (!window.appAuth || !window.appAuth.isAuthenticated()) {
                console.log('❌ Sessão expirada');
                this.redirectToLogin();
            }
        }, 5 * 60 * 1000);
    }
    
    // ===== CRÉDITOS E PREMIUM =====
    
    async loadUserCredits() {
        if (this.isLoginPage() || this.isRegisterPage()) return;
        if (!window.appAuth || !window.appAuth.isAuthenticated()) return;
        
        try {
            const response = await this.fetchWithAuth(`${this.apiBase}/payments/balance`);
            if (response && response.ok) {
                const data = await response.json();
                
                if (window.appAuth) {
                    const user = window.appAuth.getCurrentUser();
                    user.credits = data.credits || 0;
                    user.is_admin = data.is_admin || false;
                    user.is_premium = data.is_premium || false;
                    localStorage.setItem('user', JSON.stringify(user));
                    window.appAuth.updateCreditsDisplay();
                }
            }
        } catch (error) {
            console.error('Erro ao carregar créditos:', error);
        }
    }
    
    async loadPremiumStatus() {
        if (!this.isPremium()) return;
        if (this.isLoginPage() || this.isRegisterPage()) return;
        
        try {
            const response = await this.fetchWithAuth(`${this.apiBase}/premium/status`);
            if (response && response.ok) {
                const data = await response.json();
                this.displayPremiumInfo(data);
            }
        } catch (error) {
            console.error('Erro ao carregar status premium:', error);
        }
    }
    
    displayPremiumInfo(data) {
        if (!data?.has_premium) return;
        
        let premiumContainer = document.getElementById('premiumDashboardInfo');
        
        if (!premiumContainer) {
            const uploadCard = document.querySelector('.upload-card');
            if (!uploadCard) return;
            
            premiumContainer = document.createElement('div');
            premiumContainer.id = 'premiumDashboardInfo';
            premiumContainer.className = 'premium-info-box mb-4';
            uploadCard.insertAdjacentElement('beforebegin', premiumContainer);
        }
        
        const daysLeft = data.plan?.days_left || 0;
        const progress = data.plan?.progress || 0;
        const receivedToday = data.credits?.next_credit_today || false;
        
        premiumContainer.innerHTML = `
            <div class="premium-glow-card">
                <div class="d-flex align-items-center">
                    <div class="premium-icon">
                        <i class="fas fa-crown"></i>
                    </div>
                    <div class="flex-grow-1">
                        <div class="d-flex justify-content-between align-items-center">
                            <h6 class="mb-0 premium-title">PLANO PREMIUM ATIVO</h6>
                            <span class="premium-days-badge">${daysLeft} dias</span>
                        </div>
                        
                        <div class="premium-progress mt-2">
                            <div class="premium-progress-bar" style="width: ${progress}%"></div>
                        </div>
                        
                        <div class="d-flex justify-content-between small mt-1">
                            <span class="premium-status-text">
                                <i class="fas fa-calendar-alt me-1"></i>
                                ${receivedToday ? 'Crédito de hoje recebido' : 'Crédito disponível hoje'}
                            </span>
                            ${!receivedToday && daysLeft > 0 ? `
                                <button class="premium-claim-btn" onclick="window.app?.claimDailyCredit()">
                                    <i class="fas fa-gift me-1"></i>
                                    Receber
                                </button>
                            ` : ''}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    async claimDailyCredit() {
        if (!this.isPremium()) return;
        if (this.isLoginPage() || this.isRegisterPage()) return;
        
        try {
            const response = await this.fetchWithAuth(`${this.apiBase}/premium/check-daily`, {
                method: 'POST'
            });
            
            if (response && response.ok) {
                const data = await response.json();
                
                if (data.credits_added > 0) {
                    this.showNotification('⭐ Você ganhou 1 crédito do plano premium!', 'success');
                    await this.loadUserCredits();
                    await this.loadPremiumStatus();
                }
            }
        } catch (error) {
            console.error('Erro ao receber crédito:', error);
        }
    }
    
    // ===== UPLOAD COM PoW INTEGRADO =====
    
    async handleUpload(e) {
        e.preventDefault();
        
        const file = this.fileInput?.files[0];
        if (!file) {
            this.showNotification('❌ Selecione um arquivo primeiro', 'warning');
            return;
        }
        
        // Verificar créditos
        if (!this.isAdmin()) {
            const creditsCheck = await this.checkCredits();
            if (!creditsCheck) return;
        }
        
        this.setUploadLoading(true);
        
        try {
            // 🔐 UPLOAD COM PoW (silencioso)
            const response = await window.powClient.uploadWithPow(file, '/api/upload-auto');
            
            const data = await response.json();
            
            if (response.ok) {
                this.currentProcessId = data.process_id;
                this.showNotification('🚀 Análise iniciada!', 'success');
                await this.loadUserCredits();
                this.showProgress();
                this.startProgressPolling();
            } else {
                if (data.detail?.error === 'Créditos insuficientes') {
                    this.showCreditsModal();
                } else {
                    this.showNotification('❌ ' + (data.detail || 'Erro no upload'), 'error');
                }
                this.setUploadLoading(false);
            }
            
        } catch (error) {
            console.error('Erro no upload:', error);
            this.showNotification('❌ Erro de conexão', 'error');
            this.setUploadLoading(false);
        }
    }
    
    setUploadLoading(loading) {
        if (!this.uploadButton) return;
        
        this.uploadButton.disabled = loading;
        if (loading) {
            this.uploadButton.innerHTML = '<div class="spinner-glow"></div><span>Processando...</span>';
        } else {
            const icon = this.isAdmin() ? '👑' : (this.isPremium() ? '⭐' : '🚀');
            this.uploadButton.innerHTML = `${icon} Iniciar Análise Automática <span class="credit-badge">${this.getCreditsDisplay()} créditos</span>`;
        }
    }
    
    async checkCredits() {
        try {
            const response = await this.fetchWithAuth(`${this.apiBase}/payments/check-analysis`);
            if (response && response.ok) {
                const data = await response.json();
                if (!data.has_credits) {
                    if (this.isPremium()) {
                        this.showNotification('⭐ Você usou todos os créditos. Amanhã você ganha mais!', 'warning');
                    } else {
                        this.showCreditsModal();
                    }
                    return false;
                }
                return true;
            }
        } catch (error) {
            console.error('Erro ao verificar créditos:', error);
        }
        return false;
    }
    
    // ===== DRAG & DROP COM PoW (PRÉ-RESOLUÇÃO) =====
    
    handleDragEnter(e) {
        e.preventDefault();
        this.dropArea.classList.add('dragover-glow');
        
        // 🔐 PRÉ-RESOLVE PoW EM BACKGROUND durante o drag
        if (window.powClient && window.powClient.preSolveOnDrag) {
            window.powClient.prepareForUpload();
        }
    }
    
    // ===== LEITURA DE ARQUIVO =====
    
    async handleFileSelect() {
        const file = this.fileInput?.files[0];
        if (!file) return;
        
        if (!this.validateFile(file)) return;
        
        this.displayFileInfo(file);
        await this.analyzeFile(file);
    }
    
    validateFile(file) {
        const MAX_SIZE = 10 * 1024 * 1024;
        const validExtensions = ['.csv', '.xlsx', '.xls'];
        const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
        
        if (file.size > MAX_SIZE) {
            this.showNotification(`❌ Arquivo muito grande (${(file.size/1024/1024).toFixed(2)}MB). Máx: 10MB`, 'error');
            this.resetFileSelection();
            return false;
        }
        
        if (!validExtensions.includes(ext)) {
            this.showNotification('❌ Formato não suportado. Use CSV ou Excel', 'error');
            this.resetFileSelection();
            return false;
        }
        
        return true;
    }
    
    displayFileInfo(file) {
        if (this.fileName) this.fileName.textContent = file.name;
        if (this.fileSize) this.fileSize.textContent = this.formatFileSize(file.size);
        if (this.selectedFile) {
            this.selectedFile.classList.remove('d-none');
            
            this.selectedFile.innerHTML = `
                <div class="file-info-glow">
                    <div class="file-icon">
                        <i class="fas fa-file-${file.name.endsWith('.csv') ? 'csv' : 'excel'}"></i>
                    </div>
                    <div class="file-details">
                        <div class="file-name">${file.name}</div>
                        <div class="file-meta">
                            <span class="file-size">${this.formatFileSize(file.size)}</span>
                            <span class="file-type">${file.name.endsWith('.csv') ? 'CSV' : 'Excel'}</span>
                        </div>
                    </div>
                    <button class="file-remove-btn" id="removeFile">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            `;
            
            document.getElementById('removeFile')?.addEventListener('click', (e) => {
                e.stopPropagation();
                this.resetFileSelection();
            });
        }
        
        if (typeof gsap !== 'undefined') {
            gsap.from(this.selectedFile, {
                duration: 0.5,
                y: 20,
                opacity: 0,
                ease: 'power3.out'
            });
        }
    }
    
    async analyzeFile(file) {
        this.showNotification('🔍 Analisando estrutura do arquivo...', 'info');
        
        try {
            let data, columns, types;
            
            if (file.name.endsWith('.csv')) {
                const result = await this.parseCSV(file);
                data = result.data;
                columns = result.columns;
                types = result.types;
            } else {
                const result = await this.parseExcel(file);
                data = result.data;
                columns = result.columns;
                types = result.types;
            }
            
            this.fileData = data;
            this.columns = columns;
            this.dataTypes = types;
            
            this.showTechPreview(data, columns, types);
            
            this.uploadButton.disabled = false;
            this.uploadButton.innerHTML = `🚀 Iniciar Análise Automática <span class="credit-badge">${this.getCreditsDisplay()} créditos</span>`;
            
            this.showNotification('✅ Arquivo analisado! Pronto para processar.', 'success');
            
        } catch (error) {
            console.error('Erro ao analisar arquivo:', error);
            this.showNotification('❌ Erro ao analisar arquivo', 'error');
            this.resetFileSelection();
        }
    }
    
    parseCSV(file) {
        return new Promise((resolve, reject) => {
            Papa.parse(file, {
                header: true,
                preview: 20,
                dynamicTyping: true,
                complete: (result) => {
                    if (result.data && result.data.length > 0) {
                        const columns = result.meta.fields || [];
                        const types = {};
                        
                        columns.forEach(col => {
                            const values = result.data.map(row => row[col]).filter(v => v !== null && v !== undefined);
                            if (values.length === 0) {
                                types[col] = 'unknown';
                            } else if (values.every(v => typeof v === 'number')) {
                                types[col] = 'numeric';
                            } else if (values.every(v => v instanceof Date || !isNaN(Date.parse(v)))) {
                                types[col] = 'date';
                            } else {
                                types[col] = 'text';
                            }
                        });
                        
                        resolve({
                            data: result.data.slice(0, 10),
                            columns,
                            types
                        });
                    } else {
                        reject(new Error('Arquivo vazio'));
                    }
                },
                error: reject
            });
        });
    }
    
    parseExcel(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            
            reader.onload = (e) => {
                try {
                    const data = new Uint8Array(e.target.result);
                    const workbook = XLSX.read(data, { type: 'array' });
                    const firstSheet = workbook.Sheets[workbook.SheetNames[0]];
                    const jsonData = XLSX.utils.sheet_to_json(firstSheet, { header: 1 });
                    
                    if (jsonData.length > 0) {
                        const headers = jsonData[0].map(h => String(h).trim());
                        const rows = jsonData.slice(1, 11).map(row => {
                            const obj = {};
                            headers.forEach((header, index) => {
                                obj[header] = row[index];
                            });
                            return obj;
                        });
                        
                        const types = {};
                        headers.forEach(col => {
                            const values = rows.map(row => row[col]).filter(v => v !== undefined && v !== null);
                            if (values.length === 0) {
                                types[col] = 'unknown';
                            } else if (values.every(v => typeof v === 'number')) {
                                types[col] = 'numeric';
                            } else if (values.every(v => !isNaN(Date.parse(v)))) {
                                types[col] = 'date';
                            } else {
                                types[col] = 'text';
                            }
                        });
                        
                        resolve({
                            data: rows,
                            columns: headers,
                            types
                        });
                    } else {
                        reject(new Error('Arquivo vazio'));
                    }
                } catch (error) {
                    reject(error);
                }
            };
            
            reader.onerror = reject;
            reader.readAsArrayBuffer(file);
        });
    }
    
    showTechPreview(data, columns, types) {
        const previewSection = document.getElementById('dataPreview');
        if (!previewSection) return;
        
        let html = `
            <div class="tech-preview-container">
                <div class="preview-header">
                    <div class="header-left">
                        <span class="glow-dot"></span>
                        <h5>ANÁLISE DE ESTRUTURA</h5>
                    </div>
                    <div class="header-right">
                        <span class="badge-cols">${columns.length} colunas</span>
                        <span class="badge-rows">${data.length} amostras</span>
                    </div>
                </div>
                
                <div class="columns-showcase">
        `;
        
        columns.forEach(col => {
            const type = types[col] || 'unknown';
            const typeIcon = {
                'numeric': '📊',
                'date': '📅',
                'text': '📝',
                'unknown': '❓'
            }[type];
            
            html += `
                <div class="column-card" data-type="${type}">
                    <div class="column-icon">${typeIcon}</div>
                    <div class="column-info">
                        <div class="column-name">${this.truncate(col, 20)}</div>
                        <div class="column-type">
                            <span class="type-badge ${type}">${type}</span>
                        </div>
                    </div>
                </div>
            `;
        });
        
        html += `
                </div>
                
                <div class="data-matrix">
                    <div class="matrix-header">
                        <span class="matrix-title">MATRIZ DE DADOS</span>
                        <span class="matrix-dim">${data.length}×${columns.length}</span>
                    </div>
                    <div class="table-container">
                        <table class="tech-table">
                        <thead>
                            <tr>
                                ${columns.slice(0, 6).map(col => `<th>${this.truncate(col, 15)}</th>`).join('')}
                                ${columns.length > 6 ? '<th class="more-cols">+ mais</th>' : ''}
                            </tr>
                        </thead>
                        <tbody>
                            ${data.slice(0, 5).map(row => `
                                <tr>
                                    ${columns.slice(0, 6).map(col => {
                                        let value = row[col];
                                        if (value === undefined || value === null) value = '—';
                                        if (typeof value === 'number') value = value.toFixed(2);
                                        return `<td>${String(value).substring(0, 20)}</td>`;
                                    }).join('')}
                                    ${columns.length > 6 ? '<td class="more-cols">...</td>' : ''}
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                    </div>
                </div>
                
                <div class="insights-panel">
                    <div class="insight-item">
                        <i class="fas fa-calculator"></i>
                        <span><strong>${columns.filter(c => types[c] === 'numeric').length}</strong> colunas numéricas</span>
                    </div>
                    <div class="insight-item">
                        <i class="fas fa-font"></i>
                        <span><strong>${columns.filter(c => types[c] === 'text').length}</strong> colunas de texto</span>
                    </div>
                    <div class="insight-item">
                        <i class="fas fa-calendar"></i>
                        <span><strong>${columns.filter(c => types[c] === 'date').length}</strong> colunas de data</span>
                    </div>
                </div>
            </div>
        `;
        
        previewSection.innerHTML = html;
        previewSection.classList.remove('d-none');
        
        if (typeof gsap !== 'undefined') {
            gsap.from('.column-card', {
                duration: 0.4,
                scale: 0.8,
                opacity: 0,
                stagger: 0.03,
                ease: 'back.out'
            });
        }
    }
    
    truncate(str, max) {
        if (!str) return '';
        return str.length > max ? str.substring(0, max) + '…' : str;
    }
    
    // ===== PROGRESSO =====
    
    showProgress() {
        let container = document.getElementById('progressContainer');
        
        if (!container) {
            container = document.createElement('div');
            container.id = 'progressContainer';
            container.className = 'progress-glow-container mt-4';
            container.innerHTML = `
                <div class="progress-header">
                    <div class="progress-title">
                        <div class="pulse-dot"></div>
                        <span>PROCESSAMENTO EM ANDAMENTO</span>
                    </div>
                    <span class="process-id" id="processId">${this.currentProcessId}</span>
                </div>
                <div class="progress-bar-glow">
                    <div class="progress-fill" id="progressBar" style="width: 0%"></div>
                </div>
                <div class="progress-status" id="statusText">Iniciando análise...</div>
            `;
            
            const uploadCard = document.querySelector('.upload-card');
            if (uploadCard) {
                uploadCard.insertAdjacentElement('afterend', container);
            }
        } else {
            container.classList.remove('d-none');
        }
    }
    
    startProgressPolling() {
        if (this.pollInterval) clearInterval(this.pollInterval);
        
        this.pollInterval = setInterval(async () => {
            if (!this.currentProcessId) return;
            
            try {
                const status = await this.getStatus(this.currentProcessId);
                
                const progressBar = document.getElementById('progressBar');
                const statusText = document.getElementById('statusText');
                
                if (progressBar) progressBar.style.width = `${status.progress || 0}%`;
                if (statusText) statusText.textContent = this.getStatusMessage(status);
                
                if (status.status === 'completed' || status.status === 'error') {
                    clearInterval(this.pollInterval);
                    
                    if (status.status === 'completed') {
                        this.showResult(status);
                        await this.loadDashboardStats();
                        await this.loadUserCredits();
                        await this.loadAnalysisHistory();
                        document.getElementById('progressContainer')?.remove();
                    }
                    
                    this.setUploadLoading(false);
                }
                
            } catch (error) {
                console.error('Erro no polling:', error);
            }
        }, 2000);
    }
    
    async getStatus(processId) {
        try {
            const response = await fetch(`${this.apiBase}/status/${processId}`, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
            });
            return await response.json();
        } catch {
            return { status: 'unknown' };
        }
    }
    
    getStatusMessage(status) {
        const messages = {
            'uploaded': '📤 Arquivo recebido',
            'detecting': '🔍 Detectando padrões...',
            'analyzing': '📊 Analisando dados...',
            'training': '🧠 Treinando modelo...',
            'completed': '✅ Análise concluída!',
            'error': '❌ Erro no processamento'
        };
        return messages[status.status] || '⏳ Processando...';
    }
    
    showResult(result) {
        const resultContainer = document.getElementById('resultContainer');
        if (!resultContainer) return;
        
        resultContainer.style.display = 'block';
        
        const analysisInfo = result.analysis_info || {};
        const stats = result.prediction_stats || {};
        
        let html = `
            <div class="result-glow-card">
                <div class="result-header">
                    <h5>📊 RESULTADO DA ANÁLISE</h5>
                    <span class="result-badge">${analysisInfo.problem_type || 'Automático'}</span>
                </div>
                
                <div class="result-metrics">
                    <div class="metric-glow">
                        <div class="metric-value">${stats.total || 0}</div>
                        <div class="metric-label">Total de Registros</div>
                    </div>
                    <div class="metric-glow">
                        <div class="metric-value">${analysisInfo.features_count || 0}</div>
                        <div class="metric-label">Features</div>
                    </div>
                    <div class="metric-glow">
                        <div class="metric-value">${analysisInfo.model_used || 'AutoML'}</div>
                        <div class="metric-label">Modelo</div>
                    </div>
                </div>
                
                <div class="target-info">
                    <i class="fas fa-bullseye"></i>
                    <span>Coluna alvo detectada: <strong>${analysisInfo.target_column || 'automática'}</strong></span>
                </div>
            </div>
        `;
        
        resultContainer.innerHTML = html;
        
        if (typeof gsap !== 'undefined') {
            gsap.from(resultContainer, {
                duration: 0.8,
                y: 30,
                opacity: 0,
                ease: 'power3.out'
            });
        }
    }
    
    async loadAnalysisHistory() {
        if (this.isLoginPage() || this.isRegisterPage()) return;
        
        try {
            const response = await this.fetchWithAuth(`${this.apiBase}/analyses/history`);
            if (response && response.ok) {
                const analyses = await response.json();
                this.displayHistory(analyses);
            }
        } catch (error) {
            console.error('Erro ao carregar histórico:', error);
        }
    }
    
    displayHistory(analyses) {
        const container = document.getElementById('recentAnalyses');
        if (!container) return;
        
        if (!analyses || analyses.length === 0) {
            container.innerHTML = `
                <div class="history-empty">
                    <i class="fas fa-chart-line"></i>
                    <p>Nenhuma análise realizada</p>
                    <small>Envie seu primeiro arquivo</small>
                </div>
            `;
            return;
        }
        
        const html = analyses.slice(0, 5).map(a => {
            const date = new Date(a.created_at);
            return `
                <div class="history-item">
                    <div class="history-icon ${a.status}">
                        <i class="fas ${a.status === 'completed' ? 'fa-check' : 'fa-clock'}"></i>
                    </div>
                    <div class="history-content">
                        <div class="history-filename">${a.filename || 'Análise'}</div>
                        <div class="history-meta">
                            <span>${date.toLocaleDateString('pt-BR')}</span>
                            <span class="status-badge ${a.status}">${a.status}</span>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
        
        container.innerHTML = html;
    }
    
    async loadDashboardStats() {
        if (this.isLoginPage() || this.isRegisterPage()) return;
        
        try {
            const response = await this.fetchWithAuth(`${this.apiBase}/stats`);
            if (response && response.ok) {
                const stats = await response.json();
                
                if (stats) {
                    if (this.totalAnalises) this.totalAnalises.textContent = stats.total_analises || 0;
                    if (this.analisesHoje) this.analisesHoje.textContent = stats.analises_hoje || 0;
                }
            }
        } catch (error) {
            console.error('Erro ao carregar stats:', error);
        }
    }
    
    // ===== UTILIDADES =====
    
    initializeElements() {
        this.uploadForm = document.getElementById('uploadForm');
        this.fileInput = document.getElementById('fileInput');
        this.uploadButton = document.getElementById('uploadButton');
        this.dropArea = document.getElementById('dropArea');
        this.selectedFile = document.getElementById('selectedFile');
        this.fileName = document.getElementById('fileName');
        this.fileSize = document.getElementById('fileSize');
        this.historyContainer = document.getElementById('recentAnalyses');
        this.uploadCredits = document.getElementById('uploadCredits');
        this.userName = document.getElementById('userName');
        this.workshopName = document.getElementById('workshopName');
        this.totalAnalises = document.getElementById('totalAnalises');
        this.analisesHoje = document.getElementById('analisesHoje');
        
        if (this.uploadButton) {
            this.uploadButton.disabled = true;
            this.uploadButton.innerHTML = `📁 Selecione um arquivo primeiro`;
        }
    }
    
    bindEvents() {
        if (this.uploadForm) {
            this.uploadForm.addEventListener('submit', (e) => this.handleUpload(e));
        }
        
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(event => {
            if (this.dropArea) {
                this.dropArea.addEventListener(event, this.preventDefaults.bind(this));
            }
        });
        
        if (this.dropArea) {
            this.dropArea.addEventListener('drop', (e) => this.handleDrop(e));
            this.dropArea.addEventListener('click', () => this.fileInput?.click());
            this.dropArea.addEventListener('dragenter', (e) => this.handleDragEnter(e));
            this.dropArea.addEventListener('dragover', () => this.dropArea.classList.add('dragover-glow'));
            this.dropArea.addEventListener('dragleave', () => this.dropArea.classList.remove('dragover-glow'));
        }
        
        if (this.fileInput) {
            this.fileInput.addEventListener('change', () => this.handleFileSelect());
        }
    }
    
    handleDrop(e) {
        e.preventDefault();
        this.dropArea.classList.remove('dragover-glow');
        
        const files = e.dataTransfer.files;
        if (files.length > 0 && this.fileInput) {
            this.fileInput.files = files;
            this.handleFileSelect();
        }
    }
    
    preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    resetFileSelection() {
        if (this.fileInput) this.fileInput.value = '';
        if (this.selectedFile) this.selectedFile.classList.add('d-none');
        if (this.uploadButton) {
            this.uploadButton.disabled = true;
            this.uploadButton.innerHTML = `📁 Selecione um arquivo primeiro`;
        }
        
        const preview = document.getElementById('dataPreview');
        if (preview) preview.classList.add('d-none');
        
        this.fileData = null;
        this.columns = [];
    }
    
    setupLogout() {
        const logoutBtn = document.getElementById('logoutBtn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', (e) => {
                e.preventDefault();
                if (window.powClient) window.powClient.reset();
                window.appAuth?.logout();
            });
        }
    }
    
    initAnimations() {
        if (typeof gsap !== 'undefined') {
            gsap.from('.metric-card', {
                duration: 0.8,
                y: 30,
                opacity: 0,
                stagger: 0.1,
                ease: 'power3.out'
            });
        }
    }
    
    // ===== FETCH COM AUTENTICAÇÃO (VERSÃO CORRIGIDA) =====
    
    async fetchWithAuth(url, options = {}) {
        if (this.isLoginPage() || this.isRegisterPage()) {
            console.log('🚫 Requisição bloqueada - página de autenticação');
            return null;
        }
        
        if (!window.appAuth) {
            await new Promise(resolve => setTimeout(resolve, 300));
        }
        
        const token = localStorage.getItem('access_token');
        
        if (!token) {
            console.log('❌ Sem token - redirecionando');
            this.redirectToLogin();
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
                console.log('🔄 Token 401 - tentando refresh...');
                
                if (window.appAuth) {
                    const refreshed = await window.appAuth.refreshToken();
                    
                    if (refreshed) {
                        const newToken = localStorage.getItem('access_token');
                        headers['Authorization'] = `Bearer ${newToken}`;
                        response = await fetch(url, { ...options, headers });
                        console.log('✅ Requisição retentada com novo token');
                    } else {
                        console.log('❌ Refresh falhou - redirecionando');
                        this.redirectToLogin();
                        return null;
                    }
                } else {
                    this.redirectToLogin();
                    return null;
                }
            }
            
            return response;
            
        } catch (error) {
            console.error('❌ Erro na requisição:', error);
            
            if (error.name === 'TypeError' && error.message.includes('Failed to fetch')) {
                console.log('🔌 Erro de conexão com o servidor');
                this.showNotification('Erro de conexão com o servidor', 'error');
                return null;
            }
            
            return null;
        }
    }
    
    // ===== NOTIFICAÇÕES =====
    
    showNotification(message, type = 'info') {
        if (window.toastr) {
            toastr[type](message);
            return;
        }
        
        const notification = document.createElement('div');
        notification.className = `notification-glow ${type}`;
        notification.innerHTML = `
            <i class="fas ${type === 'success' ? 'fa-check-circle' : type === 'error' ? 'fa-exclamation-circle' : 'fa-info-circle'}"></i>
            <span>${message}</span>
        `;
        
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => notification.remove(), 300);
        }, 5000);
    }
    
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    showCreditsModal() {
        let modal = document.getElementById('creditsModal');
        
        if (!modal) {
            const modalHtml = `
                <div class="modal fade" id="creditsModal" tabindex="-1">
                    <div class="modal-dialog">
                        <div class="modal-content modal-glow">
                            <div class="modal-header">
                                <h5 class="modal-title">
                                    <i class="fas fa-coins text-warning me-2"></i>
                                    Créditos Insuficientes
                                </h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                            </div>
                            <div class="modal-body text-center py-4">
                                <i class="fas fa-coins fa-4x text-warning mb-3"></i>
                                <h5>Você não tem créditos suficientes</h5>
                                <p class="text-muted">Cada análise consome 1 crédito.</p>
                                <p>Seu saldo: <strong><span id="modalCredits">0</span></strong></p>
                                ${this.isPremium() ? `
                                    <div class="premium-tip mt-3">
                                        <i class="fas fa-star me-2"></i>
                                        Você é premium! Amanhã você ganha +1 crédito.
                                    </div>
                                ` : ''}
                            </div>
                            <div class="modal-footer">
                                <a href="/planos.html" class="btn btn-gradient w-100">
                                    <i class="fas fa-credit-card me-2"></i>
                                    Comprar Créditos
                                </a>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            
            document.body.insertAdjacentHTML('beforeend', modalHtml);
            modal = document.getElementById('creditsModal');
        }
        
        const modalCredits = document.getElementById('modalCredits');
        if (modalCredits) modalCredits.textContent = this.getCreditsDisplay();
        
        new bootstrap.Modal(modal).show();
    }
}

// ===== INICIALIZAÇÃO SEGURA =====
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => {
        window.app = new AutoAnalytics();
    }, 200);
});

window.getApp = () => window.app;
window.claimDailyCredit = () => window.app?.claimDailyCredit();
window.showCreditsModal = () => window.app?.showCreditsModal();