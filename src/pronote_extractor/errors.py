class ExtractionError(Exception):
    """Entrée inexploitable ; `code` est renvoyé tel quel par l'API (spec §8)."""

    def __init__(self, code, detail=""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail
