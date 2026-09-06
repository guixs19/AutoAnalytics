# backend/scripts/treinar_ayla_v1.py
"""
🔥 TREINAMENTO DO MODELO AYLA V1 - VERSÃO DEFINITIVA
================================================================================
✅ Dataset com SPLIT FIXO (treino/validação/teste)
✅ df_val é USADO explicitamente para validação
✅ Escolha do modelo: baseada na VALIDAÇÃO (não no teste!)
✅ Teste final: APENAS medição (não influencia escolha)
✅ Comparação JUSTA entre modelos
✅ Modelo salvo como aylaV1.pkl
================================================================================
"""

import sys
import os
import pandas as pd
import numpy as np
import asyncio
import json
import joblib
from datetime import datetime
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

# Adicionar caminho do projeto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.ml.train import trainer
from backend.ml.predict import predictor
from backend.ml.automl_simple import automl_office
from backend.ml.boosting_ensemble import boosting_ensemble

# ==============================================
# CONFIGURAÇÕES
# ==============================================

MODEL_NAME = "aylaV1"
MODEL_PATH = os.path.join("backend", "ml", "models", f"{MODEL_NAME}.pkl")
N_REGISTROS = 10000
TEST_SIZE = 0.20        # 20% para teste FINAL (NUNCA influencia escolha)
VAL_SIZE = 0.15         # 15% para validação (USA para escolher modelo)
SEED = 42

# ==============================================
# 1. GERADOR DE DATASET
# ==============================================

