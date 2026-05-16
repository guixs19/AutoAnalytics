// frontend/js/app.js - VERSÃO CORRIGIDA
// Limite máximo: 15KB por arquivo

class AutoAnalytics {
    constructor() {
        this.apiBase = window.location.hostname.includes('localhost') 
            ? 'http://localhost:8000/api'
            : '/api';
        
        this.MAX_FILE_SIZE_KB = 15;
        this.MAX_FILE_SIZE_BYTES = this.MAX_FILE_SIZE_KB * 1024;
        
        this.currentProcessId = null;
        this.pollInterval = null;
        this.fileData = null;
        this.columns = [];
        this.dataTypes = {};
        this.initialized = false;
        this.authCheckInterval = null;
        
        this.tokenExpiryTimer = null;
        this.tokenCheckInterval = null;
        this.isRefreshing = false;
        this.pendingRequests = [];
        
        this.waitForAuth();
    }
    
    async waitForAuth() {
        console.log('⏳ Aguardando auth.js inicializar...');
        
        for (let i = 0; i < 50; i++) {
            if (window.appAuth) {
                console.log('✅ auth.js encontrado!');
                
                if (window.appAuth.initialized === false) {
                    console.log('⏳ Aguardando inicialização do auth...');
                    await new Promise(resolve => setTimeout(resolve, 200));
                    continue;
                }
                
                if (this.isLoginPage() || this.isRegisterPage()) {
                    console.log('📝 Página de autenticação - app não será inicializado');
                    return;
                }
                
                const isAuthenticated = window.appAuth.isAuthenticated && window.appAuth.isAuthenticated();
                
                if (!isAuthenticated) {
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
    
    isLoginPage() {
        return window.location.pathname.includes('login.html') || 
               window.location.pathname.includes('/login') ||
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
    
    redirectToLogin() {
        if (!this.isLoginPage() && !this.isRegisterPage() && 
            !this.isPlanosPage() && !this.isCheckoutPage()) {
            console.log('🔄 Redirecionando para login...');
            window.location.href = '/login.html';
        }
    }
    
    // ===== FUNÇÕES DELEGADAS PARA auth.js =====
    
    isAdmin() {
        return window.appAuth && window.appAuth.isAdmin ? window.appAuth.isAdmin() : false;
    }
    
    isPremium() {
        return window.appAuth && window.appAuth.isPremium ? window.appAuth.isPremium() : false;
    }
    
    getCurrentUser() {
        return window.appAuth && window.appAuth.getCurrentUser ? window.appAuth.getCurrentUser() : {};
    }
    
    getCreditsDisplay() {
        if (window.appAuth && window.appAuth.getCreditsDisplay) {
            return window.appAuth.getCreditsDisplay();
        }
        const user = this.getCurrentUser();
        if (user.is_admin) return '∞';
        return String(user.credits || 0);
    }
    
    getCredits() {
        if (window.appAuth && window.appAuth.getCredits) {
            return window.appAuth.getCredits();
        }
        return this.getCurrentUser().credits || 0;
    }
    
    updateCreditsDisplay() {
        if (window.appAuth && window.appAuth.updateCreditsDisplay) {
            window.appAuth.updateCreditsDisplay();
        }
    }
    
    async loadUserCredits() {
        if (window.appAuth && window.appAuth.loadUserCredits) {
            return await window.appAuth.loadUserCredits();
        }
        return false;
    }
    
    async checkCreditsForAnalysis() {
        if (window.appAuth && window.appAuth.checkCreditsForAnalysis) {
            return await window.appAuth.checkCreditsForAnalysis();
        }
        return this.isAdmin() ? true : this.getCredits() > 0;
    }
    
    // ===== MONITORAMENTO DE TOKEN =====
    
    startTokenMonitoring() {
        if (this.tokenExpiryTimer) {
            clearTimeout(this.tokenExpiryTimer);
            this.tokenExpiryTimer = null;
        }
        if (this.tokenCheckInterval) {
            clearInterval(this.tokenCheckInterval);
            this.tokenCheckInterval = null;
        }
        
        const token = localStorage.getItem('access_token');
        if (!token) {
            console.log('❌ Sem token para monitorar');
            return;
        }
        
        try {
            const payload = this.decodeJWT(token);
            if (payload && payload.exp) {
                const expiresAt = payload.exp * 1000;
                const now = Date.now();
                const timeUntilExpiry = expiresAt - now;
                
                console.log(`🔐 Token expira em ${Math.round(timeUntilExpiry / 1000)} segundos`);
                
                if (timeUntilExpiry <= 0) {
                    this.handleTokenExpired();
                } else {
                    const refreshTime = Math.max(1000, timeUntilExpiry - 30000);
                    console.log(`⏰ Agendando renovação em ${Math.round(refreshTime / 1000)} segundos`);
                    
                    this.tokenExpiryTimer = setTimeout(() => {
                        console.log('🔄 Token próximo de expirar, renovando...');
                        this.refreshTokenSafely();
                    }, refreshTime);
                }
            } else {
                this.startPollingTokenCheck();
            }
        } catch (e) {
            console.warn('⚠️ Não foi possível decodificar token, usando polling:', e);
            this.startPollingTokenCheck();
        }
        
        this.tokenCheckInterval = setInterval(() => {
            this.checkTokenHealth();
        }, 30000);
    }
    
    decodeJWT(token) {
        try {
            const base64Url = token.split('.')[1];
            const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
            const jsonPayload = decodeURIComponent(atob(base64).split('').map(c => {
                return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
            }).join(''));
            return JSON.parse(jsonPayload);
        } catch (e) {
            console.error('Erro ao decodificar JWT:', e);
            return null;
        }
    }
    
    startPollingTokenCheck() {
        if (this.tokenCheckInterval) {
            clearInterval(this.tokenCheckInterval);
        }
        this.tokenCheckInterval = setInterval(() => {
            this.checkTokenHealth();
        }, 30000);
    }
    
    async checkTokenHealth() {
        try {
            const token = localStorage.getItem('access_token');
            if (!token) {
                this.handleTokenExpired();
                return;
            }
            
            const response = await fetch(`${this.apiBase}/auth/check-token`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            
            if (response.status === 401) {
                console.log('🔐 Token inválido segundo o backend');
                const refreshed = await this.refreshTokenSafely();
                if (!refreshed) {
                    this.handleTokenExpired();
                }
            } else if (response.ok) {
                const data = await response.json();
                if (data.status === 'refreshed' && data.access_token) {
                    console.log('🔄 Token renovado pelo backend');
                    localStorage.setItem('access_token', data.access_token);
                    if (data.refresh_token) {
                        localStorage.setItem('refresh_token', data.refresh_token);
                    }
                    this.startTokenMonitoring();
                }
            }
        } catch (error) {
            console.warn('Erro ao verificar saúde do token:', error);
        }
    }
    
    async refreshTokenSafely() {
        if (this.isRefreshing) {
            console.log('⏳ Refresh já em andamento, aguardando...');
            return new Promise((resolve) => {
                this.pendingRequests.push(resolve);
            });
        }
        
        this.isRefreshing = true;
        
        try {
            console.log('🔄 Tentando renovar token...');
            const refreshToken = localStorage.getItem('refresh_token');
            
            if (!refreshToken) {
                console.log('❌ Sem refresh token');
                return false;
            }
            
            const response = await fetch(`${this.apiBase}/auth/refresh`, {
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
                
                console.log('✅ Token renovado com sucesso');
                this.startTokenMonitoring();
                
                this.pendingRequests.forEach(resolve => resolve(true));
                this.pendingRequests = [];
                
                return true;
            } else {
                console.log('❌ Falha na renovação do token');
                return false;
            }
        } catch (error) {
            console.error('❌ Erro ao renovar token:', error);
            return false;
        } finally {
            this.isRefreshing = false;
        }
    }
    
    handleTokenExpired() {
        console.log('🔐 Token expirado, redirecionando para login...');
        this.showNotification('⏰ Sua sessão expirou. Faça login novamente.', 'warning');
        
        if (this.tokenExpiryTimer) {
            clearTimeout(this.tokenExpiryTimer);
            this.tokenExpiryTimer = null;
        }
        if (this.tokenCheckInterval) {
            clearInterval(this.tokenCheckInterval);
            this.tokenCheckInterval = null;
        }
        
        setTimeout(() => {
            if (window.appAuth && window.appAuth.logout) {
                window.appAuth.logout();
            } else {
                localStorage.clear();
                window.location.href = '/login.html';
            }
        }, 1500);
    }
    
    stopTokenMonitoring() {
        if (this.tokenExpiryTimer) {
            clearTimeout(this.tokenExpiryTimer);
            this.tokenExpiryTimer = null;
        }
        if (this.tokenCheckInterval) {
            clearInterval(this.tokenCheckInterval);
            this.tokenCheckInterval = null;
        }
        if (this.authCheckInterval) {
            clearInterval(this.authCheckInterval);
            this.authCheckInterval = null;
        }
    }
    
    // ===== INICIALIZAÇÃO PRINCIPAL =====
    
    async init() {
        console.log('🚀 Inicializando AutoAnalytics App...');
        console.log(`📁 Limite máximo: ${this.MAX_FILE_SIZE_KB}KB por arquivo`);
        
        if (this.isLoginPage() || this.isRegisterPage()) {
            console.log('🚫 App não inicializado em página de autenticação');
            return;
        }
        
        const isAuth = window.appAuth && window.appAuth.isAuthenticated && window.appAuth.isAuthenticated();
        
        if (!isAuth) {
            console.log('❌ Não autenticado');
            this.redirectToLogin();
            return;
        }
        
        this.startTokenMonitoring();
        
        this.initializeElements();
        this.bindEvents();
        
        setTimeout(async () => {
            await this.loadUserCredits();
            await this.loadDashboardStats();
            await this.loadAnalysisHistory();
            this.updateCreditsDisplay();
            
            if (this.isPremium()) {
                await this.loadPremiumStatus();
            }
            
            this.setupLogout();
            this.initAnimations();
            this.initialized = true;
            
            console.log('✅ App inicializado com sucesso');
            const user = this.getCurrentUser();
            console.log(`👤 Usuário: ${user.email || 'desconhecido'}`);
            console.log(`💰 Créditos: ${this.getCreditsDisplay()}`);
            console.log(`🔐 Token monitoramento: ativo`);
            console.log(`📁 Limite: ${this.MAX_FILE_SIZE_KB}KB`);
            
        }, 500);
    }
    
    // ===== VALIDAÇÃO DE TAMANHO =====
    
    validateFileSize(file) {
        const fileSizeKB = file.size / 1024;
        
        console.log(`📁 Verificando arquivo: ${file.name}`);
        console.log(`📊 Tamanho: ${fileSizeKB.toFixed(2)}KB / ${this.MAX_FILE_SIZE_KB}KB`);
        
        if (file.size > this.MAX_FILE_SIZE_BYTES) {
            const exceededBy = (file.size - this.MAX_FILE_SIZE_BYTES) / 1024;
            console.warn(`⚠️ Arquivo excede o limite! Excesso: ${exceededBy.toFixed(2)}KB`);
            
            this.showFileSizeWarning(fileSizeKB);
            return false;
        }
        
        this.hideFileSizeWarning();
        return true;
    }
    
    showFileSizeWarning(fileSizeKB) {
        const warningEl = document.getElementById('sizeWarning');
        const warningText = document.getElementById('sizeWarningText');
        
        if (warningEl && warningText) {
            warningText.innerHTML = `
                <i class="fas fa-exclamation-triangle me-2"></i>
                Arquivo muito grande! (${fileSizeKB.toFixed(2)}KB) 
                Limite máximo: ${this.MAX_FILE_SIZE_KB}KB. 
                Por favor, reduza o arquivo.
            `;
            warningEl.classList.add('show');
        }
        
        if (this.uploadButton) {
            this.uploadButton.disabled = true;
            this.uploadButton.innerHTML = `❌ Arquivo excede ${this.MAX_FILE_SIZE_KB}KB`;
        }
        
        this.showNotification(`⚠️ Arquivo excede o limite de ${this.MAX_FILE_SIZE_KB}KB!`, 'error');
    }
    
    hideFileSizeWarning() {
        const warningEl = document.getElementById('sizeWarning');
        if (warningEl) {
            warningEl.classList.remove('show');
        }
    }
    
    // ===== UPLOAD =====
    
    async handleUpload(e) {
        e.preventDefault();
        
        const file = this.fileInput?.files[0];
        if (!file) {
            this.showNotification('❌ Selecione um arquivo primeiro', 'warning');
            return;
        }
        
        if (!this.validateFileSize(file)) {
            this.resetFileSelection();
            return;
        }
        
        const validTypes = ['.xlsx', '.xls', '.csv'];
        const fileExt = '.' + file.name.split('.').pop().toLowerCase();
        if (!validTypes.includes(fileExt)) {
            this.showNotification('❌ Formato não suportado. Use Excel (.xlsx, .xls) ou CSV', 'error');
            this.resetFileSelection();
            return;
        }
        
        if (!this.isAdmin()) {
            const creditsCheck = await this.checkCreditsForAnalysis();
            if (!creditsCheck) return;
        }
        
        this.setUploadLoading(true);
        
        try {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('analysis_type', 'auto');
            formData.append('ai_model', 'auto');
            
            const token = localStorage.getItem('access_token');
            const response = await fetch(`${this.apiBase}/upload-auto`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData
            });
            
            const data = await response.json();
            
            if (response.ok && (data.id || data.process_id)) {
                this.currentProcessId = data.process_id || data.id;
                this.showNotification('🚀 Análise iniciada com sucesso!', 'success');
                
                await this.loadUserCredits();
                this.updateCreditsDisplay();
                
                this.showProgress();
                this.startProgressPolling();
                
                if (this.fileInput) this.fileInput.value = '';
                if (this.selectedFile) this.selectedFile.classList.add('d-none');
                this.hideFileSizeWarning();
                
                await this.loadAnalysisHistory();
                
            } else {
                const errorMsg = data?.detail || data?.error || 'Erro no upload';
                if (errorMsg.includes('Créditos insuficientes')) {
                    this.showCreditsModal();
                } else if (errorMsg.includes('tamanho') || errorMsg.includes('size')) {
                    this.showNotification(`❌ ${errorMsg} (Limite: ${this.MAX_FILE_SIZE_KB}KB)`, 'error');
                } else {
                    this.showNotification('❌ ' + errorMsg, 'error');
                }
                this.setUploadLoading(false);
            }
            
        } catch (error) {
            console.error('Erro no upload:', error);
            
            if (error.message === 'Failed to fetch' || error.name === 'TypeError') {
                this.showNotification('❌ Erro de conexão com o servidor.', 'error');
            } else if (error.message.includes('401')) {
                this.handleTokenExpired();
            } else {
                this.showNotification('❌ ' + (error.message || 'Erro ao processar arquivo'), 'error');
            }
            this.setUploadLoading(false);
        }
    }
    
    setUploadLoading(loading) {
        if (!this.uploadButton) return;
        
        this.uploadButton.disabled = loading;
        if (loading) {
            this.uploadButton.innerHTML = '<div class="spinner-border spinner-border-sm me-2"></div>Processando...';
        } else {
            const icon = this.isAdmin() ? '👑' : (this.isPremium() ? '⭐' : '🚀');
            const creditText = this.isAdmin() ? 'Admin' : `${this.getCreditsDisplay()} créditos`;
            this.uploadButton.innerHTML = `${icon} Iniciar Análise Automática <span class="credit-badge">${creditText}</span>`;
        }
    }
    
    // ===== DRAG & DROP =====
    
    handleDragEnter(e) {
        e.preventDefault();
        if (this.dropArea) {
            this.dropArea.classList.add('dragover-glow');
        }
    }
    
    handleDrop(e) {
        e.preventDefault();
        if (this.dropArea) {
            this.dropArea.classList.remove('dragover-glow');
        }
        
        const files = e.dataTransfer.files;
        if (files.length > 0 && this.fileInput) {
            this.fileInput.files = files;
            this.handleFileSelect();
        }
    }
    
    async handleFileSelect() {
        const file = this.fileInput?.files[0];
        if (!file) return;
        
        if (!this.validateFileSize(file)) {
            this.resetFileSelection();
            return;
        }
        
        if (!this.validateFile(file)) return;
        
        this.displayFileInfo(file);
        await this.analyzeFile(file);
    }
    
    validateFile(file) {
        const validExtensions = ['.csv', '.xlsx', '.xls'];
        const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
        
        if (!validExtensions.includes(ext)) {
            this.showNotification('❌ Formato não suportado. Use CSV ou Excel', 'error');
            this.resetFileSelection();
            return false;
        }
        
        return true;
    }
    
    displayFileInfo(file) {
        const fileSizeKB = (file.size / 1024).toFixed(2);
        const isWithinLimit = file.size <= this.MAX_FILE_SIZE_BYTES;
        
        if (this.fileName) this.fileName.textContent = file.name;
        if (this.fileSize) {
            this.fileSize.textContent = `${this.formatFileSize(file.size)} (${fileSizeKB}KB)`;
            
            if (file.size > this.MAX_FILE_SIZE_BYTES * 0.8 && file.size <= this.MAX_FILE_SIZE_BYTES) {
                this.fileSize.className = 'badge bg-warning ms-2';
            } else if (file.size <= this.MAX_FILE_SIZE_BYTES) {
                this.fileSize.className = 'badge bg-success ms-2';
            }
        }
        
        if (this.selectedFile) {
            this.selectedFile.classList.remove('d-none');
        }
        
        if (isWithinLimit) {
            console.log(`✅ Arquivo OK: ${fileSizeKB}KB dentro do limite de ${this.MAX_FILE_SIZE_KB}KB`);
        }
    }
    
    async analyzeFile(file) {
        this.showNotification(`🔍 Analisando arquivo (${(file.size/1024).toFixed(2)}KB)...`, 'info');
        
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
            
            if (this.uploadButton) {
                this.uploadButton.disabled = false;
                const creditText = this.isAdmin() ? 'Admin' : `${this.getCreditsDisplay()} créditos`;
                this.uploadButton.innerHTML = `🚀 Iniciar Análise Automática <span class="credit-badge">${creditText}</span>`;
            }
            
            this.showNotification('✅ Arquivo analisado! Pronto para processar.', 'success');
            
        } catch (error) {
            console.error('Erro ao analisar arquivo:', error);
            this.showNotification('❌ Erro ao analisar arquivo', 'error');
            this.resetFileSelection();
        }
    }
    
    parseCSV(file) {
        return new Promise((resolve, reject) => {
            if (typeof Papa === 'undefined') {
                reject(new Error('Biblioteca PapaParse não carregada'));
                return;
            }
            
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
            if (typeof XLSX === 'undefined') {
                reject(new Error('Biblioteca XLSX não carregada'));
                return;
            }
            
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
        
        const numericCount = columns.filter(c => types[c] === 'numeric').length;
        const textCount = columns.filter(c => types[c] === 'text').length;
        const dateCount = columns.filter(c => types[c] === 'date').length;
        
        let html = `
            <div class="preview-container mt-3">
                <h6><i class="fas fa-chart-line me-2"></i>Pré-visualização dos Dados</h6>
                <div class="table-responsive">
                    <table class="table table-sm table-bordered">
                        <thead class="table-light">
                            <tr>
                                ${columns.slice(0, 6).map(col => `<th>${this.truncate(col, 20)}</th>`).join('')}
                                ${columns.length > 6 ? '<th>...</th>' : ''}
                            </tr>
                        </thead>
                        <tbody>
                            ${data.slice(0, 5).map(row => `
                                <tr>
                                    ${columns.slice(0, 6).map(col => {
                                        let value = row[col];
                                        if (value === undefined || value === null) value = '—';
                                        if (typeof value === 'number') value = value.toFixed(2);
                                        return `<td title="${String(value)}">${this.truncate(String(value), 20)}</td>`;
                                    }).join('')}
                                    ${columns.length > 6 ? '<td>...</td>' : ''}
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
                <div class="text-muted small mt-2">
                    <i class="fas fa-info-circle me-1"></i>
                    Detectadas ${columns.length} colunas (${numericCount} numéricas, 
                    ${textCount} texto, ${dateCount} data)
                </div>
                <div class="text-success small mt-1">
                    <i class="fas fa-check-circle me-1"></i>
                    Tamanho do arquivo dentro do limite de ${this.MAX_FILE_SIZE_KB}KB
                </div>
            </div>
        `;
        
        previewSection.innerHTML = html;
        previewSection.classList.remove('d-none');
    }
    
    truncate(str, max) {
        if (!str) return '';
        return str.length > max ? str.substring(0, max) + '…' : str;
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    // ===== PROGRESSO =====
    
    showProgress() {
        let container = document.getElementById('progressContainer');
        
        if (!container) {
            container = document.createElement('div');
            container.id = 'progressContainer';
            container.className = 'mt-4';
            container.innerHTML = `
                <div class="card">
                    <div class="card-body">
                        <h6><i class="fas fa-spinner fa-spin me-2"></i>Processando...</h6>
                        <div class="progress">
                            <div class="progress-bar progress-bar-striped progress-bar-animated" id="progressBar" style="width: 0%"></div>
                        </div>
                        <div class="text-muted small mt-2" id="statusText">Iniciando análise...</div>
                    </div>
                </div>
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
                        this.updateCreditsDisplay();
                        const container = document.getElementById('progressContainer');
                        if (container) container.remove();
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
            <div class="card mt-3 border-success">
                <div class="card-body">
                    <h5 class="card-title text-success">📊 RESULTADO DA ANÁLISE</h5>
                    <div class="row mt-3">
                        <div class="col-md-4">
                            <div class="text-center">
                                <h3>${stats.total || 0}</h3>
                                <small class="text-muted">Total de Registros</small>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="text-center">
                                <h3>${analysisInfo.features_count || 0}</h3>
                                <small class="text-muted">Features</small>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="text-center">
                                <h3>${analysisInfo.model_used || 'AutoML'}</h3>
                                <small class="text-muted">Modelo</small>
                            </div>
                        </div>
                    </div>
                    <hr>
                    <p class="text-muted small mb-0">
                        <i class="fas fa-bullseye me-1"></i>
                        Coluna alvo: <strong>${analysisInfo.target_column || 'automática'}</strong>
                    </p>
                </div>
            </div>
        `;
        
        resultContainer.innerHTML = html;
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
                <div class="text-center text-muted py-4">
                    <i class="fas fa-chart-line fa-2x mb-2"></i>
                    <p>Nenhuma análise realizada</p>
                    <small>Envie seu primeiro arquivo</small>
                </div>
            `;
            return;
        }
        
        const html = analyses.slice(0, 5).map(a => {
            const date = new Date(a.created_at);
            const fileSizeInfo = a.file_size ? ` • ${(a.file_size/1024).toFixed(1)}KB` : '';
            return `
                <div class="list-group-item list-group-item-action">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <i class="fas fa-file-alt me-2 text-primary"></i>
                            <strong>${this.escapeHtml(a.filename || 'Análise')}</strong>
                            <small class="text-muted">${fileSizeInfo}</small>
                        </div>
                        <span class="badge ${a.status === 'completed' ? 'bg-success' : 'bg-secondary'}">${a.status}</span>
                    </div>
                    <small class="text-muted">${date.toLocaleDateString('pt-BR')}</small>
                </div>
            `;
        }).join('');
        
        container.innerHTML = `<div class="list-group">${html}</div>`;
    }
    
    async loadDashboardStats() {
        if (this.isLoginPage() || this.isRegisterPage()) return;
        
        try {
            const response = await this.fetchWithAuth(`${this.apiBase}/stats`);
            if (response && response.ok) {
                const stats = await response.json();
                
                const totalAnalises = document.getElementById('totalAnalises');
                const analisesHoje = document.getElementById('analisesHoje');
                
                if (totalAnalises) totalAnalises.textContent = stats.total_analises || 0;
                if (analisesHoje) analisesHoje.textContent = stats.analises_hoje || 0;
            }
        } catch (error) {
            console.error('Erro ao carregar stats:', error);
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
            premiumContainer.className = 'alert alert-info mb-4';
            uploadCard.insertAdjacentElement('beforebegin', premiumContainer);
        }
        
        const daysLeft = data.plan?.days_left || 0;
        
        premiumContainer.innerHTML = `
            <div class="d-flex align-items-center">
                <div class="me-3">
                    <i class="fas fa-crown fa-2x text-warning"></i>
                </div>
                <div class="flex-grow-1">
                    <h6 class="mb-0">PLANO PREMIUM ATIVO</h6>
                    <small>${daysLeft} dias restantes • 1 crédito/dia • Limite: ${this.MAX_FILE_SIZE_KB}KB</small>
                </div>
                <button class="btn btn-sm btn-outline-primary" onclick="window.app?.claimDailyCredit()">
                    <i class="fas fa-gift me-1"></i> Receber crédito
                </button>
            </div>
        `;
    }
    
    async claimDailyCredit() {
        if (!this.isPremium()) return;
        
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
        this.totalAnalises = document.getElementById('totalAnalises');
        this.analisesHoje = document.getElementById('analisesHoje');
        
        if (this.uploadButton) {
            this.uploadButton.disabled = true;
            this.uploadButton.innerHTML = `📁 Selecione um arquivo primeiro (max ${this.MAX_FILE_SIZE_KB}KB)`;
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
            this.dropArea.addEventListener('dragover', () => {
                if (this.dropArea) this.dropArea.classList.add('dragover-glow');
            });
            this.dropArea.addEventListener('dragleave', () => {
                if (this.dropArea) this.dropArea.classList.remove('dragover-glow');
            });
        }
        
        if (this.fileInput) {
            this.fileInput.addEventListener('change', () => this.handleFileSelect());
        }
        
        const removeFileBtn = document.getElementById('removeFile');
        if (removeFileBtn) {
            removeFileBtn.addEventListener('click', () => this.resetFileSelection());
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
            this.uploadButton.innerHTML = `📁 Selecione um arquivo primeiro (max ${this.MAX_FILE_SIZE_KB}KB)`;
        }
        
        const preview = document.getElementById('dataPreview');
        if (preview) preview.classList.add('d-none');
        
        this.hideFileSizeWarning();
        
        this.fileData = null;
        this.columns = [];
    }
    
    setupLogout() {
        const logoutBtn = document.getElementById('logoutBtn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.stopTokenMonitoring();
                if (window.appAuth && window.appAuth.logout) {
                    window.appAuth.logout();
                } else {
                    localStorage.clear();
                    window.location.href = '/login.html';
                }
            });
        }
    }
    
    initAnimations() {
        // Optional animations
    }
    
    async fetchWithAuth(url, options = {}) {
        if (this.isLoginPage() || this.isRegisterPage()) {
            return null;
        }
        
        if (window.appAuth && window.appAuth.fetchWithAuth) {
            return window.appAuth.fetchWithAuth(url, options);
        }
        
        const token = localStorage.getItem('access_token');
        if (!token) {
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
                const refreshed = await this.refreshTokenSafely();
                if (refreshed) {
                    const newToken = localStorage.getItem('access_token');
                    headers['Authorization'] = `Bearer ${newToken}`;
                    response = await fetch(url, { ...options, headers });
                    return response;
                } else {
                    this.redirectToLogin();
                    return null;
                }
            }
            return response;
        } catch (error) {
            console.error('Erro na requisição:', error);
            return null;
        }
    }
    
    showNotification(message, type = 'info') {
        if (window.toastr) {
            toastr[type](message);
            return;
        }
        
        const bgColor = type === 'success' ? '#48bb78' : 
                        type === 'error' ? '#f56565' :
                        type === 'warning' ? '#ed8936' : '#4299e1';
        
        const notification = document.createElement('div');
        notification.className = 'notification-glow';
        notification.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            z-index: 10000;
            background: white;
            border-left: 4px solid ${bgColor};
            padding: 12px 20px;
            border-radius: 12px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
            display: flex;
            align-items: center;
            gap: 12px;
            animation: slideInRight 0.3s ease-out;
            max-width: 350px;
        `;
        
        notification.innerHTML = `
            <i class="fas ${type === 'success' ? 'fa-check-circle' : 
                          type === 'error' ? 'fa-exclamation-circle' :
                          type === 'warning' ? 'fa-exclamation-triangle' : 'fa-info-circle'}" 
               style="color: ${bgColor}; font-size: 1.2rem;"></i>
            <span style="flex: 1;">${this.escapeHtml(message)}</span>
            <button onclick="this.parentElement.remove()" style="background: none; border: none; cursor: pointer;">
                <i class="fas fa-times" style="color: #999;"></i>
            </button>
        `;
        
        document.body.appendChild(notification);
        
        setTimeout(() => {
            if (notification.parentNode) {
                notification.style.animation = 'fadeOut 0.3s ease-out';
                setTimeout(() => notification.remove(), 300);
            }
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
        if (window.appAuth && window.appAuth.showCreditsModal) {
            window.appAuth.showCreditsModal();
        } else if (!this.isAdmin()) {
            this.showNotification('Créditos insuficientes!', 'warning');
        }
    }
    
    async loadFullHistory() {
        await this.loadAnalysisHistory();
        this.showNotification('Histórico atualizado!', 'info');
    }
}

// ===== INICIALIZAÇÃO =====
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        setTimeout(() => {
            window.app = new AutoAnalytics();
        }, 200);
    });
} else {
    setTimeout(() => {
        window.app = new AutoAnalytics();
    }, 200);
}

window.getApp = () => window.app;
window.claimDailyCredit = () => window.app?.claimDailyCredit();
window.showCreditsModal = () => window.app?.showCreditsModal();

// Adiciona CSS
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
    .dragover-glow {
        background: linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%);
        border: 2px dashed #667eea !important;
        transform: scale(1.02);
        transition: all 0.2s ease;
    }
    .credit-badge {
        background: rgba(255,255,255,0.3);
        padding: 0.2rem 0.5rem;
        border-radius: 50px;
        font-size: 0.75rem;
        margin-left: 0.5rem;
    }
    .list-group-item {
        border-radius: 12px !important;
        margin-bottom: 8px;
        border: 1px solid #e2e8f0;
    }
    .list-group-item:hover {
        background: #f8fafc;
        transform: translateX(4px);
        transition: all 0.2s;
    }
`;
document.head.appendChild(style);

console.log('✅ app.js carregado');