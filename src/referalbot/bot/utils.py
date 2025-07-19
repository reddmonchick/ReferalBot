import re
import random

def generate_promo_code(username: str) -> str:
    safe_username = re.sub(r"[^a-zA-Z0-9_-]", "", username)
    return f"{safe_username}{random.randint(100, 999)}"