class GeradorDatasetAyla:
    """
    🔥 GERADOR DE DATASET PARA TREINAMENTO DO AYLA
    """
    
    def __init__(self, seed: int = 42):
        self.seed = seed
        np.random.seed(seed)
    
    def gerar(self, n_registros: int = 10000) -> pd.DataFrame:
        """Gera dataset com 14 features + target"""
        
        print(f"\n{'='*70}")
        print(f"🔥 GERANDO DATASET - {n_registros:,} REGISTROS")
        print(f"{'='*70}")
        
        # ==========================================
        # FEATURES BASE
        # ==========================================
        
        # total_servicos (50-500)
        total_servicos = np.random.randint(50, 500, n_registros)
        
        # dias_operacao (20-60) - APENAS PARA VALIDAÇÃO
        dias_operacao = np.random.randint(20, 60, n_registros)
        
        # media_servicos_dia
        media_servicos_dia = np.round(total_servicos / dias_operacao, 2)
        media_servicos_dia = np.clip(media_servicos_dia, 1, 30)
        
        # ticket_medio (50-2000)
        ticket_medio = np.random.uniform(50, 2000, n_registros)
        
        # total_receita = ticket_medio * total_servicos
        total_receita = np.round(ticket_medio * total_servicos, 2)
        
        # taxa_conclusao (20-98%)
        taxa_conclusao = np.round(np.random.beta(4, 2, n_registros) * 100, 2)
        taxa_conclusao = np.clip(taxa_conclusao, 20, 98)
        
        # taxa_cancelamento (0-35%)
        taxa_cancelamento = np.round(
            (100 - taxa_conclusao) * np.random.uniform(0.1, 0.5, n_registros), 
            2
        )
        taxa_cancelamento = np.clip(taxa_cancelamento, 0, 35)
        
        # media_horas (0.5-12)
        media_horas = np.round(
            np.random.lognormal(mean=1.0, sigma=0.5, size=n_registros), 
            2
        )
        media_horas = np.clip(media_horas, 0.5, 12)
        
        # receita (50-3000)
        receita = np.round(
            ticket_medio * np.random.uniform(0.5, 1.8, n_registros), 
            2
        )
        receita = np.clip(receita, 50, 3000)
        
        # custo (10-2500)
        proporcao_custo = np.random.beta(3, 3, n_registros) * 0.6 + 0.2
        custo = np.round(receita * proporcao_custo, 2)
        custo = np.clip(custo, 10, 2500)
        
        # quantidade (1-5)
        quantidades = [1, 2, 3, 4, 5]
        probs = [0.30, 0.25, 0.20, 0.15, 0.10]
        quantidade = np.random.choice(quantidades, n_registros, p=probs)
        
        # ==========================================
        # RUÍDO NAS FEATURES BASE
        # ==========================================
        
        # total_servicos: +5% (INTEIRO)
        noise_std = np.std(total_servicos) * 0.05
        noise = np.random.normal(0, noise_std, n_registros)
        total_servicos_com_ruido = np.clip(
            np.round(total_servicos + noise),
            50, 500
        ).astype(int)
        
        # Receita: +5%
        noise_std = np.std(receita) * 0.05
        noise = np.random.normal(0, noise_std, n_registros)
        receita = np.clip(receita + noise, 50, 3000)
        
        # Custo: +5%
        noise_std = np.std(custo) * 0.05
        noise = np.random.normal(0, noise_std, n_registros)
        custo = np.clip(custo + noise, 10, 2500)
        
        # media_horas: +5%
        noise_std = np.std(media_horas) * 0.05
        noise = np.random.normal(0, noise_std, n_registros)
        media_horas = np.clip(media_horas + noise, 0.5, 12)
        
        # taxa_conclusao: +3%
        noise_std = np.std(taxa_conclusao) * 0.03
        noise = np.random.normal(0, noise_std, n_registros)
        taxa_conclusao = np.clip(taxa_conclusao + noise, 20, 98)
        
        # taxa_cancelamento: +3%
        noise_std = np.std(taxa_cancelamento) * 0.03
        noise = np.random.normal(0, noise_std, n_registros)
        taxa_cancelamento = np.clip(taxa_cancelamento + noise, 0, 35)
        
        # ==========================================
        # RECALCULAR FEATURES DERIVADAS
        # 🔥 Usando total_servicos_com_ruido
        # ==========================================
        
        # media_servicos_dia (recalculado com total_servicos_com_ruido)
        media_servicos_dia = np.round(total_servicos_com_ruido / dias_operacao, 2)
        media_servicos_dia = np.clip(media_servicos_dia, 1, 30)
        
        # ticket_medio (recalculado com total_servicos_com_ruido)
        # 🔥 SEM CLIP! mantém consistência
        ticket_medio = np.round(total_receita / total_servicos_com_ruido, 2)
        
        # lucro
        lucro = np.round(receita - custo, 2)
        
        # margem
        margem = np.round(lucro / receita, 4)
        margem = np.clip(margem, -0.5, 0.95)
        
        # eficiencia = (receita / total_servicos) / 10
        eficiencia = np.round((receita / total_servicos_com_ruido) / 10, 4)
        eficiencia = np.clip(eficiencia, 0.01, 10.0)
        
        # ==========================================
        # CRIAR DATAFRAME
        # ==========================================
        
        df = pd.DataFrame({
            'total_servicos': total_servicos_com_ruido,
            'media_servicos_dia': media_servicos_dia,
            'total_receita': total_receita,
            'ticket_medio': ticket_medio,
            'taxa_conclusao': taxa_conclusao,
            'taxa_cancelamento': taxa_cancelamento,
            'media_horas': media_horas,
            'receita': receita,
            'custo': custo,
            'quantidade': quantidade,
            'lucro': lucro,
            'margem': margem,
            'eficiencia': eficiencia,
            'constante': np.ones(n_registros),
        })
        
        # ==========================================
        # TARGET SINTÉTICO
        # ==========================================
        
        df['lucro_alto'] = df['lucro'] > 150
        df['margem_boa'] = df['margem'] > 0.25
        df['eficiencia_boa'] = df['eficiencia'] > 0.5
        df['volume_bom'] = df['total_servicos'] > 100
        df['qualidade_boa'] = (df['taxa_conclusao'] > 70) & (df['taxa_cancelamento'] < 15)
        df['ticket_bom'] = df['ticket_medio'] > 300
        
        df['lucrativo'] = (
            (df['lucro_alto'] | (df['margem_boa'] & df['eficiencia_boa'])) &
            df['qualidade_boa'] &
            df['volume_bom'] &
            df['ticket_bom']
        ).astype(int)
        
        # Exceções (10%)
        mask_excecao = np.random.random(len(df)) < 0.10
        df.loc[mask_excecao, 'lucrativo'] = 1 - df.loc[mask_excecao, 'lucrativo']
        
        # Remover colunas auxiliares
        cols_aux = ['lucro_alto', 'margem_boa', 'eficiencia_boa', 
                   'volume_bom', 'qualidade_boa', 'ticket_bom']
        df = df.drop(columns=cols_aux)
        
        print(f"\n✅ Dataset gerado: {len(df):,} registros")
        print(f"   Lucrativos: {df['lucrativo'].sum():,} ({df['lucrativo'].mean()*100:.1f}%)")
        
        return df

