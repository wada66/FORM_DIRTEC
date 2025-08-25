from flask import Flask, render_template, request, redirect, url_for, session, send_file, jsonify, abort 
import psycopg2
from psycopg2 import sql
from datetime import date, timedelta, datetime
import os
import tempfile
import glob
import time
from relatorio import gerar_pdf
from dotenv import load_dotenv
import numpy as np

# Carregar variáveis do .env
load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

conn = psycopg2.connect(
    host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASSWORD
)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')


def calcular_dias_uteis(inicio_str, fim_str):
    if not inicio_str or not fim_str:
        return None
    try:
        inicio = datetime.strptime(inicio_str, "%Y-%m-%d").date()
        fim = datetime.strptime(fim_str, "%Y-%m-%d").date()
        return int(np.busday_count(inicio, fim))
    except Exception as e:
        print("Erro ao calcular dias úteis:", e)
        return None


def carregar_enum(nome_enum):
    cur = conn.cursor()
    cur.execute(sql.SQL("SELECT unnest(enum_range(NULL::{}))").format(sql.Identifier(nome_enum)))
    valores = [row[0] for row in cur.fetchall()]
    cur.close()
    return valores


@app.route("/")
def index():
    cur = conn.cursor()

    # Enumerados fixos do formulário
    solicitacoes_respostas = ['ANUÊNCIA PRÉVIA', 'CONSULTA PRÉVIA', 'DESPACHO', 'INFORMAÇÃO', 'PARECER', 'REVALIDAÇÃO']
    tramitacoes = [
        'ANÁLISE', 'ARQUIVADO', 'DEVOLVIDO', 'ENCAMINHADO EXT', 'ENCAMINHADO INT',
        'LOCALIZAÇÃO', 'RETORNOU P/ ANÁLISE', 'RETORNOU PRA LOCALIZAÇÃO',
        'SOBRESTADO 01', 'SOBRESTADO 02', 'SOBRESTADO 03', 'SOBRESTADO 04', 'SOBRESTADO 05',
        '(P/ASSINAR)', '*PRIORIDADE*'
    ]
    tipologias = [
        'CONDOMÍNIO EDILÍCIO', 'CONDOMÍNIO DE LOTES', 'CURVA DE INUNDAÇÃO',
        'DESAFETAÇÃO/AFETAÇÃO', 'DESMEMBRAMENTO', 'DIRETRIZ VIÁRIA',
        'LOTEAMENTO', 'MANANCIAL', 'OUTROS', 'REURB',
        'USO DO SOLO', 'ZONEAMENTO', '(MP - AÇÃO JUDICIAL)'
    ]
    situacoes_localizacao = ['LOCALIZADA', 'NÃO PRECISA LOCALIZAR']

    # Buscar servidores/técnicos
    cur.execute("SELECT cpf_tecnico, nome_tecnico, setor_tecnico FROM tecnico")
    tecnico = cur.fetchall()

    # Buscar municípios
    cur.execute("SELECT nome_municipio FROM municipio")
    municipio = [row[0] for row in cur.fetchall()]
    
    # Para classificacao_diretriz_viaria (em vez de carregar_enum)
    cur.execute("SELECT DISTINCT classificacao_metropolitana FROM sistema_viario WHERE classificacao_metropolitana IS NOT NULL")
    classificacao_diretriz_viaria = [row[0] for row in cur.fetchall()]

    # Para faixa de servidão (em vez de usar enum)
    cur.execute("SELECT DISTINCT tipo FROM faixa_servidao WHERE tipo IS NOT NULL")
    faixa_servidao = [row[0] for row in cur.fetchall()]

    # Para curva de inundação
    cur.execute("SELECT DISTINCT tipo_curva FROM curva_inundacao WHERE tipo_curva IS NOT NULL")
    curva_de_inundacao = [row[0] for row in cur.fetchall()]

    # Para APA
    cur.execute("SELECT DISTINCT nome_apa FROM apa WHERE nome_apa IS NOT NULL")
    apa = [row[0] for row in cur.fetchall()]

    # Para UTP
    cur.execute("SELECT DISTINCT nome_utp FROM utp WHERE nome_utp IS NOT NULL")
    utp = [row[0] for row in cur.fetchall()]

    # Para manancial
    cur.execute("SELECT DISTINCT tipologia FROM manancial WHERE tipologia IS NOT NULL")
    manancial = [row[0] for row in cur.fetchall()]


    enums = {
            "classificacao_diretriz_viaria": classificacao_diretriz_viaria,
            "faixa_servidao": faixa_servidao,
            "curva_de_inundacao": curva_de_inundacao,
            "apa": apa,
            "utp": utp,
            "manancial": manancial
    }
     
    # PDF já gerado
    caminho_pdf = session.get("caminho_pdf")
    protocolo_pdf = session.get("protocolo_pdf")

    cur.close()
    
    return render_template(
        "formulario.html",
        solicitacoes_respostas=solicitacoes_respostas,
        tramitacoes=tramitacoes,
        tipologias=tipologias,
        situacoes_localizacao=situacoes_localizacao,
        tecnico=tecnico,
        municipio=municipio,
        apa=apa,
        utp=utp,
        enums=enums,
        caminho_pdf=caminho_pdf,
        protocolo_pdf=protocolo_pdf
    )


