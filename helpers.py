import os
import logging

def get_env_var(name, default, type_func=str):
    value = os.getenv(name, default)
    try:
        if type_func == bool:
            return value.lower() in ['true', '1', 't', 'y', 'yes']
        return type_func(value)
    except (ValueError, TypeError):
        logging.warning(f"Variabel .env '{name}' tidak valid. Menggunakan default: {default}")
        return default

# Variabel global yang mungkin dibutuhkan oleh banyak strategi
AGGRESSION_LEVEL = get_env_var('AGGRESSION_LEVEL', 'medium').lower()