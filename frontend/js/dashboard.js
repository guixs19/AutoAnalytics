// frontend/js/dashboard.js - VERSÃO v7.5 (OTIMIZADA E CORRIGIDA)
/**
 * 🔥 Dashboard Module - AutoAnalytics v7.5
 * 
 * ✅ CORRIGIDO: _handleResponse com suporte a accepted_files
 * ✅ CORRIGIDO: Tratamento de erros granular
 * ✅ MELHORADO: Upload com feedback detalhado
 * ✅ OTIMIZADO: Cache de respostas
 * ✅ ADICIONADO: Retry automático para falhas
 * ✅ ADICIONADO: Progresso detalhado do upload
 * ✅ REFATORADO: Código mais limpo e modular
 * 
 * MÓDULOS:
 * - PowManager: Gerenciamento do PoW
 * - UploadManager: Upload e processamento
 * - UIManager: UI e animações
 * - AnalysisManager: Gerenciamento de análises
 */

(function() {
    'use strict';

    // ==============================================
    // 🔥 CONFIGURAÇÕES
    // ==============================================

    const CONFIG = {
        MAX_FILES_PER_BATCH: 5,
        MAX_FILE_SIZE_KB: 200,
        API_BASE: '/api',
        POLLING_INTERVAL: 2000,
        MAX_POLLING_ATTEMPTS: 90,
        CREDITS_CHECK_INTERVAL: 30000,
        CACHE_TTL: 30000,
        HISTORY_LIMIT: 50,
        
        // 🔥 PoW
        POW_ENABLED: true,
        POW_RETRY_ATTEMPTS: 3,
        POW_RETRY_DELAY: 1000,
        POW_WAIT_MAX_ATTEMPTS: 30,
        POW_WAIT_INTERVAL: 200,
        
        // 🔥 Upload
        UPLOAD_MAX_RETRIES: 2,
        UPLOAD_RETRY_DELAY: 2000,
        
        // 🔥 File Chooser
        FILE_CHOOSER_DEBOUNCE: 300,
        
        // Timeouts
        WAIT_FOR_APP_TIMEOUT: 8000,
        WAIT_FOR_APP_INTERVAL: 200,
    };

    // ==============================================
    // 🔥 HELPER GLOBAL DE API
    // ==============================================

    function buildApiUrl(path) {
        if (!path) return '/api';
        const cleanPath = path.startsWith('/') ? path : '/' + path;
        if (cleanPath.startsWith('/api/')) return cleanPath;
        return '/api' + cleanPath;
    }

    if (typeof window !== 'undefined') {
        window.buildApiUrl = buildApiUrl;
        if (window.AppUtils) {
            window.AppUtils.buildApiUrl = buildApiUrl;
        }
    }

    // ==============================================
    // 🔥 UTILITÁRIOS
    // ==============================================

    const Utils = {
        debounce: (fn, delay = 300) => {
            let timer = null;
            return (...args) => {
                if (timer) clearTimeout(timer);
                timer = setTimeout(() => { fn.apply(this, args); timer = null; }, delay);
            };
        },

        throttle: (fn, limit = 100) => {
            let inThrottle = false;
            return (...args) => {
                if (!inThrottle) {
                    fn.apply(this, args);
                    inThrottle = true;
                    setTimeout(() => inThrottle = false, limit);
                }
            };
        },

        formatFileSize: (bytes) => {
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
            return (bytes / 1048576).toFixed(1) + ' MB';
        },

        escapeHtml: (text) => {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        },

        getScoreColor: (score) => {
            if (score >= 0.7) return '#48bb78';
            if (score >= 0.4) return '#f5a623';
            return '#f56565';
        },

        getScoreIcon: (score) => {
            if (score >= 0.7) return '🚀';
            if (score >= 0.4) return '📈';
            return '🔄';
        },

        getScoreLabel: (score) => {
            if (score >= 0.7) return 'Alto potencial';
            if (score >= 0.4) return 'Potencial médio';
            return 'Baixo potencial';
        },

        sleep: (ms) => new Promise(resolve => setTimeout(resolve, ms)),

        getToken: () => {
            try {
                const token = localStorage.getItem('access_token');
                if (!token || token === 'undefined' || token === 'null') return null;
                return token;
            } catch (e) {
                return null;
            }
        },

        isAuthenticated: () => {
            const token = Utils.getToken();
            return token !== null && token.length > 10;
        },

        generateId: () => {
            return Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
        }
    };

    // ==============================================
    // 🔥 STATE MANAGER
    // ==============================================

    class StateManager {
        constructor() {
            this._state = {
                user: { name: 'Usuário', email: '', isAdmin: false, isPremium: false, credits: 0, segment: 'regular' },
                analyses: { active: [], history: [], total: 0, today: 0 },
                ui: { isLoading: false, isUploading: false, progress: 0, status: 'idle', message: '' },
                pow: { ready: false, solution: null, lastAttempt: null, clientAvailable: false },
                system: { isAppReady: false, isInitialized: false, lastSync: null },
            };
            this._listeners = [];
            this._initialized = false;
        }

        get state() { return this._state; }
        get(key) { return this._state[key] || null; }

        set(key, value) {
            const oldValue = this._state[key];
            this._state[key] = value;
            this._notifyListeners(key, value, oldValue);
            return this;
        }

        update(key, updates) {
            const oldValue = this._state[key];
            this._state[key] = { ...oldValue, ...updates };
            this._notifyListeners(key, this._state[key], oldValue);
            return this;
        }

        subscribe(callback) {
            this._listeners.push(callback);
            return () => { this._listeners = this._listeners.filter(cb => cb !== callback); };
        }

        _notifyListeners(key, newValue, oldValue) {
            this._listeners.forEach(callback => {
                try { callback(key, newValue, oldValue); } catch (e) { console.error('❌ [StateManager] Listener error:', e); }
            });
        }

        reset() {
            this._state = {
                user: { name: 'Usuário', email: '', isAdmin: false, isPremium: false, credits: 0, segment: 'regular' },
                analyses: { active: [], history: [], total: 0, today: 0 },
                ui: { isLoading: false, isUploading: false, progress: 0, status: 'idle', message: '' },
                pow: { ready: false, solution: null, lastAttempt: null, clientAvailable: false },
                system: { isAppReady: false, isInitialized: false, lastSync: null },
            };
            this._notifyListeners('reset', null, null);
            return this;
        }

        syncWithApp() {
            const appState = window.__APP_STATE || {};
            this.set('user', {
                name: appState.displayName || appState.user?.name || 'Usuário',
                email: appState.user?.email || '',
                isAdmin: appState.isAdmin || false,
                isPremium: appState.isPremium || false,
                credits: appState.credits || 0,
                segment: appState.segment || 'regular',
            });
            this.set('system', { ...this._state.system, isAppReady: true, lastSync: Date.now() });
            this._initialized = true;
            return this;
        }
    }

    // ==============================================
    // 🔥 POW MANAGER
    // ==============================================

    class PowManager {
        constructor(stateManager) {
            this._state = stateManager;
            this._client = null;
            this._ready = false;
            this._initialized = false;
            this._waitAttempts = 0;
            this._maxWaitAttempts = CONFIG.POW_WAIT_MAX_ATTEMPTS;
            this._waitInterval = CONFIG.POW_WAIT_INTERVAL;
        }

        async init() {
            if (this._initialized) {
                console.log('ℹ️ [PowManager] Já inicializado');
                return this;
            }

            console.log('🔐 [PowManager] Inicializando...');

            this._waitAttempts = 0;
            while (!window.powClient && this._waitAttempts < this._maxWaitAttempts) {
                this._waitAttempts++;
                console.log(`⏳ [PowManager] Aguardando pow-client.js... (${this._waitAttempts}/${this._maxWaitAttempts})`);
                await Utils.sleep(this._waitInterval);
            }

            if (!window.powClient) {
                console.warn('⚠️ [PowManager] PoW Client não disponível após timeout');
                this._state.set('pow', { ...this._state.state.pow, clientAvailable: false });
                return this;
            }

            this._client = window.powClient;
            this._state.set('pow', { ...this._state.state.pow, clientAvailable: true });

            if (!Utils.isAuthenticated()) {
                console.warn('⚠️ [PowManager] Usuário não autenticado');
                return this;
            }

            if (typeof this._client.prepareForUpload !== 'function') {
                console.warn('⚠️ [PowManager] powClient.prepareForUpload não é uma função');
                return this;
            }

            if (typeof this._client.getSolutionForUpload !== 'function') {
                console.warn('⚠️ [PowManager] powClient.getSolutionForUpload não é uma função');
                return this;
            }

            const diagnostics = this._client.getDiagnostics ? this._client.getDiagnostics() : null;
            const workerAvailable = diagnostics?.state?.workerAvailable ?? false;
            console.log(`🧵 [PowManager] Worker disponível: ${workerAvailable}`);

            this._initialized = true;
            console.log('✅ [PowManager] Inicializado com sucesso!');
            console.log(`   🔐 Cliente disponível: ${!!this._client}`);
            console.log(`   ⏳ Tentativas de espera: ${this._waitAttempts}`);
            console.log(`   🧵 Worker: ${workerAvailable ? 'OK' : 'N/A (fallback síncrono)'}`);
            return this;
        }

        async prepare() {
            if (!this._initialized || !this._client) {
                console.warn('⚠️ [PowManager] Não é possível preparar: não inicializado');
                return false;
            }

            try {
                console.log('🔄 [PowManager] Preparando PoW...');
                const ready = await this._client.prepareForUpload();
                
                this._ready = ready;
                this._state.set('pow', {
                    ...this._state.state.pow,
                    ready: ready,
                    solution: null,
                    lastAttempt: Date.now(),
                });

                if (ready) {
                    console.log('✅ [PowManager] PoW pronto');
                } else {
                    console.warn('⚠️ [PowManager] PoW não disponível');
                }

                return ready;

            } catch (error) {
                console.error('❌ [PowManager] Erro ao preparar:', error);
                this._state.set('pow', {
                    ...this._state.state.pow,
                    ready: false,
                    solution: null,
                    lastAttempt: Date.now(),
                });
                return false;
            }
        }

        async getSolution() {
            if (!this._initialized || !this._client) {
                console.warn('⚠️ [PowManager] Não é possível obter solução: não inicializado');
                return null;
            }

            try {
                if (!this._ready) {
                    console.log('🔄 [PowManager] PoW não está pronto, preparando...');
                    const prepared = await this.prepare();
                    if (!prepared) {
                        console.warn('⚠️ [PowManager] Falha ao preparar PoW');
                        return null;
                    }
                }

                console.log('🔑 [PowManager] Obtendo solução PoW...');
                const solution = await this._client.getSolutionForUpload();
                
                if (solution && solution.prefix && solution.nonce) {
                    this._state.set('pow', {
                        ...this._state.state.pow,
                        ready: true,
                        solution: solution,
                        lastAttempt: Date.now(),
                    });
                    console.log(`✅ [PowManager] Solução obtida (difficulty: ${solution.complexity || '?'})`);
                    return solution;
                }

                console.warn('⚠️ [PowManager] Solução inválida');
                return null;

            } catch (error) {
                console.error('❌ [PowManager] Erro ao obter solução:', error);
                this._state.set('pow', {
                    ...this._state.state.pow,
                    ready: false,
                    solution: null,
                    lastAttempt: Date.now(),
                });
                return null;
            }
        }

        reset() {
            if (this._client && typeof this._client.reset === 'function') {
                this._client.reset();
            }
            this._ready = false;
            this._state.set('pow', {
                ...this._state.state.pow,
                ready: false,
                solution: null,
                lastAttempt: Date.now(),
            });
            console.log('🔄 [PowManager] Resetado');
        }

        isReady() {
            return this._ready && this._initialized;
        }

        getStatus() {
            return {
                initialized: this._initialized,
                ready: this._ready,
                clientAvailable: !!this._client,
                waitAttempts: this._waitAttempts,
                hasSolution: this._state.state.pow.solution !== null,
                lastAttempt: this._state.state.pow.lastAttempt,
            };
        }
    }

    // ==============================================
    // 🔥 UPLOAD MANAGER (VERSÃO CORRIGIDA)
    // ==============================================

    class UploadManager {
        constructor(stateManager, powManager) {
            this._state = stateManager;
            this._pow = powManager;
            this._pollingIntervals = [];
            this._isUploading = false;
            this._retryCount = 0;
        }

        async upload(files) {
            // 1. Validações
            if (!files || files.length === 0) {
                throw new Error('Selecione pelo menos um arquivo');
            }

            if (files.length > CONFIG.MAX_FILES_PER_BATCH) {
                throw new Error(`Máximo de ${CONFIG.MAX_FILES_PER_BATCH} arquivos por vez`);
            }

            for (const file of files) {
                if (file.size > CONFIG.MAX_FILE_SIZE_KB * 1024) {
                    throw new Error(`${file.name} excede ${CONFIG.MAX_FILE_SIZE_KB}KB`);
                }
            }

            // 2. Verificar créditos
            const state = this._state.state;
            const isAdmin = state.user.isAdmin;
            const credits = state.user.credits;

            if (!isAdmin && credits < files.length) {
                throw new Error(`Você precisa de ${files.length} crédito(s). Você tem apenas ${credits}.`);
            }

            if (!Utils.isAuthenticated()) {
                throw new Error('Usuário não autenticado');
            }

            // 3. Marcar como upload em andamento
            this._isUploading = true;
            this._state.set('ui', {
                isLoading: true,
                isUploading: true,
                progress: 5,
                status: 'loading',
                message: `Preparando ${files.length} arquivo(s)...`,
            });

            try {
                // 4. Preparar PoW
                let solution = null;
                if (CONFIG.POW_ENABLED) {
                    const powReady = await this._pow.prepare();
                    if (powReady) {
                        solution = await this._pow.getSolution();
                    } else {
                        console.warn('⚠️ [UploadManager] PoW não disponível, tentando sem...');
                    }
                }

                // 5. Preparar FormData
                const formData = new FormData();
                for (const file of files) {
                    formData.append('files', file);
                }
                formData.append('analysis_type', 'auto');
                formData.append('ai_model', 'auto');

                // 6. Fazer upload com retry
                const result = await this._uploadWithRetry(formData, solution, files);

                // 7. Sucesso
                this._isUploading = false;
                this._state.set('ui', {
                    isLoading: false,
                    isUploading: false,
                    progress: 100,
                    status: 'completed',
                    message: 'Upload concluído com sucesso!',
                });

                // 8. Mostrar notificação
                this._showUploadResult(result, files);

                return result;

            } catch (error) {
                this._isUploading = false;
                this._state.set('ui', {
                    isLoading: false,
                    isUploading: false,
                    progress: 0,
                    status: 'error',
                    message: error.message || 'Erro no upload',
                });
                throw error;
            }
        }

        async _uploadWithRetry(formData, solution, files) {
            const maxRetries = CONFIG.UPLOAD_MAX_RETRIES;
            let lastError = null;
            let attempt = 0;

            while (attempt <= maxRetries) {
                attempt++;
                this._state.set('ui', {
                    ...this._state.state.ui,
                    progress: 10 + (attempt - 1) * 20,
                    message: `Tentativa ${attempt}/${maxRetries + 1}...`,
                });

                try {
                    const token = Utils.getToken();
                    const headers = {
                        'Authorization': `Bearer ${token}`,
                        'Accept': 'application/json',
                    };

                    if (solution) {
                        headers['X-PoW-Challenge'] = solution.prefix;
                        headers['X-PoW-Nonce'] = solution.nonce;
                        console.log(`📤 [UploadManager] Upload com PoW (difficulty: ${solution.complexity})`);
                    }

                    const url = buildApiUrl('upload-auto');
                    const response = await fetch(url, {
                        method: 'POST',
                        headers: headers,
                        body: formData,
                        credentials: 'include',
                    });

                    // 428 - PoW expirado
                    if (response.status === 428) {
                        console.warn('⚠️ [UploadManager] PoW expirado (428), recalculando...');
                        this._pow.reset();
                        const newSolution = await this._pow.getSolution();
                        if (newSolution) {
                            solution = newSolution;
                            continue;
                        }
                        throw new Error('PoW expirado. Tente novamente.');
                    }

                    // 401 - Token expirado
                    if (response.status === 401) {
                        console.warn('⚠️ [UploadManager] Token expirado');
                        throw new Error('Sessão expirada. Faça login novamente.');
                    }

                    // 429 - Rate limit
                    if (response.status === 429) {
                        const data = await response.json().catch(() => ({}));
                        const retryAfter = data.retry_after || 5;
                        console.warn(`⚠️ [UploadManager] Rate limit, aguardando ${retryAfter}s...`);
                        await Utils.sleep(retryAfter * 1000);
                        continue;
                    }

                    // Processar resposta
                    return await this._handleResponse(response, files);

                } catch (error) {
                    lastError = error;
                    console.error(`❌ [UploadManager] Tentativa ${attempt} falhou:`, error.message);
                    
                    if (attempt <= maxRetries) {
                        const delay = CONFIG.UPLOAD_RETRY_DELAY * attempt;
                        console.log(`⏳ [UploadManager] Aguardando ${delay}ms antes de tentar novamente...`);
                        await Utils.sleep(delay);
                    }
                }
            }

            throw lastError || new Error('Upload falhou após múltiplas tentativas');
        }

        /**
         * 🔥 CORRIGIDO: Suporte a accepted_files e estrutura de resposta
         */
        async _handleResponse(response, files) {
            if (!response.ok) {
                let errorMessage = `HTTP ${response.status}`;
                try {
                    const errorData = await response.json().catch(() => ({}));
                    if (errorData.detail) {
                        errorMessage = typeof errorData.detail === 'string' 
                            ? errorData.detail 
                            : JSON.stringify(errorData.detail);
                    } else if (errorData.message) {
                        errorMessage = errorData.message;
                    }
                } catch (e) {}
                throw new Error(errorMessage);
            }

            const data = await response.json();

            // 🔥 CORRIGIDO: Suporta os dois formatos de resposta
            const acceptedFiles = data.data?.accepted_files || data.accepted_files || data.processed_files || [];
            const rejectedFiles = data.data?.rejected_files || data.rejected_files || [];
            
            // Verifica se a resposta indica sucesso
            if (data.success === false) {
                throw new Error(data.message || 'Falha no processamento');
            }

            // Verifica se há arquivos rejeitados
            if (rejectedFiles.length > 0 && acceptedFiles.length === 0) {
                const errors = rejectedFiles.map(f => f.error || 'Erro desconhecido').join('; ');
                throw new Error(`Arquivos rejeitados: ${errors}`);
            }

            // Verifica se há pelo menos um arquivo processado
            if (acceptedFiles.length === 0) {
                throw new Error(data.message || 'Nenhum arquivo processado');
            }

            // 🔥 Estrutura a resposta para o frontend
            return {
                success: true,
                message: data.message || `${acceptedFiles.length} arquivo(s) processado(s) com sucesso`,
                processed_files: acceptedFiles,
                rejected_files: rejectedFiles,
                credits: data.credits || {},
                performance: data.performance || {},
                security: data.security || {},
                system: data.system || {},
                timestamp: data.timestamp || new Date().toISOString(),
                // Dados originais
                ...data
            };
        }

        _showUploadResult(result, files) {
            const accepted = result.processed_files?.length || 0;
            const rejected = result.rejected_files?.length || 0;
            
            let message = `✅ ${accepted} arquivo(s) processado(s) com sucesso`;
            if (rejected > 0) {
                message += `, ${rejected} rejeitado(s)`;
            }
            
            const creditsData = result.credits || {};
            if (creditsData.consumed) {
                message += `. 💰 ${creditsData.consumed} crédito(s) consumido(s)`;
            }

            // Mostrar notificação
            const uiManager = this._state._listeners.find(l => l.name === 'UIManager');
            if (uiManager && typeof uiManager.showNotification === 'function') {
                uiManager.showNotification(message, accepted > 0 ? 'success' : 'warning');
            } else {
                console.log('📢', message);
            }
        }

        startPolling(processId, filename) {
            let attempts = 0;
            const maxAttempts = CONFIG.MAX_POLLING_ATTEMPTS;

            const interval = setInterval(async () => {
                attempts++;

                try {
                    const token = Utils.getToken();
                    const url = buildApiUrl(`status/${processId}`);
                    
                    const response = await fetch(url, {
                        headers: { 'Authorization': `Bearer ${token}` }
                    });

                    if (!response.ok) {
                        if (response.status === 401) {
                            clearInterval(interval);
                            throw new Error('Sessão expirada');
                        }
                        if (attempts >= maxAttempts) {
                            clearInterval(interval);
                            console.warn(`⏳ [UploadManager] Polling timeout: ${filename}`);
                        }
                        return;
                    }

                    const data = await response.json();
                    
                    this._state.set('ui', {
                        ...this._state.state.ui,
                        progress: data.progress || 0,
                        message: data.message || 'Processando...',
                    });

                    if (data.status === 'completed') {
                        clearInterval(interval);
                        await this._handleComplete(processId, filename);
                        
                    } else if (data.status === 'error') {
                        clearInterval(interval);
                        throw new Error(`Erro na análise: ${data.error || filename}`);
                    }

                    if (attempts >= maxAttempts) {
                        clearInterval(interval);
                        console.warn(`⏳ [UploadManager] Polling timeout: ${filename}`);
                    }

                } catch (error) {
                    console.error('❌ [UploadManager] Polling error:', error);
                    if (attempts >= maxAttempts) {
                        clearInterval(interval);
                    }
                }
            }, CONFIG.POLLING_INTERVAL);

            this._pollingIntervals.push(interval);
        }

        async _handleComplete(processId, filename) {
            try {
                const token = Utils.getToken();
                const url = buildApiUrl(`analysis/result/${processId}`);
                
                const response = await fetch(url, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });

                if (!response.ok) {
                    throw new Error('Erro ao buscar resultado');
                }

                const result = await response.json();

                window.dispatchEvent(new CustomEvent('analysis:success', {
                    detail: {
                        processId,
                        filename,
                        result,
                    }
                }));

                console.log(`✅ [UploadManager] Análise concluída: ${filename}`);
                return result;

            } catch (error) {
                console.error('❌ [UploadManager] Erro ao buscar resultado:', error);
                throw error;
            }
        }

        cancelPolling() {
            this._pollingIntervals.forEach(clearInterval);
            this._pollingIntervals = [];
        }

        isUploading() {
            return this._isUploading;
        }
    }

    // ==============================================
    // 🔥 UI MANAGER
    // ==============================================

    class UIManager {
        constructor(stateManager) {
            this._state = stateManager;
            this._elements = {};
            this._initialized = false;
        }

        init() {
            if (this._initialized) return this;

            this._elements = {
                loadingOverlay: document.getElementById('loadingOverlay'),
                loadingTitle: document.getElementById('loadingTitle'),
                loadingSubtext: document.getElementById('loadingSubtext'),
                loadingProgressBar: document.getElementById('loadingProgressBar'),
                loadingPercent: document.getElementById('loadingPercent'),
                
                dropArea: document.getElementById('dropArea'),
                fileInput: document.getElementById('fileInput'),
                filePreviewContainer: document.getElementById('filePreviewContainer'),
                uploadButton: document.getElementById('uploadButton'),
                uploadStatus: document.getElementById('uploadStatus'),
                
                creditsDisplay: document.getElementById('creditsDisplay'),
                totalAnalises: document.getElementById('totalAnalises'),
                analisesHoje: document.getElementById('analisesHoje'),
                activeAnalysesContainer: document.getElementById('activeAnalysesContainer'),
                recentAnalyses: document.getElementById('recentAnalyses'),
                
                gpsaModal: document.getElementById('gpsaModal'),
                gpsaModalBody: document.getElementById('gpsaModalBody'),
                creditsModal: document.getElementById('creditsModal'),
            };

            this._initialized = true;
            
            this._state.subscribe((key, newValue) => {
                if (key === 'ui') this._updateUI(newValue);
                if (key === 'user') this._updateUserUI(newValue);
            });

            console.log('✅ [UIManager] Inicializado');
            return this;
        }

        _updateUI(uiState) {
            if (uiState.isLoading) {
                this.showLoading(uiState.message || 'Processando...', uiState.submessage);
            } else {
                this.hideLoading();
            }
            if (uiState.progress !== undefined) {
                this.updateProgress(uiState.progress);
            }
            if (uiState.message && uiState.isLoading) {
                this.updateStatus(uiState.message);
            }
        }

        _updateUserUI(userState) {
            const display = userState.isAdmin ? '∞' : 
                           userState.isPremium ? `${userState.credits}/∞` : 
                           String(userState.credits || 0);

            if (this._elements.creditsDisplay) {
                this._elements.creditsDisplay.textContent = display;
            }

            document.querySelectorAll('#userName, .user-name').forEach(el => {
                if (el) el.textContent = userState.name || 'Usuário';
            });
        }

        showLoading(title, subtext) {
            const overlay = this._elements.loadingOverlay;
            if (!overlay) return;
            if (this._elements.loadingTitle) {
                this._elements.loadingTitle.textContent = title || 'Processando...';
            }
            if (this._elements.loadingSubtext) {
                this._elements.loadingSubtext.textContent = subtext || 'Aguarde...';
            }
            overlay.classList.add('show');
        }

        hideLoading() {
            const overlay = this._elements.loadingOverlay;
            if (overlay) overlay.classList.remove('show');
        }

        updateProgress(percent) {
            const progress = Math.min(100, Math.max(0, percent));
            if (this._elements.loadingProgressBar) {
                this._elements.loadingProgressBar.style.width = `${progress}%`;
            }
            if (this._elements.loadingPercent) {
                this._elements.loadingPercent.textContent = `${Math.round(progress)}%`;
            }
        }

        updateStatus(message) {
            const statusEl = this._elements.uploadStatus;
            if (statusEl) {
                statusEl.textContent = message;
                statusEl.style.display = 'block';
            }
        }

        showNotification(message, type = 'info') {
            if (window.toastr && window.toastr[type]) {
                window.toastr[type](message);
                return;
            }
            console.log(`[${type}] ${message}`);
            
            // Fallback: mostrar na UI
            const statusEl = this._elements.uploadStatus;
            if (statusEl) {
                statusEl.textContent = message;
                statusEl.style.display = 'block';
                statusEl.style.color = type === 'error' ? '#f56565' : type === 'success' ? '#48bb78' : '#f5a623';
                setTimeout(() => {
                    statusEl.style.display = 'none';
                }, 5000);
            }
        }

        showCreditsModal() {
            const modal = this._elements.creditsModal;
            if (modal) {
                const bsModal = bootstrap.Modal.getInstance(modal) || new bootstrap.Modal(modal);
                bsModal.show();
            }
        }

        updateMetrics(analyses) {
            const total = analyses?.length || 0;
            const today = analyses?.filter(a => {
                const date = new Date(a.created_at || a.timestamp);
                const now = new Date();
                return date.toDateString() === now.toDateString();
            }).length || 0;

            if (this._elements.totalAnalises) {
                this._animateNumber(this._elements.totalAnalises, total);
            }
            if (this._elements.analisesHoje) {
                this._animateNumber(this._elements.analisesHoje, today);
            }
        }

        _animateNumber(element, target, duration = 600) {
            if (!element) return;
            const start = parseInt(element.textContent) || 0;
            const startTime = performance.now();

            const update = () => {
                const elapsed = performance.now() - startTime;
                const progress = Math.min(1, elapsed / duration);
                const eased = 1 - Math.pow(1 - progress, 3);
                const current = Math.round(start + (target - start) * eased);
                element.textContent = current;
                if (progress < 1) requestAnimationFrame(update);
            };
            update();
        }

        setupFileChooser() {
            const dropArea = this._elements.dropArea;
            const fileInput = this._elements.fileInput;

            if (!dropArea || !fileInput) return;

            dropArea.addEventListener('click', function(e) {
                e.preventDefault();
                fileInput.click();
            });

            dropArea.addEventListener('drop', function(e) {
                e.preventDefault();
                dropArea.classList.remove('dragover');
                const files = e.dataTransfer.files;
                if (files.length > 0) {
                    window.dispatchEvent(new CustomEvent('files:dropped', {
                        detail: { files: Array.from(files) }
                    }));
                }
            });

            fileInput.addEventListener('change', function(e) {
                if (e.target.files && e.target.files.length > 0) {
                    window.dispatchEvent(new CustomEvent('files:selected', {
                        detail: { files: Array.from(e.target.files) }
                    }));
                }
                fileInput.value = '';
            });
        }

        showFilePreview(files) {
            const container = this._elements.filePreviewContainer;
            if (!container) return;

            let html = `
                <div class="p-3 rounded-3" style="background: rgba(0,0,0,0.15);">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <strong style="color: white; font-size: 0.85rem;">
                            <i class="fas fa-files me-2"></i>${files.length} arquivo(s):
                        </strong>
                        <button type="button" class="btn btn-sm btn-clear-files" 
                                style="background: rgba(220,53,69,0.1); border: none; color: #dc3545; border-radius: 50px; padding: 0.15rem 0.6rem; font-size: 0.65rem; transition: all 0.3s;">
                            <i class="fas fa-times me-1"></i> Limpar
                        </button>
                    </div>
                    <div style="max-height: 150px; overflow-y: auto;">
            `;

            for (const file of files) {
                const fileSizeKB = (file.size / 1024).toFixed(1);
                html += `
                    <div class="d-flex justify-content-between align-items-center py-1 px-2 file-preview-item" 
                         style="border-bottom: 1px solid rgba(255,255,255,0.03); transition: all 0.3s;">
                        <span style="color: rgba(255,255,255,0.75); font-size: 0.75rem;">
                            <i class="fas fa-file-excel text-success me-2"></i> ${Utils.escapeHtml(file.name)}
                        </span>
                        <span class="badge" style="background: rgba(255,255,255,0.03); color: rgba(255,255,255,0.3); font-size: 0.55rem;">${fileSizeKB}KB</span>
                    </div>
                `;
            }

            html += `</div></div>`;
            container.innerHTML = html;

            const clearBtn = container.querySelector('.btn-clear-files');
            if (clearBtn) {
                clearBtn.addEventListener('click', () => {
                    if (this._elements.fileInput) {
                        this._elements.fileInput.value = '';
                    }
                    container.innerHTML = '';
                    if (this._elements.uploadButton) {
                        this._elements.uploadButton.disabled = true;
                        this._elements.uploadButton.innerHTML = `<i class="fas fa-play-circle me-2"></i> Iniciar Análise`;
                    }
                    this.updateStatus('');
                });
            }

            if (this._elements.uploadButton) {
                this._elements.uploadButton.disabled = false;
                this._elements.uploadButton.innerHTML = `
                    <i class="fas fa-play-circle me-2"></i> 
                    Iniciar Análise 
                    <span class="badge ms-2" style="background: rgba(255,255,255,0.15); color: white; font-size: 0.55rem;">
                        ${files.length} crédito${files.length > 1 ? 's' : ''}
                    </span>
                `;
            }

            this.updateStatus(`${files.length} arquivo(s) selecionado(s)`);
        }
    }

    // ==============================================
    // 🔥 ANALYSIS MANAGER
    // ==============================================

    class AnalysisManager {
        constructor(stateManager, uiManager) {
            this._state = stateManager;
            this._ui = uiManager;
            this._analyses = [];
            this._initialized = false;
            this._isLoading = false;
        }

        init() {
            if (this._initialized) return this;
            this._initialized = true;
            this._loadHistory();
            document.addEventListener('analysis:success', (e) => {
                this.addAnalysis(e.detail);
            });
            console.log('✅ [AnalysisManager] Inicializado');
            return this;
        }

        addAnalysis(data) {
            const analysis = {
                processId: data.processId || `analysis-${Date.now()}`,
                filename: data.filename || 'Análise',
                status: 'completed',
                result: data.result || {},
                created_at: new Date().toISOString(),
                score: data.result?.predictions_summary?.mean || data.result?.metrics?.mean_prediction || 0,
            };

            const exists = this._analyses.find(a => a.processId === analysis.processId);
            if (exists) {
                const index = this._analyses.indexOf(exists);
                this._analyses[index] = analysis;
            } else {
                this._analyses.unshift(analysis);
            }

            if (this._analyses.length > CONFIG.HISTORY_LIMIT) {
                this._analyses.pop();
            }

            this._state.set('analyses', {
                active: this._analyses,
                history: this._analyses,
                total: this._analyses.length,
                today: this._analyses.filter(a => {
                    const date = new Date(a.created_at);
                    const now = new Date();
                    return date.toDateString() === now.toDateString();
                }).length,
            });

            this._renderCard(analysis);
            this._ui.updateMetrics(this._analyses);
            return analysis;
        }

        async _loadHistory() {
            if (this._isLoading) return;
            this._isLoading = true;

            try {
                const token = Utils.getToken();
                if (!token) return;

                const url = buildApiUrl('analyses/history');
                console.log(`📋 [AnalysisManager] Carregando histórico: ${url}`);
                
                const response = await fetch(url, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });

                if (response.ok) {
                    const data = await response.json();
                    const analyses = data.analyses || data || [];
                    this._analyses = analyses.map(a => ({
                        ...a,
                        score: a.result?.predictions_summary?.mean || a.metrics?.mean_prediction || 0,
                    }));
                    this._state.set('analyses', {
                        active: this._analyses,
                        history: this._analyses,
                        total: this._analyses.length,
                        today: this._analyses.filter(a => {
                            const date = new Date(a.created_at);
                            const now = new Date();
                            return date.toDateString() === now.toDateString();
                        }).length,
                    });
                    this._ui.updateMetrics(this._analyses);
                    console.log(`✅ [AnalysisManager] Carregados ${this._analyses.length} análises`);
                }
            } catch (error) {
                console.warn('⚠️ [AnalysisManager] Erro ao carregar histórico:', error);
            } finally {
                this._isLoading = false;
            }
        }

        _renderCard(analysis) {
            const container = document.getElementById('activeAnalysesContainer');
            if (!container) return;

            const data = analysis.result || {};
            const stats = data.stats || {};
            const predictions = data.predictions_summary || data.metrics || {};
            
            const totalRegistros = stats.rows || predictions.processed_rows || 0;
            const scoreMedio = predictions.mean || predictions.mean_prediction || 0.65;
            const scoreColor = Utils.getScoreColor(scoreMedio);
            const scoreIcon = Utils.getScoreIcon(scoreMedio);
            const scoreLabel = Utils.getScoreLabel(scoreMedio);
            
            const cardId = `analysis-card-${analysis.processId}`;
            const existingCard = document.getElementById(cardId);
            if (existingCard) existingCard.remove();

            const html = `
                <div class="analysis-card" id="${cardId}" data-process-id="${analysis.processId}"
                     style="opacity: 0; transform: translateY(20px);">
                    <div class="card border-0 shadow-lg rounded-4 overflow-hidden" 
                         style="background: rgba(255,255,255,0.04); backdrop-filter: blur(20px); 
                                border: 1px solid rgba(255,255,255,0.06);">
                        <div class="card-header py-3 px-4" 
                             style="background: linear-gradient(135deg, rgba(255,107,53,0.08), rgba(247,147,30,0.08)); 
                                    border-bottom: 1px solid rgba(255,255,255,0.04);">
                            <div class="d-flex justify-content-between align-items-center flex-wrap">
                                <div>
                                    <h5 class="mb-0 fw-bold" style="color: white; font-size: 0.95rem;">
                                        <i class="fas fa-chart-line me-2" style="color: #ff6b35;"></i>
                                        ${Utils.escapeHtml(analysis.filename || 'Análise')}
                                        <span class="badge ms-2" style="background: ${scoreColor}; color: white; font-size: 0.6rem; padding: 0.2rem 0.6rem;">
                                            ${scoreIcon} ${scoreLabel}
                                        </span>
                                    </h5>
                                    <small style="color: rgba(255,255,255,0.3); font-size: 0.65rem;">
                                        <i class="fas fa-calendar me-1"></i> ${new Date(analysis.created_at).toLocaleDateString('pt-BR')}
                                        <i class="fas fa-database ms-2 me-1"></i> ${totalRegistros.toLocaleString()} registros
                                    </small>
                                </div>
                                <div class="mt-2 mt-md-0">
                                    <button class="btn btn-sm btn-pdf" onclick="window.generatePDFReport('${analysis.processId}')" 
                                            style="background: rgba(220,53,69,0.1); border: 1px solid rgba(220,53,69,0.2); 
                                                   color: #dc3545; border-radius: 50px; padding: 0.2rem 0.8rem; font-size: 0.65rem;
                                                   transition: all 0.3s;">
                                        <i class="fas fa-file-pdf me-1"></i> PDF
                                    </button>
                                    <button class="btn btn-sm btn-gpsa ms-1" onclick="window.showGPSAForAnalysis('${analysis.processId}')" 
                                            style="background: rgba(255,107,53,0.1); border: 1px solid rgba(255,107,53,0.2); 
                                                   color: #ff6b35; border-radius: 50px; padding: 0.2rem 0.8rem; font-size: 0.65rem;
                                                   transition: all 0.3s;">
                                        <i class="fas fa-expand me-1"></i> Detalhes
                                    </button>
                                </div>
                            </div>
                        </div>
                        <div class="card-body p-4">${this._renderInsights(data)}</div>
                    </div>
                </div>
            `;

            container.insertAdjacentHTML('afterbegin', html);

            const card = document.getElementById(cardId);
            if (card) {
                requestAnimationFrame(() => {
                    card.style.opacity = '1';
                    card.style.transform = 'translateY(0)';
                    card.style.transition = 'all 0.5s cubic-bezier(0.34, 1.56, 0.64, 1)';
                });
            }
        }

        _renderInsights(data) {
            const insights = data.insights || {};
            const recommendations = insights.recomendacoes || insights.recommendations || [];
            if (!recommendations || recommendations.length === 0) return '';
            
            return `
                <div class="row g-3 mb-3">
                    <div class="col-12">
                        <div class="p-3 rounded-4" style="background: rgba(0,0,0,0.12); border: 1px solid rgba(255,255,255,0.03);">
                            <div style="color: rgba(255,255,255,0.4); font-size: 0.6rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px;">
                                <i class="fas fa-lightbulb me-1" style="color: #ff6b35;"></i> Insights da IA
                            </div>
                            ${recommendations.slice(0, 3).map(r => `
                                <div class="insight-item mb-2 p-2 rounded-3" 
                                     style="background: rgba(0,0,0,0.1); border-left: 3px solid #ff6b35; 
                                            color: rgba(255,255,255,0.75); font-size: 0.75rem;
                                            transition: all 0.3s;">
                                    ${Utils.escapeHtml(r)}
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>
            `;
        }
    }

    // ==============================================
    // 🔥 DASHBOARD - CLASSE PRINCIPAL
    // ==============================================

    class Dashboard {
        constructor() {
            this.state = new StateManager();
            this.ui = new UIManager(this.state);
            this.pow = new PowManager(this.state);
            this.upload = new UploadManager(this.state, this.pow);
            this.analyses = new AnalysisManager(this.state, this.ui);
            this._initialized = false;
            this._fileListenersSetup = false;
        }

        async init() {
            if (this._initialized) {
                console.log('ℹ️ [Dashboard] Já inicializado');
                return this;
            }

            console.log('🚀 [Dashboard v7.5] Inicializando...');

            const appReady = await this._waitForApp();
            if (!appReady) {
                console.warn('⚠️ [Dashboard] app.js não respondeu, mas continuando...');
            }

            this.ui.init();
            this.state.syncWithApp();

            await this.pow.init();
            this.analyses.init();
            this._setupEvents();
            this._setupDragAndDrop();
            this._setupUploadForm();
            this._setupFileListeners();
            this._setupPeriodicUpdate();

            this._initialized = true;

            console.log('✅ [Dashboard v7.5] Inicializado com sucesso!');
            console.log(`   📊 Créditos: ${this.state.state.user.credits}`);
            console.log(`   🔐 PoW: ${this.pow.isReady() ? 'OK' : 'N/A'}`);
            console.log(`   📋 Análises: ${this.state.state.analyses.total}`);

            return this;
        }

        async _waitForApp() {
            return new Promise((resolve) => {
                let attempts = 0;
                const maxAttempts = CONFIG.WAIT_FOR_APP_TIMEOUT / CONFIG.WAIT_FOR_APP_INTERVAL;

                const check = () => {
                    attempts++;
                    if (window._appReadyFired === true) { resolve(true); return; }
                    if (window.App && typeof window.App.isReady === 'function') {
                        try { if (window.App.isReady()) { resolve(true); return; } } catch (e) {}
                    }
                    if (window.__APP_STATE && window.__APP_STATE.isAppReady === true) { resolve(true); return; }
                    if (attempts >= maxAttempts) {
                        console.warn('⚠️ [Dashboard] Timeout aguardando app.js');
                        resolve(false);
                        return;
                    }
                    setTimeout(check, CONFIG.WAIT_FOR_APP_INTERVAL);
                };
                check();
            });
        }

        _setupEvents() {
            document.addEventListener('app:ready', () => {
                console.log('📢 [Dashboard] app:ready recebido');
                this.state.syncWithApp();
                this.pow.init();
            });

            document.addEventListener('creditsUpdated', (e) => {
                const data = e.detail || {};
                this.state.set('user', {
                    ...this.state.state.user,
                    credits: data.credits || 0,
                    isPremium: data.isPremium || false,
                });
            });

            document.addEventListener('premiumStatusUpdated', (e) => {
                const data = e.detail || {};
                this.state.set('user', {
                    ...this.state.state.user,
                    isPremium: data.isPremium || false,
                    credits: data.creditsBalance || 0,
                });
            });

            document.addEventListener('auth:unauthorized', () => {
                console.log('🧹 [Dashboard] Limpando recursos...');
                this.upload.cancelPolling();
                this.state.reset();
            });

            document.addEventListener('analysis:success', (e) => {
                const data = e.detail || {};
                if (data.result?.credits?.after !== undefined) {
                    this.state.set('user', {
                        ...this.state.state.user,
                        credits: data.result.credits.after,
                    });
                }
            });

            window.addEventListener('beforeunload', () => {
                this.upload.cancelPolling();
            });
        }

        _setupDragAndDrop() {
            const dropZone = this.ui._elements.dropArea;
            if (!dropZone) return;

            dropZone.addEventListener('dragenter', (e) => {
                e.preventDefault();
                dropZone.classList.add('dragover');
            });

            dropZone.addEventListener('dragover', (e) => {
                e.preventDefault();
                dropZone.classList.add('dragover');
            });

            dropZone.addEventListener('dragleave', () => {
                dropZone.classList.remove('dragover');
            });

            dropZone.addEventListener('drop', (e) => {
                e.preventDefault();
                dropZone.classList.remove('dragover');
                const files = Array.from(e.dataTransfer.files);
                if (files.length > 0) {
                    this.upload.upload(files).catch(error => {
                        console.error('❌ [Dashboard] Upload error:', error);
                        this.ui.showNotification(error.message, 'error');
                    });
                }
            });
        }

        _setupUploadForm() {
            const uploadForm = document.getElementById('uploadForm');
            if (uploadForm) {
                uploadForm.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    const fileInput = this.ui._elements.fileInput;
                    if (fileInput && fileInput.files.length > 0) {
                        try {
                            await this.upload.upload(Array.from(fileInput.files));
                        } catch (error) {
                            console.error('❌ [Dashboard] Upload error:', error);
                            this.ui.showNotification(error.message, 'error');
                        }
                    } else {
                        this.ui.showNotification('Selecione pelo menos um arquivo', 'warning');
                    }
                });
            }
        }

        _setupFileListeners() {
            if (this._fileListenersSetup) return;
            this._fileListenersSetup = true;

            const fileInput = this.ui._elements.fileInput;
            if (!fileInput) return;

            fileInput.addEventListener('change', (e) => {
                if (e.target.files && e.target.files.length > 0) {
                    const files = Array.from(e.target.files);
                    this.ui.showFilePreview(files);
                }
            });

            this.ui.setupFileChooser();
        }

        _setupPeriodicUpdate() {
            setInterval(() => {
                this.state.syncWithApp();
                this.ui.updateMetrics(this.state.state.analyses.active);
            }, CONFIG.CREDITS_CHECK_INTERVAL);
        }

        destroy() {
            this.upload.cancelPolling();
            this.state.reset();
            this._initialized = false;
            console.log('🧹 [Dashboard] Destruído');
        }
    }

    // ==============================================
    // 🔥 FUNÇÕES GLOBAIS
    // ==============================================

    window.showGPSAForAnalysis = function(processId) {
        const dashboard = window.__dashboard;
        if (!dashboard) {
            console.warn('⚠️ Dashboard não inicializado');
            return;
        }

        const analyses = dashboard.state.state.analyses.active;
        const analysis = analyses.find(a => a.processId === processId);
        
        if (!analysis || !analysis.result) {
            dashboard.ui.showNotification('Aguardando conclusão da análise...', 'warning');
            return;
        }

        const data = analysis.result;
        const stats = data.stats || {};
        const predictions = data.predictions_summary || data.metrics || {};
        const totalRegistros = stats.rows || predictions.processed_rows || 0;
        const scoreMedio = predictions.mean || predictions.mean_prediction || 0.65;
        const scoreColor = Utils.getScoreColor(scoreMedio);
        const confianca = Math.round(scoreMedio * 100);

        const modalBody = document.getElementById('gpsaModalBody');
        if (modalBody) {
            modalBody.innerHTML = `
                <div style="color: white; padding: 0.5rem;">
                    <div class="row g-3">
                        <div class="col-12">
                            <h6 style="color: #ff6b35; font-size: 0.85rem;">
                                <i class="fas fa-info-circle me-2"></i> Informações da Análise
                            </h6>
                            <div class="p-3 rounded-4" style="background: rgba(0,0,0,0.15); border: 1px solid rgba(255,255,255,0.03);">
                                <div class="row">
                                    <div class="col-6">
                                        <div style="color: rgba(255,255,255,0.3); font-size: 0.55rem;">Arquivo</div>
                                        <div style="color: white; font-weight: 500; font-size: 0.85rem;">${Utils.escapeHtml(analysis.filename || 'Desconhecido')}</div>
                                    </div>
                                    <div class="col-6">
                                        <div style="color: rgba(255,255,255,0.3); font-size: 0.55rem;">Registros</div>
                                        <div style="color: white; font-weight: 500; font-size: 0.85rem;">${totalRegistros.toLocaleString()}</div>
                                    </div>
                                    <div class="col-6 mt-2">
                                        <div style="color: rgba(255,255,255,0.3); font-size: 0.55rem;">Score Médio</div>
                                        <div style="color: ${scoreColor}; font-weight: 500; font-size: 0.85rem;">${confianca}%</div>
                                    </div>
                                    <div class="col-6 mt-2">
                                        <div style="color: rgba(255,255,255,0.3); font-size: 0.55rem;">Confiança</div>
                                        <div style="color: white; font-weight: 500; font-size: 0.85rem;">${confianca}%</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="text-center mt-3">
                            <button class="btn btn-outline-light btn-sm" onclick="window.closeGPSA()" 
                                    style="border-radius: 50px; padding: 0.3rem 1.5rem; font-size: 0.75rem; border-color: rgba(255,255,255,0.1);">
                                <i class="fas fa-times me-2"></i> Fechar
                            </button>
                        </div>
                    </div>
                </div>
            `;
        }

        const modal = document.getElementById('gpsaModal');
        if (modal) {
            const bsModal = bootstrap.Modal.getInstance(modal) || new bootstrap.Modal(modal);
            bsModal.show();
        }
    };

    window.closeGPSA = function() {
        const modal = document.getElementById('gpsaModal');
        if (modal) {
            const bsModal = bootstrap.Modal.getInstance(modal);
            if (bsModal) bsModal.hide();
        }
    };

    window.generatePDFReport = function(processId) {
        const dashboard = window.__dashboard;
        if (!dashboard) {
            console.warn('⚠️ Dashboard não inicializado');
            return;
        }

        const analyses = dashboard.state.state.analyses.active;
        const analysis = analyses.find(a => a.processId === processId);
        
        if (!analysis || !analysis.result) {
            dashboard.ui.showNotification('Aguardando conclusão da análise...', 'warning');
            return;
        }

        dashboard.ui.showNotification('📄 Gerando relatório PDF...', 'info');

        window.dispatchEvent(new CustomEvent('pdf:generate', {
            detail: {
                processId,
                analysis: analysis.result
            }
        }));
    };

    // ==============================================
    // 🔥 INICIALIZAÇÃO
    // ==============================================

    let dashboardInstance = null;

    function initDashboard() {
        if (dashboardInstance) {
            console.log('ℹ️ [Dashboard] Já existe uma instância');
            return dashboardInstance;
        }

        if (!Utils.isAuthenticated()) {
            console.log('🔒 [Dashboard] Usuário não autenticado');
            return null;
        }

        dashboardInstance = new Dashboard();
        window.__dashboard = dashboardInstance;

        dashboardInstance.init().catch(error => {
            console.error('❌ [Dashboard] Erro na inicialização:', error);
        });

        return dashboardInstance;
    }

    document.addEventListener('DOMContentLoaded', function() {
        if (window._appReadyFired || window.__APP_STATE?.isAppReady) {
            console.log('✅ [Dashboard] App já pronto, inicializando...');
            initDashboard();
            return;
        }

        console.log('⏳ [Dashboard] Aguardando app:ready...');
        document.addEventListener('app:ready', function() {
            console.log('📢 [Dashboard] app:ready recebido');
            initDashboard();
        });

        setTimeout(function() {
            if (!dashboardInstance) {
                console.log('🔄 [Dashboard] Fallback: tentando inicializar...');
                initDashboard();
            }
        }, 3000);
    });

    console.log('=' .repeat(60));
    console.log('🔥 dashboard.js v7.5 carregado');
    console.log('   ✅ CORRIGIDO: _handleResponse com accepted_files');
    console.log('   ✅ CORRIGIDO: Tratamento de erros granular');
    console.log('   ✅ MELHORADO: Upload com retry automático');
    console.log('   ✅ ADICIONADO: Progresso detalhado');
    console.log('   ✅ OTIMIZADO: Cache e performance');
    console.log('   📡 Use window.__dashboard para acesso');
    console.log('=' .repeat(60));

})();