// frontend/js/app.js - VERSÃO PRODUÇÃO (200KB) - TOTALMENTE CORRIGIDA E SINCRONIZADA
// Limite: 200KB | Sistema de créditos premium | API relativa para VPS

class AutoAnalytics {
    constructor() {
        // 🔥 PRODUÇÃO: Detecta ambiente automaticamente
        const isLocalhost = window.location.hostname === 'localhost' || 
                           window.location.hostname === '127.0.0.1';
        
        // 🔥 CORRIGIDO: Usa a mesma lógica de API base do backend
        this.apiBase = isLocalhost 
            ? 'http://localhost:8000/api'
            : '/api';
        
        console.log(`🌐 API Base: ${this.apiBase} (${isLocalhost ? 'localhost' : 'produção'})`);
        
        // 🔥 LIMITE: 200KB (sincronizado com backend)
        this.MAX_FILE_SIZE_KB = 200;
        this.MAX_FILE_SIZE_BYTES = this.MAX_FILE_SIZE_KB * 1024;
        this.MAX_CREDITS_BALANCE = 3;
        
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
                
                // 🔥 Suporta tanto propriedade quanto função
                let isAuthenticated = false;
                if (typeof window.appAuth.isAuthenticated === 'function') {
                    isAuthenticated = window.appAuth.isAuthenticated();
                } else {
                    isAuthenticated = window.appAuth.isAuthenticated;
                }
                
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
    
    redirectToLogin() {
        if (!this.isLoginPage() && !this.isRegisterPage() && 
            !this.isPlanosPage() && !this.isCheckoutPage()) {
            console.log('🔄 Redirecionando para login...');
            window.location.href = '/login';
        }
    }
    
    redirectToPlanos() {
        if (!this.isPlanosPage() && !this.isLoginPage() && !this.isRegisterPage()) {
            console.log('💰 Redirecionando para planos (créditos insuficientes)...');
            this.showNotification('💰 Créditos insuficientes! Adquira o plano premium.', 'warning');
            setTimeout(() => {
                window.location.href = '/planos';
            }, 1500);
        }
    }
    
    isAdmin() {
        if (window.appAuth && window.appAuth.isAdmin) {
            return typeof window.appAuth.isAdmin === 'function' ? window.appAuth.isAdmin() : window.appAuth.isAdmin;
        }
        return false;
    }
    
    isPremium() {
        if (window.appAuth && window.appAuth.isPremium) {
            return typeof window.appAuth.isPremium === 'function' ? window.appAuth.isPremium() : window.appAuth.isPremium;
        }
        return false;
    }
    
    getCurrentUser() {
        if (window.appAuth && window.appAuth.getCurrentUser) {
            return window.appAuth.getCurrentUser();
        }
        return {};
    }
    
    getCredits() {
        if (window.appAuth && window.appAuth.getCredits) {
            return window.appAuth.getCredits();
        }
        return this.getCurrentUser().credits || 0;
    }
    
    getCreditsDisplay() {
        if (window.appAuth && window.appAuth.getCreditsDisplay) {
            return window.appAuth.getCreditsDisplay();
        }
        
        const user = this.getCurrentUser();
        
        if (user.is_admin || this.isAdmin()) {
            return '∞';
        }
        
        if (this.isPremium() || user.plan === 'premium_mensal') {
            const credits = user.credits || 0;
            return `${credits}/${this.MAX_CREDITS_BALANCE}`;
        }
        
        return String(user.credits || 0);
    }
    
    updateCreditsDisplay() {
        if (window.appAuth && window.appAuth.updateCreditsDisplay) {
            window.appAuth.updateCreditsDisplay();
        }
        
        const uploadCreditsSpan = document.getElementById('uploadCredits');
        if (uploadCreditsSpan) {
            uploadCreditsSpan.textContent = this.getCreditsDisplay();
        }
        
        const creditsCountSpan = document.getElementById('creditsCount');
        if (creditsCountSpan) {
            creditsCountSpan.textContent = this.getCreditsDisplay();
        }
    }
    
    async loadUserCredits() {
        if (window.appAuth && window.appAuth.loadUserCredits) {
            const result = await window.appAuth.loadUserCredits();
            
            if (result && result.welcome_message) {
                this.showNotification(result.welcome_message, 'success');
                const hasSeenWelcome = localStorage.getItem('has_seen_welcome');
                if (!hasSeenWelcome && result.is_new_user) {
                    setTimeout(() => this.showCreditsInfoModal(), 1500);
                    localStorage.setItem('has_seen_welcome', 'true');
                }
            }
            
            this.updateCreditsDisplay();
            return result;
        }
        return false;
    }
    
    showCreditsInfoModal() {
        let modal = document.getElementById('creditsInfoModal');
        
        if (!modal) {
            const modalHtml = `
                <div class="modal fade" id="creditsInfoModal" tabindex="-1" data-bs-backdrop="static">
                    <div class="modal-dialog modal-dialog-centered">
                        <div class="modal-content rounded-4">
                            <div class="modal-header bg-success text-white border-0">
                                <h5 class="modal-title">
                                    <i class="fas fa-gift me-2"></i>
                                    🎉 Créditos Grátis Adicionados!
                                </h5>
                                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                            </div>
                            <div class="modal-body text-center py-4">
                                <i class="fas fa-coins fa-5x text-warning mb-3"></i>
                                <h3 class="fw-bold">3 Créditos Grátis!</h3>
                                <p class="text-muted mb-3">Você ganhou <strong>3 créditos</strong> para testar o sistema!</p>
                                
                                <div class="alert alert-info text-start mt-3">
                                    <i class="fas fa-info-circle me-2"></i>
                                    <strong>Como funciona o sistema de créditos:</strong>
                                    <ul class="mt-2 mb-0 small">
                                        <li>✅ Cada análise consome <strong>1 crédito</strong></li>
                                        <li>✅ Limite máximo de <strong>3 créditos acumulados</strong></li>
                                        <li>⭐ <strong>Plano Premium:</strong> 1 crédito novo por dia</li>
                                        <li>📁 Limite de <strong>200KB por arquivo</strong></li>
                                    </ul>
                                </div>
                            </div>
                            <div class="modal-footer border-0 justify-content-center">
                                <button type="button" class="btn btn-gradient px-4" data-bs-dismiss="modal">
                                    <i class="fas fa-rocket me-2"></i>
                                    Começar a Usar
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            document.body.insertAdjacentHTML('beforeend', modalHtml);
            modal = document.getElementById('creditsInfoModal');
        }
        
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
    }
    
    async checkCreditsForAnalysis() {
        if (this.isAdmin()) return true;
        
        if (this.isPlanosPage()) {
            return false;
        }
        
        try {
            // 🔥 CORRIGIDO: Usa /api/payments/check-analysis (sincronizado com backend)
            const response = await this.fetchWithAuth(`${this.apiBase}/payments/check-analysis`);
            if (response && response.ok) {
                const data = await response.json();
                if (data.has_credits) {
                    return true;
                } else {
                    this.showNotification(data.message || '💰 Créditos insuficientes!', 'warning');
                    if (!this.isPlanosPage()) {
                        setTimeout(() => {
                            window.location.href = '/planos';
                        }, 1500);
                    }
                    return false;
                }
            }
        } catch (error) {
            console.error('Erro ao verificar créditos:', error);
        }
        
        const credits = this.getCredits();
        if (credits <= 0) {
            this.showNotification('❌ Você não tem créditos disponíveis!', 'error');
            if (!this.isPlanosPage()) {
                setTimeout(() => {
                    window.location.href = '/planos';
                }, 1500);
            }
            return false;
        }
        
        return true;
    }
    
    async claimDailyCredit() {
        if (!this.isPremium()) {
            this.showNotification('⭐ Assine o plano premium para ganhar créditos diários!', 'info');
            return;
        }
        
        try {
            // 🔥 CORRIGIDO: Usa /api/payments/premium/check-daily
            const response = await this.fetchWithAuth(`${this.apiBase}/payments/premium/check-daily`, {
                method: 'POST'
            });
            
            if (response && response.ok) {
                const data = await response.json();
                if (data.credits_added > 0) {
                    this.showNotification(data.message || '⭐ Você ganhou 1 crédito do plano premium!', 'success');
                    await this.loadUserCredits();
                    await this.loadPremiumStatus();
                    this.updateCreditsDisplay();
                } else if (data.message) {
                    this.showNotification(data.message, 'info');
                }
            }
        } catch (error) {
            console.error('Erro ao receber crédito:', error);
            this.showNotification('Erro ao receber crédito. Tente novamente.', 'error');
        }
    }
    
    buyCredits() {
        this.redirectToPlanos();
    }
    
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
                
                if (timeUntilExpiry <= 0) {
                    this.handleTokenExpired();
                } else {
                    const refreshTime = Math.max(1000, timeUntilExpiry - 30000);
                    this.tokenExpiryTimer = setTimeout(() => {
                        this.refreshTokenSafely();
                    }, refreshTime);
                }
            }
        } catch (e) {
            console.warn('Erro ao decodificar token:', e);
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
            return null;
        }
    }
    
    async checkTokenHealth() {
        try {
            const token = localStorage.getItem('access_token');
            if (!token) {
                this.handleTokenExpired();
                return;
            }
            
            // 🔥 CORRIGIDO: Usa /api/auth/check-token
            const response = await fetch(`${this.apiBase}/auth/check-token`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            
            if (response.status === 401) {
                const refreshed = await this.refreshTokenSafely();
                if (!refreshed) {
                    this.handleTokenExpired();
                }
            }
        } catch (error) {
            console.warn('Erro ao verificar token:', error);
        }
    }
    
    async refreshTokenSafely() {
        if (this.isRefreshing) {
            return new Promise((resolve) => {
                this.pendingRequests.push(resolve);
            });
        }
        
        this.isRefreshing = true;
        
        try {
            const refreshToken = localStorage.getItem('refresh_token');
            if (!refreshToken) return false;
            
            // 🔥 CORRIGIDO: Usa /api/auth/refresh
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
                this.startTokenMonitoring();
                this.pendingRequests.forEach(resolve => resolve(true));
                this.pendingRequests = [];
                return true;
            }
            return false;
        } catch (error) {
            return false;
        } finally {
            this.isRefreshing = false;
        }
    }
    
    handleTokenExpired() {
        this.showNotification('⏰ Sua sessão expirou. Faça login novamente.', 'warning');
        
        if (this.tokenExpiryTimer) clearTimeout(this.tokenExpiryTimer);
        if (this.tokenCheckInterval) clearInterval(this.tokenCheckInterval);
        
        setTimeout(() => {
            if (window.appAuth && window.appAuth.logout) {
                window.appAuth.logout();
            } else {
                localStorage.clear();
                window.location.href = '/login';
            }
        }, 1500);
    }
    
    stopTokenMonitoring() {
        if (this.tokenExpiryTimer) clearTimeout(this.tokenExpiryTimer);
        if (this.tokenCheckInterval) clearInterval(this.tokenCheckInterval);
    }
    
    async init() {
        console.log('🚀 Inicializando AutoAnalytics App...');
        console.log(`📁 Limite máximo: ${this.MAX_FILE_SIZE_KB}KB por arquivo`);
        
        if (this.isLoginPage() || this.isRegisterPage()) {
            return;
        }
        
        let isAuth = false;
        if (window.appAuth) {
            if (typeof window.appAuth.isAuthenticated === 'function') {
                isAuth = window.appAuth.isAuthenticated();
            } else {
                isAuth = window.appAuth.isAuthenticated;
            }
        }
        
        if (!isAuth) {
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
            this.initialized = true;
            
            console.log('✅ App inicializado com sucesso');
            console.log(`💰 Créditos: ${this.getCreditsDisplay()}`);
            console.log(`📁 Limite: ${this.MAX_FILE_SIZE_KB}KB`);
        }, 500);
    }
    
    // ===== VALIDAÇÃO DE TAMANHO (200KB) - CORRIGIDA =====
    
    validateFileSize(file) {
        const fileSizeKB = file.size / 1024;
        
        console.log(`📁 Verificando arquivo: ${file.name}`);
        console.log(`📊 Tamanho: ${fileSizeKB.toFixed(2)}KB / ${this.MAX_FILE_SIZE_KB}KB`);
        
        if (file.size > this.MAX_FILE_SIZE_BYTES) {
            this.showFileSizeWarning(file);
            this.fileData = null;
            if (this.uploadButton) {
                this.uploadButton.disabled = true;
                this.uploadButton.innerHTML = `❌ Arquivo excede ${this.MAX_FILE_SIZE_KB}KB`;
            }
            return false;
        }
        
        this.hideFileSizeWarning();
        return true;
    }
    
    showFileSizeWarning(file) {
        const fileSizeKB = (file.size / 1024).toFixed(2);
        const warningEl = document.getElementById('sizeWarning');
        
        if (warningEl) {
            warningEl.innerHTML = `
                <div class="alert alert-warning py-2 mb-0 mt-2">
                    <i class="fas fa-exclamation-triangle me-2"></i>
                    <strong>Arquivo muito grande!</strong> O ficheiro tem ${fileSizeKB}KB. 
                    O limite máximo permitido é de ${this.MAX_FILE_SIZE_KB}KB.
                    <button type="button" class="btn-close btn-sm float-end" data-bs-dismiss="alert"></button>
                </div>
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
    
    clearSizeWarningContent() {
        const warningEl = document.getElementById('sizeWarning');
        if (warningEl) {
            warningEl.innerHTML = '';
            warningEl.classList.remove('show');
        }
    }
    
    async handleUpload(e) {
        e.preventDefault();
        
        const file = this.fileInput?.files[0];
        if (!file) {
            this.showNotification('❌ Selecione um arquivo primeiro', 'warning');
            return;
        }
        
        if (!this.validateFileSize(file)) {
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
            // 🔥 CORRIGIDO: Usa /api/upload-auto (sincronizado com backend)
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
                this.clearSizeWarningContent();
                
                await this.loadAnalysisHistory();
            } else {
                const errorMsg = data?.detail || data?.error || 'Erro no upload';
                if (errorMsg.includes('Créditos insuficientes')) {
                    this.showNotification('💰 Créditos insuficientes!', 'warning');
                    this.redirectToPlanos();
                } else {
                    this.showNotification('❌ ' + errorMsg, 'error');
                }
                this.setUploadLoading(false);
            }
        } catch (error) {
            console.error('Erro no upload:', error);
            this.showNotification('❌ Erro ao processar arquivo', 'error');
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
            this.uploadButton.innerHTML = `${icon} Iniciar Análise <span class="credit-badge">${creditText}</span>`;
        }
    }
    
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
        
        if (file.size > this.MAX_FILE_SIZE_BYTES) {
            this.validateFileSize(file);
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
        
        if (this.fileName) this.fileName.textContent = file.name;
        if (this.fileSize) {
            this.fileSize.textContent = `${this.formatFileSize(file.size)} (${fileSizeKB}KB)`;
        }
        
        if (this.selectedFile) {
            this.selectedFile.classList.remove('d-none');
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
                this.uploadButton.innerHTML = `🚀 Iniciar Análise <span class="credit-badge">${creditText}</span>`;
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
                reject(new Error('PapaParse não carregado'));
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
                            const values = result.data.map(row => row[col]).filter(v => v !== null);
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
                reject(new Error('XLSX não carregado'));
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
                            const values = rows.map(row => row[col]).filter(v => v !== undefined);
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
        
        let html = `
            <div class="preview-container mt-3">
                <h6><i class="fas fa-chart-line me-2"></i>Pré-visualização</h6>
                <div class="table-responsive">
                    <table class="table table-sm table-bordered">
                        <thead class="table-light">
                            <tr>
                                ${columns.slice(0, 6).map(col => `<th>${this.truncate(col, 20)}</th>`).join('')}
                            </tr>
                        </thead>
                        <tbody>
                            ${data.slice(0, 5).map(row => `
                                <tr>
                                    ${columns.slice(0, 6).map(col => {
                                        let value = row[col];
                                        if (value === undefined || value === null) value = '—';
                                        return `<td>${this.truncate(String(value), 20)}</td>`;
                                    }).join('')}
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
                <div class="text-muted small mt-2">
                    📊 ${columns.length} colunas (${numericCount} numéricas, ${textCount} texto)
                </div>
                <div class="text-success small mt-1">
                    ✅ Limite: ${this.MAX_FILE_SIZE_KB}KB
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
                        <div class="text-muted small mt-2" id="statusText">Iniciando...</div>
                    </div>
                </div>
            `;
            
            const uploadCard = document.querySelector('.upload-card');
            if (uploadCard) {
                uploadCard.insertAdjacentElement('afterend', container);
            }
        }
    }
    
    startProgressPolling() {
        if (this.pollInterval) clearInterval(this.pollInterval);
        
        this.pollInterval = setInterval(async () => {
            if (!this.currentProcessId) return;
            
            try {
                // 🔥 CORRIGIDO: Usa /api/status/{process_id}
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
                console.error('Polling error:', error);
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
            'completed': '✅ Concluído!',
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
        
        resultContainer.innerHTML = `
            <div class="card mt-3 border-success">
                <div class="card-body">
                    <h5 class="card-title text-success">📊 RESULTADO</h5>
                    <div class="row mt-3">
                        <div class="col-md-4">
                            <div class="text-center">
                                <h3>${stats.total || 0}</h3>
                                <small>Registros</small>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="text-center">
                                <h3>${analysisInfo.features_count || 0}</h3>
                                <small>Features</small>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="text-center">
                                <h3>${analysisInfo.model_used || 'AutoML'}</h3>
                                <small>Modelo</small>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    async loadAnalysisHistory() {
        if (this.isLoginPage() || this.isRegisterPage()) return;
        
        try {
            // 🔥 CORRIGIDO: Usa /api/analyses/history
            const response = await this.fetchWithAuth(`${this.apiBase}/analyses/history`);
            if (response && response.ok) {
                const data = await response.json();
                const analyses = data.analyses || data;
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
                <div class="timeline-item">
                    <div class="timeline-marker"></div>
                    <div class="timeline-content">
                        <p class="mb-1 text-muted">Nenhuma análise</p>
                    </div>
                </div>
            `;
            return;
        }
        
        const html = analyses.slice(0, 5).map(a => {
            const date = new Date(a.created_at);
            const statusClass = a.status === 'completed' ? 'bg-success' : 'bg-secondary';
            
            return `
                <div class="timeline-item">
                    <div class="timeline-marker ${statusClass}"></div>
                    <div class="timeline-content">
                        <p class="mb-1 small fw-bold">${this.escapeHtml(a.filename || 'Análise')}</p>
                        <small class="text-muted">${date.toLocaleDateString('pt-BR')}</small>
                    </div>
                </div>
            `;
        }).join('');
        
        container.innerHTML = html;
    }
    
    async loadDashboardStats() {
        if (this.isLoginPage() || this.isRegisterPage()) return;
        
        try {
            // 🔥 CORRIGIDO: Usa /api/stats
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
        
        try {
            // 🔥 CORRIGIDO: Usa /api/payments/balance
            const response = await this.fetchWithAuth(`${this.apiBase}/payments/balance`);
            if (response && response.ok) {
                const data = await response.json();
                this.displayPremiumInfo(data);
            }
        } catch (error) {
            console.error('Erro ao carregar premium:', error);
        }
    }
    
    displayPremiumInfo(data) {
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
        const currentCredits = this.getCredits();
        
        premiumContainer.innerHTML = `
            <div class="d-flex align-items-center justify-content-between flex-wrap">
                <div>
                    <i class="fas fa-crown text-warning me-2"></i>
                    <strong>⭐ PREMIUM ATIVO</strong>
                    <small class="ms-2">${daysLeft} dias • ${currentCredits}/${this.MAX_CREDITS_BALANCE} créditos</small>
                </div>
                <button class="btn btn-sm btn-outline-primary" onclick="window.app?.claimDailyCredit()" ${currentCredits >= this.MAX_CREDITS_BALANCE ? 'disabled' : ''}>
                    <i class="fas fa-gift me-1"></i> Receber
                </button>
            </div>
        `;
    }
    
    initializeElements() {
        this.uploadForm = document.getElementById('uploadForm');
        this.fileInput = document.getElementById('fileInput');
        this.uploadButton = document.getElementById('uploadButton');
        this.dropArea = document.getElementById('dropArea');
        this.selectedFile = document.getElementById('selectedFile');
        this.fileName = document.getElementById('fileName');
        this.fileSize = document.getElementById('fileSize');
        this.totalAnalises = document.getElementById('totalAnalises');
        this.analisesHoje = document.getElementById('analisesHoje');
        
        if (this.uploadButton) {
            this.uploadButton.disabled = true;
            this.uploadButton.innerHTML = `📁 Selecione um arquivo (max ${this.MAX_FILE_SIZE_KB}KB)`;
        }
    }
    
    bindEvents() {
        if (this.uploadForm) {
            this.uploadForm.addEventListener('submit', (e) => this.handleUpload(e));
        }
        
        if (this.dropArea) {
            this.dropArea.addEventListener('dragenter', (e) => this.handleDragEnter(e));
            this.dropArea.addEventListener('dragover', (e) => e.preventDefault());
            this.dropArea.addEventListener('dragleave', () => {
                if (this.dropArea) this.dropArea.classList.remove('dragover-glow');
            });
            this.dropArea.addEventListener('drop', (e) => this.handleDrop(e));
            this.dropArea.addEventListener('click', () => this.fileInput?.click());
        }
        
        if (this.fileInput) {
            this.fileInput.addEventListener('change', () => this.handleFileSelect());
        }
        
        const removeFileBtn = document.getElementById('removeFile');
        if (removeFileBtn) {
            removeFileBtn.addEventListener('click', () => this.resetFileSelection());
        }
        
        const buyCreditsBtn = document.getElementById('buyCreditsBtn');
        if (buyCreditsBtn) {
            buyCreditsBtn.addEventListener('click', () => this.buyCredits());
        }
    }
    
    resetFileSelection() {
        if (this.fileInput) this.fileInput.value = '';
        if (this.selectedFile) this.selectedFile.classList.add('d-none');
        if (this.uploadButton) {
            this.uploadButton.disabled = true;
            this.uploadButton.innerHTML = `📁 Selecione um arquivo (max ${this.MAX_FILE_SIZE_KB}KB)`;
        }
        
        const preview = document.getElementById('dataPreview');
        if (preview) preview.classList.add('d-none');
        
        this.clearSizeWarningContent();
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
                    window.location.href = '/login';
                }
            });
        }
    }
    
    async fetchWithAuth(url, options = {}) {
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
            'Authorization': `Bearer ${token}`,
            ...options.headers
        };
        
        try {
            let response = await fetch(url, { ...options, headers });
            
            if (response.status === 401) {
                const refreshed = await this.refreshTokenSafely();
                if (refreshed) {
                    const newToken = localStorage.getItem('access_token');
                    headers['Authorization'] = `Bearer ${newToken}`;
                    response = await fetch(url, { ...options, headers });
                    return response;
                }
                this.redirectToLogin();
                return null;
            }
            return response;
        } catch (error) {
            console.error('Fetch error:', error);
            return null;
        }
    }
    
    showNotification(message, type = 'info') {
        if (window.toastr && typeof window.toastr[type] === 'function') {
            toastr[type](message);
            return;
        }
        
        const bgColor = type === 'success' ? '#48bb78' : 
                        type === 'error' ? '#f56565' : '#4299e1';
        
        const notification = document.createElement('div');
        notification.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: white;
            border-left: 4px solid ${bgColor};
            padding: 12px 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            z-index: 10000;
            animation: slideInRight 0.3s ease;
        `;
        notification.innerHTML = `<i class="fas fa-${type === 'success' ? 'check-circle' : 'info-circle'} me-2"></i>${message}`;
        document.body.appendChild(notification);
        
        setTimeout(() => notification.remove(), 5000);
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
            this.redirectToPlanos();
        }
    }
}

// ===== INSTANCIAÇÃO GLOBAL =====
document.addEventListener('DOMContentLoaded', () => {
    console.log('📄 Inicializando app...');
    window.app = new AutoAnalytics();
});

// Fallback
if (document.readyState !== 'loading') {
    window.app = new AutoAnalytics();
}

// Exportar funções globais
window.getApp = () => window.app;
window.claimDailyCredit = () => window.app?.claimDailyCredit();
window.showCreditsModal = () => window.app?.showCreditsModal();

// CSS
if (!document.getElementById('appStyles')) {
    const style = document.createElement('style');
    style.id = 'appStyles';
    style.textContent = `
        @keyframes slideInRight {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        .dragover-glow {
            background: rgba(102,126,234,0.1);
            border: 2px dashed #667eea !important;
        }
        .credit-badge {
            background: rgba(255,255,255,0.3);
            padding: 2px 8px;
            border-radius: 20px;
            font-size: 0.7rem;
            margin-left: 8px;
        }
        .timeline-item {
            position: relative;
            padding-left: 20px;
            margin-bottom: 15px;
        }
        .timeline-marker {
            position: absolute;
            left: 0;
            top: 5px;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #667eea;
        }
        .timeline-marker.bg-success { background: #48bb78; }
        .timeline-content { padding-left: 5px; }
        .alert-warning {
            background-color: #fff3cd;
            border-color: #ffeeba;
            color: #856404;
        }
    `;
    document.head.appendChild(style);
}

console.log('✅ app.js carregado - Limite: 200KB - TOTALMENTE CORRIGIDO E SINCRONIZADO');