"""Utenti con nome e password gestiti dalla pagina Impostazioni."""

from __future__ import annotations

import json
import stat

import pytest
from fastapi.testclient import TestClient

from saporesta import utenti


@pytest.fixture(autouse=True)
def config_temporanea(tmp_path, monkeypatch):
    monkeypatch.setenv("SAPORESTA_CONFIG", str(tmp_path / "cfg" / "impostazioni.json"))
    monkeypatch.setenv("SAPORESTA_DATI", str(tmp_path / "pratiche"))
    monkeypatch.delenv("SAPORESTA_PASSWORD", raising=False)


@pytest.fixture
def client():
    from saporesta.web.app import app
    return TestClient(app)


def entra(client, nome, password):
    return client.post("/accesso", data={"utente": nome, "password": password, "dopo": "/impostazioni"})


# ------------------------------------------------------------------- archivio

def test_password_mai_in_chiaro_e_file_protetto():
    utenti.aggiungi("Mario.Rossi", "segreta-123")
    testo = utenti.percorso().read_text()
    assert "segreta-123" not in testo and "mario.rossi" in testo
    assert stat.S_IMODE(utenti.percorso().stat().st_mode) == 0o600
    assert utenti.autentica("MARIO.ROSSI ", "segreta-123") == "mario.rossi"
    assert utenti.autentica("mario.rossi", "sbagliata") is None


def test_regole_nomi_e_password():
    with pytest.raises(utenti.ErroreUtenti):
        utenti.aggiungi("admin", "abbastanza-lunga")
    with pytest.raises(utenti.ErroreUtenti):
        utenti.aggiungi("mario", "corta")
    with pytest.raises(utenti.ErroreUtenti):
        utenti.aggiungi("nome con spazi", "abbastanza-lunga")
    utenti.aggiungi("mario", "abbastanza-lunga")
    with pytest.raises(utenti.ErroreUtenti):
        utenti.aggiungi("mario", "altra-password")


def test_primo_utente_amministratore_senza_password_di_emergenza():
    u = utenti.aggiungi("mario", "abbastanza-lunga", amministratore=False)
    assert u.amministratore
    with pytest.raises(utenti.ErroreUtenti):
        utenti.imposta_amministratore("mario", False)  # resterebbe senza amministratori
    utenti.aggiungi("anna", "abbastanza-lunga")
    with pytest.raises(utenti.ErroreUtenti):
        utenti.rimuovi("mario")


def test_emergenza_admin(monkeypatch):
    monkeypatch.setenv("SAPORESTA_PASSWORD", "parola-di-prova")
    assert utenti.autentica("admin", "parola-di-prova") == "admin"
    assert utenti.autentica("admin", "altra") is None
    assert not utenti.aggiungi("anna", "abbastanza-lunga").amministratore  # c'è già l'admin di emergenza
    utenti.rimuovi("anna")


# ------------------------------------------------------------------- portale

def test_amministratore_crea_utente_che_poi_entra(client, monkeypatch):
    monkeypatch.setenv("SAPORESTA_PASSWORD", "parola-di-prova")
    entra(client, "admin", "parola-di-prova")
    r = client.post("/impostazioni/utenti/aggiungi",
                    data={"nome": "anna", "password": "password-anna", "conferma": "password-anna"})
    assert "Utente «anna» creato" in r.text
    client.post("/esci")
    r = entra(client, "anna", "password-anna")
    assert r.status_code == 200 and "La tua password" in r.text and "Aggiungi un utente" not in r.text
    # un utente normale non può toccare chiavi, utenti o carta intestata
    assert client.post("/impostazioni/aggiungi", data={"fornitore": "gemini", "valore": "x"}).status_code == 403
    assert client.post("/impostazioni/utenti/aggiungi",
                       data={"nome": "bruno", "password": "12345678", "conferma": "12345678"}).status_code == 403
    assert utenti.trova("bruno") is None


def test_password_cambiata_invalida_le_sessioni(client, monkeypatch):
    monkeypatch.setenv("SAPORESTA_PASSWORD", "parola-di-prova")
    utenti.aggiungi("anna", "password-anna")
    entra(client, "anna", "password-anna")
    vecchio = client.cookies.get("saporesta_sessione")
    r = client.post("/impostazioni/mia-password",
                    data={"attuale": "password-anna", "password": "nuova-password", "conferma": "nuova-password"})
    assert "è stata cambiata" in r.text  # resta dentro con la nuova sessione
    from saporesta.web import accesso
    assert accesso.utente_da_cookie(vecchio) is None
    assert utenti.autentica("anna", "nuova-password") == "anna"


def test_utente_eliminato_perde_la_sessione(client, monkeypatch):
    monkeypatch.setenv("SAPORESTA_PASSWORD", "parola-di-prova")
    utenti.aggiungi("anna", "password-anna")
    entra(client, "anna", "password-anna")
    utenti.rimuovi("anna")
    assert client.get("/", follow_redirects=False).status_code == 303


def test_primo_utente_dal_portale_senza_password_attiva_l_accesso(client):
    assert client.get("/", follow_redirects=False).status_code == 200  # portale locale aperto
    r = client.post("/impostazioni/utenti/aggiungi",
                    data={"nome": "mario", "password": "password-mario", "conferma": "password-mario"})
    assert "Utente «mario» creato" in r.text and "mario" in r.text
    nuovo = TestClient(client.app)
    assert nuovo.get("/", follow_redirects=False).status_code == 303  # ora serve l'accesso


def test_cookie_di_un_utente_non_vale_per_un_altro(monkeypatch):
    from saporesta.web import accesso
    monkeypatch.setenv("SAPORESTA_PASSWORD", "parola-di-prova")
    utenti.aggiungi("anna", "password-anna")
    c = accesso.crea_cookie("anna")
    assert accesso.utente_da_cookie(c) == "anna"
    falso = "admin" + c[len("anna"):]
    assert accesso.utente_da_cookie(falso) is None
