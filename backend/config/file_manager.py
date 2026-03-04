# backend/services/file_manager.py (versão simplificada)
import os
import json
import aiofiles
import uuid
from datetime import datetime
from typing import Dict, Any

class FileManager:
    # Diretórios base (relativos)
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    TEMP_DIR = os.path.join(BASE_DIR, "temp")
    OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
    MODELS_DIR = os.path.join(BASE_DIR, "models")
    DATA_DIR = os.path.join(BASE_DIR, "data")
    
    @classmethod
    async def ensure_directories(cls):
        """Cria diretórios necessários"""
        os.makedirs(cls.TEMP_DIR, exist_ok=True)
        os.makedirs(cls.OUTPUT_DIR, exist_ok=True)
        os.makedirs(cls.MODELS_DIR, exist_ok=True)
        os.makedirs(cls.DATA_DIR, exist_ok=True)
    
    @classmethod
    async def save_upload(cls, content: bytes, filename: str) -> str:
        """Salva arquivo enviado pelo usuário"""
        await cls.ensure_directories()
        filepath = os.path.join(cls.TEMP_DIR, f"{uuid.uuid4()}_{filename}")
        async with aiofiles.open(filepath, 'wb') as f:
            await f.write(content)
        return filepath
    
    @classmethod
    async def save_result(cls, content: str, process_id: str, extension: str = ".txt") -> str:
        """Salva resultado da análise"""
        await cls.ensure_directories()
        filename = f"resultado_{process_id}{extension}"
        filepath = os.path.join(cls.OUTPUT_DIR, filename)
        async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
            await f.write(content)
        return filepath
    
    @classmethod
    def get_result_path(cls, process_id: str) -> str:
        """Obtém caminho do resultado"""
        for ext in ['.txt', '.csv', '.json']:
            filepath = os.path.join(cls.OUTPUT_DIR, f"resultado_{process_id}{ext}")
            if os.path.exists(filepath):
                return filepath
        return ""
    
    @staticmethod
    async def save_json(data: Dict, filename: str) -> str:
        """Salva dados em JSON"""
        filepath = os.path.join(FileManager.DATA_DIR, filename)
        async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, indent=2, ensure_ascii=False))
        return filepath
    
    @staticmethod
    async def load_json(filename: str) -> Dict:
        """Carrega dados de JSON"""
        filepath = os.path.join(FileManager.DATA_DIR, filename)
        if os.path.exists(filepath):
            async with aiofiles.open(filepath, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content) if content else {}
        return {}