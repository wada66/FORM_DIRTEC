# relatorio.py
from fpdf import FPDF  # pip install fpdf

def gerar_pdf(formulario, caminho):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    for chave, valor in formulario.items():
        pdf.cell(0, 10, f"{chave}: {valor}", ln=True)
    
    pdf.output(caminho)
