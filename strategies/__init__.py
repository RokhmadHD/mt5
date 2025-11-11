import os
import importlib

# Secara otomatis menemukan dan mendaftarkan semua class strategi
STRATEGY_FACTORY = {}

for filename in os.listdir(os.path.dirname(__file__)):
    if filename.endswith(".py") and filename not in ["__init__.py", "strategy_base.py"]:
        module_name = filename[:-3]
        module = importlib.import_module(f"strategies.{module_name}")
        
        # Cari class di dalam file yang merupakan turunan dari Strategy
        for item_name in dir(module):
            item = getattr(module, item_name)
            if isinstance(item, type) and issubclass(item, module.Strategy) and item is not module.Strategy:
                # Gunakan nama class sebagai kunci (lowercase)
                strategy_key = item.__name__.lower()
                STRATEGY_FACTORY[strategy_key] = item
                print(f"Strategi ditemukan dan didaftarkan: {strategy_key}")