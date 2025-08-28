from flask import Flask, render_template, request, redirect, url_for, session, send_file, jsonify, session, abort
import psycopg2
from datetime import date, timedelta, datetime
import os
import tempfile
from dotenv import load_dotenv
import numpy as np


load_dotenv()


DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")


app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')


def get_db_connection():
    """Abre conexão nova com o banco de dados."""
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )


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


@app.route("/")
def index():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Enumerados fixos do formulário
            solicitacoes_respostas = [
                'ANUÊNCIA PRÉVIA', 'CONSULTA PRÉVIA', 'DESPACHO', 'INFORMAÇÃO', 'PARECER', 'REVALIDAÇÃO'
            ]
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

            cur.execute("SELECT cpf_tecnico, nome_tecnico, setor_tecnico FROM tecnico")
            tecnico = cur.fetchall()

            cur.execute("SELECT nome_municipio FROM municipio")
            municipio = [row[0] for row in cur.fetchall()]

            cur.execute("SELECT DISTINCT classificacao_metropolitana FROM sistema_viario WHERE classificacao_metropolitana IS NOT NULL")
            classificacao_diretriz_viaria = [row[0] for row in cur.fetchall()]

            cur.execute("SELECT DISTINCT tipo FROM faixa_servidao WHERE tipo IS NOT NULL")
            faixa_servidao = [row[0] for row in cur.fetchall()]

            cur.execute("SELECT DISTINCT tipo_curva FROM curva_inundacao WHERE tipo_curva IS NOT NULL")
            curva_de_inundacao = [row[0] for row in cur.fetchall()]

            cur.execute("SELECT DISTINCT nome_apa FROM apa WHERE nome_apa IS NOT NULL")
            apa = [row[0] for row in cur.fetchall()]

            cur.execute("SELECT DISTINCT nome_utp FROM utp WHERE nome_utp IS NOT NULL")
            utp = [row[0] for row in cur.fetchall()]

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

            caminho_pdf = session.get("caminho_pdf")
            protocolo_pdf = session.get("protocolo_pdf")

    return render_template(
        "formulario.html",
        solicitacoes_respostas=solicitacoes_respostas,
        tramitacoes=tramitacoes,
        tipologias=tipologias,
        situacoes_localizacao=situacoes_localizacao,
        tecnico=tecnico,
        municipio=municipio,
        enums=enums,
        caminho_pdf=caminho_pdf,
        protocolo_pdf=protocolo_pdf
    )