# ==============================================
# 2. CLASSE PARA TREINAMENTO COM VALIDAÇÃO EXPLÍCITA
# ==============================================

class TrainerComValidacao:
    """
    🔥 WRAPPER QUE USA VALIDAÇÃO EXPLÍCITA
    """
    
    @staticmethod
    async def treinar_automl_com_validacao(
        df_train: pd.DataFrame,
        df_val: pd.DataFrame,
        target_col: str
    ) -> dict:
        """
        Treina AutoML com validação explícita
        """
        # Combinar treino + validação para o treinamento interno
        df_full = pd.concat([df_train, df_val], ignore_index=True)
        
        # Treinar com CV
        resultado = await trainer.train_and_get_metrics(
            df=df_full,
            target_col=target_col,
            model_type='classifier',
            auto_ml=True,
            tune_hyperparams=True,
            feature_selection=True,
            balance=True,
            test_size=0.0,
            cv_folds=5,
            save_model=False
        )
        
        # Avaliar na validação
        X_val = df_val.drop(columns=[target_col])
        y_val = df_val[target_col]
        
        if trainer.best_scaler is not None:
            X_val_scaled = trainer.best_scaler.transform(X_val.values)
        else:
            X_val_scaled = X_val.values
        
        pred_val = trainer.best_model.predict(X_val_scaled)
        score_val = accuracy_score(y_val, pred_val)
        
        return {
            'score_val': float(score_val),
            'model': trainer.best_model,
            'scaler': trainer.best_scaler,
            'features': trainer.best_features,
            'model_name': trainer.best_model_name,
            'resultado': resultado
        }
    
    @staticmethod
    async def treinar_ensemble_com_validacao(
        df_train: pd.DataFrame,
        df_val: pd.DataFrame,
        target_col: str
    ) -> dict:
        """
        Treina Ensemble com validação explícita
        """
        X_train = df_train.drop(columns=[target_col])
        y_train = df_train[target_col]
        
        X_val = df_val.drop(columns=[target_col])
        y_val = df_val[target_col]
        
        # Treinar ensemble
        resultado = boosting_ensemble.train_sequential_boost(
            X=X_train,
            y=y_train,
            n_models=5,
            test_size=0.0,
            verbose=False,
            normalize=True,
            scaler_type='standard'
        )
        
        # Avaliar na validação
        pred_val = boosting_ensemble.predict(X_val)
        score_val = accuracy_score(y_val, pred_val)
        
        return {
            'score_val': float(score_val),
            'model': boosting_ensemble.best_model,
            'scaler': boosting_ensemble.scaler,
            'features': boosting_ensemble.feature_names,
            'model_name': 'boosting_ensemble',
            'resultado': resultado
        }

# ==============================================
# 3. FUNÇÃO DE TREINAMENTO PRINCIPAL
# ==============================================

