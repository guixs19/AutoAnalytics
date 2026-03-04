# backend/data_processor.py
import pandas as pd
import numpy as np
from typing import Dict, Any
from datetime import datetime
import os

class DataPreprocessor:
    """
    Classe simples para processar arquivos de dados
    """
    
    def __init__(self):
        print("✅ DataPreprocessor inicializado")
    
    async def process_file(self, file_path: str) -> Dict[str, Any]:
        """
        Processa arquivo CSV/Excel e retorna dados
        """
        try:
            print(f"📊 Processando arquivo: {file_path}")
            
            # Verificar se arquivo existe
            if not os.path.exists(file_path):
                return {
                    "status": "error",
                    "message": "Arquivo não encontrado",
                    "metadata": {}
                }
            
            # Carregar dados
            if file_path.endswith('.csv'):
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path)
            
            # Informações básicas
            total_rows = len(df)
            total_cols = len(df.columns)
            
            # Separar colunas numéricas
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            df_numeric = df[numeric_cols].copy() if numeric_cols else pd.DataFrame()
            
            # Preencher valores nulos
            for col in df_numeric.columns:
                if df_numeric[col].isnull().any():
                    df_numeric[col].fillna(df_numeric[col].mean(), inplace=True)
            
            # Metadados
            metadata = {
                "original": {
                    "linhas": total_rows,
                    "colunas": total_cols
                },
                "processamento": {
                    "colunas_numericas": numeric_cols,
                    "total_numericas": len(numeric_cols)
                },
                "diagnostico": {
                    "status": "success",
                    "mensagem": f"Processado: {total_rows} registros",
                    "timestamp": datetime.now().isoformat()
                }
            }
            
            return {
                "status": "success",
                "dataframe": df,
                "dataframe_numeric": df_numeric,
                "metadata": metadata
            }
            
        except Exception as e:
            print(f"❌ Erro: {e}")
            return {
                "status": "error",
                "message": str(e),
                "metadata": {}
            }