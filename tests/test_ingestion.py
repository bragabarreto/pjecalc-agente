# tests/test_ingestion.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.ingestion import normalizar_valor, normalizar_data, segmentar_sentenca, normalizar_texto


def test_normalizar_valor():
    assert normalizar_valor("R$ 12.345,67") == 12345.67
    assert normalizar_valor("1.000,00") == 1000.00
    assert normalizar_valor("500,00") == 500.00


def test_normalizar_data_numerica():
    assert normalizar_data("01/03/2018") == "01/03/2018"
    assert normalizar_data("1-3-2018") == "01/03/2018"


def test_normalizar_data_extenso():
    resultado = normalizar_data("1º de março de 2018")
    assert resultado == "01/03/2018", f"Esperado 01/03/2018, obtido {resultado}"


def test_segmentar_sentenca():
    texto = (
        "RELATÓRIO\nAs partes apresentaram alegações...\n\n"
        "FUNDAMENTAÇÃO\nAnalisando os fatos...\n\n"
        "Pelo exposto, CONDENO o reclamado ao pagamento de horas extras."
    )
    blocos = segmentar_sentenca(texto)
    assert "dispositivo" in blocos
    assert "condeno" in blocos["dispositivo"].lower()


def test_normalizar_texto_hifenacao():
    texto = "a pala-\nvra ficou correta"
    resultado = normalizar_texto(texto)
    assert "palavra" in resultado


if __name__ == "__main__":
    test_normalizar_valor()
    test_normalizar_data_numerica()
    test_normalizar_data_extenso()
    test_segmentar_sentenca()
    test_normalizar_texto_hifenacao()
    print("Todos os testes de ingestão passaram.")