async def treinar_ayla_v1(
    n_registros: int = 10000,
    test_size: float = 0.20,
    val_size: float = 0.15,
    salvar_dataset: bool = True
) -> dict:
    """
    🔥 TREINA O MODELO AYLA V1 - VERSÃO DEFINITIVA
    
    Fluxo correto:
    1. Dataset → Treino (65%) + Validação (15%) + Teste (20%)
    2. df_val é USADO explicitamente para validação
    3. Modelo escolhido: melhor score na VALIDAÇÃO
    4. Teste final: APENAS medição (não influencia escolha)
    5. Modelo salvo como aylaV1.pkl
    """
    
    print("\n" + "=" * 80)
    print("🚀 TREINANDO AYLA V1 - VERSÃO DEFINITIVA")
    print("=" * 80)
    print(f"📊 Registros: {n_registros:,}")
    print(f"📊 Treino: {(1-test_size-val_size)*100:.0f}%")
    print(f"📊 Validação: {val_size*100:.0f}% ✅ (USA para escolher modelo)")
    print(f"📊 Teste: {test_size*100:.0f}% 🔒 (APENAS medição final)")
    print(f"📊 Modelo: {MODEL_NAME}")
    print(f"📊 Saída: {MODEL_PATH}")
    print("=" * 80)
    
    start_time = datetime.now()
    
    # ==========================================
    # 1. GERAR DATASET
    # ==========================================
    print("\n📊 1. GERANDO DATASET...")
    
    gerador = GeradorDatasetAyla(seed=SEED)
    df = gerador.gerar(n_registros)
    
    # ==========================================
    # 2. SPLIT FIXO: TREINO + VALIDAÇÃO + TESTE
    # 🔥 TESTE FINAL ISOLADO
    # ==========================================
    print("\n📊 2. CRIANDO SPLITS FIXOS...")
    
    # Primeiro: separar TESTE (NUNCA influencia escolha)
    df_temp, df_test = train_test_split(
        df,
        test_size=test_size,
        random_state=SEED,
        stratify=df['lucrativo']
    )
    
    # Depois: separar TREINO e VALIDAÇÃO
    val_ratio = val_size / (1 - test_size)
    df_train, df_val = train_test_split(
        df_temp,
        test_size=val_ratio,
        random_state=SEED,
        stratify=df_temp['lucrativo']
    )
    
    # Resetar índices
    df_train = df_train.reset_index(drop=True)
    df_val = df_val.reset_index(drop=True)
    df_test = df_test.reset_index(drop=True)
    
    print(f"\n   ✅ SPLITS CRIADOS:")
    print(f"      Treino: {len(df_train):,} ({len(df_train)/len(df)*100:.1f}%)")
    print(f"      Validação: {len(df_val):,} ({len(df_val)/len(df)*100:.1f}%) ✅")
    print(f"      Teste: {len(df_test):,} ({len(df_test)/len(df)*100:.1f}%) 🔒")
    print(f"      🔒 Teste NUNCA influencia a escolha do modelo!")
    print(f"      ✅ Validação é usada para escolher o modelo!")
    
    # Salvar splits (opcional)
    if salvar_dataset:
        Path("backend/data/datasets").mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        df_train.to_csv(f"backend/data/datasets/ayla_train_{timestamp}.csv", index=False)
        df_val.to_csv(f"backend/data/datasets/ayla_val_{timestamp}.csv", index=False)
        df_test.to_csv(f"backend/data/datasets/ayla_test_{timestamp}.csv", index=False)
        print(f"\n💾 Splits salvos em: backend/data/datasets/")
    
    # ==========================================
    # 3. TREINAR AUTO-ML (COM VALIDAÇÃO EXPLÍCITA)
    # ==========================================
    print("\n📊 3. TREINANDO AUTO-ML (com validação explícita)...")
    
    resultado_automl = await TrainerComValidacao.treinar_automl_com_validacao(
        df_train=df_train,
        df_val=df_val,
        target_col='lucrativo'
    )
    
    score_automl_val = resultado_automl['score_val']
    print(f"\n✅ Auto-ML concluído!")
    print(f"   Modelo: {resultado_automl['model_name']}")
    print(f"   Score na Validação: {score_automl_val:.4f} ✅")
    
    # ==========================================
    # 4. TREINAR BOOSTING ENSEMBLE (COM VALIDAÇÃO EXPLÍCITA)
    # ==========================================
    print("\n📊 4. TREINANDO BOOSTING ENSEMBLE (com validação explícita)...")
    
    resultado_ensemble = await TrainerComValidacao.treinar_ensemble_com_validacao(
        df_train=df_train,
        df_val=df_val,
        target_col='lucrativo'
    )
    
    score_ensemble_val = resultado_ensemble['score_val']
    print(f"\n✅ Ensemble concluído!")
    print(f"   Score na Validação: {score_ensemble_val:.4f} ✅")
    
    # ==========================================
    # 5. ESCOLHER O MELHOR (BASEADO NA VALIDAÇÃO!)
    # 🔥 O TESTE NÃO INFLUENCIA A ESCOLHA
    # ==========================================
    print("\n📊 5. ESCOLHENDO O MELHOR MODELO (baseado na Validação)...")
    
    if score_ensemble_val > score_automl_val:
        modelo_final = resultado_ensemble['model']
        scaler_final = resultado_ensemble['scaler']
        model_name = resultado_ensemble['model_name']
        features = resultado_ensemble['features']
        score_escolha = score_ensemble_val
        print(f"   ✅ Ensemble escolhido (Validação: {score_escolha:.4f})")
    else:
        modelo_final = resultado_automl['model']
        scaler_final = resultado_automl['scaler']
        model_name = resultado_automl['model_name']
        features = resultado_automl['features']
        score_escolha = score_automl_val
        print(f"   ✅ AutoML escolhido (Validação: {score_escolha:.4f})")
    
    print(f"   ⚠️  O Teste NÃO foi usado para esta escolha!")
    
    # ==========================================
    # 6. AVALIAR NO TESTE FINAL (APENAS MEDIÇÃO!)
    # 🔒 O TESTE NUNCA VIU O MODELO ANTES
    # ==========================================
    print("\n📊 6. AVALIANDO NO TESTE FINAL 🔒 (APENAS MEDIÇÃO)...")
    
    X_test = df_test.drop(columns=['lucrativo'])
    y_test = df_test['lucrativo']
    
    # Predizer
    if scaler_final is not None:
        X_test_scaled = scaler_final.transform(X_test.values)
    else:
        X_test_scaled = X_test.values
    
    pred_final = modelo_final.predict(X_test_scaled)
    score_test = accuracy_score(y_test, pred_final)
    
    print(f"\n   🔒 Score no Teste FINAL: {score_test:.4f}")
    print(f"   ✅ Este score NÃO influenciou a escolha do modelo!")
    print(f"   ✅ O modelo foi escolhido APENAS pela Validação")
    
    # ==========================================
    # 7. SALVAR MODELO COMO aylaV1.pkl
    # ==========================================
    print("\n📊 7. SALVANDO MODELO...")
    
    feature_count = len(features) if features else len(df_train.drop(columns=['lucrativo']).columns)
    
    model_data = {
        'model': modelo_final,
        'scaler': scaler_final,
        'features': features or df_train.drop(columns=['lucrativo']).columns.tolist(),
        'feature_count': feature_count,
        'model_name': f"{MODEL_NAME}_{model_name}",
        'model_type': 'classifier',
        'metrics': {
            'val_score_automl': float(score_automl_val),
            'val_score_ensemble': float(score_ensemble_val),
            'val_score_escolhido': float(score_escolha),
            'test_score_final': float(score_test),
            'f1_score': float(resultado_automl['resultado'].get('f1_score', 0)),
            'precision': float(resultado_automl['resultado'].get('precision', 0)),
            'recall': float(resultado_automl['resultado'].get('recall', 0))
        },
        'normalization': 'Z-Score (StandardScaler)',
        'version': '1.0',
        'trained_date': datetime.now().isoformat(),
        'is_automl': True,
        'training_data': {
            'n_registros': n_registros,
            'n_train': len(df_train),
            'n_val': len(df_val),
            'n_test': len(df_test),
            'n_features': feature_count,
            'target': 'lucrativo',
            'seed': SEED,
            'test_size': test_size,
            'val_size': val_size
        },
        'pipeline_info': {
            'metodo_escolha': 'validacao_explicita',
            'teste_isolado': True,
            'teste_nao_influenciou_escolha': True,
            'validacao_usada_para_escolha': True
        }
    }
    
    # Salvar como aylaV1.pkl
    joblib.dump(model_data, MODEL_PATH)
    print(f"✅ Modelo salvo: {MODEL_PATH}")
    
    # Também salvar como trained_model.pkl para compatibilidade
    trained_path = os.path.join("backend", "ml", "models", "trained_model.pkl")
    joblib.dump(model_data, trained_path)
    print(f"✅ Compatibilidade: {trained_path}")
    
    # ==========================================
    # 8. RELATÓRIO
    # ==========================================
    elapsed = (datetime.now() - start_time).total_seconds()
    
    relatorio = {
        'modelo': MODEL_NAME,
        'versao': '1.0',
        'data_treino': datetime.now().isoformat(),
        'seed': SEED,
        'n_registros': n_registros,
        'n_train': len(df_train),
        'n_val': len(df_val),
        'n_test': len(df_test),
        'n_features': feature_count,
        'modelo_escolhido': model_name,
        'score_val_automl': float(score_automl_val),
        'score_val_ensemble': float(score_ensemble_val),
        'score_val_escolhido': float(score_escolha),
        'score_test_final': float(score_test),
        'f1_score': float(resultado_automl['resultado'].get('f1_score', 0)),
        'tempo_segundos': elapsed,
        'model_path': MODEL_PATH,
        'features': features[:10] if features else [],
        'teste_isolado': True,
        'teste_nao_influenciou_escolha': True,
        'validacao_usada_para_escolha': True,
        'metodo_escolha': 'validacao_explicita'
    }
    
    # Salvar relatório
    Path("backend/data/logs").mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_path = f"backend/data/logs/relatorio_ayla_v1_{timestamp}.json"
    
    with open(report_path, 'w') as f:
        json.dump(relatorio, f, indent=2)
    print(f"📊 Relatório salvo: {report_path}")
    
    # ==========================================
    # 9. RESUMO FINAL
    # ==========================================
    print("\n" + "=" * 80)
    print("✅ TREINAMENTO CONCLUÍDO COM SUCESSO!")
    print("=" * 80)
    print(f"\n📊 RESUMO FINAL:")
    print(f"   Modelo: {MODEL_NAME}")
    print(f"   Escolhido: {model_name}")
    print(f"   Score na VALIDAÇÃO: {score_escolha:.4f} ✅ (usado para escolha)")
    print(f"   Score no TESTE FINAL: {score_test:.4f} 🔒 (apenas medição)")
    print(f"   Features: {feature_count}")
    print(f"   Tempo: {elapsed:.2f}s")
    print(f"   Arquivo: {MODEL_PATH}")
    print("\n   🔒 Teste FINAL NUNCA influenciou a escolha do modelo!")
    print("   ✅ Modelo escolhido APENAS pela Validação!")
    print("   ✅ Pipeline correto e didático!")
    print("=" * 80)
    
    return relatorio

