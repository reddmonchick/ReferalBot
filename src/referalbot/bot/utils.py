import re
import random

def generate_promo_code(username: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", username)