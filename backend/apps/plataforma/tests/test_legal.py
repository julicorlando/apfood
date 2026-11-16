"""Termos de uso e política de privacidade."""

from apps.plataforma.cadastro import RESERVADOS


def test_paginas_legais_abrem_e_avisam_rascunho(client, settings):
    for url, titulo in (("/termos/", "Termos de uso"), ("/privacidade/", "Política de privacidade")):
        html = client.get(url).content.decode()
        assert titulo in html and "APFOOD_LEGAL_" in html


def test_preenchidas_saem_do_rascunho(client, settings):
    settings.APFOOD_LEGAL = {"RAZAO_SOCIAL": "Axion Web Digital LTDA", "CNPJ": "00.000.000/0001-00",
                             "EMAIL": "privacidade@exemplo.com", "CIDADE_FORO": "Recife/PE", "ATUALIZADO_EM": "16/11/2026"}
    html = client.get("/privacidade/").content.decode()
    assert "Axion Web Digital LTDA" in html and "privacidade@exemplo.com" in html and "APFOOD_LEGAL_" not in html


def test_links_no_cadastro_e_no_login(client, db):
    assert "/termos/" in client.get("/planos/").content.decode()
    assert "/privacidade/" in client.get("/painel/entrar/").content.decode()
    assert {"termos", "privacidade"} <= RESERVADOS
