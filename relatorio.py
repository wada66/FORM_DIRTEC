from fpdf import FPDF
from datetime import datetime

def gerar_pdf(formulario, caminho):
    pdf = FPDF()
    pdf.add_page()

    # Cabeçalho
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Relatório de Processo", ln=True, align="C")
    pdf.set_font("Arial", "", 12)
    data_geracao = datetime.now().strftime("%d/%m/%Y %H:%M")
    pdf.cell(0, 10, f"Gerado em: {data_geracao}", ln=True, align="C")
    pdf.ln(10)

    def add_row(chave, valor):
        pdf.set_font("Arial", "B", 12)
        # legenda alinhada à direita, largura fixa 50
        pdf.cell(50, 10, f"{chave}:", border=0, align='R')  
        pdf.set_font("Arial", "", 12)
        # dado alinhado à esquerda, largura restante (0)
        pdf.cell(0, 10, str(valor), border=0, ln=True, align='L')  


    # Adiciona apenas campos preenchidos
    for chave, valor in formulario.items():
        if valor is not None and valor != "" and valor != "None" and str(valor).strip() != "":
            add_row(chave.capitalize().replace("_", " "), valor)
            pdf.ln(2)

    # Rodapé com número da página
    pdf.set_y(-15)
    pdf.set_font("Arial", "I", 8)
    pdf.cell(0, 10, f"Página {pdf.page_no()}", align="C")

    pdf.output(caminho)


