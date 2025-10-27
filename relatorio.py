from fpdf import FPDF
from datetime import datetime

from app import get_db_connection

LEGENDAS_AMIGAVEIS = {
    "numero_pasta": "Número Pasta",
    "observacoes": "Observações",
    "solicitacao_requerente": "Solicitação do Requerente",
    "resposta_departamento": "Resposta do Departamento",
    "responsavel_analise_cpf" : "Responsável pela Análise",
    "municipio" : "Município",
    "tramitacao": "Tramitação",
    "zona_urbana" : "Zona Urbana",
    "macrozona_municipal" : "Macrozona Municipal",
    "situacao_localizacao" : "Situação Localização",
    "responsavel_localizacao_cpf" : "Responsável Localização",
    "nome_requerente" : "Nome do Requerente",
    "tipo_de_requerente" : "Tipo de Requerente",
    "cpf_cnpj_requerente" : "CPF ou CNPJ do Requerente",
    "nome_proprietario" : "Nome do Proprietário",
    "cpf_cnpj_proprietario" : "CPF ou CNPJ do Propietário",
    "matricula_imovel" : "Matrícula do Imóvel",
    "apa" : "APA",
    "zona_apa" : "Zona APA",
    "utp" : "UTP",
    "zona_utp" : "Zona UTP",
    "nome_ou_loteamento_do_condominio_a_ser_aprovado" : "Condomínio a ser aprovado",
    "cnpj_requerente" : "CNPJ Requerente",
    "cpf_requerente" : "CPF Requerente"
}


def gerar_pdf(formulario, caminho):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_margins(left=20, top=15, right=20)
    pdf.set_font("Arial", "", 12)
    data_geracao = datetime.now().strftime("%d/%m/%Y %H:%M")
    pdf.cell(0, 10, f"Gerado em: {data_geracao}", ln=True, align="C")
    pdf.ln(10)

    # Cabeçalho
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Relatório de Processo", ln=True, align="C")
    pdf.set_font("Arial", "", 12)
    pdf.ln(10)

    # 🎯 SUBSTITUIR CPFs PELOS NOMES (VERSÃO MELHORADA)
    campos_para_substituir = {
        "responsavel_analise_cpf": "tecnico",  # 👈 MUDEI OS NOMES AQUI
        "responsavel_localizacao_cpf": "tecnico",  # 👈 E AQUI
    }

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for campo, tipo in campos_para_substituir.items():
                valor = formulario.get(campo)
                if not valor:
                    continue
                if tipo == "tecnico":
                    cur.execute("SELECT nome_tecnico FROM tecnico WHERE cpf_tecnico = %s", (valor,))
                    result = cur.fetchone()
                    if result:
                        formulario[campo] = result[0]  # 👈 SUBSTITUI PELO NOME
                        print(f"🔧 Substituído {campo}: {valor} -> {result[0]}")
                    else:
                        formulario[campo] = "Desconhecido"

    # Função para adicionar linha no PDF
    def add_row(chave, valor):
        legenda = LEGENDAS_AMIGAVEIS.get(chave, chave.capitalize().replace("_", " "))
        pdf.set_font("Arial", "B", 12)
        pdf.cell(50, 10, f"{legenda}:", border=0, align='R')
        pdf.set_font("Arial", "", 12)
        pdf.cell(0, 10, str(valor), border=0, ln=True, align='L')

    for chave, valor in formulario.items():
        if chave == "finalizar":
            continue         
        if valor and str(valor).strip().lower() != "none":
            add_row(chave, valor)
            pdf.ln(2)

    # Rodapé
    pdf.set_y(-15)
    pdf.set_font("Arial", "I", 8)
    pdf.cell(0, 10, f"Página {pdf.page_no()}", align="C")

    pdf.output(caminho)