@app.route("/inserir", methods=["POST"])
def inserir():
    cur = conn.cursor()
    data_entrada = date.today()
    data_previsao_resposta = data_entrada + timedelta(days=40)

    # Capturar dados do formulário
    formulario = request.form.to_dict(flat=True)

    # Ajustes de boolean
    interesse_social = formulario.get("interesse_social") == "on"
    lei_inclui_perimetro_urbano = formulario.get("lei_inclui_perimetro_urbano") == "on"

    # Datas
    inicio_localizacao = formulario.get("inicio_localizacao") or None
    fim_localizacao = formulario.get("fim_localizacao") or None
    inicio_analise = datetime.now()
    fim_analise = datetime.now() if formulario.get("finalizar") else None

    dias_uteis_localizacao = calcular_dias_uteis(inicio_localizacao, fim_localizacao)
    dias_uteis_analise = calcular_dias_uteis(inicio_analise.strftime("%Y-%m-%d"), fim_analise.strftime("%Y-%m-%d") if fim_analise else None)

    try:
        # Tabelas auxiliares
        # Requerente
        if formulario.get("cpf_cnpj_requerente") and formulario.get("nome_requerente") and formulario.get("tipo_de_requerente"):
            cur.execute("""
                INSERT INTO requerente (cpf_cnpj_requerente, nome_requerente, tipo_de_requerente)
                VALUES (%s,%s,%s) ON CONFLICT (cpf_cnpj_requerente) DO NOTHING
            """, (formulario["cpf_cnpj_requerente"], formulario["nome_requerente"], formulario["tipo_de_requerente"]))

        # Proprietário
        if formulario.get("cpf_cnpj_proprietario") and formulario.get("nome_proprietario"):
            cur.execute("""
                INSERT INTO proprietario (cpf_cnpj_proprietario, nome_proprietario)
                VALUES (%s,%s) ON CONFLICT (cpf_cnpj_proprietario) DO NOTHING
            """, (formulario["cpf_cnpj_proprietario"], formulario["nome_proprietario"]))

        # Imóvel
        if formulario.get("matricula_imovel"):
            cur.execute("""
                INSERT INTO imovel (
                matricula_imovel, zona_municipal, zona_estadual, classificacao_diretriz_viaria_metropolitana,
                faixa_servidao, curva_de_inundacao, apa, utp, manancial, area,
                localidade_imovel, latitude, longitude, lei_inclui_perimetro_urbano
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (matricula_imovel) DO NOTHING
            """, (
            formulario.get("matricula_imovel"),
            formulario.get("zona_municipal"),
            formulario.get("zona_estadual"),
            formulario.get("classificacao_diretriz"),
            formulario.get("faixa_servidao"),
            formulario.get("curva_de_inundacao"),
            formulario.get("apa"),
            formulario.get("utp"),
            formulario.get("manancial"),
            float(formulario["area"]) if formulario.get("area") else None,
            formulario.get("localidade_imovel"),
            float(formulario["latitude"]) if formulario.get("latitude") else None,
            float(formulario["longitude"]) if formulario.get("longitude") else None,
            lei_inclui_perimetro_urbano
         ))


        # Proprietário-Imóvel
        if formulario.get("cpf_cnpj_proprietario") and formulario.get("matricula_imovel"):
            cur.execute("""
                INSERT INTO proprietario_imovel (cpf_cnpj_proprietario, matricula_imovel)
                VALUES (%s,%s) ON CONFLICT DO NOTHING
            """, (formulario["cpf_cnpj_proprietario"], formulario["matricula_imovel"]))

        # Pasta
        if formulario.get("numero_pasta"):
            cur.execute("""
                INSERT INTO pasta (numero_pasta)
                VALUES (%s) ON CONFLICT (numero_pasta) DO NOTHING
            """, (formulario["numero_pasta"],))

        # Processo principal
        cur.execute("""
            INSERT INTO processo (
                protocolo, observacoes, matricula_imovel, numero_pasta, solicitacao_requerente,
                resposta_departamento, tramitacao, setor, tipologia, municipio, situacao_localizacao,
                responsavel_localizacao_cpf, inicio_localizacao, fim_localizacao, situacao_analise,
                responsavel_analise_cpf, inicio_analise, fim_analise, dias_uteis_analise,
                dias_uteis_localizacao, requerente_cpf_cnpj, proprietario_cpf_cnpj,
                nome_ou_loteamento_do_condominio_a_ser_aprovado, interesse_social,
                data_entrada, data_previsao_resposta
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            formulario.get("protocolo"),
            formulario.get("observacoes"),
            formulario.get("matricula_imovel"),
            formulario.get("numero_pasta"),
            formulario.get("solicitacao_requerente"),
            formulario.get("resposta_departamento"),
            formulario.get("tramitacao"),
            formulario.get("setor"),  # automático do técnico escolhido
            formulario.get("tipologia"),
            formulario.get("municipio"),
            formulario.get("situacao_localizacao"),
            formulario.get("responsavel_localizacao_cpf"),
            inicio_localizacao,
            fim_localizacao,
            "FINALIZADA" if formulario.get("finalizar") else "NÃO FINALIZADA",
            formulario.get("responsavel_analise_cpf"),
            inicio_analise,
            fim_analise,
            dias_uteis_analise,
            dias_uteis_localizacao,
            formulario.get("cpf_cnpj_requerente"),
            formulario.get("cpf_cnpj_proprietario"),
            formulario.get("nome_ou_loteamento_do_condominio_a_ser_aprovado"),
            interesse_social,
            data_entrada,
            data_previsao_resposta
        ))

        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close()
        return f"Erro ao inserir processo: {e}", 500

    # Gerar PDF
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
        gerar_pdf(formulario, f.name)
        session["caminho_pdf"] = f.name
        session["protocolo_pdf"] = formulario.get("protocolo")

    cur.close()
    return redirect(url_for("index"))


@app.route("/baixar_pdf")
def baixar_pdf():
    caminho = session.get("caminho_pdf")
    if caminho and os.path.exists(caminho):
        return send_file(caminho, as_attachment=True, download_name="relatorio.pdf")
    else:
        return "Arquivo não encontrado ou expirado", 404
    
@app.route("/get_zonas_urbanas/<municipio>")
def get_zonas_urbanas(municipio):
    conn = psycopg2.connect(
        host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASSWORD
    )
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT sigla_zona_urbana
        FROM zona_urbana
        WHERE TRIM(municipio_nome) = %s
        ORDER BY sigla_zona_urbana

    """, (municipio,))
    dados = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify(dados)    
    
@app.route("/get_macrozonas/<municipio>")
def get_macrozonas(municipio):
    conn = psycopg2.connect(
        host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASSWORD
    )
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT sigla_macrozona
        FROM macrozona_municipal
        WHERE TRIM(municipio_nome) = %s
        ORDER BY sigla_macrozona

    """, (municipio,))
    dados = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify(dados)


@app.route("/get_zonas_apa/<apa>")
def get_zonas_apa(apa):
    conn = psycopg2.connect(
    host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASSWORD
)
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT nome_zona_apa
        FROM zona_apa
        WHERE TRIM(apa) = %s
        ORDER BY nome_zona_apa
    """, (apa,))
    dados = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify(dados)

@app.route("/get_zonas_utp/<utp>")
def get_zonas_utp(utp):
    conn = psycopg2.connect(
    host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASSWORD
)
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT nome_zona_utp
        FROM zona_utp
        WHERE TRIM(utp) = %s
        ORDER BY nome_zona_utp
    """, (utp,))
    dados = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify(dados)


if __name__ == "__main__":
    app.run(debug=True)
