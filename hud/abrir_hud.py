"""Iniciador simples da HUD do Jarvis.

Abre o arquivo HTML no seu navegador padrao com visualizacao completa e interativa.
"""

import sys
import webbrowser
from pathlib import Path

BASE = Path(__file__).parent
HUD_HTML = BASE / "index.html"

def main():
    print("=" * 60)
    print("  J.A.R.V.I.S. - INICIANDO HUD HOLOGRÁFICA")
    print("=" * 60)
    print(f"  Abrindo: {HUD_HTML.resolve()}")
    print("  Dica: Você pode usar os botões no rodapé da HUD para testar os estados")
    print("        (Escutando, Pensando, Falando, Busca Web).")
    print("=" * 60)
    
    webbrowser.open(HUD_HTML.as_uri())

if __name__ == "__main__":
    main()
