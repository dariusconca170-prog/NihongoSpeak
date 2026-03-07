import sys

def setup_console():
    """No-op for compatibility."""
    pass

def safe_print(message: str):
    """Print a message safely, handling encoding errors manually."""
    try:
        # Try printing directly first
        print(message)
    except UnicodeEncodeError:
        try:
            # Fallback to current stdout encoding with replacement
            enc = sys.stdout.encoding or "utf-8"
            print(message.encode(enc, errors="replace").decode(enc))
        except Exception:
            try:
                # Last resort: ASCII
                print(message.encode("ascii", errors="replace").decode("ascii"))
            except Exception:
                pass