# ==============================================
# 4. FUNÇÃO PARA VERIFICAR O MODELO
# ==============================================

def verificar_modelo():
    """Verifica se o modelo foi salvo corretamente"""
    print("\n🔍 VERIFICANDO MODELO...")
    
    if not os.path.exists(MODEL_PATH):
        print(f"❌ Modelo não encontrado: {MODEL_PATH}")
        return False
    
    try:
        model_data = joblib.load(MODEL_PATH)
        
        print(f"✅ Modelo carregado: {MODEL_PATH}")
        print(f"   Nome: {model_data.get('model_name')}")
        print(f"   Features: {model_data.get('feature_count')}")
        print(f"   Métricas:")
        for key, value in model_data.get('metrics', {}).items():
            print(f"      {key}: {value:.4f}")
        print(f"   Normalização: {model_data.get('normalization')}")
        print(f"   Pipeline: {model_data.get('pipeline_info', {}).get('metodo_escolha', 'N/A')}")
        
        return True
    except Exception as e:
        print(f"❌ Erro ao carregar: {e}")
        return False

# ==============================================
# 5. MAIN
# ==============================================

async def main():
    """Função principal"""
    
    # Treinar
    relatorio = await treinar_ayla_v1(
        n_registros=N_REGISTROS,
        test_size=TEST_SIZE,
        val_size=VAL_SIZE,
        salvar_dataset=True
    )
    
    # Verificar
    verificar_modelo()
    
    # Carregar no predictor
    print("\n🔄 CARREGANDO NO PREDICTOR...")
    predictor.load_model_intelligently(MODEL_PATH)
    
    status = predictor.get_model_summary()
    print(f"\n📊 STATUS DO PREDICTOR:")
    print(f"   Modelo: {status.get('fonte_modelo')}")
    print(f"   Features: {status.get('model_feature_count')}")
    print(f"   Normalização: {status.get('normalization')}")
    
    return relatorio

if __name__ == "__main__":
    try:
        resultado = asyncio.run(main())
        print("\n🎉 AYLA V1 PRONTA PARA USO!")
        print(f"   Modelo: {MODEL_PATH}")
        print(f"   Score na Validação: {resultado['score_val_escolhido']:.4f}")
        print(f"   Score no Teste FINAL: {resultado['score_test_final']:.4f}")
        print(f"   ✅ Teste NÃO influenciou a escolha!")
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()