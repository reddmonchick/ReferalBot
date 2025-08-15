import re
import random
import uuid

def generate_promo_code(username: str) -> str:
    ref_code =  re.sub(r"[^a-zA-Z0-9]", "", username) or str(uuid.uuid4())[:8]
    print(ref_code)
    return ref_code