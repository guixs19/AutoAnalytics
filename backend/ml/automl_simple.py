# backend/ml/automl_simple.py - VERSÃO COM INTEGRAÇÃO AUTOMÁTICA
"""
AutoML simplificado com integração automática ao predictor
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Tuple, List
import os
import joblib
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression, RidgeClassifier
from sklearn.model_selection import cross_val_score, KFold, train_test_split
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score, f1_score

# Importar predictor para integração
from ml.predict import predictor


class AutoMLOffice:
    """
    AutoML para dados de oficina com integração automática
    """
    
    def __init__(self):
        self.models_dir = os.path.join("backend", "ml", "models", "automl")
        os.makedirs(self.models_dir, exist_ok=True)
        
        self.best_model = None
        self.best_pipeline = None
        self.ranking = None
        self.scaler = None
        self.integrated = False
        
        print("✅ AutoMLOffice inicializado (com integração automática)")
    
    def comparar_modelos_classificacao(
        self,
        df: pd.DataFrame,
        target_col: str,
        n_folds: int = 10,
        test_size: float = 0.2,
        verbose: bool = True,
        integrar_apos_treino: bool = True  # NOVO: integrar automaticamente
    ) -> pd.DataFrame:
        """
        Compara modelos e integra automaticamente com o predictor
        """
        print(f"\n{'='*60}")
        print("🔬 COMPARAÇÃO DE MODELOS - OFICINA")
        print(f"{'='*60}")
        print(f"📊 Dados: {df.shape[0]} linhas, {df.shape[1]} colunas")
        print(f"🎯 Target: {target_col}")
        print(f"🔢 K-Fold: {n_folds} folds")
        print(f"{'='*60}\n")
        
        # Preparar dados
        X = df.drop(columns=[target_col])
        y = df[target_col]
        
        X = X.select_dtypes(include=[np.number])
        
        if X.empty:
            print("❌ ERRO: Nenhuma coluna numérica encontrada!")
            return pd.DataFrame()
        
        # Dividir em treino e teste
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=test_size, random_state=42, stratify=y
            )
        except:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=test_size, random_state=42
            )
        
        print(f"📈 Treino: {X_train.shape[0]} amostras")
        print(f"📉 Teste: {X_test.shape[0]} amostras")
        print(f"🎯 Classes: {np.unique(y)}")
        
        # Modelos para comparar
        modelos = {
            '🌳 RANDOM FOREST (100 ÁRVORES)': RandomForestClassifier(
                n_estimators=100, random_state=42, n_jobs=-1
            ),
            '🌲 RANDOM FOREST (50 ÁRVORES)': RandomForestClassifier(
                n_estimators=50, random_state=42, n_jobs=-1
            ),
            '📊 REGRESSÃO LOGÍSTICA': LogisticRegression(
                random_state=42, max_iter=1000, n_jobs=-1
            ),
            '📈 RIDGE CLASSIFIER': RidgeClassifier(
                random_state=42, max_iter=1000
            )
        }
        
        resultados = []
        kfold = KFold(n_splits=n_folds, shuffle=True, random_state=42)
        
        print("\n⏳ Treinando e validando modelos...\n")
        
        for nome, modelo in modelos.items():
            pipeline = Pipeline([
                ('scaler', StandardScaler()),
                ('classifier', modelo)
            ])
            
            cv_scores = cross_val_score(
                pipeline, X_train, y_train,
                cv=kfold, scoring='accuracy', n_jobs=-1
            )
            
            pipeline.fit(X_train, y_train)
            
            y_pred = pipeline.predict(X_test)
            test_acc = accuracy_score(y_test, y_pred)
            test_f1 = f1_score(y_test, y_pred, average='weighted', zero_division=0)
            
            resultados.append({
                'Modelo': nome.replace('🌳 ', '').replace('🌲 ', '').replace('📊 ', '').replace('📈 ', ''),
                'Acurácia (CV)': cv_scores.mean(),
                'Desvio (CV)': cv_scores.std(),
                'Acurácia (Teste)': test_acc,
                'F1-Score': test_f1,
                'Pipeline': pipeline
            })
            
            if verbose:
                print(f"{nome[:35]:<35} CV: {cv_scores.mean():.4f} (±{cv_scores.std():.4f}) | Teste: {test_acc:.4f}")
        
        # Criar ranking
        ranking_df = pd.DataFrame([
            {k: v for k, v in r.items() if k != 'Pipeline'}
            for r in resultados
        ])
        ranking_df = ranking_df.sort_values('Acurácia (CV)', ascending=False)
        ranking_df['Rank'] = range(1, len(ranking_df) + 1)
        
        print(f"\n{'='*60}")
        print("📊 RANKING FINAL:")
        print(ranking_df[['Rank', 'Modelo', 'Acurácia (CV)', 'F1-Score']].to_string(index=False))
        
        # Melhor modelo
        melhor = max(resultados, key=lambda x: x['Acurácia (CV)'])
        self.best_pipeline = melhor['Pipeline']
        self.best_model = melhor['Pipeline'].named_steps['classifier']
        self.scaler = melhor['Pipeline'].named_steps['scaler']
        self.ranking = ranking_df
        
        print(f"\n✅ MELHOR MODELO: {melhor['Modelo']}")
        print(f"   Acurácia CV: {melhor['Acurácia (CV)']:.2%}")
        print(f"   Acurácia Teste: {melhor['Acurácia (Teste)']:.2%}")
        
        # Salvar resultados
        self._salvar_resultados(ranking_df, melhor)
        
        # NOVO: Integrar automaticamente se solicitado
        if integrar_apos_treino:
            print("\n🔄 Integrando automaticamente com o predictor...")
            self.integrar_com_predictor()
        
        return ranking_df
    
    def analisar_votacao_100_arvores(self, df: pd.DataFrame, target_col: str) -> Dict[str, Any]:
        """Análise detalhada da votação das 100 árvores"""
        print(f"\n{'='*60}")
        print("🔍 ANÁLISE DA VOTAÇÃO DAS 100 ÁRVORES")
        print(f"{'='*60}")
        
        X = df.drop(columns=[target_col])
        y = df[target_col]
        X = X.select_dtypes(include=[np.number])
        
        if X.empty:
            return {"erro": "Sem dados numéricos"}
        
        rf = RandomForestClassifier(
            n_estimators=100,
            random_state=42,
            n_jobs=-1,
            oob_score=True
        )
        
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        rf.fit(X_scaled, y)
        
        profundidades = [tree.tree_.max_depth for tree in rf.estimators_]
        
        print(f"\n📊 ESTATÍSTICAS DA FLORESTA:")
        print(f"   🌳 Total de árvores: {len(rf.estimators_)}")
        print(f"   📏 Profundidade média: {np.mean(profundidades):.1f}")
        print(f"   🎯 Acurácia OOB: {rf.oob_score_:.2%}")
        
        importancias = dict(zip(X.columns, rf.feature_importances_))
        importancias = dict(sorted(importancias.items(), key=lambda x: x[1], reverse=True))
        
        print(f"\n🔝 TOP 5 FEATURES:")
        for feat, imp in list(importancias.items())[:5]:
            print(f"   • {feat}: {imp:.3f}")
        
        votacoes = []
        n_amostras = min(3, len(X))
        
        for i in range(n_amostras):
            votos = np.array([tree.predict(X_scaled[i:i+1])[0] for tree in rf.estimators_])
            classe_0 = np.sum(votos == 0)
            classe_1 = np.sum(votos == 1)
            decisao = 0 if classe_0 > classe_1 else 1
            confianca = max(classe_0, classe_1) / 100
            
            print(f"\n   Amostra {i+1}:")
            print(f"      Votos: {classe_0} x {classe_1}")
            print(f"      Decisão: {decisao} (confiança: {confianca:.1%})")
            
            votacoes.append({
                'amostra': i+1,
                'votos_classe_0': int(classe_0),
                'votos_classe_1': int(classe_1),
                'decisao': int(decisao),
                'confianca': float(confianca),
                'real': int(y.iloc[i])
            })
        
        return {
            'total_arvores': len(rf.estimators_),
            'profundidade_media': float(np.mean(profundidades)),
            'acuracia_oob': float(rf.oob_score_),
            'features_importantes': importancias,
            'exemplos_votacao': votacoes
        }
    
    def _salvar_resultados(self, ranking_df: pd.DataFrame, melhor_modelo: Dict):
        """Salva resultados do experimento"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        ranking_path = os.path.join(self.models_dir, f"ranking_{timestamp}.csv")
        ranking_df.to_csv(ranking_path, index=False)
        
        model_path = os.path.join(self.models_dir, f"melhor_modelo_{timestamp}.pkl")
        
        try:
            features = list(melhor_modelo['Pipeline'].feature_names_in_)
        except:
            features = []
        
        joblib.dump({
            'pipeline': melhor_modelo['Pipeline'],
            'metricas': {
                'acuracia_cv': float(melhor_modelo['Acurácia (CV)']),
                'acuracia_teste': float(melhor_modelo['Acurácia (Teste)']),
                'f1_score': float(melhor_modelo['F1-Score'])
            },
            'features': features
        }, model_path)
        
        print(f"\n💾 Resultados salvos em:")
        print(f"   📁 {ranking_path}")
        print(f"   📁 {model_path}")
    
    def integrar_com_predictor(self):
        """
        Integra o melhor modelo com o predictor existente
        """
        if self.best_pipeline is None:
            print("❌ Nenhum modelo treinado para integrar")
            return False
        
        try:
            # Extrair componentes
            scaler = self.best_pipeline.named_steps['scaler']
            model = self.best_pipeline.named_steps['classifier']
            
            # Salvar no formato do predictor
            model_data = {
                'classifier': model,
                'scaler': scaler,
                'model_type': type(model).__name__,
                'trained_date': datetime.now().isoformat(),
                'is_automl': True,
                'ranking': self.ranking.to_dict() if self.ranking is not None else None
            }
            
            model_path = os.path.join("backend", "ml", "models", "office_model.pkl")
            joblib.dump(model_data, model_path)
            
            print(f"\n✅ Modelo integrado com predictor em: {model_path}")
            self.integrated = True
            
            # Forçar recarregamento do predictor
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(predictor.load_or_train_models())
                else:
                    loop.run_until_complete(predictor.load_or_train_models())
                print("✅ Predictor recarregado com sucesso!")
            except Exception as e:
                print(f"⚠️ Predictor será recarregado na próxima chamada: {e}")
            
            return True
            
        except Exception as e:
            print(f"❌ Erro na integração: {e}")
            return False


# Instância global
automl_office = AutoMLOffice()

print("\n✅ AutoMLOffice pronto com integração automática!")
print("   Agora ao treinar um modelo, ele já integra com o predictor!")
print("   Exemplo: automl_office.comparar_modelos_classificacao(df, 'target')")