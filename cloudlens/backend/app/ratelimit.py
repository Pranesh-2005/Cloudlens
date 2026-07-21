"""Shared slowapi Limiter instance (5/min auth, 20/min /chat, 60/min elsewhere)."""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
