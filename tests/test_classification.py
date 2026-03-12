# tests/test_classification.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.classification import classificar_verba, mapear_para_pjecalc


def test_classificar_horas_extras():
    verba = {"nome_sentenca": "Horas Extras", "percentual": 0.5, "confianca": 0.9}
    resultado = classificar_verba(verba)
    assert resultado["mapeada"] is True
    assert resultado["lancamento"] == "Expresso"
    assert resultado["incidencia_fgts"] is True


def test_classificar_13_salario():
    verba = {"nome_sentenca": "13º Salário Proporcional", "confianca": 0.9}
    resultado = classificar_verba(verba)
    assert resultado["mapeada"] is True
    assert resultado["caracteristica"] == "13o Salario"


def test_mapear_multiplas_verbas():
    verbas = [
        {"nome_sentenca": "Horas Extras", "percentual": 0.5, "confianca": 0.9},
        {"nome_sentenca": "Adicional Noturno", "percentual": 0.2, "confianca": 0.85},
        {"nome_sentenca": "Dano Moral", "valor_informado": 5000.0, "confianca": 0.95},
    ]
    mapeado = mapear_para_pjecalc(verbas)
    assert len(mapeado["predefinidas"]) >= 2
    assert len(mapeado["reflexas_sugeridas"]) >= 2


def test_verba_nao_reconhecida():
    verba = {"nome_sentenca": "Gratificação Especial de Risco", "confianca": 0.7}
    resultado = classificar_verba(verba)
    # Não deve levantar exceção; pode ser mapeada ou não
    assert "nome_sentenca" in resultado


if __name__ == "__main__":
    test_classificar_horas_extras()
    test_classificar_13_salario()
    test_mapear_multiplas_verbas()
    test_verba_nao_reconhecida()
    print("Todos os testes de classificação passaram.")