@app.route("/inserir", methods=["POST"])
def inserir():
    formulario = request.form.to_dict(flat=True)

    interesse_social = formulario.get("interesse_social") == "on"
    lei_inclui_perimetro_urbano = formulario.get("lei_inclui_perimetro_urbano") == "on"

    inicio_localizacao = formulario.get("inicio_localizacao") or None
    fim_localizacao = formulario.get("fim_localizacao") or None
    inicio_analise = datetime.now()
    fim_analise = datetime.now() if formulario.get("finalizar") else None

    dias_uteis_localizacao = calcular_dias_uteis(inicio_localizacao, fim_localizacao)
    dias_uteis_analise = calcular_dias_uteis(inicio_analise.strftime("%Y-%m-%d"), fim_analise.strftime("%Y-%m-%d") if fim_analise else None)

    data_entrada = date.today()
    data_previsao_resposta = data_entrada + timedelta(days=40)

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Inserir requerente
                if formulario.get("cpf_cnpj_requerente") and formulario.get("nome_requerente") and formulario.get("tipo_de_requerente"):
                    cur.execute("""
                        INSERT INTO requerente (cpf_cnpj_requerente, nome_requerente, tipo_requerente)
                        VALUES (%s, %s, %s) ON CONFLICT (cpf_cnpj_requerente) DO NOTHING
                    """, (formulario["cpf_cnpj_requerente"], formulario["nome_requerente"], formulario["tipo_de_requerente"]))

                # Inserir proprietário
                if formulario.get("cpf_cnpj_proprietario") and formulario.get("nome_proprietario"):
                    cur.execute("""
                        INSERT INTO proprietario (cpf_cnpj_proprietario, nome_proprietario)
                        VALUES (%s, %s) ON CONFLICT (cpf_cnpj_proprietario) DO NOTHING
                    """, (formulario["cpf_cnpj_proprietario"], formulario["nome_proprietario"]))

                # Inserir imóvel
                zona_apa_nome = formulario.get("zona_apa")
                zona_utp_nome = formulario.get("zona_utp")

                # Obter id_zona_apa a partir do nome
                cur.execute("SELECT id_zona_apa FROM zona_apa WHERE nome_zona_apa = %s", (zona_apa_nome,))
                zona_apa_id = cur.fetchone()
                zona_apa_id = zona_apa_id[0] if zona_apa_id else None

                # Obter id_zona_utp a partir do nome
                cur.execute("SELECT id_zona_utp FROM zona_utp WHERE nome_zona_utp = %s", (zona_utp_nome,))
                zona_utp_id = cur.fetchone()
                zona_utp_id = zona_utp_id[0] if zona_utp_id else None

                # Inserção no imóvel usando os ids obtidos
                cur.execute("""
                    INSERT INTO imovel (matricula_imovel, zona_apa, zona_utp, classificacao_viaria, curva_inundacao, manancial, area, localidade_imovel, latitude, longitude, faixa_servidao)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (matricula_imovel) DO NOTHING
                """, (
                    formulario.get("matricula_imovel"),
                    zona_apa_id,
                    zona_utp_id,
                    formulario.get("classificacao_viaria") or None,
                    formulario.get("curva_inundacao") or None,
                    formulario.get("manancial") or None,
                    formulario.get("area") or None,
                    formulario.get("localidade_imovel") or None,
                    formulario.get("latitude") or None,
                    formulario.get("longitude") or None,
                    formulario.get("faixa_servidao") or None,
                ))

                # Depois de inserir imóvel
                if formulario.get("matricula_imovel") and formulario.get("municipio"):
                    cur.execute("""
                        INSERT INTO imovel_municipio (imovel_matricula, municipio_nome)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING
                    """, (formulario["matricula_imovel"], formulario["municipio"]))

                # Conectar proprietário ao imóvel (tabela associativa)
                if formulario.get("cpf_cnpj_proprietario") and formulario.get("matricula_imovel"):
                    cur.execute("""
                        INSERT INTO proprietario_imovel (proprietario_cpf_cnpj, imovel_matricula)
                        VALUES (%s, %s) ON CONFLICT DO NOTHING
                    """, (formulario["cpf_cnpj_proprietario"], formulario["matricula_imovel"]))

                # Inserir pasta
                if formulario.get("numero_pasta"):
                    cur.execute("""
                        INSERT INTO pasta (numero_pasta)
                        VALUES (%s) ON CONFLICT (numero_pasta) DO NOTHING
                    """, (formulario["numero_pasta"],))

                # Inserir processo principal
                cur.execute("""
                    INSERT INTO processo (
                        protocolo, observacoes, imovel_matricula, pasta_numero, solicitacao_requerente,
                        resposta_departamento, tramitacao, setor_nome, tipologia, situacao_localizacao,
                        responsavel_localizacao, inicio_localizacao, fim_localizacao,
                        dias_uteis_localizacao, requerente, 
                        nome_ou_loteamento_do_condominio_a_ser_aprovado, interesse_social,
                        data_entrada
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    formulario.get("protocolo"),
                    formulario.get("observacoes"),
                    formulario.get("matricula_imovel"),
                    formulario.get("numero_pasta"),
                    formulario.get("solicitacao_requerente"),
                    formulario.get("resposta_departamento"),
                    formulario.get("tramitacao"),
                    formulario.get("setor") or None,
                    formulario.get("tipologia"),
                    formulario.get("situacao_localizacao"),
                    formulario.get("responsavel_localizacao_cpf"),
                    inicio_localizacao,
                    fim_localizacao,
                    dias_uteis_localizacao,
                    formulario.get("cpf_cnpj_requerente"),
                    formulario.get("nome_ou_loteamento_do_condominio_a_ser_aprovado"),
                    interesse_social,
                    data_entrada,
                ))

                # Inserir análise 
                cur.execute("""
                    INSERT INTO analise (situacao_analise, responsavel_analise, inicio_analise, fim_analise, dias_uteis_analise, ultima_movimentacao, processo_protocolo)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    "NÃO FINALIZADA" if not formulario.get("finalizar") else "FINALIZADA",
                    formulario.get("responsavel_analise") or None,
                    inicio_analise,
                    fim_analise,
                    dias_uteis_analise,
                    datetime.now().date(),
                    formulario.get("protocolo")
                ))

            conn.commit()

        # Gerar PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
            from relatorio import gerar_pdf
            gerar_pdf(formulario, f.name)
            session["caminho_pdf"] = f.name
            session["protocolo_pdf"] = formulario.get("protocolo")

        return redirect(url_for("index"))

    except Exception as e:
        print(f"Erro na inserção: {e}")
        return f"Erro ao inserir dados: {e}", 500


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

@app.route('/baixar_pdf')
def baixar_pdf():
    caminho_pdf = session.get("caminho_pdf")
    if caminho_pdf:
        try:
            return send_file(caminho_pdf, as_attachment=True)
        except FileNotFoundError:
            return "Arquivo PDF não encontrado", 404
    else:
        abort(404)


if __name__ == "__main__":
    app.run(debug=True)
